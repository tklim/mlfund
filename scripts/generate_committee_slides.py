#!/usr/bin/env python3
"""
Committee Slide Generator
Renders one plain-language "committee slide" HTML page per fund from the
fund_forward_decision.py output CSVs (dashboard + details).

Run scripts/fund_forward_decision.py first (e.g. with --all) so the CSVs are
fresh, then:

    python scripts/generate_committee_slides.py            # all funds
    python scripts/generate_committee_slides.py MIIEH      # subset by code prefix
"""

import argparse
import html
import json
import math
import re
from datetime import date
from pathlib import Path
from string import Template

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
REPORTS_DIR = REPO_ROOT / "outputs" / "reports"
DEFAULT_DETAILS = REPORTS_DIR / "fund_forward_decision_details.csv"
DEFAULT_DASHBOARD = REPORTS_DIR / "fund_forward_decision_dashboard.csv"
DEFAULT_OUTPUT_DIR = REPORTS_DIR / "committee_slides"

HORIZON_PHRASE = {"1M": "one month", "3M": "three months", "6M": "six months", "1Y": "one year"}
HORIZON_ADJECTIVE = {"1M": "one-month", "3M": "three-month", "6M": "six-month", "1Y": "one-year"}
CONFIDENCE_SEGMENTS = {"LOW": 1, "MEDIUM": 2, "NORMAL": 3}
# Decision label -> (chip text, accent CSS variable)
DECISION_STYLE = {
    "BUY": ("Buy", "--up"),
    "HOLD / WATCH": ("Hold / Watch", "--hold"),
    "SELL / AVOID": ("Sell / Avoid", "--down"),
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render per-fund committee slide HTML pages from forward decision CSVs."
    )
    parser.add_argument(
        "funds",
        nargs="*",
        help="Optional fund code prefixes to render, for example MIIEH MAPF. Default: all funds.",
    )
    parser.add_argument("--details", type=Path, default=DEFAULT_DETAILS, help="Details CSV path.")
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD, help="Dashboard CSV path.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for slide HTML files.")
    return parser.parse_args()


def fund_code_and_name(fund_label):
    """MAUS_RMH_USEquityRMH -> ('MAUS_RMH', 'US Equity RMH'). The name part never
    contains underscores (see download_fund.py sanitize_label), so split on the last one."""
    code, _, rest = str(fund_label).rpartition("_")
    if not code:
        code, rest = rest, ""
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", rest).strip()
    return code, (name or code)


def pct(value, decimals=1, signed=True):
    """0.0234 -> '+2.3%'."""
    sign = "+" if signed and value >= 0 else ""
    text = f"{sign}{value * 100:.{decimals}f}%"
    return text.replace("-", "−")


def pct_points(value):
    """0.162 -> '16.2%' (unsigned probability)."""
    return f"{value * 100:.1f}%"


def display_date(value):
    return pd.Timestamp(value).strftime("%d %b %Y")


def horizon_phrase(label):
    return HORIZON_PHRASE.get(label, str(label))


def waffle_counts(up_prob, down_prob):
    up = max(0, min(100, round(up_prob * 100)))
    down = max(0, min(100 - up, round(down_prob * 100)))
    return up, 100 - up - down, down


def build_headline(decision, up_cells, down_cells, horizon_label):
    period = horizon_phrase(horizon_label)
    if decision == "BUY":
        h1 = (
            f"Over the next {period}, this fund has more ways to "
            '<span class="accent-word">win big</span> than to lose big.'
        )
        tail = "The pattern argues for adding."
    elif decision == "SELL / AVOID":
        h1 = (
            f"Over the next {period}, this fund has more ways to "
            '<span class="accent-word">lose big</span> than to win big.'
        )
        tail = "The pattern argues for stepping aside."
    elif down_cells - up_cells >= 4:
        h1 = (
            f"Over the next {period}, the odds still "
            '<span class="accent-word">lean negative</span> &mdash; but not by enough to act.'
        )
        tail = "The pattern argues for patience."
    elif up_cells - down_cells >= 4:
        h1 = (
            f"Over the next {period}, the odds "
            '<span class="accent-word">lean positive</span> &mdash; but not yet by enough to buy.'
        )
        tail = "The pattern argues for patience."
    else:
        h1 = (
            f"Over the next {period}, big wins and big losses look "
            '<span class="accent-word">about equally likely</span>.'
        )
        tail = "The pattern argues for patience."
    sub = (
        "We searched five years of this fund&rsquo;s history for the moments that most "
        f"resemble today, then looked at what happened next. {tail}"
    )
    return h1, sub


