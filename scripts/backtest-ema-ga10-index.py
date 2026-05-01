#GA10-very slow due to retune hyperparams every step 2025-01-10, for multiple offset-months
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import hashlib
import random
import warnings
warnings.filterwarnings('ignore')
import signal
import sys
import os
from pathlib import Path
import itertools  # For grid search over GA hyperparameters
import argparse
import signal
import re
import json
import platform
import socket
import time

try:
    import yfinance as yf
except ImportError:
    yf = None

# Global log file handle
log_file = None
csv_name="No-name"
lookback_years=0
offset_months=0
pop_ranges=[10]
gen_ranges = []
mutation_rates = []
crossover_rates = []
reuse_tuned_params = False
batch_name = f"{csv_name}-{lookback_years}Y-{offset_months}M"
started_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
strategy_profile = "generic"
ga_seed = None
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUTS_DIR = REPO_ROOT / "outputs"
LOGS_DIR = OUTPUTS_DIR / "logs"
CHARTS_DIR = OUTPUTS_DIR / "charts"
TUNINGS_DIR = OUTPUTS_DIR / "tunings"
RUN_HISTORY_FILE = TUNINGS_DIR / "backtest_run_history.csv"
WINDOW_HISTORY_FILE = TUNINGS_DIR / "backtest_window_history.csv"
TUNING_HISTORY_FILE = TUNINGS_DIR / "backtest_tuning_history.csv"
TOP5_PARAMETERS_FILE = TUNINGS_DIR / "top5_parameter_sets_by_fund.csv"
DEFAULT_SHORT_EMA_BOUNDS = (2, 60)
DEFAULT_LONG_EMA_BOUNDS = (30, 300)
DEFAULT_RSI_OVERSOLD_BOUNDS = (10, 40)
DEFAULT_RSI_OVERBOUGHT_BOUNDS = (60, 90)
DEFAULT_RSI_PERIOD = 14
LOCK_RETRY_SCHEDULE_SECONDS = [30, 60, 120]
history_fallback_files = []
skip_top5_refresh_for_run = False

FUND_CODE_TO_SHORT_NAME = {
    "MAKGCF": "GreaterChina",
    "MAPF": "Progress",
    "APCR": "AsiaPacificREIT",
}

DEFAULT_STRATEGY_PARAMETERS = {
    "use_rsi_filter": False,
    "rsi_oversold": 29,
    "rsi_overbought": 71,
    "rsi_period": DEFAULT_RSI_PERIOD,
    "use_trend_filter": False,
    "trend_period": 100,
    "use_stop_loss": True,
    "stop_loss_pct": 5.0,
    "use_take_profit": True,
    "take_profit_pct": 10.0,
    "cooldown_period": 3,
    "dip_threshold_pct": 5.0,
    "dip_lookback_days": 20,
    "rebound_threshold_pct": 3.0,
    "recovery_window_days": 10,
    "drawdown_exit_pct": 3.0,
    "reentry_rebound_pct": 2.0,
}

STRATEGY_PROFILE_SETTINGS = {
    "generic": {
        "execution_mode": "drawdown_reentry",
        "drawdown_exit_multiplier": 1.0,
        "cooldown_extra_periods": 0,
        "reentry_rebound_multiplier": 1.0,
        "gene_bounds": {},
        "require_price_above_long_ema_for_reentry": False,
        "require_positive_long_slope_for_reentry": False,
        "require_price_below_long_ema_for_exit": False,
        "require_negative_long_slope_for_exit": False,
        "missed_upside_after_exit_weight": 0.0,
        "default_exposure_multiplier": 1.0,
        "enable_partial_derisk": False,
        "partial_exit_target_exposure": 0.5,
        "full_exit_drawdown_multiplier": 1.0,
        "partial_reentry_rebound_multiplier": 1.0,
        "signal_reentry_buffer_scale": 0.0,
    },
    "qqq": {
        "execution_mode": "regime_signal",
        "drawdown_exit_multiplier": 1.0,
        "cooldown_extra_periods": 0,
        "reentry_rebound_multiplier": 1.0,
        "gene_bounds": {
            "cooldown": (0, 5),
            "drawdown_exit_pct": (2.5, 8.0),
            "reentry_rebound_pct": (0.25, 5.0),
        },
        "require_price_above_long_ema_for_reentry": True,
        "require_positive_long_slope_for_reentry": True,
        "require_price_below_long_ema_for_exit": True,
        "require_negative_long_slope_for_exit": True,
        "missed_upside_after_exit_weight": 1.0,
        "default_exposure_multiplier": 1.0,
        "enable_partial_derisk": False,
        "partial_exit_target_exposure": 0.5,
        "full_exit_drawdown_multiplier": 1.75,
        "partial_reentry_rebound_multiplier": 0.5,
        "signal_reentry_buffer_scale": 0.10,
    },
    "qqq-return-plus": {
        "execution_mode": "drawdown_reentry",
        "drawdown_exit_multiplier": 1.0,
        "cooldown_extra_periods": 0,
        "reentry_rebound_multiplier": 1.0,
        "gene_bounds": {
            "cooldown": (0, 5),
            "drawdown_exit_pct": (2.5, 10.0),
            "reentry_rebound_pct": (0.25, 5.0),
            "exposure_multiplier": (1.0, 1.35),
        },
        "require_price_above_long_ema_for_reentry": True,
        "require_positive_long_slope_for_reentry": True,
        "require_price_below_long_ema_for_exit": True,
        "require_negative_long_slope_for_exit": True,
        "missed_upside_after_exit_weight": 1.0,
        "default_exposure_multiplier": 1.0,
        "enable_partial_derisk": False,
        "partial_exit_target_exposure": 0.5,
        "full_exit_drawdown_multiplier": 1.75,
        "partial_reentry_rebound_multiplier": 0.5,
        "signal_reentry_buffer_scale": 0.10,
    },
    "qqq-buyhold-plus": {
        "execution_mode": "drawdown_reentry",
        "drawdown_exit_multiplier": 1.0,
        "cooldown_extra_periods": 0,
        "reentry_rebound_multiplier": 1.0,
        "gene_bounds": {
            "cooldown": (0, 0),
            "drawdown_exit_pct": (10.0, 10.0),
            "reentry_rebound_pct": (0.0, 0.0),
            "exposure_multiplier": (1.0, 1.35),
        },
        "require_price_above_long_ema_for_reentry": False,
        "require_positive_long_slope_for_reentry": False,
        "require_price_below_long_ema_for_exit": False,
        "require_negative_long_slope_for_exit": False,
        "missed_upside_after_exit_weight": 0.0,
        "default_exposure_multiplier": 1.0,
        "always_invested": True,
        "disable_timing_exits": True,
        "disable_stop_loss": True,
        "disable_take_profit": True,
        "enable_partial_derisk": False,
        "partial_exit_target_exposure": 0.5,
        "full_exit_drawdown_multiplier": 1.0,
        "partial_reentry_rebound_multiplier": 1.0,
        "signal_reentry_buffer_scale": 0.0,
    },
}

PROFILE_OVERRIDE_PRESETS = {
    "default": {},
    "qqq-tighter-exit-reentry": {
        "gene_bounds": {
            "cooldown": (2, 7),
            "drawdown_exit_pct": (1.5, 5.0),
            "reentry_rebound_pct": (2.0, 6.0),
        },
    },
    "qqq-looser-exit-reentry": {
        "gene_bounds": {
            "cooldown": (0, 3),
            "drawdown_exit_pct": (5.0, 10.0),
            "reentry_rebound_pct": (0.25, 2.0),
        },
    },
    "qqq-focused-looser-exit-reentry": {
        "gene_bounds": {
            "cooldown": (0, 2),
            "drawdown_exit_pct": (5.25, 9.75),
            "reentry_rebound_pct": (0.25, 1.75),
        },
    },
}

def parse_args():
    parser = argparse.ArgumentParser(
        description="Backtest runner with configurable lookback_years and offset_months"
    )
    parser.add_argument(
        "--lookback-years",
        type=float,
        default=2,
        help="Lookback period in years (default: 2)"
    )
    parser.add_argument(
        "--offset-months",
        type=int,
        default=6,
        help="Offset period in months (default: 6)"
    )
    parser.add_argument(
        "--pop_ranges",
        nargs="+",
        type=str,
        default=10,
        help="GA Population size (default: 10)"
    )
    parser.add_argument(
        "--gen_ranges",
        nargs="+",
        type=str,
        default=None,
        help="GA Generation size (default: 10)"
    )
    parser.add_argument(
        "--short-ema-bounds",
        nargs=2,
        type=int,
        default=list(DEFAULT_SHORT_EMA_BOUNDS),
        metavar=("MIN", "MAX"),
        help="Short EMA integer bounds for GA search (default: 2 60)"
    )
    parser.add_argument(
        "--long-ema-bounds",
        nargs=2,
        type=int,
        default=list(DEFAULT_LONG_EMA_BOUNDS),
        metavar=("MIN", "MAX"),
        help="Long EMA integer bounds for GA search (default: 30 300)"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["^GSPC", "QQQ"],
        help="Yahoo Finance symbols to download and backtest (default: ^GSPC QQQ)"
    )
    parser.add_argument(
        "--download-years",
        type=int,
        default=3,
        help="Years of daily data to download from Yahoo Finance (default: 3)"
    )
    parser.add_argument(
        "--strategy-profile",
        choices=sorted(STRATEGY_PROFILE_SETTINGS.keys()),
        default="generic",
        help="Strategy behavior profile to use (default: generic)"
    )
    parser.add_argument(
        "--ga-seed",
        type=int,
        default=None,
        help="Fixed random seed for GA optimization (default: unset)"
    )
    parser.add_argument(
        "--data-file",
        default=None,
        help="Use an existing CSV file instead of downloading by symbol"
    )
    parser.add_argument(
        "--data-files",
        nargs="+",
        default=None,
        help="Use one or more existing CSV files instead of downloading by symbol"
    )
    parser.add_argument(
        "--fund-glob",
        default="*_nav_*Y.csv",
        help="Local Manulife CSV glob to backtest when no data file is supplied"
    )
    parser.add_argument(
        "--price-column",
        default="TotalReturn",
        help="CSV price column to backtest; default prefers Manulife TotalReturn"
    )
    parser.add_argument(
        "--profile-override-preset",
        choices=sorted(PROFILE_OVERRIDE_PRESETS.keys()),
        default="default",
        help="Optional profile override preset for targeted exit/re-entry experiments"
    )
    parser.add_argument(
        "--ga-search-preset",
        choices=["grid", "focused"],
        default="grid",
        help="GA hyperparameter search preset (focused uses the observed QQQ winner: mutation=0.01, crossover=0.6)"
    )
    parser.add_argument(
        "--mutation-rates",
        nargs="+",
        type=str,
        default=None,
        help="Mutation rates to test during GA hyperparameter tuning"
    )
    parser.add_argument(
        "--crossover-rates",
        nargs="+",
        type=str,
        default=None,
        help="Crossover rates to test during GA hyperparameter tuning"
    )
    parser.add_argument(
        "--reuse-tuned-params",
        action="store_true",
        help="Reuse the best parameter set found during tuning instead of rerunning the same GA"
    )
    return parser.parse_args()


def get_strategy_profile_settings(profile_name):
    if profile_name not in STRATEGY_PROFILE_SETTINGS:
        raise ValueError(f"Unknown strategy profile: {profile_name}")
    return STRATEGY_PROFILE_SETTINGS[profile_name]


def apply_profile_override_preset(profile_name, preset_name):
    """Apply a bounded profile override preset for reproducible experiments."""
    if preset_name == "default":
        return

    preset = PROFILE_OVERRIDE_PRESETS[preset_name]
    profile_settings = get_strategy_profile_settings(profile_name)

    for key, value in preset.items():
        if key == "gene_bounds":
            merged_bounds = dict(profile_settings.get("gene_bounds", {}))
            merged_bounds.update(value)
            profile_settings["gene_bounds"] = merged_bounds
        else:
            profile_settings[key] = value


def get_exposure_bounds(strategy_profile_name):
    profile_settings = get_strategy_profile_settings(strategy_profile_name)
    default_exposure = profile_settings.get("default_exposure_multiplier", 1.0)
    return profile_settings.get("gene_bounds", {}).get(
        "exposure_multiplier",
        (default_exposure, default_exposure),
    )


def resolve_profile_gene_bounds(strategy_profile_name, short_ema_bounds, long_ema_bounds,
                                sl_bounds, cd_bounds, drawdown_exit_bounds,
                                reentry_rebound_bounds):
    """Apply profile-specific optimizer bounds without changing the public CLI."""
    profile_settings = get_strategy_profile_settings(strategy_profile_name)
    profile_bounds = profile_settings.get("gene_bounds", {})
    return (
        profile_bounds.get("short_ema", short_ema_bounds),
        profile_bounds.get("long_ema", long_ema_bounds),
        profile_bounds.get("stop_loss", sl_bounds),
        profile_bounds.get("cooldown", cd_bounds),
        profile_bounds.get("drawdown_exit_pct", drawdown_exit_bounds),
        profile_bounds.get("reentry_rebound_pct", reentry_rebound_bounds),
    )

def build_deterministic_seed(*parts):
    """Create a stable 32-bit seed from run metadata."""
    seed_material = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:8], 16)


def json_default(value):
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def stable_hash(value, length=12):
    encoded = json.dumps(value, sort_keys=True, default=json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:length]


def format_date(value):
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def build_run_id(started_at_value, fund_label, config):
    return f"{pd.Timestamp(started_at_value).strftime('%Y%m%d%H%M%S')}_{fund_label}_{stable_hash(config, 8)}"


def build_param_set_id(row):
    def normalize_param(value):
        if isinstance(value, (float, np.floating)):
            return round(float(value), 6)
        return value

    keys = [
        "fund_label",
        "price_column",
        "lookback_years",
        "offset_months",
        "strategy_profile",
        "short_ema",
        "long_ema",
        "stop_loss",
        "cooldown",
        "drawdown_exit_pct",
        "reentry_rebound_pct",
        "rsi_oversold",
        "rsi_overbought",
        "exposure_multiplier",
    ]
    return stable_hash({key: normalize_param(row.get(key)) for key in keys}, 16)


def safe_log(message):
    print(message)
    global log_file
    if log_file:
        try:
            log_file.write(message + '\n')
            log_file.flush()
        except Exception:
            pass


