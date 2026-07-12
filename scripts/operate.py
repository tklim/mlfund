#!/usr/bin/env python3
"""Operational pipeline for fund data refresh, analysis reports, and scheduling."""

import argparse
import csv
import html
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd

from common import DATA_DIR, REPORTS_DIR, REPO_ROOT, ensure_dir, fund_label_from_data_file, resolve_repo_path, save_csv


DEFAULT_CONFIG = REPO_ROOT / "config" / "operation.json"


def load_config(path=DEFAULT_CONFIG):
    path = resolve_repo_path(path)
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    validate_config(config)
    return config


def validate_config(config):
    if float(config["upside_target"]) > 1 or float(config["upside_target"]) < -1:
        raise ValueError("upside_target must be a decimal return, for example 0.15 for 15%.")
    if float(config["downside_risk"]) > 0 or float(config["downside_risk"]) < -1:
        raise ValueError("downside_risk must be a negative decimal return, for example -0.08 for -8%.")
    if int(config["default_years"]) <= 0:
        raise ValueError("default_years must be positive.")
    if config["primary_horizon"] not in {str(item).split(":", 1)[0] for item in config["horizons"]}:
        raise ValueError("primary_horizon must match one configured horizon label.")
    if int(config.get("final_backtest", {}).get("top_funds", 0)) < 0:
        raise ValueError("final_backtest.top_funds must be 0 for all funds or a positive count.")
    forward = config.get("forward_decision", {})
    min_analogs = int(forward.get("min_independent_analogs", 6))
    max_analogs = int(forward.get("max_independent_analogs", 20))
    if min_analogs <= 0 or max_analogs < min_analogs:
        raise ValueError("forward_decision analog counts must be positive and max must be >= min.")
    if float(forward.get("prior_strength", 8)) < 0:
        raise ValueError("forward_decision.prior_strength must be non-negative.")


def cfg_path(config, key):
    return resolve_repo_path(config["reports"][key])


def python_cmd(script_name, *args):
    return [sys.executable, str(REPO_ROOT / "scripts" / script_name), *map(str, args)]


def build_refresh_data_command(config):
    return python_cmd(
        "download_fund.py",
        "--all",
        "--years",
        config["default_years"],
        "--manifest",
        cfg_path(config, "refresh_manifest"),
    )


def build_forward_decision_command(config):
    forward = config.get("forward_decision", {})
    return python_cmd(
        "fund_forward_decision.py",
        "--all",
        "--fund-glob",
        config["fund_glob"],
        "--date-column",
        config["date_column"],
        "--price-column",
        config["price_column"],
        "--horizons",
        *config["horizons"],
        "--primary-horizon",
        config["primary_horizon"],
        "--upside-target",
        config["upside_target"],
        "--downside-risk",
        config["downside_risk"],
        "--min-analogs",
        forward.get("min_independent_analogs", 6),
        "--max-analogs",
        forward.get("max_independent_analogs", 20),
        "--prior-strength",
        forward.get("prior_strength", 8),
        "--output-dir",
        cfg_path(config, "report_dir"),
        "--chart-dir",
        Path(config["reports"]["chart_dir"]) / "forward_decision",
        "--charts",
        "--all-horizon-chart",
        "--validate",
    )


def build_probability_command(config):
    return python_cmd(
        "fund_probability_analysis.py",
        "--all",
        "--fund-glob",
        config["fund_glob"],
        "--date-column",
        config["date_column"],
        "--price-column",
        config["price_column"],
        "--horizons",
        *config["horizons"],
        "--thresholds",
        "0",
        "0.05",
        "0.10",
        "--upside-thresholds",
        str(config["upside_target"]),
        "0.20",
        "0.25",
        "0.30",
        "--output-dir",
        cfg_path(config, "report_dir"),
    )


def build_strategy_review_command(config):
    return python_cmd(
        "fund_strategy_review.py",
        "--report-dir",
        cfg_path(config, "report_dir"),
        "--chart-dir",
        Path(config["reports"]["chart_dir"]) / "strategy_review",
    )


