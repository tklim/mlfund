import argparse
import html
import importlib.util
import os
import re
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from common import fund_label_from_data_file

# DO NOT REMOVE: GOAL: To identify best performing result for each fund so that it can be used for future decision making. Review past tuning history results from backtest_run_history.csv, identify the best performing result (annualize excess) for each fund, capture the key info into ga_tuning_summary_XXXXXX.csv, and then generate final-simple*png and final-technical*png chart to visually display the best performer.


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUTS_DIR = REPO_ROOT / "outputs"
LOGS_DIR = OUTPUTS_DIR / "logs"
CHARTS_DIR = OUTPUTS_DIR / "charts"
TUNINGS_DIR = OUTPUTS_DIR / "tunings"
REPORTS_DIR = OUTPUTS_DIR / "reports"
DEFAULT_RUN_HISTORY_FILE = TUNINGS_DIR / "backtest_run_history.csv"


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
        description="Run final fixed-parameter backtests from the best historical backtest runs."
    )
    parser.add_argument(
        "--fund-label",
        help="Optional fund label to run, for example MAKGCF_GreaterChina.",
    )
    parser.add_argument(
        "--summary-file",
        default=str(DEFAULT_RUN_HISTORY_FILE),
        help=f"Backtest run history CSV (default: {DEFAULT_RUN_HISTORY_FILE})",
    )
    parser.add_argument(
        "--data-file",
        help="Optional data CSV override. Use with --fund-label for a single-fund run.",
    )
    parser.add_argument(
        "--price-column",
        default=None,
        help="CSV price column override. Defaults to the selected run-history row's price_column.",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=10000,
        help="Starting capital for the final backtest (default: 10000).",
    )
    parser.add_argument(
        "--top-funds",
        type=int,
        default=0,
        help="Number of top funds to chart after ranking by excess annualized return. Use 0 for all funds (default: 0, meaning all funds).",
    )
    parser.add_argument(
        "--leaderboard-only",
        action="store_true",
        help=(
            "Generate the historical excess-annualized-return leaderboard from run history "
            "without replaying the selected backtests."
        ),
    )
    return parser.parse_args()


def ensure_output_dirs():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    TUNINGS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def safe_float(row, key, default=0.0):
    value = row.get(key, default)
    if pd.isna(value):
        return default
    return float(value)


def safe_int(row, key, default=0):
    return int(round(safe_float(row, key, default)))


def annualized_return_from_pct(total_return_pct, start_date, end_date):
    if start_date is None or end_date is None:
        return 0.0
    try:
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        if pd.isna(start_ts) or pd.isna(end_ts):
            return 0.0
        days = (end_ts - start_ts).days
        growth = 1 + (float(total_return_pct) / 100)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if days <= 0:
        return 0.0
    if growth <= 0:
        return -100.0
    return (growth ** (365.25 / days) - 1) * 100


def fill_annualized_column(df, target_col, total_return_col):
    if target_col in df.columns:
        annualized = pd.to_numeric(df[target_col], errors="coerce")
    else:
        annualized = pd.Series(np.nan, index=df.index)

    fallback = df.apply(
        lambda row: annualized_return_from_pct(
            row.get(total_return_col, 0.0),
            row.get("backtest_start", row.get("data_start", None)),
            row.get("backtest_end", row.get("data_end", None)),
        ),
        axis=1,
    )
    return annualized.fillna(fallback)