def build_lock_fallback_path(path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")


def record_history_fallback(original_path, fallback_path):
    global history_fallback_files
    entry = f"{original_path} -> {fallback_path}"
    if entry not in history_fallback_files:
        history_fallback_files.append(entry)


def run_with_lock_resilience(path, writer, purpose):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error = None

    for attempt_index, wait_seconds in enumerate(LOCK_RETRY_SCHEDULE_SECONDS, start=1):
        try:
            writer(path)
            return {
                "path": str(path),
                "used_fallback": False,
                "locked": False,
            }
        except PermissionError as exc:
            last_error = exc
            safe_log(
                f"{purpose} locked: {path}. "
                f"Retry {attempt_index}/{len(LOCK_RETRY_SCHEDULE_SECONDS)} in {wait_seconds}s."
            )
            time.sleep(wait_seconds)

    try:
        writer(path)
        return {
            "path": str(path),
            "used_fallback": False,
            "locked": False,
        }
    except PermissionError as exc:
        last_error = exc

    fallback_path = build_lock_fallback_path(path)
    safe_log(
        f"{purpose} still locked after retries: {path}. "
        f"Writing fallback file instead: {fallback_path}"
    )
    writer(fallback_path)
    record_history_fallback(path, fallback_path)
    return {
        "path": str(fallback_path),
        "used_fallback": True,
        "locked": True,
        "error": str(last_error) if last_error else "",
    }


def append_csv_rows_to_path(path, rows):
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    if not path.exists():
        df.to_csv(path, index=False)
        return

    try:
        existing_cols = pd.read_csv(path, nrows=0).columns.tolist()
    except pd.errors.EmptyDataError:
        df.to_csv(path, index=False)
        return

    all_cols = existing_cols + [col for col in df.columns if col not in existing_cols]
    if len(all_cols) > len(existing_cols):
        existing_df = pd.read_csv(path)
        for col in all_cols:
            if col not in existing_df.columns:
                existing_df[col] = ""
        for col in all_cols:
            if col not in df.columns:
                df[col] = ""
        pd.concat(
            [existing_df[all_cols], df[all_cols]],
            ignore_index=True,
        ).to_csv(path, index=False)
        return

    df.reindex(columns=existing_cols).to_csv(path, mode="a", index=False, header=False)


def append_csv_rows(path, rows):
    if not rows:
        return {
            "path": str(path),
            "used_fallback": False,
            "locked": False,
        }

    result = run_with_lock_resilience(
        path,
        lambda target_path: append_csv_rows_to_path(target_path, rows),
        purpose="History CSV append",
    )

    global skip_top5_refresh_for_run
    if Path(path) == TUNING_HISTORY_FILE and result.get("used_fallback"):
        skip_top5_refresh_for_run = True
        safe_log(
            f"Top-5 refresh will be skipped for this run because the main tuning history file was unavailable. "
            f"Fallback history file: {result['path']}"
        )

    return result


def append_csv_row(path, row):
    append_csv_rows(path, [row])


def write_csv_with_lock_resilience(df, path, index=False, purpose="History CSV write"):
    return run_with_lock_resilience(
        path,
        lambda target_path: df.to_csv(target_path, index=index),
        purpose=purpose,
    )


def build_strategy_parameter_metadata(config, profile_settings):
    params = dict(DEFAULT_STRATEGY_PARAMETERS)
    params.update({
        key: value
        for key, value in (config or {}).items()
        if key in params
    })
    return {
        **params,
        "execution_mode": profile_settings.get("execution_mode", "drawdown_reentry"),
        "require_price_above_long_ema_for_reentry": profile_settings.get("require_price_above_long_ema_for_reentry", False),
        "require_positive_long_slope_for_reentry": profile_settings.get("require_positive_long_slope_for_reentry", False),
        "require_price_below_long_ema_for_exit": profile_settings.get("require_price_below_long_ema_for_exit", False),
        "require_negative_long_slope_for_exit": profile_settings.get("require_negative_long_slope_for_exit", False),
        "enable_partial_derisk": profile_settings.get("enable_partial_derisk", False),
        "partial_exit_target_exposure": profile_settings.get("partial_exit_target_exposure", 0.5),
        "always_invested": profile_settings.get("always_invested", False),
        "disable_timing_exits": profile_settings.get("disable_timing_exits", False),
        "disable_stop_loss": profile_settings.get("disable_stop_loss", False),
        "disable_take_profit": profile_settings.get("disable_take_profit", False),
    }


def get_machine_metadata():
    """Capture the runner identity so results can be compared across machines."""
    hostname = socket.gethostname()
    machine_name = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or hostname
    return {
        "machine_name": machine_name,
        "hostname": hostname,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
    }


def build_run_metadata(run_id, csv_path, fund_label, price_column, data_start, data_end,
                       row_count, lookback_years_value, offset_months_value,
                       initial_capital, backtest_start, backtest_end,
                       strategy_profile_value, profile_override_preset_value,
                       ga_seed_value, ga_search_preset_value,
                       reuse_tuned_params_value, pop_ranges_value,
                       gen_ranges_value, mutation_rates_value,
                       crossover_rates_value, short_ema_bounds_value,
                       long_ema_bounds_value, machine_metadata=None):
    machine_metadata = machine_metadata or get_machine_metadata()
    return {
        "run_id": run_id,
        **machine_metadata,
        "fund_label": fund_label,
        "data_file": str(csv_path),
        "price_column": price_column,
        "data_start": format_date(data_start),
        "data_end": format_date(data_end),
        "row_count": row_count,
        "lookback_years": lookback_years_value,
        "offset_months": offset_months_value,
        "initial_capital": initial_capital,
        "backtest_start": format_date(backtest_start),
        "backtest_end": format_date(backtest_end),
        "strategy_profile": strategy_profile_value,
        "profile_override_preset": profile_override_preset_value,
        "ga_seed": ga_seed_value if ga_seed_value is not None else "deterministic",
        "ga_search_preset": ga_search_preset_value,
        "reuse_tuned_params": reuse_tuned_params_value,
        "pop_ranges": ",".join(str(value) for value in pop_ranges_value),
        "gen_ranges": ",".join(str(value) for value in gen_ranges_value),
        "short_ema_min": short_ema_bounds_value[0],
        "short_ema_max": short_ema_bounds_value[1],
        "long_ema_min": long_ema_bounds_value[0],
        "long_ema_max": long_ema_bounds_value[1],
        "mutation_rates": ",".join(str(value) for value in mutation_rates_value) if mutation_rates_value else "default grid",
        "crossover_rates": ",".join(str(value) for value in crossover_rates_value) if crossover_rates_value else "default grid",
        "run_started_at": started_at,
    }


def normalize_tuning_history_columns(df):
    rename_map = {
        "best_short_ema": "short_ema",
        "best_long_ema": "long_ema",
        "best_stop_loss_pct": "stop_loss",
        "best_cooldown": "cooldown",
        "best_drawdown_exit_pct": "drawdown_exit_pct",
        "best_reentry_rebound_pct": "reentry_rebound_pct",
        "best_rsi_oversold": "rsi_oversold",
        "best_rsi_overbought": "rsi_overbought",
        "best_exposure_multiplier": "exposure_multiplier",
        "max_dd_pct": "max_drawdown_pct",
    }
    for old_name, new_name in rename_map.items():
        if old_name in df.columns and new_name not in df.columns:
            df[new_name] = df[old_name]
    if "rsi_oversold" not in df.columns:
        df["rsi_oversold"] = DEFAULT_STRATEGY_PARAMETERS["rsi_oversold"]
    if "rsi_overbought" not in df.columns:
        df["rsi_overbought"] = DEFAULT_STRATEGY_PARAMETERS["rsi_overbought"]
    if "rsi_period" not in df.columns:
        df["rsi_period"] = DEFAULT_RSI_PERIOD
    return df


def refresh_top5_parameter_sets():
    global skip_top5_refresh_for_run
    if skip_top5_refresh_for_run:
        safe_log(
            "Skipping top-5 refresh because the main tuning history file was not updated during this run."
        )
        return
    if not TUNING_HISTORY_FILE.exists():
        return

    try:
        history = pd.read_csv(TUNING_HISTORY_FILE)
    except PermissionError:
        safe_log(
            f"Skipping top-5 refresh because tuning history is locked: {TUNING_HISTORY_FILE}"
        )
        return
    if history.empty:
        return
    history = normalize_tuning_history_columns(history)

    group_cols = [
        "fund_label",
        "price_column",
        "lookback_years",
        "offset_months",
        "strategy_profile",
        "short_ema",
        "long_ema",
        "stop_loss",
        "cooldown",
        "drawdown_exit_pct",
        "reentry_rebound_pct",
        "rsi_oversold",
        "rsi_overbought",
        "exposure_multiplier",
    ]
    missing_cols = [col for col in group_cols if col not in history.columns]
    if missing_cols:
        log_print(f"Skipping top-5 refresh; missing columns: {missing_cols}")
        return

    numeric_cols = [
        "score",
        "excess_return_pct",
        "sharpe",
        "max_drawdown_pct",
        "trade_count",
    ]
    for col in numeric_cols:
        if col in history.columns:
            history[col] = pd.to_numeric(history[col], errors="coerce")
    if "best" in history.columns:
        history["best_flag"] = history["best"].astype(str).str.lower().isin(["true", "1", "yes"])
    else:
        history["best_flag"] = False

    grouped = history.groupby(group_cols, dropna=False).agg(
        times_tested=("score", "size"),
        times_selected_best=("best_flag", "sum"),
        avg_score=("score", "mean"),
        median_score=("score", "median"),
        avg_excess_return_pct=("excess_return_pct", "mean"),
        avg_sharpe=("sharpe", "mean"),
        avg_max_dd_pct=("max_drawdown_pct", "mean"),
        avg_trade_count=("trade_count", "mean"),
        most_recent_run_date=("run_started_at", "max"),
    ).reset_index()

    grouped["param_set_id"] = grouped.apply(lambda row: build_param_set_id(row.to_dict()), axis=1)
    grouped = grouped.sort_values(
        ["fund_label", "avg_score", "avg_excess_return_pct", "avg_sharpe", "avg_max_dd_pct", "times_selected_best"],
        ascending=[True, False, False, False, True, False],
    )
    top5 = grouped.groupby("fund_label", group_keys=False).head(5)
    write_csv_with_lock_resilience(
        top5,
        TOP5_PARAMETERS_FILE,
        index=False,
        purpose="Top-5 parameter summary write",
    )


def sanitize_label(value):
    """Return a filesystem-safe compact label."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", str(value or ""))
    return cleaned or "Unknown"


def infer_fund_output_label(csv_file):
    """
    Build a concise fund label for filenames/titles.
    Examples:
    - manulife_MAKGCF_nav_3Y.csv -> MAKGCF_GreaterChina
    - MAKGCF_GreaterChina_nav_3Y.csv -> MAKGCF_GreaterChina
    """
    stem = Path(csv_file).stem
    new_name_match = re.search(r"^([A-Za-z0-9]+)_([A-Za-z0-9]+)_nav_", stem, re.IGNORECASE)
    if new_name_match:
        fund_code = new_name_match.group(1).upper()
        short_name = new_name_match.group(2)
        return f"{fund_code}_{sanitize_label(short_name)}"

    legacy_match = re.search(r"manulife_([A-Za-z0-9]+)_nav_", stem, re.IGNORECASE)
    if legacy_match:
        fund_code = legacy_match.group(1).upper()
        short_name = FUND_CODE_TO_SHORT_NAME.get(fund_code, fund_code)
        return f"{fund_code}_{sanitize_label(short_name)}"

    return sanitize_label(stem)


def ensure_output_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    TUNINGS_DIR.mkdir(parents=True, exist_ok=True)


def resolve_input_csv_path(csv_file):
    candidate = Path(csv_file)
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate.resolve()
    data_candidate = DATA_DIR / candidate
    if data_candidate.exists():
        return data_candidate.resolve()
    return candidate.resolve()

def csv_str_to_int_list(value, default=None):
    if not value:
        return default if default is not None else []

    if isinstance(value, str):
        return [int(x.strip()) for x in value.split(",") if x.strip()]

    raise ValueError("Expected comma-separated string")

def normalize_pop_ranges(value, default=[10]):
    if value is None:
        return default

    # argparse + nargs="+" always returns a list
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, int):
                result.append(item)
            elif isinstance(item, str):
                result.extend(csv_str_to_int_list(item))
            else:
                raise ValueError("Invalid pop_ranges/gen_ranges element. e.g. 10,20 ")
        return result

    if isinstance(value, int):
        return [value]

    if isinstance(value, str):
        return csv_str_to_int_list(value, default)

    raise ValueError("Invalid pop_ranges/gen_ranges input")

def normalize_gen_ranges(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        return [int(x) for x in value.split(",")]
    raise ValueError("Invalid gen_ranges input")

def normalize_float_ranges(value, default=None):
    if value is None:
        return default
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, (float, int)):
                result.append(float(item))
            elif isinstance(item, str):
                result.extend(float(x.strip()) for x in item.split(",") if x.strip())
            else:
                raise ValueError("Invalid float range element")
        return result
    if isinstance(value, (float, int)):
        return [float(value)]
    if isinstance(value, str):
        return [float(x.strip()) for x in value.split(",") if x.strip()]
    raise ValueError("Invalid float range input")


def normalize_ema_bounds(value, label, minimum=1):
    if value is None or len(value) != 2:
        raise ValueError(f"{label} requires exactly two values: MIN MAX")
    lower, upper = int(value[0]), int(value[1])
    if lower < minimum:
        raise ValueError(f"{label} minimum must be >= {minimum}")
    if lower > upper:
        raise ValueError(f"{label} minimum must be <= maximum")
    return (lower, upper)


def validate_ema_bounds(short_bounds, long_bounds):
    if long_bounds[1] <= short_bounds[0]:
        raise ValueError("long EMA maximum must be greater than short EMA minimum")
    return short_bounds, long_bounds


def log_print(message):
    """Print to console and write to log file"""
    print(message)
    if log_file:
        log_file.write(message + '\n')
        log_file.flush()  # Ensure immediate write

def handler(signum, frame):
    log_print("\nCtrl+C detected, exiting...")
    if log_file:
        log_file.close()
    os._exit(1)

def safe_symbol_name(symbol):
    """Create a filesystem-safe label from a market symbol."""
    safe_chars = [c if c.isalnum() or c in ("-", "_") else "_" for c in symbol]
    return "".join(safe_chars).strip("_") or "symbol"

def download_market_data(symbol, years=2, interval="1d"):
    """Download market data from Yahoo Finance and save it to a local CSV."""
    if yf is None:
        raise ImportError("yfinance is not installed. Install it with: pip install yfinance")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    end_date = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    start_date = end_date - pd.DateOffset(years=years)

    print(
        f"Downloading {symbol} from {start_date.strftime('%Y-%m-%d')} "
        f"to {(end_date - pd.Timedelta(days=1)).strftime('%Y-%m-%d')}..."
    )
    df_downloaded = yf.download(
        symbol,
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False
    )

    if df_downloaded.empty:
        raise ValueError(f"No data downloaded for {symbol}")

    if isinstance(df_downloaded.columns, pd.MultiIndex):
        df_downloaded.columns = df_downloaded.columns.get_level_values(0)

    df_downloaded = df_downloaded.reset_index()
    keep_cols = [
        col for col in ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
        if col in df_downloaded.columns
    ]
    df_downloaded = df_downloaded[keep_cols]

    csv_file = DATA_DIR / f"{safe_symbol_name(symbol)}-{years}y-{pd.Timestamp.today():%Y%m%d}.csv"
    df_downloaded.to_csv(csv_file, index=False)
    print(f"Saved {symbol} data to {csv_file} ({len(df_downloaded)} rows)")
    return str(csv_file)

def calculate_ema(prices, period):
    """Calculate Exponential Moving Average"""
    return prices.ewm(span=period, adjust=False).mean()

def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index with proper handling of division by zero"""
    delta = prices.diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs.replace([np.inf, -np.inf], np.nan).fillna(0)))
    # Handle cases where avg_loss == 0
    rsi[avg_loss == 0] = 100.0
    # Handle cases where avg_gain == 0 and avg_loss == 0
    rsi[(avg_gain == 0) & (avg_loss == 0)] = 50.0
    # Handle NaN (early periods or no movement)
    rsi = rsi.fillna(50.0)  # Neutral value for no movement
    return rsi