def build_final_backtest_command(config):
    final_backtest = config.get("final_backtest", {})
    return python_cmd(
        "final_backtest_from_summary.py",
        "--top-funds",
        final_backtest.get("top_funds", 0),
        "--price-column",
        config["price_column"],
    )


def build_backtest_commands(config):
    backtest = config["backtest"]
    commands = []
    for lookback in backtest["lookback_years"]:
        for offset in backtest["offset_months"]:
            commands.append(
                python_cmd(
                    "backtest-ema-ga10-index.py",
                    "--lookback-years",
                    lookback,
                    "--offset-months",
                    offset,
                    "--pop_ranges",
                    backtest["population"],
                    "--gen_ranges",
                    backtest["generations"],
                    "--ga-search-preset",
                    backtest["ga_search_preset"],
                    "--price-column",
                    config["price_column"],
                    "--fund-glob",
                    config["fund_glob"],
                    "--reuse-tuned-params",
                )
            )
    return commands


def command_text(command):
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


def run_commands(commands, dry_run=False):
    results = []
    for command in commands:
        print(command_text(command))
        if dry_run:
            results.append({"command": command_text(command), "returncode": 0, "dry_run": True})
            continue
        completed = subprocess.run(command, cwd=REPO_ROOT)
        results.append({"command": command_text(command), "returncode": completed.returncode, "dry_run": False})
        if completed.returncode != 0:
            raise subprocess.CalledProcessError(completed.returncode, command)
    return results


def run_one_command(command):
    text = command_text(command)
    print(f"[start] {text}")
    completed = subprocess.run(command, cwd=REPO_ROOT)
    print(f"[done {completed.returncode}] {text}")
    return {"command": text, "returncode": completed.returncode, "dry_run": False}


def run_commands_parallel(commands, max_workers, dry_run=False):
    if max_workers < 1:
        raise ValueError("--max-workers must be at least 1.")
    if dry_run or max_workers == 1 or len(commands) <= 1:
        return run_commands(commands, dry_run=dry_run)

    workers = min(max_workers, len(commands))
    print(f"Running {len(commands)} command(s) with max_workers={workers}.")
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(run_one_command, command) for command in commands]
        for future in as_completed(futures):
            results.append(future.result())

    failed = [result for result in results if result["returncode"] != 0]
    if failed:
        raise subprocess.CalledProcessError(failed[0]["returncode"], failed[0]["command"])
    return results


def data_health_rows(config):
    rows = []
    required = [config["date_column"], "NAV", "Dividend", config["price_column"]]
    now = pd.Timestamp(datetime.now().date())
    for csv_path in sorted(DATA_DIR.glob(config["fund_glob"])):
        label = fund_label_from_data_file(csv_path)
        row = {
            "fund_label": label,
            "source_file": str(csv_path),
            "row_count": 0,
            "latest_date": "",
            "missing_columns": "",
            "duplicate_dates": "",
            "null_prices": "",
            "freshness_status": "error",
            "warning": "",
        }
        try:
            df = pd.read_csv(csv_path)
            missing = [col for col in required if col not in df.columns]
            row["missing_columns"] = ";".join(missing)
            row["row_count"] = len(df)
            if config["date_column"] in df.columns:
                dates = pd.to_datetime(df[config["date_column"]], errors="coerce")
                row["duplicate_dates"] = int(dates.duplicated().sum())
                latest = dates.max()
                if pd.notna(latest):
                    row["latest_date"] = latest.date().isoformat()
                    age_days = int((now - pd.Timestamp(latest.date())).days)
                    row["freshness_status"] = "fresh" if age_days <= int(config["stale_after_days"]) else "stale"
                    row["age_days"] = age_days
            if config["price_column"] in df.columns:
                row["null_prices"] = int(pd.to_numeric(df[config["price_column"]], errors="coerce").isna().sum())
            if missing:
                row["freshness_status"] = "invalid"
                row["warning"] = "missing required columns"
        except Exception as exc:
            row["warning"] = str(exc)
        rows.append(row)
    return rows


def write_data_health(config):
    rows = data_health_rows(config)
    path = cfg_path(config, "data_health")
    save_csv(pd.DataFrame(rows), path)
    return path, rows


