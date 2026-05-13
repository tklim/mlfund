import argparse
import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm

from common import DATA_DIR, REPORTS_DIR, fund_label_from_data_file, resolve_repo_path, save_csv


DEFAULT_HORIZONS = ["1M:21", "3M:63", "6M:126", "9M:189", "1Y:252"]
DEFAULT_THRESHOLDS = [0.00, 0.05, 0.10]
DEFAULT_UPSIDE_THRESHOLDS = [0.15, 0.20, 0.25, 0.30]
HEADLINE_UPSIDE_THRESHOLD = 0.20
TRADING_DAYS = 252


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze forward-return probabilities for fund TotalReturn series."
    )
    parser.add_argument(
        "--data-file",
        default="data/HWFL_HWFlexi_nav_5Y.csv",
        help="CSV file to analyze. Relative paths resolve from repo root.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Analyze every local fund CSV matching --fund-glob.",
    )
    parser.add_argument(
        "--fund-glob",
        default="*_nav_5Y.csv",
        help="Data glob under data/ when --all is used (default: *_nav_5Y.csv).",
    )
    parser.add_argument(
        "--date-column",
        default="Date",
        help="Date column name in the CSV (default: Date).",
    )
    parser.add_argument(
        "--price-column",
        default="TotalReturn",
        help="Price/return column to analyze (default: TotalReturn).",
    )
    parser.add_argument(
        "--horizons",
        nargs="+",
        default=DEFAULT_HORIZONS,
        help="Holding horizons as LABEL:DAYS, for example 1M:21 1Y:252 2Y:504.",
    )
    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=DEFAULT_THRESHOLDS,
        help="Return thresholds as decimals, for example -0.05 0 0.05 0.10.",
    )
    parser.add_argument(
        "--upside-thresholds",
        nargs="+",
        type=float,
        default=DEFAULT_UPSIDE_THRESHOLDS,
        help="Upside stretch thresholds as decimals, for example 0.15 0.20 0.25 0.30.",
    )
    parser.add_argument(
        "--non-overlap",
        action="store_true",
        help="Also calculate independent non-overlapping forward-return windows.",
    )
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=1000,
        help="Number of block-bootstrap simulations per horizon (default: 1000).",
    )
    parser.add_argument(
        "--bootstrap-block-days",
        type=int,
        default=21,
        help="Block size for horizons longer than 1M in bootstrap simulations (default: 21).",
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=42,
        help="Random seed for bootstrap simulations (default: 42).",
    )
    parser.add_argument(
        "--charts",
        action="store_true",
        help="Generate simple probability, histogram, and drawdown charts.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPORTS_DIR),
        help=f"Directory for generated CSV outputs (default: {REPORTS_DIR}).",
    )
    return parser.parse_args()


def parse_horizons(values):
    horizons = {}
    for value in values:
        if ":" not in value:
            raise ValueError(f"Invalid horizon '{value}'. Use LABEL:DAYS, for example 1Y:252.")
        label, days_text = value.split(":", 1)
        label = label.strip()
        days = int(days_text)
        if not label or days <= 0:
            raise ValueError(f"Invalid horizon '{value}'. Days must be greater than 0.")
        horizons[label] = days
    return horizons


def resolve_input_path(data_file):
    return resolve_repo_path(data_file)


def load_total_return_data(csv_path, date_col="Date", total_return_col="TotalReturn"):
    df = pd.read_csv(csv_path)
    missing = [col for col in [date_col, total_return_col] if col not in df.columns]
    if missing:
        raise ValueError(f"{csv_path} is missing required column(s): {missing}")

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[total_return_col] = pd.to_numeric(df[total_return_col], errors="coerce")
    df = df.sort_values(date_col).dropna(subset=[date_col, total_return_col])
    df = df[df[total_return_col] > 0]
    df = df[[date_col, total_return_col]].copy()
    df = df.rename(columns={date_col: "Date", total_return_col: "TotalReturn"})
    if df.empty:
        raise ValueError(f"{csv_path} has no valid positive {total_return_col} values.")
    return df


def calculate_forward_return_frame(df, label, days, step=1):
    frame = pd.DataFrame(
        {
            "Start Date": df["Date"],
            "End Date": df["Date"].shift(-days),
            "Forward Return": df["TotalReturn"].shift(-days) / df["TotalReturn"] - 1,
        }
    ).dropna()
    if step > 1:
        frame = frame.iloc[::step].copy()
    frame["Horizon"] = label
    frame["Horizon Days"] = days
    return frame.reset_index(drop=True)