def portfolio_value_from_state(shares, cash, price):
    return (shares * price) + cash


def calculate_position_fraction(shares, cash, price):
    total_value = portfolio_value_from_state(shares, cash, price)
    if total_value <= 0 or price <= 0:
        return 0.0
    return max(0.0, (shares * price) / total_value)


def rebalance_to_target_exposure(shares, cash, price, target_exposure, entry_price=0.0):
    """Move holdings toward a target long-only exposure, allowing explicit leverage."""
    total_value = portfolio_value_from_state(shares, cash, price)
    if total_value <= 0 or price <= 0:
        return shares, cash, entry_price

    clipped_target = max(0.0, float(target_exposure))
    target_shares = (total_value * clipped_target) / price
    share_delta = target_shares - shares

    if share_delta > 1e-12:
        cost = share_delta * price
        existing_cost_basis = shares * entry_price if shares > 0 and entry_price > 0 else 0.0
        new_cost_basis = share_delta * price
        cash -= cost
        shares = target_shares
        entry_price = ((existing_cost_basis + new_cost_basis) / shares) if shares > 0 else 0.0
    elif share_delta < -1e-12:
        sold_shares = -share_delta
        cash += sold_shares * price
        shares = target_shares
        if shares <= 1e-12:
            shares = 0.0
            entry_price = 0.0

    return shares, cash, entry_price

def backtest_enhanced_dual_ema(df, short_ema, long_ema, initial_capital=10000,
                              use_rsi_filter=False, rsi_oversold=30, rsi_overbought=70, rsi_period=14,
                              use_trend_filter=False, trend_period=100,
                              use_stop_loss=True, stop_loss_pct=5.0,
                              use_take_profit=True, take_profit_pct=10.0,
                              cooldown_period=3,
                              dip_threshold_pct=5.0,
                              dip_lookback_days=20,
                              rebound_threshold_pct=3.0,
                              recovery_window_days=10,
                              drawdown_exit_pct=3.0,
                              reentry_rebound_pct=2.0,
                              start_invested=False,
                              debug=False,
                              initial_state=None,
                              trade_start_idx=0,
                              return_state=False,
                              strategy_profile_name="generic",
                              exposure_multiplier=None):
    """Index-tuned dual EMA strategy that prefers trend persistence."""
    df = df.copy()
    profile_settings = get_strategy_profile_settings(strategy_profile_name)
    execution_mode = profile_settings.get('execution_mode', 'drawdown_reentry')
    effective_drawdown_exit_pct = drawdown_exit_pct * profile_settings['drawdown_exit_multiplier']
    effective_reentry_rebound_pct = reentry_rebound_pct * profile_settings['reentry_rebound_multiplier']
    effective_cooldown_period = cooldown_period + profile_settings['cooldown_extra_periods']
    always_invested = profile_settings.get("always_invested", False)
    disable_timing_exits = profile_settings.get("disable_timing_exits", False)
    disable_stop_loss = profile_settings.get("disable_stop_loss", False)
    disable_take_profit = profile_settings.get("disable_take_profit", False)
    if exposure_multiplier is None:
        exposure_multiplier = profile_settings.get("default_exposure_multiplier", 1.0)
    exposure_multiplier = max(0.0, float(exposure_multiplier))
    partial_exit_target_exposure = profile_settings.get('partial_exit_target_exposure', 0.5)
    full_exit_drawdown_pct = effective_drawdown_exit_pct * profile_settings.get('full_exit_drawdown_multiplier', 1.0)

    # Ensure Date index if not present
    if 'Date' not in df.columns and hasattr(df.index, 'name') and df.index.name == 'Date':
        df = df.reset_index()

    # Compute RSI with provided period
    df['RSI'] = calculate_rsi(df['NAV'], rsi_period)

    # Calculate EMAs
    short_ema_col = f'EMA_{int(short_ema)}'
    long_ema_col = f'EMA_{int(long_ema)}'
    df[short_ema_col] = calculate_ema(df['NAV'], short_ema)
    df[long_ema_col] = calculate_ema(df['NAV'], long_ema)
    df['Short_EMA_Value'] = df[short_ema_col]
    df['Long_EMA_Value'] = df[long_ema_col]
    df['Long_EMA_Slope_5'] = df['Long_EMA_Value'].diff(5).fillna(0.0)

    # Calculate additional indicators
    if use_trend_filter:
        df[f'Trend_EMA_{trend_period}'] = calculate_ema(df['NAV'], trend_period)

    df['Recent_High'] = df['NAV'].rolling(window=dip_lookback_days).max()
    df['Drawdown_Pct'] = (df['NAV'] - df['Recent_High']) / df['Recent_High'] * 100
    df['Rebound_Pct'] = df['NAV'].pct_change(periods=1).rolling(window=5).sum() * 100
    df['In_Dip'] = df['Drawdown_Pct'] <= -dip_threshold_pct
    df['In_Recovery'] = False
    recovery_counter = [0] * len(df)
    for i in range(1, len(df)):
        if df['In_Dip'].iloc[i - 1] and df['Rebound_Pct'].iloc[i] >= rebound_threshold_pct:
            recovery_counter[i:i + recovery_window_days] = [1] * min(recovery_window_days, len(df) - i)
    df['In_Recovery'] = [bool(c) for c in recovery_counter]

    df['EMA_Signal'] = 0
    df.loc[df[short_ema_col] > df[long_ema_col], 'EMA_Signal'] = 1
    df.loc[df[short_ema_col] <= df[long_ema_col], 'EMA_Signal'] = -1

    # In index mode, sell only when the crossdown aligns with a falling long trend.
    df['Sell_Regime_OK'] = (
        (df['EMA_Signal'] == -1)
        & (df['NAV'] < df['Long_EMA_Value'])
        & (df['Long_EMA_Slope_5'] < 0)
    )
    df['Recovery_Buy_Override'] = (
        df['In_Recovery']
        & ((df['NAV'] >= df['Long_EMA_Value']) | (df['Long_EMA_Slope_5'] >= 0))
    )

    df['Final_Signal'] = 0
    df.loc[df['EMA_Signal'] == 1, 'Final_Signal'] = 1
    df.loc[df['Sell_Regime_OK'], 'Final_Signal'] = -1
    df.loc[df['Recovery_Buy_Override'], 'Final_Signal'] = 1
    df['RSI_Filter_Block'] = False
    df['RSI_Sell_Block'] = False
    df['RSI_Buy_Block'] = False
    df['Trend_Filter_Block'] = False

    # RSI guards exits during oversold dips and entries during overbought spikes.
    if use_rsi_filter:
        rsi_sell_block = df['Sell_Regime_OK'] & (df['RSI'] < rsi_oversold)
        df.loc[rsi_sell_block, 'Final_Signal'] = 0
        df.loc[rsi_sell_block, 'RSI_Filter_Block'] = True
        df.loc[rsi_sell_block, 'RSI_Sell_Block'] = True

        rsi_buy_block = (df['Final_Signal'] > 0) & (df['RSI'] > rsi_overbought)
        df.loc[rsi_buy_block, 'Final_Signal'] = 0
        df.loc[rsi_buy_block, 'RSI_Filter_Block'] = True
        df.loc[rsi_buy_block, 'RSI_Buy_Block'] = True

    if use_trend_filter:
        trend_buy_block = (df['EMA_Signal'] == 1) & (df['NAV'] < df[f'Trend_EMA_{trend_period}'])
        trend_sell_block = (df['EMA_Signal'] == -1) & (df['NAV'] > df[f'Trend_EMA_{trend_period}'])
        df.loc[trend_buy_block, 'Final_Signal'] = 0
        df.loc[trend_sell_block, 'Final_Signal'] = 0
        df.loc[trend_buy_block | trend_sell_block, 'Trend_Filter_Block'] = True

    initial_state = initial_state or {}
    position = float(initial_state.get('position', 0.0))
    shares = float(initial_state.get('shares', 0.0))
    cash = float(initial_state.get('cash', initial_capital))
    portfolio_values = []
    entry_price = float(initial_state.get('entry_price', 0.0))
    peak_price = float(initial_state.get('peak_price', entry_price))
    cash_low_watermark = float(initial_state.get('cash_low_watermark', 0.0))
    trades = []
    cooldown_counter = int(initial_state.get('cooldown_counter', 0))

    trade_decisions = []
    df['Position'] = 0.0
    df['Exposure'] = 0.0

    def set_target_exposure(price, target_exposure):
        nonlocal shares, cash, position, entry_price, peak_price, cash_low_watermark
        before_value = portfolio_value_from_state(shares, cash, price)
        shares, cash, entry_price = rebalance_to_target_exposure(
            shares, cash, price, target_exposure, entry_price
        )
        position = calculate_position_fraction(shares, cash, price)
        if position > 0:
            peak_price = price
        if position >= 1e-9:
            cash_low_watermark = 0
        return before_value

    def exit_position(price):
        nonlocal shares, cash, position, entry_price, peak_price, cash_low_watermark
        equity = portfolio_value_from_state(shares, cash, price)
        shares = 0
        cash = equity
        position = 0.0
        entry_price = 0
        peak_price = 0
        cash_low_watermark = price
        return equity

    for i in range(len(df)):
        current_price = df['NAV'].iloc[i]
        current_signal = df['Final_Signal'].iloc[i]
        ema_signal = df['EMA_Signal'].iloc[i]
        current_date = df['Date'].iloc[i] if 'Date' in df.columns else df.index[i]
        trade_marker = current_date

        rsi_val = df['RSI'].iloc[i]
        short_ema_val = df[short_ema_col].iloc[i]
        long_ema_val = df[long_ema_col].iloc[i]

        position = calculate_position_fraction(shares, cash, current_price)

        if i < trade_start_idx:
            warmup_value = portfolio_value_from_state(shares, cash, current_price)
            trade_decisions.append({
                'Index': i,
                'Date': current_date,
                'Price': current_price,
                'Position': position,
                'EMA_Signal': ema_signal,
                'Final_Signal': current_signal,
                'RSI': rsi_val,
                'Cooldown': cooldown_counter,
                'Action': 'WARMUP',
                'Portfolio_Value': warmup_value,
                'Exposure': position
            })
            df.at[df.index[i] if isinstance(df.index, pd.DatetimeIndex) else i, 'Position'] = position
            df.at[df.index[i] if isinstance(df.index, pd.DatetimeIndex) else i, 'Exposure'] = position
            portfolio_values.append(warmup_value)
            continue

        if position > 0 and peak_price <= 0:
            peak_price = current_price
        if position < 1 and cash > 0 and cash_low_watermark <= 0:
            cash_low_watermark = current_price

        if cooldown_counter > 0:
            cooldown_counter -= 1

        exit_reason = None
        entry_blocked_reason = None

        if position > 0 and entry_price > 0:
            price_change_pct = (current_price - entry_price) / entry_price * 100
            peak_price = max(peak_price, current_price)
            if use_stop_loss and not disable_stop_loss and price_change_pct <= -stop_loss_pct:
                exit_value = exit_position(current_price)
                trades.append(('STOP_LOSS', trade_marker, current_price, exit_value))
                exit_reason = f"STOP_LOSS ({price_change_pct:.2f}%)"
                cooldown_counter = effective_cooldown_period
            elif use_take_profit and not disable_take_profit and price_change_pct >= take_profit_pct:
                exit_value = exit_position(current_price)
                trades.append(('TAKE_PROFIT', trade_marker, current_price, exit_value))
                exit_reason = f"TAKE_PROFIT ({price_change_pct:.2f}%)"

        if position < 1:
            rebound_from_low_pct = ((current_price - cash_low_watermark) / cash_low_watermark * 100) if cash_low_watermark > 0 else 0
            reentry_threshold = effective_reentry_rebound_pct
            if position > 0:
                reentry_threshold *= profile_settings.get('partial_reentry_rebound_multiplier', 1.0)
            if execution_mode == "regime_signal":
                signal_reentry_buffer_pct = (
                    effective_reentry_rebound_pct
                    * profile_settings.get('signal_reentry_buffer_scale', 0.0)
                )
                reentry_conditions_met = (
                    current_signal > 0
                    and current_price >= short_ema_val * (1 + signal_reentry_buffer_pct / 100)
                )
            else:
                reentry_conditions_met = (
                    current_price > short_ema_val
                    and rebound_from_low_pct >= reentry_threshold
                )
            if profile_settings['require_price_above_long_ema_for_reentry']:
                reentry_conditions_met = reentry_conditions_met and current_price >= long_ema_val
            if profile_settings['require_positive_long_slope_for_reentry']:
                reentry_conditions_met = reentry_conditions_met and df['Long_EMA_Slope_5'].iloc[i] >= 0
            if always_invested and cash > 0:
                reentry_conditions_met = True
            rsi_entry_blocked = use_rsi_filter and rsi_val > rsi_overbought
            if rsi_entry_blocked and reentry_conditions_met:
                reentry_conditions_met = False
                entry_blocked_reason = f"RSI_OVERBOUGHT ({rsi_val:.1f} > {rsi_overbought})"

            if i == trade_start_idx and start_invested and cash > 0 and cooldown_counter == 0 and not rsi_entry_blocked:
                entry_value = set_target_exposure(current_price, exposure_multiplier)
                trades.append(('BUY', trade_marker, current_price, entry_value))

                if debug:
                    rsi_display = f"{rsi_val:.1f}" if not np.isnan(rsi_val) else "N/A"
                    log_print(f"BUY_START: {i:3d} {current_date} | Price: {current_price:.3f} | Shares: {shares:.2f} | Exposure: {position:.2f}x")
                    log_print(f"           EMA: {short_ema_val:.3f}/{long_ema_val:.3f} | RSI: {rsi_display}")
                    log_print("")
            elif reentry_conditions_met and (cooldown_counter == 0 or position > 0):
                previous_position = position
                entry_value = set_target_exposure(current_price, exposure_multiplier)
                trade_type = 'BUY' if previous_position <= 0 else 'BUY_TOPUP'
                trades.append((trade_type, trade_marker, current_price, entry_value))

                if debug:
                    rsi_display = f"{rsi_val:.1f}" if not np.isnan(rsi_val) else "N/A"
                    action_label = "BUY" if trade_type == 'BUY' else "BUY_TOPUP"
                    log_print(f"{action_label}: {i:3d} {current_date} | Price: {current_price:.3f} | Shares: {shares:.2f} | Exposure: {position:.2f}x")
                    log_print(f"     EMA: {short_ema_val:.3f}/{long_ema_val:.3f} | RSI: {rsi_display}")
                    if execution_mode == "regime_signal":
                        signal_reentry_buffer_pct = (
                            effective_reentry_rebound_pct
                            * profile_settings.get('signal_reentry_buffer_scale', 0.0)
                        )
                        log_print(f"     Regime Buy Signal: {current_signal} | Buy Buffer: {signal_reentry_buffer_pct:.2f}%")
                    else:
                        log_print(f"     Rebound From Low: {rebound_from_low_pct:.2f}% | Threshold: {reentry_threshold:.2f}%")
                    log_print("")
            elif rsi_entry_blocked and position < 1 and cash > 0:
                entry_blocked_reason = entry_blocked_reason or f"RSI_OVERBOUGHT ({rsi_val:.1f} > {rsi_overbought})"
            elif reentry_conditions_met and cooldown_counter > 0 and position <= 0:
                entry_blocked_reason = f"COOLDOWN ({cooldown_counter} periods remaining)"
            else:
                cash_low_watermark = min(cash_low_watermark, current_price) if cash_low_watermark > 0 else current_price
        if exit_reason is None and position > 0:
            drawdown_from_peak_pct = ((current_price - peak_price) / peak_price * 100) if peak_price > 0 else 0
            if execution_mode == "regime_signal":
                exit_conditions_met = (
                    current_signal < 0
                    and drawdown_from_peak_pct <= -effective_drawdown_exit_pct
                )
            else:
                exit_conditions_met = (
                    drawdown_from_peak_pct <= -effective_drawdown_exit_pct
                    and current_price < short_ema_val
                )
            if profile_settings['require_price_below_long_ema_for_exit']:
                exit_conditions_met = exit_conditions_met and current_price < long_ema_val
            if profile_settings['require_negative_long_slope_for_exit']:
                exit_conditions_met = exit_conditions_met and df['Long_EMA_Slope_5'].iloc[i] < 0
            if disable_timing_exits:
                exit_conditions_met = False

            if exit_conditions_met:
                full_exit_required = (
                    not profile_settings.get('enable_partial_derisk', False)
                    or drawdown_from_peak_pct <= -full_exit_drawdown_pct
                )
                partial_exit_required = (
                    profile_settings.get('enable_partial_derisk', False)
                    and position > (partial_exit_target_exposure + 1e-9)
                    and not full_exit_required
                )

                if full_exit_required:
                    exit_value = exit_position(current_price)
                    trades.append(('SELL', trade_marker, current_price, exit_value))
                    exit_reason = f"DRAWDOWN_EXIT ({drawdown_from_peak_pct:.2f}%)"
                    cooldown_counter = effective_cooldown_period
                elif partial_exit_required:
                    previous_position = position
                    partial_value = set_target_exposure(current_price, partial_exit_target_exposure)
                    trades.append(('PARTIAL_SELL', trade_marker, current_price, partial_value))
                    exit_reason = (
                        f"PARTIAL_DRAWDOWN_EXIT ({drawdown_from_peak_pct:.2f}%, "
                        f"{previous_position:.2f}->{position:.2f})"
                    )
                    cash_low_watermark = current_price

        if exit_reason and debug:
            log_print(f"{exit_reason}: {i:3d} {current_date} | Price: {current_price:.3f}")
            log_print(f"              Portfolio Value: {portfolio_value_from_state(shares, cash, current_price):.2f}")
            log_print("")

        if entry_blocked_reason and debug and i % 20 == 0:
            rsi_display = f"{rsi_val:.1f}" if not np.isnan(rsi_val) else "N/A"
            log_print(f"BLOCKED: {i:3d} {current_date} | {entry_blocked_reason}")
            log_print(f"         EMA: {short_ema_val:.3f}/{long_ema_val:.3f} | RSI: {rsi_display}")
            log_print("")

        trade_decisions.append({
            'Index': i,
            'Date': current_date,
            'Price': current_price,
            'Position': position,
            'EMA_Signal': ema_signal,
            'Final_Signal': current_signal,
            'RSI': rsi_val,
            'Cooldown': cooldown_counter,
            'Action': exit_reason or entry_blocked_reason or ('HOLD' if position > 0 else 'WAIT'),
            'Portfolio_Value': portfolio_value_from_state(shares, cash, current_price),
            'Exposure': position
        })

        df.at[df.index[i] if isinstance(df.index, pd.DatetimeIndex) else i, 'Position'] = position
        df.at[df.index[i] if isinstance(df.index, pd.DatetimeIndex) else i, 'Exposure'] = position

        portfolio_value = portfolio_value_from_state(shares, cash, current_price)
        portfolio_values.append(portfolio_value)

    df['Portfolio_Value'] = portfolio_values

    analysis_df = df.iloc[trade_start_idx:].copy() if trade_start_idx > 0 else df.copy()
    analysis_portfolio_values = portfolio_values[trade_start_idx:] if trade_start_idx > 0 else portfolio_values
    total_return = (analysis_df['Portfolio_Value'].iloc[-1] - initial_capital) / initial_capital * 100 if len(analysis_df) > 0 else 0
    num_trades = len(trades)
    buy_trades = [t for t in trades if t[0] == 'BUY']
    sell_trades = [t for t in trades if t[0] in ['SELL', 'STOP_LOSS', 'TAKE_PROFIT']]

    if len(buy_trades) > len(sell_trades):
        buy_trades = buy_trades[:len(sell_trades)]

    if len(buy_trades) > 0 and len(sell_trades) > 0:
        returns = []
        for i in range(min(len(buy_trades), len(sell_trades))):
            buy_value = buy_trades[i][3]
            sell_value = sell_trades[i][3]
            trade_return = (sell_value - buy_value) / buy_value
            returns.append(trade_return)
        
        win_rate = len([r for r in returns if r > 0]) / len(returns) * 100 if returns else 0
        avg_return_per_trade = np.mean(returns) * 100 if returns else 0
    else:
        win_rate = 0
        avg_return_per_trade = 0

    decisions_df = pd.DataFrame(trade_decisions)
    if trade_start_idx > 0:
        decisions_df = decisions_df.iloc[trade_start_idx:].reset_index(drop=True)

    returns_series = pd.Series(analysis_portfolio_values).pct_change().dropna()
    sharpe = returns_series.mean() / returns_series.std() * np.sqrt(252) if len(returns_series) > 0 and returns_series.std() != 0 else 0
    portfolio_series = pd.Series(analysis_portfolio_values)
    max_dd = ((portfolio_series.cummax() - portfolio_series) / portfolio_series.cummax() * 100).max() if len(portfolio_series) > 0 else 0

    final_state = {
        'position': position,
        'shares': shares,
        'cash': cash,
        'entry_price': entry_price,
        'peak_price': peak_price,
        'cash_low_watermark': cash_low_watermark,
        'cooldown_counter': cooldown_counter,
        'exposure_multiplier': exposure_multiplier
    }

    if return_state:
        return analysis_df, total_return, num_trades, trades, win_rate, avg_return_per_trade, decisions_df, sharpe, max_dd, final_state

    return analysis_df, total_return, num_trades, trades, win_rate, avg_return_per_trade, decisions_df, sharpe, max_dd

