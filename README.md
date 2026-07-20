# Manulife Fund Data Downloader

Automated NAV (Net Asset Value) and dividend data downloader for Manulife Investment Management Malaysia funds.

## Features

- ✅ Download NAV history from Manulife API (no browser required)
- ✅ Fetch dividend data and merge with NAV history
- ✅ Calculate a dividend-reinvested **TotalReturn** index
- ✅ Handle locked CSV files (auto-timestamp fallback)
- ✅ Support multiple funds tracking
- ✅ Quick summary mode (no full download)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Download Single Fund
```bash
python scripts/download_fund.py MAKGCF
```

### Download 5 Years of Data
```bash
python scripts/download_fund.py --all --years 5
```

### Download Multiple Funds
```bash
python scripts/download_fund.py MAKGCF MAPF APCR --years 5
```

### Download All Tracked Funds
```bash
python scripts/download_fund.py --all --years 5
```

### Quick Summary (No Download)
```bash
python scripts/download_fund.py --summary
```

### Default Behavior (No Arguments)
Downloads all funds in the `TRACKED_FUNDS` list.

## Backtesting

The repo includes [backtest-ema-ga10-index.py](C:/Users/tklim/OpenWork/mlfund/scripts/backtest-ema-ga10-index.py), which reads fund CSV files from `data/` and uses `TotalReturn` as the default price series for backtesting.

### Backtest All Local Fund CSVs

This will automatically find files matching `*_nav_*Y.csv` inside `data/`:

```bash
python scripts/backtest-ema-ga10-index.py --pop_ranges 10 --gen_ranges 10 --ga-search-preset focused
```

### Backtest One Fund CSV

```bash
python scripts/backtest-ema-ga10-index.py --data-file data/MAPF_Progress_nav_3Y.csv --pop_ranges 10 --gen_ranges 10 --ga-search-preset focused
```

### Backtest 1Y Training Window, Repeated Every 6 Months

Use `--lookback-years 1` and `--offset-months 6` to train GA on the previous 1 year of data, then roll forward and retune every 6 months:

```bash
python scripts/backtest-ema-ga10-index.py --data-file data/MAKGCF_GreaterChina_nav_3Y.csv --lookback-years 1 --offset-months 6 --pop_ranges 10 --gen_ranges 10 --ga-search-preset focused
```

### EMA Search Bounds

By default, GA searches a wider EMA range:

- Short EMA: `2` to `60`
- Long EMA: `30` to `300`

Wider EMA bounds increase the search space. For serious runs, consider increasing `--pop_ranges` or `--gen_ranges` so GA has more chances to converge.

To test a narrower custom EMA range:

```bash
python scripts/backtest-ema-ga10-index.py --data-file data/MAKGCF_GreaterChina_nav_3Y.csv --short-ema-bounds 3 20 --long-ema-bounds 80 250 --pop_ranges 10 --gen_ranges 10 --ga-search-preset focused
```

### RSI GA Tuning

GA also tunes the RSI guard levels while keeping `rsi_period=14` fixed:

- RSI oversold: `10` to `40`
- RSI overbought: `60` to `90`

The RSI guard is defensive rather than a standalone signal:

- Oversold RSI blocks sell signals, helping avoid selling into sharp dips.
- Overbought RSI blocks new buys and reentries, including recovery-buy overrides.

Adding RSI expands the GA search space. `--pop_ranges 10 --gen_ranges 10 --ga-search-preset focused` is still useful for quick tests, but serious tuning may need larger population or generation sizes to reduce noisy winners.

### Use a Different Price Column

By default the script uses `TotalReturn`. If you want to test raw NAV instead:

```bash
python scripts/backtest-ema-ga10-index.py --data-file data/MAPF_Progress_nav_3Y.csv --price-column NAV --pop_ranges 10 --gen_ranges 10 --ga-search-preset focused
```

### Why `--ga-search-preset focused`?

`--pop_ranges 10 --gen_ranges 10` makes each GA run small, but the script can still try many mutation/crossover combinations during tuning. `--ga-search-preset focused` reduces that search to a single focused setting so the run finishes much faster.

### Backtest Output

Each run generates:

- A text log file in `outputs/logs/` such as `MAPF_Progress-2Y-6M-generic-ga10-YYYYMMDD_HHMMSS.txt`
- A chart PNG in `outputs/charts/` such as `MAPF_Progress-2Y-6M-generic-ga10-tuned-YYYYMMDD-HHMMSS.png`
- A GA tuning summary in `outputs/tunings/` such as `ga_tuning_summary_YYYYMMDD_HHMMSS.csv`
- Persistent tuning history CSVs in `outputs/tunings/`, including the EMA bounds used plus the winning EMA, RSI, stop-loss, cooldown, drawdown-exit, reentry-rebound, and exposure values selected by GA

