import argparse
import bisect
import html
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
import pandas as pd
from scipy.stats import beta as beta_distribution

from common import (
    CHARTS_DIR,
    DATA_DIR,
    REPORTS_DIR,
    calculate_rsi,
    fund_label_from_data_file,
    resolve_repo_path,
    save_csv,
)
from fund_probability_analysis import (
    calculate_calendar_forward_return_frame,
    expected_shortfall,
    load_total_return_data,
    parse_horizons,
    wilson_interval,
)


DEFAULT_HORIZONS = ["1M:21", "3M:63", "6M:126", "1Y:252"]
DEFAULT_CONTINUOUS_FEATURES = [
    "Trailing Return 1M",
    "Trailing Return 3M",
    "Trailing Return 6M",
    "Drawdown From 6M High",
    "Drawdown From 1Y High",
    "Rebound From 3M Low",
    "Annualized Volatility 3M",
    "RSI 14",
    "EMA 50/200 Gap",
    "EMA 200 Slope 1M",
]
LEGACY_CONTINUOUS_FEATURES = [
    "Trailing Return 1M",
    "Trailing Return 3M",
    "Trailing Return 6M",
    "Drawdown From 6M High",
    "Annualized Volatility 3M",
    "RSI 14",
    "EMA 50/200 Gap",
    "EMA 200 Slope 1M",
]
FEATURE_WEIGHTS = {
    "Trailing Return 1M": 1.00,
    "Trailing Return 3M": 1.10,
    "Trailing Return 6M": 1.10,
    "Drawdown From 6M High": 1.20,
    "Drawdown From 1Y High": 1.10,
    "Rebound From 3M Low": 1.00,
    "Annualized Volatility 3M": 0.85,
    "RSI 14": 0.65,
    "EMA 50/200 Gap": 1.10,
    "EMA 200 Slope 1M": 0.80,
}
ACTION_ORDER = {"BUY": 0, "HOLD / WATCH": 1, "SELL / AVOID": 2}
TRADING_DAYS = 252
CHART_DPI = 200
# A mismatched trend regime makes an analog less similar, but must not make
# past recoveries unreachable from a current downtrend (soft penalty, was 1.0).
TREND_STATE_MISMATCH_PENALTY = 0.25
LEGACY_TREND_STATE_MISMATCH_PENALTY = 1.0
DEFAULT_PRIOR_STRENGTH = 4.0
DEFAULT_FORWARD_METHOD = "dual_relative_v2"
FORWARD_METHOD_CHOICES = ("legacy", "dual-relative-v2")
RELATIVE_UPSIDE_QUANTILE = 0.75
RELATIVE_DOWNSIDE_QUANTILE = 0.25
TREND_MOMENTUM_PERCENTILE = 0.55
RECOVERY_MOMENTUM_PERCENTILE = 0.40
SELL_MOMENTUM_PERCENTILE = 0.45
MIN_SCORE_SIGMA = 0.01


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a conditional forward probability dashboard for fund buy/hold/sell decisions."
    )
    parser.add_argument(
        "--data-file",
        default="data/HWFL_HWFlexi_nav_5Y.csv",
        help="CSV file to analyze when --all is not used. Relative paths resolve from repo root.",
    )
    parser.add_argument(
        "--data-files",
        nargs="+",
        default=None,
        help="Explicit CSV files to analyze. Overrides --all and --data-file.",
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
    parser.add_argument("--date-column", default="Date", help="Date column name in the CSV.")
    parser.add_argument("--price-column", default="TotalReturn", help="Price/value column to analyze.")
    parser.add_argument(
        "--horizons",
        nargs="+",
        default=DEFAULT_HORIZONS,
        help="Holding horizons as LABEL:DAYS, for example 1M:21 6M:126 1Y:252.",
    )
    parser.add_argument("--primary-horizon", default="6M", help="Horizon used for headline decision label.")
    parser.add_argument(
        "--forward-method",
        choices=FORWARD_METHOD_CHOICES,
        default="dual-relative-v2",
        help="Forward methodology (default: dual-relative-v2).",
    )
    parser.add_argument(
        "--upside-target",
        type=float,
        default=0.15,
        help="Upside return target at the primary horizon as a decimal (default: 0.15).",
    )
    parser.add_argument(
        "--downside-risk",
        type=float,
        default=-0.08,
        help="Downside threshold at the primary horizon as a decimal (default: -0.08).",
    )
    parser.add_argument(
        "--target-scaling",
        choices=["compounded", "fixed"],
        default="compounded",
        help="Scale return thresholds to each horizon by compounding, or use fixed thresholds (default: compounded).",
    )
    parser.add_argument(
        "--min-analogs",
        type=int,
        default=6,
        help="Minimum independent analog periods required above low confidence (default: 6).",
    )
    parser.add_argument(
        "--max-analogs",
        type=int,
        default=20,
        help="Maximum non-overlapping nearest analog periods to use (default: 20).",
    )
    parser.add_argument(
        "--legacy-max-analogs",
        type=int,
        default=150,
        help="Maximum overlapping rows used only by the legacy comparison method (default: 150).",
    )
    parser.add_argument(
        "--prior-strength",
        type=float,
        default=DEFAULT_PRIOR_STRENGTH,
        help="Unconditional base-rate pseudo-observations used to shrink analog estimates (default: 4).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPORTS_DIR),
        help=f"Directory for CSV/HTML outputs (default: {REPORTS_DIR}).",
    )
    parser.add_argument(
        "--chart-dir",
        default=str(CHARTS_DIR / "forward_decision"),
        help="Directory for generated dashboard charts.",
    )
    parser.add_argument("--charts", action="store_true", help="Generate dashboard charts.")
    parser.add_argument(
        "--all-horizon-chart",
        action="store_true",
        help="Generate one combined decision-score heatmap across all configured horizons.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run lightweight validation checks after generating outputs.",
    )
    return parser.parse_args()


def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def trend_state(row):
    if pd.isna(row["EMA 50"]) or pd.isna(row["EMA 200"]):
        return "insufficient trend history"
    if row["EMA 50"] > row["EMA 200"] and row["EMA 200 Slope 1M"] >= 0:
        return "uptrend"
    if row["EMA 50"] < row["EMA 200"] and row["EMA 200 Slope 1M"] < 0:
        return "downtrend"
    if row["EMA 50"] > row["EMA 200"]:
        return "softening uptrend"
    return "recovering / mixed"


def annualize_return(value, periods_per_year):
    if pd.isna(value) or value <= -1:
        return np.nan
    return (1.0 + float(value)) ** float(periods_per_year) - 1.0


def expanding_prior_percentile(series, min_history=60):
    """Rank each value against prior values only, without look-ahead."""
    ranked = []
    percentiles = []
    for value in pd.to_numeric(series, errors="coerce"):
        if pd.isna(value):
            percentiles.append(np.nan)
            continue
        percentile = bisect.bisect_right(ranked, float(value)) / len(ranked) if len(ranked) >= min_history else np.nan
        percentiles.append(percentile)
        bisect.insort(ranked, float(value))
    return pd.Series(percentiles, index=series.index, dtype=float)


def add_state_features(df):
    frame = df.copy()
    price = frame["TotalReturn"]
    daily_returns = price.pct_change()

    frame["Trailing Return 1M"] = price.pct_change(21)
    frame["Trailing Return 3M"] = price.pct_change(63)
    frame["Trailing Return 6M"] = price.pct_change(126)
    trailing_high_6m = price.rolling(window=126, min_periods=20).max()
    frame["Drawdown From 6M High"] = price / trailing_high_6m - 1
    # Depressed-price and stabilization state. Drawdown is not a valuation signal.
    trailing_high_1y = price.rolling(window=252, min_periods=60).max()
    frame["Drawdown From 1Y High"] = price / trailing_high_1y - 1
    trailing_low_3m = price.rolling(window=63, min_periods=20).min()
    frame["Rebound From 3M Low"] = price / trailing_low_3m - 1
    frame["Annualized Volatility 3M"] = daily_returns.rolling(window=63, min_periods=20).std(ddof=1) * np.sqrt(
        TRADING_DAYS
    )
    frame["RSI 14"] = calculate_rsi(price, 14)
    frame["EMA 50"] = calculate_ema(price, 50)
    frame["EMA 200"] = calculate_ema(price, 200)
    frame["EMA 50/200 Gap"] = frame["EMA 50"] / frame["EMA 200"] - 1
    frame["EMA 200 Slope 1M"] = frame["EMA 200"].pct_change(21)
    annualized_3m = frame["Trailing Return 3M"].map(lambda value: annualize_return(value, 4.0))
    annualized_6m = frame["Trailing Return 6M"].map(lambda value: annualize_return(value, 2.0))
    volatility_floor = frame["Annualized Volatility 3M"].clip(lower=0.05)
    frame["Risk-Adjusted Momentum"] = (0.4 * annualized_3m + 0.6 * annualized_6m) / volatility_floor
    frame["Self-Relative Momentum Percentile"] = expanding_prior_percentile(frame["Risk-Adjusted Momentum"])
    frame["Self-Relative Momentum Percentile 1M Ago"] = frame["Self-Relative Momentum Percentile"].shift(21)
    frame["Self-Relative Momentum Percentile Change 1M"] = (
        frame["Self-Relative Momentum Percentile"] - frame["Self-Relative Momentum Percentile 1M Ago"]
    )
    frame["Trend State"] = frame.apply(trend_state, axis=1)
    return frame


def intervals_overlap(start_a, end_a, start_b, end_b):
    """Return whether half-open intervals [start, end) intersect."""
    start_a, end_a = pd.Timestamp(start_a), pd.Timestamp(end_a)
    start_b, end_b = pd.Timestamp(start_b), pd.Timestamp(end_b)
    return start_a < end_b and start_b < end_a


def select_non_overlapping_rows(frame, horizon_days=None, max_rows=None, sort_columns=None):
    """Greedily select rows using their actual forward start/end intervals."""
    if frame.empty:
        return frame.head(0).copy()
    if "Start Date" not in frame.columns:
        raise ValueError("Non-overlap selection requires a Start Date column.")
    frame = frame.copy()
    if "End Date" not in frame.columns:
        if horizon_days is None:
            raise ValueError("horizon_days is required when End Date is unavailable.")
        calendar_days = max(1, int(round(float(horizon_days) * 365.25 / TRADING_DAYS)))
        frame["End Date"] = pd.to_datetime(frame["Start Date"], errors="coerce") + pd.Timedelta(days=calendar_days)
    ranked = frame.sort_values(sort_columns or ["Start Date"]).copy()
    selected_indices = []
    selected_intervals = []
    for index, row in ranked.iterrows():
        start_date = pd.Timestamp(row["Start Date"])
        end_date = pd.Timestamp(row["End Date"])
        if pd.isna(start_date) or pd.isna(end_date) or end_date <= start_date:
            continue
        if all(not intervals_overlap(start_date, end_date, start, end) for start, end in selected_intervals):
            selected_indices.append(index)
            selected_intervals.append((start_date, end_date))
            if max_rows and len(selected_indices) >= max_rows:
                break
    return ranked.loc[selected_indices].reset_index(drop=True)


def confidence_level(analog_count, baseline_count, min_analogs):
    if analog_count < min_analogs or baseline_count < min_analogs:
        return "LOW"
    if min(analog_count, baseline_count) < max(12, min_analogs * 2):
        return "MEDIUM"
    return "NORMAL"


def legacy_effective_observations(frame):
    if frame.empty:
        return 0
    return len(select_non_overlapping_rows(frame, sort_columns=["Start Date"]))


def legacy_confidence_level(analog_count, effective_observations):
    if analog_count < 40:
        return "LOW"
    if effective_observations < 13:
        return "MEDIUM"
    return "NORMAL"


def shrunk_binomial_estimate(successes, observations, base_probability, prior_strength):
    """Return a base-rate-shrunk probability and a 95% beta interval."""
    base_probability = float(np.clip(base_probability, 0.0, 1.0))
    prior_strength = max(0.0, float(prior_strength))
    alpha = 0.5 + successes + prior_strength * base_probability
    beta = 0.5 + (observations - successes) + prior_strength * (1.0 - base_probability)
    probability = alpha / (alpha + beta)
    return probability, beta_distribution.ppf(0.025, alpha, beta), beta_distribution.ppf(0.975, alpha, beta)


def scaled_return_threshold(threshold, horizon_days, primary_horizon_days, mode="compounded"):
    """Convert a primary-horizon threshold to an equivalent compounded horizon return."""
    if mode == "fixed" or horizon_days == primary_horizon_days:
        return float(threshold)
    if threshold <= -1:
        raise ValueError("Return thresholds must be greater than -1.0.")
    return (1.0 + float(threshold)) ** (float(horizon_days) / float(primary_horizon_days)) - 1.0


def nearest_analogs(feature_frame, forward_frame, latest_row, horizon_label, horizon_days, args):
    merged = feature_frame.merge(
        forward_frame[["Start Date", "End Date", "Forward Return"]],
        left_on="Date",
        right_on="Start Date",
        how="inner",
    )
    method = getattr(args, "forward_method", DEFAULT_FORWARD_METHOD)
    continuous_features = LEGACY_CONTINUOUS_FEATURES if method == "legacy" else DEFAULT_CONTINUOUS_FEATURES
    required = continuous_features + ["Forward Return"]
    candidates = merged.dropna(subset=required).copy()
    latest_features = latest_row[continuous_features]
    if candidates.empty or latest_features.isna().any():
        return pd.DataFrame()

    distances = np.zeros(len(candidates), dtype=float)
    for feature in continuous_features:
        values = candidates[feature].astype(float)
        std = values.std(ddof=0)
        if pd.isna(std) or std == 0:
            std = 1.0
        latest_z = (float(latest_features[feature]) - values.mean()) / std
        candidate_z = (values - values.mean()) / std
        distances += FEATURE_WEIGHTS[feature] * (candidate_z - latest_z) ** 2

    mismatch_penalty = LEGACY_TREND_STATE_MISMATCH_PENALTY if method == "legacy" else TREND_STATE_MISMATCH_PENALTY
    trend_penalty = np.where(
        candidates["Trend State"].eq(latest_row["Trend State"]),
        0.0,
        mismatch_penalty,
    )
    candidates["Analog Distance"] = np.sqrt(distances) + trend_penalty
    candidates["Horizon"] = horizon_label
    candidates["Horizon Days"] = horizon_days
    candidate_count = len(candidates)
    if method == "legacy":
        selected = candidates.sort_values(["Analog Distance", "Start Date"]).head(
            getattr(args, "legacy_max_analogs", 150)
        ).reset_index(drop=True)
        selected.attrs["candidate_count"] = candidate_count
        return selected
    selected = select_non_overlapping_rows(
        candidates,
        max_rows=args.max_analogs,
        sort_columns=["Analog Distance", "Start Date"],
    )
    selected.attrs["candidate_count"] = candidate_count
    return selected


def metric_or_nan(series, fn):
    if series.empty:
        return np.nan
    return fn(series)


def summarize_analogs(fund_label, latest_row, horizon_label, horizon_days, analogs, forward_frame, args):
    returns = analogs["Forward Return"].dropna()
    analog_count = len(returns)
    method = getattr(args, "forward_method", DEFAULT_FORWARD_METHOD)
    primary_horizon_days = getattr(args, "primary_horizon_days", horizon_days)
    if method == "legacy":
        upside_target = float(args.upside_target)
        downside_risk = float(args.downside_risk)
    else:
        upside_target = scaled_return_threshold(
            args.upside_target, horizon_days, primary_horizon_days, getattr(args, "target_scaling", "compounded")
        )
        downside_risk = scaled_return_threshold(
            args.downside_risk, horizon_days, primary_horizon_days, getattr(args, "target_scaling", "compounded")
        )

    baseline_frame = select_non_overlapping_rows(forward_frame, sort_columns=["Start Date"])
    baseline_returns = baseline_frame["Forward Return"].dropna()
    base_upside_probability = (baseline_returns >= upside_target).mean() if len(baseline_returns) else np.nan
    base_downside_probability = (baseline_returns <= downside_risk).mean() if len(baseline_returns) else np.nan
    base_positive_probability = (baseline_returns > 0).mean() if len(baseline_returns) else np.nan
    base_expected_return = baseline_returns.mean() if len(baseline_returns) else np.nan

    raw_upside_probability = (returns >= upside_target).mean() if analog_count else np.nan
    raw_downside_probability = (returns <= downside_risk).mean() if analog_count else np.nan
    raw_positive_probability = (returns > 0).mean() if analog_count else np.nan
    raw_expected_return = returns.mean() if analog_count else np.nan

    eligible_returns = forward_frame["Forward Return"].dropna()
    relative_upside_threshold = eligible_returns.quantile(RELATIVE_UPSIDE_QUANTILE) if len(eligible_returns) else np.nan
    relative_downside_threshold = eligible_returns.quantile(RELATIVE_DOWNSIDE_QUANTILE) if len(eligible_returns) else np.nan
    raw_base_relative_upside = (
        (baseline_returns >= relative_upside_threshold).mean()
        if len(baseline_returns) and pd.notna(relative_upside_threshold)
        else np.nan
    )
    raw_base_relative_downside = (
        (baseline_returns <= relative_downside_threshold).mean()
        if len(baseline_returns) and pd.notna(relative_downside_threshold)
        else np.nan
    )
    raw_analog_relative_upside = (
        (returns >= relative_upside_threshold).mean()
        if analog_count and pd.notna(relative_upside_threshold)
        else np.nan
    )
    raw_analog_relative_downside = (
        (returns <= relative_downside_threshold).mean()
        if analog_count and pd.notna(relative_downside_threshold)
        else np.nan
    )

    if method == "legacy":
        upside_probability = raw_upside_probability
        downside_probability = raw_downside_probability
        positive_probability = raw_positive_probability
        expected_return = raw_expected_return
        effective_n = legacy_effective_observations(analogs)
        upside_ci_low, upside_ci_high = wilson_interval(upside_probability, effective_n)
        downside_ci_low, downside_ci_high = wilson_interval(downside_probability, effective_n)
        base_relative_upside = base_relative_downside = np.nan
        relative_upside_probability = relative_downside_probability = np.nan
        relative_upside_lift = relative_downside_lift = np.nan
        confidence = legacy_confidence_level(analog_count, effective_n)
    elif analog_count and len(baseline_returns):
        upside_probability, upside_ci_low, upside_ci_high = shrunk_binomial_estimate(
            int((returns >= upside_target).sum()), analog_count, base_upside_probability, args.prior_strength
        )
        downside_probability, downside_ci_low, downside_ci_high = shrunk_binomial_estimate(
            int((returns <= downside_risk).sum()), analog_count, base_downside_probability, args.prior_strength
        )
        positive_probability, _, _ = shrunk_binomial_estimate(
            int((returns > 0).sum()), analog_count, base_positive_probability, args.prior_strength
        )
        expected_return = (
            returns.sum() + args.prior_strength * base_expected_return
        ) / (analog_count + args.prior_strength)
        base_relative_upside, _, _ = shrunk_binomial_estimate(
            int((baseline_returns >= relative_upside_threshold).sum()),
            len(baseline_returns),
            1.0 - RELATIVE_UPSIDE_QUANTILE,
            args.prior_strength,
        )
        base_relative_downside, _, _ = shrunk_binomial_estimate(
            int((baseline_returns <= relative_downside_threshold).sum()),
            len(baseline_returns),
            RELATIVE_DOWNSIDE_QUANTILE,
            args.prior_strength,
        )
        relative_upside_probability, _, _ = shrunk_binomial_estimate(
            int((returns >= relative_upside_threshold).sum()),
            analog_count,
            base_relative_upside,
            args.prior_strength,
        )
        relative_downside_probability, _, _ = shrunk_binomial_estimate(
            int((returns <= relative_downside_threshold).sum()),
            analog_count,
            base_relative_downside,
            args.prior_strength,
        )
        relative_upside_lift = relative_upside_probability - base_relative_upside
        relative_downside_lift = relative_downside_probability - base_relative_downside
        effective_n = analog_count
        confidence = confidence_level(analog_count, len(baseline_returns), args.min_analogs)
    else:
        upside_probability = downside_probability = positive_probability = np.nan
        upside_ci_low = upside_ci_high = downside_ci_low = downside_ci_high = np.nan
        expected_return = np.nan
        base_relative_upside = base_relative_downside = np.nan
        relative_upside_probability = relative_downside_probability = np.nan
        relative_upside_lift = relative_downside_lift = np.nan
        effective_n = analog_count
        confidence = "LOW"

    raw_shortfall_10 = expected_shortfall(returns, 0.10) if analog_count else np.nan
    base_shortfall_10 = expected_shortfall(baseline_returns, 0.10) if len(baseline_returns) else np.nan
    if pd.notna(raw_shortfall_10) and pd.notna(base_shortfall_10):
        shortfall_10 = (
            analog_count * raw_shortfall_10 + args.prior_strength * base_shortfall_10
        ) / (analog_count + args.prior_strength)
    else:
        shortfall_10 = np.nan
    expected_edge = (
        expected_return - base_expected_return
        if pd.notna(expected_return) and pd.notna(base_expected_return)
        else np.nan
    )
    baseline_std = baseline_returns.std(ddof=1) if len(baseline_returns) >= 2 else np.nan
    current_volatility = latest_row.get("Annualized Volatility 3M", np.nan)
    daily_vol_scaled_sigma = (
        float(current_volatility) * np.sqrt(float(horizon_days) / TRADING_DAYS)
        if pd.notna(current_volatility) and float(current_volatility) > 0
        else np.nan
    )
    sigma_candidates = [
        float(value)
        for value in [baseline_std, daily_vol_scaled_sigma]
        if pd.notna(value) and np.isfinite(value) and float(value) > 0
    ]
    score_sigma = max([MIN_SCORE_SIGMA, *sigma_candidates]) if sigma_candidates else np.nan
    score = (
        legacy_decision_score(expected_return, upside_probability, downside_probability, shortfall_10)
        if method == "legacy"
        else decision_score(expected_edge, score_sigma)
    )

    return {
        "Forward Method Version": method,
        "Fund Label": fund_label,
        "Latest Date": latest_row["Date"].date(),
        "Latest TotalReturn": latest_row["TotalReturn"],
        "Horizon": horizon_label,
        "Horizon Days": horizon_days,
        "Upside Target": upside_target,
        "Downside Risk": downside_risk,
        "Probability >= Upside Target": upside_probability,
        "Raw Analog Probability >= Upside Target": raw_upside_probability,
        "Base Probability >= Upside Target": base_upside_probability,
        "Upside Probability CI Low": upside_ci_low,
        "Upside Probability CI High": upside_ci_high,
        "Probability <= Downside Risk": downside_probability,
        "Raw Analog Probability <= Downside Risk": raw_downside_probability,
        "Base Probability <= Downside Risk": base_downside_probability,
        "Downside Probability CI Low": downside_ci_low,
        "Downside Probability CI High": downside_ci_high,
        "Probability > 0": positive_probability,
        "Raw Analog Probability > 0": raw_positive_probability,
        "Base Probability > 0": base_positive_probability,
        "Expected Forward Return": expected_return,
        "Raw Analog Expected Forward Return": raw_expected_return,
        "Base Expected Forward Return": base_expected_return,
        "Conditional Expected Edge": expected_edge,
        "Relative Upside Threshold (P75)": relative_upside_threshold,
        "Relative Downside Threshold (P25)": relative_downside_threshold,
        "Raw Base Relative Upside Probability": raw_base_relative_upside,
        "Base Relative Upside Probability": base_relative_upside,
        "Raw Analog Relative Upside Probability": raw_analog_relative_upside,
        "Relative Upside Probability": relative_upside_probability,
        "Relative Upside Probability Lift": relative_upside_lift,
        "Raw Base Relative Downside Probability": raw_base_relative_downside,
        "Base Relative Downside Probability": base_relative_downside,
        "Raw Analog Relative Downside Probability": raw_analog_relative_downside,
        "Relative Downside Probability": relative_downside_probability,
        "Relative Downside Probability Lift": relative_downside_lift,
        "Median Forward Return": metric_or_nan(returns, lambda x: x.median()),
        "Forward Return P10": metric_or_nan(returns, lambda x: x.quantile(0.10)),
        "Forward Return P25": metric_or_nan(returns, lambda x: x.quantile(0.25)),
        "Forward Return P75": metric_or_nan(returns, lambda x: x.quantile(0.75)),
        "Forward Return P90": metric_or_nan(returns, lambda x: x.quantile(0.90)),
        "Expected Shortfall 10%": shortfall_10,
        "Raw Analog Expected Shortfall 10%": raw_shortfall_10,
        "Base Expected Shortfall 10%": base_shortfall_10,
        "Analog Count": analog_count,
        "Candidate Analog Count": analogs.attrs.get("candidate_count", analog_count),
        "Effective Observations": effective_n,
        "Base Observations": len(baseline_returns),
        "Prior Strength": args.prior_strength,
        "Confidence Level": confidence,
        "Average Analog Distance": analogs["Analog Distance"].mean() if analog_count else np.nan,
        "Nearest Analog Start Date": analogs["Start Date"].iloc[0].date() if analog_count else "",
        "Nearest Analog End Date": analogs["End Date"].iloc[0].date() if analog_count else "",
        "Current Trend State": latest_row["Trend State"],
        "Current Trailing Return 1M": latest_row["Trailing Return 1M"],
        "Current Trailing Return 3M": latest_row["Trailing Return 3M"],
        "Current Trailing Return 6M": latest_row["Trailing Return 6M"],
        "Current Drawdown From 6M High": latest_row["Drawdown From 6M High"],
        "Current Drawdown From 1Y High": latest_row["Drawdown From 1Y High"],
        "Current Rebound From 3M Low": latest_row["Rebound From 3M Low"],
        "Current Annualized Volatility 3M": latest_row["Annualized Volatility 3M"],
        "Current RSI 14": latest_row["RSI 14"],
        "Current EMA 50/200 Gap": latest_row["EMA 50/200 Gap"],
        "Current EMA 200 Slope 1M": latest_row["EMA 200 Slope 1M"],
        "Current Risk-Adjusted Momentum": latest_row.get("Risk-Adjusted Momentum", np.nan),
        "Self-Relative Momentum Percentile": latest_row.get("Self-Relative Momentum Percentile", np.nan),
        "Self-Relative Momentum Percentile 1M Ago": latest_row.get(
            "Self-Relative Momentum Percentile 1M Ago", np.nan
        ),
        "Self-Relative Momentum Percentile Change 1M": latest_row.get(
            "Self-Relative Momentum Percentile Change 1M", np.nan
        ),
        "Baseline Forward Return Std": baseline_std,
        "Daily-Vol Scaled Sigma": daily_vol_scaled_sigma,
        "Decision Score Sigma": score_sigma,
        "Decision Score": score,
    }


def decision_score(expected_edge, score_sigma):
    if pd.isna(expected_edge) or pd.isna(score_sigma) or float(score_sigma) <= 0:
        return np.nan
    return float(np.clip(float(expected_edge) / float(score_sigma), -3.0, 3.0))


def legacy_decision_score(expected_return, upside_probability, downside_probability, shortfall_10):
    if any(pd.isna(value) for value in [expected_return, upside_probability, downside_probability]):
        return np.nan
    downside_penalty = abs(min(float(shortfall_10), 0.0)) if pd.notna(shortfall_10) else 0.0
    return float(expected_return) + float(upside_probability) - float(downside_probability) - downside_penalty


def decide(primary_row):
    if primary_row is None or primary_row.empty:
        return "HOLD / WATCH", "HOLD / WATCH: no primary-horizon analog report was available."

    method = primary_row.get("Forward Method Version", DEFAULT_FORWARD_METHOD)
    if method == "legacy":
        return decide_legacy(primary_row)

    upside = primary_row["Probability >= Upside Target"]
    downside = primary_row["Probability <= Downside Risk"]
    expected = primary_row["Expected Forward Return"]
    expected_edge = primary_row.get("Conditional Expected Edge", np.nan)
    relative_upside_lift = primary_row.get("Relative Upside Probability Lift", np.nan)
    relative_downside_lift = primary_row.get("Relative Downside Probability Lift", np.nan)
    score = primary_row.get("Decision Score", np.nan)
    confidence = primary_row["Confidence Level"]
    horizon = primary_row["Horizon"]
    analog_count = int(primary_row["Analog Count"])
    base_count = int(primary_row.get("Base Observations", 0))
    candidate_count = int(primary_row.get("Candidate Analog Count", analog_count))
    target = primary_row["Upside Target"]
    risk = primary_row["Downside Risk"]
    trailing_6m = primary_row.get("Current Trailing Return 6M", np.nan)
    trailing_1m = primary_row.get("Current Trailing Return 1M", np.nan)
    trailing_3m = primary_row.get("Current Trailing Return 3M", np.nan)
    rebound_3m = primary_row.get("Current Rebound From 3M Low", np.nan)
    trend_state_label = primary_row.get("Current Trend State", "")
    ema_gap = primary_row.get("Current EMA 50/200 Gap", np.nan)
    ema_slope = primary_row.get("Current EMA 200 Slope 1M", np.nan)
    momentum_percentile = primary_row.get("Self-Relative Momentum Percentile", np.nan)
    momentum_percentile_1m_ago = primary_row.get("Self-Relative Momentum Percentile 1M Ago", np.nan)
    cross_fund_percentile = primary_row.get("Cross-Fund Momentum Percentile", np.nan)

    trend_setup = (
        all(pd.notna(value) and value > 0 for value in [trailing_6m, ema_gap, ema_slope])
        and pd.notna(momentum_percentile)
        and momentum_percentile >= TREND_MOMENTUM_PERCENTILE
    )
    recovery_setup = (
        trend_state_label == "recovering / mixed"
        and all(pd.notna(value) and value > 0 for value in [trailing_1m, trailing_3m, ema_slope])
        and pd.notna(rebound_3m)
        and rebound_3m >= 0.05
        and pd.notna(momentum_percentile)
        and momentum_percentile >= RECOVERY_MOMENTUM_PERCENTILE
        and pd.notna(momentum_percentile_1m_ago)
        and momentum_percentile > momentum_percentile_1m_ago
    )
    broken_trend_count = sum(pd.notna(value) and value < 0 for value in [trailing_6m, ema_gap, ema_slope])
    sell_setup = (
        broken_trend_count >= 2
        and pd.notna(momentum_percentile)
        and momentum_percentile <= SELL_MOMENTUM_PERCENTILE
    )

    if any(
        pd.isna(value)
        for value in [upside, downside, expected, expected_edge, relative_upside_lift, relative_downside_lift, score]
    ):
        action = "HOLD / WATCH"
    elif (
        confidence != "LOW"
        and (trend_setup or recovery_setup)
        and expected > 0
        and expected_edge > 0
        and relative_upside_lift >= 0.05
        and relative_downside_lift <= 0
    ):
        action = "BUY"
    elif (
        confidence != "LOW"
        and sell_setup
        and expected_edge < 0
        and relative_downside_lift >= 0.05
        and relative_upside_lift <= 0
    ):
        action = "SELL / AVOID"
    else:
        action = "HOLD / WATCH"

    momentum_text = "n/a" if pd.isna(momentum_percentile) else f"{momentum_percentile:.0%}"
    cross_fund_text = "n/a" if pd.isna(cross_fund_percentile) else f"{cross_fund_percentile:.0%}"
    setup_text = "trend" if trend_setup else "recovery" if recovery_setup else "none"
    reason = (
        f"{action}: V2 {horizon} absolute probabilities are {upside:.1%} for {target:+.1%} or better and "
        f"{downside:.1%} for {risk:+.1%} or worse; expected return {expected:+.1%}, conditional edge "
        f"{expected_edge:+.1%}. Shrunk relative lifts: upside {relative_upside_lift:+.1%}, downside "
        f"{relative_downside_lift:+.1%}. Setup={setup_text}, self-relative momentum={momentum_text}; "
        f"cross-fund context={cross_fund_text}. Evidence: {analog_count} independent analogs from "
        f"{candidate_count} candidates and {base_count} baseline periods ({confidence.lower()} confidence)."
    )
    return action, reason


def decide_legacy(primary_row):
    upside = primary_row.get("Probability >= Upside Target", np.nan)
    downside = primary_row.get("Probability <= Downside Risk", np.nan)
    expected = primary_row.get("Expected Forward Return", np.nan)
    confidence = primary_row.get("Confidence Level", "LOW")
    if any(pd.isna(value) for value in [upside, downside, expected]):
        action = "HOLD / WATCH"
    elif upside >= 0.25 and downside <= 0.20 and expected > 0 and confidence != "LOW":
        action = "BUY"
    elif downside >= 0.30 or (expected < 0 and downside > upside):
        action = "SELL / AVOID"
    else:
        action = "HOLD / WATCH"
    reason = (
        f"{action}: legacy overlapping-row method; upside={upside:.1%}, downside={downside:.1%}, "
        f"expected return={expected:+.1%}, confidence={str(confidence).lower()}. "
        "Use only for historical comparison, not the authoritative V2 rating."
    )
    return action, reason


def add_cross_fund_context(dashboard):
    """Add relative strength so a weak fund is not favored merely as a rebound candidate."""
    frame = dashboard.copy()
    required = {
        "Current Trailing Return 3M",
        "Current Trailing Return 6M",
        "Current Annualized Volatility 3M",
    }
    if len(frame) <= 1 or not required.issubset(frame.columns):
        frame["Cross-Fund Momentum Percentile"] = np.nan
        return frame
    return_3m = pd.to_numeric(frame.get("Current Trailing Return 3M"), errors="coerce")
    return_6m = pd.to_numeric(frame.get("Current Trailing Return 6M"), errors="coerce")
    volatility = pd.to_numeric(frame.get("Current Annualized Volatility 3M"), errors="coerce").replace(0, np.nan)
    risk_adjusted = (0.4 * return_3m + 0.6 * return_6m) / volatility
    frame["Cross-Fund Return 3M Percentile"] = return_3m.rank(pct=True, method="average")
    frame["Cross-Fund Return 6M Percentile"] = return_6m.rank(pct=True, method="average")
    frame["Cross-Fund Risk-Adjusted Momentum Percentile"] = risk_adjusted.rank(pct=True, method="average")
    frame["Cross-Fund Momentum Percentile"] = (
        0.30 * frame["Cross-Fund Return 3M Percentile"]
        + 0.50 * frame["Cross-Fund Return 6M Percentile"]
        + 0.20 * frame["Cross-Fund Risk-Adjusted Momentum Percentile"]
    )
    return frame


def refresh_dashboard_decisions(dashboard):
    frame = add_cross_fund_context(dashboard)
    decisions = frame.apply(decide, axis=1)
    frame["Decision Label"] = [item[0] for item in decisions]
    frame["Decision Reason"] = [item[1] for item in decisions]
    frame["Action Rank"] = frame["Decision Label"].map(ACTION_ORDER).fillna(99)
    return frame


def analyze_one_file(csv_path, args, horizons):
    fund_label = fund_label_from_data_file(csv_path)
    raw = load_total_return_data(csv_path, date_col=args.date_column, total_return_col=args.price_column)
    features = add_state_features(raw)
    latest_valid = features.dropna(subset=DEFAULT_CONTINUOUS_FEATURES)
    if latest_valid.empty:
        raise ValueError(f"{csv_path} has no row with complete current-state features.")
    latest_row = latest_valid.iloc[-1]

    detail_rows = []
    analog_rows = []
    for label, days in horizons.items():
        forward_frame = calculate_calendar_forward_return_frame(raw, label, days)
        analogs = nearest_analogs(features, forward_frame, latest_row, label, days, args)
        detail_rows.append(summarize_analogs(fund_label, latest_row, label, days, analogs, forward_frame, args))
        if not analogs.empty:
            analog_copy = analogs[
                [
                    "Start Date",
                    "End Date",
                    "Forward Return",
                    "Analog Distance",
                    "Trend State",
                    *DEFAULT_CONTINUOUS_FEATURES,
                ]
            ].copy()
            analog_copy.insert(0, "Fund Label", fund_label)
            analog_copy.insert(1, "Horizon", label)
            analog_rows.append(analog_copy)

    details = pd.DataFrame(detail_rows)
    primary = details[details["Horizon"].eq(args.primary_horizon)]
    dashboard = primary.copy() if not primary.empty else details.head(1).copy()
    if dashboard.empty:
        dashboard = pd.DataFrame([{"Fund Label": fund_label}])
    # Programmatic and single-fund callers receive the same centralized
    # decision.  Multi-fund callers recompute after cross-fund context is
    # assembled; that context remains descriptive and cannot change the label.
    dashboard = refresh_dashboard_decisions(dashboard)

    analog_detail = pd.concat(analog_rows, ignore_index=True) if analog_rows else pd.DataFrame()
    return dashboard, details, analog_detail


def pct(value, digits=1):
    if pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}%}"