def buy_and_hold_strategy(df, initial_capital=10000):
    """Calculate buy and hold returns"""
    if len(df) == 0:
        return pd.Series(dtype=float), 0
    start_price = df['NAV'].iloc[0]
    end_price = df['NAV'].iloc[-1]
    shares = initial_capital / start_price
    final_value = shares * end_price
    total_return = (final_value - initial_capital) / initial_capital * 100
    
    # Create portfolio value series for plotting
    portfolio_values = (df['NAV'] / start_price) * initial_capital
    
    return portfolio_values, total_return

def calculate_index_strategy_metrics(df_result, trades, initial_capital=10000, long_ema=None):
    """Calculate benchmark-aware summary metrics for index runs."""
    metrics = {
        'adaptive_return': 0.0,
        'buy_hold_return': 0.0,
        'excess_return': 0.0,
        'sharpe': 0.0,
        'max_dd': 0.0,
        'trade_count': len(trades),
        'time_invested_pct': 0.0,
        'uptrend_cash_pct': 0.0,
        'missed_upside_after_exit_pct': 0.0,
        'stop_loss_count': sum(1 for trade in trades if trade[0] == 'STOP_LOSS')
    }

    if df_result is None or len(df_result) == 0:
        return metrics

    portfolio_series = df_result['Portfolio_Value'] if 'Portfolio_Value' in df_result.columns else pd.Series([initial_capital])
    metrics['adaptive_return'] = (portfolio_series.iloc[-1] - initial_capital) / initial_capital * 100 if len(portfolio_series) > 0 else 0.0

    _, buy_hold_return = buy_and_hold_strategy(df_result, initial_capital=initial_capital)
    metrics['buy_hold_return'] = buy_hold_return
    metrics['excess_return'] = metrics['adaptive_return'] - buy_hold_return

    returns_series = portfolio_series.pct_change().dropna()
    if len(returns_series) > 0 and returns_series.std() != 0:
        metrics['sharpe'] = returns_series.mean() / returns_series.std() * np.sqrt(252)

    if len(portfolio_series) > 0:
        metrics['max_dd'] = ((portfolio_series.cummax() - portfolio_series) / portfolio_series.cummax() * 100).max()

    if 'Position' in df_result.columns and len(df_result) > 0:
        metrics['time_invested_pct'] = df_result['Position'].fillna(0).clip(lower=0, upper=1).mean() * 100

    if 'NAV' in df_result.columns and len(df_result) > 0:
        if 'Long_EMA_Value' in df_result.columns:
            long_ema_series = df_result['Long_EMA_Value']
        elif long_ema is not None and f'EMA_{int(long_ema)}' in df_result.columns:
            long_ema_series = df_result[f'EMA_{int(long_ema)}']
        else:
            long_ema_series = None

        if long_ema_series is not None and 'Position' in df_result.columns:
            uptrend_cash_fraction = (
                (1 - df_result['Position'].fillna(0).clip(lower=0, upper=1))
                .where(df_result['NAV'] > long_ema_series, 0.0)
            )
            metrics['uptrend_cash_pct'] = uptrend_cash_fraction.mean() * 100

    metrics['missed_upside_after_exit_pct'] = calculate_missed_upside_after_exits(df_result, trades)

    return metrics

def calculate_missed_upside_after_exits(df_result, trades):
    """Sum positive rallies missed after reducing exposure, weighted by exposure cut."""
    if df_result is None or len(df_result) == 0 or 'NAV' not in df_result.columns:
        return 0.0

    if 'Position' in df_result.columns:
        positions = df_result['Position'].fillna(0).clip(lower=0, upper=1).to_numpy(dtype=float)
        prices = df_result['NAV'].to_numpy(dtype=float)
        position_deltas = np.diff(positions, prepend=positions[0])
        missed_upside = 0.0

        for exit_pos in np.where(position_deltas < -1e-9)[0]:
            exited_fraction = min(1.0, max(0.0, -position_deltas[exit_pos]))
            if exited_fraction <= 0 or prices[exit_pos] <= 0:
                continue

            next_buy_positions = np.where(position_deltas[exit_pos + 1:] > 1e-9)[0]
            if len(next_buy_positions) > 0:
                end_pos = exit_pos + 1 + int(next_buy_positions[0])
            else:
                end_pos = len(prices) - 1

            if end_pos <= exit_pos:
                continue

            best_missed_price = np.max(prices[exit_pos:end_pos + 1])
            if best_missed_price > prices[exit_pos]:
                missed_upside += ((best_missed_price - prices[exit_pos]) / prices[exit_pos] * 100) * exited_fraction

        if missed_upside > 0:
            return missed_upside

    if not trades:
        return 0.0

    def trade_position(marker):
        index_matches = np.where(df_result.index == marker)[0]
        if len(index_matches) > 0:
            return int(index_matches[0])

        if 'Date' in df_result.columns:
            try:
                marker_date = pd.to_datetime(marker)
                date_matches = np.where(pd.to_datetime(df_result['Date']) == marker_date)[0]
                if len(date_matches) > 0:
                    return int(date_matches[0])
            except Exception:
                pass

        if isinstance(marker, (int, np.integer)) and 0 <= int(marker) < len(df_result):
            return int(marker)

        return None

    positioned_trades = []
    for trade_type, marker, price, value in trades:
        pos = trade_position(marker)
        if pos is not None:
            positioned_trades.append((trade_type, pos, price, value))

    if not positioned_trades:
        return 0.0

    missed_upside = 0.0
    for idx, (trade_type, exit_pos, exit_price, _) in enumerate(positioned_trades):
        if trade_type not in ['SELL', 'STOP_LOSS', 'TAKE_PROFIT'] or exit_price <= 0:
            continue

        next_buy_pos = None
        for next_trade_type, next_pos, _, _ in positioned_trades[idx + 1:]:
            if next_trade_type == 'BUY':
                next_buy_pos = next_pos
                break

        end_pos = next_buy_pos if next_buy_pos is not None else len(df_result) - 1
        if end_pos <= exit_pos:
            continue

        cash_nav = df_result['NAV'].iloc[exit_pos:end_pos + 1]
        if len(cash_nav) == 0:
            continue

        best_missed_price = cash_nav.max()
        if best_missed_price > exit_price:
            missed_upside += (best_missed_price - exit_price) / exit_price * 100

    return missed_upside

