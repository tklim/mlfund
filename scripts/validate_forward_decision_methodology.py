"""Rolling-origin comparison of legacy and dual_relative_v2 forward decisions.

This validator deliberately imports the production feature, analog, probability,
and decision functions.  It is a research diagnostic, not investment advice.
"""

import argparse
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from common import DATA_DIR, REPORTS_DIR, fund_label_from_data_file, resolve_repo_path, save_csv
from fund_forward_decision import (
    DEFAULT_CONTINUOUS_FEATURES,
    DEFAULT_FORWARD_METHOD,
    add_state_features,
    calculate_calendar_forward_return_frame,
    decide,
    load_total_return_data,
    nearest_analogs,
    select_non_overlapping_rows,
    summarize_analogs,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Walk-forward validation for both forward-decision methods.")
    parser.add_argument("--data-file", default="data/HWFL_HWFlexi_nav_5Y.csv")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--fund-glob", default="*_nav_5Y.csv")
    parser.add_argument("--date-column", default="Date")
    parser.add_argument("--price-column", default="TotalReturn")
    parser.add_argument("--horizon", default="6M")
    parser.add_argument("--horizon-days", type=int, default=126)
    parser.add_argument("--upside-target", type=float, default=0.15)
    parser.add_argument("--downside-risk", type=float, default=-0.08)
    parser.add_argument("--min-analogs", type=int, default=6)
    parser.add_argument("--max-analogs", type=int, default=20)
    parser.add_argument("--legacy-max-analogs", type=int, default=150)
    parser.add_argument("--prior-strength", type=float, default=4.0)
    parser.add_argument("--calibration-fraction", type=float, default=0.70)
    parser.add_argument("--output-dir", default=str(REPORTS_DIR))
    return parser.parse_args()


def training_forward_frame(forward_frame, decision_date):
    """Use only outcomes fully known strictly before the decision date."""
    decision_date = pd.Timestamp(decision_date)
    frame = forward_frame.copy()
    frame["End Date"] = pd.to_datetime(frame["End Date"], errors="coerce")
    return frame.loc[frame["End Date"] < decision_date].copy()


def select_evaluation_periods(forward_frame, features, min_baseline=6):
    """Return chronologically spaced actual intervals with enough prior evidence."""
    complete_dates = set(
        pd.to_datetime(features.dropna(subset=DEFAULT_CONTINUOUS_FEATURES)["Date"], errors="coerce")
    )
    candidates = forward_frame.loc[forward_frame["Start Date"].isin(complete_dates)].copy()
    eligible = []
    for index, row in candidates.sort_values("Start Date").iterrows():
        train = training_forward_frame(forward_frame, row["Start Date"])
        independent = select_non_overlapping_rows(train, sort_columns=["End Date", "Start Date"])
        if len(independent) >= min_baseline:
            eligible.append(index)
    if not eligible:
        return candidates.head(0).copy()
    eligible_frame = candidates.loc[eligible]
    return select_non_overlapping_rows(eligible_frame, sort_columns=["Start Date"])


def model_args(base, method, prior_strength):
    return SimpleNamespace(
        forward_method=method,
        legacy_max_analogs=base.legacy_max_analogs,
        min_analogs=base.min_analogs,
        max_analogs=base.max_analogs,
        prior_strength=float(prior_strength),
        upside_target=base.upside_target,
        downside_risk=base.downside_risk,
        target_scaling="compounded",
        primary_horizon_days=base.horizon_days,
    )


def relative_predictions(summary, analogs, training_returns):
    p75 = training_returns.quantile(0.75) if len(training_returns) else np.nan
    p25 = training_returns.quantile(0.25) if len(training_returns) else np.nan
    if summary["Forward Method Version"] == DEFAULT_FORWARD_METHOD:
        return (
            summary["Relative Upside Probability"],
            summary["Relative Downside Probability"],
            p75,
            p25,
        )
    analog_returns = analogs["Forward Return"].dropna()
    if not len(analog_returns) or pd.isna(p75) or pd.isna(p25):
        return np.nan, np.nan, p75, p25
    return float((analog_returns >= p75).mean()), float((analog_returns <= p25).mean()), p75, p25


def evaluate_variant(path, raw, features, forward_frame, evaluation_periods, base, method, prior_strength):
    rows = []
    fund_label = fund_label_from_data_file(path)
    args = model_args(base, method, prior_strength)
    feature_by_date = features.set_index("Date", drop=False)
    for _, evaluation in evaluation_periods.iterrows():
        decision_date = pd.Timestamp(evaluation["Start Date"])
        training_forward = training_forward_frame(forward_frame, decision_date)
        training_features = features.loc[features["Date"] < decision_date].copy()
        latest_row = feature_by_date.loc[decision_date]
        if isinstance(latest_row, pd.DataFrame):
            latest_row = latest_row.iloc[-1]
        analogs = nearest_analogs(
            training_features,
            training_forward,
            latest_row,
            base.horizon,
            base.horizon_days,
            args,
        )
        summary = summarize_analogs(
            fund_label,
            latest_row,
            base.horizon,
            base.horizon_days,
            analogs,
            training_forward,
            args,
        )
        action, _ = decide(pd.Series(summary))
        training_returns = training_forward["Forward Return"].dropna()
        rel_up, rel_down, p75, p25 = relative_predictions(summary, analogs, training_returns)
        realized = float(evaluation["Forward Return"])
        up_target = float(summary["Upside Target"])
        down_target = float(summary["Downside Risk"])
        rows.append(
            {
                "Fund Label": fund_label,
                "Decision Date": decision_date,
                "Evaluation End Date": pd.Timestamp(evaluation["End Date"]),
                "Method": method,
                "Prior Strength": float(prior_strength),
                "Decision Label": action,
                "Trend State": latest_row["Trend State"],
                "Annualized Volatility 3M": latest_row["Annualized Volatility 3M"],
                "Expected Return": summary["Expected Forward Return"],
                "Realized Return": realized,
                "Signed Error": summary["Expected Forward Return"] - realized,
                "Absolute Error": abs(summary["Expected Forward Return"] - realized),
                "Absolute Upside Probability": summary["Probability >= Upside Target"],
                "Absolute Downside Probability": summary["Probability <= Downside Risk"],
                "Absolute Upside Event": float(realized >= up_target),
                "Absolute Downside Event": float(realized <= down_target),
                "Relative Upside Probability": rel_up,
                "Relative Downside Probability": rel_down,
                "Relative Upside Event": float(realized >= p75) if pd.notna(p75) else np.nan,
                "Relative Downside Event": float(realized <= p25) if pd.notna(p25) else np.nan,
                "Relative Upside Threshold": p75,
                "Relative Downside Threshold": p25,
                "Analog Count": summary["Analog Count"],
                "Base Observations": summary["Base Observations"],
                "Confidence Level": summary["Confidence Level"],
            }
        )
    return rows


def brier(frame, probability_col, event_col):
    valid = frame[[probability_col, event_col]].dropna()
    return float(((valid[probability_col] - valid[event_col]) ** 2).mean()) if len(valid) else np.nan


def metric_row(frame, split_name, method, prior):
    return {
        "Split": split_name,
        "Method": method,
        "Prior Strength": prior,
        "Observations": len(frame),
        "MAE": frame["Absolute Error"].mean(),
        "Signed Bias": frame["Signed Error"].mean(),
        "Absolute Upside Brier": brier(frame, "Absolute Upside Probability", "Absolute Upside Event"),
        "Absolute Downside Brier": brier(frame, "Absolute Downside Probability", "Absolute Downside Event"),
        "Relative Upside Brier": brier(frame, "Relative Upside Probability", "Relative Upside Event"),
        "Relative Downside Brier": brier(frame, "Relative Downside Probability", "Relative Downside Event"),
    }


def add_split_and_volatility(frame, calibration_fraction):
    result = frame.copy()
    unique_dates = sorted(pd.to_datetime(result["Decision Date"].unique()))
    cutoff_index = max(1, min(len(unique_dates) - 1, int(np.floor(len(unique_dates) * calibration_fraction))))
    holdout_dates = set(unique_dates[cutoff_index:])
    result["Split"] = np.where(result["Decision Date"].isin(holdout_dates), "holdout", "calibration")
    base = result.loc[
        (result["Method"] == DEFAULT_FORWARD_METHOD) & (result["Prior Strength"] == 4.0)
    ].drop_duplicates(["Fund Label", "Decision Date"])
    vol_map = {}
    for fund, group in base.groupby("Fund Label"):
        try:
            labels = pd.qcut(group["Annualized Volatility 3M"], 3, labels=["low", "middle", "high"], duplicates="drop")
        except ValueError:
            labels = pd.Series("unavailable", index=group.index)
        for index, label in labels.items():
            vol_map[(fund, pd.Timestamp(base.loc[index, "Decision Date"]))] = str(label)
    result["Volatility Tertile"] = [
        vol_map.get((row["Fund Label"], pd.Timestamp(row["Decision Date"])), "unavailable")
        for _, row in result.iterrows()
    ]
    return result


def average_brier(row):
    values = [
        row.get("Absolute Upside Brier"),
        row.get("Absolute Downside Brier"),
        row.get("Relative Upside Brier"),
        row.get("Relative Downside Brier"),
    ]
    values = [float(value) for value in values if pd.notna(value)]
    return float(np.mean(values)) if values else np.nan


def relative_worsening(new, old):
    if pd.isna(new) or pd.isna(old):
        return np.inf
    return (new - old) / max(abs(old), 1e-12)


def acceptance_result(metrics, results):
    holdout = metrics.loc[(metrics["Split"] == "holdout") & (metrics["Prior Strength"] == 4.0)]
    legacy = holdout.loc[holdout["Method"] == "legacy"]
    v2 = holdout.loc[holdout["Method"] == DEFAULT_FORWARD_METHOD]
    if legacy.empty or v2.empty:
        return "REVIEW: insufficient holdout observations"
    legacy, v2 = legacy.iloc[0], v2.iloc[0]
    mae_change = relative_worsening(v2["MAE"], legacy["MAE"])
    brier_change = relative_worsening(average_brier(v2), average_brier(legacy))
    acceptable = (mae_change <= 0 and brier_change <= 0) or (
        (mae_change <= 0 and brier_change <= 0.05) or (brier_change <= 0 and mae_change <= 0.05)
    )
    subgroup_stop = False
    holdout_results = results.loc[(results["Split"] == "holdout") & (results["Prior Strength"] == 4.0)]
    for group_col in ["Trend State", "Volatility Tertile"]:
        for _, group in holdout_results.groupby(group_col):
            pivot = group.groupby("Method")["Signed Error"].agg(["mean", "count"])
            if {"legacy", DEFAULT_FORWARD_METHOD}.issubset(pivot.index):
                comparable_n = min(pivot.loc["legacy", "count"], pivot.loc[DEFAULT_FORWARD_METHOD, "count"])
                added_bias = abs(pivot.loc[DEFAULT_FORWARD_METHOD, "mean"]) - abs(pivot.loc["legacy", "mean"])
                if comparable_n >= 10 and added_bias > 0.05:
                    subgroup_stop = True
    if subgroup_stop:
        return "REVIEW: subgroup signed bias worsened by more than 5 percentage points"
    return "ACCEPT" if acceptable else "REVIEW: rollout thresholds were not met"


def markdown_report(metrics, results, acceptance):
    primary = results.loc[results["Prior Strength"] == 4.0]
    labels = primary.groupby(["Split", "Method", "Decision Label"]).size().rename("Count").reset_index()
    outcomes = (
        primary.groupby(["Split", "Method", "Decision Label"])["Realized Return"]
        .agg(["count", "mean", "median"])
        .reset_index()
    )
    subgroup = (
        primary.groupby(["Split", "Method", "Trend State", "Volatility Tertile"])
        .agg(Observations=("Realized Return", "size"), Signed_Bias=("Signed Error", "mean"), MAE=("Absolute Error", "mean"))
        .reset_index()
    )
    lines = [
        "# Forward-Decision Walk-Forward Validation",
        "",
        f"**Rollout result:** {acceptance}",
        "",
        "The first 70% of horizon-spaced decision dates are calibration diagnostics; the latest 30% are untouched holdout. Prior strength 4 is pre-registered. Sensitivity 2/4/8 is reported only on calibration and never changes the selected prior.",
        "",
        "All training outcomes and P25/P75 thresholds use rows whose actual `End Date` is strictly earlier than the decision date. Ratings are general research support, not personalized financial advice.",
        "",
        "## Core Metrics",
        "",
        metrics.to_markdown(index=False, floatfmt=".5f"),
        "",
        "## Label Frequency",
        "",
        labels.to_markdown(index=False),
        "",
        "## Realized Outcomes by Label",
        "",
        outcomes.to_markdown(index=False, floatfmt=".5f"),
        "",
        "## Trend and Volatility Subgroups",
        "",
        subgroup.to_markdown(index=False, floatfmt=".5f"),
        "",
    ]
    active_v2 = primary.loc[
        (primary["Method"] == DEFAULT_FORWARD_METHOD)
        & primary["Decision Label"].isin(["BUY", "SELL / AVOID"])
    ]
    if len(active_v2) < 6:
        lines.extend(["**Signal sample:** insufficient decisions; independence and confidence rules were not relaxed.", ""])
    return "\n".join(lines)


def main():
    args = parse_args()
    if args.prior_strength != 4.0:
        raise ValueError("Prior strength 4 is pre-registered; use 2/4/8 sensitivity only through this validator.")
    if not 0 < args.calibration_fraction < 1:
        raise ValueError("--calibration-fraction must be between 0 and 1.")
    paths = sorted(DATA_DIR.glob(args.fund_glob)) if args.all else [resolve_repo_path(args.data_file)]
    if not paths:
        raise FileNotFoundError("No input fund files were found.")

    prepared = []
    evaluation_dates = []
    for path in paths:
        raw = load_total_return_data(path, args.date_column, args.price_column)
        features = add_state_features(raw)
        forward_frame = calculate_calendar_forward_return_frame(raw, args.horizon, args.horizon_days)
        evaluation_periods = select_evaluation_periods(forward_frame, features, args.min_analogs)
        if evaluation_periods.empty:
            print(f"Warning: no eligible evaluation periods for {path.name}")
            continue
        prepared.append((path, raw, features, forward_frame, evaluation_periods))
        evaluation_dates.extend(pd.to_datetime(evaluation_periods["Start Date"]).tolist())
    if not prepared:
        raise ValueError("No walk-forward evaluations could be generated.")

    unique_dates = sorted(set(evaluation_dates))
    cutoff_index = max(
        1,
        min(len(unique_dates) - 1, int(np.floor(len(unique_dates) * args.calibration_fraction))),
    )
    holdout_dates = set(unique_dates[cutoff_index:])

    rows = []
    for path, raw, features, forward_frame, evaluation_periods in prepared:
        rows.extend(evaluate_variant(path, raw, features, forward_frame, evaluation_periods, args, "legacy", 4.0))
        rows.extend(
            evaluate_variant(path, raw, features, forward_frame, evaluation_periods, args, DEFAULT_FORWARD_METHOD, 4.0)
        )
        calibration_periods = evaluation_periods.loc[~evaluation_periods["Start Date"].isin(holdout_dates)]
        for prior in [2.0, 8.0]:
            rows.extend(
                evaluate_variant(
                    path,
                    raw,
                    features,
                    forward_frame,
                    calibration_periods,
                    args,
                    DEFAULT_FORWARD_METHOD,
                    prior,
                )
            )

    results = add_split_and_volatility(pd.DataFrame(rows), args.calibration_fraction)
    metric_rows = []
    for (split, method, prior), group in results.groupby(["Split", "Method", "Prior Strength"]):
        if split == "holdout" and method == DEFAULT_FORWARD_METHOD and prior != 4.0:
            continue
        metric_rows.append(metric_row(group, split, method, prior))
    metrics = pd.DataFrame(metric_rows)
    acceptance = acceptance_result(metrics, results)

    output_dir = resolve_repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "forward_decision_walk_forward.csv"
    metrics_path = output_dir / "forward_decision_walk_forward_metrics.csv"
    report_path = output_dir / "forward_decision_walk_forward.md"
    save_csv(results, results_path)
    save_csv(metrics, metrics_path)
    report_path.write_text(markdown_report(metrics, results, acceptance), encoding="utf-8")
    print(f"Evaluations: {len(results)}")
    print(f"Rollout result: {acceptance}")
    print(f"Results CSV: {results_path}")
    print(f"Metrics CSV: {metrics_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
