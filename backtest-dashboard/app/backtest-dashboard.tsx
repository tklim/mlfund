"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { backtestSnapshot, type BacktestFund, type BacktestMetrics } from "./backtest-data.generated";

type SortKey = "latest" | "annualized" | "buyHold" | "excess" | "drawdown";
type Direction = "desc" | "asc";
type ChartKey = "latestTechnical" | "sourceTechnical" | "sourceSimple";
type ColumnKey = "annualized" | "buyHold" | "excess" | "drawdown" | "sharpe" | "trades";

const SORTS: Array<{ key: SortKey; label: string }> = [
  { key: "latest", label: "Latest strategy" },
  { key: "annualized", label: "Strategy ann." },
  { key: "buyHold", label: "B&H ann." },
  { key: "excess", label: "Excess" },
  { key: "drawdown", label: "Drawdown" },
];
const ALL_COLUMNS: Array<{ key: ColumnKey; label: string }> = [
  { key: "annualized", label: "Strategy ann." }, { key: "buyHold", label: "B&H ann." },
  { key: "excess", label: "Excess" }, { key: "drawdown", label: "Drawdown" },
  { key: "sharpe", label: "Sharpe" }, { key: "trades", label: "Trades" },
];
const CHARTS: Array<{ key: ChartKey; label: string; description: string }> = [
  { key: "latestTechnical", label: "Latest technical", description: "Full local history replay with signals, RSI and portfolio value." },
  { key: "sourceTechnical", label: "Source technical", description: "The original evaluation window used for the selected parameters." },
  { key: "sourceSimple", label: "Simple comparison", description: "A concise strategy-versus-buy-and-hold result view." },
];
const DEFAULT_COLUMNS = new Set<ColumnKey>(["annualized", "buyHold", "excess", "drawdown"]);

