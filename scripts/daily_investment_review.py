#!/usr/bin/env python3
"""
Daily fund data refresh and investment decision report.

The daily path is intentionally lightweight: refresh 5Y fund data, run the
conditional forward-decision dashboard, and write a dated summary/log.
"""

import argparse
import csv
import html
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd

from common import (
    CHARTS_DIR,
    DATA_DIR,
    REPORTS_DIR,
    infer_total_return_method,
    resolve_repo_path,
)
from download_fund import TRACKED_FUNDS, download_fund


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DAILY_REPORT_DIR = REPORTS_DIR / "daily"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Refresh fund data and generate the daily investment decision dashboard."
    )
    parser.add_argument(
        "--fund-ids",
        nargs="+",
        default=None,
        help="Fund IDs to refresh. Defaults to all TRACKED_FUNDS.",
    )
    parser.add_argument("--years", type=int, default=5, help="NAV history years to download/analyze.")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use latest local data files instead of downloading new data.",
    )
    parser.add_argument("--primary-horizon", default="6M", help="Headline decision horizon.")
    parser.add_argument("--upside-target", type=float, default=0.15, help="Upside target as decimal.")
    parser.add_argument("--downside-risk", type=float, default=-0.08, help="Downside risk threshold as decimal.")
    parser.add_argument(
        "--report-dir",
        default=str(REPORTS_DIR),
        help="Forward-decision report output directory.",
    )
    parser.add_argument(
        "--daily-dir",
        default=str(DAILY_REPORT_DIR),
        help="Directory for dated daily logs and summaries.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used to invoke fund_forward_decision.py.",
    )
    return parser.parse_args()


def fund_label_prefix(fund_id):
    return f"{fund_id}_"


