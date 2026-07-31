#!/usr/bin/env python3
"""
Build weekly earnings briefing context and markdown from an earnings calendar CSV.

Optional: merge ticker-level context notes from AgentMail JSON produced by
scripts/extract_agentmail_earnings.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%b %d, %Y",
    "%B %d, %Y",
]


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def find_col(headers: Sequence[str], aliases: Sequence[str]) -> Optional[str]:
    normalized = {normalize_key(h): h for h in headers}
    for alias in aliases:
        key = normalize_key(alias)
        if key in normalized:
            return normalized[key]
    return None


def parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    cleaned = value.strip()
    cleaned = cleaned.split("T")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    token = cleaned.split(" ")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def parse_percent(value: str) -> Optional[float]:
    if not value:
        return None
    match = re.search(r"[-+]?\d+(\.\d+)?", value.replace(",", ""))
    return float(match.group(0)) if match else None


def parse_market_cap_billions(value: str) -> Optional[float]:
    if not value:
        return None
    cleaned = value.strip().upper().replace(",", "")
    match = re.search(r"(\d+(\.\d+)?)", cleaned)
    if not match:
        return None
    number = float(match.group(1))
    if "T" in cleaned:
        return number * 1000.0
    if "B" in cleaned:
        return number
    if "M" in cleaned:
        return number / 1000.0
    if number > 1_000_000_000:
        return number / 1_000_000_000
    return number


def monday_of_week(anchor: date) -> date:
    return anchor - timedelta(days=anchor.weekday())


def parse_csv_list(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def average(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def truncate_text(value: str, limit: int = 200) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def enrich_market_caps(events: List["EarningsEvent"]) -> None:
    """Fill missing market_cap_b from yfinance for events in scope."""
    missing = [e for e in events if e.market_cap_b is None and e.ticker]
    if not missing:
        return
    try:
        import yfinance as yf  # type: ignore
        data = yf.Tickers(" ".join(e.ticker for e in missing))
        for event in missing:
            try:
                raw = (data.tickers.get(event.ticker) or data.tickers.get(event.ticker.upper()))
                if raw is None:
                    continue
                mcap = raw.info.get("marketCap") or 0
                if mcap > 0:
                    event.market_cap_b = round(mcap / 1_000_000_000, 2)
            except Exception:
                pass
    except Exception:
        pass


def enrich_financial_snapshots(events: List["EarningsEvent"]) -> None:
    """Fetch revenue/margin/guidance snapshots for coverage-universe events only
    (bounded set, unlike the full calendar) so the notable table can show real
    numbers instead of narrative research."""
    targets = [e for e in events if "coverage universe" in e.score_reasons.lower() and e.ticker]
    if not targets:
        return
    try:
        import sys
        workspace_root = Path(__file__).resolve().parents[2]
        if str(workspace_root) not in sys.path:
            sys.path.insert(0, str(workspace_root))
        from core.stock_data import fetch_financial_snapshot
    except Exception:
        return
    for event in targets:
        try:
            event.financial_snapshot = fetch_financial_snapshot(event.ticker)
            if event.market_cap_b is None and event.financial_snapshot.get("market_cap_b") is not None:
                event.market_cap_b = event.financial_snapshot["market_cap_b"]
        except Exception:
            pass


def enrich_notable_what_matters(events: List["EarningsEvent"]) -> None:
    """LLM-synthesize a grounded 'what matters' line for coverage-universe
    events, from a light research fetch + the financial snapshot already on
    the event. Skips silently (leaves what_matters blank) if no LLM key is
    configured -- callers should treat that as normal, not an error."""
    targets = [e for e in events if "coverage universe" in e.score_reasons.lower() and e.ticker]
    if not targets:
        return
    try:
        import os
        import sys
        workspace_root = Path(__file__).resolve().parents[2]
        if str(workspace_root) not in sys.path:
            sys.path.insert(0, str(workspace_root))
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            return
        from core.research import run_research_query_cascade
        from core.synthesis import synthesize_narrative
    except Exception:
        return

    for event in targets:
        try:
            query = f"{event.company} ({event.ticker}) {event.report_date.isoformat()} earnings preview what to watch"
            research = run_research_query_cascade(query=query, max_results_per_provider=2)
            snap = event.financial_snapshot or {}
            facts = {
                "report_date": event.report_date.isoformat(),
                "report_time": event.report_time,
                "last_q_revenue_label": snap.get("last_q_label"),
                "last_q_revenue_yoy_pct": snap.get("last_q_yoy_pct"),
                "gross_margin_pct": snap.get("gross_margin_pct"),
                "next_q_revenue_consensus_yoy_pct": snap.get("next_q_yoy_pct"),
                "fy_revenue_consensus_yoy_pct": snap.get("fy_yoy_pct"),
            }
            narrative = synthesize_narrative(
                ticker=event.ticker,
                company=event.company,
                context_label="Upcoming earnings preview",
                facts=facts,
                research_snippets=research.get("results", []),
            )
            event.what_matters = narrative.get("what_matters", "")
        except Exception:
            pass


def event_rank_key(event: "EarningsEvent") -> Tuple[int, int, int, int, int, str]:
    has_coverage = 1 if "coverage universe" in event.score_reasons.lower() else 0
    has_notes = 1 if event.agentmail_notes else 0
    has_time = 1 if event.report_time and event.report_time != "TBD" else 0
    has_eps = 1 if str(event.eps_estimate or "").strip() else 0
    return (
        event.score,
        has_coverage,
        has_notes,
        has_time,
        has_eps,
        event.ticker,
    )


@dataclass
class EarningsEvent:
    ticker: str
    company: str
    report_date: date
    report_time: str
    sector: str
    eps_estimate: str
    revenue_estimate: str
    implied_move_pct: Optional[float]
    market_cap_b: Optional[float]
    score: int = 0
    score_reasons: str = ""
    agentmail_notes: List[dict] = field(default_factory=list)
    research_hits: List[Dict[str, str]] = field(default_factory=list)
    priority_label: str = "Monitor"
    newsletter_digest: Dict[str, Any] = field(default_factory=dict)
    financial_snapshot: Dict[str, Any] = field(default_factory=dict)
    what_matters: str = ""


def load_agentmail_notes(path: Optional[str]) -> Dict[str, List[dict]]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    raw = payload.get("notes", {}) if isinstance(payload, dict) else {}
    out: Dict[str, List[dict]] = {}
    for ticker, items in raw.items():
        clean_ticker = str(ticker).upper().strip()
        if not re.fullmatch(r"[A-Z]{1,6}", clean_ticker):
            continue
        if isinstance(items, list):
            out[clean_ticker] = [item for item in items if isinstance(item, dict)]
    return out


def load_events(calendar_csv: str) -> Tuple[List[EarningsEvent], List[str]]:
    warnings: List[str] = []
    with open(calendar_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV is missing headers")

        ticker_col = find_col(reader.fieldnames, ["ticker", "symbol"])
        company_col = find_col(reader.fieldnames, ["company", "company name", "name"])
        date_col = find_col(
            reader.fieldnames, ["report date", "earnings date", "date", "earningsreportdate"]
        )
        if not ticker_col or not company_col or not date_col:
            raise ValueError(
                "CSV must contain ticker/symbol, company name, and report/earnings date columns"
            )

        time_col = find_col(
            reader.fieldnames, ["report time", "time", "session", "timing", "when"]
        )
        sector_col = find_col(reader.fieldnames, ["sector", "industry"])
        eps_col = find_col(
            reader.fieldnames, ["eps estimate", "eps est", "consensus eps", "eps"]
        )
        rev_col = find_col(
            reader.fieldnames,
            ["revenue estimate", "revenue est", "consensus revenue", "revenue"],
        )
        move_col = find_col(
            reader.fieldnames, ["implied move", "options implied move", "iv move"]
        )
        mcap_col = find_col(reader.fieldnames, ["market cap", "marketcap", "mkt cap"])

        events: List[EarningsEvent] = []
        for idx, row in enumerate(reader, start=2):
            ticker = (row.get(ticker_col) or "").strip().upper()
            # Normalize dual-class share notation used by Alpha Vantage:
            # MOG.A → MOG-A, BRK.B → BRK-B (Yahoo Finance / standard format)
            if "." in ticker:
                ticker = ticker.replace(".", "-")
            company = (row.get(company_col) or "").strip()
            report_date = parse_date(row.get(date_col, ""))
            if not ticker or not re.fullmatch(r"[A-Z]{1,6}(-[A-Z]{1,2})?", ticker):
                warnings.append(f"Row {idx}: invalid ticker '{row.get(ticker_col, '')}'")
                continue
            if not report_date:
                warnings.append(f"Row {idx}: invalid report date '{row.get(date_col, '')}'")
                continue
            events.append(
                EarningsEvent(
                    ticker=ticker,
                    company=company or "Unknown Company",
                    report_date=report_date,
                    report_time=(row.get(time_col, "") if time_col else "").strip() or "TBD",
                    sector=(row.get(sector_col, "") if sector_col else "").strip(),
                    eps_estimate=(row.get(eps_col, "") if eps_col else "").strip(),
                    revenue_estimate=(row.get(rev_col, "") if rev_col else "").strip(),
                    implied_move_pct=parse_percent(row.get(move_col, "")) if move_col else None,
                    market_cap_b=parse_market_cap_billions(row.get(mcap_col, "")) if mcap_col else None,
                )
            )
    return events, warnings


def score_events(
    events: List[EarningsEvent],
    agentmail_notes: Dict[str, List[dict]],
    watchlist: List[str],
    focus_sectors: List[str],
) -> None:
    watch = {item.upper() for item in watchlist}
    sector_focus = {item.lower() for item in focus_sectors}
    for event in events:
        score = 0
        reasons: List[str] = []

        if event.market_cap_b is not None:
            if event.market_cap_b >= 200:
                score += 5
                reasons.append("bellwether scale")
            elif event.market_cap_b >= 100:
                score += 4
                reasons.append("large cap")
            elif event.market_cap_b >= 50:
                score += 3
                reasons.append("major company")
            elif event.market_cap_b >= 10:
                score += 2
                reasons.append("mid-cap+")
            elif event.market_cap_b >= 2:
                score += 1
                reasons.append("small-cap+")

        # Cap implied-move contribution at +1 so small high-IV names
        # don't crowd out large-cap coverage universe names
        if event.implied_move_pct is not None and event.implied_move_pct >= 10:
            score += 1
            reasons.append("high implied move")

        if event.ticker in watch:
            score += 5  # elevated so coverage universe always ranks above non-universe peers
            reasons.append("coverage universe")

        if event.sector and event.sector.lower() in sector_focus:
            score += 1
            reasons.append("coverage theme")

        event.agentmail_notes = list(agentmail_notes.get(event.ticker, []) or [])
        if event.agentmail_notes:
            score += 2
            reasons.append("AgentMail context")

        event.score = score
        event.score_reasons = ", ".join(reasons) if reasons else "baseline"


def format_cell(value: Optional[str]) -> str:
    return value if value else "-"


def event_priority_label(event: EarningsEvent) -> str:
    if event.score >= 9:
        return "KEY READ-THROUGH"
    if event.score >= 6:
        return "INDUSTRY SIGNAL"
    if event.score >= 3:
        return "MONITOR"
    return "LOWER SIGNAL"


def sector_watch_items(sector: str) -> List[str]:
    lower = str(sector or "").lower()
    if "semi" in lower:
        return [
            "AI accelerator demand, supply tightness, and margin mix",
            "Advanced packaging, memory, and equipment-cycle read-throughs",
        ]
    if "software" in lower:
        return [
            "Vertical workflow demand, retention, and AI monetization",
            "Bookings, seat growth, and sales-cycle commentary",
        ]
    if "cloud" in lower or "data" in lower:
        return [
            "AI capacity demand, utilization, and capex intensity",
            "Power, networking, GPU availability, and customer concentration",
        ]
    if "logistics" in lower or "industrial" in lower:
        return [
            "Volume trends, pricing, and cost discipline",
            "Macro demand commentary and margin protection",
        ]
    return [
        "Management tone on demand durability and the next-quarter guide",
        "Any KPI, margin, or capex commentary with sector read-through",
    ]


def build_event_digest(event: EarningsEvent) -> Dict[str, Any]:
    note_texts = [
        truncate_text(str(item.get("note", "")).strip(), 180)
        for item in event.agentmail_notes
        if str(item.get("note", "")).strip()
    ]
    research_snippets = [
        truncate_text(str(item.get("snippet", "")).strip(), 180)
        for item in event.research_hits
        if str(item.get("snippet", "")).strip()
    ]
    summary = (
        note_texts[:1]
        or research_snippets[:1]
        or [f"{event.company} reports this period and may add useful market read-through for Example Fund coverage areas."]
    )
    read_through = (
        research_snippets[:1]
        or note_texts[1:2]
        or [f"Relevance is driven by {event.score_reasons or 'calendar placement'}."]
    )
    what_to_watch = note_texts[1:3] or sector_watch_items(event.sector)
    market_cap_label = (
        f"{event.market_cap_b:.0f}B market cap"
        if event.market_cap_b is not None and event.market_cap_b < 1000
        else (f"{event.market_cap_b / 1000:.2f}T market cap" if event.market_cap_b is not None else "market cap not listed")
    )
    implied_move_label = (
        f"{event.implied_move_pct:.1f}% implied move"
        if event.implied_move_pct is not None
        else "implied move not listed"
    )

    return {
        "section_label": "MARKET TRENDS / EARNINGS READ-THROUGH",
        "headline": f"{event.ticker} - {event.company} reports {event.report_date.isoformat()} ({event.report_time})",
        "summary": summary[0],
        "view": f"{market_cap_label}; {implied_move_label}; reasons: {event.score_reasons}.",
        "read_through": read_through[0],
        "implication_label": event.priority_label,
        "implication_text": f"This report ranks {event.score} on the Example Fund market-intelligence signal score.",
        "watch_items": what_to_watch[:3],
    }


def group_notable_by_weekday(
    events: List[EarningsEvent], week_start: date, today: Optional[date] = None
) -> List[Dict[str, Any]]:
    """Group coverage-universe events by weekday (Monday-Friday) for the daily
    radar's compact table. Only coverage-universe names are included -- this is
    a notable list, not a full calendar dump.

    This radar is pre-earnings only: today's Before Open reporters have
    already printed by the time this sends (9:30am ET), so their pre-earnings
    "what to expect" estimates are stale and belong in the post-earnings
    digest instead, not here -- mixing the two reads as confusing/wrong."""
    by_day: Dict[date, List[EarningsEvent]] = {}
    for event in events:
        if "coverage universe" not in event.score_reasons.lower():
            continue
        if today and event.report_date == today and event.report_time.strip().lower().startswith("before"):
            continue
        by_day.setdefault(event.report_date, []).append(event)

    sections: List[Dict[str, Any]] = []
    for offset in range(5):
        day = week_start + timedelta(days=offset)
        # Biggest names first -- market cap is what a reader actually scans
        # for, not the internal signal score. Missing market cap sorts last
        # rather than erroring; ticker is only a tiebreak.
        day_events = sorted(
            by_day.get(day, []),
            key=lambda e: (e.market_cap_b is None, -(e.market_cap_b or 0), e.ticker),
        )
        sections.append({
            "date": day,
            "weekday_label": day.strftime("%A"),
            "date_label": f"{day.strftime('%b')} {day.day}",
            "events": day_events,
        })
    return sections


def build_weekly_context(
    events: List[EarningsEvent],
    top_n: int,
    week_start: date,
    week_end: date,
    agentmail_notes: Dict[str, List[dict]],
    warnings: List[str],
    notable_count: int = 5,
    title: str = "",
    is_daily: bool = False,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    ranked = sorted(events, key=lambda e: event_rank_key(e), reverse=True)
    for event in ranked:
        event.agentmail_notes = list(agentmail_notes.get(event.ticker, []) or [])
        event.priority_label = event_priority_label(event)
        event.newsletter_digest = build_event_digest(event)

    top = ranked[:top_n]
    # Detailed read-through section: only show coverage universe names or
    # tickers with AgentMail context — never surface random micro/small-caps
    notable_candidates = [
        event
        for event in ranked
        if "coverage universe" in event.score_reasons.lower()
        or event.agentmail_notes
    ]
    # Fallback: large-cap non-universe names (≥10B) if nothing else available
    secondary_candidates = [
        event
        for event in ranked
        if event not in notable_candidates
        and (event.market_cap_b or 0) >= 10
    ]
    if notable_candidates:
        notable = notable_candidates[: max(1, notable_count)]
    elif secondary_candidates:
        notable = secondary_candidates[: max(1, notable_count)]
    else:
        notable = ranked[: max(1, notable_count)] if ranked else []
    avg_implied = average([event.implied_move_pct for event in events if event.implied_move_pct is not None])
    focus_sectors = sorted({event.sector for event in events if event.sector})[:4]
    coverage_hits = len([event for event in events if "coverage universe" in event.score_reasons.lower()])

    highlights: List[Dict[str, str]] = []
    for ticker in sorted(agentmail_notes):
        for item in agentmail_notes[ticker]:
            note = str(item.get("note", "")).strip()
            if not note:
                continue
            highlights.append(
                {
                    "ticker": ticker,
                    "priority": str(item.get("priority", "unspecified")).strip() or "unspecified",
                    "note": note,
                    "source": str(item.get("source", "")).strip(),
                }
            )

    report_title = title.strip() or ("Daily Earnings Radar" if is_daily else "Weekly Earnings Radar")
    today = today or week_start
    # Full, uncapped coverage-universe list grouped by day -- used by both
    # modes now. Daily's window is a single day, so this naturally reduces to
    # "today only"; weekly's window is the full upcoming week, so this is the
    # comprehensive view nothing should silently drop out of (unlike
    # notable_events below, which is capped to notable_count for the
    # narrative section).
    notable_by_weekday = group_notable_by_weekday(events, week_start, today)
    coverage_event_count = sum(len(section["events"]) for section in notable_by_weekday)

    return {
        "title": report_title,
        "is_daily": is_daily,
        "today": today,
        "week_start": week_start,
        "week_end": week_end,
        "generated_at": datetime.now(),
        "events": events,
        "ranked_events": ranked,
        "top_events": top,
        "notable_events": notable,
        "notable_by_weekday": notable_by_weekday,
        "agentmail_notes": agentmail_notes,
        "agentmail_highlights": highlights,
        "warnings": warnings,
        "summary_cards": [
            {"label": "Notable This Week" if is_daily else "Events This Week", "value": str(coverage_event_count) if is_daily else str(len(events)), "note": "Coverage-universe reporters" if is_daily else "Calendar entries in scope"},
            {"label": "Market Signals", "value": str(len(notable)), "note": "Reports with useful read-through"},
            {"label": "Avg. Implied Move", "value": f"{avg_implied:.1f}%" if avg_implied is not None else "N/A", "note": "Among names with options context"},
            {"label": "Coverage Hits", "value": str(coverage_hits), "note": "Names in Example Fund coverage universe"},
        ],
        "focus_sectors": focus_sectors,
    }


def build_markdown(
    events: List[EarningsEvent],
    top_n: int,
    week_start: date,
    week_end: date,
    agentmail_notes: Dict[str, List[dict]],
    warnings: List[str],
) -> str:
    context = build_weekly_context(
        events=events,
        top_n=top_n,
        week_start=week_start,
        week_end=week_end,
        agentmail_notes=agentmail_notes,
        warnings=warnings,
    )
    lines: List[str] = []
    lines.append(f"# {context['title']}")
    lines.append("")
    lines.append(f"- Week: {week_start.isoformat()} to {week_end.isoformat()}")
    lines.append(f"- Generated: {context['generated_at'].strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("- Signal scoring: Example Fund market-intelligence heuristic")
    lines.append("")

    top = context["top_events"]
    lines.append(f"## Key Earnings Signals (Top {len(top)})")
    lines.append("")
    lines.append(
        "| Date | Time | Ticker | Company | Score | EPS Est | Revenue Est | Notes | Reasons |"
    )
    lines.append("|---|---|---|---|---:|---|---|---|---|")
    for event in top:
        note_flag = "Yes" if event.agentmail_notes else "No"
        lines.append(
            "| {date} | {time} | {ticker} | {company} | {score} | {eps} | {rev} | {notes} | {reasons} |".format(
                date=event.report_date.isoformat(),
                time=format_cell(event.report_time),
                ticker=event.ticker,
                company=event.company.replace("|", "/"),
                score=event.score,
                eps=format_cell(event.eps_estimate),
                rev=format_cell(event.revenue_estimate),
                notes=note_flag,
                reasons=event.score_reasons.replace("|", "/"),
            )
        )
    if not top:
        lines.append("| - | - | - | - | - | - | - | - | - |")
    lines.append("")

    notable = context["notable_events"]
    if notable:
        lines.append("## Market Read-Throughs")
        lines.append("")
        for event in notable:
            digest = event.newsletter_digest or {}
            lines.append(f"### {event.ticker} - {event.company}")
            lines.append(f"- Summary: {digest.get('summary', '')}")
            lines.append(f"- View: {digest.get('view', '')}")
            lines.append(f"- Read-Through: {digest.get('read_through', '')}")
            lines.append(
                f"- Implication: {digest.get('implication_label', '')} - {digest.get('implication_text', '')}"
            )
            for item in digest.get("watch_items", [])[:3]:
                lines.append(f"- What to Watch: {item}")
            lines.append("")

    lines.append("## Full Weekly Calendar")
    lines.append("")
    lines.append("| Date | Time | Ticker | Company | Sector |")
    lines.append("|---|---|---|---|---|")
    for event in sorted(events, key=lambda e: (e.report_date, e.ticker)):
        lines.append(
            "| {date} | {time} | {ticker} | {company} | {sector} |".format(
                date=event.report_date.isoformat(),
                time=format_cell(event.report_time),
                ticker=event.ticker,
                company=event.company.replace("|", "/"),
                sector=format_cell(event.sector).replace("|", "/"),
            )
        )
    if not events:
        lines.append("| - | - | - | No earnings found in selected week | - |")
    lines.append("")

    lines.append("## AgentMail Highlights")
    lines.append("")
    if context["agentmail_highlights"]:
        for item in context["agentmail_highlights"]:
            lines.append(
                f"- {item['ticker']} ({item['priority']}): {item['note']} [{item['source']}]"
            )
    else:
        lines.append("- No AgentMail notes provided.")
    lines.append("")

    lines.append("## Data Gaps and Warnings")
    lines.append("")
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- No data warnings.")
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build weekly key earnings markdown brief.")
    parser.add_argument("--calendar-csv", required=True, help="Path to earnings calculator CSV export.")
    parser.add_argument("--agentmail-json", help="Path to AgentMail notes JSON.")
    parser.add_argument("--output", required=True, help="Output markdown file path.")
    parser.add_argument("--week-start", help="Week start date (YYYY-MM-DD). Default: current week Monday.")
    parser.add_argument("--week-end", help="Week end date (YYYY-MM-DD). Default: week-start + 6 days.")
    parser.add_argument("--watchlist", default="", help="Comma-separated coverage universe tickers.")
    parser.add_argument("--focus-sectors", default="", help="Comma-separated coverage themes/sectors.")
    parser.add_argument("--top-n", type=int, default=15, help="Top N key names to show.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.week_start:
        start = parse_date(args.week_start)
        if not start:
            print(f"[ERROR] Invalid --week-start date: {args.week_start}")
            return 1
    else:
        start = monday_of_week(date.today())

    if args.week_end:
        end = parse_date(args.week_end)
        if not end:
            print(f"[ERROR] Invalid --week-end date: {args.week_end}")
            return 1
    else:
        end = start + timedelta(days=6)

    if end < start:
        print("[ERROR] --week-end must be on or after --week-start.")
        return 1

    events, warnings = load_events(args.calendar_csv)
    week_events = [event for event in events if start <= event.report_date <= end]
    agentmail_notes = load_agentmail_notes(args.agentmail_json)

    print(f"[build] Enriching market caps for {len(week_events)} events via yfinance...", flush=True)
    enrich_market_caps(week_events)

    score_events(
        week_events,
        agentmail_notes=agentmail_notes,
        watchlist=parse_csv_list(args.watchlist),
        focus_sectors=parse_csv_list(args.focus_sectors),
    )

    report = build_markdown(
        events=week_events,
        top_n=max(1, args.top_n),
        week_start=start,
        week_end=end,
        agentmail_notes=agentmail_notes,
        warnings=warnings,
    )

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[OK] Wrote weekly earnings brief: {args.output} ({len(week_events)} events)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
