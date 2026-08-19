"""Generate the standalone, dependency-free Backtest Intelligence website."""

from __future__ import annotations

import csv
import html
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

try:
    from scripts.generate_buyhold_dashboard_charts import buyhold_period_metrics, generate_buyhold_chart, resolve_data_file
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from generate_buyhold_dashboard_charts import buyhold_period_metrics, generate_buyhold_chart, resolve_data_file


ROOT = Path(__file__).resolve().parents[1]
TUNINGS = ROOT / "outputs" / "tunings"
PROJECT = ROOT / "backtest-dashboard"
SOURCE = PROJECT / "source"
SITE = PROJECT / "site"

FUND_NAMES = {
    "MAKGCF_GreaterChina": ("MAKGCF", "Greater China"),
    "MAPAC_AsiaPacificexJapan": ("MAPAC", "Asia Pacific ex Japan"),
    "HWFL_HWFlexi": ("HWFL", "HW Flexi"),
    "APCR_AsiaPacificREIT": ("APCR", "Asia Pacific REIT"),
    "MGLVH_GlobalLowVolatilityEquityARMHClass": ("MGLVH", "Global Low Volatility"),
    "MIIEH_IndiaEquityRMH": ("MIIEH", "India Equity"),
    "MSCEH_ShariahChinaEquityARMHClass": ("MSCEH", "Shariah China Equity"),
    "MPGFC_PRSGrowthC": ("MPGFC", "PRS Growth C"),
    "MAPF_Progress": ("MAPF", "Progress"),
    "MAUS_RMH_USEquityRMH": ("MAUS", "US Equity"),
    "MGPRH_GlobalPerspective": ("MGPRH", "Global Perspective"),
    "SPGA_ShariahPRSGoldenAsiaClassC": ("SPGA", "Shariah PRS Golden Asia"),
    "MSGLR_RM_ShariahGlobalREITMYR": ("MSGLR", "Shariah Global REIT"),
}

# Earlier history exports embedded the source-file suffix in two fund labels.
# Preserve their useful run evidence in the configured fund universe.
HISTORY_FUND_ALIASES = {
    "MAUSRMHUSEquityRMHnav5Y": "MAUS_RMH_USEquityRMH",
    "MSGLRRMShariahGlobalREITMYRnav5Y": "MSGLR_RM_ShariahGlobalREITMYR",
    "MSGLRRMShariahGlobalREITMYRnav3Y": "MSGLR_RM_ShariahGlobalREITMYR",
}

CHARTS = (
    ("latestTechnical", "latest_chart_file", "latest-technical", "Latest technical", "Full local history replay with signals, RSI and portfolio value."),
    ("sourceTechnical", "technical_chart_file", "source-technical", "Source technical", "The original evaluation window used for the selected parameters."),
    ("sourceSimple", "simple_chart_file", "source-simple", "Simple comparison", "A concise strategy-versus-buy-and-hold result view."),
)

SOURCE_YEARS_PATTERN = re.compile(r"(?:_nav_|nav)(\d+(?:\.\d+)?)Y", re.IGNORECASE)
BUYHOLD_RUN_YEARS = (5.0, 4.0, 3.0, 2.0, 1.0)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str] | None, key: str, digits: int = 2) -> float | None:
    value = (row or {}).get(key, "")
    if value is None or not str(value).strip():
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def integer(row: dict[str, str] | None, key: str) -> int | None:
    value = number(row, key, 0)
    return None if value is None else int(value)


def normalize_signal(value: str | None) -> str:
    text = (value or "UNKNOWN").upper().replace(" ", "")
    if text.startswith("BUY/HOLD"):
        return "BUY / HOLD"
    if text.startswith("SELL/CASH"):
        return "SELL / CASH"
    return "UNKNOWN"


def latest_successful_summary(paths: Iterable[Path]) -> tuple[Path, list[dict[str, str]]]:
    for path in sorted(paths, key=lambda item: item.name, reverse=True):
        rows = [row for row in read_csv(path) if row.get("status", "").lower() == "completed"]
        if rows:
            return path, rows
    raise FileNotFoundError("No successful final_backtest_summary CSV is available")


def best_history_rows(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    best: dict[str, dict[str, str]] = {}
    for row in rows:
        fund = row.get("fund_label", "")
        excess = number(row, "excess_annualized_return_pct", 8)
        if fund not in FUND_NAMES or excess is None or excess == 0:
            continue
        incumbent = best.get(fund)
        incumbent_excess = number(incumbent, "excess_annualized_return_pct", 8)
        candidate_key = (excess, row.get("run_started_at", ""), row.get("run_id", ""))
        incumbent_key = None if incumbent_excess is None else (
            incumbent_excess,
            incumbent.get("run_started_at", ""),
            incumbent.get("run_id", ""),
        )
        if incumbent_key is None or candidate_key > incumbent_key:
            best[fund] = row
    return best


def normalized_history_label(label: str) -> str:
    return HISTORY_FUND_ALIASES.get(label, label)


def source_years(row: dict[str, str]) -> float | None:
    match = SOURCE_YEARS_PATTERN.search(row.get("data_file", ""))
    return round(float(match.group(1)), 2) if match else None


def duration_label(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{int(value) if value.is_integer() else value:g}Y"


def history_run_label(row: dict[str, str]) -> str:
    lookback = duration_label(number(row, "lookback_years", 2))
    offset = integer(row, "offset_months")
    profile = row.get("strategy_profile") or "strategy"
    return f"{lookback}/{offset if offset is not None else '—'}M {profile}"


def excess_history_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, object]]:
    eligible: list[dict[str, object]] = []
    for row in rows:
        label = normalized_history_label(row.get("fund_label", ""))
        excess = number(row, "excess_annualized_return_pct", 8)
        chart_path = Path(row["chart_file"]) if row.get("chart_file") else None
        source = source_years(row)
        lookback = number(row, "lookback_years", 2)
        if (
            label not in FUND_NAMES
            or row.get("run_status", "").lower() != "completed"
            or excess is None
            or excess == 0
            or chart_path is None
            or not chart_path.is_file()
        ):
            continue
        run_years = round(source - lookback, 2) if source is not None and lookback is not None else None
        if run_years is not None and run_years <= 0:
            continue
        code, name = FUND_NAMES[label]
        eligible.append({
            "id": row.get("run_id", ""), "fund": label, "code": code, "name": name,
            "sourceYears": source, "runYears": run_years, "end": row.get("backtest_end") or row.get("data_end") or None,
            "started": row.get("run_started_at", ""), "chartPath": chart_path,
            "excessAnnualized": excess, "strategyAnnualized": number(row, "adaptive_annualized_return_pct"),
            "buyHoldAnnualized": number(row, "buy_hold_annualized_return_pct"), "label": history_run_label(row),
        })
    return eligible