def build_verdict(decision):
    if decision == "BUY":
        sub = "The likely payoff justifies the downside from here."
        actions = [
            ("Add", "new money in measured steps."),
            ("Size", "the position so the loss line below is survivable."),
            ("Reassess", "if the price trend rolls back over."),
        ]
    elif decision == "SELL / AVOID":
        sub = "The likely payoff is too small to justify the downside from here."
        actions = [
            ("Hold off", "on adding new money."),
            ("Consider trimming", "existing exposure."),
            ("Revisit", "when the price trend turns up."),
        ]
    else:
        sub = "Not weak enough to sell &mdash; not strong enough to buy."
        actions = [
            ("Keep", "existing units; no need to exit here."),
            ("Don&rsquo;t add", "new money until the trend turns up."),
            ("Reassess", "if momentum improves or the price breaks down."),
        ]
    actions_html = "\n".join(
        '          <div class="action"><span class="tick">&#9646;</span>'
        f"<span><b>{verb}</b> {rest}</span></div>"
        for verb, rest in actions
    )
    return sub, actions_html


def build_why_items(primary, decision):
    items = []

    r1 = primary["Current Trailing Return 1M"]
    dd_1y = primary["Current Drawdown From 1Y High"]
    below_trend = primary["Current EMA 50/200 Gap"] < 0
    trend_clause = (
        "trading under its long-term trend line" if below_trend else "trading above its long-term trend line"
    )
    if r1 >= 0.02:
        title = "The price is rebounding"
        body = (
            f'Up <span class="stat-up">{pct(r1)}</span> over the past month, but still '
            f'<span class="stat-down">{pct(dd_1y)}</span> from its one-year high and {trend_clause}.'
            if dd_1y < -0.02
            else f'Up <span class="stat-up">{pct(r1)}</span> over the past month and near its one-year high, {trend_clause}.'
        )
    elif r1 <= -0.02:
        title = "The price is falling"
        body = (
            f'Down <span class="stat-down">{pct(r1)}</span> over the past month, '
            f'<span class="stat-down">{pct(dd_1y)}</span> from its one-year high and {trend_clause}.'
        )
    else:
        title = "The price is drifting sideways"
        body = (
            f"Little changed over the past month; "
            f'<span class="stat-down">{pct(dd_1y)}</span> from its one-year high and {trend_clause}.'
        )
    items.append((title, body))

    mom = primary["Self-Relative Momentum Percentile"]
    mom_ago = primary["Self-Relative Momentum Percentile 1M Ago"]
    mom_pct = f"{mom * 100:.0f}%"
    if mom < 0.40:
        title = "Momentum is recovering from weak levels" if mom - mom_ago >= 0.05 else "Momentum is unusually weak"
        body = f'Stronger right now than only <span class="stat-down">{mom_pct}</span> of its own five-year history'
    elif mom > 0.60:
        title = "Momentum is strong"
        body = f'Stronger right now than <span class="stat-up">{mom_pct}</span> of its own five-year history'
    else:
        title = "Momentum is middling"
        body = f"Stronger right now than <b>{mom_pct}</b> of its own five-year history"
    if abs(mom - mom_ago) >= 0.05:
        direction = "up" if mom > mom_ago else "down"
        body += f", {direction} from {mom_ago * 100:.0f}% a month ago"
    items.append((title, body + "."))

    expected = primary["Expected Forward Return"]
    median = primary["Median Forward Return"]
    period = HORIZON_ADJECTIVE.get(primary["Horizon"], str(primary["Horizon"]))
    median_clause = "the middle outcome is roughly flat" if abs(median) < 0.005 else f"the middle outcome is {pct(median)}"
    if decision == "BUY":
        title = "The payoff covers the risk"
        stat_class = "stat-up"
    elif decision == "SELL / AVOID":
        title = "The payoff doesn&rsquo;t cover the risk"
        stat_class = "stat-down"
    else:
        title = "The payoff doesn&rsquo;t argue for adding"
        stat_class = "stat-accent"
    body = (
        f"Expected {period} return of "
        f'<span class="{stat_class}">{pct(expected)}</span>, and {median_clause}.'
    )
    items.append((title, body))

    return "\n".join(
        '          <div class="why-item">\n'
        f"            <h3>{title}</h3>\n"
        f"            <p>{body}</p>\n"
        "          </div>"
        for title, body in items
    )


def build_takeaway(up_cells, down_cells, expected, median):
    if up_cells - down_cells >= 4:
        lead = "The good pile is bigger than the bad pile"
    elif down_cells - up_cells >= 4:
        lead = "The bad pile is bigger than the good pile"
    else:
        lead = "The good and bad piles are about the same size"
    median_clause = (
        "the middle outcome is roughly flat" if abs(median) < 0.005 else f"the middle outcome is {pct(median)}"
    )
    return (
        f"<b>{lead}</b> &mdash; the average of all 100 outcomes is <b>{pct(expected)}</b>, "
        f"and {median_clause}."
    )


