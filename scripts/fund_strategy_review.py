import argparse
import html
import os
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_HISTORY_FILE = REPO_ROOT / "outputs" / "tunings" / "backtest_run_history.csv"
DEFAULT_REPORT_DIR = REPO_ROOT / "outputs" / "reports"
DEFAULT_CHART_DIR = REPO_ROOT / "outputs" / "charts" / "strategy_review"
FUNDS_DIR = REPO_ROOT / "outputs" / "funds"

NUMERIC_COLUMNS = [
    "lookback_years",
    "offset_months",
    "initial_capital",
    "duration_seconds",
    "duration_minutes",
    "final_portfolio_value",
    "adaptive_return_pct",
    "buy_hold_return_pct",
    "excess_return_pct",
    "sharpe",
    "max_dd_pct",
    "trade_count",
    "win_rate_pct",
    "time_invested_pct",
    "uptrend_cash_pct",
    "missed_upside_after_exit_pct",
    "stop_loss_count",
    "score",
    "best_ga_pop_size",
    "best_ga_generations",
    "best_ga_mutation_rate",
    "best_ga_crossover_rate",
    "last_short_ema",
    "last_long_ema",
    "last_stop_loss",
    "last_cooldown",
    "last_drawdown_exit_pct",
    "last_reentry_rebound_pct",
    "last_rsi_oversold",
    "last_rsi_overbought",
    "last_rsi_period",
    "last_exposure_multiplier",
    "adaptive_annualized_return_pct",
    "buy_hold_annualized_return_pct",
    "excess_annualized_return_pct",
]

DISPLAY_COLUMNS = [
    "fund_label",
    "adaptive_annualized_return_pct",
    "buy_hold_annualized_return_pct",
    "excess_annualized_return_pct",
    "adaptive_return_pct",
    "buy_hold_return_pct",
    "excess_return_pct",
    "sharpe",
    "max_dd_pct",
    "trade_count",
    "win_rate_pct",
    "lookback_years",
    "offset_months",
    "best_ga_pop_size",
    "best_ga_generations",
    "last_short_ema",
    "last_long_ema",
    "last_stop_loss",
    "last_drawdown_exit_pct",
    "last_reentry_rebound_pct",
    "last_rsi_oversold",
    "last_rsi_overbought",
    "score",
    "decision_status",
]

PARAMETER_COLUMNS = [
    "lookback_years",
    "offset_months",
    "best_ga_pop_size",
    "best_ga_generations",
    "last_short_ema",
    "last_long_ema",
    "last_stop_loss",
    "last_drawdown_exit_pct",
    "last_reentry_rebound_pct",
    "last_rsi_oversold",
    "last_rsi_overbought",
    "trade_count",
    "win_rate_pct",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create a review-ready fund strategy analysis dashboard from backtest run history."
    )
    parser.add_argument(
        "--history-file",
        default=None,
        help="Backtest run history CSV to analyze. Defaults to the global history, or the fund-specific history when --fund-label is used and available.",
    )
    parser.add_argument(
        "--fund-label",
        default=None,
        help="Optional fund label to analyze. Writes reports under outputs/funds/<fund_label>/reports by default.",
    )
    parser.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory for generated HTML, markdown, and summary CSV outputs.",
    )
    parser.add_argument(
        "--chart-dir",
        default=str(DEFAULT_CHART_DIR),
        help="Directory for generated chart PNGs.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Rows to keep per leaderboard.",
    )
    return parser.parse_args()


