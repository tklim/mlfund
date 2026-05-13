import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.common import CHARTS_DIR, TUNINGS_DIR, ensure_dir, resolve_repo_path, save_csv


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze GA population/generation performance.")
    parser.add_argument(
        "--analysis-file",
        default=str(TUNINGS_DIR / "miieh_analysis.csv"),
        help="Cleaned fund analysis CSV. Relative paths resolve from repo root.",
    )
    parser.add_argument("--output-dir", default=str(CHARTS_DIR), help="Directory for generated charts.")
    parser.add_argument(
        "--summary-file",
        default=str(TUNINGS_DIR / "miieh_pop_gen_summary.csv"),
        help="CSV summary output path.",
    )
    parser.add_argument("--fund-label", default="MIIEH", help="Fund label used in chart titles.")
    return parser.parse_args()


def main():
    args = parse_args()
    analysis_file = resolve_repo_path(args.analysis_file)
    if not analysis_file.exists():
        raise FileNotFoundError(f"Analysis file not found: {analysis_file}")

    cols = ["best_ga_pop_size", "best_ga_generations", "adaptive_return_pct", "lookback_years", "offset_months"]
    df = pd.read_csv(analysis_file)
    df = df[[col for col in cols if col in df.columns]].copy()
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["best_ga_pop_size", "best_ga_generations", "adaptive_return_pct"])

    output_dir = ensure_dir(resolve_repo_path(args.output_dir))
    label = args.fund_label
    print(f"Analyzing {len(df)} {label} runs with pop/gen data")

    pivot = df.pivot_table(
        values="adaptive_return_pct",
        index="best_ga_generations",
        columns="best_ga_pop_size",
        aggfunc="mean",
    )

    plt.figure(figsize=(10, 6))
    heatmap = plt.imshow(pivot.values, cmap="RdYlGn", aspect="auto")
    plt.xticks(range(len(pivot.columns)), pivot.columns)
    plt.yticks(range(len(pivot.index)), pivot.index)
    plt.xlabel("Population Size")
    plt.ylabel("Generations")
    plt.title(f"{label}: Adaptive Return by Pop Size & Generations")
    plt.colorbar(heatmap, label="Avg Adaptive Return (%)")
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            if not np.isnan(val):
                plt.text(j, i, f"{val:.1f}", ha="center", va="center", color="black" if val < -10 else "white")
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_pop_gen_heatmap.png", dpi=150)
    plt.close()

    plt.figure(figsize=(10, 6))
    scatter = plt.scatter(
        df["best_ga_pop_size"],
        df["best_ga_generations"],
        c=df["adaptive_return_pct"],
        cmap="RdYlGn",
        s=100,
        alpha=0.7,
        edgecolors="black",
    )
    plt.xlabel("Population Size")
    plt.ylabel("Generations")
    plt.title(f"{label}: Pop Size vs Generations (Color = Adaptive Return)")
    plt.colorbar(scatter, label="Adaptive Return (%)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_pop_gen_scatter.png", dpi=150)
    plt.close()

    print("\nTop 5 Pop/Gen combos (highest avg return):")
    top_combos = (
        df.groupby(["best_ga_pop_size", "best_ga_generations"])["adaptive_return_pct"]
        .mean()
        .sort_values(ascending=False)
        .head(5)
    )
    print(top_combos)

    summary = (
        df.groupby(["best_ga_pop_size", "best_ga_generations"])["adaptive_return_pct"]
        .agg(["mean", "count"])
        .reset_index()
    )
    summary_path = save_csv(summary, resolve_repo_path(args.summary_file))
    print(f"\nSaved summary to {summary_path}")


if __name__ == "__main__":
    main()