def build_confidence(primary):
    level = str(primary["Confidence Level"]).upper()
    segments = CONFIDENCE_SEGMENTS.get(level, 1)
    seg_html = "".join(
        f'<span class="seg{" on" if i < segments else ""}"></span>' for i in range(3)
    )
    analogs = int(primary["Analog Count"])
    candidates = int(primary["Candidate Analog Count"])
    tip = (
        f"{analogs} independent look-alike episodes found among {candidates} candidate windows screened. "
        "More episodes would mean higher confidence."
    )
    return level, seg_html, analogs, candidates, tip


def build_horizon_data(rows):
    horizon_rows = []
    sr_rows = []
    for _, row in rows.iterrows():
        up = round(row["Probability >= Upside Target"] * 100)
        down = round(row["Probability <= Downside Risk"] * 100)
        name = horizon_phrase(row["Horizon"])
        horizon_rows.append(
            {
                "name": name,
                "note": f'target {pct(row["Upside Target"])} / risk {pct(row["Downside Risk"])}',
                "up": up,
                "down": down,
            }
        )
        sr_rows.append(
            f"        <tr><td>{name}</td><td>{up}%</td><td>{down}%</td></tr>"
        )
    max_value = max((max(r["up"], r["down"]) for r in horizon_rows), default=50)
    scale_max = max(50, int(math.ceil(max_value / 10.0)) * 10)
    return horizon_rows, "\n".join(sr_rows), scale_max


