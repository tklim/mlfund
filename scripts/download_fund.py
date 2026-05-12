#!/usr/bin/env python3
"""
Manulife Fund Data Downloader
Downloads NAV history and dividend data for specified fund codes from Manulife Investment Management Malaysia.
"""

import os
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from requests import RequestException

# Configuration
BASE_URL = "https://www.manulifeim.com.my/funds/fund-details/_jcr_content/root/responsivegrid_641029165"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.7727.102 Safari/537.36",
    "Accept": "application/json",
}
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_DIR = REPO_ROOT / "data"
TRACKED_FUNDS = ["MAUS_RMH", "MGPRH", "MIIEH", "MAPF", "MGLVH", "MAKGCF", "HWFL", "MAPAC", "APCR", "MSGLR_RM"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download Manulife fund NAV and dividend history."
    )
    parser.add_argument(
        "fund_ids",
        nargs="*",
        help="Fund code(s) to download, for example MAKGCF MAPF APCR.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download all tracked funds.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show a quick summary without downloading price history.",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=3,
        help="Number of years of NAV history to download (default: 3).",
    )
    return parser.parse_args()


def sanitize_label(value):
    """Return a compact filesystem-safe label."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", str(value or ""))
    return cleaned or "Unknown"


def short_fund_label(fund_id, fund_name):
    """
    Convert a full fund name into a compact label.
    Example: Manulife Investment Greater China Fund -> MAKGCF_GreaterChina
    """
    short_name = re.sub(r"\bManulife\b", "", str(fund_name or ""), flags=re.IGNORECASE)
    short_name = re.sub(r"\bInvestment\b", "", short_name, flags=re.IGNORECASE)
    short_name = re.sub(r"\bFund\b", "", short_name, flags=re.IGNORECASE)
    short_name = re.sub(r"Hedged\b", "H", short_name, flags=re.IGNORECASE)
    short_name = re.sub(r"\s+", " ", short_name).strip()
    return f"{fund_id}_{sanitize_label(short_name)}"


def get_dividends(fund_id):
    """Fetch dividend history for a fund."""
    dividends_url = f"{BASE_URL}/funds.dividends.json?productLine=mf&overrideLocale=en_MY&classId={fund_id}"
    try:
        response = requests.get(dividends_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        response = response.json()
    except (RequestException, ValueError) as exc:
        print(f"Warning: unable to load dividend history for {fund_id}: {exc}")
        return []

    # Handle list with data field - the API returns [ {"data": [...]} ]
    if isinstance(response, list) and len(response) > 0:
        response = response[0]

    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return response if isinstance(response, list) else []


def download_fund(fund_id, years=3):
    """Download NAV history and dividends for a fund."""
    print(f"\n{'=' * 50}")
    print(f"Downloading: {fund_id}")
    print(f"{'=' * 50}")

    # Get fund details
    details_url = f"{BASE_URL}/funds.details.json?productLine=mf&overrideLocale=en_MY&classId={fund_id}"
    details = requests.get(details_url, headers=HEADERS).json()

    # Get prices
    prices_url = f"{BASE_URL}/funds.prices.json?productLine=mf&overrideLocale=en_MY&classId={fund_id}"
    prices = requests.get(prices_url, headers=HEADERS).json()

    # Get dividends
    dividends = get_dividends(fund_id)

    fund_name = details.get("fundName", "Unknown Fund")
    nav = details.get("nav", {})
    current_price = nav.get("price")
    current_date = nav.get("asOfDate")
    change = nav.get("changePrice")
    change_pct = nav.get("changePercent")

    print(f"Fund: {fund_name}")
    print(f"Current NAV: {current_price} MYR ({current_date})")
    if change:
        print(f"Daily Change: {change:.4f} ({change_pct:.2f}%)")
    print(f"Dividend Records: {len(dividends)}")

    # Build NAV dataframe
    nav_data = []
    for p in prices:
        date = p.get("asOfDate")
        price = p.get("price")
        if date and price:
            nav_data.append({"Date": date, "NAV": price})

    df = pd.DataFrame(nav_data)
    df = df.drop_duplicates(subset=["Date"], keep="last")
    df = df.sort_values("Date")
    df["Date"] = pd.to_datetime(df["Date"])

    # Filter to specified years
    cutoff = datetime.now() - pd.DateOffset(years=years)
    df = df[df["Date"] >= cutoff]

    # Prepare dividend data
    div_list = []
    for d in dividends:
        div = d.get("dividend")
        ex_date = d.get("exDividendDate")
        if div and ex_date:
            div_list.append({"Date": ex_date, "Dividend": div})

    # Merge dividends
    if div_list:
        div_df = pd.DataFrame(div_list)
        div_df["Date"] = pd.to_datetime(div_df["Date"])
        df = df.merge(div_df, on="Date", how="left")
        df["Dividend"] = df["Dividend"].fillna("")

        # Calculate TotalReturn: NAV + cumulative dividends received
        df["DividendAmount"] = df["Dividend"].replace("", 0).astype(float)
        df["TotalReturn"] = df["NAV"] + df["DividendAmount"].cumsum()

    print(f"NAV Records: {len(df)}")
    print(
        f"Date Range: {df['Date'].min().strftime('%Y-%m-%d')} to {df['Date'].max().strftime('%Y-%m-%d')}"
    )

    # Reorder columns
    cols = ["Date", "NAV"]
    if "Dividend" in df.columns:
        cols.extend(["Dividend", "TotalReturn"])
    df = df[cols]

    # Save CSV (handle locked files)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    fund_label = short_fund_label(fund_id, fund_name)
    base_file = f"{fund_label}_nav_{years}Y.csv"
    out_path = DATA_DIR / base_file

    if out_path.exists():
        try:
            with out_path.open("a"):
                pass
        except IOError:
            # File locked - use timestamp
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = DATA_DIR / f"{fund_label}_nav_{years}Y_{ts}.csv"

    df.to_csv(out_path, index=False)
    print(f"Saved: {out_path}")

    return {
        "fund_id": fund_id,
        "fund_name": fund_name,
        "fund_label": fund_label,
        "current_nav": current_price,
        "current_date": current_date,
        "change": change,
        "change_pct": change_pct,
        "dividend_count": len(dividends),
        "records": len(df),
        "output_path": str(out_path),
    }


def get_fund_summary(fund_id):
    """Get quick fund summary without full price history."""
    details_url = f"{BASE_URL}/funds.details.json?productLine=mf&overrideLocale=en_MY&classId={fund_id}"
    details = requests.get(details_url, headers=HEADERS).json()

    # Get latest dividend
    dividends = get_dividends(fund_id)
    latest_div = dividends[0] if dividends else None

    fund_name = details.get("fundName", "Unknown")
    nav = details.get("nav", {})
    price = nav.get("price")
    date = nav.get("asOfDate")
    change = nav.get("changePrice")
    change_pct = nav.get("changePercent")

    return {
        "fund_id": fund_id,
        "fund_name": fund_name,
        "nav": price,
        "date": date,
        "change": change,
        "change_pct": change_pct,
        "latest_dividend": latest_div.get("dividend") if latest_div else None,
        "dividend_date": latest_div.get("exDividendDate") if latest_div else None,
    }


if __name__ == "__main__":
    args = parse_args()
    if args.years <= 0:
        raise ValueError("--years must be greater than 0")

    if args.summary:
        print("Fund Summary:")
        summary_funds = args.fund_ids if args.fund_ids else TRACKED_FUNDS
        for fid in summary_funds:
            s = get_fund_summary(fid)
            div = (
                f", Div: {s['latest_dividend']} ({s['dividend_date']})"
                if s["latest_dividend"]
                else ""
            )
            print(
                f"{s['fund_id']}: {s['fund_name']} - {s['nav']} MYR ({s['date']}){div}"
            )
        sys.exit(0)

    if args.all:
        funds_to_download = TRACKED_FUNDS
        print(f"Downloading all tracked funds for {args.years}Y: {TRACKED_FUNDS}")
    elif args.fund_ids:
        funds_to_download = args.fund_ids
        print(f"Downloading specified funds for {args.years}Y: {funds_to_download}")
    else:
        funds_to_download = TRACKED_FUNDS
        print(f"Downloading default funds for {args.years}Y: {TRACKED_FUNDS}")

    results = []
    for fid in funds_to_download:
        results.append(download_fund(fid, years=args.years))

    if not args.fund_ids or args.all:
        print(f"\n{'=' * 50}")
        print("SUMMARY")
        print(f"{'=' * 50}")
        for r in results:
            print(f"{r['fund_id']}: {r['fund_name']}")
            print(f"  NAV: {r['current_nav']} MYR ({r['current_date']})")
            print(f"  Change: {r['change']:.4f} ({r['change_pct']:.2f}%)")
            print(f"  Dividends: {r['dividend_count']}")
            print(f"  Records: {r['records']}")
