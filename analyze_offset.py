import argparse

import matplotlib.pyplot as plt
import pandas as pd

from scripts.common import CHARTS_DIR, TUNINGS_DIR, ensure_dir, resolve_repo_path


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze one fund's offset-month performance.")
    parser.add_argument(
        "--analysis-file",
        default=str(TUNINGS_DIR / "miieh_analysis.csv"),
        help="Cleaned fund analysis CSV. Relative paths resolve from repo root.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(CHARTS_DIR),
        help="Directory for generated charts.",
    )
    parser.add_argument(
        "--fund-label",
        default="MIIEH",
        help="Fund label used in chart titles and filenames.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    analysis_file = resolve_repo_path(args.analysis_file)
    if not analysis_file.exists():
        raise FileNotFoundError(f"Analysis file not found: {analysis_file}")

    df = pd.read_csv(analysis_file)
    for col in ["offset_months", "adaptive_return_pct", "lookback_years", "sharpe", "max_dd_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["offset_months", "adaptive_return_pct"])

    output_dir = ensure_dir(resolve_repo_path(args.output_dir))
    label = args.fund_label

    print(f"Analyzing {len(df)} {label} runs")
    print(f"Offset months: {sorted(df['offset_months'].unique())}")

    plt.figure(figsize=(12, 6))
    for lookback in sorted(df["lookback_years"].dropna().unique()):
        subset = df[df["lookback_years"] == lookback]
        offset_means = subset.groupby("offset_months")["adaptive_return_pct"].mean()
        plt.plot(offset_means.index, offset_means.values, marker="o", label=f"{lookback}Y lookback", linewidth=2, markersize=8)
    plt.xlabel("Offset Months")
    plt.ylabel("Avg Adaptive Return (%)")
    plt.title(f"{label}: Offset Months vs Adaptive Return (by Lookback)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_offset_vs_return.png", dpi=150)
    plt.close()

    plt.figure(figsize=(12, 6))
    for lookback in sorted(df["lookback_years"].dropna().unique()):
        subset = df[df["lookback_years"] == lookback]
        offset_means = subset.groupby("offset_months")["sharpe"].mean()
        plt.plot(offset_means.index, offset_means.values, marker="s", label=f"{lookback}Y lookback", linewidth=2, markersize=8)
    plt.xlabel("Offset Months")
    plt.ylabel("Avg Sharpe Ratio")
    plt.title(f"{label}: Offset Months vs Sharpe Ratio (by Lookback)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_offset_vs_sharpe.png", dpi=150)
    plt.close()

    plt.figure(figsize=(12, 6))
    for lookback in sorted(df["lookback_years"].dropna().unique()):
        subset = df[df["lookback_years"] == lookback]
        offset_means = subset.groupby("offset_months")["max_dd_pct"].mean()
        plt.plot(offset_means.index, offset_means.values, marker="^", label=f"{lookback}Y lookback", linewidth=2, markersize=8)
    plt.xlabel("Offset Months")
    plt.ylabel("Avg Max Drawdown (%)")
    plt.title(f"{label}: Offset Months vs Max Drawdown (by Lookback)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_offset_vs_dd.png", dpi=150)
    plt.close()

    plt.figure(figsize=(10, 6))
    df.boxplot(column="adaptive_return_pct", by="offset_months", grid=True, ax=plt.gca())
    plt.title(f"{label}: Adaptive Return Distribution by Offset Months")
    plt.suptitle("")
    plt.xlabel("Offset Months")
    plt.ylabel("Adaptive Return (%)")
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_offset_boxplot.png", dpi=150)
    plt.close()

    print("\n=== Offset Months Analysis ===")
    print(
        df.groupby("offset_months")
        .agg({"adaptive_return_pct": ["mean", "std", "count"], "sharpe": "mean", "max_dd_pct": "mean"})
        .round(2)
    )

    print("\n=== Best Offset (by avg return) ===")
    print(df.groupby("offset_months")["adaptive_return_pct"].mean().sort_values(ascending=False))


if __name__ == "__main__":
    main()