def normalize_run_history(run_history_df):
    required = [
        "fund_label",
        "data_file",
        "adaptive_return_pct",
        "last_short_ema",
        "last_long_ema",
        "last_stop_loss",
        "last_cooldown",
        "last_drawdown_exit_pct",
        "last_reentry_rebound_pct",
        "last_exposure_multiplier",
    ]
    missing = [col for col in required if col not in run_history_df.columns]
    if missing:
        raise ValueError(f"Run history file is missing required columns: {missing}")

    df = run_history_df.copy()
    if "run_status" in df.columns:
        status = df["run_status"].fillna("completed").astype(str).str.lower()
        df = df[status.isin(["completed", "nan", ""])]

    for col in [
        "adaptive_return_pct",
        "last_short_ema",
        "last_long_ema",
        "last_stop_loss",
        "last_cooldown",
        "last_drawdown_exit_pct",
        "last_reentry_rebound_pct",
        "last_exposure_multiplier",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(
        subset=[
            "adaptive_return_pct",
            "last_short_ema",
            "last_long_ema",
            "last_stop_loss",
            "last_cooldown",
            "last_drawdown_exit_pct",
            "last_reentry_rebound_pct",
        ]
    )

    df["source_data_file"] = df["data_file"]
    df["source_run_id"] = df.get("run_id", "")
    df["source_run_started_at"] = df.get("run_started_at", "")
    df["source_adaptive_return_pct"] = df["adaptive_return_pct"]
    df["source_buy_hold_return_pct"] = pd.to_numeric(df.get("buy_hold_return_pct", 0), errors="coerce")
    df["source_excess_return_pct"] = pd.to_numeric(df.get("excess_return_pct", 0), errors="coerce")
    df["source_adaptive_annualized_return_pct"] = fill_annualized_column(
        df, "adaptive_annualized_return_pct", "adaptive_return_pct"
    )
    df["source_buy_hold_annualized_return_pct"] = fill_annualized_column(
        df, "buy_hold_annualized_return_pct", "buy_hold_return_pct"
    )
    if "excess_annualized_return_pct" in df.columns:
        df["source_excess_annualized_return_pct"] = pd.to_numeric(
            df["excess_annualized_return_pct"], errors="coerce"
        )
    else:
        df["source_excess_annualized_return_pct"] = (
            df["source_adaptive_annualized_return_pct"] - df["source_buy_hold_annualized_return_pct"]
        )
    df["source_excess_annualized_return_pct"] = df["source_excess_annualized_return_pct"].fillna(
        df["source_adaptive_annualized_return_pct"] - df["source_buy_hold_annualized_return_pct"]
    )
    df["source_sharpe"] = pd.to_numeric(df.get("sharpe", 0), errors="coerce")
    df["source_max_dd_pct"] = pd.to_numeric(df.get("max_dd_pct", 0), errors="coerce")

    df["short_ema"] = df["last_short_ema"]
    df["long_ema"] = df["last_long_ema"]
    df["stop_loss"] = df["last_stop_loss"]
    df["cooldown"] = df["last_cooldown"]
    df["drawdown_exit_pct"] = df["last_drawdown_exit_pct"]
    df["reentry_rebound_pct"] = df["last_reentry_rebound_pct"]
    df["exposure_multiplier"] = df["last_exposure_multiplier"].fillna(1.0)

    if "last_rsi_oversold" in df.columns:
        df["rsi_oversold"] = pd.to_numeric(df["last_rsi_oversold"], errors="coerce")
    else:
        df["rsi_oversold"] = np.nan
    if "last_rsi_overbought" in df.columns:
        df["rsi_overbought"] = pd.to_numeric(df["last_rsi_overbought"], errors="coerce")
    else:
        df["rsi_overbought"] = np.nan
    df["rsi_oversold"] = df["rsi_oversold"].fillna(bt.DEFAULT_STRATEGY_PARAMETERS["rsi_oversold"])
    df["rsi_overbought"] = df["rsi_overbought"].fillna(bt.DEFAULT_STRATEGY_PARAMETERS["rsi_overbought"])
    if "price_column" not in df.columns:
        df["price_column"] = "TotalReturn"
    if "strategy_profile" not in df.columns:
        df["strategy_profile"] = "generic"
    df["canonical_fund_label"] = df.apply(
        lambda row: data_prefix_from_path(row.get("data_file", "")) or row.get("fund_label", ""),
        axis=1,
    )
    return df


def data_prefix_from_path(path):
    if not str(path).strip():
        return None
    return fund_label_from_data_file(path)


def select_best_run_rows(run_history_df, fund_label=None, top_funds=2):
    if fund_label:
        run_history_df = run_history_df[
            (run_history_df["fund_label"] == fund_label)
            | (run_history_df["canonical_fund_label"] == fund_label)
        ].copy()
        if run_history_df.empty:
            raise ValueError(f"No run-history rows found for fund label: {fund_label}")

    if "run_started_at" in run_history_df.columns:
        run_history_df["run_started_at_sort"] = pd.to_datetime(run_history_df["run_started_at"], errors="coerce")
    else:
        run_history_df["run_started_at_sort"] = pd.NaT

    sorted_runs = run_history_df.sort_values(
        ["source_excess_annualized_return_pct", "run_started_at_sort"],
        ascending=[False, False],
    )
    rank1 = sorted_runs.groupby("canonical_fund_label", sort=False, as_index=False).head(1).reset_index(drop=True)
    # Exclude the fund only after finding its actual leader. Filtering zero rows
    # before grouping could incorrectly promote a lower, negative run.
    leader_values = pd.to_numeric(rank1["source_excess_annualized_return_pct"], errors="coerce")
    rank1 = rank1[leader_values.notna() & leader_values.ne(0)].reset_index(drop=True)
    if not fund_label and top_funds and top_funds > 0:
        rank1 = rank1.head(top_funds).reset_index(drop=True)
    return rank1


def nav_years_from_path(path):
    match = re.search(r"_nav_(\d+)Y\.csv$", path.name, re.IGNORECASE)
    return int(match.group(1)) if match else -1


def choose_data_file(row, data_file=None):
    warning = None

    if data_file:
        path = Path(data_file)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path, warning

    fund_label = row["fund_label"]
    source_data_file = row.get("source_data_file", "")
    source_path = Path(str(source_data_file)) if str(source_data_file).strip() else None

    if source_path and source_path.exists():
        return source_path, warning

    source_filename = source_path.name if source_path else None
    if source_filename:
        local_source_path = DATA_DIR / source_filename
        if local_source_path.exists():
            return local_source_path, warning

    if source_path:
        warning = f"Source data file not found: {source_path}. Trying to find matching file..."

    source_years = nav_years_from_path(source_path) if source_path else -1

    candidates = sorted(DATA_DIR.glob(f"{fund_label}_nav_*Y.csv"))
    source_prefix = data_prefix_from_path(source_data_file) if str(source_data_file).strip() else None

    if not candidates and source_prefix:
        candidates = sorted(DATA_DIR.glob(f"{source_prefix}_nav_*Y.csv"))
    if not candidates:
        return None, warning

    if source_years > 0:
        matching = [c for c in candidates if nav_years_from_path(c) == source_years]
        if matching:
            selected = max(matching, key=lambda p: p.stat().st_mtime)
            if warning:
                warning += f" Using {selected.name} (matching {source_years}Y)."
            return selected, warning
        else:
            warning = f"No {source_years}Y file found. Available: {[c.name for c in candidates]}. Using closest match..."

    selected = max(candidates, key=lambda path: (nav_years_from_path(path), path.stat().st_mtime))
    if warning:
        warning += f" Using {selected.name}."
    return selected, warning


def load_price_data(csv_path, price_column):
    df = pd.read_csv(csv_path)
    if "Date" not in df.columns:
        raise ValueError(f"{csv_path} does not contain a Date column")
    if price_column not in df.columns:
        raise ValueError(f"{csv_path} does not contain price column {price_column}")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df[price_column] = pd.to_numeric(df[price_column], errors="coerce")
    df = df.dropna(subset=["Date", price_column]).sort_values("Date").reset_index(drop=True)
    if df.empty:
        raise ValueError(f"{csv_path} has no valid rows for {price_column}")

    df["NAV"] = df[price_column]
    df = df.set_index("Date")
    return df


def run_fixed_backtest(df, params, initial_capital, strategy_profile):
    return bt.backtest_enhanced_dual_ema(
        df,
        safe_int(params, "short_ema"),
        safe_int(params, "long_ema"),
        initial_capital=initial_capital,
        use_rsi_filter=True,
        rsi_oversold=safe_int(params, "rsi_oversold", bt.DEFAULT_STRATEGY_PARAMETERS["rsi_oversold"]),
        rsi_overbought=safe_int(params, "rsi_overbought", bt.DEFAULT_STRATEGY_PARAMETERS["rsi_overbought"]),
        rsi_period=bt.DEFAULT_RSI_PERIOD,
        use_trend_filter=False,
        use_stop_loss=True,
        stop_loss_pct=safe_float(params, "stop_loss"),
        use_take_profit=False,
        cooldown_period=safe_int(params, "cooldown"),
        drawdown_exit_pct=safe_float(params, "drawdown_exit_pct"),
        reentry_rebound_pct=safe_float(params, "reentry_rebound_pct"),
        start_invested=True,
        debug=False,
        strategy_profile_name=strategy_profile,
        exposure_multiplier=safe_float(params, "exposure_multiplier", 1.0),
    )


def build_buy_hold_series(df, initial_capital):
    series, total_return = bt.buy_and_hold_strategy(df, initial_capital=initial_capital)
    if "Date" in df.columns and len(series) == len(df):
        series.index = pd.to_datetime(df["Date"])
    return series, total_return


def current_position_context(df_result):
    """Return the ending signal and last trade date from a completed replay."""
    if df_result is None or df_result.empty or "Position" not in df_result.columns:
        return "unknown", ""
    positions = pd.to_numeric(df_result["Position"], errors="coerce").fillna(0.0)
    signal = "BUY/HOLD invested" if float(positions.iloc[-1]) > 1e-6 else "SELL/CASH"
    position_changes = positions.diff().abs() > 1e-9
    if not position_changes.any():
        return signal, ""
    last_trade_row = df_result.loc[position_changes].iloc[-1]
    last_trade_value = last_trade_row.get("Date", last_trade_row.name)
    return signal, pd.Timestamp(last_trade_value).strftime("%Y-%m-%d")


def format_final_parameter_box(params, price_column, initial_capital):
    ga_pop = params.get("best_ga_pop_size", "")
    ga_gen = params.get("best_ga_generations", "")
    ga_mut = params.get("best_ga_mutation_rate", "")
    ga_cross = params.get("best_ga_crossover_rate", "")
    if pd.isna(ga_pop):
        ga_pop = ""
    if pd.isna(ga_gen):
        ga_gen = ""
    if pd.isna(ga_mut):
        ga_mut = ""
    if pd.isna(ga_cross):
        ga_cross = ""
    ga_line = (
        f"GA: pop={ga_pop or 'n/a'} | gen={ga_gen or 'n/a'} | "
        f"mut={ga_mut or 'n/a'} | cross={ga_cross or 'n/a'}"
    )
    return (
        "Configured\n"
        f"Price: {price_column} | Initial capital: {initial_capital:,.0f}\n"
        f"Source adaptive: {safe_float(params, 'source_adaptive_return_pct', 0.0):.2f}% | "
        f"Source excess: {safe_float(params, 'source_excess_return_pct', 0.0):.2f}%\n"
        f"Source annualized: {safe_float(params, 'source_adaptive_annualized_return_pct', 0.0):.2f}% | "
        f"Source ann. excess: {safe_float(params, 'source_excess_annualized_return_pct', 0.0):.2f}%\n"
        f"{ga_line}\n\n"
        "Best parameters\n"
        f"EMA: {safe_int(params, 'short_ema')} / {safe_int(params, 'long_ema')} | "
        f"SL: {safe_float(params, 'stop_loss'):.2f} | CD: {safe_int(params, 'cooldown')}\n"
        f"DDX: {safe_float(params, 'drawdown_exit_pct'):.2f} | "
        f"RBR: {safe_float(params, 'reentry_rebound_pct'):.2f} | "
        f"RSI: {safe_int(params, 'rsi_oversold', 30)} / {safe_int(params, 'rsi_overbought', 70)} | "
        f"EXP: {safe_float(params, 'exposure_multiplier', 1.0):.2f}x"
    )


def plot_technical_chart(
    fund_label,
    df_result,
    buy_hold_series,
    buy_hold_return,
    metrics,
    params,
    price_column,
    initial_capital,
    output_path,
    chart_context_label,
):
    short_ema = safe_int(params, "short_ema")
    long_ema = safe_int(params, "long_ema")
    rsi_oversold = safe_int(params, "rsi_oversold", bt.DEFAULT_STRATEGY_PARAMETERS["rsi_oversold"])
    rsi_overbought = safe_int(params, "rsi_overbought", bt.DEFAULT_STRATEGY_PARAMETERS["rsi_overbought"])
    chart_last_data_date = bt.last_available_data_date(df_result)
    chart_generated_at = datetime.now()

    fig = plt.figure(figsize=(15, 12))
    grid = fig.add_gridspec(3, 1, height_ratios=[1.2, 0.8, 0.8])

    plt.subplot(grid[0])
    x_axis = df_result["Date"] if "Date" in df_result.columns else df_result.index
    plt.plot(x_axis, df_result["NAV"], label=price_column, linewidth=1.5, color="black")
    if f"EMA_{short_ema}" in df_result.columns:
        plt.plot(x_axis, df_result[f"EMA_{short_ema}"], label=f"Short EMA {short_ema}", color="blue", alpha=0.8)
    if f"EMA_{long_ema}" in df_result.columns:
        plt.plot(x_axis, df_result[f"EMA_{long_ema}"], label=f"Long EMA {long_ema}", color="red", alpha=0.8)

    if "Position" in df_result.columns:
        pos_diff = df_result["Position"].diff().fillna(0)
        buy_signals = df_result[pos_diff > 0]
        sell_signals = df_result[pos_diff < 0]
        if not buy_signals.empty:
            plt.scatter(
                buy_signals["Date"] if "Date" in buy_signals.columns else buy_signals.index,
                buy_signals["NAV"],
                color="green",
                marker="^",
                s=90,
                label="Buy",
                zorder=5,
            )
        if not sell_signals.empty:
            plt.scatter(
                sell_signals["Date"] if "Date" in sell_signals.columns else sell_signals.index,
                sell_signals["NAV"],
                color="red",
                marker="v",
                s=90,
                label="Sell",
                zorder=5,
            )

    bt.set_chart_title(
        plt.gca(),
        f"{fund_label} Final Technical Backtest",
        chart_last_data_date,
        fontsize=14,
        fontweight="bold",
        context_label=chart_context_label,
        generated_at=chart_generated_at,
    )
    plt.gca().text(
        0.01,
        0.98,
        format_final_parameter_box(params, price_column, initial_capital),
        transform=plt.gca().transAxes,
        va="top",
        ha="left",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "white", "edgecolor": "#cccccc", "alpha": 0.9},
    )
    plt.ylabel(price_column)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)

    plt.subplot(grid[1])
    plt.plot(x_axis, df_result["RSI"], label="RSI", color="orange")
    plt.axhline(y=rsi_oversold, color="green", linestyle="--", alpha=0.7, label=f"Oversold Guard ({rsi_oversold})")
    plt.axhline(y=rsi_overbought, color="red", linestyle="--", alpha=0.7, label=f"Overbought Guard ({rsi_overbought})")
    bt.set_chart_title(
        plt.gca(), "RSI Indicator", chart_last_data_date, fontsize=12, context_label=chart_context_label,
        generated_at=chart_generated_at,
    )
    plt.ylabel("RSI")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)

    plt.subplot(grid[2])
    plt.plot(
        x_axis,
        df_result["Portfolio_Value"],
        label=f"Best-Parameter Strategy ({metrics['adaptive_return']:.2f}%)",
        linewidth=2,
        color="green",
    )
    bh_x = buy_hold_series.index
    plt.plot(
        bh_x,
        buy_hold_series,
        label=f"Buy & Hold ({buy_hold_return:.2f}%)",
        linewidth=2,
        color="blue",
    )
    bt.set_chart_title(
        plt.gca(),
        "Portfolio Value Comparison",
        chart_last_data_date,
        fontsize=14,
        fontweight="bold",
        context_label=chart_context_label,
        generated_at=chart_generated_at,
    )
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def annualized_return_pct(start_value, end_value, start_date, end_date):
    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)
    days = (end_date - start_date).days
    if days <= 0 or start_value <= 0 or end_value <= 0:
        return 0.0
    years = days / 365.25
    return ((end_value / start_value) ** (1 / years) - 1) * 100


