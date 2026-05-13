import argparse

import matplotlib.pyplot as plt
import pandas as pd

from scripts.common import CHARTS_DIR, TUNINGS_DIR, ensure_dir, resolve_repo_path


def parse_args():
    parser = argparse.ArgumentParser(description="Visualize one fund's parameter sensitivity charts.")
    parser.add_argument(
        "--analysis-file",
        default=str(TUNINGS_DIR / "miieh_analysis.csv"),
        help="Cleaned fund analysis CSV. Relative paths resolve from repo root.",
    )
    parser.add_argument("--output-dir", default=str(CHARTS_DIR), help="Directory for generated charts.")
    parser.add_argument("--fund-label", default="MIIEH", help="Fund label used in chart titles.")
    return parser.parse_args()


def scatter_chart(df, x, y, color, title, output_path):
    plt.figure(figsize=(10, 8))
    scatter = plt.scatter(df[x], df[y], c=df[color], cmap="RdYlGn", s=100, alpha=0.7, edgecolors="black")
    plt.xlabel(x.replace("_", " ").title())
    plt.ylabel(y.replace("_", " ").title())
    plt.title(title)
    plt.colorbar(scatter, label=color.replace("_", " ").title())
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def main():
    args = parse_args()
    analysis_file = resolve_repo_path(args.analysis_file)
    if not analysis_file.exists():
        raise FileNotFoundError(f"Analysis file not found: {analysis_file}")

    df = pd.read_csv(analysis_file)
    numeric_cols = [
        "lookback_years",
        "offset_months",
        "adaptive_return_pct",
        "sharpe",
        "max_dd_pct",
        "excess_return_pct",
        "last_short_ema",
        "last_long_ema",
        "last_stop_loss",
        "last_cooldown",
        "last_drawdown_exit_pct",
        "last_reentry_rebound_pct",
        "last_rsi_oversold",
        "last_rsi_overbought",
        "trade_count",
        "win_rate_pct",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["lookback_years"])

    output_dir = ensure_dir(resolve_repo_path(args.output_dir))
    label = args.fund_label

    print(f"Analyzing {len(df)} {label} runs")
    print(f"Lookback years range: {df['lookback_years'].min()} - {df['lookback_years'].max()}")
    print(f"Offset months range: {df['offset_months'].min()} - {df['offset_months'].max()}")

    plt.style.use("seaborn-v0_8-darkgrid")

    plt.figure(figsize=(12, 6))
    for offset in sorted(df["offset_months"].dropna().unique()):
        subset = df[df["offset_months"] == offset]
        plt.plot(subset["lookback_years"], subset["adaptive_return_pct"], marker="o", label=f"Offset {int(offset)}M", linewidth=2)
    plt.xlabel("Lookback Years")
    plt.ylabel("Adaptive Return (%)")
    plt.title(f"{label}: Adaptive Return vs Lookback Years (by Offset)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_return_vs_lookback.png", dpi=150)
    plt.close()

    plt.figure(figsize=(12, 6))
    for offset in sorted(df["offset_months"].dropna().unique()):
        subset = df[df["offset_months"] == offset]
        plt.plot(subset["lookback_years"], subset["sharpe"], marker="s", label=f"Offset {int(offset)}M", linewidth=2)
    plt.xlabel("Lookback Years")
    plt.ylabel("Sharpe Ratio")
    plt.title(f"{label}: Sharpe Ratio vs Lookback Years (by Offset)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_sharpe_vs_lookback.png", dpi=150)
    plt.close()

    plt.figure(figsize=(12, 6))
    for offset in sorted(df["offset_months"].dropna().unique()):
        subset = df[df["offset_months"] == offset]
        plt.plot(subset["lookback_years"], subset["max_dd_pct"], marker="^", label=f"Offset {int(offset)}M", linewidth=2)
    plt.xlabel("Lookback Years")
    plt.ylabel("Max Drawdown (%)")
    plt.title(f"{label}: Max Drawdown vs Lookback Years (by Offset)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_dd_vs_lookback.png", dpi=150)
    plt.close()

    scatter_chart(df, "last_short_ema", "last_long_ema", "adaptive_return_pct", f"{label}: EMA Parameters vs Adaptive Return", output_dir / f"{label.lower()}_ema_heatmap.png")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    ax1.scatter(df["last_stop_loss"], df["adaptive_return_pct"], c=df["lookback_years"], cmap="viridis", s=80, alpha=0.7)
    ax1.set_xlabel("Stop Loss (%)")
    ax1.set_ylabel("Adaptive Return (%)")
    ax1.set_title(f"{label}: Stop Loss vs Return")
    ax1.grid(True, alpha=0.3)
    ax2.scatter(df["last_drawdown_exit_pct"], df["adaptive_return_pct"], c=df["lookback_years"], cmap="viridis", s=80, alpha=0.7)
    ax2.set_xlabel("Drawdown Exit (%)")
    ax2.set_ylabel("Adaptive Return (%)")
    ax2.set_title(f"{label}: Drawdown Exit vs Return")
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_sl_ddx_vs_return.png", dpi=150)
    plt.close()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    ax1.scatter(df["last_reentry_rebound_pct"], df["adaptive_return_pct"], c=df["lookback_years"], cmap="viridis", s=80, alpha=0.7)
    ax1.set_xlabel("Reentry Rebound (%)")
    ax1.set_ylabel("Adaptive Return (%)")
    ax1.set_title(f"{label}: Reentry Rebound vs Return")
    ax1.grid(True, alpha=0.3)
    ax2.scatter(df["last_cooldown"], df["adaptive_return_pct"], c=df["lookback_years"], cmap="viridis", s=80, alpha=0.7)
    ax2.set_xlabel("Cooldown (periods)")
    ax2.set_ylabel("Adaptive Return (%)")
    ax2.set_title(f"{label}: Cooldown vs Return")
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_rbr_cd_vs_return.png", dpi=150)
    plt.close()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    ax1.scatter(df["last_rsi_oversold"], df["adaptive_return_pct"], c=df["lookback_years"], cmap="viridis", s=80, alpha=0.7)
    ax1.set_xlabel("RSI Oversold")
    ax1.set_ylabel("Adaptive Return (%)")
    ax1.set_title(f"{label}: RSI Oversold vs Return")
    ax1.grid(True, alpha=0.3)
    ax2.scatter(df["last_rsi_overbought"], df["adaptive_return_pct"], c=df["lookback_years"], cmap="viridis", s=80, alpha=0.7)
    ax2.set_xlabel("RSI Overbought")
    ax2.set_ylabel("Adaptive Return (%)")
    ax2.set_title(f"{label}: RSI Overbought vs Return")
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_rsi_vs_return.png", dpi=150)
    plt.close()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    ax1.scatter(df["trade_count"], df["adaptive_return_pct"], c=df["lookback_years"], cmap="viridis", s=80, alpha=0.7)
    ax1.set_xlabel("Trade Count")
    ax1.set_ylabel("Adaptive Return (%)")
    ax1.set_title(f"{label}: Trade Count vs Return")
    ax1.grid(True, alpha=0.3)
    ax2.scatter(df["win_rate_pct"], df["adaptive_return_pct"], c=df["lookback_years"], cmap="viridis", s=80, alpha=0.7)
    ax2.set_xlabel("Win Rate (%)")
    ax2.set_ylabel("Adaptive Return (%)")
    ax2.set_title(f"{label}: Win Rate vs Return")
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_trades_vs_return.png", dpi=150)
    plt.close()

    plt.figure(figsize=(10, 6))
    df.boxplot(column="adaptive_return_pct", by="lookback_years", grid=True, ax=plt.gca())
    plt.title(f"{label}: Adaptive Return Distribution by Lookback Years")
    plt.suptitle("")
    plt.xlabel("Lookback Years")
    plt.ylabel("Adaptive Return (%)")
    plt.tight_layout()
    plt.savefig(output_dir / f"{label.lower()}_return_boxplot.png", dpi=150)
    plt.close()

    print(f"\nGenerated 9 charts in {output_dir}")


if __name__ == "__main__":
    main()
