# ML Fund Forward-Decision V2 — release and machine handoff

Release: `v2.0.0`

Branch: `codex/forward-decision-dashboard`

Date: 2026-07-14

## What changed

- `dual_relative_v2` is the default forward-decision method; `legacy` remains callable for validation only.
- Decisions use actual non-overlapping `[Start Date, End Date)` intervals, two-stage probability shrinkage with pre-registered prior strength 4, fund-relative P75/P25 lifts, conditional expected edge, a dimensionless volatility-scaled score, and separate trend/recovery momentum paths.
- `operate.py` treats the V2 conclusion as authoritative. GA is contextual and reported as `CONFIRM`, `CONFLICT`, or `NEUTRAL`.
- Technical fixed-target likelihoods are explicitly labeled as a separate model and are not V2 inputs.
- Total return uses a dividend-reinvestment index and forward-merges non-NAV ex-dates. Old additive-total-return backtests are not comparable with regenerated results.
- Network downloads now use timeouts, HTTP status checks, response validation, and empty-data guards.
- A rolling-origin legacy/V2 validator and expanded automated tests are included.

The detailed methodology, canonical research references, regenerated results, and limitations are in `FORWARD_DECISION_METHODOLOGY_REVIEW.md`.

## Install on another Windows machine

```powershell
git clone https://github.com/tklim/mlfund.git
cd mlfund
git fetch --tags origin
git switch codex/forward-decision-dashboard
git pull --ff-only origin codex/forward-decision-dashboard
git describe --tags --exact-match

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest -q
```

If the repository already exists:

```powershell
git fetch --all --tags --prune
git switch codex/forward-decision-dashboard
git pull --ff-only origin codex/forward-decision-dashboard
git status --short --branch
```

The tag can also be checked out directly for a frozen, detached release snapshot:

```powershell
git checkout v2.0.0
```

## Regenerate local data and reports

Generated NAV files and `outputs/` are intentionally not released. Each machine must create its own current data and reports:

```powershell
python scripts/download_fund.py --all --years 5
python scripts/fund_forward_decision.py --all --charts --all-horizon-chart --validate
python scripts/validate_forward_decision_methodology.py --all --output-dir outputs/reports
python scripts/operate.py report
```

For the regular daily workflow:

```powershell
.\run_daily_investment_review.ps1
```

## Migration and operational notes

- Do not copy old generated dashboards as evidence that the new machine is working; regenerate them from current NAV data.
- Do not compare historical additive-total-return runs with reinvestment-index runs. Keep or label old histories separately.
- Five years of data normally permits only about nine independent 6M outcomes and about four 1Y outcomes. Rare 6M signals and evidence-limited 1Y HOLD decisions are expected.
- If technical review reports `NO_PARAMETERS`, regenerate GA/backtest history against the current reinvested `TotalReturn` method before relying on technical context:

```powershell
.\run_weekly_strategy_review.ps1
```

- Prior strength remains locked at 4. Sensitivity 2/4/8 is calibration-only and must not be selected from holdout results.
- Ratings are general research support, not personalized financial advice.

## Verification recorded for this release

- `python -m pytest -q`: 37 passed.
- V2 dashboard: 11 funds analyzed; validation passed.
- Full walk-forward comparison: rollout result `ACCEPT`, but the historical V2 BUY/SELL sample was insufficient and rules were not relaxed.
- Latest regenerated live dashboard at release time: 1 BUY, 10 HOLD/WATCH, 0 SELL/AVOID.