PAGE_TEMPLATE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$page_title</title>
<style>
  :root {
    --ground: #EDF0F2;
    --surface: #FFFFFF;
    --surface-2: #F5F7F8;
    --ink: #1B2530;
    --muted: #5A6674;
    --faint: #8B96A1;
    --hairline: #D9DFE4;
    --track: #E4E9ED;
    --up: #2C5F9E;
    --down: #B0392F;
    --hold: #9A6A1C;
    --chip-ink: #FFFFFF;
    --shadow: 0 18px 50px rgba(27, 37, 48, 0.10), 0 2px 8px rgba(27, 37, 48, 0.06);
    --serif: "Charter", "Bitstream Charter", "Sitka Text", Cambria, Georgia, serif;
    --sans: "Avenir Next", "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
    --accent: var($accent_var);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --ground: #0F141A;
      --surface: #181F27;
      --surface-2: #1E2731;
      --ink: #E7ECF1;
      --muted: #9AA6B2;
      --faint: #6E7B88;
      --hairline: #2C3742;
      --track: #2A333D;
      --up: #4E85C6;
      --down: #D06055;
      --hold: #C89144;
      --chip-ink: #10151B;
      --shadow: 0 18px 50px rgba(0, 0, 0, 0.45), 0 2px 8px rgba(0, 0, 0, 0.35);
    }
  }
  :root[data-theme="light"] {
    --ground: #EDF0F2;
    --surface: #FFFFFF;
    --surface-2: #F5F7F8;
    --ink: #1B2530;
    --muted: #5A6674;
    --faint: #8B96A1;
    --hairline: #D9DFE4;
    --track: #E4E9ED;
    --up: #2C5F9E;
    --down: #B0392F;
    --hold: #9A6A1C;
    --chip-ink: #FFFFFF;
    --shadow: 0 18px 50px rgba(27, 37, 48, 0.10), 0 2px 8px rgba(27, 37, 48, 0.06);
  }
  :root[data-theme="dark"] {
    --ground: #0F141A;
    --surface: #181F27;
    --surface-2: #1E2731;
    --ink: #E7ECF1;
    --muted: #9AA6B2;
    --faint: #6E7B88;
    --hairline: #2C3742;
    --track: #2A333D;
    --up: #4E85C6;
    --down: #D06055;
    --hold: #C89144;
    --chip-ink: #10151B;
    --shadow: 0 18px 50px rgba(0, 0, 0, 0.45), 0 2px 8px rgba(0, 0, 0, 0.35);
  }

  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    background: var(--ground);
    color: var(--ink);
    font-family: var(--sans);
    font-size: 15px;
    line-height: 1.45;
    -webkit-font-smoothing: antialiased;
  }

  .stage {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: clamp(12px, 3vw, 40px);
  }

  .slide {
    width: 100%;
    max-width: 1240px;
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: 6px;
    box-shadow: var(--shadow);
    padding: clamp(20px, 3.2vw, 44px) clamp(20px, 3.6vw, 52px) clamp(14px, 2vw, 22px);
    display: flex;
    flex-direction: column;
    gap: clamp(16px, 2.2vw, 26px);
  }

  .kicker-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 16px;
    flex-wrap: wrap;
  }
  .kicker {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .kicker b { color: var(--ink); font-weight: 700; }
  .datechip {
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    border: 1px solid var(--hairline);
    border-radius: 999px;
    padding: 4px 12px;
    white-space: nowrap;
  }

  .headline { max-width: 62ch; }
  .headline h1 {
    font-family: var(--serif);
    font-size: clamp(24px, 3.1vw, 38px);
    line-height: 1.16;
    font-weight: 700;
    margin: 0 0 10px;
    text-wrap: balance;
    letter-spacing: -0.01em;
  }
  .headline h1 .accent-word { color: var(--accent); }
  .headline p {
    margin: 0;
    color: var(--muted);
    font-size: clamp(14px, 1.3vw, 16px);
    max-width: 58ch;
  }

  .body-grid {
    display: grid;
    grid-template-columns: minmax(210px, 0.85fr) minmax(320px, 1.5fr) minmax(230px, 1fr);
    gap: clamp(16px, 2.4vw, 34px);
    align-items: stretch;
  }
  @media (max-width: 920px) {
    .body-grid { grid-template-columns: 1fr; }
  }

  .panel-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--faint);
    margin: 0 0 12px;
  }

  .verdict {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .verdict-chip {
    align-self: flex-start;
    background: var(--accent);
    color: var(--chip-ink);
    font-family: var(--serif);
    font-weight: 700;
    font-size: clamp(19px, 1.8vw, 24px);
    letter-spacing: 0.01em;
    padding: 10px 18px 11px;
    border-radius: 4px;
    line-height: 1.1;
  }
  .verdict-sub {
    font-size: 13.5px;
    color: var(--muted);
    margin: 0;
    max-width: 30ch;
  }
  .actions { display: flex; flex-direction: column; gap: 8px; margin-top: 2px; }
  .action {
    display: flex; gap: 10px; align-items: baseline;
    background: var(--surface-2);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    padding: 9px 12px;
    font-size: 13.5px;
  }
  .action .tick {
    font-weight: 700;
    color: var(--accent);
    flex: none;
    font-size: 12px;
  }
  .action b { font-weight: 600; }

  .odds { display: flex; flex-direction: column; }
  .odds-frame {
    display: flex;
    gap: clamp(16px, 2vw, 28px);
    align-items: stretch;
    flex: 1;
  }
  .waffle {
    display: grid;
    grid-template-columns: repeat(10, 1fr);
    gap: 4px;
    aspect-ratio: 1 / 1;
    width: min(100%, 320px);
    flex: none;
    align-self: center;
  }
  .cell {
    border-radius: 3px;
    background: var(--track);
    transition: transform 120ms ease;
  }
  .cell.up   { background: var(--up); }
  .cell.down { background: var(--down); }
  @media (prefers-reduced-motion: no-preference) {
    .cell { opacity: 0; animation: pop 300ms ease forwards; }
    @keyframes pop { from { opacity: 0; transform: scale(0.6); } to { opacity: 1; transform: scale(1); } }
  }

  .odds-legend {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 14px;
    min-width: 0;
  }
  @media (max-width: 680px) {
    .odds-frame { flex-direction: column; }
    .waffle { align-self: flex-start; width: min(100%, 340px); }
    .odds-legend { gap: 8px; }
    .odds-item .cap { max-width: none; }
  }
  .odds-item {
    display: grid;
    grid-template-columns: 14px 1fr;
    column-gap: 10px;
    row-gap: 2px;
    padding: 8px 10px;
    border-radius: 4px;
    cursor: default;
  }
  .odds-item .swatch {
    width: 14px; height: 14px; border-radius: 3px; margin-top: 5px;
    background: var(--track);
  }
  .odds-item.win  .swatch { background: var(--up); }
  .odds-item.loss .swatch { background: var(--down); }
  .odds-item .big {
    font-size: clamp(20px, 2vw, 26px);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1.15;
  }
  .odds-item.win  .big { color: var(--up); }
  .odds-item.loss .big { color: var(--down); }
  .odds-item .cap { grid-column: 2; font-size: 12.5px; color: var(--muted); max-width: 24ch; }
  .odds-takeaway {
    margin: 14px 0 0;
    font-size: 13px;
    color: var(--muted);
    border-top: 1px solid var(--hairline);
    padding-top: 10px;
    max-width: 60ch;
  }
  .odds-takeaway b { color: var(--ink); }

  .why { display: flex; flex-direction: column; }
  .why-list { display: flex; flex-direction: column; gap: 10px; flex: 1; }
  .why-item {
    border-left: 3px solid var(--hairline);
    padding: 2px 0 2px 12px;
  }
  .why-item h3 {
    margin: 0 0 2px;
    font-size: 14px;
    font-weight: 700;
  }
  .why-item p { margin: 0; font-size: 12.5px; color: var(--muted); }
  .why-item .stat-down, .why-item .stat-up, .why-item .stat-accent {
    font-variant-numeric: tabular-nums;
    font-weight: 700;
  }
  .why-item .stat-down { color: var(--down); }
  .why-item .stat-up { color: var(--up); }
  .why-item .stat-accent { color: var(--accent); }
  .confidence {
    margin-top: 14px;
    background: var(--surface-2);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    padding: 10px 12px;
    font-size: 12.5px;
    color: var(--muted);
  }
  .confidence .meter {
    display: flex; gap: 4px; margin: 7px 0 6px;
  }
  .confidence .seg {
    height: 6px; flex: 1; border-radius: 3px; background: var(--track);
  }
  .confidence .seg.on { background: var(--ink); }
  .confidence b { color: var(--ink); letter-spacing: 0.06em; }

  .horizons {
    border-top: 1px solid var(--hairline);
    padding-top: 14px;
  }
  .horizons-head {
    display: flex; justify-content: space-between; align-items: baseline;
    gap: 16px; flex-wrap: wrap; margin-bottom: 10px;
  }
  .horizons-head .panel-label { margin: 0; }
  .legend { display: flex; gap: 16px; font-size: 11.5px; color: var(--muted); }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .legend i {
    width: 10px; height: 10px; border-radius: 2px; display: inline-block;
  }
  .legend .li-up i { background: var(--up); }
  .legend .li-down i { background: var(--down); }

  .horizon-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: clamp(14px, 2vw, 28px);
  }
  .hz { display: grid; grid-template-columns: 84px 1fr; row-gap: 5px; column-gap: 12px; align-items: center; }
  .hz .hz-name {
    grid-row: span 2;
    font-size: 13px; font-weight: 700; line-height: 1.25;
  }
  .hz .hz-name small { display: block; font-weight: 400; color: var(--faint); font-size: 11px; }
  .bar { display: flex; align-items: center; gap: 8px; }
  .bar .rail {
    flex: 1; height: 10px; background: var(--track); border-radius: 3px; overflow: hidden;
    position: relative;
  }
  .bar .fill {
    height: 100%; border-radius: 3px 0 0 3px;
  }
  .bar.up .fill { background: var(--up); }
  .bar.down .fill { background: var(--down); }
  .bar .val {
    flex: none; width: 38px; text-align: right;
    font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums;
  }
  .bar.up .val { color: var(--up); }
  .bar.down .val { color: var(--down); }

  .slide-footer {
    border-top: 1px solid var(--hairline);
    padding-top: 10px;
    display: flex;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    font-size: 10.5px;
    color: var(--faint);
  }
  .slide-footer .pageno { font-variant-numeric: tabular-nums; white-space: nowrap; }

  .tip {
    position: fixed;
    z-index: 10;
    pointer-events: none;
    background: var(--ink);
    color: var(--surface);
    font-size: 12px;
    line-height: 1.35;
    padding: 7px 10px;
    border-radius: 4px;
    max-width: 260px;
    opacity: 0;
    transform: translateY(4px);
    transition: opacity 120ms ease, transform 120ms ease;
  }
  .tip.show { opacity: 1; transform: translateY(0); }
  [data-tip] { cursor: default; }
  [data-tip]:focus-visible { outline: 2px solid var(--up); outline-offset: 2px; border-radius: 4px; }

  .sr-only {
    position: absolute; width: 1px; height: 1px;
    clip: rect(0 0 0 0); clip-path: inset(50%); overflow: hidden; white-space: nowrap;
  }
