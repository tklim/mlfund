"""Export the latest local fund reports into the dashboard's typed snapshot."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "outputs" / "reports"
DATA = ROOT / "data"
OUTPUT = ROOT / "dashboard" / "app" / "fund-data.generated.ts"
FUNDAMENTALS = REPORTS / "fundamentals"

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
    "MSCEH_ShariahChinaEquityARMHClass": ("MSCEH", "Shariah China Equity"),
    "SPGA_ShariahPRSGoldenAsiaClassC": ("SPGA", "Shariah PRS Golden Asia"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: str | None, *, scale: float = 1.0, digits: int = 1) -> float | None:
    if value in (None, ""):
        return None
    return round(float(value) * scale, digits)


def price_series(fund_label: str, latest: str) -> list[dict[str, float | str]]:
    path = DATA / f"{fund_label}_nav_5Y.csv"
    if not path.exists():
        return []
    cutoff = date.fromisoformat(latest) - timedelta(days=370)
    points = [
        {"date": row["Date"], "value": round(float(row["TotalReturn"]), 6)}
        for row in read_csv(path)
        if date.fromisoformat(row["Date"]) >= cutoff
    ]
    if len(points) <= 28:
        return points
    step = max(1, len(points) // 24)
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def main() -> None:
    forward_rows = read_csv(REPORTS / "fund_forward_decision_dashboard.csv")
    scores = {row["Fund Label"]: row for row in read_csv(REPORTS / "fund_decision_scores.csv")}
    strategy_path = REPORTS / "fund_strategy_best_by_fund.csv"
    strategies = {row["fund_label"]: row for row in read_csv(strategy_path)} if strategy_path.exists() else {}

    funds: list[dict[str, object]] = []
    series: dict[str, list[dict[str, float | str]]] = {}
    for row in forward_rows:
        fund_label = row["Fund Label"]
        if fund_label not in FUND_NAMES:
            continue
        code, name = FUND_NAMES[fund_label]
        score = scores.get(fund_label, {})
        strategy = strategies.get(fund_label, {})
        latest = row["Latest Date"]
        funds.append(
            {
                "id": fund_label,
                "code": code,
                "name": name,
                "date": latest,
                "nav": number(row.get("Latest TotalReturn"), digits=6),
                "conclusion": score.get("Conclusion") or row["Decision Label"],
                "forwardDecision": row["Decision Label"],
                "expected": number(row.get("Expected Forward Return"), scale=100),
                "positive": number(row.get("Probability > 0"), scale=100),
                "upside": number(row.get("Probability >= Upside Target"), scale=100),
                "downside": number(row.get("Probability <= Downside Risk"), scale=100),
                "edge": number(row.get("Conditional Expected Edge"), scale=100),
                "ret1m": number(row.get("Current Trailing Return 1M"), scale=100),
                "ret3m": number(row.get("Current Trailing Return 3M"), scale=100),
                "ret6m": number(row.get("Current Trailing Return 6M"), scale=100),
                "drawdown": number(row.get("Current Drawdown From 1Y High"), scale=100),
                "score": number(row.get("Decision Score"), scale=100),
                "crossRank": number(row.get("Cross-Fund Momentum Percentile"), scale=100, digits=0),
                "gaSignal": (score.get("GA Signal") or "unknown").replace("BUY/HOLD invested", "BUY / HOLD").replace("SELL/CASH", "SELL / CASH"),
                "agreement": score.get("GA Agreement") or "NEUTRAL",
                "lastTrade": strategy.get("last_trade_date") or None,
                "annualized": number(strategy.get("adaptive_annualized_return_pct")),
                "excess": number(strategy.get("excess_annualized_return_pct")),
                "sharpe": number(strategy.get("sharpe"), digits=2),
                "maxdd": number(strategy.get("max_dd_pct")),
                "confidence": row["Confidence Level"],
                "analogs": int(float(row["Effective Observations"])),
                "status": score.get("Data Status") or "unknown",
            }
        )
        series[code] = price_series(fund_label, latest)

    funds.sort(key=lambda item: float(item["score"] or -999), reverse=True)
    fundamental_snapshots: dict[str, dict[str, object]] = {}
    for code, _name in FUND_NAMES.values():
        path = FUNDAMENTALS / code / "latest.json"
        if not path.exists():
            continue
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            stale_days = int(snapshot.get("stale_after_days", 45))
            information_date = date.fromisoformat(snapshot["facts"]["information_date"])
            snapshot["is_stale"] = date.today() - information_date > timedelta(days=stale_days)
            fundamental_snapshots[code] = snapshot
        except (OSError, ValueError, KeyError, TypeError):
            continue
    latest_date = max(str(fund["date"]) for fund in funds)
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    payload = (
        "// Generated by scripts/export_dashboard_data.py. Do not edit manually.\n"
        "export type FundSnapshot = {\n"
        "  id: string; code: string; name: string; date: string; nav: number | null; conclusion: string; forwardDecision: string;\n"
        "  expected: number; positive: number; upside: number; downside: number; edge: number; ret1m: number; ret3m: number; ret6m: number; drawdown: number;\n"
        "  score: number; crossRank: number; gaSignal: string; agreement: string; lastTrade: string | null; annualized: number | null; excess: number | null;\n"
        "  sharpe: number | null; maxdd: number | null; confidence: string; analogs: number; status: string;\n"
        "};\n"
        "export type PricePoint = { date: string; value: number };\n"
        "export type Allocation = { rank: number; name: string; weight_pct: number };\n"
        "export type HoldingMetrics = { company_name: string | null; currency: string | null; market_cap: number | null; trailing_pe: number | null; forward_pe: number | null; price_to_book: number | null; revenue_growth_pct: number | null; earnings_growth_pct: number | null; return_on_equity_pct: number | null; free_cashflow_margin_pct: number | null; debt_to_equity_pct: number | null; beta: number | null; dividend_yield_pct: number | null };\n"
        "export type HoldingFundamentals = Allocation & { ticker: string | null; status: string; metrics_as_of: string | null; metrics: Partial<HoldingMetrics>; score: number | null; metric_coverage_pct?: number; subscores?: Record<string, number | null>; error?: string };\n"
        "export type FundFacts = { source_url: string; source_hash: string; factsheet_month: string; information_date: string; category: string; objective: string; investor_profile: string; profile_label: string; fund_manager: string; trustee: string; nav: number; nav_currency: string; fund_size_million: number; fund_size_currency: string; units_million: number; launch_date: string; inception_date: string; financial_year_end: string; currency: string; management_fee: string; trustee_fee: string; sales_charge: string; redemption_charge: string; distribution_frequency: string; benchmark: string; volatility_3y: number | null; volatility_label: string | null; published_returns_pct: Record<string, number>; calendar_returns_pct: Record<string, number>; sector_allocation: Allocation[]; geography_allocation: Allocation[] };\n"
        "export type FundFundamentals = { schema_version: number; fund_code: string; generated_at: string; status: string; is_stale: boolean; stale_after_days: number; facts: FundFacts; holdings: HoldingFundamentals[]; assessment: { score: number | null; label: string; top_five_weight_pct: number; scored_weight_pct: number; coverage_pct: number; scope: string }; methodology: { weights: Record<string, number>; minimum_metrics: number; decision_integration: string } };\n"
        f"export const snapshotDate = {json.dumps(latest_date)};\n"
        f"export const snapshotGeneratedAt = {json.dumps(generated_at)};\n"
        f"export const funds: FundSnapshot[] = {json.dumps(funds, separators=(',', ':'))};\n"
        f"export const fundSeries: Record<string, PricePoint[]> = {json.dumps(series, separators=(',', ':'))};\n"
        f"export const fundFundamentals: Record<string, FundFundamentals> = {json.dumps(fundamental_snapshots, separators=(',', ':'))};\n"
    )
    OUTPUT.write_text(payload, encoding="utf-8")
    print(f"Exported {len(funds)} funds to {OUTPUT}")


if __name__ == "__main__":
    main()