def fmt_pct(value):
    try:
        numeric = float(value)
        return "" if pd.isna(numeric) else f"{numeric * 100:.1f}%"
    except (TypeError, ValueError):
        return ""


def fmt_percent_points(value):
    try:
        numeric = float(value)
        return "" if pd.isna(numeric) else f"{numeric:.1f}%"
    except (TypeError, ValueError):
        return ""


def read_csv_if_exists(path):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def strategy_signal(report_dir):
    md_path = Path(report_dir) / "fund_strategy_review.md"
    if not md_path.exists():
        return "Strategy review not available."
    for line in md_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "Current signal from best-run log:" in line:
            return line.strip("- ").replace("`", "")
    return "Strategy review generated; current signal not found."


def bounded(value, lower=0.0, upper=1.0):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return lower
    if pd.isna(numeric):
        return lower
    return min(upper, max(lower, numeric))


def build_decision_scores(dashboard, best_by_fund, health):
    """Combine forward outcomes and GA confirmation into transparent evidence scores.

    Buy/Sell Scores are decision-support indices, not calibrated probabilities.
    Low effective sample size and stale data shrink scores toward the neutral 50.
    """
    columns = [
        "Fund Label",
        "Conclusion",
        "Buy Score",
        "Sell Score",
        "Score Spread",
        "Upside Probability",
        "Downside Probability",
        "Expected Forward Return",
        "Evidence Reliability",
        "Effective Observations",
        "Confidence Level",
        "GA Signal",
        "Data Status",
    ]
    if dashboard.empty:
        return pd.DataFrame(columns=columns)

    strategy_rows = {}
    if not best_by_fund.empty and "fund_label" in best_by_fund.columns:
        strategy_rows = {
            str(row["fund_label"]): row
            for _, row in best_by_fund.drop_duplicates("fund_label", keep="first").iterrows()
        }
    health_rows = {}
    if not health.empty and "fund_label" in health.columns:
        health_rows = {
            str(row["fund_label"]): row
            for _, row in health.drop_duplicates("fund_label", keep="first").iterrows()
        }

    score_rows = []
    for _, row in dashboard.iterrows():
        fund = str(row.get("Fund Label", ""))
        strategy = strategy_rows.get(fund, {})
        fund_health = health_rows.get(fund, {})

        upside_probability = bounded(row.get("Probability >= Upside Target", 0.5))
        downside_probability = bounded(row.get("Probability <= Downside Risk", 0.5))
        positive_probability = bounded(row.get("Probability > 0", 0.5))
        expected_return = float(row.get("Expected Forward Return", 0.0) or 0.0)
        upside_target = max(1e-9, abs(float(row.get("Upside Target", 0.15) or 0.15)))
        downside_risk = max(1e-9, abs(float(row.get("Downside Risk", -0.08) or -0.08)))
        expected_buy_support = bounded(expected_return / upside_target)
        expected_sell_support = bounded(-expected_return / downside_risk)

        trend = str(row.get("Current Trend State", "")).lower()
        trend_buy_support = {
            "uptrend": 1.0,
            "softening uptrend": 0.65,
            "recovering / mixed": 0.50,
            "downtrend": 0.0,
        }.get(trend, 0.5)
        trend_sell_support = 1.0 - trend_buy_support

        ga_signal = str(strategy.get("ga_signal", "unknown"))
        ga_signal_upper = ga_signal.upper()
        if "BUY" in ga_signal_upper or "INVESTED" in ga_signal_upper:
            ga_buy_support, ga_sell_support = 1.0, 0.0
        elif "SELL" in ga_signal_upper or "EXIT" in ga_signal_upper or "CASH" in ga_signal_upper:
            ga_buy_support, ga_sell_support = 0.0, 1.0
        else:
            ga_buy_support = ga_sell_support = 0.5

        ga_excess = strategy.get("excess_annualized_return_pct", 0.0)
        ga_quality = bounded(0.5 + (float(ga_excess) / 40.0 if pd.notna(ga_excess) else 0.0))

        raw_buy = 100 * (
            0.30 * upside_probability
            + 0.20 * positive_probability
            + 0.20 * expected_buy_support
            + 0.10 * trend_buy_support
            + 0.10 * ga_buy_support
            + 0.10 * ga_quality
        )
        raw_sell = 100 * (
            0.30 * downside_probability
            + 0.20 * (1.0 - positive_probability)
            + 0.20 * expected_sell_support
            + 0.10 * trend_sell_support
            + 0.10 * ga_sell_support
            + 0.10 * (1.0 - ga_quality)
        )

        effective_observations = max(0.0, float(row.get("Effective Observations", 0.0) or 0.0))
        confidence = str(row.get("Confidence Level", "LOW")).upper()
        confidence_cap = {"LOW": 0.35, "MEDIUM": 0.65, "NORMAL": 1.0}.get(confidence, 0.35)
        reliability = min(1.0, effective_observations / 20.0, confidence_cap)
        data_status = str(fund_health.get("freshness_status", "unknown")).lower()
        if data_status != "fresh":
            reliability *= 0.5

        buy_score = 50.0 + (raw_buy - 50.0) * reliability
        sell_score = 50.0 + (raw_sell - 50.0) * reliability
        spread = buy_score - sell_score
        if data_status not in {"fresh", "unknown"}:
            conclusion = "DATA WARNING"
        elif buy_score >= 70 and spread >= 15:
            conclusion = "STRONG BUY EVIDENCE"
        elif buy_score >= 60 and spread >= 10:
            conclusion = "BUY LEAN"
        elif sell_score >= 70 and spread <= -15:
            conclusion = "STRONG SELL EVIDENCE"
        elif sell_score >= 60 and spread <= -10:
            conclusion = "SELL LEAN"
        else:
            conclusion = "HOLD / WATCH"

        score_rows.append(
            {
                "Fund Label": fund,
                "Conclusion": conclusion,
                "Buy Score": round(buy_score, 1),
                "Sell Score": round(sell_score, 1),
                "Score Spread": round(spread, 1),
                "Upside Probability": upside_probability,
                "Downside Probability": downside_probability,
                "Expected Forward Return": expected_return,
                "Evidence Reliability": round(reliability, 2),
                "Effective Observations": int(effective_observations),
                "Confidence Level": confidence,
                "GA Signal": ga_signal,
                "Data Status": data_status,
            }
        )

    scores = pd.DataFrame(score_rows, columns=columns)
    scores["Conviction"] = scores[["Buy Score", "Sell Score"]].max(axis=1)
    scores = scores.sort_values(["Conviction", "Score Spread"], ascending=[False, False])
    return scores.drop(columns="Conviction").reset_index(drop=True)


