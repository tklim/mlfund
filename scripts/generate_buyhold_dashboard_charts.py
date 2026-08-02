"""Create compact buy-and-hold chart thumbnails for the static dashboard."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


INITIAL_CAPITAL = 10_000.0


def resolve_data_file(value: str, data_root: Path) -> Path | None:
    candidate = Path(value)
    if candidate.is_file():
        return candidate
    fallback = data_root / candidate.name
    return fallback if fallback.is_file() else None


def buyhold_window(data_file: Path, start: str, end: str) -> tuple[pd.Series, pd.Series] | None:
    try:
        frame = pd.read_csv(data_file)
    except (OSError, ValueError, UnicodeError):
        return None
    if "Date" not in frame:
        return None
    price_column = "TotalReturn" if "TotalReturn" in frame else "NAV" if "NAV" in frame else None
    if price_column is None:
        return None
    dates = pd.to_datetime(frame["Date"], errors="coerce")
    prices = pd.to_numeric(frame[price_column], errors="coerce")
    start_date = pd.to_datetime(start, errors="coerce")
    end_date = pd.to_datetime(end, errors="coerce")
    valid = dates.notna() & prices.notna() & (prices > 0)
    if pd.isna(start_date) or pd.isna(end_date):
        return None
    valid &= (dates >= start_date) & (dates <= end_date)
    dates, prices = dates[valid], prices[valid]
    if len(prices) < 2 or prices.iloc[0] <= 0:
        return None
    return dates, INITIAL_CAPITAL * prices / prices.iloc[0]


def generate_buyhold_chart(data_file: Path, start: str, end: str, output_path: Path) -> bool:
    series = buyhold_window(data_file, start, end)
    if series is None:
        return False
    dates, portfolio = series
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(5.2, 1.9), dpi=80)
    axis.plot(dates, portfolio, color="#0a715f", linewidth=2.2)
    axis.fill_between(dates, portfolio, INITIAL_CAPITAL, color="#0a715f", alpha=0.12)
    axis.set_axis_off()
    axis.margins(x=0.02, y=0.18)
    figure.tight_layout(pad=0.05)
    figure.savefig(output_path, dpi=80, bbox_inches="tight", pad_inches=0.03)
    plt.close(figure)
    return True
