import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.common import CHARTS_DIR, TUNINGS_DIR, annualize_return_series, ensure_dir, resolve_repo_path, save_csv


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze all fund backtest runs and generate summary charts.")
    parser.add_argument(
        "--history-file",
        default=str(TUNINGS_DIR / "backtest_run_history.csv"),
        help="Backtest run history CSV. Relative paths resolve from repo root.",
    )
    parser.add_argument("--output-dir", default=str(CHARTS_DIR), help="Directory for generated charts.")
    parser.add_argument(
        "--summary-file",
        default=str(TUNINGS_DIR / "all_funds_summary.csv"),
        help="CSV summary output path.",
    )
    parser.add_argument(
        "--exclude-funds",
        nargs="*",
        default=[],
        help="Optional fund labels to exclude.",
    )
    parser.add_argument("--top-n", type=int, default=5, help="Number of funds to include in comparison charts.")
    return parser.parse_args()


def ensure_annualized_fields(df):
    for col in [
        "adaptive_annualized_return_pct",
        "buy_hold_annualized_return_pct",
        "excess_annualized_return_pct",
    ]:
        if col not in df.columns:
            df[col] = np.nan

    if {"adaptive_return_pct", "backtest_start", "backtest_end"}.issubset(df.columns):
        derived = annualize_return_series(df["adaptive_return_pct"], df["backtest_start"], df["backtest_end"])
        df["adaptive_annualized_return_pct"] = df["adaptive_annualized_return_pct"].fillna(derived)
    if {"buy_hold_return_pct", "backtest_start", "backtest_end"}.issubset(df.columns):
        derived = annualize_return_series(df["buy_hold_return_pct"], df["backtest_start"], df["backtest_end"])
        df["buy_hold_annualized_return_pct"] = df["buy_hold_annualized_return_pct"].fillna(derived)
    if {"excess_return_pct", "backtest_start", "backtest_end"}.issubset(df.columns):
        derived = annualize_return_series(df["excess_return_pct"], df["backtest_start"], df["backtest_end"])
        df["excess_annualized_return_pct"] = df["excess_annualized_return_pct"].fillna(derived)
    return df