def write_decision_brief(config):
    report_dir = cfg_path(config, "report_dir")
    ensure_dir(report_dir)
    dashboard = read_csv_if_exists(report_dir / "fund_forward_decision_dashboard.csv")
    health = read_csv_if_exists(cfg_path(config, "data_health"))
    probability = read_csv_if_exists(report_dir / "fund_probability_cross_fund_summary.csv")
    best_by_fund = read_csv_if_exists(report_dir / "fund_strategy_best_by_fund.csv")
    decision_scores = build_decision_scores(dashboard, best_by_fund, health)
    score_path = None
    if not decision_scores.empty:
        score_path = save_csv(decision_scores, report_dir / "fund_decision_scores.csv")

    lines = [
        "# Daily Investment Decision Brief",
        "",
        f"Generated: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "This is decision-support output based on historical NAV/TotalReturn records; it is not personalized financial advice.",
        "",
        "## Data Health",
        "",
    ]
    if health.empty:
        lines.append("Data-health summary is not available.")
    else:
        stale = health[health["freshness_status"].astype(str).ne("fresh")]
        lines.append(f"- Funds checked: `{len(health)}`")
        lines.append(f"- Fresh funds: `{len(health) - len(stale)}`")
        lines.append(f"- Warnings: `{len(stale)}`")
        if not stale.empty:
            for _, row in stale.iterrows():
                lines.append(f"- {row.get('fund_label')}: {row.get('freshness_status')} latest={row.get('latest_date')} {row.get('warning', '')}")

    lines.extend(["", "## Decision Dashboard", ""])
    if dashboard.empty:
        lines.append("Forward decision dashboard is not available.")
    else:
        cols = [
            "Fund Label",
            "Latest Date",
            "Decision Label",
            "Confidence Level",
            "Analog Count",
            "Expected Forward Return",
            "Probability >= Upside Target",
            "Probability <= Downside Risk",
        ]
        present = [col for col in cols if col in dashboard.columns]
        lines.append("| " + " | ".join(present) + " |")
        lines.append("| " + " | ".join(["---"] * len(present)) + " |")
        for _, row in dashboard[present].iterrows():
            values = []
            for col in present:
                value = row[col]
                if col.startswith("Probability") or col == "Expected Forward Return":
                    value = fmt_pct(value)
                values.append(str(value))
            lines.append("| " + " | ".join(values) + " |")

    lines.extend(["", "## Best GA Strategy By Fund", ""])
    if best_by_fund.empty:
        lines.append("Per-fund GA strategy summary is not available. Run `python scripts/operate.py report` after backtests complete.")
    else:
        cols = [
            "fund_label",
            "ga_signal",
            "last_trade_date",
            "adaptive_annualized_return_pct",
            "excess_annualized_return_pct",
            "sharpe",
            "max_dd_pct",
            "lookback_years",
            "offset_months",
            "last_short_ema",
            "last_long_ema",
        ]
        present = [col for col in cols if col in best_by_fund.columns]
        labels = {
            "fund_label": "Fund Label",
            "ga_signal": "GA Signal",
            "last_trade_date": "Last GA Trade",
            "adaptive_annualized_return_pct": "GA Adaptive Ann.",
            "excess_annualized_return_pct": "GA Excess Ann.",
            "sharpe": "Sharpe",
            "max_dd_pct": "Max DD",
            "lookback_years": "Lookback Y",
            "offset_months": "Offset M",
            "last_short_ema": "Short EMA",
            "last_long_ema": "Long EMA",
        }
        lines.append("| " + " | ".join(labels.get(col, col) for col in present) + " |")
        lines.append("| " + " | ".join(["---"] * len(present)) + " |")
        for _, row in best_by_fund[present].iterrows():
            values = []
            for col in present:
                value = row[col]
                if col in {"adaptive_annualized_return_pct", "excess_annualized_return_pct", "max_dd_pct"}:
                    value = fmt_percent_points(value)
                elif col == "sharpe":
                    try:
                        value = f"{float(value):.2f}"
                    except (TypeError, ValueError):
                        value = ""
                values.append(str(value))
            lines.append("| " + " | ".join(values) + " |")

    lines.extend(["", "## Probability Highlights", ""])
    if probability.empty:
        lines.append("Cross-fund probability summary is not available.")
    else:
        highlight_cols = [col for col in probability.columns if "Probability >=" in col][:4]
        cols = ["Fund Label", *highlight_cols]
        cols = [col for col in cols if col in probability.columns]
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
        for _, row in probability[cols].iterrows():
            values = [str(row[col]) if col == "Fund Label" else fmt_pct(row[col]) for col in cols]
            lines.append("| " + " | ".join(values) + " |")

    lines.extend(["", "## Conclusion: Buy and Sell Evidence", ""])
    if decision_scores.empty:
        lines.append("Decision evidence scores are not available.")
    else:
        lines.extend(
            [
                "Buy Score and Sell Score are transparent 0-100 evidence indices, not calibrated probabilities. Scores combine conditional forward outcomes, expected return, trend state, and GA confirmation, then shrink toward neutral `50` when effective observations are limited or data is stale.",
                "",
            ]
        )
        score_cols = [
            "Fund Label",
            "Conclusion",
            "Buy Score",
            "Sell Score",
            "Score Spread",
            "Upside Probability",
            "Downside Probability",
            "Expected Forward Return",
            "Evidence Reliability",
            "Effective Observations",
        ]
        lines.append("| " + " | ".join(score_cols) + " |")
        lines.append("| " + " | ".join(["---"] * len(score_cols)) + " |")
        for _, row in decision_scores[score_cols].iterrows():
            values = []
            for col in score_cols:
                value = row[col]
                if col in {"Upside Probability", "Downside Probability", "Expected Forward Return", "Evidence Reliability"}:
                    value = fmt_pct(value)
                elif col in {"Buy Score", "Sell Score", "Score Spread"}:
                    value = f"{float(value):.1f}"
                values.append(str(value))
            lines.append("| " + " | ".join(values) + " |")

        buy_leans = decision_scores[decision_scores["Conclusion"].isin(["BUY LEAN", "STRONG BUY EVIDENCE"])]
        sell_leans = decision_scores[decision_scores["Conclusion"].isin(["SELL LEAN", "STRONG SELL EVIDENCE"])]
        lines.extend(
            [
                "",
                f"- Buy-evidence candidates: {', '.join(buy_leans['Fund Label']) if not buy_leans.empty else 'none at the current reliability threshold'}.",
                f"- Sell-evidence candidates: {', '.join(sell_leans['Fund Label']) if not sell_leans.empty else 'none at the current reliability threshold'}.",
                "- Upside/Downside Probability columns are empirical conditional outcome frequencies. They are the probability estimates; Buy/Sell Scores are synthesis indices.",
            ]
        )

    lines.extend(
        [
            "",
            "## Strategy Signal",
            "",
            "- Overall champion signal retained for reference only; use the fund-by-fund GA table above for strategy decisions.",
            f"- Overall champion: {strategy_signal(report_dir)}",
            "",
            "## Detailed Reports",
            "",
            "- [Forward decision dashboard](fund_forward_decision_dashboard.html)",
            "- [Strategy review](fund_strategy_review.html)",
            "- [Data health](data_health.csv)",
            "- [Buy/sell evidence scores](fund_decision_scores.csv)",
            "- [Operation run history](operation_run_history.csv)",
        ]
    )

    md = "\n".join(lines) + "\n"
    md_path = cfg_path(config, "decision_brief_md")
    html_path = cfg_path(config, "decision_brief_html")
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(markdown_to_simple_html(md, "Daily Investment Decision Brief"), encoding="utf-8")
    return tuple(path for path in [md_path, html_path, score_path] if path is not None)