###########################################################
def genetic_optimize_params(df, short_ema_bounds=DEFAULT_SHORT_EMA_BOUNDS, long_ema_bounds=DEFAULT_LONG_EMA_BOUNDS,
                           sl_bounds=(8, 15), cd_bounds=(0, 3),
                           drawdown_exit_bounds=(2.5, 4.0), reentry_rebound_bounds=(1.0, 3.0),
                           pop_size=50, generations=50, mutation_rate=0.1, crossover_rate=0.7,
                           initial_capital=10000, strategy_profile_name="generic",
                           ga_seed_value=None, **kwargs):
    """GA optimizer for index behavior using benchmark-relative fitness."""
    import pygad
    profile_settings = get_strategy_profile_settings(strategy_profile_name)
    short_ema_bounds, long_ema_bounds, sl_bounds, cd_bounds, drawdown_exit_bounds, reentry_rebound_bounds = resolve_profile_gene_bounds(
        strategy_profile_name,
        short_ema_bounds,
        long_ema_bounds,
        sl_bounds,
        cd_bounds,
        drawdown_exit_bounds,
        reentry_rebound_bounds,
    )

    gene_space = [
        {'low': short_ema_bounds[0], 'high': short_ema_bounds[1] + 1, 'step': 1},
        {'low': long_ema_bounds[0], 'high': long_ema_bounds[1] + 1, 'step': 1},
        {'low': sl_bounds[0], 'high': sl_bounds[1]},
        {'low': cd_bounds[0], 'high': cd_bounds[1] + 1, 'step': 1},
        {'low': drawdown_exit_bounds[0], 'high': drawdown_exit_bounds[1]},
        {'low': reentry_rebound_bounds[0], 'high': reentry_rebound_bounds[1]},
        {'low': DEFAULT_RSI_OVERSOLD_BOUNDS[0], 'high': DEFAULT_RSI_OVERSOLD_BOUNDS[1] + 1, 'step': 1},
        {'low': DEFAULT_RSI_OVERBOUGHT_BOUNDS[0], 'high': DEFAULT_RSI_OVERBOUGHT_BOUNDS[1] + 1, 'step': 1},
    ]
    exposure_bounds = get_exposure_bounds(strategy_profile_name)
    uses_exposure_gene = exposure_bounds[1] > exposure_bounds[0]
    if uses_exposure_gene:
        gene_space.append({'low': exposure_bounds[0], 'high': exposure_bounds[1]})
    num_genes = len(gene_space)

    def fitness_func(ga_instance, solution, solution_idx):
        short_ema, long_ema, sl, cd, drawdown_exit_pct, reentry_rebound_pct, rsi_oversold, rsi_overbought = solution[:8]
        exposure_multiplier = float(solution[8]) if uses_exposure_gene else profile_settings.get("default_exposure_multiplier", 1.0)
        short_ema = int(short_ema)
        long_ema = int(long_ema)
        cd = int(cd)
        rsi_oversold = int(rsi_oversold)
        rsi_overbought = int(rsi_overbought)

        if short_ema >= long_ema or (long_ema - short_ema) < 40 or rsi_oversold >= rsi_overbought:
            return -np.inf

        split_idx = int(len(df) * 0.8)
        df_train = df.iloc[:split_idx].copy()
        df_test = df.iloc[split_idx:].copy()

        if len(df_test) < 20:
            multiplier = 1.0
        else:
            train_result, _, _, train_trades, _, _, _, _, _ = backtest_enhanced_dual_ema(
                df_train, short_ema, long_ema, initial_capital,
                use_rsi_filter=True, rsi_oversold=rsi_oversold,
                rsi_overbought=rsi_overbought, rsi_period=DEFAULT_RSI_PERIOD,
                use_stop_loss=True, stop_loss_pct=sl, use_take_profit=False,
                cooldown_period=cd, drawdown_exit_pct=drawdown_exit_pct,
                reentry_rebound_pct=reentry_rebound_pct, start_invested=True, debug=False,
                strategy_profile_name=strategy_profile_name,
                exposure_multiplier=exposure_multiplier
            )
            test_result, _, _, test_trades, _, _, _, _, _ = backtest_enhanced_dual_ema(
                df_test, short_ema, long_ema, initial_capital,
                use_rsi_filter=True, rsi_oversold=rsi_oversold,
                rsi_overbought=rsi_overbought, rsi_period=DEFAULT_RSI_PERIOD,
                use_stop_loss=True, stop_loss_pct=sl, use_take_profit=False,
                cooldown_period=cd, drawdown_exit_pct=drawdown_exit_pct,
                reentry_rebound_pct=reentry_rebound_pct, start_invested=True, debug=False,
                strategy_profile_name=strategy_profile_name,
                exposure_multiplier=exposure_multiplier
            )
            train_metrics = calculate_index_strategy_metrics(train_result, train_trades, initial_capital, long_ema)
            test_metrics = calculate_index_strategy_metrics(test_result, test_trades, initial_capital, long_ema)
            divergence = abs(train_metrics['excess_return'] - test_metrics['excess_return']) / 100
            multiplier = max(0.01, 1 - divergence)

        df_result, _, num_trades, trades, _, _, _, _, _ = backtest_enhanced_dual_ema(
            df, short_ema, long_ema, initial_capital,
            use_rsi_filter=True, rsi_oversold=rsi_oversold,
            rsi_overbought=rsi_overbought, rsi_period=DEFAULT_RSI_PERIOD,
            use_stop_loss=True, stop_loss_pct=sl, use_take_profit=False,
            cooldown_period=cd, drawdown_exit_pct=drawdown_exit_pct,
            reentry_rebound_pct=reentry_rebound_pct, start_invested=True, debug=False,
            strategy_profile_name=strategy_profile_name,
            exposure_multiplier=exposure_multiplier
        )

        metrics = calculate_index_strategy_metrics(df_result, trades, initial_capital, long_ema)
        missed_upside_penalty = (
            profile_settings['missed_upside_after_exit_weight']
            * metrics['missed_upside_after_exit_pct']
        )
        base_fitness = (
            (2.0 * metrics['excess_return'])
            + (6.0 * metrics['sharpe'])
            - (0.30 * metrics['max_dd'])
            - (0.10 * num_trades)
            - (0.5 * metrics['uptrend_cash_pct'])
            - missed_upside_penalty
        )
        fitness = base_fitness * multiplier
        return fitness if not np.isnan(fitness) else 0

    try:
        window_start = df['Date'].iloc[0] if 'Date' in df.columns else df.index[0]
        window_end = df['Date'].iloc[-1] if 'Date' in df.columns else df.index[-1]
        selected_ga_seed = ga_seed_value
        if selected_ga_seed is None:
            selected_ga_seed = build_deterministic_seed(
                csv_name,
                strategy_profile_name,
                str(window_start),
                str(window_end),
                len(df),
                pop_size,
                generations,
                mutation_rate,
                crossover_rate
            )
        np.random.seed(selected_ga_seed)
        random.seed(selected_ga_seed)
        log_print(
            f" >>> {batch_name} ga10 pop_size={pop_size}, generations={generations}, "
            f"mutation_rate={mutation_rate}, crossover_rate={crossover_rate}, seed={selected_ga_seed}"
        )
        ga_instance = pygad.GA(num_generations=generations,
                               sol_per_pop=pop_size,
                               num_genes=num_genes,
                               num_parents_mating=min(10, pop_size),
                               fitness_func=fitness_func,
                               init_range_low=0,
                               init_range_high=10,
                               mutation_percent_genes=10,
                               mutation_type="random",
                               mutation_by_replacement=True,
                               mutation_num_genes=None,
                               random_mutation_min_val=0,
                               random_mutation_max_val=5,
                               parent_selection_type="sss",
                               keep_parents=1,
                               crossover_type="single_point",
                               gene_space=gene_space,
                               mutation_probability=mutation_rate,
                               crossover_probability=crossover_rate,
                               random_seed=selected_ga_seed)
        
        ga_instance.run()
        
        solution, solution_fitness, solution_idx = ga_instance.best_solution()
        best_params = {
            'short_ema': int(solution[0]),
            'long_ema': int(solution[1]),
            'stop_loss': solution[2],
            'cooldown': int(solution[3]),
            'drawdown_exit_pct': solution[4],
            'reentry_rebound_pct': solution[5],
            'use_rsi_filter': True,
            'rsi_oversold': int(solution[6]),
            'rsi_overbought': int(solution[7]),
            'rsi_period': DEFAULT_RSI_PERIOD,
            'exposure_multiplier': float(solution[8]) if uses_exposure_gene else profile_settings.get("default_exposure_multiplier", 1.0),
            'effective_cooldown': int(solution[3]) + profile_settings['cooldown_extra_periods'],
            'effective_drawdown_exit_pct': solution[4] * profile_settings['drawdown_exit_multiplier'],
            'effective_reentry_rebound_pct': solution[5] * profile_settings['reentry_rebound_multiplier'],
        }
        log_print(
            f"Best : EMA({best_params['short_ema']}, {best_params['long_ema']}), "
            f"SL={best_params['stop_loss']:.2f}, CD={best_params['cooldown']}, "
            f"DDX={best_params['drawdown_exit_pct']:.2f}, RBR={best_params['reentry_rebound_pct']:.2f}, "
            f"RSI={best_params['rsi_oversold']}/{best_params['rsi_overbought']}, "
            f"EXP={best_params['exposure_multiplier']:.2f}x"
        )
        return best_params
    except Exception as e:
        log_print(f"GA optimization error: {e}")
        return None


