# Plan: make buy & hold reachable in the GA search space

## Context

**The question that prompted this:** NVDA is the strategy's worst case — **0 of 140
completed runs beat buy & hold**, median excess **-38.4%/yr**, best -18.2%/yr. On the
5-year slice buy & hold returns +88%/yr and the best strategy run manages +68%. Why
can't the optimizer simply tune itself down to buy & hold and stop losing?

**The answer: buy & hold is not representable in the gene space.** It is not that the
GA searches badly — it is that the target is outside the search domain. Three hard
floors in `backtest_stocks.py`, all hard-coded as *function defaults* on
`genetic_optimize_params` (:1812-1813) and `tune_ga_hyperparams` (:1996-1997):

| gene | bound | consequence |
|---|---|---|
| `drawdown_exit_pct` | `(2.5, 4.0)` | **the binding constraint** — a 4% dip from peak while price < short EMA forces a full exit |
| `stop_loss` | `(8, 15)` | a 15% drop from entry always liquidates |
| `reentry_rebound_pct` | `(1.0, 3.0)` | minimum 1.0 — never re-enters immediately |

For scale: on `backtest/data/NVDA.csv`, rolling 6-month windows have a **median
peak-drawdown of 22.3%**. A 4% exit therefore fires in essentially every window. The
measured symptoms match exactly — `time_invested_pct` **never exceeds 73.3%** across all
140 runs, and median `missed_upside_after_exit_pct` is **110.6%**.

These four tuples are unreachable from the CLI. No call site passes them; the
`resolve_profile_gene_bounds` call at :2218-2226 discards four of six results via
`_, _, _, _`. The only override channel is a profile's `gene_bounds` dict.

**The irony worth recording:** the GA objective *already* asks for buy-&-hold-like
behaviour and cannot deliver it. Fitness (:1904-1917) is
`2.0*excess_return + 6.0*sharpe - 0.30*max_dd - 0.10*num_trades - 0.5*uptrend_cash_pct - missed_upside_penalty`.
Excess-vs-B&H, time-in-cash-during-uptrend and churn are all penalised. The optimizer is
being asked to minimise time in cash while the search space guarantees a floor on it.

**Intended outcome:** buy & hold becomes a *reachable corner* the GA may choose at 1.0x
exposure — giving the strategy a floor of roughly "never much worse than B&H" — while it
stays free to trade when trading genuinely helps. The existing trading region
(`stop_loss` 8-15, `drawdown_exit` 2.5-4) remains fully inside the new bounds.

## Key discovery: this is a bounds change, not a strategy-logic change

`price_change_pct` (:1401) and `drawdown_from_peak_pct` (:1479) are both floored at -100
(price cannot go below zero). So **any `stop_loss` or `drawdown_exit_pct` = 100 can never
fire**, while `use_stop_loss=True` stays as-is. No edit to the strategy core is needed.

Two follow-on simplifications, both verified:
- The `current_price > short_ema_val` re-entry conjunct (:1429) is unreachable on the
  B&H path — the whole re-entry block is behind `if position < 1:` (:1413), and with no
  exits, position never drops. Leave it alone.
- `rsi_overbought` is the one gate not plumbed through `resolve_profile_gene_bounds`
  (it reaches the GA directly at :2420-2421 / :2472-2473), but `--rsi-overbought-bounds`
  **already exists as a CLI flag** (:355), and the RSI gate only affects the *first*
  entry. So no plumbing change is required for the core experiment.

## Changes

### 1. `backtest/backtest_stocks.py` — two new profiles

Both go in `STRATEGY_PROFILE_SETTINGS` (:100-274). `--strategy-profile` uses
`choices=sorted(STRATEGY_PROFILE_SETTINGS.keys())` (:377), so they are picked up
automatically.

**`buyhold-1x`** — an un-levered pure buy & hold control. Copy `qqq-buyhold-plus`
(:247-273) verbatim and change `exposure_multiplier` from `(1.0, 1.35)` (:256) to
`(1.0, 1.0)`. Same relationship `qqq-return-plus-nolev` (:224-246) has to
`qqq-return-plus`. This is the *first* thing to run — see Verification.

**`generic-bh-reachable`** — derived from `generic` (:101-118) so the only difference is
gene bounds, giving clean single-variable attribution against the 953 existing `generic`
runs. Copy the **entire** `generic` dict and replace `gene_bounds` with:

```python
"gene_bounds": {
    "stop_loss": (8, 101),           # >=100 can never fire; keeps 8-15 trading region
    "cooldown": (0, 3),
    "drawdown_exit_pct": (2.5, 101),  # the binding constraint, now escapable
    "reentry_rebound_pct": (0.0, 3.0),
    "exposure_multiplier": (1.0, 1.0),
},
```

Three traps that fail **silently**:
- The key is `"stop_loss"`, **not** `"stop_loss_pct"` — `resolve_profile_gene_bounds`
  reads `"stop_loss"` (:492) but `"drawdown_exit_pct"` (:494). Getting it wrong keeps
  `(8,15)` and the experiment looks like a null result.
- **Copy all 13 keys** from `generic`. `backtest_enhanced_dual_ema` subscripts the
  profile dict directly with no `.get` (:1230-1232, :1432-1434, :1490-1492, :1905); a
  missing key raises `KeyError` inside the GA, which is swallowed by `except Exception`
  (:1989) and surfaces only as an opaque `GA optimization error:`.
- Continuous gene `high` is **exclusive** (:1835, :1837). Write `(8, 101)`, not
  `(8, 100)`.

