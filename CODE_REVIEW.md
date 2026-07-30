# Code Review — mlfund Python scripts

Reviewed: 2026-07-12. Scope: all 15 `*.py` files (5 root analysis scripts + 10 under `scripts/`).
Overall: the pipeline is coherent and the newer scripts (`fund_forward_decision.py`, `fund_probability_analysis.py`, `technical_signal_review.py`) are well structured. The main risks are a few real runtime bugs, a questionable TotalReturn formula that feeds every backtest, and heavy duplication of helpers with inconsistent semantics.

---

## 1. Bugs (likely to break at runtime)

### 1.1 `daily_investment_review.py` — crash in download mode
`write_csv()` uses `csv.DictWriter` with a fixed `fieldnames` list, but `download_fund()` returns an extra key `dividend_count`. `DictWriter.writerows` raises `ValueError` on extra keys (default `extrasaction="raise"`), so any run **without** `--skip-download` fails when writing `daily_downloaded_files_<run>.csv`.
Fix: `csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")` or add `dividend_count` to the fieldnames.

### 1.2 `download_fund.py` — summary print crashes on `None`
In the final SUMMARY block: `print(f"  Change: {r['change']:.4f} ({r['change_pct']:.2f}%)")`. `change`/`change_pct` come from the API and can be `None` (the per-fund print correctly guards with `if change:`, this one doesn't). A single fund with no daily change kills the whole batch after all downloads finished.

### 1.3 `download_fund.py` — no timeout / error handling on main requests
`funds.details.json` and `funds.prices.json` are fetched with bare `requests.get(...).json()` — no `timeout`, no `raise_for_status()`, no try/except (unlike `get_dividends`, which does all three). A hung connection stalls forever; an HTML error page raises an opaque `JSONDecodeError`. Also: if `prices` is empty, `df['Date'].min()` raises on the empty DataFrame.

### 1.4 `analyze_all_funds.py` / `visualize_miieh.py` — unguarded column access
Both scripts check `if col in df.columns` when coercing numerics, but then plot/aggregate unconditionally: `df["last_short_ema"]`, `df["last_rsi_oversold"]`, `groupby(...)["sharpe"]`, `pivot_table(... "best_ga_pop_size" ...)`. Any history CSV missing one of these columns raises `KeyError` mid-run, after some charts are written. Apply the same presence checks used in `fund_strategy_review.py` (`save_heatmap`/`save_scatter` guard properly — good pattern to copy).

### 1.5 `fund_forward_decision.py` — `pivot` raises on duplicate fund labels
`create_all_horizon_chart` uses `DataFrame.pivot(index="Fund Label", ...)`, which raises if the same fund appears twice (e.g., two data files that normalize to the same label). Use `pivot_table` with an explicit aggfunc, or de-duplicate first.

---

## 2. Methodology concerns (results correctness)

### 2.1 `TotalReturn = NAV + cumsum(dividends)` (`download_fund.py`)
This additive series is not a total-return index: it ignores dividend reinvestment/compounding and injects step discontinuities that EMAs and RSI then smooth over. Since `TotalReturn` is the **default price column for every backtest**, this biases all downstream results (understates long-horizon returns, distorts crossover timing near ex-dates). Standard approach: `factor = (1 + Dividend/NAV).cumprod(); TotalReturn = NAV * factor` (or build from adjusted returns). Also note dividends whose ex-date is not an exact NAV date are silently dropped by the `how="left"` merge.

### 2.2 Four inconsistent copies of `annualized_return_from_pct`
- `scripts/common.py`: returns `np.nan` when growth ≤ 0 or dates invalid.
- `backtest-ema-ga10-index.py` and `final_backtest_from_summary.py`: return `0.0` on invalid input, `-100.0` when growth ≤ 0.
- `fund_strategy_review.py`: returns `np.nan` on invalid, `-100.0` when growth ≤ 0.

The same run can therefore show a different annualized figure depending on which report you read (0.0 vs NaN materially changes means/rankings in summaries). Consolidate on `scripts/common.py` and import it everywhere.

### 2.3 Duplicate, non-identical indicator implementations
`calculate_rsi`/`calculate_ema` exist in both `backtest-ema-ga10-index.py` (rolling `min_periods=1`, fills 50/100 special cases) and `fund_forward_decision.py` (`min_periods=period`, different zero-loss handling). The "technical state" in the forward-decision dashboard is thus computed on slightly different RSI values than the backtester used to trade. Worth unifying in `common.py`.

### 2.4 Win-rate pairing is approximate (`backtest-ema-ga10-index.py`)
Both win-rate computations pair the i-th BUY with the i-th SELL and compare stored *portfolio values*. `BUY_TOPUP` and `PARTIAL_SELL` are excluded from pairing, so with top-ups/partial exits the pairs misalign and the "return per trade" is really portfolio growth between two arbitrary points. Fine as a rough diagnostic; don't treat `win_rate_pct` as a per-trade statistic.

### 2.5 Stale hard-coded "recommendations" (`fund_strategy_review.py`)
`build_recommended_runs()` ignores its `df`/`top_ranges` arguments and emits fixed text: fixed EMA bounds 20–55/70–135, a hard-coded fallback data file (`MIIEH_IndiaEquityRMH_nav_5Y.csv`), and the claim "the current CLI does not expose RSI bounds" — which is now false (`--rsi-oversold-bounds`/`--rsi-overbought-bounds` exist). These render in the HTML/markdown report as if data-driven. Either derive them from `top_ranges` or label them clearly as a static playbook.

---

## 3. Robustness / coworking concerns

### 3.1 Fallback CSVs are written but never read back
`save_csv()` (common.py) and `run_with_lock_resilience()` (backtester) write timestamped fallback files when the canonical CSV is locked — good. But consumers read only the canonical name: `daily_investment_review.read_dashboard()` reads `fund_forward_decision_dashboard.csv`; if the child process fell back, the daily report silently uses **stale** data from a previous run. In a shared/coworking setup with two agents this is a live race. Suggest: have child scripts print the actual path written and pass it, or fail loudly when a fallback was used.

### 3.2 Absolute `file://` URIs in HTML reports
`daily_investment_review.py` and `technical_signal_review.py` embed chart images via `path.as_uri()` (absolute paths). Reports break when the folder syncs to another machine (the repo already records `machine_name` per run, so multi-machine use is expected). `fund_strategy_review.py` does it right with `os.path.relpath` — reuse that.

### 3.3 Lock-retry schedule can stall a run ~3.5 minutes per file
`LOCK_RETRY_SCHEDULE_SECONDS = [30, 60, 120]` plus a final attempt: a locked history file blocks each append for up to 210s inside the walk-forward loop. Consider shorter retries and going straight to the fallback path.

---

## 4. Code health

### 4.1 `backtest-ema-ga10-index.py` (2,877 lines) — the big one
- **Un-importable filename**: hyphens force `importlib.util.spec_from_file_location` hacks in *two* consumers (`final_backtest_from_summary.py`, `technical_signal_review.py`), each of which re-executes ~800 lines of module-level code. Rename to `backtest_ema_ga10_index.py` (keep a thin shim with the old name if CLI muscle memory matters).
- **Global-state coupling**: `csv_name`, `lookback_years`, `pop_ranges`, `gen_ranges`, `log_file`, `skip_top5_refresh_for_run`, etc. are module globals mutated by `run_backtest_for_csv` and read inside `genetic_optimize_params`/`tune_ga_hyperparams`. When imported by other scripts these hold stale defaults ("No-name"); today only cosmetic (log lines, deterministic-seed material), but it makes the GA seed depend on whether globals were set — pass them as parameters.
- **Duplicated code**: `import signal` twice (lines 10, 16); the elapsed-time block appears 3× with copy-paste drift — the second copy (line ~2482) uses `now` captured *before* the GA tuning ran, so the printed "Elapsed" understates wall time; the fitness scoring formula (`2.0*excess + 6.0*sharpe − 0.30*dd − 0.10*trades − 0.5*uptrend_cash − missed_upside`) is written out 3× (fitness_func, tune loop, run summary) — extract one `score_metrics()` so weights can't drift apart.
- **Silent failure**: `genetic_optimize_params` wraps everything in `except Exception: return None`, and callers skip the window. A typo inside the fitness path would silently produce "no valid parameters" runs. Catch narrowly or at least log the traceback.
- `sanitize_label`/`sanitize_fund_folder_name`/`infer_fund_output_label` duplicate `common.py` equivalents.

### 4.2 Import-style split
Root scripts import `from scripts.common import ...`; scripts inside `scripts/` import `from common import ...`. Both work only from their respective working directories. Adding `scripts/__init__.py` and using `scripts.common` everywhere (running with `python -m scripts.foo`) would make the repo runnable from one place.

### 4.3 Minor
- `backtest-ema-ga10-index.py parse_args`: `--pop_ranges` default is the scalar `10` while `nargs="+"` implies a list; `normalize_pop_ranges` papers over it — set `default=["10"]`. Also mixed flag styles (`--pop_ranges` vs `--offset-months`).
- `visualize_miieh.py`: line charts plot raw rows (`subset["lookback_years"] vs adaptive_return_pct`) without sorting or aggregating — with several runs per lookback the lines zigzag/backtrack. Aggregate with `groupby(...).mean()` as `analyze_offset.py` does.
- `warnings.filterwarnings('ignore')` globally in the backtester hides pandas FutureWarnings you'll want during upgrades.
- `technical_signal_review.py`: `normalize_run_history` hard-requires `duration_seconds` and drops rows without it; a merged history from another machine missing that column hard-fails. Could default to NaN → neutral rank (0.5).
- `final_backtest_from_summary.py`: `normalize_run_history` hard-requires `last_exposure_multiplier` but then does `.fillna(1.0)` — accept the column being absent and default to 1.0.
- No `requirements.txt`/lockfile: pandas, numpy, matplotlib, scipy, requests, pygad, yfinance are implicit. Pin them; `pygad`'s API changed across majors and `tick_labels=` in `ax.boxplot` requires matplotlib ≥ 3.9.
- No tests. Highest-value first targets: `normalize_pop_ranges`, `annualized_return_from_pct` (all variants), the win-rate pairing, and `append_csv_rows_to_path` column-union logic.

---

## 5. What's good

- `scripts/common.py` is clean and the right idea — the fix for most of section 2/4 is just *using* it everywhere.
- Walk-forward design with warmup data + `trade_start_idx`, deterministic seeds from run metadata, and per-window history rows are all solid, reproducible-research practices.
- Overlapping-window inflation is handled honestly in `fund_probability_analysis.py` (effective N, Wilson intervals) and `fund_forward_decision.py` (non-overlapping date counting).
- Lock-resilient CSV writes and per-fund history mirroring show real operational thought; the remaining gap is the read side (3.1).
- `--validate` flags on the newer dashboards are a nice self-check habit.

## Suggested fix order
1. §1.1 DictWriter crash (one-line) and §1.2 None-format crash (one-line).
2. §2.1 TotalReturn compounding — decide and re-download, since everything depends on it.
3. §2.2 consolidate `annualized_return_from_pct` into `common.py`.
4. §1.3, §1.4, §1.5 guards.
5. §4.1 rename backtester + extract shared score function.