def calendar_offset_from_horizon(label, fallback_days):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([DMWY])\s*", str(label), flags=re.IGNORECASE)
    if not match:
        return pd.DateOffset(days=fallback_days)

    amount = float(match.group(1))
    unit = match.group(2).upper()
    if unit == "D":
        return pd.DateOffset(days=int(round(amount)))
    if unit == "W":
        return pd.DateOffset(weeks=int(round(amount)))
    if unit == "M":
        return pd.DateOffset(months=int(round(amount)))
    if unit == "Y":
        return pd.DateOffset(months=int(round(amount * 12)))
    return pd.DateOffset(days=fallback_days)


def calculate_calendar_forward_return_frame(df, label, days, step=1):
    offset = calendar_offset_from_horizon(label, days)
    starts = df[["Date", "TotalReturn"]].rename(
        columns={"Date": "Start Date", "TotalReturn": "Start TotalReturn"}
    )
    starts["Target End Date"] = starts["Start Date"] + offset

    ends = df[["Date", "TotalReturn"]].rename(
        columns={"Date": "End Date", "TotalReturn": "End TotalReturn"}
    )
    frame = pd.merge_asof(
        starts.sort_values("Target End Date"),
        ends.sort_values("End Date"),
        left_on="Target End Date",
        right_on="End Date",
        direction="forward",
    ).dropna(subset=["End Date", "End TotalReturn"])

    frame["Forward Return"] = frame["End TotalReturn"] / frame["Start TotalReturn"] - 1
    frame["Horizon"] = label
    frame["Horizon Days"] = days
    frame["Calendar Horizon"] = True
    frame = frame.sort_values("Start Date").reset_index(drop=True)
    if step > 1:
        frame = frame.iloc[::step].copy()
    return frame.reset_index(drop=True)


def wilson_interval(probability, effective_n, z=1.96):
    if effective_n <= 0 or pd.isna(probability):
        return np.nan, np.nan
    denominator = 1 + (z**2 / effective_n)
    center = probability + (z**2 / (2 * effective_n))
    margin = z * np.sqrt((probability * (1 - probability) / effective_n) + (z**2 / (4 * effective_n**2)))
    return (center - margin) / denominator, (center + margin) / denominator


def expected_shortfall(returns, tail=0.05):
    if returns.empty:
        return np.nan
    cutoff = returns.quantile(tail)
    return returns[returns <= cutoff].mean()


def summarize_return_distribution(frame):
    returns = frame["Forward Return"].dropna()
    if returns.empty:
        return {
            "Observations": 0,
            "Average Forward Return": np.nan,
            "Median Forward Return": np.nan,
            "Std Forward Return": np.nan,
            "Forward Return P05": np.nan,
            "Forward Return P25": np.nan,
            "Forward Return P75": np.nan,
            "Forward Return P95": np.nan,
            "Worst Forward Return": np.nan,
            "Best Forward Return": np.nan,
            "Expected Shortfall 5%": np.nan,
            "Expected Shortfall 10%": np.nan,
            "Worst Start Date": "",
            "Worst End Date": "",
            "Best Start Date": "",
            "Best End Date": "",
        }

    worst_idx = returns.idxmin()
    best_idx = returns.idxmax()
    return {
        "Observations": len(returns),
        "Average Forward Return": returns.mean(),
        "Median Forward Return": returns.median(),
        "Std Forward Return": returns.std(ddof=1),
        "Forward Return P05": returns.quantile(0.05),
        "Forward Return P25": returns.quantile(0.25),
        "Forward Return P75": returns.quantile(0.75),
        "Forward Return P95": returns.quantile(0.95),
        "Worst Forward Return": returns.min(),
        "Best Forward Return": returns.max(),
        "Expected Shortfall 5%": expected_shortfall(returns, 0.05),
        "Expected Shortfall 10%": expected_shortfall(returns, 0.10),
        "Worst Start Date": frame.loc[worst_idx, "Start Date"].date(),
        "Worst End Date": frame.loc[worst_idx, "End Date"].date(),
        "Best Start Date": frame.loc[best_idx, "Start Date"].date(),
        "Best End Date": frame.loc[best_idx, "End Date"].date(),
    }