</style>
</head>
<body>

<div class="stage">
  <div class="slide" role="figure" aria-label="Investment committee slide for the $fund_code fund. Recommendation: $chip_text.">

    <div class="kicker-row">
      <div class="kicker">Investment Committee &middot; Fund Review &mdash; <b>$fund_code &middot; $fund_name</b></div>
      <div class="datechip">Data through $data_through</div>
    </div>

    <div class="headline">
      <h1>$headline_h1</h1>
      <p>$headline_sub</p>
    </div>

    <div class="body-grid">

      <!-- Verdict -->
      <section class="verdict">
        <h2 class="panel-label">Recommendation</h2>
        <div class="verdict-chip">$chip_text</div>
        <p class="verdict-sub">$verdict_sub</p>
        <div class="actions">
$actions_html
        </div>
      </section>

      <!-- Odds waffle -->
      <section class="odds">
        <h2 class="panel-label">If the next $primary_period played out 100 times&hellip;</h2>
        <div class="odds-frame">
          <div class="waffle" id="waffle" role="img"
               aria-label="Out of 100 hypothetical $primary_period_adj outcomes: $win_n end in a gain of $upside_plain or more, $mid_n land in between, $loss_n end in a loss of $downside_plain or worse."></div>
          <div class="odds-legend">
            <div class="odds-item win" tabindex="0"
                 data-tip="Historical odds of gaining $upside_txt or more over the next $primary_period, given today&rsquo;s conditions: $upside_prob.">
              <span class="swatch"></span>
              <span class="big">$win_n end well</span>
              <span class="cap">a gain of <b>$upside_txt or more</b></span>
            </div>
            <div class="odds-item" tabindex="0"
                 data-tip="The remaining outcomes fall between the $upside_txt win line and the $downside_txt loss line.">
              <span class="swatch"></span>
              <span class="big" style="color: var(--muted);">$mid_n land in between</span>
              <span class="cap">neither a big win nor a big loss</span>
            </div>
            <div class="odds-item loss" tabindex="0"
                 data-tip="Historical odds of losing $downside_txt or worse over the next $primary_period, given today&rsquo;s conditions: $downside_prob.">
              <span class="swatch"></span>
              <span class="big">$loss_n end badly</span>
              <span class="cap">a loss of <b>$downside_txt or worse</b></span>
            </div>
          </div>
        </div>
        <p class="odds-takeaway">$takeaway</p>
      </section>

      <!-- Why -->
      <section class="why">
        <h2 class="panel-label">$why_label</h2>
        <div class="why-list">