def sanitize_fund_folder_name(fund_label):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(fund_label or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned or "UnknownFund"


def fund_output_dirs(fund_label):
    fund_dir = FUNDS_DIR / sanitize_fund_folder_name(fund_label)
    return {
        "root": fund_dir,
        "tunings": fund_dir / "tunings",
        "reports": fund_dir / "reports",
        "charts": fund_dir / "reports" / "charts",
    }


def fund_run_history_path(fund_label):
    fund_name = sanitize_fund_folder_name(fund_label)
    return fund_output_dirs(fund_name)["tunings"] / f"{fund_name}-backtest_run_history.csv"


def resolve_inputs(args):
    if args.fund_label:
        fund_dirs = fund_output_dirs(args.fund_label)
        default_fund_history = fund_run_history_path(args.fund_label)
        history_file = Path(args.history_file).resolve() if args.history_file else (
            default_fund_history if default_fund_history.exists() else DEFAULT_HISTORY_FILE
        )
        report_dir = Path(args.report_dir).resolve() if args.report_dir != str(DEFAULT_REPORT_DIR) else fund_dirs["reports"].resolve()
        chart_dir = Path(args.chart_dir).resolve() if args.chart_dir != str(DEFAULT_CHART_DIR) else fund_dirs["charts"].resolve()
        return history_file.resolve(), report_dir, chart_dir

    history_file = Path(args.history_file).resolve() if args.history_file else DEFAULT_HISTORY_FILE.resolve()
    return history_file, Path(args.report_dir).resolve(), Path(args.chart_dir).resolve()


def load_history(history_file, fund_label=None):
    if not history_file.exists():
        raise FileNotFoundError(f"Run history not found: {history_file}")

    df = pd.read_csv(history_file)
    df.columns = [col.strip() for col in df.columns]

    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "run_status" in df.columns:
        df = df[df["run_status"].astype(str).str.lower().eq("completed")].copy()

    if fund_label:
        if "fund_label" not in df.columns:
            raise ValueError("--fund-label was supplied, but history has no fund_label column")
        df = df[df["fund_label"].astype(str).eq(str(fund_label))].copy()
        if df.empty:
            raise ValueError(f"No completed rows found for fund_label={fund_label}")

    if "adaptive_return_pct" not in df.columns:
        raise ValueError("Required column missing: adaptive_return_pct")
    if "buy_hold_return_pct" not in df.columns:
        raise ValueError("Required column missing: buy_hold_return_pct")

    df = ensure_annualized_returns(df)
    df = df.dropna(subset=["adaptive_annualized_return_pct", "excess_annualized_return_pct"]).copy()
    df["decision_status"] = np.select(
        [
            (df["adaptive_annualized_return_pct"] > 0) & (df["excess_annualized_return_pct"] > 0),
            (df["adaptive_annualized_return_pct"] > 0) & (df["excess_annualized_return_pct"] <= 0),
        ],
        ["green: adaptive beats buy-and-hold annualized", "amber: positive annualized but trails buy-and-hold"],
        default="red: negative adaptive annualized return",
    )
    return df


def pct(value, digits=2):
    if pd.isna(value):
        return "n/a"
    return f"{value:.{digits}f}%"


def num(value, digits=2):
    if pd.isna(value):
        return "n/a"
    if isinstance(value, (np.integer, int)):
        return str(value)
    if isinstance(value, (np.floating, float)) and float(value).is_integer():
        return str(int(value))
    return f"{value:.{digits}f}"


def safe_text(value):
    if pd.isna(value):
        return ""
    return str(value)


def annualized_return_from_pct(total_return_pct, start_date, end_date):
    if pd.isna(total_return_pct) or pd.isna(start_date) or pd.isna(end_date):
        return np.nan
    try:
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        days = (end_ts - start_ts).days
        growth = 1 + (float(total_return_pct) / 100)
    except (TypeError, ValueError, OverflowError):
        return np.nan
    if days <= 0:
        return np.nan
    if growth <= 0:
        return -100.0
    return (growth ** (365.25 / days) - 1) * 100


def ensure_annualized_returns(df):
    required = [
        "adaptive_annualized_return_pct",
        "buy_hold_annualized_return_pct",
        "excess_annualized_return_pct",
    ]
    for col in required:
        if col not in df.columns:
            df[col] = np.nan

    if not all(col in df.columns for col in ["backtest_start", "backtest_end"]):
        return df

    for total_col, annualized_col in [
        ("adaptive_return_pct", "adaptive_annualized_return_pct"),
        ("buy_hold_return_pct", "buy_hold_annualized_return_pct"),
    ]:
        missing = df[annualized_col].isna()
        if missing.any() and total_col in df.columns:
            df.loc[missing, annualized_col] = df.loc[missing].apply(
                lambda row: annualized_return_from_pct(
                    row.get(total_col),
                    row.get("backtest_start"),
                    row.get("backtest_end"),
                ),
                axis=1,
            )

    missing_excess = df["excess_annualized_return_pct"].isna()
    if missing_excess.any():
        df.loc[missing_excess, "excess_annualized_return_pct"] = (
            df.loc[missing_excess, "adaptive_annualized_return_pct"]
            - df.loc[missing_excess, "buy_hold_annualized_return_pct"]
        )
    return df


def clipped_columns(df, columns):
    present = [col for col in columns if col in df.columns]
    return df[present].copy()


def build_leaderboards(df, top_n):
    boards = []

    definitions = [
        ("best_adaptive_annualized_return", ["adaptive_annualized_return_pct", "sharpe"], [False, False]),
        ("best_excess_annualized_return", ["excess_annualized_return_pct", "adaptive_annualized_return_pct"], [False, False]),
        ("best_risk_adjusted", ["sharpe", "adaptive_annualized_return_pct"], [False, False]),
        ("best_downside_control", ["max_dd_pct", "adaptive_annualized_return_pct"], [True, False]),
        ("best_win_rate", ["win_rate_pct", "adaptive_annualized_return_pct"], [False, False]),
        ("best_score", ["score", "adaptive_annualized_return_pct"], [False, False]),
    ]

    for name, sort_cols, ascending in definitions:
        available_sort_cols = [col for col in sort_cols if col in df.columns]
        if not available_sort_cols:
            continue
        board = df.sort_values(available_sort_cols, ascending=ascending[: len(available_sort_cols)])
        board = clipped_columns(board.head(top_n), DISPLAY_COLUMNS)
        board.insert(0, "leaderboard", name)
        board.insert(1, "rank", range(1, len(board) + 1))
        boards.append(board)

    if not boards:
        return pd.DataFrame()
    return pd.concat(boards, ignore_index=True)


def build_parameter_summary(df):
    summaries = []
    groupings = [
        ("lookback_offset", ["lookback_years", "offset_months"]),
        ("pop_generation", ["best_ga_pop_size", "best_ga_generations"]),
        ("lookback", ["lookback_years"]),
        ("offset", ["offset_months"]),
    ]
    aggregations = {
        "adaptive_annualized_return_pct": ["count", "mean", "median", "max"],
        "excess_annualized_return_pct": ["mean", "max"],
        "adaptive_return_pct": ["mean", "max"],
        "excess_return_pct": ["mean", "max"],
        "sharpe": ["mean", "max"],
        "max_dd_pct": ["mean", "min"],
    }

    for label, group_cols in groupings:
        if not all(col in df.columns for col in group_cols):
            continue
        summary = df.groupby(group_cols).agg(aggregations)
        summary.columns = ["_".join(col).strip("_") for col in summary.columns]
        summary = summary.reset_index()
        summary.insert(0, "grouping", label)
        summaries.append(summary)

    if not summaries:
        return pd.DataFrame()
    return pd.concat(summaries, ignore_index=True, sort=False)


def build_top_quartile_ranges(df):
    cutoff = df["adaptive_annualized_return_pct"].quantile(0.75)
    top = df[df["adaptive_annualized_return_pct"] >= cutoff].copy()
    rows = []
    for col in PARAMETER_COLUMNS:
        if col not in top.columns:
            continue
        rows.append(
            {
                "parameter": col,
                "top_quartile_min": top[col].min(),
                "top_quartile_median": top[col].median(),
                "top_quartile_max": top[col].max(),
                "all_run_min": df[col].min(),
                "all_run_median": df[col].median(),
                "all_run_max": df[col].max(),
            }
        )
    return pd.DataFrame(rows)


def parse_log_metrics(log_file):
    result = {
        "log_exists": False,
        "adaptive_return_pct": np.nan,
        "buy_hold_return_pct": np.nan,
        "excess_return_pct": np.nan,
        "sharpe": np.nan,
        "max_dd_pct": np.nan,
        "win_rate_pct": np.nan,
        "last_trade_signal": "unknown",
        "last_trade_date": "",
        "last_trade_price": np.nan,
        "last_trade_line": "",
    }
    if not log_file:
        return result

    path = Path(str(log_file))
    if not path.exists():
        return result

    result["log_exists"] = True
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "adaptive_return_pct": r"Adaptive Enhanced Strategy Return:\s*([-+]?\d+(?:\.\d+)?)%",
        "buy_hold_return_pct": r"Buy & Hold Return:\s*([-+]?\d+(?:\.\d+)?)%",
        "excess_return_pct": r"Excess Return vs Buy & Hold:\s*([-+]?\d+(?:\.\d+)?)%",
        "sharpe": r"Sharpe Ratio:\s*([-+]?\d+(?:\.\d+)?)",
        "max_dd_pct": r"Max Drawdown:\s*([-+]?\d+(?:\.\d+)?)%",
        "win_rate_pct": r"Win Rate:\s*([-+]?\d+(?:\.\d+)?)%",
    }
    for key, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if matches:
            result[key] = float(matches[-1])

    trade_lines = []
    for line in text.splitlines():
        if re.match(r"^(BUY|SELL|DRAWDOWN_EXIT|STOP_LOSS|TAKE_PROFIT)", line.strip()):
            trade_lines.append(line.strip())

    if trade_lines:
        last = trade_lines[-1]
        result["last_trade_line"] = last
        signal = last.split(":", 1)[0].split(" ", 1)[0]
        result["last_trade_signal"] = "BUY/HOLD invested" if signal == "BUY" else "SELL/CASH"
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", last)
        price_match = re.search(r"Price:\s*([0-9.]+)", last)
        if date_match:
            result["last_trade_date"] = date_match.group(1)
        if price_match:
            result["last_trade_price"] = float(price_match.group(1))

    return result


