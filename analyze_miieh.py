import argparse
import re

import numpy as np
import pandas as pd

from scripts.common import TUNINGS_DIR, resolve_repo_path, save_csv


def parse_args():
    parser = argparse.ArgumentParser(description="Prepare cleaned run-history rows for one fund.")
    parser.add_argument(
        "--history-file",
        default=str(TUNINGS_DIR / "backtest_run_history.csv"),
        help="Backtest run history CSV. Relative paths resolve from repo root.",
    )
    parser.add_argument(
        "--fund-label",
        default="MIIEH",
        help="Fund label substring to filter (default: MIIEH).",
    )
    parser.add_argument(
        "--output-file",
        default=str(TUNINGS_DIR / "miieh_analysis.csv"),
        help="Cleaned analysis CSV output path.",
    )
    return parser.parse_args()


def extract_lookback(log_file):
    if pd.isna(log_file):
        return np.nan
    match = re.search(r"_(\d+\.?\d*)Y-", str(log_file))
    return float(match.group(1)) if match else np.nan


def extract_offset(log_file):
    if pd.isna(log_file):
        return np.nan
    match = re.search(r"Y-(\d+)M-", str(log_file))
    return int(match.group(1)) if match else np.nan


def main():
    args = parse_args()
    history_file = resolve_repo_path(args.history_file)
    if not history_file.exists():
        raise FileNotFoundError(f"Run history file not found: {history_file}")

    df = pd.read_csv(history_file)
    fund_df = df[df["fund_label"].str.contains(args.fund_label, na=False)].copy()
    if fund_df.empty:
        raise ValueError(f"No runs found for fund label filter: {args.fund_label}")

    print(f"Found {len(fund_df)} rows for {args.fund_label}")
    print("\nColumns available:", fund_df.columns.tolist())

    numeric_cols = [
        "lookback_years",
        "offset_months",
        "adaptive_return_pct",
        "adaptive_annualized_return_pct",
        "sharpe",
        "max_dd_pct",
        "excess_return_pct",
        "last_short_ema",
        "last_long_ema",
        "last_stop_loss",
        "last_cooldown",
        "last_drawdown_exit_pct",
        "last_reentry_rebound_pct",
    ]
    for col in numeric_cols:
        if col in fund_df.columns:
            fund_df[col] = pd.to_numeric(fund_df[col], errors="coerce")

    if "lookback_years" not in fund_df.columns or fund_df["lookback_years"].isna().all():
        print("Extracting lookback_years from log file names...")
        if "log_file" in fund_df.columns:
            fund_df["lookback_years"] = fund_df["log_file"].apply(extract_lookback)

    if "offset_months" not in fund_df.columns or fund_df["offset_months"].isna().all():
        print("Extracting offset_months from log file names...")
        if "log_file" in fund_df.columns:
            fund_df["offset_months"] = fund_df["log_file"].apply(extract_offset)

    print("\nSample data:")
    print(
        fund_df[
            ["lookback_years", "offset_months", "adaptive_return_pct", "sharpe", "max_dd_pct"]
        ].head(10)
    )

    output_file = save_csv(fund_df, resolve_repo_path(args.output_file))
    print(f"\nSaved cleaned data to {output_file}")


if __name__ == "__main__":
    main()
