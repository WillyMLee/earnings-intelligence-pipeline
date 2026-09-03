#!/usr/bin/env python3
"""
Auto-trigger per-company pre-earnings deep-dive emails for coverage-universe
names reporting tomorrow.

Runs the afternoon before market open on the day before (cron target: report
date minus 1). For each coverage-universe ticker reporting tomorrow, fetches
a financial snapshot + runs deep research, LLM-synthesizes a structured
multi-section brief, renders it in the plain memo-style format, and sends via
AgentMail.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
WORKSPACE_ROOT = PROJECT_ROOT  # core/ and pipelines/ are now siblings under repo root
NY_TZ = ZoneInfo("America/New_York")

if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from core.stock_data import fetch_financial_snapshot  # noqa: E402
from core.research import run_research_query_cascade  # noqa: E402
from core.synthesis import (  # noqa: E402
    earnings_brief_delivery_issues,
    synthesize_earnings_brief_with_review,
    synthesize_pre_earnings_brief,
)
import agentmail_delivery  # noqa: E402
from earnings_archive import archive_pre_earnings_snapshot  # noqa: E402
from render_pre_earnings_deep_dive_email import (  # noqa: E402
    build_email_subject,
    create_email_message,
    parse_recipients,
    render_deep_dive_email,
    render_markdown_summary,
    save_email_message,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Auto-trigger pre-earnings deep-dive emails for tomorrow's reporters.")
    p.add_argument("--calendar-csv", required=True, help="Normalized earnings calendar CSV.")
    p.add_argument("--for-date", default="", help="YYYY-MM-DD override for 'today'. Defaults to today NY time.")
    p.add_argument("--watchlist", default="", help="Comma-separated coverage universe tickers.")
    p.add_argument("--output-dir", default="", help="Root output directory for artifacts.")
    p.add_argument("--draft-only", action="store_true", help="Build email artifacts without sending.")
    p.add_argument("--correction", action="store_true", help="Label the delivered email as a correction.")
    p.add_argument(
        "--dashboard-only",
        action="store_true",
        help="Analyze and archive focused site-only names without sending email.",
    )
    return p.parse_args()


def ensure_calendar_csv(path: str) -> None:
    # Cloudflare's command contract refreshes this before every scheduled run.
    # Keep this fallback for direct/local invocations instead of assuming a
    # different job populated the container filesystem.
    csv_path = Path(path)
    if csv_path.exists():
        return
    print(f"[pre-deep-dive] Calendar CSV not found at {csv_path}, fetching...", flush=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "fetch_earnings_calendar.py"), "--output", str(csv_path)],
        check=True,
    )


def _parse_date(s: str) -> date:
    return date.fromisoformat(s.split("T")[0])


def _next_business_day(today: date) -> date:
    candidate = today + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def quarter_label(d: date) -> str:
    m, y = d.month, d.year
    if m <= 3:
        return f"Q4 {y - 1}"
    if m <= 6:
        return f"Q1 {y}"
    if m <= 9:
        return f"Q2 {y}"
    return f"Q3 {y}"


def load_coverage_reporters(csv_path: str, target_date: date, watchlist: set) -> list:
    reporters = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("Ticker") or row.get("ticker") or "").strip().upper()
            date_str = (row.get("Report Date") or row.get("report date") or "").strip()
            if not ticker or not date_str:
                continue
            try:
                report_date = _parse_date(date_str)
            except ValueError:
                continue
            if report_date == target_date and ticker in watchlist:
                reporters.append({
                    "ticker": ticker,
                    "company": (row.get("Company Name") or row.get("company name") or ticker).strip(),
                    "report_time": (row.get("Report Time") or "").strip() or "TBD",
                })
    return reporters


def _resolve_watchlist(arg_watchlist: str) -> set:
    source = arg_watchlist.strip() or os.environ.get("EARNINGS_COVERAGE_UNIVERSE", "").strip()
    if source:
        return {t.strip().upper() for t in source.split(",") if t.strip()}
    try:
        from run_earnings_radar_automation import DEFAULT_COVERAGE_UNIVERSE  # type: ignore
        return {t.strip().upper() for t in DEFAULT_COVERAGE_UNIVERSE.split(",") if t.strip()}
    except Exception:
        return set()


def _fmt_billions(value: object, digits: int = 1) -> str:
    if not isinstance(value, (int, float)):
        return ""
    return f"${value / 1_000_000_000:,.{digits}f}B"


def _fmt_pct(value: object) -> str:
    if not isinstance(value, (int, float)):
        return ""
    return f"{value:+.0f}%"


def _build_key_figures(snap: dict, brief: dict) -> list[dict]:
    financials = brief.get("financials") or {}
    consensus = financials.get("revenue_consensus_usd") or snap.get("next_q_revenue_consensus")
    eps_consensus = financials.get("eps_consensus")
    prior_growth = _fmt_pct(snap.get("last_q_yoy_pct"))
    figures = [
        {"label": "Street revenue", "value": _fmt_billions(consensus)},
        {"label": "Street EPS", "value": f"${eps_consensus:.2f}" if isinstance(eps_consensus, (int, float)) else ""},
        {
            "label": "Prior qtr revenue",
            "value": " ".join(filter(None, [_fmt_billions(snap.get("last_q_revenue")), f"({prior_growth} YoY)" if prior_growth else ""])),
        },
        {"label": "TTM gross margin", "value": f"{snap['gross_margin_pct']:.1f}%" if isinstance(snap.get("gross_margin_pct"), (int, float)) else ""},
        {"label": "Price", "value": f"${snap['price']:,.2f}" if isinstance(snap.get("price"), (int, float)) else ""},
        {
            "label": "Market cap",
            "value": (
                f"${snap['market_cap_b'] / 1000:,.2f}T"
                if isinstance(snap.get("market_cap_b"), (int, float)) and snap["market_cap_b"] >= 1000
                else (f"${snap['market_cap_b']:,.1f}B" if isinstance(snap.get("market_cap_b"), (int, float)) else "")
            ),
        },
    ]
    return [item for item in figures if item["value"]]


def build_brief_context(reporter: dict, report_date: date, correction: bool = False) -> dict:
    ticker = reporter["ticker"]
    company = reporter["company"]
    quarter = quarter_label(report_date)

    print(f"[pre-deep-dive] Fetching financial snapshot for {ticker}...", flush=True)
    snap = fetch_financial_snapshot(ticker)
    try:
        archive_result = archive_pre_earnings_snapshot(ticker=ticker, report_date=report_date.isoformat(), snap=snap)
        if archive_result.get("status") != "archived":
            print(f"[pre-deep-dive] {ticker}: consensus archive skipped ({archive_result.get('reason')})", flush=True)
    except Exception as exc:
        print(f"[pre-deep-dive] {ticker}: consensus archive failed: {exc}", flush=True)

    facts = {
        "last_q_revenue": snap.get("last_q_revenue"),
        "last_q_revenue_label": snap.get("last_q_label"),
        "last_q_period_end": snap.get("last_q_period_end"),
        "last_q_yoy_pct": snap.get("last_q_yoy_pct"),
        "gross_margin_pct": snap.get("gross_margin_pct"),
        "next_q_revenue_consensus": snap.get("next_q_revenue_consensus"),
        "next_q_yoy_pct": snap.get("next_q_yoy_pct"),
        "next_q_expected_period_end": snap.get("next_q_expected_period_end"),
        "fy_revenue_consensus": snap.get("fy_revenue_consensus"),
        "fy_yoy_pct": snap.get("fy_yoy_pct"),
        "last_fy_capex_actual": snap.get("last_fy_capex_actual"),
        "last_fy_capex_period_end": snap.get("last_fy_capex_period_end"),
        "fy_capex_qtd_actual": snap.get("fy_capex_qtd_actual"),
        "fy_capex_qtd_quarters": snap.get("fy_capex_qtd_quarters"),
        "report_date": report_date.isoformat(),
        "report_time": reporter.get("report_time", ""),
        "price": snap.get("price"),
        "market_cap_b": snap.get("market_cap_b"),
        "enterprise_value_b": snap.get("enterprise_value_b"),
        "shares_outstanding": snap.get("shares_outstanding"),
    }

    # Primary: OpenAI's web_search tool researches and writes in one grounded
    # pass -- much higher figure density than pre-fetched short snippets.
    print(f"[pre-deep-dive] Synthesizing brief for {ticker} via web search...", flush=True)
    brief = synthesize_earnings_brief_with_review(ticker, company, quarter, "pre", facts)

    if not brief or not brief.get("sections"):
        # Fallback: our own research cascade + a plain synthesis call.
        print(f"[pre-deep-dive] Web search unavailable/empty for {ticker}, falling back to snippet research...", flush=True)
        r1 = run_research_query_cascade(
            query=f"{company} ({ticker}) {quarter} earnings preview guidance analyst expectations",
            max_results_per_provider=5,
        )
        r2 = run_research_query_cascade(
            query=f"{company} ({ticker}) prior quarter earnings results margins backlog growth",
            max_results_per_provider=5,
        )
        seen = set()
        snippets = []
        for item in r1.get("results", []) + r2.get("results", []):
            key = item.get("url") or item.get("title")
            if key and key not in seen:
                seen.add(key)
                snippets.append(item)
        brief = synthesize_pre_earnings_brief(ticker, company, quarter, facts, snippets)
        fallback_issues = earnings_brief_delivery_issues(brief, "pre", facts)
        brief = dict(brief)
        brief["_qa_approved"] = not fallback_issues
        brief["_qa_issues"] = fallback_issues

    if brief.get("_qa_approved") is False:
        issues = brief.get("_qa_issues") or ["unresolved factual review"]
        raise RuntimeError(f"delivery blocked by earnings QA: {'; '.join(str(issue) for issue in issues[:5])}")

    report_time_label = reporter.get("report_time", "TBD")

    # Prefer the model's own researched fiscal-quarter label over our
    # calendar-based guess -- quarter_label() assumes every company's fiscal
    # year matches the calendar, which is wrong for companies like Microsoft
    # (fiscal year ends in June). Using the wrong label in the title/prompt
    # anchor was observed live to confuse the synthesis into writing an
    # entirely retrospective brief instead of a forward-looking one.
    display_quarter = str(brief.get("fiscal_quarter_label") or "").strip() or quarter

    return {
        "ticker": ticker,
        "company": company,
        "quarter": display_quarter,
        "brief_label": "Correction: Pre-Earnings Summary" if correction else "Pre-Earnings Summary",
        "report_date_label": f"Reports {report_date.isoformat()} -- {report_time_label}",
        "intro": brief.get("intro", ""),
        "financial_highlights": brief.get("financial_highlights", []),
        "sections": brief.get("sections", []),
        "key_metrics": brief.get("key_metrics", []),
        "official_links": brief.get("official_links", {}),
        "key_figures": _build_key_figures(snap, brief),
        "estimate_comparisons": brief.get("estimate_comparisons", []),
        "valuation_reference": brief.get("valuation_reference", {}),
    }


def send_deep_dive(context: dict, output_dir: Path, draft_only: bool) -> bool:
    recipient = os.environ.get("DEAL_ALERT_EMAIL_TO", "").strip()
    if not recipient:
        print(f"[pre-deep-dive] {context['ticker']}: no DEAL_ALERT_EMAIL_TO set -- skipping send", flush=True)
        return False

    ticker_dir = output_dir / context["ticker"].lower()
    ticker_dir.mkdir(parents=True, exist_ok=True)

    html_body = render_deep_dive_email(context)
    markdown = render_markdown_summary(context)
    (ticker_dir / f"{context['ticker'].lower()}_deep_dive.html").write_text(html_body, encoding="utf-8")
    (ticker_dir / f"{context['ticker'].lower()}_deep_dive.md").write_text(markdown, encoding="utf-8")

    subject = build_email_subject(
        context["company"], context["ticker"], context["quarter"], context.get("brief_label", "Pre-Earnings Summary")
    )
    recipients = parse_recipients(recipient)
    sender = os.environ.get("EARNINGS_EMAIL_FROM", "earnings-bot@localhost")
    reply_to = os.environ.get("EARNINGS_EMAIL_REPLY_TO", "")
    message = create_email_message(subject, html_body, markdown, sender, recipients, reply_to)
    save_email_message(message, str(ticker_dir / f"{context['ticker'].lower()}_deep_dive.eml"))

    if draft_only:
        print(f"[pre-deep-dive] {context['ticker']}: drafted only", flush=True)
        return True

    api_key = os.environ.get("AGENTMAIL_API_KEY", "").strip()
    if not api_key:
        print(f"[pre-deep-dive] {context['ticker']}: no AGENTMAIL_API_KEY set -- skipping send", flush=True)
        return False
    try:
        inbox = agentmail_delivery.ensure_inbox(
            api_key=api_key,
            inbox_id=os.environ.get("AGENTMAIL_INBOX_ID", ""),
        )
        result = agentmail_delivery.send_message(
            api_key=api_key,
            inbox_id=str(inbox.get("inbox_id") or inbox.get("email", "")),
            to=recipients,
            subject=subject,
            text=markdown,
            html=html_body,
            reply_to=reply_to,
        )
        print(f"[pre-deep-dive] {context['ticker']}: sent (message_id={result.get('message_id')})", flush=True)
        return True
    except Exception as exc:
        print(f"[pre-deep-dive] {context['ticker']}: send failed: {exc}", flush=True)
        return False


def main() -> int:
    args = parse_args()
    today = _parse_date(args.for_date) if args.for_date else datetime.now(NY_TZ).date()
    tomorrow = _next_business_day(today)

    if args.dashboard_only:
        from core.coverage import dashboard_only_tickers

        watchlist = set(dashboard_only_tickers())
    else:
        watchlist = _resolve_watchlist(args.watchlist)
    if not watchlist:
        print("[pre-deep-dive] No watchlist resolved -- nothing to do", flush=True)
        return 0

    ensure_calendar_csv(args.calendar_csv)
    reporters = load_coverage_reporters(args.calendar_csv, tomorrow, watchlist)
    if not reporters:
        print(f"[pre-deep-dive] No coverage universe reporters on {tomorrow}", flush=True)
        return 0

    print(f"[pre-deep-dive] Found {len(reporters)} reporter(s) for {tomorrow}: {[r['ticker'] for r in reporters]}", flush=True)

    output_root = WORKSPACE_ROOT / "outputs" / "pre-earnings-deep-dive"
    output_dir = Path(args.output_dir) if args.output_dir else output_root / tomorrow.isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)

    succeeded = 0
    for reporter in reporters:
        try:
            context = build_brief_context(reporter, tomorrow, correction=args.correction)
            if send_deep_dive(context, output_dir, args.draft_only or args.dashboard_only):
                succeeded += 1
        except Exception as exc:
            print(f"[pre-deep-dive] {reporter['ticker']}: failed without blocking other reporters: {exc}", flush=True)

    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
