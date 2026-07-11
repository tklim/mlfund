#!/usr/bin/env python3
"""
Manulife Fund Data Downloader
Downloads NAV history and dividend data for specified fund codes from Manulife Investment Management Malaysia.
"""

import os
import re
import sys
import argparse
import csv
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from requests import RequestException

from common import dividend_reinvested_index

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
REQUEST_TIMEOUT_SECONDS = 30


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
    parser.add_argument(
        "--manifest",
        default=None,
        help="Optional CSV path for a machine-readable refresh manifest.",
    )
    return parser.parse_args()


def fetch_json(url, *, description):
    """Fetch JSON with timeout and HTTP validation for scheduled runs."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (RequestException, ValueError) as exc:
        raise RuntimeError(f"Unable to load {description}: {exc}") from exc


def fmt_number(value, digits=4):
    if value is None or value == "":
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


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


def get_dividends_with_warning(fund_id):
    """Fetch dividend history and return a warning string when the endpoint is unavailable."""
    dividends_url = f"{BASE_URL}/funds.dividends.json?productLine=mf&overrideLocale=en_MY&classId={fund_id}"
    try:
        response = fetch_json(dividends_url, description=f"dividend history for {fund_id}")
    except RuntimeError as exc:
        warning = f"unable to load dividend history for {fund_id}: {exc}"
        print(f"Warning: {warning}")
        return [], warning

    # Handle list with data field - the API returns [ {"data": [...]} ]
    if isinstance(response, list) and len(response) > 0:
        response = response[0]

    if isinstance(response, dict) and "data" in response:
        return response["data"], ""
    return response if isinstance(response, list) else [], ""


def get_dividends(fund_id):
    """Fetch dividend history for a fund."""
    dividends, _warning = get_dividends_with_warning(fund_id)
    return dividends


def build_output_path(fund_label, years):
    return DATA_DIR / f"{fund_label}_nav_{years}Y.csv"


def load_cached_dividends(path):
    if not path.exists():
        return []
    try:
        cached = pd.read_csv(path, usecols=["Date", "Dividend"])
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return []
    cached["Dividend"] = pd.to_numeric(cached["Dividend"], errors="coerce").fillna(0.0)
    cached = cached[cached["Dividend"].ne(0.0)]
    return [
        {"exDividendDate": row["Date"], "dividend": row["Dividend"]}
        for _, row in cached.iterrows()
    ]


def download_fund(fund_id, years=3):
    """Download NAV history and dividends for a fund."""
    print(f"\n{'=' * 50}")
    print(f"Downloading: {fund_id}")
    print(f"{'=' * 50}")

    # Get fund details
    details_url = f"{BASE_URL}/funds.details.json?productLine=mf&overrideLocale=en_MY&classId={fund_id}"
    details = fetch_json(details_url, description=f"fund details for {fund_id}")

    # Get prices
    prices_url = f"{BASE_URL}/funds.prices.json?productLine=mf&overrideLocale=en_MY&classId={fund_id}"
    prices = fetch_json(prices_url, description=f"NAV prices for {fund_id}")
    if not isinstance(prices, list):
        raise RuntimeError(f"Unexpected price payload for {fund_id}: expected a list.")

    fund_name = details.get("fundName", "Unknown Fund")
    nav = details.get("nav", {})
    current_price = nav.get("price")
    current_date = nav.get("asOfDate")
    change = nav.get("changePrice")
    change_pct = nav.get("changePercent")
    fund_label = short_fund_label(fund_id, fund_name)
    out_path = build_output_path(fund_label, years)

    # Get dividends
    dividends, dividend_warning = get_dividends_with_warning(fund_id)
    dividend_source = "api"
    if dividend_warning:
        cached_dividends = load_cached_dividends(out_path)
        if cached_dividends:
            dividends = cached_dividends
            dividend_source = "cached_existing_file"
            dividend_warning = f"{dividend_warning}; reused {len(cached_dividends)} cached dividend row(s) from {out_path.name}"
        else:
            dividend_source = "unavailable"

    print(f"Fund: {fund_name}")
    print(f"Current NAV: {current_price} MYR ({current_date})")
    if change is not None:
        print(f"Daily Change: {fmt_number(change)} ({fmt_number(change_pct, 2)}%)")
    print(f"Dividend Records: {len(dividends)}")
    if dividend_source != "api":
        print(f"Dividend Source: {dividend_source}")

    # Build NAV dataframe
    nav_data = []
    for p in prices:
        date = p.get("asOfDate")
        price = p.get("price")
        if date and price:
            nav_data.append({"Date": date, "NAV": price})

    df = pd.DataFrame(nav_data)
    if df.empty:
        raise RuntimeError(f"No NAV price rows returned for {fund_id}.")
    df = df.drop_duplicates(subset=["Date"], keep="last")
    df = df.sort_values("Date")
    df["Date"] = pd.to_datetime(df["Date"])
    df["NAV"] = pd.to_numeric(df["NAV"], errors="coerce")
    df = df.dropna(subset=["Date", "NAV"])

    # Filter to specified years
    cutoff = datetime.now() - pd.DateOffset(years=years)
    df = df[df["Date"] >= cutoff]
    if df.empty:
        raise RuntimeError(f"No NAV rows remain for {fund_id} after filtering to {years}Y.")

    # Prepare dividend data
    div_list = []
    for d in dividends:
        div = d.get("dividend")
        ex_date = d.get("exDividendDate")
        if div and ex_date:
            div_list.append({"Date": ex_date, "Dividend": div})

    # Merge dividends. Funds with no distributions still need a TotalReturn column;
    # in that case TotalReturn is the same as NAV.
    if div_list:
        div_df = pd.DataFrame(div_list)
        div_df["Date"] = pd.to_datetime(div_df["Date"])
        div_df["Dividend"] = pd.to_numeric(div_df["Dividend"], errors="coerce").fillna(0.0)
        div_df = div_df.groupby("Date", as_index=False)["Dividend"].sum()
        df = df.merge(div_df, on="Date", how="left")
    else:
        df["Dividend"] = 0.0

    # Calculate a price-like total-return index with dividends reinvested on
    # each ex-dividend date. The first observation is anchored to its NAV.
    df["Dividend"] = pd.to_numeric(df["Dividend"], errors="coerce").fillna(0.0)
    df["TotalReturn"] = dividend_reinvested_index(df["NAV"], df["Dividend"])

    print(f"NAV Records: {len(df)}")
    print(
        f"Date Range: {df['Date'].min().strftime('%Y-%m-%d')} to {df['Date'].max().strftime('%Y-%m-%d')}"
    )

    # Reorder columns
    cols = ["Date", "NAV", "Dividend", "TotalReturn"]
    df = df[cols]

    # Save CSV (handle locked files)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

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
        "dividend_source": dividend_source,
        "warning": dividend_warning,
        "records": len(df),
        "output_path": str(out_path),
    }


def get_fund_summary(fund_id):
    """Get quick fund summary without full price history."""
    details_url = f"{BASE_URL}/funds.details.json?productLine=mf&overrideLocale=en_MY&classId={fund_id}"
    details = fetch_json(details_url, description=f"fund summary for {fund_id}")

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


def write_manifest(results, manifest_path):
    if not manifest_path:
        return None
    path = Path(manifest_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timestamp",
        "fund_id",
        "fund_name",
        "fund_label",
        "status",
        "error",
        "current_nav",
        "current_date",
        "change",
        "change_pct",
        "dividend_count",
        "dividend_source",
        "records",
        "warning",
        "output_path",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow({key: result.get(key, "") for key in fieldnames})
    print(f"Manifest: {path}")
    return path


def download_many(fund_ids, years):
    results = []
    failed = 0
    for fid in fund_ids:
        try:
            result = download_fund(fid, years=years)
            result["status"] = "ok_with_warnings" if result.get("warning") else "ok"
            result["error"] = ""
            result["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            results.append(result)
        except Exception as exc:
            failed += 1
            print(f"ERROR: {fid} failed: {exc}")
            results.append(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "fund_id": fid,
                    "fund_name": "",
                    "fund_label": "",
                    "status": "failed",
                    "error": str(exc),
                    "current_nav": "",
                    "current_date": "",
                    "change": "",
                    "change_pct": "",
                    "dividend_count": "",
                    "dividend_source": "",
                    "records": "",
                    "warning": "",
                    "output_path": "",
                }
            )
    return results, failed


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
            print(f"{s['fund_id']}: {s['fund_name']} - {s['nav']} MYR ({s['date']}){div}")
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

    results, failed = download_many(funds_to_download, years=args.years)

    write_manifest(results, args.manifest)

    if not args.fund_ids or args.all:
        print(f"\n{'=' * 50}")
        print("SUMMARY")
        print(f"{'=' * 50}")
        for r in results:
            print(f"{r['fund_id']}: {r.get('fund_name') or 'n/a'} [{r.get('status', 'ok')}]")
            if r.get("status") == "failed":
                print(f"  Error: {r.get('error')}")
                continue
            print(f"  NAV: {r.get('current_nav')} MYR ({r.get('current_date')})")
            print(f"  Change: {fmt_number(r.get('change'))} ({fmt_number(r.get('change_pct'), 2)}%)")
            print(f"  Dividends: {r.get('dividend_count')}")
            if r.get("warning"):
                print(f"  Warning: {r.get('warning')}")
            print(f"  Records: {r.get('records')}")

    if failed and not (args.all or len(funds_to_download) > 1):
        sys.exit(1)
    if failed:
        print(f"Completed with {failed} failed fund(s). See manifest for details.")
