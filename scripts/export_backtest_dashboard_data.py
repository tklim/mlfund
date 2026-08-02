"""Export a self-contained snapshot for the standalone backtest dashboard."""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TUNINGS = ROOT / "outputs" / "tunings"
APP = ROOT / "backtest-dashboard"
OUTPUT = APP / "app" / "backtest-data.generated.ts"
ASSETS = APP / "public" / "backtests"

FUND_NAMES = {
    "MAKGCF_GreaterChina": ("MAKGCF", "Greater China"),
    "MAPAC_AsiaPacificexJapan": ("MAPAC", "Asia Pacific ex Japan"),
    "HWFL_HWFlexi": ("HWFL", "HW Flexi"),
    "APCR_AsiaPacificREIT": ("APCR", "Asia Pacific REIT"),
    "MGLVH_GlobalLowVolatilityEquityARMHClass": ("MGLVH", "Global Low Volatility"),
    "MIIEH_IndiaEquityRMH": ("MIIEH", "India Equity"),
    "MPGFC_PRSGrowthC": ("MPGFC", "PRS Growth C"),
    "MAPF_Progress": ("MAPF", "Progress"),
    "MAUS_RMH_USEquityRMH": ("MAUS", "US Equity"),
    "MGPRH_GlobalPerspective": ("MGPRH", "Global Perspective"),
    "MSGLR_RM_ShariahGlobalREITMYR": ("MSGLR", "Shariah Global REIT"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str, digits: int = 2) -> float | None:
    value = row.get(key, "")
    if value is None or not str(value).strip():
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def integer(row: dict[str, str], key: str) -> int | None:
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
        incumbent_excess = number(incumbent, "excess_annualized_return_pct", 8) if incumbent else None
        candidate_key = (excess, row.get("run_started_at", ""), row.get("run_id", ""))
        incumbent_key = (incumbent_excess, incumbent.get("run_started_at", ""), incumbent.get("run_id", "")) if incumbent and incumbent_excess is not None else None
        if incumbent_key is None or candidate_key > incumbent_key:
            best[fund] = row
    return best


def metric_block(row: dict[str, str], prefix: str = "") -> dict[str, object]:
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


def copy_chart(source: str | None, code: str, kind: str) -> str | None:
    if not source:
        return None
    path = Path(source)
    if not path.exists():
        return None
    ASSETS.mkdir(parents=True, exist_ok=True)
    destination = ASSETS / f"{code.lower()}-{kind}{path.suffix.lower()}"
    shutil.copy2(path, destination)
    return f"/backtests/{destination.name}"


def build_snapshot(summary_path: Path, rows: list[dict[str, str]], history: list[dict[str, str]]) -> dict[str, object]:
    historical = best_history_rows(history)
    funds: list[dict[str, object]] = []
    for row in rows:
        label = row.get("fund_label", "")
        if label not in FUND_NAMES:
            continue
        code, name = FUND_NAMES[label]
        history_row = historical.get(label, {})
        latest = metric_block(row, "latest_")
        source = metric_block(row)
        best = metric_block(history_row)
        fund = {
            "id": label,
            "slug": code.lower(),
            "code": code,
            "name": name,
            "signal": normalize_signal(row.get("ga_signal")),
            "lastTradeDate": row.get("last_trade_date") or None,
            "latestStart": row.get("latest_data_start") or None,
            "latestEnd": row.get("latest_data_end") or None,
            "sourceStart": row.get("data_start") or None,
            "sourceEnd": row.get("data_end") or None,
            "latest": latest,
            "source": source,
            "historicalBest": {
                **best,
                "lookbackYears": number(history_row, "lookback_years", 1),
                "offsetMonths": integer(history_row, "offset_months"),
                "start": history_row.get("backtest_start") or None,
                "end": history_row.get("backtest_end") or None,
                "runId": history_row.get("run_id") or None,
            },
            "parameters": {
                "shortEma": integer(row, "short_ema"),
                "longEma": integer(row, "long_ema"),
                "stopLoss": number(row, "stop_loss"),
                "cooldown": integer(row, "cooldown"),
                "drawdownExit": number(row, "drawdown_exit_pct"),
                "reentryRebound": number(row, "reentry_rebound_pct"),
                "rsiOversold": integer(row, "rsi_oversold"),
                "rsiOverbought": integer(row, "rsi_overbought"),
                "exposure": number(row, "exposure_multiplier"),
            },
            "statistics": {
                "trades": integer(row, "trade_count"),
                "winRate": number(row, "win_rate_pct"),
                "timeInvested": number(row, "time_invested_pct"),
                "uptrendCash": number(row, "uptrend_cash_pct"),
                "missedUpside": number(row, "missed_upside_after_exit_pct"),
                "stopLossCount": integer(row, "stop_loss_count"),
            },
            "charts": {
                "latestTechnical": copy_chart(row.get("latest_chart_file"), code, "latest-technical"),
                "sourceTechnical": copy_chart(row.get("technical_chart_file"), code, "source-technical"),
                "sourceSimple": copy_chart(row.get("simple_chart_file"), code, "source-simple"),
            },
        }
        funds.append(fund)

    funds.sort(key=lambda item: (item["latest"]["totalReturn"] is not None, item["latest"]["totalReturn"] or float("-inf"), item["code"]), reverse=True)
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


def write_snapshot(snapshot: dict[str, object]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False)
    OUTPUT.write_text(
        "// Generated by scripts/export_backtest_dashboard_data.py. Do not edit manually.\n"
        "export type BacktestMetrics = { totalReturn: number | null; buyHoldReturn: number | null; excessReturn: number | null; annualized: number | null; buyHoldAnnualized: number | null; excessAnnualized: number | null; sharpe: number | null; maxDrawdown: number | null };\n"
        "export type BacktestFund = { id: string; slug: string; code: string; name: string; rank: number; signal: string; lastTradeDate: string | null; latestStart: string | null; latestEnd: string | null; sourceStart: string | null; sourceEnd: string | null; latest: BacktestMetrics; source: BacktestMetrics; historicalBest: BacktestMetrics & { lookbackYears: number | null; offsetMonths: number | null; start: string | null; end: string | null; runId: string | null }; parameters: Record<string, number | null>; statistics: Record<string, number | null>; charts: Record<string, string | null> };\n"
        "export type BacktestSnapshot = { generatedAt: string; sourceSummary: string; runCompletedAt: string | null; latestObservation: string | null; funds: BacktestFund[] };\n"
        f"export const backtestSnapshot: BacktestSnapshot = {payload};\n",
        encoding="utf-8",
    )


def main() -> None:
    summary_path, rows = latest_successful_summary(TUNINGS.glob("final_backtest_summary_*.csv"))
    history_path = TUNINGS / "backtest_run_history.csv"
    snapshot = build_snapshot(summary_path, rows, read_csv(history_path))
    write_snapshot(snapshot)
    print(f"Exported {len(snapshot['funds'])} funds from {summary_path.name} to {OUTPUT}")


if __name__ == "__main__":
    main()