def markdown_to_simple_html(markdown, title):
    body = []
    in_table = False
    for line in markdown.splitlines():
        if line.startswith("# "):
            body.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_table:
                body.append("</tbody></table>")
                in_table = False
            body.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("| "):
            cells = [render_inline(cell.strip()) for cell in line.strip("|").split("|")]
            if set(cells) == {"---"}:
                continue
            if not in_table:
                body.append("<table><tbody>")
                in_table = True
            body.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
        elif line.startswith("- "):
            if in_table:
                body.append("</tbody></table>")
                in_table = False
            body.append(f"<p>{render_inline(line[2:])}</p>")
        elif line.strip():
            if in_table:
                body.append("</tbody></table>")
                in_table = False
            body.append(f"<p>{render_inline(line)}</p>")
    if in_table:
        body.append("</tbody></table>")
    style = "body{font-family:Arial,sans-serif;margin:32px;line-height:1.4}table{border-collapse:collapse;width:100%;margin:12px 0}td{border:1px solid #ddd;padding:6px}tr:first-child{font-weight:bold;background:#f3f6f8}h1,h2{color:#1f2937}"
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{style}</style></head><body>{''.join(body)}</body></html>"


def render_inline(text):
    parts = []
    pos = 0
    for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", str(text)):
        parts.append(html.escape(str(text)[pos : match.start()]))
        label = html.escape(match.group(1))
        href = html.escape(match.group(2), quote=True)
        parts.append(f'<a href="{href}">{label}</a>')
        pos = match.end()
    parts.append(html.escape(str(text)[pos:]))
    rendered = "".join(parts)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)