$why_items
        </div>
        <div class="confidence" data-tip="$confidence_tip" tabindex="0">
          How sure are we? <b>$confidence_level</b>
          <div class="meter" aria-hidden="true">
            $confidence_meter
          </div>
          Based on the $analog_count past episodes that most resemble today, out of $candidate_count screened.
        </div>
      </section>
    </div>

    <!-- Horizon strip -->
    <section class="horizons">
      <div class="horizons-head">
        <h2 class="panel-label">The picture at every holding period we checked</h2>
        <div class="legend" aria-hidden="true">
          <span class="li-up"><i></i>Chance of a big gain</span>
          <span class="li-down"><i></i>Chance of a big loss</span>
        </div>
      </div>
      <div class="horizon-grid" id="horizonGrid"></div>
    </section>

    <table class="sr-only">
      <caption>Chance of a big gain versus a big loss by holding period</caption>
      <thead><tr><th>Holding period</th><th>Chance of big gain</th><th>Chance of big loss</th></tr></thead>
      <tbody>
$sr_rows
      </tbody>
    </table>

    <div class="slide-footer">
      <span>Source: fund_forward_decision.py ($method_name) &middot; $fund_label NAV, 5-yr total-return series &middot; Generated $generated_date</span>
      <span>Model output for discussion &mdash; not investment advice</span>
      <span class="pageno">1 / 1</span>
    </div>
  </div>
</div>

<div class="tip" id="tip" role="tooltip"></div>

<script>
  // ---- Waffle ----
  (function () {
    var waffle = document.getElementById('waffle');
    var counts = $waffle_json;
    var idx = 0;
    counts.forEach(function (grp) {
      for (var i = 0; i < grp.n; i++) {
        var c = document.createElement('div');
        c.className = 'cell' + (grp.cls ? ' ' + grp.cls : '');
        c.style.animationDelay = (idx * 6) + 'ms';
        c.setAttribute('data-tip', grp.tip);
        waffle.appendChild(c);
        idx++;
      }
    });
  })();

  // ---- Horizon paired bars ----
  (function () {
    var rows = $horizon_json;
    var max = $scale_max; // common scale so bars compare across horizons
    var grid = document.getElementById('horizonGrid');
    rows.forEach(function (r) {
      var el = document.createElement('div');
      el.className = 'hz';
      el.innerHTML =
        '<div class="hz-name">' + r.name + '<small>' + r.note + '</small></div>' +
        '<div class="bar up" data-tip="Chance of a big gain over ' + r.name + ': ' + r.up + '%">' +
          '<div class="rail"><div class="fill" style="width:' + (r.up / max * 100) + '%"></div></div>' +
          '<span class="val">' + r.up + '%</span></div>' +
        '<div class="bar down" data-tip="Chance of a big loss over ' + r.name + ': ' + r.down + '%">' +
          '<div class="rail"><div class="fill" style="width:' + (r.down / max * 100) + '%"></div></div>' +
          '<span class="val">' + r.down + '%</span></div>';
      grid.appendChild(el);
    });
  })();

  // ---- Tooltip ----
  (function () {
    var tip = document.getElementById('tip');
    function show(target, x, y) {
      var text = target.getAttribute('data-tip');
      if (!text) return;
      tip.innerHTML = text;
      tip.classList.add('show');
      position(x, y);
    }
    function position(x, y) {
      var pad = 14;
      var w = tip.offsetWidth, h = tip.offsetHeight;
      var left = Math.min(x + pad, window.innerWidth - w - 8);
      var top = y - h - pad;
      if (top < 8) top = y + pad;
      tip.style.left = left + 'px';
      tip.style.top = top + 'px';
    }
    function hide() { tip.classList.remove('show'); }

    document.addEventListener('mousemove', function (e) {
      var t = e.target.closest('[data-tip]');
      if (t) { show(t, e.clientX, e.clientY); } else { hide(); }
    });
    document.addEventListener('focusin', function (e) {
      var t = e.target.closest('[data-tip]');
      if (t) {
        var r = t.getBoundingClientRect();
        show(t, r.left + r.width / 2, r.top);
      }
    });
    document.addEventListener('focusout', hide);
    document.addEventListener('scroll', hide, true);
  })();
