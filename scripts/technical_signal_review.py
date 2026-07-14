#!/usr/bin/env python3
"""
Fast daily technical-signal review from historical EMA-GA tuning results.

This script does not run a new GA search. It selects one balanced fast/best
historical parameter set per fund, reruns the fixed EMA strategy on the latest
data, and estimates forward outcomes after matching historical technical states.
"""

import argparse
import importlib.util
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import (
    CHARTS_DIR,
    DATA_DIR,
    LEGACY_TOTAL_RETURN_METHOD,
    NOT_APPLICABLE_TOTAL_RETURN_METHOD,
    REPORTS_DIR,
    TUNINGS_DIR,
    fund_label_from_data_file,
    infer_total_return_method,
    resolve_repo_path,
    save_csv,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_RUN_HISTORY_FILE = TUNINGS_DIR / "backtest_run_history.csv"
DEFAULT_HORIZONS = "1M:21 3M:63 6M:126 1Y:252"
DEFAULT_CHART_DIR = CHARTS_DIR / "daily_technical"
ACTION_KEYWORDS = (
    "BUY",
    "BUY_TOPUP",
    "SELL",
    "STOP_LOSS",
    "TAKE_PROFIT",
    "DRAWDOWN_EXIT",
    "PARTIAL_DRAWDOWN_EXIT",
)


def load_backtester_module():
    module_path = SCRIPT_DIR / "backtest-ema-ga10-index.py"
    spec = importlib.util.spec_from_file_location("backtest_ema_ga10_index", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load backtester module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bt = load_backtester_module()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate daily fixed-parameter EMA technical signals and forward outcome likelihoods."
    )
    parser.add_argument("--all", action="store_true", help="Analyze all matching local data files.")
    parser.add_argument("--fund-glob", default="*_nav_5Y.csv", help="Data glob used with --all.")
    parser.add_argument("--data-file", default=None, help="Single data CSV to analyze.")
    parser.add_argument("--data-files", nargs="+", default=None, help="Explicit data CSVs to analyze.")
    parser.add_argument("--price-column", default="TotalReturn", help="Investment value column.")
    parser.add_argument("--history-file", default=str(DEFAULT_RUN_HISTORY_FILE), help="Backtest run history CSV.")
    parser.add_argument("--output-dir", default=str(REPORTS_DIR), help="Report output directory.")
    parser.add_argument("--horizons", default=DEFAULT_HORIZONS, help='Horizons as labels and days, e.g. "1M:21 6M:126".')
    parser.add_argument("--primary-horizon", default="6M", help="Headline technical likelihood horizon.")
    parser.add_argument("--upside-target", type=float, default=0.15, help="Upside target as decimal return.")
    parser.add_argument("--downside-risk", type=float, default=-0.08, help="Downside risk threshold as decimal return.")
    parser.add_argument("--min-observations", type=int, default=40, help="Normal confidence observation threshold.")
    parser.add_argument("--initial-capital", type=float, default=10000.0, help="Backtest starting capital.")
    parser.add_argument("--charts", action="store_true", help="Generate fixed-backtest technical PNG charts.")
    parser.add_argument("--chart-dir", default=str(DEFAULT_CHART_DIR), help="Chart output directory.")
    parser.add_argument("--run-id", default=None, help="Optional run id used as a chart subdirectory.")
    parser.add_argument("--validate", action="store_true", help="Validate generated output shape.")
    return parser.parse_args()


def parse_horizons(value):
    horizons = {}
    for part in str(value).split():
        if ":" not in part:
            raise ValueError(f"Invalid horizon token: {part}")
        label, days = part.split(":", 1)
        label = label.strip()
        days = int(days)
        if not label or days <= 0:
            raise ValueError(f"Invalid horizon token: {part}")
        horizons[label] = days
    if not horizons:
        raise ValueError("At least one horizon is required.")
    return horizons


def safe_float(row, key, default=0.0):
    value = row.get(key, default)
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(row, key, default=0):
    return int(round(safe_float(row, key, default)))


def pct_rank(series, higher_is_better=True):
    values = pd.to_numeric(series, errors="coerce")
    if values.notna().sum() <= 1:
        return pd.Series(0.5, index=series.index)
    rank = values.rank(pct=True, ascending=not higher_is_better)
    return rank.fillna(0.5)


def normalize_run_history(path):
    if not path.exists():
        raise FileNotFoundError(f"Run history not found: {path}")
    df = pd.read_csv(path)
    required = [
        "fund_label",
        "data_file",
        "price_column",
        "last_short_ema",
        "last_long_ema",
        "last_stop_loss",
        "last_cooldown",
        "last_drawdown_exit_pct",
        "last_reentry_rebound_pct",
        "duration_seconds",
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Run history is missing required columns: {missing}")

    if "run_status" in df.columns:
        status = df["run_status"].fillna("completed").astype(str).str.lower()
        df = df[status.isin(["completed", "", "nan"])].copy()
    else:
        df = df.copy()

    if "total_return_method" not in df.columns:
        df["total_return_method"] = np.where(
            df["price_column"].astype(str).eq("TotalReturn"),
            LEGACY_TOTAL_RETURN_METHOD,
            NOT_APPLICABLE_TOTAL_RETURN_METHOD,
        )
    else:
        missing_method = df["total_return_method"].fillna("").astype(str).str.strip().eq("")
        df.loc[missing_method, "total_return_method"] = np.where(
            df.loc[missing_method, "price_column"].astype(str).eq("TotalReturn"),
            LEGACY_TOTAL_RETURN_METHOD,
            NOT_APPLICABLE_TOTAL_RETURN_METHOD,
        )

    numeric_cols = [
        "adaptive_annualized_return_pct",
        "excess_annualized_return_pct",
        "adaptive_return_pct",
        "excess_return_pct",
        "sharpe",
        "max_dd_pct",
        "duration_seconds",
        "last_short_ema",
        "last_long_ema",
        "last_stop_loss",
        "last_cooldown",
        "last_drawdown_exit_pct",
        "last_reentry_rebound_pct",
        "last_exposure_multiplier",
        "last_rsi_oversold",
        "last_rsi_overbought",
        "last_rsi_period",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(
        subset=[
            "last_short_ema",
            "last_long_ema",
            "last_stop_loss",
            "last_cooldown",
            "last_drawdown_exit_pct",
            "last_reentry_rebound_pct",
            "duration_seconds",
        ]
    ).copy()

    if "adaptive_annualized_return_pct" not in df.columns:
        df["adaptive_annualized_return_pct"] = np.nan
    if "excess_annualized_return_pct" not in df.columns:
        df["excess_annualized_return_pct"] = np.nan
    df["adaptive_score_source"] = df["adaptive_annualized_return_pct"].fillna(df.get("adaptive_return_pct", 0))
    df["excess_score_source"] = df["excess_annualized_return_pct"].fillna(df.get("excess_return_pct", 0))
    df["sharpe_score_source"] = pd.to_numeric(df.get("sharpe", 0), errors="coerce").fillna(0)
    df["drawdown_score_source"] = pd.to_numeric(df.get("max_dd_pct", 0), errors="coerce").fillna(0)
    df["duration_score_source"] = pd.to_numeric(df.get("duration_seconds", 0), errors="coerce").fillna(0)

    df["balanced_parameter_score"] = (
        0.35 * pct_rank(df["adaptive_score_source"], higher_is_better=True)
        + 0.25 * pct_rank(df["excess_score_source"], higher_is_better=True)
        + 0.15 * pct_rank(df["sharpe_score_source"], higher_is_better=True)
        + 0.15 * pct_rank(df["drawdown_score_source"], higher_is_better=False)
        + 0.10 * pct_rank(df["duration_score_source"], higher_is_better=False)
    )
    return df


def data_prefix_from_file(path):
    return fund_label_from_data_file(path)


def select_params_for_fund(history, fund_label, price_column, total_return_method):
    candidates = history[
        (history["fund_label"].astype(str).eq(fund_label))
        | history["data_file"].astype(str).map(lambda value: data_prefix_from_file(value)).eq(fund_label)
    ].copy()
    if "price_column" in candidates.columns:
        same_price = candidates["price_column"].fillna("").astype(str).eq(price_column)
        if same_price.any():
            candidates = candidates[same_price].copy()
    if "total_return_method" in candidates.columns:
        candidates = candidates[
            candidates["total_return_method"].astype(str).eq(total_return_method)
        ].copy()
    if candidates.empty:
        return None
    if "run_started_at" in candidates.columns:
        candidates["run_started_at_sort"] = pd.to_datetime(candidates["run_started_at"], errors="coerce")
    else:
        candidates["run_started_at_sort"] = pd.NaT
    candidates = candidates.sort_values(
        ["balanced_parameter_score", "run_started_at_sort"],
        ascending=[False, False],
    )
    return candidates.iloc[0]


def load_price_data(path, price_column):
    df = pd.read_csv(path)
    if "Date" not in df.columns:
        raise ValueError(f"{path} does not contain a Date column")
    if price_column not in df.columns:
        raise ValueError(f"{path} does not contain price column {price_column}")
    total_return_method = infer_total_return_method(df, price_column)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df[price_column] = pd.to_numeric(df[price_column], errors="coerce")
    df = df.dropna(subset=["Date", price_column]).sort_values("Date").reset_index(drop=True)
    if df.empty:
        raise ValueError(f"{path} has no valid rows for {price_column}")
    df["NAV"] = df[price_column]
    return df.set_index("Date"), total_return_method


def run_fixed_backtest(df, params, initial_capital):
    strategy_profile = str(params.get("strategy_profile", "generic") or "generic")
    return bt.backtest_enhanced_dual_ema(
        df,
        safe_int(params, "last_short_ema"),
        safe_int(params, "last_long_ema"),
        initial_capital=initial_capital,
        use_rsi_filter=True,
        rsi_oversold=safe_int(params, "last_rsi_oversold", bt.DEFAULT_STRATEGY_PARAMETERS["rsi_oversold"]),
        rsi_overbought=safe_int(params, "last_rsi_overbought", bt.DEFAULT_STRATEGY_PARAMETERS["rsi_overbought"]),
        rsi_period=safe_int(params, "last_rsi_period", bt.DEFAULT_RSI_PERIOD),
        use_trend_filter=False,
        use_stop_loss=True,
        stop_loss_pct=safe_float(params, "last_stop_loss"),
        use_take_profit=False,
        cooldown_period=safe_int(params, "last_cooldown"),
        drawdown_exit_pct=safe_float(params, "last_drawdown_exit_pct"),
        reentry_rebound_pct=safe_float(params, "last_reentry_rebound_pct"),
        start_invested=True,
        debug=False,
        strategy_profile_name=strategy_profile,
        exposure_multiplier=safe_float(params, "last_exposure_multiplier", 1.0),
    )


def build_buy_hold_series(df, initial_capital):
    series, total_return = bt.buy_and_hold_strategy(df, initial_capital=initial_capital)
    if "Date" in df.columns and len(series) == len(df):
        series.index = pd.to_datetime(df["Date"])
    return series, total_return


def parameter_box(params, price_column, initial_capital):
    return (
        "Selected parameters\n"
        f"Price: {price_column} | Capital: {initial_capital:,.0f}\n"
        f"EMA: {safe_int(params, 'last_short_ema')} / {safe_int(params, 'last_long_ema')} | "
        f"SL: {safe_float(params, 'last_stop_loss'):.2f} | CD: {safe_int(params, 'last_cooldown')}\n"
        f"DDX: {safe_float(params, 'last_drawdown_exit_pct'):.2f} | "
        f"RBR: {safe_float(params, 'last_reentry_rebound_pct'):.2f} | "
        f"RSI: {safe_int(params, 'last_rsi_oversold', 30)} / {safe_int(params, 'last_rsi_overbought', 70)}\n"
        f"GA: pop={safe_int(params, 'best_ga_pop_size', 0) or 'n/a'} | "
        f"gen={safe_int(params, 'best_ga_generations', 0) or 'n/a'} | "
        f"mut={safe_float(params, 'best_ga_mutation_rate', np.nan):.2g} | "
        f"cross={safe_float(params, 'best_ga_crossover_rate', np.nan):.2g}"
    )


def chart_x_axis(df_result):
    return pd.to_datetime(df_result["Date"], errors="coerce") if "Date" in df_result.columns else df_result.index


def plot_technical_chart(fund_label, df_result, buy_hold_series, buy_hold_return, metrics, params, price_column, initial_capital, output_path):
    short_ema = safe_int(params, "last_short_ema")
    long_ema = safe_int(params, "last_long_ema")
    rsi_oversold = safe_int(params, "last_rsi_oversold", bt.DEFAULT_STRATEGY_PARAMETERS["rsi_oversold"])
    rsi_overbought = safe_int(params, "last_rsi_overbought", bt.DEFAULT_STRATEGY_PARAMETERS["rsi_overbought"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    x_axis = chart_x_axis(df_result)
    fig = plt.figure(figsize=(15, 12))
    grid = fig.add_gridspec(3, 1, height_ratios=[1.2, 0.8, 0.8])

    ax_price = fig.add_subplot(grid[0])
    ax_price.plot(x_axis, df_result["NAV"], label=price_column, linewidth=1.5, color="black")
    for col, label, color in [
        (f"EMA_{short_ema}", f"Short EMA {short_ema}", "blue"),
        (f"EMA_{long_ema}", f"Long EMA {long_ema}", "red"),
    ]:
        if col in df_result.columns:
            ax_price.plot(x_axis, df_result[col], label=label, color=color, alpha=0.8)
    if "Position" in df_result.columns:
        pos_diff = df_result["Position"].diff().fillna(0)
        buy_signals = df_result[pos_diff > 0]
        sell_signals = df_result[pos_diff < 0]
        if not buy_signals.empty:
            ax_price.scatter(chart_x_axis(buy_signals), buy_signals["NAV"], color="green", marker="^", s=90, label="Buy", zorder=5)
        if not sell_signals.empty:
            ax_price.scatter(chart_x_axis(sell_signals), sell_signals["NAV"], color="red", marker="v", s=90, label="Sell", zorder=5)
    ax_price.set_title(f"{fund_label} Daily Technical Backtest", fontsize=14, fontweight="bold")
    ax_price.text(
        0.01,
        0.98,
        parameter_box(params, price_column, initial_capital),
        transform=ax_price.transAxes,
        va="top",
        ha="left",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "white", "edgecolor": "#cccccc", "alpha": 0.9},
    )
    ax_price.set_ylabel(price_column)
    ax_price.legend()
    ax_price.grid(True, alpha=0.3)
    ax_price.tick_params(axis="x", rotation=45)

    ax_rsi = fig.add_subplot(grid[1])
    ax_rsi.plot(x_axis, df_result["RSI"], label="RSI", color="orange")
    ax_rsi.axhline(y=rsi_oversold, color="green", linestyle="--", alpha=0.7, label=f"Oversold Guard ({rsi_oversold})")
    ax_rsi.axhline(y=rsi_overbought, color="red", linestyle="--", alpha=0.7, label=f"Overbought Guard ({rsi_overbought})")
    ax_rsi.set_title("RSI Indicator", fontsize=12)
    ax_rsi.set_ylabel("RSI")
    ax_rsi.legend()
    ax_rsi.grid(True, alpha=0.3)
    ax_rsi.tick_params(axis="x", rotation=45)

    ax_portfolio = fig.add_subplot(grid[2])
    ax_portfolio.plot(
        x_axis,
        df_result["Portfolio_Value"],
        label=f"Fixed-parameter strategy ({metrics['adaptive_return']:.2f}%)",
        linewidth=2,
        color="green",
    )
    ax_portfolio.plot(
        buy_hold_series.index,
        buy_hold_series,
        label=f"Buy & Hold ({buy_hold_return:.2f}%)",
        linewidth=2,
        color="blue",
    )
    ax_portfolio.set_title("Portfolio Value Comparison", fontsize=14, fontweight="bold")
    ax_portfolio.set_xlabel("Date")
    ax_portfolio.set_ylabel("Portfolio Value")
    ax_portfolio.legend()
    ax_portfolio.grid(True, alpha=0.3)
    ax_portfolio.tick_params(axis="x", rotation=45)

    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def annualized_return_pct(start_value, end_value, start_date, end_date):
    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)
    days = (end_date - start_date).days
    if days <= 0 or start_value <= 0 or end_value <= 0:
        return 0.0
    years = days / 365.25
    return ((end_value / start_value) ** (1 / years) - 1) * 100


def last_trade_marker(df_result):
    if "Position" not in df_result.columns or df_result.empty:
        return None
    position_delta = df_result["Position"].diff().fillna(0)
    trade_rows = df_result[position_delta.abs() > 1e-9]
    if trade_rows.empty:
        return None
    last_index = trade_rows.index[-1]
    last_delta = position_delta.loc[last_index]
    action = "BUY" if last_delta > 0 else "SELL"
    return {
        "action": action,
        "marker": "^" if action == "BUY" else "v",
        "color": "#138a43" if action == "BUY" else "#c9362c",
        "date": df_result.loc[last_index, "Date"] if "Date" in df_result.columns else last_index,
        "value": df_result.loc[last_index, "Portfolio_Value"],
    }


def plot_simple_chart(fund_label, df_result, buy_hold_series, buy_hold_return, metrics, initial_capital, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    x_axis = chart_x_axis(df_result)
    strategy_value = df_result["Portfolio_Value"]

    fig, ax = plt.subplots(figsize=(13, 7))
    ax.plot(x_axis, strategy_value, label="Fixed-parameter strategy", color="#1f8f4d", linewidth=3)
    ax.plot(buy_hold_series.index, buy_hold_series, label="Buy and hold", color="#2f65d9", linewidth=3)
    ax.fill_between(x_axis, strategy_value, initial_capital, color="#1f8f4d", alpha=0.08)

    final_strategy_value = strategy_value.iloc[-1]
    final_buy_hold_value = buy_hold_series.iloc[-1] if len(buy_hold_series) else initial_capital
    start_date = x_axis.iloc[0] if hasattr(x_axis, "iloc") else x_axis[0]
    end_date = x_axis.iloc[-1] if hasattr(x_axis, "iloc") else x_axis[-1]
    strategy_annualized = annualized_return_pct(initial_capital, final_strategy_value, start_date, end_date)
    buy_hold_annualized = annualized_return_pct(initial_capital, final_buy_hold_value, start_date, end_date)
    annotation = (
        f"Starting capital: {initial_capital:,.0f}\n"
        f"Strategy return: {metrics['adaptive_return']:.2f}%\n"
        f"Strategy annualized: {strategy_annualized:.2f}%\n"
        f"Buy & hold return: {buy_hold_return:.2f}%\n"
        f"Buy & hold annualized: {buy_hold_annualized:.2f}%\n"
        f"Extra return: {metrics['excess_return']:.2f}%"
    )
    ax.annotate(
        annotation,
        xy=(0.02, 0.96),
        xycoords="axes fraction",
        va="top",
        ha="left",
        fontsize=12,
        bbox={"boxstyle": "round,pad=0.5", "facecolor": "white", "edgecolor": "#d9d9d9", "alpha": 0.95},
    )

    ax.scatter([x_axis.iloc[-1] if hasattr(x_axis, "iloc") else x_axis[-1]], [final_strategy_value], color="#1f8f4d", s=80, zorder=5)
    if len(buy_hold_series):
        ax.scatter([buy_hold_series.index[-1]], [final_buy_hold_value], color="#2f65d9", s=80, zorder=5)
    marker = last_trade_marker(df_result)
    if marker:
        ax.scatter(
            [marker["date"]],
            [marker["value"]],
            color=marker["color"],
            marker=marker["marker"],
            s=170,
            edgecolors="white",
            linewidths=1.4,
            label=f"Last trade: {marker['action']}",
            zorder=6,
        )
        ax.annotate(
            f"Last {marker['action']}",
            xy=(marker["date"], marker["value"]),
            xytext=(10, 14 if marker["action"] == "BUY" else -24),
            textcoords="offset points",
            fontsize=10,
            color=marker["color"],
            arrowprops={"arrowstyle": "->", "color": marker["color"], "lw": 1},
        )

    ax.set_title(f"{fund_label}: Strategy vs Buy and Hold", fontsize=18, fontweight="bold")
    ax.set_ylabel("Portfolio Value")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.22)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def chart_output_dir(args):
    base_dir = resolve_repo_path(args.chart_dir)
    if args.run_id:
        base_dir = base_dir / args.run_id
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def generate_charts_if_requested(fund_label, price_df, analysis_df, params, metrics, args):
    if not args.charts:
        return "", ""
    chart_dir = chart_output_dir(args)
    technical_chart = chart_dir / f"{fund_label}-daily-technical.png"
    simple_chart = chart_dir / f"{fund_label}-daily-simple.png"
    buy_hold_series, buy_hold_return = build_buy_hold_series(price_df, args.initial_capital)
    plot_technical_chart(
        fund_label,
        analysis_df,
        buy_hold_series,
        buy_hold_return,
        metrics,
        params,
        args.price_column,
        args.initial_capital,
        technical_chart,
    )
    plot_simple_chart(
        fund_label,
        analysis_df,
        buy_hold_series,
        buy_hold_return,
        metrics,
        args.initial_capital,
        simple_chart,
    )
    return str(technical_chart), str(simple_chart)


def action_is_trade(action):
    text = str(action or "").upper()
    return any(keyword in text for keyword in ACTION_KEYWORDS)


def last_trade(trades, decisions):
    if trades:
        action, date, price, value = trades[-1]
        return {
            "Action": action,
            "Date": date,
            "Price": price,
            "Portfolio_Value": value,
        }
    if decisions.empty or "Action" not in decisions.columns:
        return {}
    mask = decisions["Action"].map(action_is_trade)
    if not mask.any():
        return {}
    row = decisions[mask].iloc[-1]
    return row.to_dict()


def technical_state_from_position(position):
    return "BUY/HOLD invested" if float(position or 0) > 1e-6 else "SELL/CASH"


def confidence_from_count(count, min_observations):
    if count >= min_observations:
        return "NORMAL"
    if count > 0:
        return "LOW"
    return "NONE"


def calculate_likelihoods(analysis_df, current_state, horizons, upside_target, downside_risk, min_observations):
    frame = analysis_df.copy()
    if "Date" in frame.columns:
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    else:
        frame["Date"] = pd.to_datetime(frame.index, errors="coerce")
    frame["Technical State"] = np.where(
        pd.to_numeric(frame.get("Position", 0), errors="coerce").fillna(0) > 1e-6,
        "BUY/HOLD invested",
        "SELL/CASH",
    )

    rows = []
    same_state = frame["Technical State"].eq(current_state)
    for label, days in horizons.items():
        forward_return = frame["NAV"].shift(-days) / frame["NAV"] - 1
        sample = forward_return[same_state & forward_return.notna()]
        count = int(sample.shape[0])
        if count:
            expected = float(sample.mean())
            median = float(sample.median())
            positive = float((sample > 0).mean())
            upside = float((sample >= upside_target).mean())
            downside = float((sample <= downside_risk).mean())
        else:
            expected = median = positive = upside = downside = np.nan
        rows.append(
            {
                "Horizon": label,
                "Horizon Days": days,
                "Technical State": current_state,
                "Technical Likelihood Method": "absolute_fixed_threshold",
                "Technical Observation Count": count,
                "Technical Confidence": confidence_from_count(count, min_observations),
                "Technical Probability > 0": positive,
                "Technical Absolute Probability >= Upside Target": upside,
                "Technical Absolute Probability <= Downside Risk": downside,
                "Technical Absolute Expected Forward Return": expected,
                # Compatibility aliases retained for one reporting cycle.
                "Technical Probability >= Upside Target": upside,
                "Technical Probability <= Downside Risk": downside,
                "Technical Expected Forward Return": expected,
                "Technical Median Forward Return": median,
            }
        )
    return rows


def build_unavailable_rows(
    fund_label,
    data_file,
    status,
    message,
    horizons,
    primary_horizon,
    total_return_method="",
):
    detail_rows = []
    for label, days in horizons.items():
        detail_rows.append(
            {
                "Fund Label": fund_label,
                "Data File": str(data_file),
                "Total Return Method": total_return_method,
                "Status": status,
                "Status Message": message,
                "Horizon": label,
                "Horizon Days": days,
                "Technical State": "UNAVAILABLE",
                "Technical Likelihood Method": "absolute_fixed_threshold",
                "Technical Observation Count": 0,
                "Technical Confidence": "NONE",
                "Technical Probability > 0": np.nan,
                "Technical Absolute Probability >= Upside Target": np.nan,
                "Technical Absolute Probability <= Downside Risk": np.nan,
                "Technical Absolute Expected Forward Return": np.nan,
                "Technical Probability >= Upside Target": np.nan,
                "Technical Probability <= Downside Risk": np.nan,
                "Technical Expected Forward Return": np.nan,
                "Technical Chart File": "",
                "Simple Technical Chart File": "",
            }
        )
    summary = {
        "Fund Label": fund_label,
        "Data File": str(data_file),
        "Total Return Method": total_return_method,
        "Status": status,
        "Status Message": message,
        "Horizon": primary_horizon,
        "Technical State": "UNAVAILABLE",
        "Technical Likelihood Method": "absolute_fixed_threshold",
        "Technical Confidence": "NONE",
        "Technical Observation Count": 0,
        "Technical Probability > 0": np.nan,
        "Technical Absolute Probability >= Upside Target": np.nan,
        "Technical Absolute Probability <= Downside Risk": np.nan,
        "Technical Absolute Expected Forward Return": np.nan,
        "Technical Probability >= Upside Target": np.nan,
        "Technical Probability <= Downside Risk": np.nan,
        "Technical Expected Forward Return": np.nan,
        "Technical Chart File": "",
        "Simple Technical Chart File": "",
    }
    return summary, detail_rows


def analyze_file(path, args, history, horizons):
    fund_label = fund_label_from_data_file(path)
    try:
        price_df, total_return_method = load_price_data(path, args.price_column)
    except Exception as exc:
        return build_unavailable_rows(
            fund_label,
            path,
            "DATA_FAILED",
            str(exc),
            horizons,
            args.primary_horizon,
        )

    params = select_params_for_fund(
        history,
        fund_label,
        args.price_column,
        total_return_method,
    )
    if params is None:
        return build_unavailable_rows(
            fund_label,
            path,
            "NO_PARAMETERS",
            f"No completed historical tuning/run row matched this fund and TotalReturn method ({total_return_method}).",
            horizons,
            args.primary_horizon,
            total_return_method,
        )

    try:
        result = run_fixed_backtest(price_df, params, args.initial_capital)
    except Exception as exc:
        return build_unavailable_rows(
            fund_label,
            path,
            "BACKTEST_FAILED",
            str(exc),
            horizons,
            args.primary_horizon,
            total_return_method,
        )

    analysis_df, total_return, num_trades, trades, win_rate, avg_return, decisions_df, sharpe, max_dd = result
    buy_hold_series, buy_hold_return = build_buy_hold_series(price_df, args.initial_capital)
    metrics = {
        "adaptive_return": float(total_return),
        "buy_hold_return": float(buy_hold_return),
        "excess_return": float(total_return - buy_hold_return),
    }
    try:
        technical_chart_file, simple_chart_file = generate_charts_if_requested(
            fund_label,
            price_df,
            analysis_df,
            params,
            metrics,
            args,
        )
    except Exception as exc:
        technical_chart_file = ""
        simple_chart_file = ""
        chart_error = str(exc)
    else:
        chart_error = ""
    latest = decisions_df.iloc[-1].to_dict() if not decisions_df.empty else {}
    latest_date = pd.Timestamp(latest.get("Date")).date().isoformat() if latest.get("Date") is not None else ""
    latest_position = safe_float(latest, "Position", 0.0)
    current_state = technical_state_from_position(latest_position)
    trade = last_trade(trades, decisions_df)
    last_signal_date = ""
    last_signal_action = ""
    last_signal_price = np.nan
    days_since_signal = np.nan
    if trade:
        trade_date = pd.Timestamp(trade.get("Date"))
        latest_ts = pd.Timestamp(latest.get("Date"))
        if not pd.isna(trade_date):
            last_signal_date = trade_date.date().isoformat()
        if not pd.isna(trade_date) and not pd.isna(latest_ts):
            days_since_signal = int((latest_ts - trade_date).days)
        last_signal_action = str(trade.get("Action", ""))
        last_signal_price = safe_float(trade, "Price", np.nan)

    likelihood_rows = calculate_likelihoods(
        analysis_df,
        current_state,
        horizons,
        args.upside_target,
        args.downside_risk,
        args.min_observations,
    )

    base = {
        "Fund Label": fund_label,
        "Data File": str(path),
        "Total Return Method": total_return_method,
        "Status": "OK",
        "Status Message": "",
        "Latest Date": latest_date,
        f"Latest {args.price_column}": safe_float(latest, "Price", np.nan),
        "Technical State": current_state,
        "Current Position": latest_position,
        "Current Exposure": safe_float(latest, "Exposure", latest_position),
        "Current EMA Signal": safe_int(latest, "EMA_Signal", 0),
        "Current Final Signal": safe_int(latest, "Final_Signal", 0),
        "Current RSI": safe_float(latest, "RSI", np.nan),
        "Current Cooldown": safe_int(latest, "Cooldown", 0),
        "Last Signal Action": last_signal_action,
        "Last Signal Date": last_signal_date,
        "Last Signal Price": last_signal_price,
        "Days Since Last Signal": days_since_signal,
        "Selected Short EMA": safe_int(params, "last_short_ema"),
        "Selected Long EMA": safe_int(params, "last_long_ema"),
        "Selected Stop Loss": safe_float(params, "last_stop_loss"),
        "Selected Cooldown": safe_int(params, "last_cooldown"),
        "Selected Drawdown Exit": safe_float(params, "last_drawdown_exit_pct"),
        "Selected Reentry Rebound": safe_float(params, "last_reentry_rebound_pct"),
        "Selected RSI Oversold": safe_int(params, "last_rsi_oversold", bt.DEFAULT_STRATEGY_PARAMETERS["rsi_oversold"]),
        "Selected RSI Overbought": safe_int(params, "last_rsi_overbought", bt.DEFAULT_STRATEGY_PARAMETERS["rsi_overbought"]),
        "Selected Exposure Multiplier": safe_float(params, "last_exposure_multiplier", 1.0),
        "Selected GA Pop Size": safe_int(params, "best_ga_pop_size", 0),
        "Selected GA Generations": safe_int(params, "best_ga_generations", 0),
        "Selected GA Mutation Rate": safe_float(params, "best_ga_mutation_rate", np.nan),
        "Selected GA Crossover Rate": safe_float(params, "best_ga_crossover_rate", np.nan),
        "Selected GA Search Preset": params.get("ga_search_preset", ""),
        "Selected Reuse Tuned Params": params.get("reuse_tuned_params", ""),
        "Parameter Selection Score": safe_float(params, "balanced_parameter_score", np.nan),
        "Source Run ID": params.get("run_id", ""),
        "Source Run Started At": params.get("run_started_at", ""),
        "Source Run Completed At": params.get("run_completed_at", ""),
        "Source Adaptive Annualized Return": safe_float(params, "adaptive_score_source", np.nan),
        "Source Excess Annualized Return": safe_float(params, "excess_score_source", np.nan),
        "Source Sharpe": safe_float(params, "sharpe_score_source", np.nan),
        "Source Max Drawdown": safe_float(params, "drawdown_score_source", np.nan),
        "Source Duration Seconds": safe_float(params, "duration_score_source", np.nan),
        "Fixed Backtest Return": float(total_return),
        "Fixed Backtest Trade Count": int(num_trades),
        "Fixed Backtest Win Rate": float(win_rate),
        "Fixed Backtest Sharpe": float(sharpe),
        "Fixed Backtest Max Drawdown": float(max_dd),
        "Buy Hold Return": float(buy_hold_return),
        "Excess Return": float(total_return - buy_hold_return),
        "Technical Chart File": technical_chart_file,
        "Simple Technical Chart File": simple_chart_file,
        "Chart Status Message": chart_error,
    }

    detail_rows = []
    primary_metrics = None
    for row in likelihood_rows:
        detail_row = {**base, **row}
        detail_rows.append(detail_row)
        if row["Horizon"] == args.primary_horizon:
            primary_metrics = row
    if primary_metrics is None:
        raise ValueError(f"--primary-horizon must be one of: {', '.join(horizons)}")
    summary = {**base, **primary_metrics}
    return summary, detail_rows


def validate_outputs(summary_df, detail_df, expected_funds, horizons):
    errors = []
    missing = sorted(set(expected_funds) - set(summary_df.get("Fund Label", [])))
    if missing:
        errors.append(f"Missing summary rows for funds: {missing}")
    required = [
        "Fund Label",
        "Technical State",
        "Technical Likelihood Method",
        "Technical Absolute Probability >= Upside Target",
        "Technical Absolute Probability <= Downside Risk",
        "Technical Observation Count",
        "Technical Confidence",
    ]
    missing_cols = [col for col in required if col not in summary_df.columns]
    if missing_cols:
        errors.append(f"Summary missing columns: {missing_cols}")
    if len(detail_df) < len(expected_funds) * len(horizons):
        errors.append("Detail output has fewer rows than expected horizons per fund.")
    if errors:
        raise AssertionError("; ".join(errors))


def main():
    args = parse_args()
    horizons = parse_horizons(args.horizons)
    if args.primary_horizon not in horizons:
        raise ValueError(f"--primary-horizon must be one of: {', '.join(horizons)}")
    if args.min_observations <= 0:
        raise ValueError("--min-observations must be positive.")

    if args.data_files:
        data_paths = [resolve_repo_path(path) for path in args.data_files]
    elif args.all:
        data_paths = sorted(DATA_DIR.glob(args.fund_glob))
    elif args.data_file:
        data_paths = [resolve_repo_path(args.data_file)]
    else:
        raise ValueError("Use --data-files, --data-file, or --all.")
    missing_paths = [path for path in data_paths if not path.exists()]
    if missing_paths:
        raise FileNotFoundError(f"Data file(s) not found: {missing_paths}")

    history = normalize_run_history(resolve_repo_path(args.history_file))
    summaries = []
    details = []
    for path in data_paths:
        summary, detail_rows = analyze_file(path, args, history, horizons)
        summaries.append(summary)
        details.extend(detail_rows)

    summary_df = pd.DataFrame(summaries)
    detail_df = pd.DataFrame(details)
    output_dir = resolve_repo_path(args.output_dir)
    summary_path = save_csv(
        summary_df,
        output_dir / "technical_signal_review.csv",
        allow_fallback=False,
    )
    details_path = save_csv(
        detail_df,
        output_dir / "technical_signal_details.csv",
        allow_fallback=False,
    )

    if args.validate:
        expected = [fund_label_from_data_file(path) for path in data_paths]
        validate_outputs(summary_df, detail_df, expected, horizons)

    ok_count = int(summary_df["Status"].eq("OK").sum()) if "Status" in summary_df.columns else 0
    low_count = int(summary_df.get("Technical Confidence", pd.Series(dtype=str)).eq("LOW").sum())
    print(f"Technical signal review complete: {len(summary_df)} funds, {ok_count} OK, {low_count} LOW confidence")
    print(f"Summary: {summary_path}")
    print(f"Details: {details_path}")


if __name__ == "__main__":
    main()
