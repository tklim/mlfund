# Manulife Fund Data Downloader

Automated NAV (Net Asset Value) and dividend data downloader for Manulife Investment Management Malaysia funds.

## Features

- ✅ Download NAV history from Manulife API (no browser required)
- ✅ Fetch dividend data and merge with NAV history
- ✅ Calculate **TotalReturn** = NAV + cumulative dividends received
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

## Output

CSV files are saved to the `data/` folder with the format:
`{FUND_ID}_{ShortName}_nav_{YEARS}Y.csv`

### CSV Columns

| Column | Description |
|--------|-------------|
| `Date` | Trading date |
| `NAV` | Net Asset Value (MYR) |
| `Dividend` | Dividend paid on ex-dividend date (empty if no dividend) |
| `TotalReturn` | NAV + cumulative dividends received to date |

## TotalReturn Calculation

The **TotalReturn** column represents the total value if you held the fund, including reinvested dividends:

```
TotalReturn = NAV + Σ(Dividends received to date)
```

**Example:**
| Date | NAV | Dividend | TotalReturn |
|------|-----|----------|-------------|
| 2024-07-26 | 0.4064 | - | 0.4064 |
| 2024-07-29 | 0.3736 | 0.0365 | **0.4101** |
| 2024-07-30 | 0.3724 | - | 0.4089 |

On 2024-07-29, the NAV dropped from 0.4064 to 0.3736 (dividend detached), but you received 0.0365 in cash. Total value = 0.3736 + 0.0365 = **0.4101**.

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
schtasks /create /tn "ManulifeFundDownload" /tr "python C:\Users\tklim\OpenWork\mlfund\scripts\download_fund.py" /sc daily /st 18:00
```

### Cron (Linux/Mac)
```bash
0 18 * * * cd /path/to/mlfund && python scripts/download_fund.py
```

## Notes

- Data is fetched for the last **3 years** by default; use `--years 5` to download 5 years
- Dividend data is merged on ex-dividend dates
- If CSV file is locked (open in Excel), script automatically adds timestamp to filename
- All values in **MYR** (Malaysian Ringgit)

## License

MIT License - Use freely for personal/investment tracking purposes.
