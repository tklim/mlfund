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
pip install pandas requests
```

## Usage

### Download Single Fund
```bash
python download_fund.py MAKGCF
```

### Download Multiple Funds
```bash
python download_fund.py MAKGCF MAPF APCR
```

### Download All Tracked Funds
```bash
python download_fund.py --all
```

### Quick Summary (No Download)
```bash
python download_fund.py --summary
```

### Default Behavior (No Arguments)
Downloads all funds in the `TRACKED_FUNDS` list.

## Output

CSV files are saved to the `mlfund` folder with the format:
`manulife_{FUND_ID}_nav_{YEARS}Y.csv`

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
├── download_fund.py          # Main download script
├── README.md                 # This file
├── manulife_MAKGCF_nav_3Y.csv  # Greater China Fund data
├── manulife_MAPF_nav_3Y.csv   # Progress Fund data
└── manulife_APCR_nav_3Y.csv   # Asia-Pacific REIT Fund data
```

## Automation

### Windows Task Scheduler
Create a scheduled task to run daily:
```bash
schtasks /create /tn "ManulifeFundDownload" /tr "python C:\Users\tklim\OpenWork\mlfund\download_fund.py" /sc daily /st 18:00
```

### Cron (Linux/Mac)
```bash
0 18 * * * cd /path/to/mlfund && python download_fund.py
```

## Notes

- Data is fetched for the last **3 years** by default (modify `years` parameter in script)
- Dividend data is merged on ex-dividend dates
- If CSV file is locked (open in Excel), script automatically adds timestamp to filename
- All values in **MYR** (Malaysian Ringgit)

## License

MIT License - Use freely for personal/investment tracking purposes.