def cross_check_best_run(best_row):
    parsed = parse_log_metrics(best_row.get("log_file", ""))
    checks = []
    for col in [
        "adaptive_return_pct",
        "buy_hold_return_pct",
        "excess_return_pct",
        "sharpe",
        "max_dd_pct",
        "win_rate_pct",
    ]:
        csv_value = best_row.get(col, np.nan)
        log_value = parsed.get(col, np.nan)
        if pd.isna(csv_value) or pd.isna(log_value):
            status = "missing"
            diff = np.nan
        else:
            diff = abs(float(csv_value) - float(log_value))
            status = "ok" if diff <= 0.05 else "mismatch"
        checks.append(
            {
                "metric": col,
                "csv_value": csv_value,
                "log_value": log_value,
                "absolute_diff": diff,
                "status": status,
            }
        )
    return pd.DataFrame(checks), parsed


def robustness_score(row, df):
    if not all(col in df.columns for col in ["lookback_years", "offset_months"]):
        return np.nan, 0
    lookback = row["lookback_years"]
    offset = row["offset_months"]
    nearby = df[
        (df["lookback_years"].sub(lookback).abs() <= 0.5)
        & (df["offset_months"].sub(offset).abs() <= 3)
    ]
    if nearby.empty:
        return np.nan, 0
    positive_count = int((nearby["adaptive_annualized_return_pct"] > 0).sum())
    median_return = float(nearby["adaptive_annualized_return_pct"].median())
    best_return = float(row["adaptive_annualized_return_pct"])
    isolation_penalty = max(0.0, best_return - median_return)
    robust = median_return - isolation_penalty
    if positive_count <= 1:
        robust -= 5.0
    return robust, len(nearby)