def append_operation_history(config, mode, command_results, outputs, started_at, status, warnings=0, errors=0):
    path = cfg_path(config, "operation_history")
    ensure_dir(path.parent)
    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "command": " | ".join(result["command"] for result in command_results),
        "fund_count": len(list(DATA_DIR.glob(config["fund_glob"]))),
        "warning_count": warnings,
        "error_count": errors,
        "output_paths": ";".join(str(path) for path in outputs),
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "exit_status": status,
    }
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return path


def build_report_commands(config):
    return [
        build_forward_decision_command(config),
        build_probability_command(config),
        build_strategy_review_command(config),
        build_final_backtest_command(config),
    ]


def run_mode(mode, config, dry_run=False, max_workers=1):
    started_at = datetime.now()
    outputs = []
    command_results = []
    warnings = 0
    errors = 0

    if mode == "refresh-data":
        commands = [build_refresh_data_command(config)]
    elif mode == "report":
        commands = build_report_commands(config)
    elif mode == "daily":
        commands = [build_refresh_data_command(config), *build_report_commands(config)]
    elif mode == "deep-backtest":
        commands = build_backtest_commands(config)
    elif mode == "status":
        print_status(config)
        return 0
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    if dry_run:
        command_results = run_commands_parallel(commands, max_workers=max_workers if mode == "deep-backtest" else 1, dry_run=True)
        return 0

    try:
        if mode == "deep-backtest":
            command_results = run_commands_parallel(commands, max_workers=max_workers, dry_run=False)
        else:
            command_results = run_commands(commands, dry_run=False)
        if mode in {"daily", "report"}:
            health_path, health_rows = write_data_health(config)
            warnings = len([row for row in health_rows if row.get("freshness_status") != "fresh"])
            outputs.append(health_path)
            outputs.extend(write_decision_brief(config))
        status = "ok"
    except Exception:
        status = "failed"
        errors = 1
        append_operation_history(config, mode, command_results, outputs, started_at, status, warnings, errors)
        raise

    if mode != "status":
        outputs.append(append_operation_history(config, mode, command_results, outputs, started_at, status, warnings, errors))
    return 0