def probability_rows_from_returns(fund_label, method, label, days, frame, thresholds, effective_observations=None):
    stats = summarize_return_distribution(frame)
    returns = frame["Forward Return"].dropna()
    observations = len(returns)
    effective_n = effective_observations if effective_observations is not None else observations
    rows = []
    for threshold in thresholds:
        probability = (returns >= threshold).mean() if observations else np.nan
        ci_low, ci_high = wilson_interval(probability, effective_n)
        rows.append(
            {
                "Fund Label": fund_label,
                "Analysis Method": method,
                "Horizon": label,
                "Horizon Days": days,
                "Threshold": threshold,
                "Probability": probability,
                "Probability CI Low": ci_low,
                "Probability CI High": ci_high,
                "Effective Observations": effective_n,
                **stats,
            }
        )
    return rows


def historical_probability_analysis(fund_label, df, horizons, thresholds, include_non_overlap=False):
    rows = []
    forward_frames = {}
    stretch_frames = []
    for label, days in horizons.items():
        if len(df) <= days:
            print(f"Skipping {label}: need more than {days} rows, found {len(df)}.")
            continue
        overlapping = calculate_forward_return_frame(df, label, days, step=1)
        effective_n = max(1, len(overlapping) // days)
        rows.extend(
            probability_rows_from_returns(
                fund_label,
                "Historical Overlapping Windows",
                label,
                days,
                overlapping,
                thresholds,
                effective_observations=effective_n,
            )
        )
        forward_frames[label] = overlapping
        calendar_overlapping = calculate_calendar_forward_return_frame(df, label, days, step=1)
        if not calendar_overlapping.empty:
            stretch_frames.append(("Historical Calendar Windows", label, days, calendar_overlapping))

        if include_non_overlap:
            non_overlap = calculate_forward_return_frame(df, label, days, step=days)
            rows.extend(
                probability_rows_from_returns(
                    fund_label,
                    "Historical Non-Overlapping Windows",
                    label,
                    days,
                    non_overlap,
                    thresholds,
                )
            )
            calendar_non_overlap = calculate_calendar_forward_return_frame(df, label, days, step=days)
            if not calendar_non_overlap.empty:
                stretch_frames.append(("Historical Calendar Non-Overlapping Windows", label, days, calendar_non_overlap))
    return pd.DataFrame(rows), forward_frames, stretch_frames


def categorize_upside_threshold(threshold, p75, p90, p95, max_return):
    if pd.isna(max_return):
        return ""
    if threshold > max_return:
        return "Beyond history"
    if threshold <= p75:
        return "Common upside"
    if threshold <= p90:
        return "Strong upside"
    if threshold <= p95:
        return "Rare upside"
    return "Extreme upside"


def upside_stretch_analysis(fund_label, stretch_frames, upside_thresholds):
    rows = []
    for method, label, days, frame in stretch_frames:
        returns = frame["Forward Return"].dropna()
        if returns.empty:
            continue

        p75 = returns.quantile(0.75)
        p90 = returns.quantile(0.90)
        p95 = returns.quantile(0.95)
        p99 = returns.quantile(0.99)
        max_return = returns.max()
        max_idx = returns.idxmax()
        max_start_date = frame.loc[max_idx, "Start Date"]
        max_end_date = frame.loc[max_idx, "End Date"]

        for threshold in upside_thresholds:
            rows.append(
                {
                    "Fund Label": fund_label,
                    "Analysis Method": method,
                    "Horizon": label,
                    "Horizon Days": days,
                    "Upside Threshold": threshold,
                    "Probability >= Upside Threshold": (returns >= threshold).mean(),
                    "Upside Percentile Rank": (returns <= threshold).mean(),
                    "Return P75": p75,
                    "Return P90": p90,
                    "Return P95": p95,
                    "Return P99": p99,
                    "Max Historical Forward Return": max_return,
                    "Max Historical Start Date": max_start_date.date(),
                    "Max Historical End Date": max_end_date.date(),
                    "Upside Category": categorize_upside_threshold(threshold, p75, p90, p95, max_return),
                    "Observations": len(returns),
                }
            )
    return pd.DataFrame(rows)


def lognormal_model_probability_analysis(fund_label, df, horizons, thresholds):
    daily_log_returns = np.log(df["TotalReturn"] / df["TotalReturn"].shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    daily_mu = daily_log_returns.mean()
    daily_sigma = daily_log_returns.std(ddof=1)

    rows = []
    for label, days in horizons.items():
        horizon_mu = daily_mu * days
        horizon_sigma = daily_sigma * np.sqrt(days)
        quantiles = {
            "Forward Return P05": np.exp(norm.ppf(0.05, loc=horizon_mu, scale=horizon_sigma)) - 1,
            "Forward Return P25": np.exp(norm.ppf(0.25, loc=horizon_mu, scale=horizon_sigma)) - 1,
            "Forward Return P75": np.exp(norm.ppf(0.75, loc=horizon_mu, scale=horizon_sigma)) - 1,
            "Forward Return P95": np.exp(norm.ppf(0.95, loc=horizon_mu, scale=horizon_sigma)) - 1,
        }
        for threshold in thresholds:
            log_threshold = np.log(1 + threshold)
            probability = 1 - norm.cdf(log_threshold, loc=horizon_mu, scale=horizon_sigma)
            rows.append(
                {
                    "Fund Label": fund_label,
                    "Analysis Method": "Simplified Lognormal Model",
                    "Horizon": label,
                    "Horizon Days": days,
                    "Threshold": threshold,
                    "Probability": probability,
                    "Probability CI Low": np.nan,
                    "Probability CI High": np.nan,
                    "Effective Observations": len(daily_log_returns),
                    "Observations": len(daily_log_returns),
                    "Average Forward Return": np.exp(horizon_mu) - 1,
                    "Median Forward Return": np.exp(horizon_mu) - 1,
                    "Std Forward Return": horizon_sigma,
                    "Worst Forward Return": np.nan,
                    "Best Forward Return": np.nan,
                    "Expected Shortfall 5%": np.nan,
                    "Expected Shortfall 10%": np.nan,
                    "Worst Start Date": "",
                    "Worst End Date": "",
                    "Best Start Date": "",
                    "Best End Date": "",
                    **quantiles,
                }
            )
    return pd.DataFrame(rows)


def sample_block_bootstrap_returns(log_returns, horizon_days, samples, block_days, rng):
    values = np.asarray(log_returns.dropna(), dtype=float)
    if len(values) == 0:
        return np.array([])
    block_length = 1 if horizon_days <= 21 else max(1, min(block_days, len(values)))
    simulated = np.empty(samples)
    for i in range(samples):
        path = []
        while len(path) < horizon_days:
            if len(values) <= block_length:
                start = 0
            else:
                start = rng.integers(0, len(values) - block_length + 1)
            path.extend(values[start : start + block_length])
        simulated[i] = np.exp(np.sum(path[:horizon_days])) - 1
    return simulated


def bootstrap_model_probability_analysis(fund_label, df, horizons, thresholds, samples, block_days, seed):
    daily_log_returns = np.log(df["TotalReturn"] / df["TotalReturn"].shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    rng = np.random.default_rng(seed)
    rows = []
    for label, days in horizons.items():
        simulated = sample_block_bootstrap_returns(daily_log_returns, days, samples, block_days, rng)
        frame = pd.DataFrame({"Forward Return": simulated})
        frame["Start Date"] = pd.NaT
        frame["End Date"] = pd.NaT
        rows.extend(
            probability_rows_from_returns(
                fund_label,
                "Block Bootstrap Model",
                label,
                days,
                frame,
                thresholds,
                effective_observations=len(simulated),
            )
        )
    return pd.DataFrame(rows)


def max_drawdown(series):
    drawdown = series / series.cummax() - 1
    return drawdown.min()


def performance_summary(fund_label, df):
    start_value = df["TotalReturn"].iloc[0]
    end_value = df["TotalReturn"].iloc[-1]
    total_return = end_value / start_value - 1
    num_days = (df["Date"].iloc[-1] - df["Date"].iloc[0]).days
    years = num_days / 365.25
    annualized_return = (end_value / start_value) ** (1 / years) - 1 if years > 0 else np.nan

    daily_returns = df["TotalReturn"].pct_change().dropna()
    downside_returns = daily_returns[daily_returns < 0]
    monthly_returns = (
        df.set_index("Date")["TotalReturn"].resample("ME").last().pct_change().dropna()
        if len(df) > 1
        else pd.Series(dtype=float)
    )

    return pd.DataFrame(
        [
            {
                "Fund Label": fund_label,
                "Start Date": df["Date"].iloc[0].date(),
                "End Date": df["Date"].iloc[-1].date(),
                "Rows": len(df),
                "Start TotalReturn": start_value,
                "End TotalReturn": end_value,
                "Total Cumulative Return": total_return,
                "Annualized Return": annualized_return,
                "Annualized Volatility": daily_returns.std(ddof=1) * np.sqrt(TRADING_DAYS),
                "Downside Volatility": downside_returns.std(ddof=1) * np.sqrt(TRADING_DAYS),
                "Negative Daily Return %": (daily_returns < 0).mean(),
                "Worst Monthly Return": monthly_returns.min() if not monthly_returns.empty else np.nan,
                "Max Drawdown": max_drawdown(df["TotalReturn"]),
            }
        ]
    )


def format_percent_columns(df):
    formatted = df.copy()
    for col in formatted.columns:
        if col in {"Start TotalReturn", "End TotalReturn"}:
            formatted[col] = formatted[col].map(lambda x: f"{x:.4f}" if pd.notna(x) and x != "" else "")
        elif col in {"Threshold", "Upside Threshold"}:
            formatted[col] = formatted[col].map(lambda x: f"{x:.2%}" if pd.notna(x) else "")
        elif any(token in col for token in ["Return", "Probability", "Volatility", "Drawdown"]):
            formatted[col] = formatted[col].map(lambda x: f"{x:.2%}" if pd.notna(x) and x != "" else "")
        elif "Percentile Rank" in col:
            formatted[col] = formatted[col].map(lambda x: f"{x:.2%}" if pd.notna(x) and x != "" else "")
    return formatted


def plot_probability_chart(fund_label, probability_report, output_dir):
    historical = probability_report[
        (probability_report["Analysis Method"] == "Historical Overlapping Windows")
        & (probability_report["Threshold"] == 0)
    ]
    if historical.empty:
        return None
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(historical["Horizon"], historical["Probability"], color="#2b8cbe", edgecolor="black")
    ax.set_title(f"{fund_label}: Probability of Positive Return")
    ax.set_xlabel("Holding Horizon")
    ax.set_ylabel("Probability")
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    path = output_dir / f"{fund_label}_probability_by_horizon.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_forward_return_histogram(fund_label, forward_frames, output_dir):
    if not forward_frames:
        return None
    label = next(reversed(forward_frames))
    frame = forward_frames[label]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(frame["Forward Return"].dropna(), bins=30, color="#74a9cf", edgecolor="black")
    ax.set_title(f"{fund_label}: {label} Forward Return Distribution")
    ax.set_xlabel("Forward Return")
    ax.set_ylabel("Count")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = output_dir / f"{fund_label}_{label}_forward_return_histogram.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_drawdown_chart(fund_label, df, output_dir):
    drawdown = df["TotalReturn"] / df["TotalReturn"].cummax() - 1
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["Date"], drawdown, color="#d95f0e", linewidth=1.8)
    ax.fill_between(df["Date"], drawdown, 0, color="#fdd0a2", alpha=0.35)
    ax.set_title(f"{fund_label}: Drawdown")
    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = output_dir / f"{fund_label}_drawdown.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def analyze_one_file(csv_path, args, horizons, thresholds, output_dir):
    fund_label = fund_label_from_data_file(csv_path)
    df = load_total_return_data(csv_path, date_col=args.date_column, total_return_col=args.price_column)
    summary = performance_summary(fund_label, df)
    historical, forward_frames, stretch_frames = historical_probability_analysis(
        fund_label,
        df,
        horizons,
        thresholds,
        include_non_overlap=args.non_overlap,
    )
    lognormal = lognormal_model_probability_analysis(fund_label, df, horizons, thresholds)
    bootstrap = bootstrap_model_probability_analysis(
        fund_label,
        df,
        horizons,
        thresholds,
        samples=args.bootstrap_samples,
        block_days=args.bootstrap_block_days,
        seed=args.bootstrap_seed,
    )
    probability_report = pd.concat([historical, lognormal, bootstrap], ignore_index=True)
    upside_report = upside_stretch_analysis(fund_label, stretch_frames, args.upside_thresholds)

    summary_path = save_csv(summary, output_dir / f"{fund_label}_probability_summary.csv")
    report_path = save_csv(probability_report, output_dir / f"{fund_label}_probability_report.csv")
    upside_path = save_csv(upside_report, output_dir / f"{fund_label}_upside_stretch_report.csv")

    chart_paths = []
    if args.charts:
        chart_paths = [
            path
            for path in [
                plot_probability_chart(fund_label, probability_report, output_dir),
                plot_forward_return_histogram(fund_label, forward_frames, output_dir),
                plot_drawdown_chart(fund_label, df, output_dir),
            ]
            if path is not None
        ]

    print(f"\n=== {fund_label}: TotalReturn Performance Summary ===")
    print(format_percent_columns(summary).to_string(index=False))
    print("\n=== Probability Report ===")
    display_cols = [
        "Analysis Method",
        "Horizon",
        "Threshold",
        "Probability",
        "Probability CI Low",
        "Probability CI High",
        "Observations",
        "Effective Observations",
        "Average Forward Return",
        "Worst Forward Return",
        "Best Forward Return",
    ]
    print(format_percent_columns(probability_report[display_cols]).to_string(index=False))
    print("\n=== Upside Stretch Report ===")
    upside_display_cols = [
        "Analysis Method",
        "Horizon",
        "Upside Threshold",
        "Probability >= Upside Threshold",
        "Upside Percentile Rank",
        "Return P75",
        "Return P90",
        "Return P95",
        "Return P99",
        "Max Historical Forward Return",
        "Max Historical Start Date",
        "Max Historical End Date",
        "Upside Category",
        "Observations",
    ]
    if upside_report.empty:
        print("No upside stretch rows generated.")
    else:
        print(format_percent_columns(upside_report[upside_display_cols]).to_string(index=False))
    print("\nSaved files:")
    print(f"- {summary_path}")
    print(f"- {report_path}")
    print(f"- {upside_path}")
    for chart_path in chart_paths:
        print(f"- {chart_path}")

    return summary, probability_report, upside_report


def build_cross_fund_summary(summaries, reports, thresholds, upside_reports):
    if not summaries:
        return pd.DataFrame()
    cross = pd.concat(summaries, ignore_index=True)
    report_df = pd.concat(reports, ignore_index=True) if reports else pd.DataFrame()
    if not report_df.empty:
        primary = report_df[report_df["Analysis Method"] == "Historical Overlapping Windows"]
        for horizon in primary["Horizon"].dropna().unique():
            for threshold in thresholds:
                subset = primary[(primary["Horizon"] == horizon) & (primary["Threshold"] == threshold)]
                if subset.empty:
                    continue
                col = f"{horizon} Probability >= {threshold:.0%}"
                values = subset.set_index("Fund Label")["Probability"]
                cross[col] = cross["Fund Label"].map(values)

    upside_df = pd.concat(upside_reports, ignore_index=True) if upside_reports else pd.DataFrame()
    if not upside_df.empty:
        primary_upside = upside_df[
            (upside_df["Analysis Method"] == "Historical Calendar Windows")
            & (np.isclose(upside_df["Upside Threshold"], HEADLINE_UPSIDE_THRESHOLD))
        ]
        for horizon in primary_upside["Horizon"].dropna().unique():
            subset = primary_upside[primary_upside["Horizon"] == horizon]
            if subset.empty:
                continue
            by_fund = subset.set_index("Fund Label")
            threshold_label = f"{HEADLINE_UPSIDE_THRESHOLD:.0%}"
            cross[f"{horizon} Probability >= {threshold_label}"] = cross["Fund Label"].map(
                by_fund["Probability >= Upside Threshold"]
            )
            cross[f"{horizon} {threshold_label} Upside Category"] = cross["Fund Label"].map(by_fund["Upside Category"])
            cross[f"{horizon} {threshold_label} Percentile Rank"] = cross["Fund Label"].map(
                by_fund["Upside Percentile Rank"]
            )
    return cross


def main():
    args = parse_args()
    horizons = parse_horizons(args.horizons)
    thresholds = tuple(args.thresholds)
    output_dir = resolve_repo_path(args.output_dir)

    if args.all:
        csv_paths = sorted(DATA_DIR.glob(args.fund_glob))
        if not csv_paths:
            raise FileNotFoundError(f"No files matched data/{args.fund_glob}")
    else:
        csv_paths = [resolve_input_path(args.data_file)]
        if not csv_paths[0].exists():
            raise FileNotFoundError(f"CSV file not found: {csv_paths[0]}")

    summaries = []
    reports = []
    upside_reports = []
    for csv_path in csv_paths:
        try:
            summary, report, upside_report = analyze_one_file(csv_path, args, horizons, thresholds, output_dir)
            summaries.append(summary)
            reports.append(report)
            upside_reports.append(upside_report)
        except Exception as exc:
            print(f"Skipping {csv_path}: {exc}")
            if not args.all:
                raise

    if args.all:
        cross_fund_summary = build_cross_fund_summary(summaries, reports, thresholds, upside_reports)
        cross_path = save_csv(cross_fund_summary, output_dir / "fund_probability_cross_fund_summary.csv")
        print(f"\nCross-fund summary saved to: {cross_path}")


if __name__ == "__main__":
    main()