### Strategy Review Dashboard

Generate a review-ready strategy dashboard from the persistent run history:

```bash
python scripts/fund_strategy_review.py
```

The dashboard uses `outputs/tunings/backtest_run_history.csv` and creates:

- `outputs/reports/fund_strategy_review.html`
- `outputs/reports/fund_strategy_review.md`
- leaderboard, parameter sensitivity, recommended next-run, and log cross-check CSVs in `outputs/reports/`
- dashboard charts in `outputs/charts/strategy_review/`

The report ranks current strategy candidates by annualized adaptive and excess return, compares adaptive returns against buy-and-hold on the same time basis, flags decision status, summarizes top-quartile parameter zones, and recommends the next tuning runs to explore.

For a single fund, generate the review under `outputs/funds/{FUND_LABEL}/reports/`:

```bash
python scripts/fund_strategy_review.py --fund-label MIIEH_IndiaEquityRMH
```

Backtests still write global histories under `outputs/tunings/`, and also mirror fund-specific histories under `outputs/funds/{FUND_LABEL}/tunings/`. To backfill existing global histories into those fund folders:

```bash
python scripts/backfill_fund_outputs.py
```

### Latest Fixed-Parameter Backtest Dashboard

Replay the best annualized-excess parameter set for every fund against both its original evaluation slice and the latest matching local data:

```bash
python scripts/final_backtest_from_summary.py --top-funds 0 --price-column TotalReturn
```

In addition to per-fund charts and the timestamped summary CSV, this creates:

- `outputs/reports/dashboard.html`, with sortable fund cards and zoomable charts;
- `outputs/reports/dashboard.pdf`, with one fund per landscape page;
- a latest-replay GA signal and last-trade date for downstream `CONFIRM` / `CONFLICT` / `NEUTRAL` context.

### Conditional Forward Probability Dashboard

Generate a decision-support dashboard that compares each fund's latest state with similar historical states, then summarizes forward-return probabilities for BUY / HOLD / SELL review:

```bash
python scripts/fund_forward_decision.py --all --validate --charts
```

The default run analyzes `data/*_nav_5Y.csv` with the authoritative `dual_relative_v2` methodology. Decisions use independent actual-date intervals, shrunk fund-relative P75/P25 probability lifts, conditional return edge, and path-specific momentum confirmation. The `+15%` upside and `-8%` downside fields remain descriptive absolute-threshold statistics rather than V2 decision gates. Outputs are saved to:

- `outputs/reports/fund_forward_decision_dashboard.csv`
- `outputs/reports/fund_forward_decision_details.csv`
- `outputs/reports/fund_forward_decision_dashboard.html`
- `outputs/charts/forward_decision/`

To compare every configured horizon in one visual, add:

```bash
python scripts/fund_forward_decision.py --all --all-horizon-chart --validate
```

For a reproducible rolling-origin comparison against the original overlapping-window method:

```bash
python scripts/validate_forward_decision_methodology.py --all --output-dir outputs/reports
```

See `FORWARD_DECISION_METHODOLOGY_REVIEW.md` for the equations, decision paths, validation findings, and evidence limitations. The old model remains callable only for comparison:

```bash
python scripts/fund_forward_decision.py --all --forward-method legacy --validate
```

### Daily Investment Decision Pipeline

Run the daily investment review to refresh 5Y fund data, analyze the exact refreshed CSV files, and publish the decision dashboard:

```powershell
.\run_daily_investment_review.ps1
```

For a safe local dry run that skips downloading and uses the latest existing local 5Y CSVs:

```powershell
.\run_daily_investment_review.ps1 -SkipDownload
```

The daily pipeline writes:

- `outputs/reports/fund_forward_decision_dashboard.html`
- `outputs/reports/fund_forward_decision_dashboard.csv`
- `outputs/reports/fund_forward_decision_details.csv`
- `outputs/charts/forward_decision/`
- dated logs and compact summaries under `outputs/reports/daily/`

Daily runs use a 6M headline decision horizon and include the all-horizon heatmap for 1M/3M/6M/1Y context. Keep slower GA/backtest strategy refreshes on a weekly cadence:

```powershell
.\run_weekly_strategy_review.ps1
```

To refresh only the strategy review from existing backtest history:

