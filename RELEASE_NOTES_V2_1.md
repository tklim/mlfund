# ML Fund V2.1 — reconciled operational release

Release: `v2.1.0`

Branch: `codex/forward-decision-dashboard`

Date: 2026-07-14

## Reconciled changes

This release incorporates the other GitHub agent's operational work on top of Forward-Decision V2:

- standardized fund-label handling across backtests, backfill, strategy review, and final replay;
- resilient multi-fund downloads that continue after an individual endpoint failure;
- cached-dividend reuse with explicit warning/source fields when the live dividend endpoint fails;
- per-fund best-GA summaries in strategy review;
- latest-data fixed-parameter replay charts, an HTML dashboard, and a one-fund-per-page PDF;
- Windows batch launchers for report and long-running GA workflows;
- expanded operational regression coverage.

Review also corrected three reconciliation regressions before publication:

- restored the pre-registered V2 prior strength from 8 to 4 in configuration and operational defaults;
- removed the fallback that reconstructed missing interval ends; independence again requires each row's actual `Start Date` and `End Date`;
- changed the exported current GA signal and last-trade date to use the full latest replay rather than the historical evaluation slice.

## Update another Windows machine

For a frozen release snapshot:

```powershell
git fetch --all --tags --prune
git checkout v2.1.0

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest -q
```

For continued development on the shared branch:

```powershell
git fetch --all --tags --prune
git switch codex/forward-decision-dashboard
git pull --ff-only origin codex/forward-decision-dashboard
```

Generated NAV and `outputs/` files are intentionally not distributed. Regenerate them locally:

```powershell
python scripts/download_fund.py --all --years 5
python scripts/fund_forward_decision.py --all --charts --all-horizon-chart --validate
python scripts/final_backtest_from_summary.py --top-funds 0 --price-column TotalReturn
python scripts/operate.py report
```

## Verification

- `python -m pytest -q`: 60 passed.
- Python compilation completed successfully.
- V2 dashboard validation passed for 11 funds.
- Live result remained 1 BUY and 10 HOLD/WATCH, using `dual_relative_v2` with prior strength 4.
- Operational dry run emitted `--prior-strength 4.0`.

All ratings remain general research support, not personalized financial advice.