def build_recommended_runs(df, best_row, top_ranges):
    data_file = safe_text(best_row.get("data_file", "data/MIIEH_IndiaEquityRMH_nav_5Y.csv"))
    if data_file.startswith(str(REPO_ROOT)):
        data_file = str(Path(data_file).resolve().relative_to(REPO_ROOT))

    # Keep the first follow-up sweep deliberately narrow around the plan's
    # strongest practical zone instead of letting top-quartile outliers expand it.
    short_min, short_max = 20, 55
    long_min, long_max = 70, 135

    rows = [
        {
            "priority": 1,
            "experiment": "Champion deeper convergence",
            "lookback_years": 2.5,
            "offset_months": 9,
            "pop_gen": "50/50 then 60/60",
            "ema_bounds": f"{short_min}-{short_max} / {long_min}-{long_max}",
            "reason": "Retest the strongest annualized adaptive-return zone with more GA convergence.",
            "command": f"python scripts/backtest-ema-ga10-index.py --data-file {data_file} --lookback-years 2.5 --offset-months 9 --pop_ranges 50 60 --gen_ranges 50 60 --short-ema-bounds {short_min} {short_max} --long-ema-bounds {long_min} {long_max}",
        },
        {
            "priority": 2,
            "experiment": "Neighbour offset stress test",
            "lookback_years": 2.5,
            "offset_months": "6, 9, 12",
            "pop_gen": "50/50",
            "ema_bounds": f"{short_min}-{short_max} / {long_min}-{long_max}",
            "reason": "Check whether the 2.5Y signal survives adjacent retune schedules.",
            "command": f"Run the same command separately with --offset-months 6, 9, and 12 using --pop_ranges 50 --gen_ranges 50.",
        },
        {
            "priority": 3,
            "experiment": "Best excess-return defensive retest",
            "lookback_years": 1.0,
            "offset_months": 3,
            "pop_gen": "50/50",
            "ema_bounds": "20-55 / 70-135",
            "reason": "This area had the least underperformance versus buy-and-hold, but needs return improvement.",
            "command": f"python scripts/backtest-ema-ga10-index.py --data-file {data_file} --lookback-years 1 --offset-months 3 --pop_ranges 50 --gen_ranges 50 --short-ema-bounds 20 55 --long-ema-bounds 70 135",
        },
        {
            "priority": 4,
            "experiment": "RSI lower-overbought retest",
            "lookback_years": 2.5,
            "offset_months": "6, 9, 12",
            "pop_gen": "50/50 or 60/60",
            "ema_bounds": f"{short_min}-{short_max} / {long_min}-{long_max}",
            "reason": "Top-quartile runs cluster around RSI overbought 60-76; the current CLI does not expose RSI bounds.",
            "command": "Expose RSI bounds in the backtest CLI or add a profile override, then retest overbought 60-76 and oversold 20-40.",
        },
    ]
    return pd.DataFrame(rows)