function pct(value: number | null, signed = true) {
  if (value === null) return "—";
  return `${signed && value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}
function num(value: number | null, digits = 2) { return value === null ? "—" : value.toFixed(digits); }
function displayDate(value: string | null) {
  if (!value) return "Unavailable";
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(`${value}T00:00:00`));
}
function signalClass(signal: string) { return signal.startsWith("BUY") ? "buy" : signal.startsWith("SELL") ? "cash" : "unknown"; }
function sortValue(fund: BacktestFund, key: SortKey) {
  if (key === "latest") return fund.latest.totalReturn;
  if (key === "annualized") return fund.latest.annualized;
  if (key === "buyHold") return fund.latest.buyHoldAnnualized;
  if (key === "excess") return fund.latest.excessAnnualized;
  return fund.latest.maxDrawdown === null ? null : -Math.abs(fund.latest.maxDrawdown);
}
function metricTone(value: number | null) { return value === null ? "muted" : value >= 0 ? "positive" : "negative"; }

function ThemeToggle() {
  const bootstrapped = useSyncExternalStore(() => () => {}, () => document.documentElement.dataset.theme === "dark" ? "dark" : "light", () => "light");
  const [override, setOverride] = useState<"light" | "dark" | null>(null);
  const theme = override ?? bootstrapped;
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    document.documentElement.style.colorScheme = next;
    localStorage.setItem("backtest-theme", next);
    setOverride(next);
  };
  return <button className="theme-toggle" type="button" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} aria-pressed={theme === "dark"}><span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span><b>{theme === "dark" ? "Light" : "Dark"}</b></button>;
}

function MasterDashboard() {
  const [sort, setSort] = useState<SortKey>("latest");
  const [direction, setDirection] = useState<Direction>("desc");
  const [query, setQuery] = useState("");
  const [columns, setColumns] = useState(DEFAULT_COLUMNS);
  const funds = backtestSnapshot.funds;
  const ranked = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return funds.filter((fund) => !normalized || `${fund.code} ${fund.name}`.toLowerCase().includes(normalized)).toSorted((a, b) => {
      const av = sortValue(a, sort); const bv = sortValue(b, sort);
      const base = av === null ? 1 : bv === null ? -1 : av - bv;
      return (direction === "asc" ? base : -base) || a.code.localeCompare(b.code);
    });
  }, [direction, funds, query, sort]);
  const leader = funds.toSorted((a, b) => (b.latest.totalReturn ?? -Infinity) - (a.latest.totalReturn ?? -Infinity))[0];
  const excessLeader = funds.toSorted((a, b) => (b.historicalBest.excessAnnualized ?? -Infinity) - (a.historicalBest.excessAnnualized ?? -Infinity))[0];
  const buyCount = funds.filter((fund) => fund.signal.startsWith("BUY")).length;
  const setPreset = (key: SortKey) => { setSort(key); setDirection("desc"); document.getElementById("ranking")?.scrollIntoView({ behavior: "smooth", block: "start" }); };
  const toggleColumn = (key: ColumnKey) => setColumns((current) => { const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next; });

  return <div className="site-shell">
    <header className="topbar"><Link className="brand" href="/"><span className="brand-mark">BI</span><span><b>Backtest Intelligence</b><small>Strategy evidence hub</small></span></Link><div className="top-actions"><span className="fresh"><i />Local snapshot · {displayDate(backtestSnapshot.latestObservation)}</span><ThemeToggle /></div></header>
    <main className="master-shell">
      <section className="hero"><span className="eyebrow">BACKTEST INTELLIGENCE HUB</span><h1>Every strategy. One evidence trail.</h1><p>Compare full-history replays, rank adaptive strategies against buy and hold, and open every fund&apos;s technical evidence from one independent workspace.</p><div className="hero-pills"><span>{funds.length} funds</span><span>Latest local data {backtestSnapshot.latestObservation}</span><span>Run completed {backtestSnapshot.runCompletedAt?.slice(0, 16) ?? "Unavailable"}</span></div></section>
      <section className="kpi-grid" aria-label="Backtest summary">
        <article><span>Latest leader</span><strong>{leader.code} · {pct(leader.latest.totalReturn)}</strong></article>
        <article><span>Best historical excess</span><strong>{excessLeader.code} · {pct(excessLeader.historicalBest.excessAnnualized)}</strong></article>
        <article><span>Buy signals</span><strong>{buyCount} of {funds.length}</strong></article>
        <article><span>Newest observation</span><strong>{backtestSnapshot.latestObservation}</strong></article>
      </section>
      <section className="lens-grid" aria-label="Backtest views">
        {[
          ["1", "Latest results", "Rank the most recent full-history replay.", "latest"],
          ["2", "Historical excess", "Find the strongest run versus buy and hold.", "excess"],
          ["3", "Annualized return", "Compare long-run strategy compounding.", "annualized"],
          ["4", "Chart gallery", "Open a fund to inspect all three charts.", "latest"],
          ["5", "Buy & hold horizons", "Contrast the strategy with passive exposure.", "buyHold"],
        ].map(([index, title, text, key]) => <button key={title} type="button" onClick={() => setPreset(key as SortKey)}><span>{index}</span><strong>{title}</strong><p>{text}</p></button>)}
      </section>
      <section className="ranking-panel" id="ranking" aria-labelledby="ranking-title">
        <div className="ranking-toolbar"><div><span className="eyebrow dark">LATEST REPLAY</span><h2 id="ranking-title">Backtest rankings</h2></div><label className="search"><span className="sr-only">Search fund name or code</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name or code" /></label></div>
        <div className="sortbar"><span className="sort-label">SORT FUNDS</span><div className="sort-pills">{SORTS.map((item) => <button key={item.key} className={sort === item.key ? "selected" : ""} type="button" onClick={() => setSort(item.key)}>{item.label}</button>)}</div><div className="sort-actions"><button className="direction" type="button" onClick={() => setDirection(direction === "desc" ? "asc" : "desc")}>{direction === "desc" ? "Highest first ↓" : "Lowest first ↑"}</button><details className="columns"><summary>Columns ({columns.size + 3})</summary><div>{ALL_COLUMNS.map((column) => <label key={column.key}><input type="checkbox" checked={columns.has(column.key)} onChange={() => toggleColumn(column.key)} />{column.label}</label>)}</div></details></div></div>
        <p className="table-note">{ranked.length} funds · {buyCount} buy signals · <b>W</b> marks the stronger annualized result <span>All data through <strong>{backtestSnapshot.latestObservation}</strong></span></p>
        <div className="table-wrap"><table><thead><tr><th>#</th><th>Fund / signal</th><th>Latest strategy</th>{columns.has("annualized") && <th>Strategy ann.</th>}{columns.has("buyHold") && <th>B&amp;H ann.</th>}{columns.has("excess") && <th>Excess</th>}{columns.has("drawdown") && <th>Drawdown</th>}{columns.has("sharpe") && <th>Sharpe</th>}{columns.has("trades") && <th>Trades</th>}<th aria-label="Open fund detail" /></tr></thead><tbody>
          {ranked.map((fund, index) => { const strategyWins = (fund.latest.annualized ?? -Infinity) >= (fund.latest.buyHoldAnnualized ?? -Infinity); return <tr key={fund.id}><td>#{index + 1}</td><td><Link className="fund-identity" href={`/funds/${fund.slug}`}><strong>{fund.code}</strong><span>{fund.name}</span><small className={`signal ${signalClass(fund.signal)}`}><i />{fund.signal}</small></Link></td><td className={metricTone(fund.latest.totalReturn)}><b>{pct(fund.latest.totalReturn)}</b></td>{columns.has("annualized") && <td className={metricTone(fund.latest.annualized)}>{pct(fund.latest.annualized)} {strategyWins && <em>W</em>}</td>}{columns.has("buyHold") && <td className={metricTone(fund.latest.buyHoldAnnualized)}>{pct(fund.latest.buyHoldAnnualized)} {!strategyWins && <em>W</em>}</td>}{columns.has("excess") && <td className={metricTone(fund.latest.excessAnnualized)}>{pct(fund.latest.excessAnnualized)}</td>}{columns.has("drawdown") && <td className="negative">{pct(fund.latest.maxDrawdown, false)}</td>}{columns.has("sharpe") && <td>{num(fund.latest.sharpe)}</td>}{columns.has("trades") && <td>{fund.statistics.trades ?? "—"}</td>}<td><Link className="row-arrow" href={`/funds/${fund.slug}`} aria-label={`Open ${fund.name} backtest detail`}>→</Link></td></tr>; })}
        </tbody></table></div>
        <div className="mobile-results">{ranked.map((fund, index) => <Link href={`/funds/${fund.slug}`} key={fund.id} className="mobile-result"><span className="mobile-rank">#{index + 1}</span><span className="mobile-title"><strong>{fund.code}</strong><small>{fund.name}</small></span><span className={`signal ${signalClass(fund.signal)}`}><i />{fund.signal}</span><dl><div><dt>Latest</dt><dd>{pct(fund.latest.totalReturn)}</dd></div><div><dt>Annualized</dt><dd>{pct(fund.latest.annualized)}</dd></div><div><dt>Excess</dt><dd>{pct(fund.latest.excessAnnualized)}</dd></div></dl><b className="mobile-arrow">→</b></Link>)}</div>
      </section>
    </main>
    <footer>Generated from {backtestSnapshot.sourceSummary} · Standalone backtest workspace</footer>
  </div>;
}

function MetricCard({ label, metrics, historical = false }: { label: string; metrics: BacktestMetrics; historical?: boolean }) {
  return <article className="metric-card"><span>{label}</span><strong className={metricTone(metrics.annualized)}>{pct(metrics.annualized)}</strong><small>Annualized strategy</small><dl><div><dt>Total return</dt><dd>{pct(metrics.totalReturn)}</dd></div><div><dt>Buy &amp; hold ann.</dt><dd>{pct(metrics.buyHoldAnnualized)}</dd></div><div><dt>Excess ann.</dt><dd className={metricTone(metrics.excessAnnualized)}>{pct(metrics.excessAnnualized)}</dd></div><div><dt>Sharpe</dt><dd>{num(metrics.sharpe)}</dd></div></dl>{historical && <p>Best valid completed historical run</p>}</article>;
}

function FundDetail({ fund }: { fund: BacktestFund }) {
  const firstAvailable = CHARTS.find((chart) => fund.charts[chart.key])?.key ?? "latestTechnical";
  const [chart, setChart] = useState<ChartKey>(firstAvailable);
  const active = CHARTS.find((item) => item.key === chart)!;
  useEffect(() => { document.title = `${fund.code} · Backtest Intelligence`; }, [fund.code]);
  return <div className="site-shell detail-page">
    <header className="topbar"><Link className="brand" href="/"><span className="brand-mark">BI</span><span><b>Backtest Intelligence</b><small>Strategy evidence hub</small></span></Link><ThemeToggle /></header>
    <main className="detail-shell">
      <Link className="back-link" href="/">← Master dashboard</Link>
      <section className="detail-heading"><div><span className="eyebrow dark">FUND BACKTEST · LATEST RANK #{fund.rank}</span><h1>{fund.name}</h1><p>{fund.code} · Full strategy evidence and replay diagnostics</p></div><span className={`signal large ${signalClass(fund.signal)}`}><i />{fund.signal}</span></section>
      <section className="detail-facts"><span>Latest history <b>{displayDate(fund.latestStart)} — {displayDate(fund.latestEnd)}</b></span><span>Source window <b>{displayDate(fund.sourceStart)} — {displayDate(fund.sourceEnd)}</b></span><span>Last trade <b>{displayDate(fund.lastTradeDate)}</b></span></section>
      <section className="detail-metrics"><MetricCard label="Latest full history" metrics={fund.latest} /><MetricCard label="Source replay" metrics={fund.source} /><MetricCard label="Historical leader" metrics={fund.historicalBest} historical /></section>
      <section className="parameter-panel"><div className="section-heading"><div><span className="eyebrow dark">SELECTED STRATEGY</span><h2>Parameters and run quality</h2></div></div><div className="parameter-grid">
        {[['Short / long EMA', `${fund.parameters.shortEma ?? '—'} / ${fund.parameters.longEma ?? '—'}`], ['RSI guards', `${fund.parameters.rsiOversold ?? '—'} / ${fund.parameters.rsiOverbought ?? '—'}`], ['Stop loss', pct(fund.parameters.stopLoss, false)], ['Cooldown', `${fund.parameters.cooldown ?? '—'} days`], ['Drawdown exit', pct(fund.parameters.drawdownExit, false)], ['Reentry rebound', pct(fund.parameters.reentryRebound, false)], ['Exposure', `${num(fund.parameters.exposure)}×`], ['Trades', String(fund.statistics.trades ?? '—')], ['Win rate', pct(fund.statistics.winRate, false)], ['Time invested', pct(fund.statistics.timeInvested, false)], ['Uptrend cash', pct(fund.statistics.uptrendCash, false)], ['Stop-loss exits', String(fund.statistics.stopLossCount ?? '—')]].map(([label, value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}
      </div></section>
      <section className="chart-panel"><div className="section-heading"><div><span className="eyebrow dark">VISUAL EVIDENCE</span><h2>Backtest charts</h2><p>{active.description}</p></div></div><div className="chart-tabs" role="tablist" aria-label="Backtest chart type">{CHARTS.map((item) => <button key={item.key} role="tab" aria-selected={chart === item.key} disabled={!fund.charts[item.key]} className={chart === item.key ? "selected" : ""} onClick={() => setChart(item.key)}>{item.label}</button>)}</div>{fund.charts[chart] ? <a className="chart-frame" href={fund.charts[chart]!} target="_blank" rel="noreferrer"><img src={fund.charts[chart]!} alt={`${fund.name} ${active.label.toLowerCase()} backtest chart`} /><span>Open full-size chart ↗</span></a> : <div className="chart-unavailable"><strong>Chart unavailable</strong><p>This run did not produce the selected chart asset.</p></div>}</section>
    </main>
    <footer>{fund.code} · Data through {fund.latestEnd ?? "unavailable"} · Past simulated results do not predict future performance.</footer>
  </div>;
}

export function BacktestDashboard({ fundKey }: { fundKey?: string }) {
  if (!fundKey) return <MasterDashboard />;
  const fund = backtestSnapshot.funds.find((item) => item.slug === fundKey.toLowerCase() || item.code.toLowerCase() === fundKey.toLowerCase());
  if (!fund) return <div className="not-found"><span>404</span><h1>Backtest not found</h1><p>No generated fund snapshot matches “{fundKey}”.</p><Link href="/">Return to master dashboard</Link></div>;
  return <FundDetail fund={fund} />;
}