</script>

</body>
</html>
""")

INDEX_TEMPLATE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Committee Slides &mdash; Fund Review</title>
<style>
  :root {
    --ground: #EDF0F2; --surface: #FFFFFF; --ink: #1B2530; --muted: #5A6674;
    --hairline: #D9DFE4; --up: #2C5F9E; --down: #B0392F; --hold: #9A6A1C;
    --chip-ink: #FFFFFF;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --ground: #0F141A; --surface: #181F27; --ink: #E7ECF1; --muted: #9AA6B2;
      --hairline: #2C3742; --up: #4E85C6; --down: #D06055; --hold: #C89144;
      --chip-ink: #10151B;
    }
  }
  :root[data-theme="light"] {
    --ground: #EDF0F2; --surface: #FFFFFF; --ink: #1B2530; --muted: #5A6674;
    --hairline: #D9DFE4; --up: #2C5F9E; --down: #B0392F; --hold: #9A6A1C;
    --chip-ink: #FFFFFF;
  }
  :root[data-theme="dark"] {
    --ground: #0F141A; --surface: #181F27; --ink: #E7ECF1; --muted: #9AA6B2;
    --hairline: #2C3742; --up: #4E85C6; --down: #D06055; --hold: #C89144;
    --chip-ink: #10151B;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: clamp(16px, 4vw, 48px);
    background: var(--ground); color: var(--ink);
    font: 15px/1.45 "Avenir Next", "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
  }
  h1 {
    font-family: "Charter", "Bitstream Charter", "Sitka Text", Cambria, Georgia, serif;
    font-size: clamp(22px, 3vw, 32px); margin: 0 0 4px;
  }
  .sub { color: var(--muted); margin: 0 0 24px; font-size: 13.5px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; max-width: 1240px; }
  a.card {
    display: flex; flex-direction: column; gap: 10px;
    background: var(--surface); border: 1px solid var(--hairline); border-radius: 6px;
    padding: 14px 16px; text-decoration: none; color: var(--ink);
  }
  a.card:hover { border-color: var(--muted); }
  .card .head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .card .name { font-weight: 600; font-size: 14px; }
  .card .name small { display: block; font-weight: 400; color: var(--muted); font-size: 12px; }
  .card .stats {
    display: flex; gap: 14px; flex-wrap: wrap;
    border-top: 1px solid var(--hairline); padding-top: 8px;
    font-size: 11px; color: var(--muted);
  }
  .card .stats b {
    display: block; font-size: 13px; font-variant-numeric: tabular-nums; color: var(--ink);
  }
  .card .stats .gain b { color: var(--up); }
  .card .stats .loss b { color: var(--down); }
  .chip {
    flex: none; font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--chip-ink); border-radius: 999px; padding: 4px 10px;
  }
  .chip.buy { background: var(--up); }
  .chip.hold { background: var(--hold); }
  .chip.sell { background: var(--down); }
</style>
</head>
<body>
<h1>Committee Slides</h1>
<p class="sub">Generated $generated_date &middot; data through $data_through &middot; fund_forward_decision.py ($method_name)</p>
<div class="grid">
$cards
</div>
</body>
</html>
""")

CHIP_CLASS = {"BUY": "buy", "HOLD / WATCH": "hold", "SELL / AVOID": "sell"}