def main():
    args = parse_args()
    history_file = resolve_repo_path(args.history_file)
    if not history_file.exists():
        raise FileNotFoundError(f"Run history file not found: {history_file}")

    df = pd.read_csv(history_file)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed:")].copy()
    if args.exclude_funds:
        df = df[~df["fund_label"].isin(args.exclude_funds)]
        print(f"Excluded funds: {args.exclude_funds}")

    numeric_cols = [
        "lookback_years",
        "offset_months",
        "adaptive_return_pct",
        "adaptive_annualized_return_pct",
        "buy_hold_annualized_return_pct",
        "sharpe",
        "max_dd_pct",
        "excess_return_pct",
        "excess_annualized_return_pct",
        "last_short_ema",
        "last_long_ema",
        "last_stop_loss",
        "last_cooldown",
        "last_drawdown_exit_pct",
        "last_reentry_rebound_pct",
        "trade_count",
        "win_rate_pct",
        "best_ga_pop_size",
        "best_ga_generations",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = ensure_annualized_fields(df)

    print(f"Total runs: {len(df)}")
    print(f"Funds: {df['fund_label'].unique()}")
    print(f"Columns: {len(df.columns)}")

    output_dir = ensure_dir(resolve_repo_path(args.output_dir))
    annualized_col = "adaptive_annualized_return_pct"
    valid_df = df[df[annualized_col].notna()].copy()
    fund_order = (
        valid_df.groupby("fund_label")[annualized_col]
        .mean()
        .sort_values(ascending=False)
        .index
        .tolist()
    )
    funds_without_annualized = sorted(set(df["fund_label"]) - set(valid_df["fund_label"]))

    print("\n=== Avg Annualized Return by Fund ===")
    fund_stats = df.groupby("fund_label").agg({annualized_col: ["mean", "std", "count"], "sharpe": "mean", "max_dd_pct": "mean"}).round(2)
    print(fund_stats)
    if funds_without_annualized:
        print(f"\nFunds with no usable annualized return data: {funds_without_annualized}")

    fig, ax = plt.subplots(figsize=(12, 6))
    boxplot_funds = sorted(valid_df["fund_label"].dropna().unique())
    boxplot_data = [valid_df.loc[valid_df["fund_label"] == fund, annualized_col].dropna().values for fund in boxplot_funds]
    if boxplot_data:
        ax.boxplot(boxplot_data, tick_labels=boxplot_funds)
    ax.set_title("Adaptive Annualized Return Distribution by Fund")
    ax.set_xlabel("Fund")
    ax.set_ylabel("Annualized Return (%)")
    ax.grid(True, alpha=0.3)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "allfunds_return_boxplot.png", dpi=150)
    plt.close()

    fig, ax = plt.subplots(figsize=(12, 6))
    fund_sharpe = df.groupby("fund_label")["sharpe"].mean().sort_values(ascending=False)
    x_positions = np.arange(len(fund_sharpe.index))
    ax.bar(x_positions, fund_sharpe.values, color="skyblue", edgecolor="black", width=0.52)
    ax.set_title("Average Sharpe Ratio by Fund")
    ax.set_xlabel("Fund")
    ax.set_ylabel("Sharpe Ratio")
    ax.set_xticks(x_positions)
    ax.set_xticklabels(fund_sharpe.index.tolist(), rotation=45, ha="right")
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(output_dir / "allfunds_sharpe_bar.png", dpi=150)
    plt.close()

    plt.figure(figsize=(12, 6))
    for fund in fund_order[: args.top_n]:
        avg = df[df["fund_label"] == fund].groupby("lookback_years")[annualized_col].mean().dropna()
        if not avg.empty:
            plt.plot(avg.index, avg.values, marker="o", label=fund[:15], linewidth=2)
    plt.xlabel("Lookback Years")
    plt.ylabel("Avg Annualized Return (%)")
    plt.title(f"Annualized Return vs Lookback Years (Top {args.top_n} Funds)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / "allfunds_return_vs_lookback.png", dpi=150)
    plt.close()

    plt.figure(figsize=(12, 6))
    for fund in fund_order[: args.top_n]:
        avg = df[df["fund_label"] == fund].groupby("offset_months")[annualized_col].mean().dropna()
        if not avg.empty:
            plt.plot(avg.index, avg.values, marker="s", label=fund[:15], linewidth=2)
    plt.xlabel("Offset Months")
    plt.ylabel("Avg Annualized Return (%)")
    plt.title(f"Annualized Return vs Offset Months (Top {args.top_n} Funds)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / "allfunds_return_vs_offset.png", dpi=150)
    plt.close()

    pivot = df.pivot_table(values=annualized_col, index="best_ga_generations", columns="best_ga_pop_size", aggfunc="mean")
    if not pivot.empty:
        plt.figure(figsize=(10, 6))
        heatmap = plt.imshow(pivot.values, cmap="RdYlGn", aspect="auto")
        plt.xticks(range(len(pivot.columns)), pivot.columns)
        plt.yticks(range(len(pivot.index)), pivot.index)
        plt.xlabel("Population Size")
        plt.ylabel("Generations")
        plt.title("All Funds: Avg Annualized Return by Pop Size & Generations")
        plt.colorbar(heatmap, label="Avg Annualized Return (%)")
        plt.tight_layout()
        plt.savefig(output_dir / "allfunds_pop_gen_heatmap.png", dpi=150)
        plt.close()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    ax1.hist(df["last_short_ema"].dropna(), bins=20, alpha=0.7, color="blue", edgecolor="black")
    ax1.set_xlabel("Short EMA")
    ax1.set_ylabel("Count")
    ax1.set_title("Short EMA Distribution (All Funds)")
    ax1.grid(True, alpha=0.3)
    ax2.hist(df["last_long_ema"].dropna(), bins=20, alpha=0.7, color="red", edgecolor="black")
    ax2.set_xlabel("Long EMA")
    ax2.set_ylabel("Count")
    ax2.set_title("Long EMA Distribution (All Funds)")
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / "allfunds_ema_dist.png", dpi=150)
    plt.close()

    print("\n=== Best Run per Fund (Highest Annualized Return) ===")
    best_idx = valid_df.groupby("fund_label")[annualized_col].idxmax().dropna().astype(int)
    best_runs = df.loc[best_idx].sort_values(["fund_label", annualized_col], ascending=[True, False])
    if best_runs.empty:
        print("No funds have usable annualized return data.")
    else:
        print(best_runs[["fund_label", annualized_col, "lookback_years", "offset_months", "last_short_ema", "last_long_ema", "last_stop_loss"]].to_string(index=False))

    summary = df.groupby("fund_label").agg({
        annualized_col: ["mean", "std", "min", "max", "count"],
        "sharpe": "mean",
        "max_dd_pct": "mean",
        "lookback_years": "mean",
        "offset_months": "mean",
    }).round(2)
    summary_path = save_csv(summary.reset_index(), resolve_repo_path(args.summary_file))
    print(f"\nSaved summary to {summary_path}")
    print(f"\nGenerated charts in {output_dir}")


if __name__ == "__main__":
    main()