def best_excess_runs(rows: Iterable[dict[str, object]], source_group: float | str = "mixed", run_years: float | None = None) -> list[dict[str, object]]:
    winners: dict[str, dict[str, object]] = {}
    for row in rows:
        if source_group != "mixed" and (
            (source_group == "other" and row["sourceYears"] is not None)
            or (source_group != "other" and row["sourceYears"] != source_group)
        ):
            continue
        if run_years is not None and row["runYears"] != run_years:
            continue
        incumbent = winners.get(row["fund"])
        key = (row["excessAnnualized"], row["started"], row["id"])
        if incumbent is None or key > (incumbent["excessAnnualized"], incumbent["started"], incumbent["id"]):
            winners[row["fund"]] = row
    return sorted(winners.values(), key=lambda row: (-row["excessAnnualized"], row["code"]))


def buyhold_history_rows(rows: Iterable[dict[str, str]], data_root: Path = ROOT / "data") -> list[dict[str, object]]:
    eligible: list[dict[str, object]] = []
    for row in rows:
        label = normalized_history_label(row.get("fund_label", ""))
        annualized = number(row, "buy_hold_annualized_return_pct", 8)
        source = source_years(row)
        data_file = resolve_data_file(row.get("data_file", ""), data_root)
        start = row.get("backtest_start") or row.get("data_start") or ""
        end = row.get("backtest_end") or row.get("data_end") or ""
        if (
            label not in FUND_NAMES
            or row.get("run_status", "").lower() != "completed"
            or source is None
            or data_file is None
            or not start
            or not end
        ):
            continue
        code, name = FUND_NAMES[label]
        lookback = number(row, "lookback_years", 2)
        eligible.append({
            "id": row.get("run_id", ""), "fund": label, "code": code, "name": name,
            "sourceYears": source, "scoredYears": round(source - lookback, 2) if lookback is not None else None,
            "start": start, "end": end, "started": row.get("run_started_at", ""), "dataFile": data_file,
            "buyHoldAnnualized": annualized, "strategyAnnualized": number(row, "adaptive_annualized_return_pct"),
            "label": history_run_label(row),
        })
    return eligible


