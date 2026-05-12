import argparse
import re
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUTS_DIR = REPO_ROOT / "outputs"
TUNINGS_DIR = OUTPUTS_DIR / "tunings"
FUNDS_DIR = OUTPUTS_DIR / "funds"

GLOBAL_FILES = {
    "run": TUNINGS_DIR / "backtest_run_history.csv",
    "window": TUNINGS_DIR / "backtest_window_history.csv",
    "tuning": TUNINGS_DIR / "backtest_tuning_history.csv",
    "top5": TUNINGS_DIR / "top5_parameter_sets_by_fund.csv",
}


def sanitize_fund_folder_name(fund_label):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(fund_label or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned or "UnknownFund"


def fund_tuning_dir(fund_label):
    return FUNDS_DIR / sanitize_fund_folder_name(fund_label) / "tunings"


def fund_history_path(fund_label, history_key):
    fund_name = sanitize_fund_folder_name(fund_label)
    names = {
        "run": f"{fund_name}-backtest_run_history.csv",
        "window": f"{fund_name}-backtest_window_history.csv",
        "tuning": f"{fund_name}-backtest_tuning_history.csv",
        "top5": f"{fund_name}-top5_parameter_sets.csv",
    }
    return fund_tuning_dir(fund_name) / names[history_key]


def write_group(df, fund_label, history_key, dry_run=False):
    target = fund_history_path(fund_label, history_key)
    if dry_run:
        print(f"[dry-run] {history_key}: {fund_label} -> {target} ({len(df)} rows)")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=False)
    print(f"{history_key}: {fund_label} -> {target} ({len(df)} rows)")


def split_global_file(history_key, path, dry_run=False):
    if not path.exists():
        print(f"skip {history_key}: missing {path}")
        return
    df = pd.read_csv(path)
    if df.empty:
        print(f"skip {history_key}: empty {path}")
        return
    if "fund_label" not in df.columns:
        print(f"skip {history_key}: no fund_label column in {path}")
        return

    for fund_label, fund_df in df.groupby("fund_label", dropna=False):
        write_group(fund_df, fund_label, history_key, dry_run=dry_run)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill outputs/funds/<fund>/tunings from global backtest history CSVs."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the files that would be written without changing anything.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    for history_key, path in GLOBAL_FILES.items():
        split_global_file(history_key, path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