def print_status(config):
    health_path = cfg_path(config, "data_health")
    history_path = cfg_path(config, "operation_history")
    brief_path = cfg_path(config, "decision_brief_html")
    print(f"Repo: {REPO_ROOT}")
    print(f"Data files: {len(list(DATA_DIR.glob(config['fund_glob'])))} matching {config['fund_glob']}")
    print(f"Data health: {health_path} {'exists' if health_path.exists() else 'missing'}")
    print(f"Decision brief: {brief_path} {'exists' if brief_path.exists() else 'missing'}")
    print(f"Operation history: {history_path} {'exists' if history_path.exists() else 'missing'}")


def install_scheduler(config, task_name=None, time_value=None, dry_run=False):
    task_name = task_name or config["schedule"]["task_name"]
    time_value = time_value or config["schedule"]["time"]
    command = f'cmd /c cd /d "{REPO_ROOT}" && "{sys.executable}" "{REPO_ROOT / "scripts" / "operate.py"}" daily'
    schtasks = ["schtasks", "/Create", "/TN", task_name, "/TR", command, "/SC", "DAILY", "/ST", time_value, "/F"]
    print(command_text(schtasks))
    if dry_run:
        return 0
    completed = subprocess.run(schtasks)
    return completed.returncode


def parse_args():
    parser = argparse.ArgumentParser(description="Run operational fund analysis workflows.")
    parser.add_argument("mode", choices=["daily", "refresh-data", "deep-backtest", "report", "status", "install-scheduler"])
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Operation JSON config path.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them or writing reports.")
    parser.add_argument("--task-name", default=None, help="Windows Task Scheduler task name.")
    parser.add_argument("--time", default=None, help="Windows Task Scheduler daily time, for example 18:30.")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Maximum concurrent sessions for deep-backtest only. Use up to 4 on this workstation.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)
    if args.mode == "install-scheduler":
        return install_scheduler(config, task_name=args.task_name, time_value=args.time, dry_run=args.dry_run)
    return run_mode(args.mode, config, dry_run=args.dry_run, max_workers=args.max_workers)


if __name__ == "__main__":
    raise SystemExit(main())