def num(value, digits=3):
    if pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def format_report_values(df):
    formatted = df.copy()
    percent_columns = [
        col
        for col in formatted.columns
        if col != "Latest TotalReturn"
        and any(
            token in col
            for token in ["Probability", "Return", "Risk", "Target", "Drawdown", "Volatility", "Gap", "Slope", "Percentile"]
        )
    ]
    for col in percent_columns:
        if col in formatted.columns and pd.api.types.is_numeric_dtype(formatted[col]):
            formatted[col] = formatted[col].map(lambda value: "" if pd.isna(value) else f"{value:.1%}")
    if "Latest TotalReturn" in formatted.columns:
        formatted["Latest TotalReturn"] = formatted["Latest TotalReturn"].map(
            lambda value: "" if pd.isna(value) else f"{value:.4f}"
        )
    if "Current RSI 14" in formatted.columns:
        formatted["Current RSI 14"] = formatted["Current RSI 14"].map(lambda value: "" if pd.isna(value) else f"{value:.1f}")
    for col in ["Decision Score", "Average Analog Distance"]:
        if col in formatted.columns:
            formatted[col] = formatted[col].map(lambda value: "" if pd.isna(value) else f"{value:.3f}")
    return formatted


def dataframe_to_html(df, columns, max_rows=100):
    if df.empty:
        return "<p>No data available.</p>"
    show_df = df[[col for col in columns if col in df.columns]].head(max_rows).copy()
    show_df = format_report_values(show_df)
    return show_df.to_html(index=False, escape=True, border=0, classes="data-table")