def latest_local_fund_file(fund_id, years):
    pattern = f"{fund_label_prefix(fund_id)}*_nav_{years}Y*.csv"
    candidates = sorted(DATA_DIR.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def download_or_find_files(fund_ids, years, skip_download):
    results = []
    log_parts = []
    for fund_id in fund_ids:
        if skip_download:
            path = latest_local_fund_file(fund_id, years)
            if path is None:
                raise FileNotFoundError(f"No local {years}Y CSV found for {fund_id}.")
            total_return_method = infer_total_return_method(
                pd.read_csv(path, nrows=1),
                "TotalReturn",
            )
            results.append(
                {
                    "fund_id": fund_id,
                    "fund_name": "",
                    "fund_label": path.stem,
                    "current_nav": "",
                    "current_date": "",
                    "change": "",
                    "change_pct": "",
                    "total_return_method": total_return_method,
                    "records": "",
                    "output_path": str(path),
                    "mode": "local",
                }
            )
            log_parts.append(f"Using local file for {fund_id}: {path}")
            continue

        buffer = StringIO()
        with redirect_stdout(buffer), redirect_stderr(buffer):
            result = download_fund(fund_id, years=years)
        result["mode"] = "download"
        results.append(result)
        log_parts.append(buffer.getvalue())
    return results, "\n".join(log_parts)


def run_forward_decision(data_files, args):
    command = [
        args.python,
        str(SCRIPT_DIR / "fund_forward_decision.py"),
        "--data-files",
        *[str(path) for path in data_files],
        "--primary-horizon",
        args.primary_horizon,
        "--upside-target",
        str(args.upside_target),
        "--downside-risk",
        str(args.downside_risk),
        "--charts",
        "--all-horizon-chart",
        "--validate",
        "--output-dir",
        str(resolve_repo_path(args.report_dir)),
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return command, completed


def run_technical_signal_review(data_files, args, run_id):
    command = [
        args.python,
        str(SCRIPT_DIR / "technical_signal_review.py"),
        "--data-files",
        *[str(path) for path in data_files],
        "--primary-horizon",
        args.primary_horizon,
        "--upside-target",
        str(args.upside_target),
        "--downside-risk",
        str(args.downside_risk),
        "--validate",
        "--charts",
        "--run-id",
        run_id,
        "--chart-dir",
        str(CHARTS_DIR / "daily_technical"),
        "--output-dir",
        str(resolve_repo_path(args.report_dir)),
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return command, completed


def read_dashboard(report_dir):
    path = resolve_repo_path(report_dir) / "fund_forward_decision_dashboard.csv"
    if not path.exists():
        raise FileNotFoundError(f"Decision dashboard was not generated: {path}")
    return path, pd.read_csv(path)


def read_technical_review(report_dir):
    path = resolve_repo_path(report_dir) / "technical_signal_review.csv"
    if not path.exists():
        raise FileNotFoundError(f"Technical signal review was not generated: {path}")
    return path, pd.read_csv(path)


def require_unique_fund_labels(frame, report_name):
    if "Fund Label" not in frame.columns:
        raise ValueError(f"{report_name} is missing the Fund Label column.")
    duplicates = frame.loc[frame["Fund Label"].duplicated(False), "Fund Label"].dropna().unique()
    if len(duplicates):
        raise ValueError(f"{report_name} contains duplicate fund labels: {sorted(duplicates)}")


def write_csv(rows, path, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def format_percent(value):
    value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(value):
        return ""
    return f"{value * 100:.1f}%"


def format_number(value, decimals=2):
    value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(value):
        return ""
    return f"{value:.{decimals}f}"


def agreement_label(row):
    decision = str(row.get("Decision Label", ""))
    state = str(row.get("Technical State", ""))
    if decision == "BUY" and state == "BUY/HOLD invested":
        return "Aligned opportunity"
    if decision == "SELL / AVOID" and state == "SELL/CASH":
        return "Aligned caution"
    if decision == "BUY" and state == "SELL/CASH":
        return "Conflict: probability bullish, technical cash"
    if decision == "SELL / AVOID" and state == "BUY/HOLD invested":
        return "Conflict: probability cautious, technical invested"
    if decision == "HOLD / WATCH" and state == "BUY/HOLD invested":
        return "Neutral, technically invested"
    if decision == "HOLD / WATCH" and state == "SELL/CASH":
        return "Neutral, technically cautious"
    return "Review needed"


def status_class(value):
    text = str(value or "").lower()
    if "aligned opportunity" in text or text == "buy" or "buy/hold" in text:
        return "good"
    if "aligned caution" in text or "sell" in text or "conflict" in text:
        return "risk"
    return "watch"


def render_table(df, columns):
    existing = [col for col in columns if col in df.columns]
    if not existing:
        return "<p>No rows available.</p>"
    header = "".join(f"<th>{html.escape(col)}</th>" for col in existing)
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col in existing:
            value = row.get(col, "")
            if "Probability" in col or "Return" in col or "Risk" in col:
                text = format_percent(value)
            elif "Score" in col:
                text = format_number(value, 2)
            else:
                text = "" if pd.isna(value) else str(value)
            classes = ""
            if col in {"Decision Label", "Technical State", "Agreement"}:
                classes = f' class="{status_class(text)}"'
            cells.append(f"<td{classes}>{html.escape(text)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_technical_chart_gallery(df):
    if "Technical Chart File" not in df.columns:
        return "<p>No technical backtest charts were generated.</p>"
    blocks = []
    for _, row in df.iterrows():
        chart_value = row.get("Technical Chart File", "")
        chart_path = Path(str(chart_value)) if str(chart_value).strip() else None
        if not chart_path or not chart_path.exists():
            continue
        simple_value = row.get("Simple Technical Chart File", "")
        simple_path = Path(str(simple_value)) if str(simple_value).strip() else None
        fund_label = str(row.get("Fund Label", ""))
        tech_state = str(row.get("Technical State", ""))
        last_action = str(row.get("Last Signal Action", ""))
        last_date = str(row.get("Last Signal Date", ""))
        link_html = ""
        if simple_path and simple_path.exists():
            link_html = f' <a href="{html.escape(simple_path.as_uri())}">simple chart</a>'
        blocks.append(
            "<figure>"
            f'<img src="{html.escape(chart_path.as_uri())}" alt="{html.escape(fund_label)} technical backtest chart">'
            f"<figcaption><strong>{html.escape(fund_label)}</strong> | "
            f"{html.escape(tech_state)} | Last signal: {html.escape(last_action)} "
            f"{html.escape(last_date)}{link_html}</figcaption>"
            "</figure>"
        )
    if not blocks:
        return "<p>No technical backtest charts were generated.</p>"
    return f'<div class="technical-gallery">{"".join(blocks)}</div>'


def generate_daily_html(run_id, args, combined, download_results, paths):
    html_path = resolve_repo_path(args.daily_dir) / f"daily_investment_review_{run_id}.html"
    latest_html_path = resolve_repo_path(args.daily_dir) / "daily_investment_review_latest.html"

    decision_counts = combined.get("Decision Label", pd.Series(dtype=str)).value_counts().to_dict()
    tech_counts = combined.get("Technical State", pd.Series(dtype=str)).value_counts().to_dict()
    chart_dir = resolve_repo_path(args.report_dir).parent / "charts" / "forward_decision"
    primary_chart = chart_dir / "forward_decision_score_by_fund.png"
    heatmap_chart = chart_dir / "forward_decision_score_all_horizons.png"

    daily_columns = [
        "Fund Label",
        "Forward Method Version",
        "Decision Label",
        "Technical State",
        "Agreement",
        "Probability >= Upside Target",
        "Probability <= Downside Risk",
        "Expected Forward Return",
        "Conditional Expected Edge",
        "Relative Upside Probability Lift",
        "Relative Downside Probability Lift",
        "Technical Absolute Probability >= Upside Target",
        "Technical Absolute Probability <= Downside Risk",
        "Technical Absolute Expected Forward Return",
        "Last Signal Action",
        "Last Signal Date",
        "Technical Confidence",
        "Decision Score",
    ]
    probability_columns = [
        "Fund Label",
        "Forward Method Version",
        "Decision Reason",
        "Probability > 0",
        "Probability >= Upside Target",
        "Probability <= Downside Risk",
        "Expected Forward Return",
        "Relative Upside Threshold (P75)",
        "Relative Upside Probability",
        "Base Relative Upside Probability",
        "Relative Upside Probability Lift",
        "Relative Downside Threshold (P25)",
        "Relative Downside Probability",
        "Base Relative Downside Probability",
        "Relative Downside Probability Lift",
        "Confidence Level",
        "Analog Count",
        "Base Observations",
    ]
    technical_columns = [
        "Fund Label",
        "Technical State",
        "Last Signal Action",
        "Last Signal Date",
        "Days Since Last Signal",
        "Technical Probability > 0",
        "Technical Absolute Probability >= Upside Target",
        "Technical Absolute Probability <= Downside Risk",
        "Technical Observation Count",
        "Technical Confidence",
        "Selected Short EMA",
        "Selected Long EMA",
    ]
    download_rows = pd.DataFrame(download_results)

    chart_blocks = []
    for chart, label in [(primary_chart, "6M probability score chart"), (heatmap_chart, "All-horizon score heatmap")]:
        if chart.exists():
            chart_src = chart.as_uri()
            chart_blocks.append(
                f'<figure><img src="{html.escape(chart_src)}" alt="{html.escape(label)}"><figcaption>{html.escape(label)}</figcaption></figure>'
            )

    css = """
    body { font-family: Segoe UI, Arial, sans-serif; margin: 28px; color: #111827; background: #f8fafc; }
    h1 { margin-bottom: 4px; }
    h2 { margin-top: 28px; }
    .subtle { color: #475569; margin-top: 0; }
    .cards { display: flex; gap: 12px; flex-wrap: wrap; margin: 18px 0; }
    .card { background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 14px; min-width: 160px; }
    .card strong { display: block; font-size: 20px; margin-top: 4px; }
    table { border-collapse: collapse; width: 100%; background: white; margin: 12px 0 24px; font-size: 13px; }
    th, td { border: 1px solid #e5e7eb; padding: 7px 8px; text-align: left; vertical-align: top; }
    th { background: #f1f5f9; position: sticky; top: 0; z-index: 1; }
    tr:nth-child(even) td { background: #fbfdff; }
    .good { color: #047857; font-weight: 700; }
    .watch { color: #b45309; font-weight: 700; }
    .risk { color: #b91c1c; font-weight: 700; }
    .charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; align-items: start; }
    .technical-gallery { display: grid; grid-template-columns: repeat(auto-fit, minmax(520px, 1fr)); gap: 16px; align-items: start; }
    figure { margin: 0; background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; }
    img { max-width: 100%; height: auto; display: block; }
    figcaption { color: #475569; font-size: 12px; margin-top: 6px; }
    """

    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Daily Investment Review {html.escape(run_id)}</title>
<style>{css}</style>
</head>
<body>
<h1>Daily Investment Review</h1>
<p class="subtle">Run {html.escape(run_id)} | Headline horizon: {html.escape(args.primary_horizon)} | Decision support, not financial advice.</p>
<div class="cards">
  <div class="card">Funds analyzed<strong>{len(combined)}</strong></div>
  <div class="card">Probability BUY<strong>{decision_counts.get('BUY', 0)}</strong></div>
  <div class="card">Probability SELL/AVOID<strong>{decision_counts.get('SELL / AVOID', 0)}</strong></div>
  <div class="card">Technically invested<strong>{tech_counts.get('BUY/HOLD invested', 0)}</strong></div>
</div>
<h2>Daily View</h2>
{render_table(combined, daily_columns)}
<h2>Charts</h2>
<div class="charts">{''.join(chart_blocks) if chart_blocks else '<p>No charts were generated.</p>'}</div>
<h2>Technical Backtest Charts</h2>
{render_technical_chart_gallery(combined)}
<h2>Probability Detail</h2>
{render_table(combined, probability_columns)}
<h2>Absolute-Threshold Technical Likelihood</h2>
<p class="subtle">Separate model for descriptive likelihoods; these fields are not inputs to the V2 forward decision.</p>
{render_table(combined, technical_columns)}
<h2>Data Files</h2>
{render_table(download_rows, ['fund_id', 'fund_label', 'current_date', 'records', 'output_path', 'mode'])}
<h2>Output Files</h2>
<p class="subtle">Forward dashboard: {html.escape(str(paths['dashboard_path']))}<br>
Technical review: {html.escape(str(paths['technical_path']))}<br>
Daily summary CSV: {html.escape(str(paths['summary_path']))}<br>
Run log: {html.escape(str(paths['log_path']))}</p>
</body>
</html>"""
    html_path.write_text(body, encoding="utf-8")
    latest_html_path.write_text(body, encoding="utf-8")
    return html_path, latest_html_path


def copy_if_exists(source, destination):
    if source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination
    return None


def write_daily_log(
    run_id,
    args,
    download_results,
    download_log,
    decision_command,
    decision_result,
    technical_command,
    technical_result,
):
    daily_dir = resolve_repo_path(args.daily_dir)
    daily_dir.mkdir(parents=True, exist_ok=True)
    log_path = daily_dir / f"daily_investment_review_{run_id}.log"
    log_text = "\n".join(
        [
            f"Daily investment review run: {run_id}",
            f"Mode: {'local files' if args.skip_download else 'download'}",
            f"Funds: {', '.join(row['fund_id'] for row in download_results)}",
            "",
            "=== Data Refresh ===",
            download_log,
            "",
            "=== Forward Decision Command ===",
            " ".join(f'"{part}"' if " " in part else part for part in decision_command),
            "",
            "=== Forward Decision stdout ===",
            decision_result.stdout,
            "",
            "=== Forward Decision stderr ===",
            decision_result.stderr,
            f"Exit code: {decision_result.returncode}",
            "",
            "=== Technical Signal Command ===",
            " ".join(f'"{part}"' if " " in part else part for part in technical_command),
            "",
            "=== Technical Signal stdout ===",
            technical_result.stdout,
            "",
            "=== Technical Signal stderr ===",
            technical_result.stderr,
            f"Exit code: {technical_result.returncode}",
        ]
    )
    log_path.write_text(log_text, encoding="utf-8")
    return log_path


def ensure_report_commands_succeeded(decision_result, technical_result, log_path):
    if decision_result.returncode != 0:
        raise RuntimeError(f"Forward decision report failed. See log: {log_path}")
    if technical_result.returncode != 0:
        raise RuntimeError(f"Technical signal review failed. See log: {log_path}")


def write_daily_outputs(run_id, args, download_results, log_path):
    daily_dir = resolve_repo_path(args.daily_dir)
    daily_dir.mkdir(parents=True, exist_ok=True)

    downloads_path = daily_dir / f"daily_downloaded_files_{run_id}.csv"
    write_csv(
        download_results,
        downloads_path,
        [
            "fund_id",
            "fund_name",
            "fund_label",
            "current_nav",
            "current_date",
            "change",
            "change_pct",
            "total_return_method",
            "records",
            "output_path",
            "mode",
        ],
    )

    dashboard_path, dashboard = read_dashboard(args.report_dir)
    technical_path, technical = read_technical_review(args.report_dir)
    require_unique_fund_labels(dashboard, "Forward decision dashboard")
    require_unique_fund_labels(technical, "Technical signal review")
    combined = dashboard.merge(technical, on="Fund Label", how="left", suffixes=("", " Technical"))
    combined["Agreement"] = combined.apply(agreement_label, axis=1)

    summary_path = daily_dir / f"daily_decision_summary_{run_id}.csv"
    summary_columns = [
        "Fund Label",
        "Forward Method Version",
        "Decision Label",
        "Technical State",
        "Agreement",
        "Latest Date",
        "Probability >= Upside Target",
        "Probability <= Downside Risk",
        "Expected Forward Return",
        "Conditional Expected Edge",
        "Relative Upside Probability Lift",
        "Relative Downside Probability Lift",
        "Technical Absolute Probability >= Upside Target",
        "Technical Absolute Probability <= Downside Risk",
        "Technical Absolute Expected Forward Return",
        "Last Signal Action",
        "Last Signal Date",
        "Technical Confidence",
        "Confidence Level",
        "Decision Score",
        "Technical Chart File",
        "Simple Technical Chart File",
    ]
    combined[[col for col in summary_columns if col in combined.columns]].to_csv(summary_path, index=False)

    latest_summary_path = daily_dir / "daily_decision_summary_latest.csv"
    combined[[col for col in summary_columns if col in combined.columns]].to_csv(latest_summary_path, index=False)

    technical_daily_path = copy_if_exists(
        technical_path, daily_dir / f"technical_signal_review_{run_id}.csv"
    )
    technical_details_path = resolve_repo_path(args.report_dir) / "technical_signal_details.csv"
    technical_details_daily_path = copy_if_exists(
        technical_details_path, daily_dir / f"technical_signal_details_{run_id}.csv"
    )

    paths = {
        "log_path": log_path,
        "downloads_path": downloads_path,
        "summary_path": summary_path,
        "latest_summary_path": latest_summary_path,
        "dashboard_path": dashboard_path,
        "technical_path": technical_path,
    }
    html_path, latest_html_path = generate_daily_html(run_id, args, combined, download_results, paths)

    return {
        "log_path": log_path,
        "downloads_path": downloads_path,
        "summary_path": summary_path,
        "latest_summary_path": latest_summary_path,
        "dashboard_path": dashboard_path,
        "technical_path": technical_path,
        "technical_daily_path": technical_daily_path,
        "technical_details_daily_path": technical_details_daily_path,
        "html_path": html_path,
        "latest_html_path": latest_html_path,
        "dashboard_rows": len(dashboard),
    }


def main():
    args = parse_args()
    if args.years <= 0:
        raise ValueError("--years must be greater than 0.")
    fund_ids = args.fund_ids or TRACKED_FUNDS
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    download_results, download_log = download_or_find_files(fund_ids, args.years, args.skip_download)
    data_files = [Path(row["output_path"]) for row in download_results]
    decision_command, decision_result = run_forward_decision(data_files, args)
    technical_command, technical_result = run_technical_signal_review(data_files, args, run_id)
    log_path = write_daily_log(
        run_id,
        args,
        download_results,
        download_log,
        decision_command,
        decision_result,
        technical_command,
        technical_result,
    )
    ensure_report_commands_succeeded(decision_result, technical_result, log_path)
    outputs = write_daily_outputs(
        run_id,
        args,
        download_results,
        log_path,
    )

    print(f"Daily investment review complete: {run_id}")
    print(f"Analyzed funds: {outputs['dashboard_rows']}")
    print(f"Dashboard: {outputs['dashboard_path']}")
    print(f"Technical review: {outputs['technical_path']}")
    print(f"Daily summary: {outputs['summary_path']}")
    print(f"Latest summary: {outputs['latest_summary_path']}")
    print(f"Daily HTML: {outputs['html_path']}")
    print(f"Run log: {outputs['log_path']}")


if __name__ == "__main__":
    main()