def last_trade_marker(df_result):
    if "Position" not in df_result.columns or len(df_result) == 0:
        return None

    position_delta = df_result["Position"].diff().fillna(0)
    trade_rows = df_result[position_delta.abs() > 1e-9]
    if trade_rows.empty:
        return None

    last_index = trade_rows.index[-1]
    last_delta = position_delta.loc[last_index]
    action = "BUY" if last_delta > 0 else "SELL"
    marker = "^" if action == "BUY" else "v"
    color = "#138a43" if action == "BUY" else "#c9362c"
    return {
        "action": action,
        "marker": marker,
        "color": color,
        "date": df_result.loc[last_index, "Date"] if "Date" in df_result.columns else last_index,
        "value": df_result.loc[last_index, "Portfolio_Value"],
    }


def plot_simple_chart(fund_label, df_result, buy_hold_series, buy_hold_return, metrics, initial_capital, output_path, chart_context_label):
    x_axis = df_result["Date"] if "Date" in df_result.columns else df_result.index
    strategy_value = df_result["Portfolio_Value"]
    chart_last_data_date = bt.last_available_data_date(df_result)

    plt.figure(figsize=(13, 7))
    plt.plot(x_axis, strategy_value, label="Best-parameter strategy", color="#1f8f4d", linewidth=3)
    plt.plot(buy_hold_series.index, buy_hold_series, label="Buy and hold", color="#2f65d9", linewidth=3)
    plt.fill_between(x_axis, strategy_value, initial_capital, color="#1f8f4d", alpha=0.08)

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
    plt.annotate(
        annotation,
        xy=(0.02, 0.96),
        xycoords="axes fraction",
        va="top",
        ha="left",
        fontsize=12,
        bbox={"boxstyle": "round,pad=0.5", "facecolor": "white", "edgecolor": "#d9d9d9", "alpha": 0.95},
    )

    last_x = x_axis.iloc[-1] if hasattr(x_axis, "iloc") else x_axis[-1]
    plt.scatter([last_x], [final_strategy_value], color="#1f8f4d", s=80, zorder=5)
    plt.scatter([buy_hold_series.index[-1]], [final_buy_hold_value], color="#2f65d9", s=80, zorder=5)
    marker = last_trade_marker(df_result)
    if marker:
        plt.scatter(
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
        plt.annotate(
            f"Last {marker['action']}",
            xy=(marker["date"], marker["value"]),
            xytext=(10, 14 if marker["action"] == "BUY" else -24),
            textcoords="offset points",
            fontsize=10,
            color=marker["color"],
            arrowprops={"arrowstyle": "->", "color": marker["color"], "lw": 1},
        )
    bt.set_chart_title(
        plt.gca(),
        f"{fund_label}: Strategy vs Buy and Hold",
        chart_last_data_date,
        fontsize=18,
        fontweight="bold",
        context_label=chart_context_label,
    )
    plt.ylabel("Portfolio Value")
    plt.legend(loc="lower right")
    plt.grid(True, alpha=0.22)
    plt.xticks(rotation=30)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def write_log(log_path, lines):
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")


def output_label_for_data_file(data_file, fallback_label):
    return data_prefix_from_path(data_file) or fallback_label


def run_one_fund(row, args, run_timestamp):
    source_fund_label = row["fund_label"]
    data_file, file_warning = choose_data_file(row, args.data_file)
    if file_warning:
        print(f"WARNING: {file_warning}")
    if data_file is None:
        message = f"Skipping {source_fund_label}: no matching data CSV found"
        print(message)
        return {
            "fund_label": source_fund_label,
            "status": "skipped_no_data_file",
            "message": message,
        }
    if not data_file.exists():
        message = f"Skipping {source_fund_label}: data file not found: {data_file}"
        print(message)
        return {
            "fund_label": source_fund_label,
            "status": "skipped_no_data_file",
            "data_file": str(data_file),
            "message": message,
        }

    fund_label = output_label_for_data_file(data_file, source_fund_label)
    started_at = datetime.now()
    formatted = started_at.strftime("%Y%m%d_%H%M%S")
    chart_stamp = started_at.strftime("%Y%m%d-%H%M%S")
    log_path = LOGS_DIR / f"{fund_label}-final-bestparams-{formatted}.txt"
    technical_chart = CHARTS_DIR / f"{fund_label}-final-technical-{chart_stamp}.png"
    simple_chart = CHARTS_DIR / f"{fund_label}-final-simple-{chart_stamp}.png"
    latest_chart = CHARTS_DIR / f"{fund_label}-final-latest-{chart_stamp}.png"

    original_chart_file = row.get("chart_file", "")
    use_original_chart = original_chart_file and Path(original_chart_file).exists()

    strategy_profile = row.get("strategy_profile", "generic")
    if pd.isna(strategy_profile):
        strategy_profile = "generic"
    price_column = args.price_column or row.get("price_column", "TotalReturn")
    if pd.notna(price_column) and str(price_column).strip():
        pass
    else:
        price_column = "TotalReturn"

    df = load_price_data(data_file, price_column)
    df_full = df.copy()
    backtest_start = row.get("backtest_start", "")
    backtest_end = row.get("backtest_end", "")
    if pd.notna(backtest_start) and str(backtest_start).strip():
        start_date = pd.to_datetime(backtest_start)
        df = df.loc[start_date:]
    if pd.notna(backtest_end) and str(backtest_end).strip():
        end_date = pd.to_datetime(backtest_end)
        df = df.loc[:end_date]

    result = run_fixed_backtest(df, row, args.initial_capital, strategy_profile)

    result_latest = run_fixed_backtest(df_full, row, args.initial_capital, strategy_profile)
    df_result_latest, total_return_latest, num_trades_latest, trades_latest, win_rate_latest, _, _, _, _ = result_latest
    buy_hold_series_latest, buy_hold_return_latest = build_buy_hold_series(df_result_latest, args.initial_capital)
    metrics_latest = bt.calculate_index_strategy_metrics(
        df_result_latest,
        trades_latest,
        initial_capital=args.initial_capital,
        long_ema=safe_int(row, "long_ema"),
    )
    metrics_latest["buy_hold_return"] = buy_hold_return_latest
    metrics_latest["excess_return"] = metrics_latest["adaptive_return"] - buy_hold_return_latest
    df_result, total_return, num_trades, trades, win_rate, avg_return, decisions_df, sharpe, max_dd = result
    buy_hold_series, buy_hold_return = build_buy_hold_series(df_result, args.initial_capital)
    metrics = bt.calculate_index_strategy_metrics(
        df_result,
        trades,
        initial_capital=args.initial_capital,
        long_ema=safe_int(row, "long_ema"),
    )
    metrics["buy_hold_return"] = buy_hold_return
    metrics["excess_return"] = metrics["adaptive_return"] - buy_hold_return
    if "Date" in df_result.columns and len(df_result):
        result_start_date = pd.to_datetime(df_result["Date"], errors="coerce").dropna().min()
        result_end_date = pd.to_datetime(df_result["Date"], errors="coerce").dropna().max()
    else:
        result_start_date = df_result.index.min()
        result_end_date = df_result.index.max()
    adaptive_annualized = annualized_return_from_pct(
        metrics["adaptive_return"], result_start_date, result_end_date
    )
    buy_hold_annualized = annualized_return_from_pct(
        buy_hold_return, result_start_date, result_end_date
    )
    excess_annualized = adaptive_annualized - buy_hold_annualized
    ga_signal, last_trade_date = current_position_context(df_result_latest)

    if use_original_chart:
        import shutil
        shutil.copy(original_chart_file, technical_chart)
        source_chart_name = Path(original_chart_file).name
        source_chart_copy = CHARTS_DIR / f"{fund_label}-final-find-source-{source_chart_name}"
        shutil.copy(original_chart_file, source_chart_copy)

    if df_result is not None:
        chart_context_label = bt.build_chart_context_label(
            df_full,
            df_result,
            safe_float(row, "lookback_years"),
            safe_int(row, "offset_months"),
        )
        plot_technical_chart(
            fund_label,
            df_result,
            buy_hold_series,
            buy_hold_return,
            metrics,
            row,
            price_column,
            args.initial_capital,
            technical_chart,
            chart_context_label,
        )
        plot_simple_chart(
            fund_label,
            df_result,
            buy_hold_series,
            buy_hold_return,
            metrics,
            args.initial_capital,
            simple_chart,
            chart_context_label,
        )
        if df_result_latest is not None:
            latest_chart_context_label = bt.build_chart_context_label(
                df_full,
                df_result_latest,
                safe_float(row, "lookback_years"),
                safe_int(row, "offset_months"),
            )
            plot_technical_chart(
                f"{fund_label} [Latest]",
                df_result_latest,
                buy_hold_series_latest,
                buy_hold_return_latest,
                metrics_latest,
                row,
                price_column,
                args.initial_capital,
                latest_chart,
                latest_chart_context_label,
            )

    completed_at = datetime.now()
    duration_seconds = int((completed_at - started_at).total_seconds())
    log_lines = [
        "=== Final Backtest From Best Parameters ===",
        f"Fund: {fund_label}",
        f"Source run-history fund label: {source_fund_label}",
        f"Data file: {data_file}",
        f"Data file warning: {file_warning}" if file_warning else "Data file warning: (none)",
        f"Price column: {price_column}",
        f"Source run ID: {row.get('source_run_id', '')}",
        f"Source adaptive return: {safe_float(row, 'source_adaptive_return_pct', 0.0):.2f}%",
        f"Source adaptive annualized return: {safe_float(row, 'source_adaptive_annualized_return_pct', 0.0):.2f}%",
        f"Started at: {started_at:%Y-%m-%d %H:%M:%S}",
        f"Completed at: {completed_at:%Y-%m-%d %H:%M:%S}",
        f"Duration seconds: {duration_seconds}",
        "",
        "Selected parameters:",
        f"EMA: {safe_int(row, 'short_ema')} / {safe_int(row, 'long_ema')}",
        f"Stop loss: {safe_float(row, 'stop_loss'):.4f}",
        f"Cooldown: {safe_int(row, 'cooldown')}",
        f"Drawdown exit: {safe_float(row, 'drawdown_exit_pct'):.4f}",
        f"Reentry rebound: {safe_float(row, 'reentry_rebound_pct'):.4f}",
        f"RSI: {safe_int(row, 'rsi_oversold', 30)} / {safe_int(row, 'rsi_overbought', 70)}",
        f"Exposure: {safe_float(row, 'exposure_multiplier', 1.0):.4f}x",
        "",
        "Results:",
        f"Strategy return: {metrics['adaptive_return']:.2f}%",
        f"Strategy annualized return: {adaptive_annualized:.2f}%",
        f"Buy & hold return: {buy_hold_return:.2f}%",
        f"Buy & hold annualized return: {buy_hold_annualized:.2f}%",
        f"Excess return: {metrics['excess_return']:.2f}%",
        f"Excess annualized return: {excess_annualized:.2f}%",
        f"Sharpe: {metrics['sharpe']:.4f}",
        f"Max drawdown: {metrics['max_dd']:.2f}%",
        f"Trades: {num_trades}",
        f"Win rate: {win_rate:.2f}%",
        f"Current GA signal: {ga_signal}",
        f"Last trade date: {last_trade_date or 'n/a'}",
        "",
        f"Technical chart: {technical_chart}",
        f"Simple chart: {simple_chart}",
    ]
    write_log(log_path, log_lines)
    run_id = f"{run_timestamp}_{fund_label}"
    source_run_id = row.get("source_run_id", "n/a")
    source_adaptive = safe_float(row, "source_adaptive_return_pct", 0.0)
    source_buy_hold = safe_float(row, "source_buy_hold_return_pct", 0.0)
    source_excess = safe_float(row, "source_excess_return_pct", 0.0)
    source_chart_file = row.get("chart_file", "")
    source_chart_name = Path(source_chart_file).name if source_chart_file else "N/A"
    print()
    print(f"=" * 60)
    print(f"Run ID: {run_id}")
    print(f"Source Run ID: {source_run_id}")
    print(f"Source Data File: {row.get('source_data_file', 'N/A')}")
    print(f"Source Chart File: {source_chart_name}")
    print(f"Fund: {fund_label}")
    print(f"  Source -> Adaptive: {source_adaptive:>7.2f}%  |  Buy & Hold: {source_buy_hold:>7.2f}%  |  Excess: {source_excess:>7.2f}%")
    print(f"  Final  -> Adaptive: {metrics['adaptive_return']:>7.2f}%  |  Buy & Hold: {buy_hold_return:>7.2f}%  |  Excess: {metrics['excess_return']:>7.2f}%")
    print(f"  Latest -> Adaptive: {metrics_latest['adaptive_return']:>7.2f}%  |  Buy & Hold: {buy_hold_return_latest:>7.2f}%  |  Excess: {metrics_latest['excess_return']:>7.2f}%")
    print(f"  Trades: {num_trades}  |  Win Rate: {win_rate:.1f}%  |  Sharpe: {metrics['sharpe']:.3f}")
    print(f"  Charts: {technical_chart.name}, {simple_chart.name}, {latest_chart.name}")
    print(f"=" * 60)

    return {
        "run_id": run_id,
        "status": "completed",
        "fund_label": fund_label,
        "source_fund_label": source_fund_label,
        "data_file": str(data_file),
        "price_column": price_column,
        "strategy_profile": strategy_profile,
        "initial_capital": args.initial_capital,
        "data_start": df.index.min().strftime("%Y-%m-%d"),
        "data_end": df.index.max().strftime("%Y-%m-%d"),
        "row_count": len(df),
        "short_ema": safe_int(row, "short_ema"),
        "long_ema": safe_int(row, "long_ema"),
        "stop_loss": safe_float(row, "stop_loss"),
        "cooldown": safe_int(row, "cooldown"),
        "drawdown_exit_pct": safe_float(row, "drawdown_exit_pct"),
        "reentry_rebound_pct": safe_float(row, "reentry_rebound_pct"),
        "rsi_oversold": safe_int(row, "rsi_oversold", 30),
        "rsi_overbought": safe_int(row, "rsi_overbought", 70),
        "rsi_period": bt.DEFAULT_RSI_PERIOD,
        "exposure_multiplier": safe_float(row, "exposure_multiplier", 1.0),
        "source_run_id": row.get("source_run_id", ""),
        "source_run_started_at": row.get("source_run_started_at", ""),
        "source_adaptive_return_pct": row.get("source_adaptive_return_pct", ""),
        "source_buy_hold_return_pct": row.get("source_buy_hold_return_pct", ""),
        "source_excess_return_pct": row.get("source_excess_return_pct", ""),
        "source_adaptive_annualized_return_pct": row.get("source_adaptive_annualized_return_pct", ""),
        "source_buy_hold_annualized_return_pct": row.get("source_buy_hold_annualized_return_pct", ""),
        "source_excess_annualized_return_pct": row.get("source_excess_annualized_return_pct", ""),
        "source_sharpe": row.get("source_sharpe", ""),
        "source_max_dd_pct": row.get("source_max_dd_pct", ""),
        "final_portfolio_value": df_result["Portfolio_Value"].iloc[-1],
        "adaptive_return_pct": metrics["adaptive_return"],
        "buy_hold_return_pct": buy_hold_return,
        "excess_return_pct": metrics["excess_return"],
        "adaptive_annualized_return_pct": adaptive_annualized,
        "buy_hold_annualized_return_pct": buy_hold_annualized,
        "excess_annualized_return_pct": excess_annualized,
        "sharpe": metrics["sharpe"],
        "max_dd_pct": metrics["max_dd"],
        "trade_count": num_trades,
        "win_rate_pct": win_rate,
        "time_invested_pct": metrics["time_invested_pct"],
        "uptrend_cash_pct": metrics["uptrend_cash_pct"],
        "missed_upside_after_exit_pct": metrics["missed_upside_after_exit_pct"],
        "stop_loss_count": metrics["stop_loss_count"],
        "ga_signal": ga_signal,
        "last_trade_date": last_trade_date,
        "log_file": str(log_path),
        "technical_chart_file": str(technical_chart),
        "simple_chart_file": str(simple_chart),
        "latest_chart_file": str(latest_chart),
        "latest_data_start": df_full.index.min().strftime("%Y-%m-%d"),
        "latest_data_end": df_full.index.max().strftime("%Y-%m-%d"),
        "latest_adaptive_return_pct": metrics_latest["adaptive_return"],
        "latest_buy_hold_return_pct": buy_hold_return_latest,
        "latest_excess_return_pct": metrics_latest["excess_return"],
        "latest_adaptive_annualized_return_pct": metrics_latest["adaptive_annualized_return"],
        "latest_buy_hold_annualized_return_pct": metrics_latest["buy_hold_annualized_return"],
        "latest_excess_annualized_return_pct": metrics_latest["excess_annualized_return"],
        "latest_sharpe": metrics_latest["sharpe"],
        "latest_max_dd_pct": metrics_latest["max_dd"],
        "run_started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "run_completed_at": completed_at.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": duration_seconds,
    }


def sorted_latest_results(results):
    completed = [row for row in results if row.get("status") == "completed" and row.get("latest_chart_file")]
    completed.sort(
        key=lambda row: safe_float(row, "latest_adaptive_annualized_return_pct", float("-inf")),
        reverse=True,
    )
    return completed


EXCESS_LEADERBOARD_COLUMNS = [
    "rank",
    "canonical_fund_label",
    "source_excess_annualized_return_pct",
    "source_adaptive_annualized_return_pct",
    "source_buy_hold_annualized_return_pct",
    "source_excess_return_pct",
    "source_sharpe",
    "source_max_dd_pct",
    "lookback_years",
    "offset_months",
    "backtest_start",
    "backtest_end",
    "source_run_id",
    "source_run_started_at",
    "source_data_file",
]


def write_excess_annualized_dashboard(leaders, run_timestamp):
    """Write a run-history leaderboard without replaying any backtests."""
    leaderboard = leaders.copy().reset_index(drop=True)
    leaderboard.insert(0, "rank", range(1, len(leaderboard) + 1))

    csv_path = REPORTS_DIR / "excess_annualized_return_leaderboard.csv"
    leaderboard.reindex(columns=EXCESS_LEADERBOARD_COLUMNS).to_csv(csv_path, index=False)

    def pct(row, key):
        value = row.get(key)
        return "n/a" if value is None or pd.isna(value) else f"{float(value):+.2f}%"

    def value_or_na(row, key, digits=0):
        value = row.get(key)
        return "n/a" if value is None or pd.isna(value) else f"{float(value):.{digits}f}"

    max_abs_excess = max(
        (abs(safe_float(row, "source_excess_annualized_return_pct")) for _, row in leaderboard.iterrows()),
        default=1.0,
    ) or 1.0
    cards = []
    for _, row in leaderboard.iterrows():
        excess = safe_float(row, "source_excess_annualized_return_pct")
        width = min(50.0, abs(excess) / max_abs_excess * 50.0)
        tone = "positive" if excess > 0 else "negative"
        bar_style = f"left:50%;width:{width:.3f}%" if excess > 0 else f"right:50%;width:{width:.3f}%"
        canonical_label = html.escape(str(row.get("canonical_fund_label", "Unknown fund")))
        source_label = html.escape(str(row.get("fund_label", canonical_label)))
        source_note = (
            f'<small class="source-label">History label: {source_label}</small>'
            if source_label != canonical_label
            else ""
        )
        started_at = row.get("source_run_started_at", "")
        started_text = "n/a" if pd.isna(started_at) or not str(started_at).strip() else html.escape(str(started_at))
        window_start = row.get("backtest_start", "")
        window_end = row.get("backtest_end", "")
        window_text = "n/a"
        if pd.notna(window_start) and pd.notna(window_end) and str(window_start).strip() and str(window_end).strip():
            window_text = f"{html.escape(str(window_start))} to {html.escape(str(window_end))}"
        cards.append(
            f"""
            <article class="leader-row">
              <div class="identity">
                <span class="rank">{int(row['rank']):02d}</span>
                <div><h2>{canonical_label}</h2>{source_note}<small>Best completed run started {started_text}</small></div>
              </div>
              <div class="primary">
                <span>Excess annualized</span>
                <strong class="{tone}">{pct(row, 'source_excess_annualized_return_pct')}</strong>
                <div class="bar-track" aria-hidden="true"><i class="{tone}" style="{bar_style}"></i></div>
              </div>
              <dl>
                <div><dt>Strategy ann.</dt><dd>{pct(row, 'source_adaptive_annualized_return_pct')}</dd></div>
                <div><dt>Buy &amp; hold ann.</dt><dd>{pct(row, 'source_buy_hold_annualized_return_pct')}</dd></div>
                <div><dt>Total excess</dt><dd>{pct(row, 'source_excess_return_pct')}</dd></div>
                <div><dt>Sharpe</dt><dd>{value_or_na(row, 'source_sharpe', 2)}</dd></div>
                <div><dt>Max drawdown</dt><dd>{pct(row, 'source_max_dd_pct')}</dd></div>
                <div><dt>Lookback / offset</dt><dd>{value_or_na(row, 'lookback_years', 1)}Y / {value_or_na(row, 'offset_months')}M</dd></div>
              </dl>
              <div class="window"><span>Backtest window</span><b>{window_text}</b></div>
            </article>
            """
        )

    excess_values = pd.to_numeric(
        leaderboard.get("source_excess_annualized_return_pct", pd.Series(dtype=float)),
        errors="coerce",
    )
    positive_count = int((excess_values > 0).sum())
    negative_count = int((excess_values < 0).sum())
    top_value = pct(leaderboard.iloc[0], "source_excess_annualized_return_pct") if not leaderboard.empty else "n/a"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dashboard = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Excess Annualized Return Leaderboard</title>
  <style>
    :root{{--ink:#132238;--muted:#647186;--paper:#f4f7f8;--card:#fff;--line:#dce4e7;--green:#087a5b;--green-soft:#ddf4eb;--red:#b33a45;--red-soft:#fbe6e8;--navy:#173b57}}
    *{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
    header{{padding:42px clamp(18px,5vw,72px) 34px;background:linear-gradient(125deg,#102e45,#1d5565);color:#fff}}header>div,main{{max-width:1380px;margin:auto}}
    .eyebrow{{display:block;margin-bottom:9px;color:#a8e3d3;font-size:.72rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase}}
    h1{{max-width:820px;margin:0;font-size:clamp(2rem,4.5vw,4rem);line-height:1.02;letter-spacing:-.045em}}header p{{max-width:760px;margin:17px 0 0;color:#d6e4e8;line-height:1.6}}
    .summary{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;margin-top:30px;overflow:hidden;border:1px solid rgba(255,255,255,.2);border-radius:14px;background:rgba(255,255,255,.2)}}
    .summary div{{padding:14px 16px;background:rgba(9,34,49,.5)}}.summary span,.primary span,.window span{{display:block;color:var(--muted);font-size:.7rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}}
    .summary span{{color:#b8d0d6}}.summary strong{{display:block;margin-top:3px;font-size:1.35rem}}main{{padding:26px clamp(12px,3vw,40px) 60px}}
    .method{{display:flex;justify-content:space-between;gap:20px;margin:0 0 15px;padding:0 4px;color:var(--muted);font-size:.84rem}}.leaderboard{{display:grid;gap:10px}}
    .leader-row{{display:grid;grid-template-columns:minmax(250px,1.35fr) minmax(180px,.8fr) minmax(520px,2.3fr) minmax(190px,.8fr);align-items:center;gap:22px;padding:18px 20px;border:1px solid var(--line);border-radius:16px;background:var(--card);box-shadow:0 7px 24px rgba(27,57,75,.045)}}
    .identity{{display:flex;align-items:center;gap:14px;min-width:0}}.rank{{display:grid;place-items:center;min-width:44px;height:44px;border-radius:12px;background:#eaf0f3;color:var(--navy);font-weight:900}}
    h2{{margin:0;font-size:1rem;overflow-wrap:anywhere}}.identity small{{display:block;margin-top:4px;color:var(--muted);font-size:.72rem}}.source-label{{color:#8a5a22!important}}
    .primary strong{{display:block;margin:3px 0 8px;font-size:1.55rem}}.positive{{color:var(--green)}}.negative{{color:var(--red)}}
    .bar-track{{position:relative;height:5px;border-radius:99px;background:linear-gradient(90deg,var(--red-soft) 0 49.8%,#a9b4bf 49.8% 50.2%,var(--green-soft) 50.2% 100%)}}.bar-track i{{position:absolute;top:0;height:5px;border-radius:99px;background:currentColor}}
    dl{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0}}dl div{{padding:9px 10px;border-radius:10px;background:#f6f8f9}}dt{{color:var(--muted);font-size:.67rem;text-transform:uppercase;letter-spacing:.05em}}dd{{margin:3px 0 0;font-size:.88rem;font-weight:800}}
    .window b{{display:block;margin-top:4px;font-size:.78rem;line-height:1.35}}.empty{{padding:50px;border:1px dashed var(--line);border-radius:16px;background:#fff;text-align:center;color:var(--muted)}}
    @media(max-width:1050px){{.leader-row{{grid-template-columns:1.3fr .8fr 2fr}}.window{{grid-column:1/-1;padding-left:58px}}}}
    @media(max-width:760px){{header{{padding-top:30px}}.summary{{grid-template-columns:repeat(2,1fr)}}.method{{display:block}}.method span{{display:block;margin-top:5px}}.leader-row{{grid-template-columns:1fr;gap:15px}}.window{{grid-column:auto;padding-left:0}}dl{{grid-template-columns:repeat(2,1fr)}}}}
    @media(max-width:420px){{dl{{grid-template-columns:1fr}}}}@media print{{body{{background:#fff}}header{{padding:18px 24px;background:#173b57!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}}main{{padding:14px 0}}.leader-row{{break-inside:avoid;box-shadow:none;border-radius:0}}}}
  </style>
</head>
<body>
  <header><div>
    <span class="eyebrow">Backtest run history</span>
    <h1>Excess annualized return leaderboard</h1>
    <p>Each fund appears once, using its strongest completed historical run versus buy and hold. A zero-valued fund leader is omitted because it may indicate an invalid or incomplete result.</p>
    <section class="summary" aria-label="Leaderboard summary">
      <div><span>Ranked funds</span><strong>{len(leaderboard)}</strong></div>
      <div><span>Positive leaders</span><strong>{positive_count}</strong></div>
      <div><span>Negative leaders</span><strong>{negative_count}</strong></div>
      <div><span>Top excess ann.</span><strong>{top_value}</strong></div>
    </section>
  </div></header>
  <main>
    <p class="method">Sorted by best excess annualized return, descending. Ties use the most recent run. <span>Generated {generated_at} &middot; run {html.escape(run_timestamp)}</span></p>
    <section class="leaderboard" aria-label="Ranked funds">{''.join(cards) if cards else '<div class="empty">No non-zero completed fund leaders were available.</div>'}</section>
  </main>
</body>
</html>"""
    dashboard_path = REPORTS_DIR / "excess_annualized_return_dashboard.html"
    dashboard_path.write_text(dashboard, encoding="utf-8")
    return dashboard_path, csv_path


def write_latest_dashboard(results, run_timestamp):
    completed = sorted_latest_results(results)

    def pct(row, key):
        value = row.get(key)
        return "n/a" if value is None or pd.isna(value) else f"{float(value):+.2f}%"

    cards = []
    for rank, row in enumerate(completed, start=1):
        chart_path = Path(row["latest_chart_file"])
        chart_src = os.path.relpath(chart_path, REPORTS_DIR).replace(os.sep, "/")
        fund_label = html.escape(str(row.get("fund_label", "Unknown fund")))
        chart_alt = html.escape(f"Latest strategy chart for {row.get('fund_label', 'fund')}")
        cards.append(
            f"""
            <article class="fund-card">
              <div class="card-heading">
                <div><span class="rank">#{rank}</span><h2>{fund_label}</h2></div>
                <div class="annual-return"><span>Annual return</span><strong>{pct(row, 'latest_adaptive_annualized_return_pct')}</strong></div>
              </div>
              <div class="metrics">
                <span>Fund return <b>{pct(row, 'latest_adaptive_return_pct')}</b></span>
                <span>Buy &amp; hold ann. <b>{pct(row, 'latest_buy_hold_annualized_return_pct')}</b></span>
                <span>Excess ann. <b>{pct(row, 'latest_excess_annualized_return_pct')}</b></span>
                <span>Max drawdown <b>{pct(row, 'latest_max_dd_pct')}</b></span>
                <span>Through <b>{html.escape(str(row.get('latest_data_end', 'n/a')))}</b></span>
              </div>
              <button class="chart-button" type="button" data-src="{html.escape(chart_src, quote=True)}" data-title="{fund_label}" aria-label="Open zoomable chart for {fund_label}">
                <img src="{html.escape(chart_src, quote=True)}" alt="{chart_alt}" loading="lazy">
                <span class="zoom-hint">Click to zoom</span>
              </button>
            </article>
            """
        )

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dashboard = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Latest Fund Backtest Dashboard</title>
  <style>
    :root{{--ink:#172033;--muted:#667085;--line:#dce2ea;--surface:#fff;--accent:#176b5b;--accent-soft:#e8f4f1;--bg:#f3f5f7}}
    *{{box-sizing:border-box}}
    body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}}
    header{{position:sticky;top:0;z-index:10;padding:20px clamp(18px,4vw,52px);background:rgba(243,245,247,.94);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}}
    header h1{{margin:0 0 5px;font-size:clamp(1.45rem,3vw,2.2rem)}}
    header p{{margin:0;color:var(--muted)}}
    main{{display:grid;gap:22px;padding:28px clamp(16px,3vw,42px) 56px;max-width:1900px;margin:auto}}
    .fund-card{{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 8px 26px rgba(19,33,55,.06)}}
    .card-heading,.card-heading>div,.metrics{{display:flex;align-items:center}}
    .card-heading{{justify-content:space-between;gap:18px;margin-bottom:13px}}
    .card-heading>div:first-child{{gap:10px;min-width:0}}
    .rank{{display:grid;place-items:center;min-width:38px;height:30px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-weight:800}}
    h2{{font-size:clamp(1rem,2vw,1.35rem);margin:0;overflow-wrap:anywhere}}
    .annual-return{{display:flex;flex-direction:column!important;align-items:flex-end!important;white-space:nowrap}}
    .annual-return span{{font-size:.76rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}
    .annual-return strong{{font-size:1.35rem;color:var(--accent)}}
    .metrics{{flex-wrap:wrap;gap:8px;margin-bottom:14px}}
    .metrics span{{padding:7px 10px;border-radius:9px;background:#f7f8fa;color:var(--muted);font-size:.84rem}}
    .metrics b{{color:var(--ink)}}
    .chart-button{{display:block;position:relative;width:100%;padding:0;border:0;border-radius:12px;overflow:hidden;background:#e8ebef;cursor:zoom-in}}
    .chart-button img{{display:block;width:100%;height:auto}}
    .zoom-hint{{position:absolute;right:12px;bottom:12px;padding:7px 10px;border-radius:8px;background:rgba(16,24,40,.78);color:#fff;font-size:.78rem;opacity:0;transition:opacity .18s}}
    .chart-button:hover .zoom-hint,.chart-button:focus-visible .zoom-hint{{opacity:1}}
    dialog{{width:calc(100vw - 24px);height:calc(100vh - 24px);max-width:none;max-height:none;padding:0;border:0;border-radius:16px;background:#111827;overflow:hidden}}
    dialog::backdrop{{background:rgba(3,8,18,.82)}}
    .viewer-bar{{position:absolute;inset:0 0 auto 0;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;background:rgba(17,24,39,.9);color:white}}
    .viewer-bar strong{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .controls{{display:flex;gap:7px}}
    .controls button{{border:1px solid #667085;background:#263246;color:white;border-radius:8px;padding:7px 11px;cursor:pointer}}
    .viewport{{width:100%;height:100%;overflow:hidden;cursor:grab;touch-action:none}}
    .viewport.dragging{{cursor:grabbing}}
    #viewerImage{{position:absolute;left:50%;top:50%;max-width:none;transform-origin:center;user-select:none;pointer-events:none}}
    @media (min-width:1200px){{main{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
    @page{{size:A4 landscape;margin:8mm}}
    @media print{{
      body{{background:#fff}}
      header,dialog,.zoom-hint{{display:none!important}}
      main{{display:block;max-width:none;padding:0;margin:0}}
      .fund-card{{height:194mm;margin:0;padding:4mm;border:0;border-radius:0;box-shadow:none;overflow:hidden;break-inside:avoid;page-break-inside:avoid;break-after:page;page-break-after:always}}
      .fund-card:last-child{{break-after:auto;page-break-after:auto}}
      .card-heading{{margin-bottom:2mm}}
      .metrics{{margin-bottom:2mm;gap:1.5mm}}
      .metrics span{{padding:1.5mm 2mm}}
      .chart-button{{height:158mm;border-radius:0;cursor:default;overflow:hidden}}
      .chart-button img{{width:100%;height:100%;object-fit:contain}}
    }}
  </style>
</head>
<body>
  <header><h1>Latest Fund Backtest Dashboard</h1><p>{len(completed)} funds · sorted by latest strategy annualized return · generated {generated_at}</p></header>
  <main>{''.join(cards) if cards else '<p>No completed latest charts were available.</p>'}</main>
  <dialog id="viewer">
    <div class="viewer-bar"><strong id="viewerTitle">Chart</strong><div class="controls"><button id="zoomOut" type="button">−</button><button id="resetZoom" type="button">Reset</button><button id="zoomIn" type="button">+</button><button id="closeViewer" type="button">Close</button></div></div>
    <div class="viewport" id="viewport"><img id="viewerImage" alt=""></div>
  </dialog>
  <script>
    const viewer=document.getElementById('viewer'), viewport=document.getElementById('viewport'), image=document.getElementById('viewerImage');
    let scale=1,x=0,y=0,drag=false,startX=0,startY=0;
    function render(){{image.style.transform=`translate(calc(-50% + ${{x}}px),calc(-50% + ${{y}}px)) scale(${{scale}})`}}
    function fit(){{if(!image.naturalWidth)return;scale=Math.min(1,(viewport.clientWidth-36)/image.naturalWidth,(viewport.clientHeight-86)/image.naturalHeight);x=0;y=0;render()}}
    function reset(){{fit()}}
    function zoom(factor){{scale=Math.min(8,Math.max(.5,scale*factor));render()}}
    image.addEventListener('load',fit);
    document.querySelectorAll('.chart-button').forEach(button=>button.addEventListener('click',()=>{{image.src=button.dataset.src;image.alt=button.dataset.title;document.getElementById('viewerTitle').textContent=button.dataset.title;viewer.showModal();if(image.complete)fit()}}));
    document.getElementById('closeViewer').onclick=()=>viewer.close();
    document.getElementById('zoomIn').onclick=()=>zoom(1.25);document.getElementById('zoomOut').onclick=()=>zoom(.8);document.getElementById('resetZoom').onclick=reset;
    viewport.addEventListener('wheel',event=>{{event.preventDefault();zoom(event.deltaY<0?1.15:.87)}},{{passive:false}});
    viewport.addEventListener('pointerdown',event=>{{drag=true;startX=event.clientX-x;startY=event.clientY-y;viewport.setPointerCapture(event.pointerId);viewport.classList.add('dragging')}});
    viewport.addEventListener('pointermove',event=>{{if(!drag)return;x=event.clientX-startX;y=event.clientY-startY;render()}});
    viewport.addEventListener('pointerup',()=>{{drag=false;viewport.classList.remove('dragging')}});
    viewer.addEventListener('click',event=>{{if(event.target===viewer)viewer.close()}});
  </script>
</body>
</html>"""
    dashboard_path = REPORTS_DIR / "dashboard.html"
    dashboard_path.write_text(dashboard, encoding="utf-8")
    return dashboard_path


def write_latest_pdf(results):
    completed = sorted_latest_results(results)
    pdf_path = REPORTS_DIR / "dashboard.pdf"

    def write_pdf(path):
        with PdfPages(path) as pdf:
            for rank, row in enumerate(completed, start=1):
                chart_path = Path(row["latest_chart_file"])
                if not chart_path.exists():
                    continue

                figure = plt.figure(figsize=(11.69, 8.27), facecolor="white")
                fund_label = str(row.get("fund_label", "Unknown fund"))
                annualized = safe_float(row, "latest_adaptive_annualized_return_pct", np.nan)
                figure.text(0.045, 0.948, f"#{rank}  {fund_label}", fontsize=17, fontweight="bold", color="#172033", va="top")
                figure.text(0.955, 0.948, f"Annual return {annualized:+.2f}%" if np.isfinite(annualized) else "Annual return n/a", fontsize=15, fontweight="bold", color="#176b5b", ha="right", va="top")
                metrics_line = (
                    f"Fund return {safe_float(row, 'latest_adaptive_return_pct', np.nan):+.2f}%    |    "
                    f"Buy & hold annualized {safe_float(row, 'latest_buy_hold_annualized_return_pct', np.nan):+.2f}%    |    "
                    f"Excess annualized {safe_float(row, 'latest_excess_annualized_return_pct', np.nan):+.2f}%    |    "
                    f"Max drawdown {safe_float(row, 'latest_max_dd_pct', np.nan):.2f}%    |    "
                    f"Through {row.get('latest_data_end', 'n/a')}"
                )
                figure.text(0.045, 0.895, metrics_line, fontsize=9.5, color="#596579", va="top")

                chart_axis = figure.add_axes([0.035, 0.035, 0.93, 0.82])
                chart_axis.imshow(plt.imread(chart_path))
                chart_axis.set_axis_off()
                pdf.savefig(figure)
                plt.close(figure)

    try:
        write_pdf(pdf_path)
        return pdf_path
    except PermissionError:
        fallback = REPORTS_DIR / f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        write_pdf(fallback)
        print(f"Warning: {pdf_path} is locked. Saved PDF to {fallback}")
        return fallback


def main():
    args = parse_args()
    ensure_output_dirs()

    if args.data_file and not args.fund_label:
        raise ValueError("--data-file is only supported with --fund-label so the parameter row is unambiguous")

    summary_path = Path(args.summary_file)
    if not summary_path.is_absolute():
        summary_path = REPO_ROOT / summary_path
    if not summary_path.exists():
        raise FileNotFoundError(f"Run history file not found: {summary_path}")

    run_history_df = normalize_run_history(pd.read_csv(summary_path, low_memory=False))
    selected_rows = select_best_run_rows(run_history_df, args.fund_label, args.top_funds)
    all_leaders = select_best_run_rows(run_history_df, args.fund_label, top_funds=0)
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excess_dashboard_path, excess_csv_path = write_excess_annualized_dashboard(
        all_leaders,
        run_timestamp,
    )
    print(f"Excess annualized return dashboard saved to: {excess_dashboard_path}")
    print(f"Excess annualized return leaderboard saved to: {excess_csv_path}")
    if args.leaderboard_only:
        return 0

    if not args.fund_label and args.top_funds and args.top_funds > 0:
        print(
            f"Generating final charts for top {len(selected_rows)} fund(s) "
            "ranked by historical excess annualized return."
        )

    results = []
    for _, row in selected_rows.iterrows():
        try:
            results.append(run_one_fund(row, args, run_timestamp))
        except Exception as exc:
            fund_label = row.get("fund_label", "unknown")
            message = f"Skipping {fund_label}: {exc}"
            print(message)
            results.append({
                "run_id": f"{run_timestamp}_{fund_label}",
                "status": "error",
                "fund_label": fund_label,
                "message": str(exc),
            })

    summary_output = TUNINGS_DIR / f"final_backtest_summary_{run_timestamp}.csv"
    pd.DataFrame(results).to_csv(summary_output, index=False)
    dashboard_path = write_latest_dashboard(results, run_timestamp)
    pdf_path = write_latest_pdf(results)
    print(f"\nFinal backtest summary saved to: {summary_output}")
    print(f"Latest chart dashboard saved to: {dashboard_path}")
    print(f"One-fund-per-page PDF saved to: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