def render_fund(dash_row, fund_details, generated_date):
    fund_label = dash_row["Fund Label"]
    code, name = fund_code_and_name(fund_label)
    decision = dash_row["Decision Label"]
    chip_text, accent_var = DECISION_STYLE.get(decision, ("Hold / Watch", "--hold"))

    horizons = fund_details.sort_values("Horizon Days")
    primary = horizons[horizons["Horizon"] == dash_row["Horizon"]].iloc[0]
    period = horizon_phrase(primary["Horizon"])

    win_n, mid_n, loss_n = waffle_counts(
        primary["Probability >= Upside Target"], primary["Probability <= Downside Risk"]
    )
    upside_txt = pct(primary["Upside Target"], decimals=0)
    downside_txt = pct(primary["Downside Risk"], decimals=0)
    headline_h1, headline_sub = build_headline(decision, win_n, loss_n, primary["Horizon"])
    verdict_sub, actions_html = build_verdict(decision)
    why_items = build_why_items(primary, decision)
    conf_level, conf_meter, analog_count, candidate_count, conf_tip = build_confidence(primary)
    horizon_rows, sr_rows, scale_max = build_horizon_data(horizons)

    waffle_json = json.dumps(
        [
            {"n": win_n, "cls": "up", "tip": f"{win_n} in 100: a gain of {upside_txt} or more"},
            {"n": mid_n, "cls": "", "tip": f"{mid_n} in 100: somewhere in between"},
            {"n": loss_n, "cls": "down", "tip": f"{loss_n} in 100: a loss of {downside_txt} or worse"},
        ]
    )

    why_label = {
        "BUY": "Why the odds look good",
        "SELL / AVOID": "Why the odds look poor",
    }.get(decision, "Why hold rather than buy or sell")

    method_name = str(dash_row.get("Forward Method Version", "")).replace("_", "-").replace("dual-relative-v2", "dual-relative v2")

    return PAGE_TEMPLATE.substitute(
        page_title=f"{code} Fund Review — Committee Slide",
        accent_var=accent_var,
        fund_code=html.escape(code),
        fund_name=html.escape(name),
        fund_label=html.escape(str(fund_label)),
        data_through=display_date(dash_row["Latest Date"]),
        headline_h1=headline_h1,
        headline_sub=headline_sub,
        chip_text=chip_text,
        verdict_sub=verdict_sub,
        actions_html=actions_html,
        primary_period=period,
        primary_period_adj=HORIZON_ADJECTIVE.get(primary["Horizon"], str(primary["Horizon"])),
        win_n=win_n,
        mid_n=mid_n,
        loss_n=loss_n,
        upside_txt=upside_txt,
        downside_txt=downside_txt,
        upside_plain=f"{primary['Upside Target'] * 100:.0f} percent",
        downside_plain=f"{abs(primary['Downside Risk']) * 100:.0f} percent",
        upside_prob=pct_points(primary["Probability >= Upside Target"]),
        downside_prob=pct_points(primary["Probability <= Downside Risk"]),
        takeaway=build_takeaway(win_n, loss_n, primary["Expected Forward Return"], primary["Median Forward Return"]),
        why_label=why_label,
        why_items=why_items,
        confidence_level=conf_level,
        confidence_meter=conf_meter,
        confidence_tip=html.escape(conf_tip, quote=True),
        analog_count=analog_count,
        candidate_count=candidate_count,
        sr_rows=sr_rows,
        waffle_json=waffle_json,
        horizon_json=json.dumps(horizon_rows, ensure_ascii=False),
        scale_max=scale_max,
        method_name=html.escape(method_name),
        generated_date=generated_date,
    )


def main():
    args = parse_args()
    for path in (args.details, args.dashboard):
        if not path.exists():
            raise SystemExit(f"Missing {path} - run scripts/fund_forward_decision.py first (e.g. with --all).")

    details = pd.read_csv(args.details)
    dashboard = pd.read_csv(args.dashboard)
    if args.funds:
        prefixes = tuple(code.upper() for code in args.funds)
        dashboard = dashboard[dashboard["Fund Label"].str.upper().str.startswith(prefixes)]
        if dashboard.empty:
            raise SystemExit(f"No funds in {args.dashboard} match: {', '.join(args.funds)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    generated_date = date.today().strftime("%d %b %Y")

    cards = []
    for _, dash_row in dashboard.sort_values("Fund Label").iterrows():
        fund_label = dash_row["Fund Label"]
        fund_details = details[details["Fund Label"] == fund_label]
        if fund_details.empty:
            print(f"Skipping {fund_label}: no rows in details CSV.")
            continue
        page = render_fund(dash_row, fund_details, generated_date)
        out_path = args.output_dir / f"{fund_label}_committee_slide.html"
        out_path.write_text(page, encoding="utf-8")
        print(f"{dash_row['Decision Label']:>12}  {out_path}")

        code, name = fund_code_and_name(fund_label)
        chip_class = CHIP_CLASS.get(dash_row["Decision Label"], "hold")
        horizon = html.escape(str(dash_row["Horizon"]))
        cards.append(
            f'  <a class="card" href="{out_path.name}">\n'
            '    <span class="head">'
            f'<span class="name">{html.escape(code)}<small>{html.escape(name)}</small></span>'
            f'<span class="chip {chip_class}">{html.escape(dash_row["Decision Label"])}</span></span>\n'
            '    <span class="stats">'
            f'<span class="gain">Big gain ({horizon})<b>{pct_points(dash_row["Probability >= Upside Target"])}</b></span>'
            f'<span class="loss">Big loss ({horizon})<b>{pct_points(dash_row["Probability <= Downside Risk"])}</b></span>'
            f'<span>Expected ({horizon})<b>{pct(dash_row["Expected Forward Return"])}</b></span>'
            f'<span>Confidence<b>{html.escape(str(dash_row["Confidence Level"]))}</b></span>'
            '</span>\n'
            '  </a>'
        )

    if cards:
        index_path = args.output_dir / "index.html"
        index_path.write_text(
            INDEX_TEMPLATE.substitute(
                generated_date=generated_date,
                data_through=display_date(dashboard["Latest Date"].max()),
                method_name="dual-relative v2",
                cards="\n".join(cards),
            ),
            encoding="utf-8",
        )
        print(f"\nIndex: {index_path}")


if __name__ == "__main__":
    main()