def build_html_report(dashboard, details, chart_paths, output_dir, args):
    action_counts = dashboard["Decision Label"].value_counts().to_dict() if "Decision Label" in dashboard.columns else {}
    summary_bits = " | ".join(f"{html.escape(action)}: {count}" for action, count in action_counts.items())
    dashboard_columns = [
        "Forward Method Version",
        "Fund Label",
        "Decision Label",
        "Decision Reason",
        "Latest Date",
        "Latest TotalReturn",
        "Cross-Fund Momentum Percentile",
        "Upside Target",
        "Probability >= Upside Target",
        "Base Probability >= Upside Target",
        "Downside Risk",
        "Probability <= Downside Risk",
        "Base Probability <= Downside Risk",
        "Probability > 0",
        "Expected Forward Return",
        "Base Expected Forward Return",
        "Conditional Expected Edge",
        "Relative Upside Threshold (P75)",
        "Relative Upside Probability",
        "Base Relative Upside Probability",
        "Relative Upside Probability Lift",
        "Relative Downside Threshold (P25)",
        "Relative Downside Probability",
        "Base Relative Downside Probability",
        "Relative Downside Probability Lift",
        "Median Forward Return",
        "Forward Return P10",
        "Forward Return P90",
        "Confidence Level",
        "Analog Count",
        "Effective Observations",
        "Current Trend State",
        "Current Drawdown From 6M High",
        "Current Drawdown From 1Y High",
        "Current Rebound From 3M Low",
        "Self-Relative Momentum Percentile",
        "Self-Relative Momentum Percentile Change 1M",
        "Current RSI 14",
        "Current Annualized Volatility 3M",
        "Decision Score",
    ]
    detail_columns = [
        "Forward Method Version",
        "Fund Label",
        "Horizon",
        "Upside Target",
        "Probability >= Upside Target",
        "Base Probability >= Upside Target",
        "Downside Risk",
        "Probability <= Downside Risk",
        "Base Probability <= Downside Risk",
        "Probability > 0",
        "Expected Forward Return",
        "Base Expected Forward Return",
        "Conditional Expected Edge",
        "Relative Upside Threshold (P75)",
        "Relative Upside Probability",
        "Base Relative Upside Probability",
        "Relative Upside Probability Lift",
        "Relative Downside Threshold (P25)",
        "Relative Downside Probability",
        "Base Relative Downside Probability",
        "Relative Downside Probability Lift",
        "Median Forward Return",
        "Forward Return P10",
        "Forward Return P90",
        "Confidence Level",
        "Analog Count",
        "Effective Observations",
        "Decision Score",
    ]
    chart_html = "\n".join(
        f'<figure><img src="{html.escape(os.path.relpath(path, output_dir).replace(os.sep, "/"))}" alt="{html.escape(Path(path).stem)}"><figcaption>{html.escape(Path(path).stem.replace("_", " ").title())}</figcaption></figure>'
        for path in chart_paths
    )
    if not chart_html:
        chart_html = "<p>No charts generated. Run with <code>--charts</code> to create chart images.</p>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Conditional Forward Probability Decision Dashboard</title>
  <style>
    :root {{
      --ink: #111827;
      --muted: #5b6677;
      --line: #d9e0ea;
      --panel: #f7f9fc;
      --buy: #047857;
      --hold: #92400e;
      --sell: #b91c1c;
    }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Segoe UI", Arial, sans-serif;
      background: #ffffff;
    }}
    header {{
      padding: 28px 36px 18px;
      border-bottom: 1px solid var(--line);
    }}
    main {{
      max-width: 1880px;
      margin: 0 auto;
      padding: 24px 36px 44px;
    }}
    h1, h2 {{
      margin: 0;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 29px;
      line-height: 1.2;
    }}
    h2 {{
      font-size: 20px;
      margin: 30px 0 12px;
    }}
    p {{
      color: var(--muted);
      line-height: 1.55;
    }}
    .meta {{
      color: var(--muted);
      margin-top: 10px;
      font-size: 13px;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      background: #ffffff;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }}
    td:nth-child(4) {{
      white-space: normal;
      min-width: 420px;
    }}
    th {{
      background: var(--panel);
      font-weight: 700;
    }}
    .charts {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 28px;
    }}
    figure {{
      margin: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
    }}
    img {{
      width: 100%;
      height: auto;
      display: block;
    }}
    figcaption {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 8px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Conditional Forward Probability Decision Dashboard</h1>
    <div class="meta">Method: {html.escape(args.forward_method)} | Primary horizon: {html.escape(args.primary_horizon)} | Absolute upside report: {args.upside_target:+.0%} | Absolute downside report: {args.downside_risk:.0%} | Target scaling: {html.escape(args.target_scaling)} | {summary_bits}</div>
  </header>
  <main>
    <p>V2 decisions use exact non-overlapping historical intervals, shrunk P75/P25 probability lifts, conditional expected edge, and each fund's self-relative momentum. The +15%/-8% probabilities remain descriptive absolute outcomes and cross-fund momentum is context only. With five years of history, 1Y decisions are evidence-limited by construction and 6M signals should be rare. For more activity, use a 3M primary horizon or obtain longer NAV history; do not weaken interval independence. This is general research support, not personalized financial advice or a guarantee.</p>
    <section>
      <h2>Decision Dashboard</h2>
      <div class="table-wrap">{dataframe_to_html(dashboard, dashboard_columns)}</div>
    </section>
    <section>
      <h2>Horizon Detail</h2>
      <div class="table-wrap">{dataframe_to_html(details, detail_columns, max_rows=500)}</div>
    </section>
    <section>
      <h2>Charts</h2>
      <div class="charts">{chart_html}</div>
    </section>
  </main>
</body>
</html>
"""


def short_decision_label(decision_label):
    if decision_label == "BUY":
        return "BUY"
    if decision_label == "SELL / AVOID":
        return "SELL"
    return "HOLD"


def add_horizon_decisions(details):
    contextualized = pd.concat(
        [add_cross_fund_context(group) for _, group in details.groupby("Horizon", sort=False)],
        ignore_index=True,
    )
    rows = []
    for _, row in contextualized.iterrows():
        decision_label, _ = decide(row)
        out = row.copy()
        out["Horizon Decision Label"] = decision_label
        rows.append(out)
    return pd.DataFrame(rows)


def create_all_horizon_chart(details, chart_dir, horizon_order):
    if details.empty:
        return None

    plot_df = add_horizon_decisions(details)
    plot_df["Horizon"] = pd.Categorical(plot_df["Horizon"], categories=horizon_order, ordered=True)
    score_matrix = plot_df.pivot_table(
        index="Fund Label",
        columns="Horizon",
        values="Decision Score",
        aggfunc="first",
        observed=False,
    )
    label_matrix = plot_df.pivot_table(
        index="Fund Label",
        columns="Horizon",
        values="Horizon Decision Label",
        aggfunc="first",
        observed=False,
    )
    score_matrix = score_matrix[[horizon for horizon in horizon_order if horizon in score_matrix.columns]]
    label_matrix = label_matrix[score_matrix.columns]

    fund_order = score_matrix.mean(axis=1).sort_values(ascending=False).index
    score_matrix = score_matrix.loc[fund_order]
    label_matrix = label_matrix.loc[fund_order]

    finite_scores = score_matrix.to_numpy(dtype=float)
    max_abs_score = np.nanmax(np.abs(finite_scores)) if np.isfinite(finite_scores).any() else 1.0
    max_abs_score = max(max_abs_score, 0.1)
    norm = TwoSlopeNorm(vmin=-max_abs_score, vcenter=0.0, vmax=max_abs_score)

    fig_width = max(20.0, len(score_matrix.columns) * 3.25 + 7.0)
    fig_height = max(9.0, len(score_matrix) * 0.70 + 3.0)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    image = ax.imshow(score_matrix, cmap="RdYlGn", norm=norm, aspect="auto")

    ax.set_title("Forward Decision Score Across Horizons", pad=24, fontsize=18)
    ax.set_xlabel("Forward decision horizon", fontsize=13)
    ax.set_ylabel("Fund", fontsize=13)
    ax.set_xticks(np.arange(len(score_matrix.columns)))
    ax.set_xticklabels([f"{horizon} Horizon" for horizon in score_matrix.columns], fontsize=12)
    ax.set_yticks(np.arange(len(score_matrix.index)))
    ax.set_yticklabels(score_matrix.index, fontsize=11)
    ax.tick_params(axis="x", top=True, bottom=False, labeltop=True, labelbottom=False)

    for row_idx, fund_label in enumerate(score_matrix.index):
        for col_idx, horizon in enumerate(score_matrix.columns):
            score = score_matrix.loc[fund_label, horizon]
            if pd.isna(score):
                text = "n/a"
                color = "#111827"
            else:
                action = short_decision_label(label_matrix.loc[fund_label, horizon])
                text = f"{action}\n{score:+.2f}"
                color = "#ffffff" if abs(score) > max_abs_score * 0.45 else "#111827"
            ax.text(col_idx, row_idx, text, ha="center", va="center", fontsize=11, color=color)

    ax.set_xticks(np.arange(-0.5, len(score_matrix.columns), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(score_matrix.index), 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.5)
    ax.tick_params(which="minor", bottom=False, left=False)

    cbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Decision Score (green = stronger buy setup)", fontsize=12)
    cbar.ax.tick_params(labelsize=10)
    fig.tight_layout()

    path = chart_dir / "forward_decision_score_all_horizons.png"
    fig.savefig(path, dpi=CHART_DPI)
    plt.close(fig)
    return path


def create_charts(
    dashboard,
    details,
    chart_dir,
    primary_horizon,
    horizon_order,
    include_primary_charts=True,
    include_all_horizon_chart=False,
):
    chart_dir.mkdir(parents=True, exist_ok=True)
    chart_paths = []
    if include_all_horizon_chart:
        all_horizon_path = create_all_horizon_chart(details, chart_dir, horizon_order)
        if all_horizon_path:
            chart_paths.append(all_horizon_path)
    if not include_primary_charts:
        return chart_paths
    if dashboard.empty:
        return chart_paths

    plot_df = dashboard.copy()
    plot_df = plot_df.sort_values("Decision Score", ascending=True)
    fig, ax = plt.subplots(figsize=(17.5, max(8.0, len(plot_df) * 0.70)))
    color_map = {"BUY": "#047857", "HOLD / WATCH": "#b45309", "SELL / AVOID": "#b91c1c"}
    colors = plot_df["Decision Label"].map(color_map).fillna("#64748b")
    ax.barh(plot_df["Fund Label"], plot_df["Decision Score"], color=colors)
    score_min = plot_df["Decision Score"].min()
    score_max = plot_df["Decision Score"].max()
    raw_span = max(score_max - score_min, 0.1)
    left_limit = min(score_min - raw_span * 0.18, -0.02)
    longest_label_chars = max(len(f'{row["Decision Label"]} {row["Decision Score"]:+.2f}') for _, row in plot_df.iterrows())
    label_space = raw_span * max(0.40, longest_label_chars * 0.025)
    right_limit = max(score_max + label_space, 0 + label_space, 0.04)
    ax.set_xlim(left_limit, right_limit)
    ax.axvline(0, color="#111827", linewidth=0.8)
    ax.set_title(f"Forward Decision Score by Fund ({primary_horizon} Horizon)", pad=26, fontsize=18)
    ax.set_xlabel("Decision Score (right/positive = stronger buy setup)", fontsize=13)
    ax.tick_params(axis="both", labelsize=11)
    xmin, xmax = ax.get_xlim()
    x_span = xmax - xmin
    ax.text(
        xmin + 0.01 * x_span,
        0.985,
        "Lower score / more caution",
        transform=ax.get_xaxis_transform(),
        ha="left",
        va="top",
        fontsize=11,
        color="#7f1d1d",
    )
    ax.text(
        xmax - 0.01 * x_span,
        0.985,
        "Higher score / more attractive",
        transform=ax.get_xaxis_transform(),
        ha="right",
        va="top",
        fontsize=11,
        color="#065f46",
    )
    for _, row in plot_df.iterrows():
        value = row["Decision Score"]
        label = f'{row["Decision Label"]} {value:+.2f}'
        offset = 0.008 * x_span
        if value >= 0:
            x = value + offset
            ha = "left"
        else:
            x = 0 + offset
            ha = "left"
        ax.text(x, row["Fund Label"], label, va="center", ha=ha, fontsize=10, color="#111827")
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=color_map["BUY"], label="BUY"),
        plt.Rectangle((0, 0), 1, 1, color=color_map["HOLD / WATCH"], label="HOLD / WATCH"),
        plt.Rectangle((0, 0), 1, 1, color=color_map["SELL / AVOID"], label="SELL / AVOID"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=True, fontsize=10, title="Decision label", title_fontsize=11)
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    path = chart_dir / "forward_decision_score_by_fund.png"
    fig.savefig(path, dpi=CHART_DPI)
    plt.close(fig)
    chart_paths.append(path)

    detail_plot = details[details["Horizon"].eq(primary_horizon)].copy()
    if not detail_plot.empty:
        fig, ax = plt.subplots(figsize=(16.0, max(8.0, len(detail_plot) * 0.65)))
        y = np.arange(len(detail_plot))
        detail_plot = detail_plot.sort_values("Probability >= Upside Target")
        ax.barh(y - 0.18, detail_plot["Probability >= Upside Target"], height=0.36, label="Upside >= target", color="#047857")
        ax.barh(y + 0.18, detail_plot["Probability <= Downside Risk"], height=0.36, label="Downside <= risk", color="#b91c1c")
        ax.set_yticks(y)
        ax.set_yticklabels(detail_plot["Fund Label"])
        ax.set_xlim(0, 1)
        ax.set_title(f"{primary_horizon} Upside vs Downside Analog Probability", fontsize=18, pad=22)
        ax.set_xlabel("Probability", fontsize=13)
        ax.tick_params(axis="both", labelsize=11)
        ax.legend(fontsize=11)
        ax.grid(True, axis="x", alpha=0.25)
        fig.tight_layout()
        horizon_slug = str(primary_horizon).lower().replace(" ", "_")
        path = chart_dir / f"forward_decision_{horizon_slug}_upside_downside.png"
        fig.savefig(path, dpi=CHART_DPI)
        plt.close(fig)
        chart_paths.append(path)

    return chart_paths


def validate_outputs(dashboard, details, analogs, horizons, args):
    errors = []
    if args.data_files:
        expected_funds = {fund_label_from_data_file(resolve_repo_path(path)) for path in args.data_files}
        actual_funds = set(dashboard["Fund Label"]) if "Fund Label" in dashboard.columns else set()
        missing = sorted(expected_funds - actual_funds)
        if missing:
            errors.append(f"Dashboard is missing explicit data-file rows: {missing}")
    elif args.all:
        expected_funds = {fund_label_from_data_file(path) for path in DATA_DIR.glob(args.fund_glob)}
        actual_funds = set(dashboard["Fund Label"]) if "Fund Label" in dashboard.columns else set()
        missing = sorted(expected_funds - actual_funds)
        if missing:
            errors.append(f"Dashboard is missing fund rows: {missing}")

    required_dashboard_cols = [
        "Fund Label",
        "Decision Label",
        "Decision Reason",
        "Probability >= Upside Target",
        "Probability <= Downside Risk",
        "Expected Forward Return",
        "Confidence Level",
        "Analog Count",
    ]
    missing_cols = [col for col in required_dashboard_cols if col not in dashboard.columns]
    if missing_cols:
        errors.append(f"Dashboard missing columns: {missing_cols}")

    expected_detail_rows = len(set(dashboard["Fund Label"])) * len(horizons) if "Fund Label" in dashboard.columns else 0
    if len(details) < expected_detail_rows:
        errors.append(f"Detail rows are fewer than expected: {len(details)} < {expected_detail_rows}")

    if not analogs.empty and analogs["Forward Return"].isna().any():
        errors.append("Analog detail contains rows without known forward returns.")

    if (
        getattr(args, "forward_method", DEFAULT_FORWARD_METHOD) != "legacy"
        and not analogs.empty
        and {"Fund Label", "Horizon", "Start Date", "End Date"}.issubset(analogs.columns)
    ):
        for (fund_label, horizon_label), group in analogs.groupby(["Fund Label", "Horizon"]):
            intervals = [
                (pd.Timestamp(row["Start Date"]), pd.Timestamp(row["End Date"]))
                for _, row in group.iterrows()
            ]
            for index, (start, end) in enumerate(intervals):
                if any(intervals_overlap(start, end, other_start, other_end) for other_start, other_end in intervals[index + 1 :]):
                    errors.append(f"Overlapping analog periods found for {fund_label} {horizon_label}.")
                    break

    if "Decision Label" in dashboard.columns:
        recomputed = dashboard.apply(lambda row: decide(row)[0], axis=1)
        if not recomputed.eq(dashboard["Decision Label"]).all():
            errors.append("At least one dashboard decision does not match the centralized decision rules.")

    bad_actions = set(dashboard.get("Decision Label", [])) - set(ACTION_ORDER)
    if bad_actions:
        errors.append(f"Unexpected decision labels: {sorted(bad_actions)}")

    if errors:
        raise AssertionError("; ".join(errors))


def deduplicate_csv_paths(csv_paths):
    """Keep the newest file for each normalized fund label and warn on collisions."""
    grouped = {}
    for path in csv_paths:
        grouped.setdefault(fund_label_from_data_file(path), []).append(Path(path))

    selected = []
    for fund_label, paths in grouped.items():
        keep = max(paths, key=lambda path: (path.stat().st_mtime_ns, str(path)))
        selected.append(keep)
        if len(paths) > 1:
            skipped_paths = list(paths)
            skipped_paths.remove(keep)
            skipped = [str(path) for path in skipped_paths]
            print(
                f"Warning: duplicate data files normalize to {fund_label}; "
                f"using newest file {keep} and skipping {skipped}."
            )
    return selected


def main():
    args = parse_args()
    if args.forward_method == "dual-relative-v2":
        args.forward_method = DEFAULT_FORWARD_METHOD
    horizons = parse_horizons(args.horizons)
    output_dir = resolve_repo_path(args.output_dir)
    chart_dir = resolve_repo_path(args.chart_dir)

    if args.primary_horizon not in horizons:
        raise ValueError(f"--primary-horizon must be one of: {', '.join(horizons)}")
    if args.min_analogs <= 0 or args.max_analogs <= 0:
        raise ValueError("--min-analogs and --max-analogs must be positive.")
    if args.max_analogs < args.min_analogs:
        raise ValueError("--max-analogs must be greater than or equal to --min-analogs.")
    if args.legacy_max_analogs <= 0:
        raise ValueError("--legacy-max-analogs must be positive.")
    if args.prior_strength < 0:
        raise ValueError("--prior-strength must be non-negative.")
    if args.upside_target <= -1 or args.downside_risk <= -1:
        raise ValueError("Return thresholds must be greater than -1.0.")
    args.primary_horizon_days = horizons[args.primary_horizon]

    if args.data_files:
        csv_paths = [resolve_repo_path(path) for path in args.data_files]
        missing_paths = [path for path in csv_paths if not path.exists()]
        if missing_paths:
            raise FileNotFoundError(f"CSV file(s) not found: {missing_paths}")
    elif args.all:
        csv_paths = sorted(DATA_DIR.glob(args.fund_glob))
        if not csv_paths:
            raise FileNotFoundError(f"No files matched data/{args.fund_glob}")
    else:
        csv_paths = [resolve_repo_path(args.data_file)]
        if not csv_paths[0].exists():
            raise FileNotFoundError(f"CSV file not found: {csv_paths[0]}")

    csv_paths = deduplicate_csv_paths(csv_paths)

    dashboards = []
    details = []
    analog_details = []
    for csv_path in csv_paths:
        dashboard, detail, analog_detail = analyze_one_file(csv_path, args, horizons)
        dashboards.append(dashboard)
        details.append(detail)
        if not analog_detail.empty:
            analog_details.append(analog_detail)

    dashboard_df = pd.concat(dashboards, ignore_index=True)
    detail_df = pd.concat(details, ignore_index=True)
    analog_df = pd.concat(analog_details, ignore_index=True) if analog_details else pd.DataFrame()

    if dashboard_df["Fund Label"].duplicated().any():
        duplicates = sorted(dashboard_df.loc[dashboard_df["Fund Label"].duplicated(False), "Fund Label"].unique())
        raise ValueError(f"Dashboard contains duplicate fund labels after input deduplication: {duplicates}")
    if detail_df.duplicated(["Fund Label", "Horizon"]).any():
        duplicate_pairs = detail_df.loc[
            detail_df.duplicated(["Fund Label", "Horizon"], keep=False),
            ["Fund Label", "Horizon"],
        ].drop_duplicates()
        raise ValueError(f"Decision details contain duplicate fund/horizon rows: {duplicate_pairs.to_dict('records')}")

    dashboard_df = refresh_dashboard_decisions(dashboard_df)
    dashboard_df = dashboard_df.sort_values(
        ["Action Rank", "Decision Score", "Probability >= Upside Target"],
        ascending=[True, False, False],
    ).reset_index(drop=True)
    dashboard_df = dashboard_df.drop(columns=["Action Rank"], errors="ignore")
    detail_df = detail_df.sort_values(["Fund Label", "Horizon"]).reset_index(drop=True)

    chart_paths = (
        create_charts(
            dashboard_df,
            detail_df,
            chart_dir,
            args.primary_horizon,
            list(horizons.keys()),
            include_primary_charts=args.charts,
            include_all_horizon_chart=args.all_horizon_chart,
        )
        if args.charts or args.all_horizon_chart
        else []
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = save_csv(
        dashboard_df,
        output_dir / "fund_forward_decision_dashboard.csv",
        allow_fallback=False,
    )
    details_path = save_csv(
        detail_df,
        output_dir / "fund_forward_decision_details.csv",
        allow_fallback=False,
    )
    analog_path = (
        save_csv(
            analog_df,
            output_dir / "fund_forward_decision_analogs.csv",
            allow_fallback=False,
        )
        if not analog_df.empty
        else None
    )
    html_path = output_dir / "fund_forward_decision_dashboard.html"
    html_path.write_text(build_html_report(dashboard_df, detail_df, chart_paths, output_dir, args), encoding="utf-8")

    if args.validate:
        validate_outputs(dashboard_df, detail_df, analog_df, horizons, args)

    print(f"Analyzed {len(csv_paths)} fund file(s).")
    print(f"Dashboard CSV: {dashboard_path}")
    print(f"Details CSV: {details_path}")
    if analog_path:
        print(f"Analog detail CSV: {analog_path}")
    print(f"HTML dashboard: {html_path}")
    if chart_paths:
        print(f"Charts: {chart_dir}")
    if args.validate:
        print("Validation checks passed.")


if __name__ == "__main__":
    main()