Do **not** set `always_invested` / `disable_*` on `generic-bh-reachable` — those *force*
B&H; the point is to make it choosable. (They also carry a latent bug: the RSI gate at
:1438-1441 is applied *after* the `always_invested` override and silently cancels it.
`qqq-buyhold-plus` has never been run, so this has never surfaced. Setting
`"rsi_overbought": (100, 100)` is not possible via profile today — hence
`--rsi-overbought-bounds 60 100` on the control run.)

### 2. `run_grid.ps1` — allow the new profiles

`ValidateSet` at :45 currently lists only `generic, qqq, qqq-return-plus,
qqq-buyhold-plus` — it already omits three existing profiles, so they are undriveable
from the grid. Add the two new names (and ideally the three missing ones), or drop
`ValidateSet` and let Python's `choices` reject bad values.

### 3. `backtest/analysis/` — profile-aware analysis (chosen: add to the toolkit)

Without this, `summarize.py --fund NVDA` pools new runs with the 140 existing `generic`
NVDA runs and reports blended medians that prove nothing.

- `sweep_data.py` — add `"profile": r.get("strategy_profile", "")` to the run dict built
  in `load_runs` (~:133-155). This is where the leverage rule and slice handling already
  live, per `analysis/README.md`.
- `summarize.py` — add `--profile` to argparse (:104-109) and filter; show the profile
  mix in the header so pooling is never silent.
- `dashboard.py` — add `--profile` (:1098-1102). Profile belongs as a *filter*, not a new
  chart; if more than one profile is present in a build, say so in the footer.

## Verification

**Step 1 — control first; this gates everything.**

```powershell
python backtest\backtest_stocks.py --data-file NVDA.csv --fund-group NVDA `
  --lookback-years 2 --offset-months 6 --pop_ranges 4 --gen_ranges 2 `
  --strategy-profile buyhold-1x --price-column "Adj Close" `
  --rsi-overbought-bounds 60 100 --reuse-tuned-params
```

Expect `excess_annualized_return_pct` ˜ 0 and `time_invested_pct` ˜ 100. **If it is not
flat, stop** — that means an accounting bug in walk-forward stitching (:2635-2645),
`carry_state` hand-off (:2539-2547) or annualization (:1635-1652), and every one of the
1000+ historical excess figures is suspect. That would be a far more important finding
than the strategy question. A small non-zero residual is expected and worth quantifying:
`buy_and_hold_strategy` (:1605-1618) prices off the first bar of the stitched frame while
the strategy enters at `trade_start_idx`.

**Step 2 — smoke-test the new bounds took effect.** One `generic-bh-reachable` run; check
the tuning log (:2017-2024) prints `SL=(8, 101) ... DDX=(2.5, 101)`. Cheapest possible
confirmation.

**Step 3 — matched sweep.** Same cells as the existing `generic` NVDA runs, since
`sweep_data.cell_key` keys comparability on `(depth, lookback, offset)`:

```powershell
.\run_grid.ps1 -Funds NVDA -StrategyProfile generic-bh-reachable `
  -LookbackYears 1,2,3 -OffsetMonths 3,6,9,12 -Population 4 -Generations 2 `
  -PriceColumn 'Adj Close' -LogFile nvda-bh-reachable.log
```

**Step 4 — evaluate.** `python backtest/analysis/summarize.py --fund NVDA --profile generic-bh-reachable`

| signal | current (generic) | expected if it worked |
|---|---|---|
| `time_invested_pct` | max **73.3** | reaches ~100 — **the falsifiable claim: the 73.3 ceiling must break** |
| `excess_annualized_return_pct` | median -38.4 | median ? ~0; worst case bounded near 0 |
| `last_stop_loss` / `last_drawdown_exit_pct` | =15 / =4.0 | values »15 / »4.0 — direct proof the GA used the new range |
| `trade_count` | tens | 0–2 on B&H-corner runs |
| `last_exposure_multiplier` | 1.0 | exactly 1.0 on every row (hard rule) |

The `last_*` columns (:2899-2906) are decisive: they distinguish "corner reachable and
chosen" from "corner reachable but not found".

**Step 5 — regression check.** Run one AAPL cell to confirm the wider bounds don't *hurt*
where the strategy is closer to competitive.

## Notes

**Search-space risk is low.** The B&H corner has large volume, not measure zero: any
`stop_loss` above the window's max adverse excursion is equivalent to off (~60 on NVDA),
likewise `drawdown_exit_pct` (~60). Under the proposed bounds that is ~44% and ~42% of
each gene's range, ~18% jointly per individual — so at pop=4/gen=2 (~12 evaluations)
there is a ~91% chance of sampling an effectively-B&H individual, and elitism preserves
it. Today that probability is **exactly 0**. This is a reachability problem, not a search
problem — consistent with the earlier finding that GA budget correlates ~0 with outcome.

**Deferred deliberately (user decision): the overfit-guard sign bug.** At :1889-1890/:1916,
`multiplier = max(0.01, 1 - divergence)` multiplies a `base_fitness` that is negative for
93% of all runs and **100% of NVDA runs** — so more train/test divergence yields a *less
negative* fitness and ranks *higher*. The guard rewards overfitting exactly where the
strategy loses. Fix is one line, sign-preserving and algebraically identical for positive
fitness: `fitness = base_fitness - abs(base_fitness) * min(divergence, 0.99)`. Ship it
**after** this change as its own profile variant (gate on a `overfit_guard_mode` profile
setting, not a CLI flag, so it is recorded in run history) — bundling would make the NVDA
result unattributable between two independent hypotheses.

**Not a bug (checked and dismissed):** `uptrend_cash_pct` is *not* silently zero in the
reported score — `Long_EMA_Value` is always present on `adaptive_df` (:1256, :2619), and
1028 of 1089 history rows carry a non-zero value.
