import argparse

import pandas as pd
import numpy as np
from scipy.stats import norm

from common import REPORTS_DIR, fund_label_from_data_file, resolve_repo_path, save_csv


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze forward-return probabilities for a fund TotalReturn series."
    )
    parser.add_argument(
        "--data-file",
        default="data/HWFL_HWFlexi_nav_5Y.csv",
        help="CSV file to analyze. Relative paths resolve from repo root.",
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
        "--output-dir",
        default=str(REPORTS_DIR),
        help=f"Directory for generated CSV outputs (default: {REPORTS_DIR}).",
    )
    return parser.parse_args()


def resolve_input_path(data_file):
    return resolve_repo_path(data_file)


def load_total_return_data(csv_path, date_col="Date", total_return_col="TotalReturn"):
    """
    Load fund data and prepare TotalReturn time series.
    Update date_col / total_return_col if your CSV uses different column names.
    """
    df = pd.read_csv(csv_path)

    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col).dropna(subset=[date_col, total_return_col])

    df = df[[date_col, total_return_col]].copy()
    df = df.rename(columns={date_col: "Date", total_return_col: "TotalReturn"})

    df["TotalReturn"] = pd.to_numeric(df["TotalReturn"], errors="coerce")
    df = df.dropna(subset=["TotalReturn"])

    return df


def calculate_forward_returns(df, horizons):
    """
    Calculate forward returns over different holding periods.

    Example:
    If today TotalReturn = 100 and 252 trading days later = 110,
    then 1Y forward return = 10%.
    """
    result = df.copy()

    for label, days in horizons.items():
        result[f"ForwardReturn_{label}"] = (
            result["TotalReturn"].shift(-days) / result["TotalReturn"] - 1
        )

    return result


def historical_probability_analysis(df, horizons, thresholds=(0.00, 0.05, 0.10)):
    """
    Estimate probabilities directly from historical forward returns.
    This answers questions like:
    - What % of past 1-year periods produced at least +5%?
    - What % of past 1-year periods produced at least +10%?
    """
    rows = []

    for label in horizons:
        col = f"ForwardReturn_{label}"
        returns = df[col].dropna()

        row = {
            "Horizon": label,
            "Observations": len(returns),
            "Average Forward Return": returns.mean(),
            "Median Forward Return": returns.median(),
            "Worst Forward Return": returns.min(),
            "Best Forward Return": returns.max(),
        }

        for threshold in thresholds:
            row[f"Probability >= {threshold:.0%}"] = (returns >= threshold).mean()

        rows.append(row)

    return pd.DataFrame(rows)


def lognormal_model_probability_analysis(df, horizons, thresholds=(0.00, 0.05, 0.10), trading_days=252):
    """
    Model-based probability estimate using daily log returns.

    Assumption:
    Daily TotalReturn changes are approximately normally distributed in log terms.
    This is a simplification, but useful as a comparison to historical forward returns.
    """
    daily_log_returns = np.log(df["TotalReturn"] / df["TotalReturn"].shift(1)).dropna()

    daily_mu = daily_log_returns.mean()
    daily_sigma = daily_log_returns.std(ddof=1)

    rows = []

    for label, days in horizons.items():
        horizon_mu = daily_mu * days
        horizon_sigma = daily_sigma * np.sqrt(days)

        row = {
            "Horizon": label,
            "Expected Return": np.exp(horizon_mu) - 1,
            "Expected Volatility": horizon_sigma,
        }

        for threshold in thresholds:
            log_threshold = np.log(1 + threshold)
            probability = 1 - norm.cdf(log_threshold, loc=horizon_mu, scale=horizon_sigma)
            row[f"Probability >= {threshold:.0%}"] = probability

        rows.append(row)

    return pd.DataFrame(rows)


def performance_summary(df, trading_days=252):
    """
    Overall performance summary for the TotalReturn series.
    """
    start_value = df["TotalReturn"].iloc[0]
    end_value = df["TotalReturn"].iloc[-1]

    total_return = end_value / start_value - 1

    num_days = (df["Date"].iloc[-1] - df["Date"].iloc[0]).days
    years = num_days / 365.25

    annualized_return = (end_value / start_value) ** (1 / years) - 1

    daily_returns = df["TotalReturn"].pct_change().dropna()
    annualized_volatility = daily_returns.std(ddof=1) * np.sqrt(trading_days)

    return pd.DataFrame(
        [{
            "Start Date": df["Date"].iloc[0].date(),
            "End Date": df["Date"].iloc[-1].date(),
            "Start TotalReturn": start_value,
            "End TotalReturn": end_value,
            "Total Cumulative Return": total_return,
            "Annualized Return": annualized_return,
            "Annualized Volatility": annualized_volatility,
        }]
    )


def format_percent_columns(df):
    """
    Nicely format probability and return columns as percentages.
    """
    formatted = df.copy()

    for col in formatted.columns:
        if (
            "Return" in col
            or "Probability" in col
            or "Volatility" in col
        ):
            formatted[col] = formatted[col].map(lambda x: f"{x:.2%}" if pd.notna(x) else "")

    return formatted


def main():
    args = parse_args()
    csv_path = resolve_input_path(args.data_file)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    output_dir = resolve_repo_path(args.output_dir)
    fund_label = fund_label_from_data_file(csv_path)

    horizons = {
        "1M": 21,
        "3M": 63,
        "6M": 126,
        "1Y": 252,
    }

    thresholds = (0.00, 0.05, 0.10)

    df = load_total_return_data(
        csv_path,
        date_col=args.date_column,
        total_return_col=args.price_column
    )

    df = calculate_forward_returns(df, horizons)

    summary = performance_summary(df)
    historical_probs = historical_probability_analysis(df, horizons, thresholds)
    model_probs = lognormal_model_probability_analysis(df, horizons, thresholds)

    print("\n=== TotalReturn Performance Summary ===")
    print(format_percent_columns(summary).to_string(index=False))

    print("\n=== Historical Forward-Return Probability Analysis ===")
    print(format_percent_columns(historical_probs).to_string(index=False))

    print("\n=== Lognormal Model-Based Probability Analysis ===")
    print(format_percent_columns(model_probs).to_string(index=False))

    summary_path = save_csv(summary, output_dir / f"{fund_label}_probability_summary.csv")
    historical_path = save_csv(
        historical_probs,
        output_dir / f"{fund_label}_historical_forward_return_probabilities.csv",
    )
    model_path = save_csv(
        model_probs,
        output_dir / f"{fund_label}_lognormal_model_probabilities.csv",
    )

    print("\nSaved files:")
    print(f"- {summary_path}")
    print(f"- {historical_path}")
    print(f"- {model_path}")


if __name__ == "__main__":
    main()
