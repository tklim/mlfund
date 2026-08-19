"""Create compact buy-and-hold chart thumbnails for the static dashboard."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


INITIAL_CAPITAL = 10_000.0
POSITIVE_COLOR = "#0a715f"
NEGATIVE_COLOR = "#b24b42"
DEFAULT_YEARS = (5.0, 4.0, 3.0)


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
    window = pd.DataFrame({"date": dates[valid], "price": prices[valid]}).sort_values("date")
    dates, prices = window["date"], window["price"]
    if len(prices) < 2 or prices.iloc[0] <= 0:
        return None
    return dates, INITIAL_CAPITAL * prices / prices.iloc[0]


def buyhold_period_metrics(data_file: Path, years: float, end_date: str | None = None) -> dict[str, object] | None:
    """Return a trailing buy-and-hold window when the CSV covers the requested duration."""
    try:
        frame = pd.read_csv(data_file)
    except (OSError, ValueError, UnicodeError):
        return None
    if "Date" not in frame:
        return None
    price_column = "TotalReturn" if "TotalReturn" in frame else "NAV" if "NAV" in frame else None
    if price_column is None:
        return None
    clean = pd.DataFrame({
        "date": pd.to_datetime(frame["Date"], errors="coerce"),
        "price": pd.to_numeric(frame[price_column], errors="coerce"),
    }).dropna()
    clean = clean[clean["price"] > 0].sort_values("date")
    if len(clean) < 2 or years <= 0:
        return None
    requested_end = pd.to_datetime(end_date, errors="coerce") if end_date else clean["date"].iloc[-1]
    if pd.isna(requested_end):
        return None
    clean = clean[clean["date"] <= requested_end]
    if len(clean) < 2:
        return None
    actual_end = clean["date"].iloc[-1]
    requested_start = actual_end - pd.DateOffset(months=round(years * 12))
    window = clean[clean["date"] >= requested_start]
    if len(window) < 2:
        return None
    actual_days = (window["date"].iloc[-1] - window["date"].iloc[0]).days
    if actual_days < years * 365.25 * 0.95:
        return None
    growth = window["price"].iloc[-1] / window["price"].iloc[0]
    if growth <= 0 or actual_days <= 0:
        return None
    annualized = (growth ** (365.25 / actual_days) - 1) * 100
    return {
        "start": window["date"].iloc[0].strftime("%Y-%m-%d"),
        "end": actual_end.strftime("%Y-%m-%d"),
        "annualized": round(float(annualized), 8),
    }


def generate_buyhold_chart(data_file: Path, start: str, end: str, output_path: Path) -> bool:
    series = buyhold_window(data_file, start, end)
    if series is None:
        return False
    dates, portfolio = series
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(5.2, 1.9), dpi=80)
    color = NEGATIVE_COLOR if portfolio.iloc[-1] < portfolio.iloc[0] else POSITIVE_COLOR
    axis.plot(dates, portfolio, color=color, linewidth=2.2)
    axis.fill_between(dates, portfolio, INITIAL_CAPITAL, color=color, alpha=0.12)
    axis.set_axis_off()
    axis.margins(x=0.02, y=0.18)
    figure.tight_layout(pad=0.05)
    figure.savefig(output_path, dpi=80, bbox_inches="tight", pad_inches=0.03)
    plt.close(figure)
    return True


def generate_buyhold_period_charts(
    data_file: Path,
    output_dir: Path,
    years: Iterable[float] = DEFAULT_YEARS,
    prefix: str | None = None,
    end_date: str | None = None,
) -> tuple[list[dict[str, object]], list[float]]:
    """Generate all requested horizons against one consistent latest end date."""
    safe_prefix = re.sub(r"[^a-zA-Z0-9_-]+", "-", prefix or data_file.stem).strip("-") or "buyhold"
    generated: list[dict[str, object]] = []
    skipped: list[float] = []
    for value in years:
        period = float(value)
        metrics = buyhold_period_metrics(data_file, period, end_date=end_date)
        if metrics is None:
            skipped.append(period)
            continue
        label = f"{period:g}y"
        output_path = output_dir / f"{safe_prefix}-{label}.png"
        if not generate_buyhold_chart(data_file, metrics["start"], metrics["end"], output_path):
            skipped.append(period)
            continue
        generated.append({**metrics, "years": period, "output": output_path})
    return generated, skipped


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate compact 5Y, 4Y and 3Y buy-and-hold charts.")
    parser.add_argument("--data-file", required=True, type=Path, help="Source CSV containing Date and TotalReturn or NAV.")
    parser.add_argument("--output-dir", type=Path, default=Path.cwd(), help="Directory for generated PNG files.")
    parser.add_argument("--years", nargs="+", type=float, default=list(DEFAULT_YEARS), help="Trailing durations to generate; defaults to 5 4 3.")
    parser.add_argument("--prefix", help="Filename prefix; defaults to the source CSV stem.")
    parser.add_argument("--end-date", help="Optional YYYY-MM-DD cutoff; defaults to the latest usable CSV date.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.data_file.is_file():
        print(f"Source CSV not found: {args.data_file}")
        return 2
    generated, skipped = generate_buyhold_period_charts(
        args.data_file,
        args.output_dir,
        years=args.years,
        prefix=args.prefix,
        end_date=args.end_date,
    )
    for item in generated:
        print(f"Generated {item['years']:g}Y through {item['end']}: {item['output']}")
    for years in skipped:
        print(f"Skipped {years:g}Y: insufficient usable source history.")
    return 0 if generated and not skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