```powershell
.\run_weekly_strategy_review.ps1 -SkipBacktest
```

To also regenerate final fixed-parameter backtest charts:

```powershell
.\run_weekly_strategy_review.ps1 -RunFinalBacktest
```

## Output

CSV files are saved to the `data/` folder with the format:
`{FUND_ID}_{ShortName}_nav_{YEARS}Y.csv`

### CSV Columns

| Column | Description |
|--------|-------------|
| `Date` | Trading date |
| `NAV` | Net Asset Value (MYR) |
| `Dividend` | Distribution aligned to the next available NAV date |
| `TotalReturn` | Dividend-reinvested NAV index |

## TotalReturn Calculation

The **TotalReturn** column is a reinvestment index. A dividend is attached to the next available NAV date when its ex-date is not a NAV date, and the growth factors are compounded:

```
TotalReturn = NAV × cumulative_product(1 + Dividend / NAV)
```

**Example:**
| Date | NAV | Dividend | TotalReturn |
|------|-----|----------|-------------|
| 2024-07-26 | 0.4064 | - | 0.4064 |
| 2024-07-29 | 0.3736 | 0.0365 | dividend growth factor applied |
| 2024-07-30 | 0.3724 | - | reinvested index continues |

This method preserves proportional reinvestment rather than adding historical cash dividends to later NAV values. Results produced with the former additive method are not directly comparable.

## Tracked Funds

Edit the `TRACKED_FUNDS` list in `download_fund.py` to add/remove funds:

```python
TRACKED_FUNDS = ['MAKGCF', 'MAPF', 'APCR']
```

### Fund Codes Reference

| Code | Fund Name |
|------|-----------|
| MAKGCF | Manulife Investment Greater China Fund |
| MAPF | Manulife Investment Progress Fund |
| APCR | Manulife Investment Asia-Pacific REIT Fund |

Find more fund codes at: https://www.manulifeim.com.my/funds/fund-prices.html

## API Endpoints Used

- **Fund Details:** `/funds/fund-details/_jcr_content/root/responsivegrid_641029165/funds.details.json`
- **NAV Prices:** `/funds/fund-details/_jcr_content/root/responsivegrid_641029165/funds.prices.json`
- **Dividends:** `/funds/fund-details/_jcr_content/root/responsivegrid_641029165/funds.dividends.json`

## File Structure

```
mlfund/
├── scripts/
│   ├── download_fund.py
│   └── backtest-ema-ga10-index.py
├── data/
│   ├── MAKGCF_GreaterChina_nav_3Y.csv
│   ├── MAPF_Progress_nav_3Y.csv
│   └── APCR_AsiaPacificREIT_nav_3Y.csv
├── outputs/
│   ├── logs/
│   ├── charts/
│   └── tunings/
└── README.md
```

## Automation

### Windows Task Scheduler
Create a scheduled task to run daily:
```bash
schtasks /create /tn "MLFundDailyInvestmentReview" /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\tklim\OpenWork\mlfund\run_daily_investment_review.ps1" /sc daily /st 19:00
```

### Cron (Linux/Mac)
```bash
0 19 * * * cd /path/to/mlfund && python scripts/daily_investment_review.py
```

## Notes

- Data is fetched for the last **3 years** by default; use `--years 5` to download 5 years
- Dividend ex-dates without NAV observations are aligned to the next available NAV date
- If the dividend endpoint fails, an existing matching CSV can supply cached dividend rows and the run records a warning
- If CSV file is locked (open in Excel), script automatically adds timestamp to filename
- All values in **MYR** (Malaysian Ringgit)

## License

MIT License - Use freely for personal/investment tracking purposes.

## Fund Signal web dashboard

The internet dashboard is maintained as a separate Git repository nested at
`dashboard/`:

- Source: `https://github.com/tklim/fund-signal-dashboard.git`
- Production: `https://fund-signal-dashboard.ltkiat.workers.dev`

The outer `mlfund` repository owns the analysis pipeline and generates the
dashboard snapshot. The nested repository owns the web application and its
Cloudflare deployment. Git operations and commits must remain separate.

Prepare a new clone or validate the existing nested repository:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_dashboard_repo.ps1
```

After the local analysis outputs are ready, publish a snapshot through a
reviewed dashboard pull request:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync_dashboard_snapshot.ps1
```

The sync helper updates `origin/main`, creates a `codex/data-refresh-...`
branch, regenerates and validates the snapshot, commits only the generated
file, pushes the branch, and prints the pull-request URL. Merging the reviewed
pull request into dashboard `main` triggers the production deployment.
