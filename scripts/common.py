import re
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUTS_DIR = REPO_ROOT / "outputs"
LOGS_DIR = OUTPUTS_DIR / "logs"
CHARTS_DIR = OUTPUTS_DIR / "charts"
TUNINGS_DIR = OUTPUTS_DIR / "tunings"
REPORTS_DIR = OUTPUTS_DIR / "reports"


def resolve_repo_path(path_value):
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_fund_label(value):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned or "UnknownFund"


def fund_label_from_data_file(path_value):
    stem = Path(path_value).stem
    match = re.match(r"(.+)_nav_\d+Y(?:_\d{8}_\d{6})?$", stem, re.IGNORECASE)
    return sanitize_fund_label(match.group(1) if match else stem)


def annualized_return_from_pct(total_return_pct, start_date, end_date):
    if start_date is None or end_date is None:
        return np.nan
    try:
        total_return = float(total_return_pct) / 100.0
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        days = (end_ts - start_ts).days
    except (TypeError, ValueError, OverflowError):
        return np.nan
    if pd.isna(start_ts) or pd.isna(end_ts) or days <= 0 or (1 + total_return) <= 0:
        return np.nan
    return (((1 + total_return) ** (365.25 / days)) - 1) * 100


def annualize_return_series(total_return_pct, start_series, end_series):
    total_return = pd.to_numeric(total_return_pct, errors="coerce") / 100.0
    start_dates = pd.to_datetime(start_series, errors="coerce")
    end_dates = pd.to_datetime(end_series, errors="coerce")
    day_counts = (end_dates - start_dates).dt.days

    valid = (
        total_return.notna()
        & start_dates.notna()
        & end_dates.notna()
        & (day_counts > 0)
        & ((1 + total_return) > 0)
    )
    annualized = pd.Series(np.nan, index=total_return.index, dtype=float)
    annualized.loc[valid] = (((1 + total_return.loc[valid]) ** (365.25 / day_counts.loc[valid])) - 1) * 100
    return annualized


def save_csv(df, path, **kwargs):
    path = Path(path)
    ensure_dir(path.parent)
    df.to_csv(path, index=False, **kwargs)
    return path