def latest_buyhold_run_years(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build passive windows whose calculated and scored horizons are identical."""
    generated: list[dict[str, object]] = []
    for fund in sorted({row["fund"] for row in rows}):
        fund_rows = [row for row in rows if row["fund"] == fund]
        unique_sources: dict[Path, dict[str, object]] = {}
        for row in fund_rows:
            source = row["dataFile"].resolve()
            incumbent = unique_sources.get(source)
            if incumbent is None or (row["started"], row["id"]) > (incumbent["started"], incumbent["id"]):
                unique_sources[source] = row
        for years in BUYHOLD_RUN_YEARS:
            candidates: list[tuple[dict[str, object], dict[str, object]]] = []
            for source_row in unique_sources.values():
                if source_row["sourceYears"] < years:
                    continue
                metrics = buyhold_period_metrics(source_row["dataFile"], years)
                if metrics is not None:
                    candidates.append((source_row, metrics))
            if not candidates:
                continue
            source_row, metrics = max(
                candidates,
                key=lambda candidate: (
                    candidate[0]["sourceYears"] == years,
                    candidate[1]["end"],
                    candidate[0]["started"],
                    candidate[0]["id"],
                ),
            )
            generated.append({
                **source_row,
                "id": f"latest-{source_row['code'].lower()}-{duration_label(years).lower()}",
                "sourceYears": years,
                "scoredYears": years,
                "start": metrics["start"],
                "end": metrics["end"],
                "buyHoldAnnualized": metrics["annualized"],
                "strategyAnnualized": None,
                "label": f"Latest {duration_label(years)} passive window",
            })
    return generated


def best_buyhold_runs(rows: Iterable[dict[str, object]], run_group: float | str = "mixed") -> list[dict[str, object]]:
    winners: dict[str, dict[str, object]] = {}
    for row in rows:
        if run_group != "mixed" and row["scoredYears"] != run_group:
            continue
        incumbent = winners.get(row["fund"])
        key = (row["buyHoldAnnualized"], row["started"], row["id"])
        if incumbent is None or key > (incumbent["buyHoldAnnualized"], incumbent["started"], incumbent["id"]):
            winners[row["fund"]] = row
    return sorted(winners.values(), key=lambda row: (-row["buyHoldAnnualized"], row["code"]))


def buyhold_ranking_views(rows: list[dict[str, object]]) -> tuple[list[float | str], dict[str, list[dict[str, object]]]]:
    run_groups: list[float | str] = ["mixed", *[years for years in BUYHOLD_RUN_YEARS if any(row["scoredYears"] == years for row in rows)]]
    return run_groups, {buyhold_run_key(group): best_buyhold_runs(rows, group) for group in run_groups}


def annualized_history_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, object]]:
    eligible: list[dict[str, object]] = []
    for row in rows:
        label = normalized_history_label(row.get("fund_label", ""))
        strategy = number(row, "adaptive_annualized_return_pct", 8)
        buyhold = number(row, "buy_hold_annualized_return_pct", 8)
        source = source_years(row)
        chart_path = Path(row["chart_file"]) if row.get("chart_file") else None
        if (
            label not in FUND_NAMES
            or row.get("run_status", "").lower() != "completed"
            or (strategy is None and buyhold is None)
            or source is None
            or chart_path is None
            or not chart_path.is_file()
        ):
            continue
        score = max(value for value in (strategy, buyhold) if value is not None)
        winner = "Strategy annualized" if strategy is not None and (buyhold is None or strategy >= buyhold) else "Buy & hold annualized"
        code, name = FUND_NAMES[label]
        lookback = number(row, "lookback_years", 2)
        eligible.append({
            "id": row.get("run_id", ""), "fund": label, "code": code, "name": name,
            "sourceYears": source, "scoredYears": round(source - lookback, 2) if lookback is not None else None,
            "end": row.get("backtest_end") or row.get("data_end") or None, "started": row.get("run_started_at", ""),
            "chartPath": chart_path, "strategyAnnualized": strategy, "buyHoldAnnualized": buyhold,
            "score": score, "winner": winner, "label": history_run_label(row),
        })
    return eligible


def best_annualized_runs(rows: Iterable[dict[str, object]], source_group: float | str = "mixed") -> list[dict[str, object]]:
    winners: dict[str, dict[str, object]] = {}
    for row in rows:
        if source_group != "mixed" and row["sourceYears"] != source_group:
            continue
        incumbent = winners.get(row["fund"])
        key = (row["score"], row["started"], row["id"])
        if incumbent is None or key > (incumbent["score"], incumbent["started"], incumbent["id"]):
            winners[row["fund"]] = row
    return sorted(winners.values(), key=lambda row: (-row["score"], row["code"]))


def annualized_ranking_views(rows: list[dict[str, object]]) -> tuple[list[float | str], dict[str, list[dict[str, object]]]]:
    source_groups: list[float | str] = ["mixed", *sorted({row["sourceYears"] for row in rows}, reverse=True)]
    return source_groups, {excess_source_key(group): best_annualized_runs(rows, group) for group in source_groups}


def metric_block(row: dict[str, str] | None, prefix: str = "") -> dict[str, float | None]:
    return {
        "totalReturn": number(row, f"{prefix}adaptive_return_pct"),
        "buyHoldReturn": number(row, f"{prefix}buy_hold_return_pct"),
        "excessReturn": number(row, f"{prefix}excess_return_pct"),
        "annualized": number(row, f"{prefix}adaptive_annualized_return_pct"),
        "buyHoldAnnualized": number(row, f"{prefix}buy_hold_annualized_return_pct"),
        "excessAnnualized": number(row, f"{prefix}excess_annualized_return_pct"),
        "sharpe": number(row, f"{prefix}sharpe"),
        "maxDrawdown": number(row, f"{prefix}max_dd_pct"),
    }


def build_snapshot(summary_path: Path, rows: list[dict[str, str]], history: list[dict[str, str]]) -> dict[str, object]:
    historical = best_history_rows(history)
    funds: list[dict[str, object]] = []
    for row in rows:
        label = row.get("fund_label", "")
        if label not in FUND_NAMES:
            continue
        code, name = FUND_NAMES[label]
        history_row = historical.get(label)
        score_years = source_years(row)
        lookback_years = number(history_row, "lookback_years")
        fund = {
            "id": label,
            "slug": code.lower(),
            "code": code,
            "name": name,
            "scoreYears": score_years,
            "runYears": round(score_years - lookback_years, 2) if score_years is not None and lookback_years is not None else None,
            "signal": normalize_signal(row.get("ga_signal")),
            "lastTradeDate": row.get("last_trade_date") or None,
            "latestStart": row.get("latest_data_start") or None,
            "latestEnd": row.get("latest_data_end") or None,
            "sourceStart": row.get("data_start") or None,
            "sourceEnd": row.get("data_end") or None,
            "latest": metric_block(row, "latest_"),
            "source": metric_block(row),
            "historicalBest": {
                **metric_block(history_row),
                "lookbackYears": number(history_row, "lookback_years", 1),
                "offsetMonths": integer(history_row, "offset_months"),
                "start": (history_row or {}).get("backtest_start") or None,
                "end": (history_row or {}).get("backtest_end") or None,
                "runId": (history_row or {}).get("run_id") or None,
            },
            "parameters": {
                "shortEma": integer(row, "short_ema"), "longEma": integer(row, "long_ema"),
                "stopLoss": number(row, "stop_loss"), "cooldown": integer(row, "cooldown"),
                "drawdownExit": number(row, "drawdown_exit_pct"), "reentryRebound": number(row, "reentry_rebound_pct"),
                "rsiOversold": integer(row, "rsi_oversold"), "rsiOverbought": integer(row, "rsi_overbought"),
                "exposure": number(row, "exposure_multiplier"),
            },
            "statistics": {
                "trades": integer(row, "trade_count"), "winRate": number(row, "win_rate_pct"),
                "timeInvested": number(row, "time_invested_pct"), "uptrendCash": number(row, "uptrend_cash_pct"),
                "missedUpside": number(row, "missed_upside_after_exit_pct"), "stopLossCount": integer(row, "stop_loss_count"),
            },
            "chartSources": {key: row.get(column) or None for key, column, *_ in CHARTS},
            "charts": {},
        }
        funds.append(fund)

    funds.sort(key=lambda item: (item["latest"]["totalReturn"] is None, -(item["latest"]["totalReturn"] or 0), item["code"]))
    for index, fund in enumerate(funds, start=1):
        fund["rank"] = index
    latest_end = max((fund["latestEnd"] or "" for fund in funds), default="") or None
    completed = max((row.get("run_completed_at", "") for row in rows), default="") or None
    return {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sourceSummary": summary_path.name,
        "runCompletedAt": completed,
        "latestObservation": latest_end,
        "funds": funds,
    }


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def pct(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "—"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:.2f}%"


def num(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def value_attr(value: float | None, drawdown: bool = False) -> str:
    if value is None:
        return ""
    return str(-abs(value) if drawdown else value)


def date_text(value: str | None) -> str:
    if not value:
        return "Unavailable"
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return value


def tone(value: float | None) -> str:
    return "muted" if value is None else "positive" if value >= 0 else "negative"


def signal_class(signal: str) -> str:
    return "buy" if signal.startswith("BUY") else "cash" if signal.startswith("SELL") else "unknown"


def page_head(title: str, prefix: str, description: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:image" content="{prefix}assets/og.png">
<link rel="icon" href="{prefix}assets/og.png"><link rel="stylesheet" href="{prefix}assets/styles.css">
<script defer src="{prefix}assets/dashboard.js"></script></head>"""


def theme_button() -> str:
    return '<button class="theme-toggle" type="button" data-theme-toggle aria-label="Switch to dark mode" aria-pressed="false"><span aria-hidden="true">☾</span><b>Dark</b></button>'


def brand(href: str) -> str:
    return f'<a class="brand" href="{href}"><span class="brand-mark">BI</span><span><b>Backtest Intelligence</b><small>Strategy evidence hub</small></span></a>'


def result_attrs(fund: dict[str, object]) -> str:
    metrics = fund["latest"]
    return (
        f'data-fund-result data-code="{esc(fund["code"])}" data-search="{esc((fund["code"] + " " + fund["name"]).lower())}" '
        f'data-latest="{value_attr(metrics["totalReturn"])}" data-annualized="{value_attr(metrics["annualized"])}" '
        f'data-buy-hold="{value_attr(metrics["buyHoldAnnualized"])}" data-excess="{value_attr(metrics["excessAnnualized"])}" '
        f'data-drawdown="{value_attr(metrics["maxDrawdown"], True)}" data-sharpe="{value_attr(metrics["sharpe"])}" data-trades="{value_attr(fund["statistics"]["trades"])}" '
        f'data-score-years="{value_attr(fund["scoreYears"])}" data-run-years="{value_attr(fund["runYears"])}"'
    )


def render_table_row(fund: dict[str, object]) -> str:
    m, stats = fund["latest"], fund["statistics"]
    href = f'funds/{fund["slug"]}/index.html'
    wins = (m["annualized"] if m["annualized"] is not None else float("-inf")) >= (m["buyHoldAnnualized"] if m["buyHoldAnnualized"] is not None else float("-inf"))
    signal = fund["signal"]
    score_run = f"{duration_label(fund['scoreYears'])} / {duration_label(fund['runYears'])}"
    return f"""<tr {result_attrs(fund)}><td data-rank>#{fund['rank']}</td><td><a class="fund-identity" href="{href}"><strong>{esc(fund['code'])}</strong><span>{esc(fund['name'])}</span><small class="signal {signal_class(signal)}"><i></i>{esc(signal)}</small></a></td><td class="score-run-years">{score_run}</td>
<td class="{tone(m['totalReturn'])}"><b>{pct(m['totalReturn'])}</b></td>
<td class="column-annualized {tone(m['annualized'])}">{pct(m['annualized'])} {'<em>W</em>' if wins else ''}</td>
<td class="column-buyHold {tone(m['buyHoldAnnualized'])}">{pct(m['buyHoldAnnualized'])} {'<em>W</em>' if not wins else ''}</td>
<td class="column-excess {tone(m['excessAnnualized'])}">{pct(m['excessAnnualized'])}</td>
<td class="column-drawdown negative">{pct(m['maxDrawdown'], False)}</td>
<td class="column-sharpe column-hidden">{num(m['sharpe'])}</td><td class="column-trades column-hidden">{stats['trades'] if stats['trades'] is not None else '—'}</td>
<td><a class="row-arrow" href="{href}" aria-label="Open {esc(fund['name'])} backtest detail">→</a></td></tr>"""


def render_mobile_card(fund: dict[str, object]) -> str:
    m, signal = fund["latest"], fund["signal"]
    return f"""<a href="funds/{fund['slug']}/index.html" class="mobile-result" {result_attrs(fund)}><span class="mobile-rank" data-rank>#{fund['rank']}</span><span class="mobile-title"><strong>{esc(fund['code'])}</strong><small>{esc(fund['name'])}</small></span><span class="signal {signal_class(signal)}"><i></i>{esc(signal)}</span><dl><div><dt>Latest</dt><dd>{pct(m['totalReturn'])}</dd></div><div><dt>Annualized</dt><dd>{pct(m['annualized'])}</dd></div><div><dt>Excess</dt><dd>{pct(m['excessAnnualized'])}</dd></div></dl><b class="mobile-arrow">→</b></a>"""


def render_master(snapshot: dict[str, object]) -> str:
    funds = snapshot["funds"]
    leader = max(funds, key=lambda f: f["latest"]["totalReturn"] if f["latest"]["totalReturn"] is not None else float("-inf"))
    excess_leader = max(funds, key=lambda f: f["historicalBest"]["excessAnnualized"] if f["historicalBest"]["excessAnnualized"] is not None else float("-inf"))
    buys = sum(fund["signal"].startswith("BUY") for fund in funds)
    rows = "".join(render_table_row(fund) for fund in funds)
    cards = "".join(render_mobile_card(fund) for fund in funds)
    columns = (("annualized", "Strategy ann.", True), ("buyHold", "B&H ann.", True), ("excess", "Excess", True), ("drawdown", "Drawdown", True), ("sharpe", "Sharpe", False), ("trades", "Trades", False))
    checks = "".join(f'<label><input type="checkbox" data-column="{key}" {"checked" if checked else ""}>{label}</label>' for key, label, checked in columns)
    return page_head("Backtest Intelligence", "", "Independent strategy backtest rankings and evidence.") + f"""<body><div class="site-shell" data-master-dashboard>
<header class="topbar">{brand('index.html')}<div class="top-actions"><span class="fresh"><i></i>Local snapshot · {date_text(snapshot['latestObservation'])}</span>{theme_button()}</div></header>
<main class="master-shell"><section class="hero"><span class="eyebrow">BACKTEST INTELLIGENCE HUB</span><h1>Every strategy. One evidence trail.</h1><p>Compare full-history replays, rank adaptive strategies against buy and hold, and open every fund’s technical evidence from one independent workspace.</p><div class="hero-pills"><span>{len(funds)} funds</span><span>Latest local data {esc(snapshot['latestObservation'])}</span><span>Run completed {esc((snapshot['runCompletedAt'] or 'Unavailable')[:16])}</span></div></section>
<section class="kpi-grid" aria-label="Backtest summary"><article><span>Latest leader</span><strong>{leader['code']} · {pct(leader['latest']['totalReturn'])}</strong></article><article><span>Best historical excess</span><strong>{excess_leader['code']} · {pct(excess_leader['historicalBest']['excessAnnualized'])}</strong></article><article><span>Buy signals</span><strong>{buys} of {len(funds)}</strong></article><article><span>Newest observation</span><strong>{esc(snapshot['latestObservation'])}</strong></article></section>
<section class="lens-grid" aria-label="Backtest views"><button type="button" data-preset="latest"><span>1</span><strong>Latest results</strong><p>Rank the most recent full-history replay.</p></button><a href="excess-ranking/index.html"><span>2</span><strong>Historical excess</strong><p>Find the strongest run versus buy and hold.</p></a><a href="annualized-ranking/index.html"><span>3</span><strong>Annualized return</strong><p>Rank the stronger strategy or passive annualized result.</p></a><a href="buyhold-ranking/index.html"><span>4</span><strong>Buy &amp; hold horizons</strong><p>Compare passive returns across scored 5Y, 4Y and 3Y horizons.</p></a></section>
<section class="ranking-panel" id="ranking" aria-labelledby="ranking-title"><div class="ranking-toolbar"><div><span class="eyebrow dark">LATEST REPLAY</span><h2 id="ranking-title">Backtest rankings</h2></div><label class="search"><span class="sr-only">Search fund name or code</span><input type="search" data-search placeholder="Search name or code"></label></div>
<div class="sortbar"><span class="sort-label">SORT FUNDS</span><div class="sort-pills"><button class="selected" type="button" data-sort="latest">Latest strategy</button><button type="button" data-sort="annualized">Strategy ann.</button><button type="button" data-sort="buyHold">B&amp;H ann.</button><button type="button" data-sort="excess">Excess</button><button type="button" data-sort="drawdown">Drawdown</button></div><div class="sort-actions"><button class="direction" type="button" data-direction>Highest first ↓</button><details class="columns"><summary>Columns (<span data-column-count>7</span>)</summary><div>{checks}</div></details></div></div>
<p class="table-note"><span><span data-result-count>{len(funds)}</span> funds · {buys} buy signals · <b>W</b> marks the stronger annualized result</span><span>All data through <strong>{esc(snapshot['latestObservation'])}</strong></span></p><noscript><p class="noscript-note">Interactive search, sorting, columns and theme require JavaScript; all results and detail links remain available.</p></noscript>
<div class="table-wrap"><table><thead><tr><th>#</th><th>Fund / signal</th><th>Source Year / Run Years</th><th><button type="button" data-sort="latest">Latest strategy</button></th><th class="column-annualized"><button type="button" data-sort="annualized">Strategy ann.</button></th><th class="column-buyHold"><button type="button" data-sort="buyHold">B&amp;H ann.</button></th><th class="column-excess"><button type="button" data-sort="excess">Excess</button></th><th class="column-drawdown"><button type="button" data-sort="drawdown">Drawdown</button></th><th class="column-sharpe column-hidden"><button type="button" data-sort="sharpe">Sharpe</button></th><th class="column-trades column-hidden"><button type="button" data-sort="trades">Trades</button></th><th aria-label="Open fund detail"></th></tr></thead><tbody>{rows}</tbody></table></div><div class="mobile-results">{cards}</div><p class="empty-results" data-empty-results hidden>No funds match this search.</p></section></main>
<footer>Generated from {esc(snapshot['sourceSummary'])} · Standalone backtest workspace</footer></div></body></html>"""


def excess_source_key(value: float | str) -> str:
    return value if isinstance(value, str) else f"source-{value:g}"


def buyhold_run_key(value: float | str) -> str:
    return value if isinstance(value, str) else f"run-{value:g}"


def excess_run_key(value: float | None) -> str:
    return "all" if value is None else f"run-{value:g}"


def render_excess_card(row: dict[str, object], rank: int) -> str:
    return f"""<article class="excess-card"><div class="excess-card-head"><div><span class="rank-chip">#{rank}</span><strong>{esc(row['code'])}</strong><small>{esc(row['name'])}</small></div><div><span>EXCESS ANNUALIZED</span><b class="{tone(row['excessAnnualized'])}">{pct(row['excessAnnualized'])}</b></div></div>
<div class="excess-facts"><span>Source years <b>{duration_label(row['sourceYears'])}</b></span><span>Run years <b>{duration_label(row['runYears'])}</b></span><span>Strategy ann. <b>{pct(row['strategyAnnualized'])}</b></span><span>Buy &amp; hold ann. <b>{pct(row['buyHoldAnnualized'])}</b></span><span>Through <b>{esc(row['end'] or 'Unavailable')}</b></span><span>Winning run <b>{esc(row['label'])}</b></span></div>
<a class="excess-chart" href="{esc(row['chart'])}" target="_blank" rel="noreferrer"><img src="{esc(row['chart'])}" alt="{esc(row['name'])} historical excess backtest chart"><span>Open chart ↗</span></a></article>"""


def excess_ranking_views(rows: list[dict[str, object]]) -> tuple[list[float | str], list[float], dict[tuple[str, str], list[dict[str, object]]]]:
    source_values = sorted({row["sourceYears"] for row in rows if row["sourceYears"] is not None}, reverse=True)
    run_values = sorted({row["runYears"] for row in rows if row["runYears"] is not None})
    source_groups: list[float | str] = ["mixed", *source_values]
    if any(row["sourceYears"] is None for row in rows):
        source_groups.append("other")
    selections: dict[tuple[str, str], list[dict[str, object]]] = {}
    for source_group in source_groups:
        for run_years in [None, *run_values]:
            winners = best_excess_runs(rows, source_group, run_years)
            selections[(excess_source_key(source_group), excess_run_key(run_years))] = winners
    return source_groups, run_values, selections


def render_excess_ranking(rows: list[dict[str, object]], history_path: Path) -> str:
    source_groups, run_values, selections = excess_ranking_views(rows)
    views: list[str] = []
    for (source_key, run_key), winners in selections.items():
            cards = "".join(render_excess_card(row, index) for index, row in enumerate(winners, start=1))
            hidden = "" if source_key == "mixed" and run_key == "all" else " hidden"
            content = cards or '<p class="empty-results">No eligible chart-backed runs match this grouping.</p>'
            views.append(f'<section class="excess-grid" data-excess-view data-source="{source_key}" data-run="{run_key}"{hidden}>{content}</section>')
    source_tabs = "".join(
        f'<button role="tab" type="button" data-excess-source="{excess_source_key(group)}" aria-selected="{str(group == "mixed").lower()}">{"Mixed" if group == "mixed" else "Other" if group == "other" else duration_label(group)}</button>'
        for group in source_groups
    )
    run_tabs = "".join(
        f'<button role="tab" type="button" data-excess-run="{excess_run_key(value)}" aria-selected="{str(value is None).lower()}">{"All run years" if value is None else duration_label(value)}</button>'
        for value in [None, *run_values]
    )
    written = datetime.fromtimestamp(history_path.stat().st_mtime).astimezone().strftime("%d %b %Y %H:%M")
    page = page_head("Excess Ranking · Backtest Intelligence", "../", "Historical excess annualized backtest rankings with chart evidence.") + f"""<body><div class="site-shell excess-page" data-excess-dashboard>
<header class="topbar">{brand('../index.html')}<div class="top-actions"><span class="fresh"><i></i>History refreshed {written}</span>{theme_button()}</div></header>
<main class="excess-shell"><a class="back-link" href="../index.html">← Master dashboard</a><section class="excess-heading"><span class="eyebrow dark">HISTORICAL RUN EVIDENCE</span><h1>Excess Ranking</h1><p>Best strategy excess over buy and hold, grouped by source-data horizon and scored run duration.</p><small>Source <b>{esc(history_path.name)}</b> · {len(rows)} eligible completed runs with chart evidence.</small></section>
<section class="excess-controls"><div><p>Choose the source-data CSV horizon.</p><div class="excess-tabs" role="tablist" aria-label="Source data horizon" data-tab-group>{source_tabs}</div></div><div><p>Run years = source years − lookback years.</p><div class="excess-tabs" role="tablist" aria-label="Run duration" data-tab-group>{run_tabs}</div></div></section>
<p class="excess-note">Each view ranks the strongest eligible historical run per fund. Runs without a usable technical chart are excluded.</p>{''.join(views)}</main><footer>Historical evidence from {esc(history_path.name)} · Past simulated results do not predict future performance.</footer></div></body></html>"""
    return page


def render_buyhold_card(row: dict[str, object], rank: int) -> str:
    return f"""<article class="buyhold-card"><div class="excess-card-head"><div><span class="rank-chip">#{rank}</span><strong>{esc(row['code'])}</strong><small>{esc(row['name'])}</small></div><div><span>BUY &amp; HOLD ANNUALIZED</span><b class="{tone(row['buyHoldAnnualized'])}">{pct(row['buyHoldAnnualized'])}</b></div></div>
<div class="excess-facts"><span>Source years <b>{duration_label(row['sourceYears'])}</b></span><span>Scored years <b>{duration_label(row['scoredYears'])}</b></span><span>Strategy ann. <b>{pct(row['strategyAnnualized'])}</b></span><span>Through <b>{esc(row['end'])}</b></span><span>Winning run <b>{esc(row['label'])}</b></span></div>
<a class="buyhold-chart" href="{esc(row['chart'])}" target="_blank" rel="noreferrer"><img src="{esc(row['chart'])}" alt="{esc(row['name'])} buy and hold portfolio chart"><span>{esc(row['start'])}</span><b>{esc(row['end'])}</b></a></article>"""


def render_buyhold_table(rows: list[dict[str, object]]) -> str:
    body = "".join(
        f'<tr><td>{index}</td><td><strong>{esc(row["code"])}</strong><small>{esc(row["name"])}</small></td>'
        f'<td class="{tone(row["buyHoldAnnualized"])}">{pct(row["buyHoldAnnualized"])}</td>'
        f'<td>{duration_label(row["sourceYears"])}</td><td>{duration_label(row["scoredYears"])}</td><td>{esc(row["end"])}</td></tr>'
        for index, row in enumerate(rows, start=1)
    )
    if not body:
        return '<p class="empty-results">No eligible local buy-and-hold results match this horizon.</p>'
    return f'<div class="buyhold-table-wrap"><table class="buyhold-table"><thead><tr><th>#</th><th><button type="button" data-buyhold-sort="fund">Fund</button></th><th><button type="button" data-buyhold-sort="annualized">Buy &amp; hold ann.</button></th><th><button type="button" data-buyhold-sort="source">Source years</button></th><th><button type="button" data-buyhold-sort="scored">Scored years</button></th><th><button type="button" data-buyhold-sort="through">Through</button></th></tr></thead><tbody>{body}</tbody></table></div>'


def render_buyhold_ranking(rows: list[dict[str, object]], history_path: Path) -> str:
    run_groups, views = buyhold_ranking_views(rows)
    run_tabs = "".join(
        f'<button role="tab" type="button" data-buyhold-run="{buyhold_run_key(group)}" aria-selected="{str(group == "mixed").lower()}">{"Mixed highest" if group == "mixed" else duration_label(group)}</button>'
        for group in run_groups
    )
    cards = []
    for source_key, winners in views.items():
        hidden = "" if source_key == "mixed" else " hidden"
        content = "".join(render_buyhold_card(row, index) for index, row in enumerate(winners, start=1))
        content = content or '<p class="empty-results">No eligible local buy-and-hold charts match this horizon.</p>'
        title = "Mixed highest" if source_key == "mixed" else f"{duration_label(winners[0]['scoredYears'])} scored" if winners else "No results"
        cards.append(f'<section class="buyhold-view" data-buyhold-view data-run="{source_key}"{hidden}><h2 class="buyhold-view-title">{title}</h2>{render_buyhold_table(winners)}<div class="buyhold-grid">{content}</div></section>')
    written = datetime.fromtimestamp(history_path.stat().st_mtime).astimezone().strftime("%d %b %Y %H:%M")
    return page_head("Buy & Hold Ranking · Backtest Intelligence", "../", "Historical buy and hold annualized rankings with compact portfolio charts.") + f"""<body><div class="site-shell buyhold-page" data-buyhold-dashboard>
<header class="topbar">{brand('../index.html')}<div class="top-actions"><span class="fresh"><i></i>History refreshed {written}</span>{theme_button()}</div></header>
<main class="excess-shell"><a class="back-link" href="../index.html">← Master dashboard</a><section class="excess-heading"><span class="eyebrow dark">HISTORICAL PASSIVE RETURNS</span><h1>Buy &amp; Hold Ranking</h1><p>Highest historical buy-and-hold annualized outcome, grouped by scored or generated run duration.</p><small>Source <b>{esc(history_path.name)}</b> · {len(rows)} eligible completed and generated passive windows with local chart data.</small></section>
<section class="excess-controls buyhold-controls"><div><p>Choose the buy-and-hold scored duration.</p><div class="excess-tabs" role="tablist" aria-label="Buy and hold scored duration" data-tab-group>{run_tabs}</div></div></section>
<p class="excess-note">Each chart calculates the same window length as its scored duration and uses a $10,000 normalized investment. A horizon is omitted when local source data does not contain enough history.</p>{''.join(cards)}</main><footer>Historical passive-return evidence from {esc(history_path.name)} · Past results do not predict future performance.</footer></div></body></html>"""


def render_annualized_card(row: dict[str, object], rank: int) -> str:
    return f"""<article class="excess-card annualized-card"><div class="excess-card-head"><div><span class="rank-chip">#{rank}</span><strong>{esc(row['code'])}</strong><small>{esc(row['name'])}</small></div><div><span>{esc(row['winner']).upper()}</span><b class="{tone(row['score'])}">{pct(row['score'])}</b></div></div>
<div class="excess-facts"><span>Source years <b>{duration_label(row['sourceYears'])}</b></span><span>Scored years <b>{duration_label(row['scoredYears'])}</b></span><span>Strategy ann. <b>{pct(row['strategyAnnualized'])}</b></span><span>Buy &amp; hold ann. <b>{pct(row['buyHoldAnnualized'])}</b></span><span>Through <b>{esc(row['end'] or 'Unavailable')}</b></span><span>Winning run <b>{esc(row['label'])}</b></span></div>
<a class="excess-chart" href="{esc(row['chart'])}" target="_blank" rel="noreferrer"><img src="{esc(row['chart'])}" alt="{esc(row['name'])} top annualized historical backtest chart"><span>Open chart ↗</span></a></article>"""


def render_annualized_ranking(rows: list[dict[str, object]], history_path: Path) -> str:
    source_groups, views = annualized_ranking_views(rows)
    source_tabs = "".join(
        f'<button role="tab" type="button" data-annualized-source="{excess_source_key(group)}" aria-selected="{str(group == "mixed").lower()}">{"Mixed highest" if group == "mixed" else duration_label(group)}</button>'
        for group in source_groups
    )
    cards = []
    for source_key, winners in views.items():
        hidden = "" if source_key == "mixed" else " hidden"
        content = "".join(render_annualized_card(row, index) for index, row in enumerate(winners, start=1))
        content = content or '<p class="empty-results">No eligible chart-backed annualized results match this horizon.</p>'
        cards.append(f'<section class="excess-grid" data-annualized-view data-source="{source_key}"{hidden}>{content}</section>')
    written = datetime.fromtimestamp(history_path.stat().st_mtime).astimezone().strftime("%d %b %Y %H:%M")
    return page_head("Top Annualized Return · Backtest Intelligence", "../", "Historical strategy and buy-and-hold annualized return rankings.") + f"""<body><div class="site-shell annualized-page" data-annualized-dashboard>
<header class="topbar">{brand('../index.html')}<div class="top-actions"><span class="fresh"><i></i>History refreshed {written}</span>{theme_button()}</div></header>
<main class="excess-shell"><a class="back-link" href="../index.html">← Master dashboard</a><section class="excess-heading"><span class="eyebrow dark">HISTORICAL COMPOUNDING</span><h1>Top Annualized Return</h1><p>Highest historical annualized result, whether from strategy or buy and hold, grouped by source-data horizon.</p><small>Source <b>{esc(history_path.name)}</b> · {len(rows)} eligible completed runs with chart evidence.</small></section>
<section class="excess-controls buyhold-controls"><div><p>Choose the source-data CSV horizon.</p><div class="excess-tabs" role="tablist" aria-label="Annualized return source horizon" data-tab-group>{source_tabs}</div></div></section>
<p class="excess-note">Each view selects the strongest annualized result per fund. Strategy wins exact ties; runs without a usable technical chart are excluded.</p>{''.join(cards)}</main><footer>Historical compounding evidence from {esc(history_path.name)} · Past simulated results do not predict future performance.</footer></div></body></html>"""


def metric_card(label: str, metrics: dict[str, object], historical: bool = False) -> str:
    note = "<p>Best valid completed historical run</p>" if historical else ""
    return f"""<article class="metric-card"><span>{label}</span><strong class="{tone(metrics['annualized'])}">{pct(metrics['annualized'])}</strong><small>Annualized strategy</small><dl><div><dt>Total return</dt><dd>{pct(metrics['totalReturn'])}</dd></div><div><dt>Buy &amp; hold ann.</dt><dd>{pct(metrics['buyHoldAnnualized'])}</dd></div><div><dt>Excess ann.</dt><dd class="{tone(metrics['excessAnnualized'])}">{pct(metrics['excessAnnualized'])}</dd></div><div><dt>Sharpe</dt><dd>{num(metrics['sharpe'])}</dd></div></dl>{note}</article>"""


def render_detail(fund: dict[str, object]) -> str:
    m, params, stats, charts = fund["latest"], fund["parameters"], fund["statistics"], fund["charts"]
    signal = fund["signal"]
    parameter_values = (
        ("Short / long EMA", f"{params['shortEma'] if params['shortEma'] is not None else '—'} / {params['longEma'] if params['longEma'] is not None else '—'}"),
        ("RSI guards", f"{params['rsiOversold'] if params['rsiOversold'] is not None else '—'} / {params['rsiOverbought'] if params['rsiOverbought'] is not None else '—'}"),
        ("Stop loss", pct(params["stopLoss"], False)), ("Cooldown", f"{params['cooldown'] if params['cooldown'] is not None else '—'} days"),
        ("Drawdown exit", pct(params["drawdownExit"], False)), ("Reentry rebound", pct(params["reentryRebound"], False)),
        ("Exposure", f"{num(params['exposure'])}×"), ("Trades", stats["trades"] if stats["trades"] is not None else "—"),
        ("Win rate", pct(stats["winRate"], False)), ("Time invested", pct(stats["timeInvested"], False)),
        ("Uptrend cash", pct(stats["uptrendCash"], False)), ("Stop-loss exits", stats["stopLossCount"] if stats["stopLossCount"] is not None else "—"),
    )
    parameters_html = "".join(f"<article><span>{label}</span><strong>{esc(value)}</strong></article>" for label, value in parameter_values)
    available = next((item for item in CHARTS if charts.get(item[0])), None)
    tabs = "".join(
        f'<button role="tab" data-chart-tab aria-selected="{str(item == available).lower()}" class="{"selected" if item == available else ""}" {"" if charts.get(item[0]) else "disabled"} data-src="{esc(charts.get(item[0]) or "")}" data-description="{esc(item[4])}" data-alt="{esc(fund["name"] + " " + item[3].lower() + " backtest chart")}">{item[3]}</button>'
        for item in CHARTS
    )
    initial_src = charts.get(available[0]) if available else ""
    initial_description = available[4] if available else "No chart assets were produced for this run."
    frame_class = "chart-frame" if initial_src else "chart-frame is-hidden"
    unavailable_class = "chart-unavailable is-hidden" if initial_src else "chart-unavailable"
    return page_head(f"{fund['code']} · Backtest Intelligence", "../../", f"Backtest evidence and diagnostics for {fund['name']}.") + f"""<body><div class="site-shell detail-page"><header class="topbar">{brand('../../index.html')}{theme_button()}</header><main class="detail-shell"><a class="back-link" href="../../index.html">← Master dashboard</a>
<section class="detail-heading"><div><span class="eyebrow dark">FUND BACKTEST · LATEST RANK #{fund['rank']}</span><h1>{esc(fund['name'])}</h1><p>{esc(fund['code'])} · Full strategy evidence and replay diagnostics</p></div><span class="signal large {signal_class(signal)}"><i></i>{esc(signal)}</span></section>
<section class="detail-facts"><span>Latest history <b>{date_text(fund['latestStart'])} — {date_text(fund['latestEnd'])}</b></span><span>Source window <b>{date_text(fund['sourceStart'])} — {date_text(fund['sourceEnd'])}</b></span><span>Last trade <b>{date_text(fund['lastTradeDate'])}</b></span></section>
<section class="detail-metrics">{metric_card('Latest full history', m)}{metric_card('Source replay', fund['source'])}{metric_card('Historical leader', fund['historicalBest'], True)}</section>
<section class="parameter-panel"><div class="section-heading"><div><span class="eyebrow dark">SELECTED STRATEGY</span><h2>Parameters and run quality</h2></div></div><div class="parameter-grid">{parameters_html}</div></section>
<section class="chart-panel" data-chart-panel><div class="section-heading"><div><span class="eyebrow dark">VISUAL EVIDENCE</span><h2>Backtest charts</h2><p class="chart-description" data-chart-description>{esc(initial_description)}</p></div></div><div class="chart-tabs" role="tablist" aria-label="Backtest chart type">{tabs}</div><a class="{frame_class}" data-chart-frame href="{esc(initial_src)}" target="_blank" rel="noreferrer"><img src="{esc(initial_src)}" alt="{esc(fund['name'])} backtest chart"><span>Open full-size chart ↗</span></a><div class="{unavailable_class}" data-chart-unavailable><div><strong>Chart unavailable</strong><p>This run did not produce the selected chart asset.</p></div></div></section></main>
<footer>{esc(fund['code'])} · Data through {esc(fund['latestEnd'] or 'unavailable')} · Past simulated results do not predict future performance.</footer></div></body></html>"""


def build_site(
    snapshot: dict[str, object],
    history: list[dict[str, str]] | None = None,
    history_path: Path | None = None,
    site: Path = SITE,
    source: Path = SOURCE,
) -> None:
    project = site.parent.resolve()
    staging = project / ".site-build"
    if staging.exists():
        shutil.rmtree(staging)
    assets = staging / "assets"
    charts_dir = assets / "charts"
    charts_dir.mkdir(parents=True)
    for filename in ("styles.css", "dashboard.js", "og.png"):
        shutil.copy2(source / filename, assets / filename)

    for fund in snapshot["funds"]:
        generated: dict[str, str | None] = {}
        for key, _, suffix, _, _ in CHARTS:
            chart_source = fund["chartSources"].get(key)
            path = Path(chart_source) if chart_source else None
            if path and path.is_file():
                destination = charts_dir / f"{fund['slug']}-{suffix}{path.suffix.lower()}"
                shutil.copy2(path, destination)
                generated[key] = f"../../assets/charts/{destination.name}"
            else:
                generated[key] = None
        fund["charts"] = generated

    excess_rows = excess_history_rows(history or [])
    buyhold_rows = latest_buyhold_run_years(buyhold_history_rows(history or []))
    annualized_rows = annualized_history_rows(history or [])
    if history_path is not None:
        _, _, excess_views = excess_ranking_views(excess_rows)
        unique_runs = {row["id"]: row for winners in excess_views.values() for row in winners}
        excess_charts_dir = assets / "excess-charts"
        excess_charts_dir.mkdir(parents=True, exist_ok=True)
        for row in unique_runs.values():
            source_chart = row["chartPath"]
            safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", row["id"]).strip("-") or row["code"].lower()
            destination = excess_charts_dir / f"{row['code'].lower()}-{safe_id}{source_chart.suffix.lower()}"
            shutil.copy2(source_chart, destination)
            row["chart"] = f"../assets/excess-charts/{destination.name}"

        _, annualized_views = annualized_ranking_views(annualized_rows)
        annualized_runs = {row["id"]: row for winners in annualized_views.values() for row in winners}
        annualized_charts_dir = assets / "annualized-charts"
        annualized_charts_dir.mkdir(parents=True, exist_ok=True)
        for row in annualized_runs.values():
            source_chart = row["chartPath"]
            safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", row["id"]).strip("-") or row["code"].lower()
            destination = annualized_charts_dir / f"{row['code'].lower()}-{safe_id}{source_chart.suffix.lower()}"
            shutil.copy2(source_chart, destination)
            row["chart"] = f"../assets/annualized-charts/{destination.name}"

        buyhold_charts_dir = assets / "buyhold-charts"
        buyhold_charts_dir.mkdir(parents=True, exist_ok=True)
        while buyhold_rows:
            _, buyhold_views = buyhold_ranking_views(buyhold_rows)
            selected = {row["id"]: row for winners in buyhold_views.values() for row in winners}
            failed: set[str] = set()
            for row in selected.values():
                safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", row["id"]).strip("-") or row["code"].lower()
                destination = buyhold_charts_dir / f"{row['code'].lower()}-{safe_id}.png"
                if not generate_buyhold_chart(row["dataFile"], row["start"], row["end"], destination):
                    failed.add(row["id"])
                    continue
                row["chart"] = f"../assets/buyhold-charts/{destination.name}"
            if not failed:
                break
            buyhold_rows = [row for row in buyhold_rows if row["id"] not in failed]

    (staging / "index.html").write_text(render_master(snapshot), encoding="utf-8")
    for fund in snapshot["funds"]:
        fund_dir = staging / "funds" / fund["slug"]
        fund_dir.mkdir(parents=True)
        (fund_dir / "index.html").write_text(render_detail(fund), encoding="utf-8")
    if history_path is not None:
        excess_dir = staging / "excess-ranking"
        excess_dir.mkdir()
        (excess_dir / "index.html").write_text(render_excess_ranking(excess_rows, history_path), encoding="utf-8")
        buyhold_dir = staging / "buyhold-ranking"
        buyhold_dir.mkdir()
        (buyhold_dir / "index.html").write_text(render_buyhold_ranking(buyhold_rows, history_path), encoding="utf-8")
        annualized_dir = staging / "annualized-ranking"
        annualized_dir.mkdir()
        (annualized_dir / "index.html").write_text(render_annualized_ranking(annualized_rows, history_path), encoding="utf-8")

    if site.exists():
        shutil.rmtree(site)
    shutil.move(str(staging), str(site))


def main() -> None:
    summary_path, rows = latest_successful_summary(TUNINGS.glob("final_backtest_summary_*.csv"))
    history_path = TUNINGS / "backtest_run_history.csv"
    history = read_csv(history_path)
    snapshot = build_snapshot(summary_path, rows, history)
    build_site(snapshot, history, history_path)
    print(f"Generated {len(snapshot['funds'])} fund pages from {summary_path.name}")
    print(f"Open locally: {(SITE / 'index.html').resolve()}")


if __name__ == "__main__":
    main()