# Hyperparameter Tuning Function
def tune_ga_hyperparams(df_tune, short_ema_bounds=DEFAULT_SHORT_EMA_BOUNDS, long_ema_bounds=DEFAULT_LONG_EMA_BOUNDS,
                        sl_bounds=(8,15), cd_bounds=(0,3),
                        drawdown_exit_bounds=(2.5,4.0), reentry_rebound_bounds=(1.0,3.0),
                        initial_capital=10000, strategy_profile_name="generic",
                        ga_seed_value=None, mutation_rates_value=None,
                        crossover_rates_value=None, return_best_params=False,
                        run_metadata=None, window_metadata=None,
                        strategy_parameter_metadata=None):
    """Grid search over GA hyperparameters for the index-specific objective."""
    log_print("\n=== GA HYPERPARAMETER TUNING PHASE ===")
    profile_settings = get_strategy_profile_settings(strategy_profile_name)
    short_ema_bounds, long_ema_bounds, sl_bounds, cd_bounds, drawdown_exit_bounds, reentry_rebound_bounds = resolve_profile_gene_bounds(
        strategy_profile_name,
        short_ema_bounds,
        long_ema_bounds,
        sl_bounds,
        cd_bounds,
        drawdown_exit_bounds,
        reentry_rebound_bounds,
    )
    log_print(
        "Profile gene bounds: "
        f"EMA short={short_ema_bounds}, EMA long={long_ema_bounds}, "
        f"SL={sl_bounds}, CD={cd_bounds}, DDX={drawdown_exit_bounds}, "
        f"RBR={reentry_rebound_bounds}, "
        f"RSI={DEFAULT_RSI_OVERSOLD_BOUNDS}/{DEFAULT_RSI_OVERBOUGHT_BOUNDS}, "
        f"EXP={get_exposure_bounds(strategy_profile_name)}"
    )
    mut_ranges = mutation_rates_value if mutation_rates_value else [0.01, 0.05, 0.1, 0.15]
    cross_ranges = crossover_rates_value if crossover_rates_value else [0.6, 0.7, 0.8, 0.9]
    log_print(f"GA search ranges: mutation={mut_ranges}, crossover={cross_ranges}")

    results = []
    best_score = -np.inf
    best_combo = None
    best_combo_params = None

    for pop, gens, mut, cross in itertools.product(pop_ranges, gen_ranges, mut_ranges, cross_ranges):
        best_params = genetic_optimize_params(
            df_tune, short_ema_bounds, long_ema_bounds, sl_bounds, cd_bounds,
            drawdown_exit_bounds, reentry_rebound_bounds,
            pop_size=pop, generations=gens, mutation_rate=mut, crossover_rate=cross,
            initial_capital=initial_capital,
            strategy_profile_name=strategy_profile_name,
            ga_seed_value=ga_seed_value
        )

        if best_params is None:
            log_print(f"  Skipping due to GA error")
            continue

        df_result, _, num_trades, trades, win_rate, _, _, _, _ = backtest_enhanced_dual_ema(
            df_tune, best_params['short_ema'], best_params['long_ema'], initial_capital,
            use_rsi_filter=True,
            rsi_oversold=best_params['rsi_oversold'],
            rsi_overbought=best_params['rsi_overbought'],
            rsi_period=best_params.get('rsi_period', DEFAULT_RSI_PERIOD),
            use_stop_loss=True, stop_loss_pct=best_params['stop_loss'], use_take_profit=False,
            cooldown_period=best_params['cooldown'],
            drawdown_exit_pct=best_params['drawdown_exit_pct'],
            reentry_rebound_pct=best_params['reentry_rebound_pct'],
            start_invested=True, debug=False,
            strategy_profile_name=strategy_profile_name,
            exposure_multiplier=best_params.get('exposure_multiplier', profile_settings.get("default_exposure_multiplier", 1.0))
        )
        metrics = calculate_index_strategy_metrics(df_result, trades, initial_capital, best_params['long_ema'])

        missed_upside_penalty = (
            profile_settings['missed_upside_after_exit_weight']
            * metrics['missed_upside_after_exit_pct']
        )
        score = (
            (2.0 * metrics['excess_return'])
            + (6.0 * metrics['sharpe'])
            - (0.30 * metrics['max_dd'])
            - (0.10 * num_trades)
            - (0.5 * metrics['uptrend_cash_pct'])
            - missed_upside_penalty
        )
        results.append({
            'pop_size': pop, 'generations': gens, 'mutation_rate': mut, 'crossover_rate': cross,
            'best_short_ema': best_params['short_ema'],
            'best_long_ema': best_params['long_ema'],
            'best_stop_loss_pct': best_params['stop_loss'],
            'best_cooldown': best_params['cooldown'],
            'best_drawdown_exit_pct': best_params['drawdown_exit_pct'],
            'best_reentry_rebound_pct': best_params['reentry_rebound_pct'],
            'best_rsi_oversold': best_params['rsi_oversold'],
            'best_rsi_overbought': best_params['rsi_overbought'],
            'use_rsi_filter': best_params.get('use_rsi_filter', True),
            'rsi_period': best_params.get('rsi_period', DEFAULT_RSI_PERIOD),
            'best_exposure_multiplier': best_params.get('exposure_multiplier', profile_settings.get("default_exposure_multiplier", 1.0)),
            'effective_cooldown': best_params['effective_cooldown'],
            'effective_drawdown_exit_pct': best_params['effective_drawdown_exit_pct'],
            'effective_reentry_rebound_pct': best_params['effective_reentry_rebound_pct'],
            'adaptive_return_pct': metrics['adaptive_return'],
            'buy_hold_return_pct': metrics['buy_hold_return'],
            'excess_return_pct': metrics['excess_return'],
            'sharpe': metrics['sharpe'],
            'max_dd_pct': metrics['max_dd'],
            'trade_count': num_trades,
            'win_rate_pct': win_rate,
            'time_invested_pct': metrics['time_invested_pct'],
            'uptrend_cash_pct': metrics['uptrend_cash_pct'],
            'missed_upside_after_exit_pct': metrics['missed_upside_after_exit_pct'],
            'score': score
        })
        if score > best_score:
            best_score = score
            best_combo = (pop, gens, mut, cross)
            best_combo_params = best_params

    if not results:
        log_print("No valid tuning results; falling back to defaults.")
        results_df = pd.DataFrame([{
            'pop_size': 10, 'generations': 10, 'mutation_rate': 0.05, 'crossover_rate': 0.7,
            'best_short_ema': 0, 'best_long_ema': 0, 'best_stop_loss_pct': 0,
            'best_cooldown': 0, 'best_drawdown_exit_pct': 0, 'best_reentry_rebound_pct': 0,
            'best_rsi_oversold': DEFAULT_STRATEGY_PARAMETERS["rsi_oversold"],
            'best_rsi_overbought': DEFAULT_STRATEGY_PARAMETERS["rsi_overbought"],
            'use_rsi_filter': True,
            'rsi_period': DEFAULT_RSI_PERIOD,
            'best_exposure_multiplier': 1.0,
            'effective_cooldown': 0, 'effective_drawdown_exit_pct': 0,
            'effective_reentry_rebound_pct': 0,
            'adaptive_return_pct': 0, 'buy_hold_return_pct': 0, 'excess_return_pct': 0,
            'sharpe': 0, 'max_dd_pct': 0, 'trade_count': 0, 'win_rate_pct': 0,
            'time_invested_pct': 0, 'uptrend_cash_pct': 0,
            'missed_upside_after_exit_pct': 0, 'score': 0
        }])
        best_combo = (10, 10, 0.05, 0.7)
        best_combo_params = None
    else:
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values('score', ascending=False).reset_index(drop=True)

    results_df['best'] = results_df['score'] == results_df['score'].max()
    metadata = {}
    metadata.update(run_metadata or {})
    metadata.update(window_metadata or {})
    metadata.update(strategy_parameter_metadata or {})
    if metadata:
        for key, value in metadata.items():
            results_df[key] = value

    results_df["run_started_at"] = metadata.get("run_started_at", started_at)
    results_df["tuning_recorded_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results_df["short_ema"] = results_df["best_short_ema"]
    results_df["long_ema"] = results_df["best_long_ema"]
    results_df["stop_loss"] = results_df["best_stop_loss_pct"]
    results_df["cooldown"] = results_df["best_cooldown"]
    results_df["stop_loss_pct"] = results_df["best_stop_loss_pct"]
    results_df["cooldown_period"] = results_df["best_cooldown"]
    results_df["drawdown_exit_pct"] = results_df["best_drawdown_exit_pct"]
    results_df["reentry_rebound_pct"] = results_df["best_reentry_rebound_pct"]
    results_df["rsi_oversold"] = results_df["best_rsi_oversold"]
    results_df["rsi_overbought"] = results_df["best_rsi_overbought"]
    results_df["rsi_period"] = results_df.get("rsi_period", DEFAULT_RSI_PERIOD)
    results_df["use_rsi_filter"] = True
    results_df["exposure_multiplier"] = results_df["best_exposure_multiplier"]
    results_df["max_drawdown_pct"] = results_df["max_dd_pct"]
    results_df["param_set_id"] = results_df.apply(lambda row: build_param_set_id(row.to_dict()), axis=1)

    log_print("\nGA Hyperparameter Tuning Results:")
    log_print(results_df.to_string(index=False))
    tune_csv = f"ga_tuning_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    tune_csv = TUNINGS_DIR / tune_csv
    results_df.to_csv(tune_csv, index=False)
    append_csv_rows(TUNING_HISTORY_FILE, results_df.to_dict("records"))
    refresh_top5_parameter_sets()
    log_print(f"\nFull results saved to: {tune_csv}")
    log_print(f"Best combo (max score {best_score:.3f}): pop={best_combo[0]}, gens={best_combo[1]}, mut={best_combo[2]}, cross={best_combo[3]}")

    if return_best_params:
        return best_combo, best_combo_params
    return best_combo

def run_backtest_for_csv(csv_file, lookback_years_value, offset_months_value,
                         pop_ranges_value, gen_ranges_value, initial_capital=10000,
                         strategy_profile_value="generic", ga_seed_value=None,
                         mutation_rates_value=None, crossover_rates_value=None,
                         short_ema_bounds_value=DEFAULT_SHORT_EMA_BOUNDS,
                         long_ema_bounds_value=DEFAULT_LONG_EMA_BOUNDS,
                         reuse_tuned_params_value=False, price_column_value="TotalReturn",
                         ga_search_preset_value="grid", profile_override_preset_value="default"):
    """Run the full walk-forward GA backtest for a single CSV data source."""
    global log_file, csv_name, lookback_years, offset_months, pop_ranges
    global gen_ranges, mutation_rates, crossover_rates, reuse_tuned_params
    global batch_name, started_at, strategy_profile, ga_seed
    global history_fallback_files, skip_top5_refresh_for_run

    ensure_output_dirs()
    history_fallback_files = []
    skip_top5_refresh_for_run = False
    csv_path = resolve_input_csv_path(csv_file)
    csv_name = infer_fund_output_label(csv_path)
    lookback_years = lookback_years_value
    offset_months = offset_months_value
    pop_ranges = pop_ranges_value
    gen_ranges = gen_ranges_value
    mutation_rates = mutation_rates_value or []
    crossover_rates = crossover_rates_value or []
    short_ema_bounds_value, long_ema_bounds_value = validate_ema_bounds(
        normalize_ema_bounds(short_ema_bounds_value, "--short-ema-bounds"),
        normalize_ema_bounds(long_ema_bounds_value, "--long-ema-bounds"),
    )
    short_ema_bounds_value, long_ema_bounds_value, _, _, _, _ = resolve_profile_gene_bounds(
        strategy_profile_value,
        short_ema_bounds_value,
        long_ema_bounds_value,
        (8, 15),
        (0, 3),
        (2.5, 4.0),
        (1.0, 3.0),
    )
    short_ema_bounds_value, long_ema_bounds_value = validate_ema_bounds(
        short_ema_bounds_value,
        long_ema_bounds_value,
    )
    reuse_tuned_params = reuse_tuned_params_value
    strategy_profile = strategy_profile_value
    ga_seed = ga_seed_value
    batch_name = f"{csv_name}, {lookback_years}Y, {offset_months}M, profile={strategy_profile}"
    started_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    machine_metadata = get_machine_metadata()

    now = datetime.now()
    log_filename = LOGS_DIR / f"{csv_name}-{lookback_years}Y-{offset_months}M-{strategy_profile}-ga10-{now.strftime('%Y%m%d_%H%M%S')}.txt"
    log_file = open(log_filename, 'w')
    log_print(f"=== Trading Strategy Backtest Log ===")
    log_print(f"Started at: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"Machine: {machine_metadata['machine_name']}")
    log_print(f"Hostname: {machine_metadata['hostname']}")
    log_print(f"Platform: {machine_metadata['platform']}")
    log_print(f"Python: {machine_metadata['python_version']}")
    log_print(f"Log file: {log_filename}")
    log_print(f"Strategy profile: {strategy_profile}")
    log_print(f"GA seed: {ga_seed if ga_seed is not None else 'deterministic'}")
    log_print(f"EMA bounds: short={short_ema_bounds_value}, long={long_ema_bounds_value}")
    log_print(f"GA mutation rates: {mutation_rates if mutation_rates else 'default grid'}")
    log_print(f"GA crossover rates: {crossover_rates if crossover_rates else 'default grid'}")
    log_print(f"Reuse tuned params: {reuse_tuned_params}")
    if "profile_override_preset" in globals():
        log_print(f"Profile override preset: {profile_override_preset}")

    try:
        df_clean = pd.read_csv(csv_path)

        if 'Date' in df_clean.columns:
            df_clean['Date'] = pd.to_datetime(df_clean['Date'], errors='coerce')
            df_clean = df_clean.dropna(subset=['Date'])

        df_clean = df_clean.sort_values('Date').reset_index(drop=True)

        preferred_price_col = price_column_value
        fallback_price_cols = [preferred_price_col, 'TotalReturn', 'NAV', 'Close']
        fallback_price_cols = list(dict.fromkeys([col for col in fallback_price_cols if col]))
        price_col = next((col for col in fallback_price_cols if col in df_clean.columns), None)

        if price_col is None:
            raise ValueError(
                f"No recognized price column found. Tried {fallback_price_cols}. "
                f"Available columns: {list(df_clean.columns)}"
            )

        if price_col == 'Close':
            df_clean['NAV'] = df_clean['Close']
            cols_to_drop = [col for col in ['High', 'Low', 'Open', 'Volume'] if col in df_clean.columns]
            if cols_to_drop:
                df_clean = df_clean.drop(columns=cols_to_drop)
            log_print("Detected yfinance Close price format; using Close as internal NAV.")
        elif price_col != 'NAV':
            if 'NAV' in df_clean.columns:
                df_clean['Raw_NAV'] = df_clean['NAV']
            df_clean['NAV'] = df_clean[price_col]
            log_print(f"Using {price_col} as the backtest price series (mapped to internal NAV).")
        else:
            log_print("Using NAV as the backtest price series.")

        df_clean['NAV'] = pd.to_numeric(df_clean['NAV'], errors='coerce')
        df_clean = df_clean.dropna(subset=['NAV'])
        df_clean = df_clean.set_index('Date')
        df_clean['RSI'] = calculate_rsi(df_clean['NAV'], DEFAULT_RSI_PERIOD)

        log_print(f"Loading data from {csv_path}...")
        log_print(f"Price data loaded from {price_col}: {len(df_clean)} valid data points")
        log_print(
            f"Date range: {df_clean.index.min().strftime('%Y-%m-%d')} "
            f"to {df_clean.index.max().strftime('%Y-%m-%d')}"
        )

        lookback_months = int(lookback_years * 12)
        start_date = df_clean.index.min() + pd.DateOffset(months=lookback_months)
        end_date = df_clean.index.max()
        run_config_for_hash = {
            "fund_label": csv_name,
            "data_file": str(csv_path),
            "price_column": price_col,
            "lookback_years": lookback_years,
            "offset_months": offset_months,
            "strategy_profile": strategy_profile,
            "profile_override_preset": profile_override_preset_value,
            "ga_seed": ga_seed if ga_seed is not None else "deterministic",
            "ga_search_preset": ga_search_preset_value,
            "pop_ranges": pop_ranges,
            "gen_ranges": gen_ranges,
            "short_ema_bounds": short_ema_bounds_value,
            "long_ema_bounds": long_ema_bounds_value,
            "mutation_rates": mutation_rates or "default grid",
            "crossover_rates": crossover_rates or "default grid",
        }
        run_id = build_run_id(started_at, csv_name, run_config_for_hash)
        run_metadata = build_run_metadata(
            run_id,
            csv_path,
            csv_name,
            price_col,
            df_clean.index.min(),
            df_clean.index.max(),
            len(df_clean),
            lookback_years,
            offset_months,
            initial_capital,
            start_date,
            end_date,
            strategy_profile,
            profile_override_preset_value,
            ga_seed,
            ga_search_preset_value,
            reuse_tuned_params,
            pop_ranges,
            gen_ranges,
            mutation_rates,
            crossover_rates,
            short_ema_bounds_value,
            long_ema_bounds_value,
            machine_metadata,
        )
        strategy_parameter_metadata = build_strategy_parameter_metadata(
            {},
            get_strategy_profile_settings(strategy_profile),
        )
        log_print(f"Run ID: {run_id}")

        current_date = start_date
        portfolio_value = initial_capital
        portfolio_history = []
        trade_count = 0
        params_history = []
        adaptive_results = []
        all_decisions = []
        all_trades = []
        best_ga_params = None
        carry_state = None
        window_sequence = 0

        log_print(
            f"\nStarting ga10 walk-forward optimization from "
            f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} "
            f"with {lookback_years}Y {offset_months}M ... "
        )

        while current_date < end_date:
            window_sequence += 1
            tuned_best_params = None
            lookback_start = current_date - pd.DateOffset(months=lookback_months)
            next_period_end = current_date + pd.DateOffset(months=offset_months)
            window_metadata = {
                "window_sequence": window_sequence,
                "train_start": format_date(lookback_start),
                "train_end": format_date(current_date),
                "test_start": format_date(current_date),
                "test_end": format_date(min(next_period_end, end_date)),
            }
            now = datetime.now()
            log_print(f"\nCurrent Date & Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            log_print(
                f"start date={lookback_start.strftime('%Y-%m-%d')}, "
                f"end date={current_date.strftime('%Y-%m-%d')}"
            )
            lookback_data = df_clean[(df_clean.index >= lookback_start) & (df_clean.index < current_date)].copy()
            df_tune = lookback_data.copy()

            if len(df_tune) >= 100:
                tune_result = tune_ga_hyperparams(
                    df_tune,
                    short_ema_bounds=short_ema_bounds_value,
                    long_ema_bounds=long_ema_bounds_value,
                    strategy_profile_name=strategy_profile,
                    ga_seed_value=ga_seed,
                    mutation_rates_value=mutation_rates,
                    crossover_rates_value=crossover_rates,
                    return_best_params=reuse_tuned_params,
                    run_metadata=run_metadata,
                    window_metadata=window_metadata,
                    strategy_parameter_metadata=strategy_parameter_metadata,
                )
                tuned_best_params = None
                if reuse_tuned_params:
                    best_ga_params, tuned_best_params = tune_result
                else:
                    best_ga_params = tune_result
                pop_size, generations, mutation_rate, crossover_rate = best_ga_params
                log_print(f"Retuned GA at {current_date}: {best_ga_params}")
                elapsed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                started_at2 = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
                elapsed_at2 = datetime.strptime(elapsed_at, "%Y-%m-%d %H:%M:%S")
                duration = elapsed_at2 - started_at2
                print(
                    f"duration={duration}, elapsed_at2={elapsed_at2}, "
                    f"started_at2={started_at2}, started_at={started_at}"
                )
                hours, remainder = divmod(duration.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                print(f"Elapsed = {int(hours)} hours {int(minutes)} minutes {int(seconds)} seconds")
            else:
                pop_size, generations, mutation_rate, crossover_rate = (10, 10, 0.05, 0.7)
                log_print(f"Insufficient data at {current_date}, using default GA parameters")

            if len(lookback_data) < 50:
                log_print(f"Skipping {current_date.strftime('%Y-%m-%d')}: Insufficient data")
                current_date += pd.DateOffset(months=offset_months)
                continue

            lookback_data = lookback_data.dropna(subset=['NAV'])
            if len(lookback_data) < 50:
                log_print(f"Skipping {current_date.strftime('%Y-%m-%d')}: Insufficient data after NaN drop")
                current_date += pd.DateOffset(months=offset_months)
                continue

            if reuse_tuned_params and tuned_best_params is not None:
                best_params = tuned_best_params
                log_print("Reusing best params from tuning phase for this walk-forward window.")
            else:
                best_params = genetic_optimize_params(
                    lookback_data,
                    short_ema_bounds=short_ema_bounds_value,
                    long_ema_bounds=long_ema_bounds_value,
                    pop_size=pop_size,
                    generations=generations,
                    mutation_rate=mutation_rate,
                    crossover_rate=crossover_rate,
                    initial_capital=initial_capital,
                    strategy_profile_name=strategy_profile,
                    ga_seed_value=ga_seed
                )
            if best_params is None:
                log_print(f"Skipping {current_date.strftime('%Y-%m-%d')}: No valid parameters")
                current_date += pd.DateOffset(months=offset_months)
                continue

            log_print(
                f"Optimized for {current_date.strftime('%Y-%m-%d')}: "
                f"EMA({best_params['short_ema']}, {best_params['long_ema']}), "
                f"SL={best_params['stop_loss']:.2f}, CD={best_params['cooldown']}, "
                f"DDX={best_params['drawdown_exit_pct']:.2f}, "
                f"RBR={best_params['reentry_rebound_pct']:.2f}, "
                f"RSI={best_params['rsi_oversold']}/{best_params['rsi_overbought']}, "
                f"EXP={best_params.get('exposure_multiplier', 1.0):.2f}x"
            )
            params_history.append((
                current_date,
                best_params['short_ema'],
                best_params['long_ema'],
                best_params['stop_loss'],
                best_params['cooldown'],
                best_params['drawdown_exit_pct'],
                best_params['reentry_rebound_pct'],
                best_params['rsi_oversold'],
                best_params['rsi_overbought'],
                best_params.get('exposure_multiplier', 1.0)
            ))

            next_period_data = df_clean[(df_clean.index >= current_date) & (df_clean.index < next_period_end)].copy()

            if len(next_period_data) == 0:
                log_print(f"No data for period starting {current_date.strftime('%Y-%m-%d')}")
                break

            warmup_data = lookback_data.copy()
            eval_data = pd.concat([warmup_data, next_period_data]).sort_index()
            eval_data = eval_data[~eval_data.index.duplicated(keep='last')]
            trade_start_idx = len(eval_data) - len(next_period_data)

            config = {
                'use_rsi_filter': True,
                'rsi_oversold': best_params['rsi_oversold'],
                'rsi_overbought': best_params['rsi_overbought'],
                'rsi_period': best_params.get('rsi_period', DEFAULT_RSI_PERIOD),
                'use_trend_filter': False,
                'use_stop_loss': True,
                'stop_loss_pct': best_params['stop_loss'],
                'use_take_profit': False,
                'cooldown_period': best_params['cooldown'],
                'drawdown_exit_pct': best_params['drawdown_exit_pct'],
                'reentry_rebound_pct': best_params['reentry_rebound_pct'],
                'exposure_multiplier': best_params.get('exposure_multiplier', 1.0),
                'start_invested': carry_state is None,
                'trade_start_idx': trade_start_idx,
                'debug': True,
                'strategy_profile_name': strategy_profile,
            }
            period_initial_capital = portfolio_value
            df_result, total_return, num_trades, trades, period_win_rate, avg_return, decisions_df, _, _, carry_state = backtest_enhanced_dual_ema(
                eval_data,
                best_params['short_ema'],
                best_params['long_ema'],
                portfolio_value,
                initial_state=carry_state,
                return_state=True,
                **config
            )
            period_metrics = calculate_index_strategy_metrics(
                df_result,
                trades,
                period_initial_capital,
                best_params['long_ema'],
            )
            portfolio_value = df_result['Portfolio_Value'].iloc[-1]
            trade_count += num_trades
            all_trades.extend(trades)
            window_row = {
                **run_metadata,
                **window_metadata,
                **build_strategy_parameter_metadata(config, get_strategy_profile_settings(strategy_profile)),
                "param_set_id": build_param_set_id({
                    **run_metadata,
                    "short_ema": best_params['short_ema'],
                    "long_ema": best_params['long_ema'],
                    "stop_loss": best_params['stop_loss'],
                    "cooldown": best_params['cooldown'],
                    "drawdown_exit_pct": best_params['drawdown_exit_pct'],
                    "reentry_rebound_pct": best_params['reentry_rebound_pct'],
                    "rsi_oversold": best_params['rsi_oversold'],
                    "rsi_overbought": best_params['rsi_overbought'],
                    "exposure_multiplier": best_params.get('exposure_multiplier', 1.0),
                }),
                "pop_size": pop_size,
                "generations": generations,
                "mutation_rate": mutation_rate,
                "crossover_rate": crossover_rate,
                "short_ema": best_params['short_ema'],
                "long_ema": best_params['long_ema'],
                "stop_loss": best_params['stop_loss'],
                "cooldown": best_params['cooldown'],
                "drawdown_exit_pct": best_params['drawdown_exit_pct'],
                "reentry_rebound_pct": best_params['reentry_rebound_pct'],
                "rsi_oversold": best_params['rsi_oversold'],
                "rsi_overbought": best_params['rsi_overbought'],
                "rsi_period": best_params.get('rsi_period', DEFAULT_RSI_PERIOD),
                "use_rsi_filter": True,
                "exposure_multiplier": best_params.get('exposure_multiplier', 1.0),
                "effective_cooldown": best_params['effective_cooldown'],
                "effective_drawdown_exit_pct": best_params['effective_drawdown_exit_pct'],
                "effective_reentry_rebound_pct": best_params['effective_reentry_rebound_pct'],
                "period_initial_capital": period_initial_capital,
                "period_final_value": portfolio_value,
                "period_return_pct": period_metrics['adaptive_return'],
                "period_buy_hold_return_pct": period_metrics['buy_hold_return'],
                "period_excess_return_pct": period_metrics['excess_return'],
                "period_sharpe": period_metrics['sharpe'],
                "period_max_dd_pct": period_metrics['max_dd'],
                "period_trade_count": num_trades,
                "period_win_rate_pct": period_win_rate,
                "period_time_invested_pct": period_metrics['time_invested_pct'],
                "period_uptrend_cash_pct": period_metrics['uptrend_cash_pct'],
                "period_missed_upside_after_exit_pct": period_metrics['missed_upside_after_exit_pct'],
                "period_stop_loss_count": period_metrics['stop_loss_count'],
                "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            append_csv_row(WINDOW_HISTORY_FILE, window_row)
            portfolio_history.append(
                df_result[['Date', 'Portfolio_Value', 'Position', 'Exposure']].copy()
                if 'Date' in df_result.columns
                else df_result.reset_index().rename(columns={'index': 'Date'})
            )
            adaptive_df_period = df_result[[
                'Date', 'NAV', f'EMA_{best_params["short_ema"]}', f'EMA_{best_params["long_ema"]}',
                'RSI', 'EMA_Signal', 'Final_Signal', 'Position', 'Exposure', 'Portfolio_Value',
                'Short_EMA_Value', 'Long_EMA_Value', 'Long_EMA_Slope_5',
                'Sell_Regime_OK', 'Recovery_Buy_Override',
                'RSI_Filter_Block', 'RSI_Sell_Block', 'RSI_Buy_Block'
            ]].copy()
            adaptive_results.append(adaptive_df_period)
            all_decisions.append(decisions_df)
            current_date = next_period_end

            elapsed_at = now.strftime('%Y-%m-%d %H:%M:%S')
            started_at2 = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
            elapsed_at2 = datetime.strptime(elapsed_at, "%Y-%m-%d %H:%M:%S")
            duration = elapsed_at2 - started_at2
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            print(f"Elapsed = {int(hours)} hours {int(minutes)} minutes {int(seconds)} seconds")

        if portfolio_history and adaptive_results:
            try:
                portfolio_df = pd.concat(portfolio_history, ignore_index=True)
                adaptive_df = pd.concat(adaptive_results, ignore_index=True)

                if 'Date' in adaptive_df.columns:
                    adaptive_df = adaptive_df.drop_duplicates(subset=['Date'], keep='last')
                    adaptive_df = adaptive_df.sort_values('Date').reset_index(drop=True)
                else:
                    adaptive_df = adaptive_df.reset_index()
                    adaptive_df = adaptive_df.rename(columns={'index': 'Date'}) if 'index' in adaptive_df.columns else adaptive_df

                if not portfolio_df.empty and 'Portfolio_Value' in portfolio_df.columns:
                    final_return = (portfolio_df['Portfolio_Value'].iloc[-1] - initial_capital) / initial_capital * 100
                else:
                    final_return = 0
                    log_print("Warning: Empty portfolio_df, setting return to 0")
            except Exception as e:
                log_print(f"Error combining results: {e}")
                portfolio_df = pd.DataFrame()
                adaptive_df = pd.DataFrame()
                final_return = 0
        else:
            portfolio_df = pd.DataFrame()
            adaptive_df = pd.DataFrame()
            final_return = 0
            log_print("No portfolio history generated due to insufficient data or errors.")

        backtest_data = df_clean[df_clean.index >= start_date]
        if backtest_data.empty:
            log_print(
                "No forward-test data available. "
                f"Need data after {start_date.strftime('%Y-%m-%d')}, "
                f"but CSV ends at {end_date.strftime('%Y-%m-%d')}."
            )
        bh_portfolio, bh_return = buy_and_hold_strategy(backtest_data, initial_capital)
        summary_metrics = calculate_index_strategy_metrics(adaptive_df, all_trades, initial_capital)
        final_return = summary_metrics['adaptive_return']
        excess_return = summary_metrics['excess_return']

        overall_win_rate = 0
        if all_trades:
            paired_trade_returns = []
            pending_buy = None
            for trade in all_trades:
                trade_type, _, trade_price, _ = trade
                if trade_type == 'BUY':
                    pending_buy = trade_price
                elif trade_type in ['SELL', 'STOP_LOSS', 'TAKE_PROFIT'] and pending_buy is not None:
                    paired_trade_returns.append((trade_price - pending_buy) / pending_buy * 100)
                    pending_buy = None

            overall_win_rate = (
                len([ret for ret in paired_trade_returns if ret > 0]) / len(paired_trade_returns) * 100
                if paired_trade_returns else 0
            )

        tuned_summary = best_ga_params if best_ga_params is not None else "not retuned"
        log_print(f"\n=== BACKTESTING RESULTS {csv_path}-{lookback_years}Y-{offset_months}M [{strategy_profile}] ===")
        log_print(f"Adaptive Enhanced Strategy Return:  {final_return:.2f}%  <<< ga10 (profile: {strategy_profile}, tuned: {tuned_summary})")
        log_print(f"Buy & Hold Return: {bh_return:.2f}%")
        log_print(f"Excess Return vs Buy & Hold: {excess_return:.2f}%")
        log_print(f"Total Trades (Adaptive): {trade_count}")
        log_print(f"Percent Time Invested: {summary_metrics['time_invested_pct']:.2f}%")
        log_print(f"Percent Time In Cash During Uptrend: {summary_metrics['uptrend_cash_pct']:.2f}%")
        log_print(f"Missed Upside After Exits: {summary_metrics['missed_upside_after_exit_pct']:.2f}%")
        log_print(f"Stop-Loss Exit Count: {summary_metrics['stop_loss_count']}")

        log_print(f"\nParameter History:")
        for date, short, long, sl, cd, drawdown_exit_pct, reentry_rebound_pct, rsi_oversold, rsi_overbought, exposure_multiplier in params_history:
            log_print(
                f"{date.strftime('%Y-%m-%d')}: EMA({short}, {long}), SL={sl:.2f}, "
                f"CD={cd}, DDX={drawdown_exit_pct:.2f}, RBR={reentry_rebound_pct:.2f}, "
                f"RSI={rsi_oversold}/{rsi_overbought}, "
                f"EXP={exposure_multiplier:.2f}x"
            )

        if not portfolio_df.empty and len(portfolio_history) > 0:
            log_print(f"\nSharpe Ratio: {summary_metrics['sharpe']:.2f}")
            log_print(f"Max Drawdown: {summary_metrics['max_dd']:.2f}%")
            log_print(f'Win Rate: {overall_win_rate:.1f}%')
        else:
            log_print('\nNo portfolio data for metrics.')

        if all_trades:
            log_print(f'Manual Win Rate (from trades): {overall_win_rate:.1f}%')

        completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_print(f"\nCompleted at: {completed_at}")
        log_print(f"Started at: {started_at}")

        started_at2 = datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
        completed_at2 = datetime.strptime(completed_at, "%Y-%m-%d %H:%M:%S")
        duration = completed_at2 - started_at2
        duration_seconds = int(duration.total_seconds())
        duration_minutes = round(duration_seconds / 60, 2)
        log_print(f"Duration: {duration}")
        log_print(f"Duration seconds: {duration_seconds}")
        hours, remainder = divmod(duration.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        print(f"{int(hours)} hours {int(minutes)} minutes {int(seconds)} seconds")
        if history_fallback_files:
            log_print("\nHistory fallback files used during this run:")
            for entry in history_fallback_files:
                log_print(f"- {entry}")

        last_chart_params = params_history[-1] if params_history else None
        mutation_label = ",".join(str(value) for value in mutation_rates) if mutation_rates else "default grid"
        crossover_label = ",".join(str(value) for value in crossover_rates) if crossover_rates else "default grid"
        if last_chart_params:
            final_param_text = (
                "Final selected params\n"
                f"EMA: {last_chart_params[1]} / {last_chart_params[2]} | "
                f"SL: {last_chart_params[3]:.2f} | CD: {last_chart_params[4]}\n"
                f"DDX: {last_chart_params[5]:.2f} | RBR: {last_chart_params[6]:.2f} | "
                f"RSI: {last_chart_params[7]} / {last_chart_params[8]} | "
                f"EXP: {last_chart_params[9]:.2f}x"
            )
        else:
            final_param_text = "Final selected params\nNo valid walk-forward parameter set"
        technical_param_text = (
            "Configured\n"
            f"Price: {price_col} | Lookback/offset: {lookback_years}Y/{offset_months}M | Profile: {strategy_profile}\n"
            f"EMA bounds: {short_ema_bounds_value}/{long_ema_bounds_value} | "
            f"GA: pop={pop_ranges}, gen={gen_ranges}, mut={mutation_label}, cross={crossover_label}\n"
            f"Best GA combo: {best_ga_params if best_ga_params is not None else 'not retuned'}\n\n"
            f"{final_param_text}"
        )

        fig = plt.figure(figsize=(15, 12))
        grid = fig.add_gridspec(3, 1, height_ratios=[1.2, 0.8, 0.8])

        plt.subplot(grid[0])
        if not adaptive_df.empty and 'NAV' in adaptive_df.columns:
            x_nav = adaptive_df['Date'] if 'Date' in adaptive_df.columns else adaptive_df.index
            y_nav = adaptive_df['NAV']
        else:
            x_nav = df_clean.index
            y_nav = df_clean['NAV']
        plt.plot(x_nav, y_nav, label=price_col, linewidth=1.5, color='black')

        for i, (date, short, long, sl, cd, drawdown_exit_pct, reentry_rebound_pct, rsi_oversold, rsi_overbought, exposure_multiplier) in enumerate(params_history):
            mask = (adaptive_df['Date'] >= date) & (adaptive_df['Date'] < (date + pd.DateOffset(months=offset_months))) if 'Date' in adaptive_df.columns else slice(None)
            period_data = adaptive_df.loc[mask] if not adaptive_df.empty else pd.DataFrame()
            if not period_data.empty and f'EMA_{short}' in period_data.columns:
                x_period = period_data['Date'] if 'Date' in period_data.columns else period_data.index
                plt.plot(x_period, period_data[f'EMA_{short}'], alpha=0.7, color='blue', linestyle='--' if i % 2 else '-', label='Short EMA' if i == 0 else None)
                plt.plot(x_period, period_data[f'EMA_{long}'], alpha=0.7, color='red', linestyle='--' if i % 2 else '-', label='Long EMA' if i == 0 else None)

        if 'Position' in adaptive_df.columns:
            pos_diff = adaptive_df['Position'].diff().fillna(0)
            buy_signals = adaptive_df[pos_diff > 0]
            sell_signals = adaptive_df[pos_diff < 0]
            x_buy = buy_signals['Date'] if 'Date' in buy_signals.columns else buy_signals.index
            plt.scatter(x_buy, buy_signals['NAV'], color='green', marker='^', s=100, label='Buy Signal', zorder=5)
            x_sell = sell_signals['Date'] if 'Date' in sell_signals.columns else sell_signals.index
            plt.scatter(x_sell, sell_signals['NAV'], color='red', marker='v', s=100, label='Sell Signal', zorder=5)

        plt.title(f'Index-Tuned Adaptive Strategy {csv_name}-{lookback_years}Y-{offset_months}M {strategy_profile} ga10', fontsize=14, fontweight='bold')
        plt.gca().text(
            0.01,
            0.98,
            technical_param_text,
            transform=plt.gca().transAxes,
            va='top',
            ha='left',
            fontsize=8.5,
            bbox={'boxstyle': 'round,pad=0.45', 'facecolor': 'white', 'edgecolor': '#cccccc', 'alpha': 0.9},
        )
        plt.ylabel(price_col)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)

        plt.subplot(grid[1])
        rsi_data = df_clean[df_clean.index >= start_date].copy()
        plt.plot(rsi_data.index, rsi_data['RSI'], label='RSI', color='orange')
        if params_history:
            avg_rsi_oversold = np.mean([entry[7] for entry in params_history])
            avg_rsi_overbought = np.mean([entry[8] for entry in params_history])
            plt.axhline(y=avg_rsi_oversold, color='g', linestyle='--', alpha=0.7, label=f'Avg Oversold Guard ({avg_rsi_oversold:.0f})')
            plt.axhline(y=avg_rsi_overbought, color='r', linestyle='--', alpha=0.7, label=f'Avg Overbought Guard ({avg_rsi_overbought:.0f})')
        else:
            plt.axhline(y=DEFAULT_STRATEGY_PARAMETERS["rsi_oversold"], color='g', linestyle='--', alpha=0.7, label='Oversold Guard')
            plt.axhline(y=DEFAULT_STRATEGY_PARAMETERS["rsi_overbought"], color='r', linestyle='--', alpha=0.7, label='Overbought Guard')
        plt.title('RSI Indicator (GA-Tuned Entry/Exit Guards)', fontsize=12)
        plt.ylabel('RSI')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)

        plt.subplot(grid[2])
        if not portfolio_df.empty:
            x_port = portfolio_df['Date'] if 'Date' in portfolio_df.columns else portfolio_df.index
            plt.plot(x_port, portfolio_df['Portfolio_Value'], label=f'Adaptive Enhanced ({final_return:.2f}%)', linewidth=2, color='green')
        bh_x = backtest_data.index
        if len(bh_x) == len(bh_portfolio) and len(bh_x) > 0:
            plt.plot(bh_x, bh_portfolio, label=f'Buy & Hold ({bh_return:.2f}%)', linewidth=2, color='blue')
        else:
            log_print("Skipping buy-and-hold chart line because no forward-test dates are available.")

        plt.title('Portfolio Value Comparison', fontsize=14, fontweight='bold')
        plt.xlabel('Date')
        plt.ylabel('Portfolio Value')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)

        plt.tight_layout()

        formatted = datetime.now().strftime("%Y%m%d-%H%M%S")
        png_file = CHARTS_DIR / f"{csv_name}-{lookback_years}Y-{offset_months}M-{strategy_profile}-ga10-tuned-{formatted}.png"
        plt.savefig(png_file, dpi=200, bbox_inches="tight")
        plt.close()
        log_print(f"\nChart saved to: {png_file}")

        profile_settings = get_strategy_profile_settings(strategy_profile)
        run_score = (
            (2.0 * summary_metrics['excess_return'])
            + (6.0 * summary_metrics['sharpe'])
            - (0.30 * summary_metrics['max_dd'])
            - (0.10 * trade_count)
            - (0.5 * summary_metrics['uptrend_cash_pct'])
            - (
                profile_settings['missed_upside_after_exit_weight']
                * summary_metrics['missed_upside_after_exit_pct']
            )
        )
        last_params = params_history[-1] if params_history else None
        run_row = {
            **run_metadata,
            "run_completed_at": completed_at,
            "run_status": "completed" if len(backtest_data) > 0 else "insufficient_data",
            "duration": str(duration),
            "duration_seconds": duration_seconds,
            "duration_minutes": duration_minutes,
            "log_file": str(log_filename),
            "chart_file": str(png_file),
            "final_portfolio_value": portfolio_value,
            "adaptive_return_pct": summary_metrics['adaptive_return'],
            "buy_hold_return_pct": summary_metrics['buy_hold_return'],
            "excess_return_pct": summary_metrics['excess_return'],
            "sharpe": summary_metrics['sharpe'],
            "max_dd_pct": summary_metrics['max_dd'],
            "trade_count": trade_count,
            "win_rate_pct": overall_win_rate,
            "time_invested_pct": summary_metrics['time_invested_pct'],
            "uptrend_cash_pct": summary_metrics['uptrend_cash_pct'],
            "missed_upside_after_exit_pct": summary_metrics['missed_upside_after_exit_pct'],
            "stop_loss_count": summary_metrics['stop_loss_count'],
            "score": run_score,
            "best_ga_pop_size": best_ga_params[0] if best_ga_params else "",
            "best_ga_generations": best_ga_params[1] if best_ga_params else "",
            "best_ga_mutation_rate": best_ga_params[2] if best_ga_params else "",
            "best_ga_crossover_rate": best_ga_params[3] if best_ga_params else "",
            "last_short_ema": last_params[1] if last_params else "",
            "last_long_ema": last_params[2] if last_params else "",
            "last_stop_loss": last_params[3] if last_params else "",
            "last_cooldown": last_params[4] if last_params else "",
            "last_drawdown_exit_pct": last_params[5] if last_params else "",
            "last_reentry_rebound_pct": last_params[6] if last_params else "",
            "last_rsi_oversold": last_params[7] if last_params else "",
            "last_rsi_overbought": last_params[8] if last_params else "",
            "last_rsi_period": DEFAULT_RSI_PERIOD if last_params else "",
            "last_exposure_multiplier": last_params[9] if last_params else "",
        }
        append_csv_row(RUN_HISTORY_FILE, run_row)
        refresh_top5_parameter_sets()

        log_print("\n=== COMPLETED ===")

        if log_file:
            log_file.close()
            print(f"\nLog saved to: {log_filename}")
            log_file = None

    except KeyboardInterrupt:
        log_print("\nInterrupted cleanly")
        if log_file:
            log_file.close()
            log_file = None
    except Exception as e:
        log_print(f"\nError occurred: {str(e)}")
        if log_file:
            log_file.close()
            log_file = None
        raise

# Main execution (minor updates for rsi_period in backtest calls)
if __name__ == "__main__":
    signal.signal(signal.SIGINT, handler)
    ensure_output_dirs()
    args = parse_args()
    profile_override_preset = args.profile_override_preset
    apply_profile_override_preset(args.strategy_profile, profile_override_preset)
    lookback_years = args.lookback_years
    offset_months = args.offset_months
    pop_ranges = normalize_pop_ranges(args.pop_ranges)
    if args.gen_ranges is None:
        gen_ranges = pop_ranges
    else:
        gen_ranges = normalize_pop_ranges(args.gen_ranges)
    short_ema_bounds, long_ema_bounds = validate_ema_bounds(
        normalize_ema_bounds(args.short_ema_bounds, "--short-ema-bounds"),
        normalize_ema_bounds(args.long_ema_bounds, "--long-ema-bounds"),
    )
    if args.ga_search_preset == "focused":
        mutation_rates = normalize_float_ranges(args.mutation_rates, [0.01])
        crossover_rates = normalize_float_ranges(args.crossover_rates, [0.6])
        reuse_tuned_params = True
    else:
        mutation_rates = normalize_float_ranges(args.mutation_rates, None)
        crossover_rates = normalize_float_ranges(args.crossover_rates, None)
        reuse_tuned_params = args.reuse_tuned_params
    program_name = os.path.basename(sys.argv[0])
    print(
        f"Example: python {program_name} --symbols ^GSPC QQQ "
        f"--download-years 3 --lookback-years 2 --offset-months 6"
    )
    print(
        f"Using lookback_years={lookback_years}, offset_months={offset_months}, "
        f"pop_ranges={pop_ranges}, gen_ranges={gen_ranges}, symbols={args.symbols}, "
        f"short_ema_bounds={short_ema_bounds}, long_ema_bounds={long_ema_bounds}, "
        f"download_years={args.download_years}, ga_seed={args.ga_seed}, "
        f"data_file={args.data_file}, data_files={args.data_files}, fund_glob={args.fund_glob}, "
        f"price_column={args.price_column}, profile_override_preset={args.profile_override_preset}, "
        f"ga_search_preset={args.ga_search_preset}, mutation_rates={mutation_rates}, "
        f"crossover_rates={crossover_rates}, reuse_tuned_params={reuse_tuned_params}\n"
    )
    if lookback_years <= 0:
        raise ValueError("lookback_years must be > 0")
    if offset_months < 0:
        raise ValueError("offset_months must be >= 0")

    downloaded_files = []
    if args.data_files:
        downloaded_files.extend(args.data_files)
    elif args.data_file:
        downloaded_files.append(args.data_file)
    else:
        local_fund_files = sorted(str(path.resolve()) for path in DATA_DIR.glob(args.fund_glob))
        if local_fund_files:
            downloaded_files.extend(local_fund_files)
            print(f"Found {len(local_fund_files)} local fund CSV file(s) in {DATA_DIR} matching {args.fund_glob}.")
        else:
            if args.download_years <= 0:
                raise ValueError("download_years must be > 0")
            if args.download_years < lookback_years:
                raise ValueError("download_years must be >= lookback_years")
            for symbol in args.symbols:
                downloaded_files.append(download_market_data(symbol, years=args.download_years))

    for csv_file in downloaded_files:
        print(f"\n=== Running backtest for {csv_file} ===")
        run_backtest_for_csv(
            csv_file,
            lookback_years_value=lookback_years,
            offset_months_value=offset_months,
            pop_ranges_value=pop_ranges,
            gen_ranges_value=gen_ranges,
            initial_capital=10000,
            strategy_profile_value=args.strategy_profile,
            ga_seed_value=args.ga_seed,
            mutation_rates_value=mutation_rates,
            crossover_rates_value=crossover_rates,
            short_ema_bounds_value=short_ema_bounds,
            long_ema_bounds_value=long_ema_bounds,
            reuse_tuned_params_value=reuse_tuned_params,
            price_column_value=args.price_column,
            ga_search_preset_value=args.ga_search_preset,
            profile_override_preset_value=args.profile_override_preset,
        )