def save_table(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def annotate_heatmap(ax, pivot):
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            value = pivot.iloc[i, j]
            if pd.isna(value):
                continue
            ax.text(j, i, f"{value:.1f}", ha="center", va="center", fontsize=8, color="#111827")


def save_heatmap(df, values, index, columns, title, path, cmap="RdYlGn"):
    if not all(col in df.columns for col in [values, index, columns]):
        return None
    pivot = df.pivot_table(values=values, index=index, columns=columns, aggfunc="mean")
    if pivot.empty:
        return None

    fig, ax = plt.subplots(figsize=(9, 5.5))
    image = ax.imshow(pivot.values, cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([num(v, 1) for v in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([num(v, 1) for v in pivot.index])
    ax.set_xlabel(columns.replace("_", " ").title())
    ax.set_ylabel(index.replace("_", " ").title())
    ax.set_title(title)
    annotate_heatmap(ax, pivot)
    fig.colorbar(image, ax=ax, label=values.replace("_", " ").title())
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def save_scatter(df, x, y, color, title, path, xlabel=None, ylabel=None):
    if not all(col in df.columns for col in [x, y, color]):
        return None
    plot_df = df[[x, y, color]].dropna()
    if plot_df.empty:
        return None

    fig, ax = plt.subplots(figsize=(8, 5.5))
    scatter = ax.scatter(
        plot_df[x],
        plot_df[y],
        c=plot_df[color],
        cmap="RdYlGn",
        s=90,
        alpha=0.78,
        edgecolors="#1f2937",
        linewidths=0.6,
    )
    ax.set_title(title)
    ax.set_xlabel(xlabel or x.replace("_", " ").title())
    ax.set_ylabel(ylabel or y.replace("_", " ").title())
    ax.grid(True, alpha=0.25)
    fig.colorbar(scatter, ax=ax, label=color.replace("_", " ").title())
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def save_top_runs_chart(df, path):
    plot_df = df.sort_values("adaptive_annualized_return_pct", ascending=False).head(8).copy()
    labels = [
        f"{row.lookback_years:g}Y/{int(row.offset_months)}M"
        for row in plot_df.itertuples()
    ]
    x = np.arange(len(plot_df))
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(x - 0.18, plot_df["adaptive_annualized_return_pct"], width=0.36, label="Adaptive annualized", color="#0f766e")
    ax.bar(x + 0.18, plot_df["buy_hold_annualized_return_pct"], width=0.36, label="Buy & hold annualized", color="#64748b")
    ax.axhline(0, color="#111827", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel("Annualized return (%)")
    ax.set_title("Top Adaptive Runs vs Buy-and-Hold (Annualized)")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def create_charts(df, chart_dir):
    chart_dir.mkdir(parents=True, exist_ok=True)
    charts = []
    chart_specs = [
        save_top_runs_chart(df, chart_dir / "strategy_top_runs_vs_buy_hold.png"),
        save_heatmap(
            df,
            "adaptive_annualized_return_pct",
            "lookback_years",
            "offset_months",
            "Annualized Adaptive Return by Lookback and Offset",
            chart_dir / "strategy_lookback_offset_heatmap.png",
        ),
        save_heatmap(
            df,
            "adaptive_annualized_return_pct",
            "best_ga_generations",
            "best_ga_pop_size",
            "Annualized Adaptive Return by GA Population and Generations",
            chart_dir / "strategy_pop_gen_heatmap.png",
        ),
        save_scatter(
            df,
            "last_short_ema",
            "last_long_ema",
            "adaptive_annualized_return_pct",
            "EMA Pair Sensitivity",
            chart_dir / "strategy_ema_scatter.png",
            "Short EMA",
            "Long EMA",
        ),
        save_scatter(
            df,
            "last_rsi_oversold",
            "last_rsi_overbought",
            "adaptive_annualized_return_pct",
            "RSI Guard Sensitivity",
            chart_dir / "strategy_rsi_scatter.png",
            "RSI Oversold",
            "RSI Overbought",
        ),
        save_scatter(
            df,
            "last_stop_loss",
            "last_drawdown_exit_pct",
            "adaptive_annualized_return_pct",
            "Exit Rule Sensitivity",
            chart_dir / "strategy_exit_rules_scatter.png",
            "Stop Loss (%)",
            "Drawdown Exit (%)",
        ),
    ]
    for path in chart_specs:
        if path:
            charts.append(path)
    return charts


def dataframe_to_html(df, max_rows=10, classes=""):
    if df.empty:
        return "<p>No data available.</p>"

    show_df = df.head(max_rows).copy()
    for col in show_df.columns:
        if pd.api.types.is_numeric_dtype(show_df[col]):
            show_df[col] = show_df[col].map(lambda value: "" if pd.isna(value) else f"{value:.3f}".rstrip("0").rstrip("."))
    return show_df.to_html(index=False, escape=True, classes=classes, border=0)


def dataframe_to_markdown(df, max_rows=10):
    if df.empty:
        return "No data available."
    show_df = df.head(max_rows).copy()
    for col in show_df.columns:
        if pd.api.types.is_numeric_dtype(show_df[col]):
            show_df[col] = show_df[col].map(lambda value: "" if pd.isna(value) else f"{value:.3f}".rstrip("0").rstrip("."))
    columns = list(show_df.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in show_df.iterrows():
        lines.append("| " + " | ".join(html.escape(str(row[col])) for col in columns) + " |")
    return "\n".join(lines)


def rel_path(path, base):
    return os.path.relpath(path, base).replace("\\", "/")


def build_html_report(
    df,
    best_row,
    leaderboards,
    parameter_summary,
    top_ranges,
    recommended_runs,
    cross_check,
    log_parse,
    charts,
    report_dir,
    history_file,
):
    status_class = "status-red"
    if str(best_row["decision_status"]).startswith("green"):
        status_class = "status-green"
    elif str(best_row["decision_status"]).startswith("amber"):
        status_class = "status-amber"

    fund_count = df["fund_label"].nunique() if "fund_label" in df.columns else 0
    run_count = len(df)
    best_card = {
        "Fund": safe_text(best_row.get("fund_label", "")),
        "Decision": "Best annualized adaptive candidate, but not superior to buy-and-hold yet",
        "Signal": log_parse.get("last_trade_signal", "unknown"),
        "Last signal date": log_parse.get("last_trade_date", ""),
        "Adaptive annualized": pct(best_row.get("adaptive_annualized_return_pct")),
        "Buy-and-hold annualized": pct(best_row.get("buy_hold_annualized_return_pct")),
        "Excess annualized": pct(best_row.get("excess_annualized_return_pct")),
        "Adaptive total": pct(best_row.get("adaptive_return_pct")),
        "Buy-and-hold total": pct(best_row.get("buy_hold_return_pct")),
        "Excess total": pct(best_row.get("excess_return_pct")),
        "Sharpe": num(best_row.get("sharpe")),
        "Max drawdown": pct(best_row.get("max_dd_pct")),
        "Win rate": pct(best_row.get("win_rate_pct")),
    }

    param_card = {
        "Lookback / Offset": f"{num(best_row.get('lookback_years'), 1)}Y / {num(best_row.get('offset_months'), 0)}M",
        "GA pop/gen": f"{num(best_row.get('best_ga_pop_size'), 0)} / {num(best_row.get('best_ga_generations'), 0)}",
        "EMA short/long": f"{num(best_row.get('last_short_ema'), 0)} / {num(best_row.get('last_long_ema'), 0)}",
        "Stop loss": pct(best_row.get("last_stop_loss")),
        "Drawdown exit": pct(best_row.get("last_drawdown_exit_pct")),
        "Reentry rebound": pct(best_row.get("last_reentry_rebound_pct")),
        "RSI oversold/overbought": f"{num(best_row.get('last_rsi_oversold'), 0)} / {num(best_row.get('last_rsi_overbought'), 0)}",
    }

    chart_html = "\n".join(
        f'<figure><img src="{html.escape(rel_path(chart, report_dir))}" alt="{html.escape(chart.stem)}"><figcaption>{html.escape(chart.stem.replace("_", " ").title())}</figcaption></figure>'
        for chart in charts
    )

    cards_html = "\n".join(
        f"<div><span>{html.escape(k)}</span><strong>{html.escape(str(v))}</strong></div>"
        for k, v in best_card.items()
    )
    params_html = "\n".join(
        f"<div><span>{html.escape(k)}</span><strong>{html.escape(str(v))}</strong></div>"
        for k, v in param_card.items()
    )

    top_adaptive = leaderboards[leaderboards["leaderboard"].eq("best_adaptive_annualized_return")]
    top_excess = leaderboards[leaderboards["leaderboard"].eq("best_excess_annualized_return")]
    top_risk = leaderboards[leaderboards["leaderboard"].eq("best_risk_adjusted")]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fund Strategy Review</title>
  <style>
    :root {{
      --ink: #111827;
      --muted: #64748b;
      --line: #d8dee9;
      --panel: #f8fafc;
      --green: #0f766e;
      --amber: #b45309;
      --red: #b91c1c;
      --blue: #1d4ed8;
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
      padding: 24px 36px 40px;
      max-width: 1380px;
      margin: 0 auto;
    }}
    h1, h2, h3 {{
      margin: 0;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 30px;
      line-height: 1.2;
    }}
    h2 {{
      font-size: 20px;
      margin-top: 34px;
      margin-bottom: 14px;
    }}
    h3 {{
      font-size: 16px;
      margin: 18px 0 10px;
    }}
    p {{
      color: var(--muted);
      line-height: 1.55;
      max-width: 980px;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 18px;
      color: var(--muted);
      font-size: 13px;
      margin-top: 12px;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin-top: 18px;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
    }}
    .card div {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 8px 0;
      border-bottom: 1px solid #e7ebf2;
    }}
    .card div:last-child {{
      border-bottom: 0;
    }}
    .card span {{
      color: var(--muted);
    }}
    .card strong {{
      text-align: right;
    }}
    .badge {{
      display: inline-block;
      padding: 5px 9px;
      border-radius: 999px;
      color: #ffffff;
      font-size: 12px;
      font-weight: 700;
      margin-top: 12px;
    }}
    .status-green {{ background: var(--green); }}
    .status-amber {{ background: var(--amber); }}
    .status-red {{ background: var(--red); }}
    .charts {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
      gap: 18px;
    }}
    figure {{
      margin: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #ffffff;
    }}
    figure img {{
      width: 100%;
      height: auto;
      display: block;
    }}
    figcaption {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 8px;
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
    }}
    th {{
      background: #f1f5f9;
      font-weight: 700;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    code {{
      white-space: pre-wrap;
      color: var(--blue);
    }}
  </style>
</head>
<body>
  <header>
    <h1>Fund Strategy Review</h1>
    <div class="meta">
      <span>Source: {html.escape(str(history_file))}</span>
      <span>Completed runs: {run_count}</span>
      <span>Funds: {fund_count}</span>
    </div>
    <span class="badge {status_class}">{html.escape(str(best_row["decision_status"]))}</span>
  </header>
  <main>
    <section>
      <h2>Executive Decision</h2>
      <p>The best adaptive run is selected by annualized return so unequal backtest windows are compared on the same time basis. It remains a tuning lead unless annualized excess return versus buy-and-hold is positive after risk review.</p>
      <div class="cards">
        <div class="card">{cards_html}</div>
        <div class="card">{params_html}</div>
      </div>
    </section>

    <section>
      <h2>Visual Review</h2>
      <div class="charts">{chart_html}</div>
    </section>

    <section>
      <h2>Leaderboards</h2>
      <h3>Best Adaptive Annualized Return</h3>
      <div class="table-wrap">{dataframe_to_html(top_adaptive, 10)}</div>
      <h3>Best Excess Annualized Return</h3>
      <div class="table-wrap">{dataframe_to_html(top_excess, 10)}</div>
      <h3>Best Risk-Adjusted</h3>
      <div class="table-wrap">{dataframe_to_html(top_risk, 10)}</div>
    </section>

    <section>
      <h2>Parameter Sensitivity</h2>
      <h3>Top-Quartile Parameter Ranges</h3>
      <div class="table-wrap">{dataframe_to_html(top_ranges, 20)}</div>
      <h3>Grouped Performance</h3>
      <div class="table-wrap">{dataframe_to_html(parameter_summary, 20)}</div>
    </section>

    <section>
      <h2>Robustness And Log Cross-Check</h2>
      <p>Best run log exists: {html.escape(str(log_parse.get("log_exists")))}. Last parsed trade line: <code>{html.escape(str(log_parse.get("last_trade_line", "")))}</code></p>
      <div class="table-wrap">{dataframe_to_html(cross_check, 10)}</div>
    </section>

    <section>
      <h2>Recommended Next Runs</h2>
      <div class="table-wrap">{dataframe_to_html(recommended_runs, 10)}</div>
    </section>
  </main>
</body>
</html>
"""


def build_markdown_report(
    df,
    best_row,
    leaderboards,
    parameter_summary,
    top_ranges,
    recommended_runs,
    cross_check,
    log_parse,
    history_file,
):
    top_adaptive = leaderboards[leaderboards["leaderboard"].eq("best_adaptive_annualized_return")]
    top_excess = leaderboards[leaderboards["leaderboard"].eq("best_excess_annualized_return")]
    top_risk = leaderboards[leaderboards["leaderboard"].eq("best_risk_adjusted")]
    robust, nearby_count = robustness_score(best_row, df)
    lines = [
        "# Fund Strategy Review",
        "",
        f"Source: `{history_file}`",
        f"Completed runs: `{len(df)}`",
        f"Funds: `{df['fund_label'].nunique() if 'fund_label' in df.columns else 0}`",
        "",
        "## Executive Decision",
        "",
        "Best annualized adaptive candidate. Use annualized excess return versus buy-and-hold as the apples-to-apples decision metric.",
        "",
        f"- Fund: `{safe_text(best_row.get('fund_label', ''))}`",
        f"- Current signal from best-run log: `{log_parse.get('last_trade_signal', 'unknown')}` on `{log_parse.get('last_trade_date', '')}`",
        f"- Adaptive annualized return: `{pct(best_row.get('adaptive_annualized_return_pct'))}`",
        f"- Buy-and-hold annualized return: `{pct(best_row.get('buy_hold_annualized_return_pct'))}`",
        f"- Excess annualized return: `{pct(best_row.get('excess_annualized_return_pct'))}`",
        f"- Adaptive total return: `{pct(best_row.get('adaptive_return_pct'))}`",
        f"- Buy-and-hold total return: `{pct(best_row.get('buy_hold_return_pct'))}`",
        f"- Excess total return: `{pct(best_row.get('excess_return_pct'))}`",
        f"- Sharpe: `{num(best_row.get('sharpe'))}`",
        f"- Max drawdown: `{pct(best_row.get('max_dd_pct'))}`",
        f"- Win rate: `{pct(best_row.get('win_rate_pct'))}`",
        f"- Robustness score: `{num(robust)}` using `{nearby_count}` nearby runs",
        "",
        "## Current Best Parameters",
        "",
        f"- Lookback / offset: `{num(best_row.get('lookback_years'), 1)}Y / {num(best_row.get('offset_months'), 0)}M`",
        f"- GA pop/gen: `{num(best_row.get('best_ga_pop_size'), 0)} / {num(best_row.get('best_ga_generations'), 0)}`",
        f"- EMA short/long: `{num(best_row.get('last_short_ema'), 0)} / {num(best_row.get('last_long_ema'), 0)}`",
        f"- Stop loss: `{pct(best_row.get('last_stop_loss'))}`",
        f"- Drawdown exit: `{pct(best_row.get('last_drawdown_exit_pct'))}`",
        f"- Reentry rebound: `{pct(best_row.get('last_reentry_rebound_pct'))}`",
        f"- RSI oversold/overbought: `{num(best_row.get('last_rsi_oversold'), 0)} / {num(best_row.get('last_rsi_overbought'), 0)}`",
        "",
        "## Best Adaptive Annualized Return",
        "",
        dataframe_to_markdown(top_adaptive, 10),
        "",
        "## Best Excess Annualized Return",
        "",
        dataframe_to_markdown(top_excess, 10),
        "",
        "## Best Risk-Adjusted",
        "",
        dataframe_to_markdown(top_risk, 10),
        "",
        "## Top-Quartile Parameter Ranges",
        "",
        dataframe_to_markdown(top_ranges, 20),
        "",
        "## Grouped Performance",
        "",
        dataframe_to_markdown(parameter_summary, 20),
        "",
        "## Log Cross-Check",
        "",
        f"Best run log exists: `{log_parse.get('log_exists')}`",
        f"Last parsed trade line: `{log_parse.get('last_trade_line', '')}`",
        "",
        dataframe_to_markdown(cross_check, 10),
        "",
        "## Recommended Next Runs",
        "",
        dataframe_to_markdown(recommended_runs, 10),
        "",
    ]
    return "\n".join(lines)


def main():
    args = parse_args()
    history_file, report_dir, chart_dir = resolve_inputs(args)

    report_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)

    df = load_history(history_file, fund_label=args.fund_label)
    if df.empty:
        raise ValueError("No completed, usable runs found in history file.")

    best_row = df.sort_values(["adaptive_annualized_return_pct", "sharpe"], ascending=[False, False]).iloc[0]
    leaderboards = build_leaderboards(df, args.top_n)
    parameter_summary = build_parameter_summary(df)
    top_ranges = build_top_quartile_ranges(df)
    recommended_runs = build_recommended_runs(df, best_row, top_ranges)
    cross_check, log_parse = cross_check_best_run(best_row)
    charts = create_charts(df, chart_dir)

    save_table(leaderboards, report_dir / "fund_strategy_leaderboards.csv")
    save_table(parameter_summary, report_dir / "fund_strategy_parameter_summary.csv")
    save_table(top_ranges, report_dir / "fund_strategy_top_quartile_ranges.csv")
    save_table(recommended_runs, report_dir / "fund_strategy_recommended_next_runs.csv")
    save_table(cross_check, report_dir / "fund_strategy_best_run_log_cross_check.csv")

    html_report = build_html_report(
        df,
        best_row,
        leaderboards,
        parameter_summary,
        top_ranges,
        recommended_runs,
        cross_check,
        log_parse,
        charts,
        report_dir,
        history_file,
    )
    markdown_report = build_markdown_report(
        df,
        best_row,
        leaderboards,
        parameter_summary,
        top_ranges,
        recommended_runs,
        cross_check,
        log_parse,
        history_file,
    )

    html_path = report_dir / "fund_strategy_review.html"
    md_path = report_dir / "fund_strategy_review.md"
    html_path.write_text(html_report, encoding="utf-8")
    md_path.write_text(markdown_report, encoding="utf-8")

    print(f"Analyzed {len(df)} completed runs from {history_file}")
    print(
        f"Best adaptive run: {safe_text(best_row.get('fund_label'))} "
        f"{pct(best_row.get('adaptive_annualized_return_pct'))} annualized adaptive, "
        f"{pct(best_row.get('excess_annualized_return_pct'))} annualized excess"
    )
    print(f"Current signal from best log: {log_parse.get('last_trade_signal')} {log_parse.get('last_trade_date')}")
    print(f"HTML report: {html_path}")
    print(f"Markdown report: {md_path}")
    print(f"Charts: {chart_dir}")


if __name__ == "__main__":
    main()
