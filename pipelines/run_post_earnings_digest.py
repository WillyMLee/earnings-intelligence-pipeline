#!/usr/bin/env python3
"""
Post-earnings outcomes digest -- runs twice a day, each covering only
same-day, freshly-reacted reporters instead of mixing session ages:
  - Morning (--session bmo, ~10am ET): today's Before Open reporters,
    processed by the 9:30am morning-post-earnings cron half an hour earlier.
  - Evening (--session amc, ~7:30pm ET): today's After Close/TBD reporters,
    processed by the 6pm evening cron ~90 minutes earlier.

This split exists because a single once-daily digest that mixed "today's
BMO" with "yesterday's AMC" (the original design) showed a reaction
percentage for AMC reporters that was frozen at whatever moment the prior
evening's per-company cron happened to run -- stale by the time anyone read
it the next morning, and wrong in a way that varied with how much the stock
moved overnight. Each digest run now also re-fetches a LIVE reaction
percentage at send time (via fetch_live_reaction_move, session-aware per
yfinance's own marketState) rather than trusting the archived snapshot, so
the number shown always reflects the actual market state when the email is
read, not when the underlying per-company brief was generated.

--session all (the original default) is kept for manual/ad-hoc use and
combines today's BMO with the prior business day's AMC, matching the
pre-split behavior.

Reuses each per-company deep dive's already-reviewed/sanity-checked summary
for company/key_metrics data (not re-fetching or re-synthesizing that part)
-- keeps this digest consistent with the detailed emails and avoids
duplicate API/LLM cost. Falls back to a fresh, cheap reaction-only lookup
(no LLM) if a summary file is missing, so a gap in one company's earlier run
doesn't drop it from the digest entirely.
"""

from __future__ import annotations

import argparse
import csv
import json
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

from core.stock_data import fetch_financial_snapshot, fetch_live_reaction_move  # noqa: E402
import agentmail_delivery  # noqa: E402
from earnings_archive import fetch_post_earnings_summaries_by_date, fetch_post_earnings_summary  # noqa: E402
from run_post_earnings_deep_dive_auto import (  # noqa: E402
    load_coverage_reporters,
    _matches_session,
    _resolve_watchlist,
    ensure_calendar_csv,
)
from render_weekly_earnings_email import (  # noqa: E402
    render_post_earnings_digest_email,
    create_email_message,
    save_email_message,
    parse_recipients,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Send the post-earnings outcomes digest.")
    p.add_argument("--calendar-csv", required=True, help="Normalized earnings calendar CSV.")
    p.add_argument("--for-date", default="", help="YYYY-MM-DD override for 'today'. Defaults to today NY time.")
    p.add_argument("--watchlist", default="", help="Comma-separated coverage universe tickers.")
    p.add_argument("--draft-only", action="store_true", help="Build the digest artifact without sending.")
    p.add_argument(
        "--session",
        choices=["all", "bmo", "amc"],
        default="all",
        help=(
            "'bmo' -- today's Before Open reporters only (morning run). 'amc' -- today's After "
            "Close/TBD reporters only (evening run). 'all' -- the original combined behavior: "
            "today's BMO plus the prior business day's AMC (manual/ad-hoc use)."
        ),
    )
    return p.parse_args()


def _parse_date(s: str) -> date:
    return date.fromisoformat(s.split("T")[0])


def prior_business_day(today: date) -> date:
    # Monday -> prior Friday (skip the weekend, no market activity then).
    delta = 3 if today.weekday() == 0 else 1
    return today - timedelta(days=delta)


def _summary_path(root: Path, date_dir: str, ticker: str) -> Path:
    return root / date_dir / ticker.lower() / f"{ticker.lower()}_summary.json"


def _basic_fact_bullets(ticker: str, company: str) -> List[str]:
    """Cheap, deterministic baseline facts (no LLM) for a reporter whose full
    reviewed brief isn't available yet -- so the digest always shows at least
    something concrete per company instead of a bare reaction percentage."""
    try:
        snap = fetch_financial_snapshot(ticker)
    except Exception as exc:
        print(f"[digest] {ticker}: financial snapshot fetch failed ({exc})", flush=True)
        return []
    bullets: List[str] = []
    price = snap.get("price")
    mcap = snap.get("market_cap_b")
    if price is not None or mcap is not None:
        parts = []
        if price is not None:
            parts.append(f"Price ${price:,.2f}")
        if mcap is not None:
            parts.append(f"market cap ${mcap:,.0f}B" if mcap < 1000 else f"market cap ${mcap / 1000:.1f}T")
        bullets.append(", ".join(parts))
    revenue = snap.get("last_q_revenue")
    yoy = snap.get("last_q_yoy_pct")
    if revenue is not None:
        billions = revenue / 1_000_000_000
        yoy_str = f", {yoy:+.0f}% YoY" if yoy is not None else ""
        bullets.append(f"Prior-quarter revenue: ${billions:,.1f}B{yoy_str}")
    return bullets


def _fresh_reaction_pct(ticker: str, company: str, report_time: str, fallback: "float | None") -> "float | None":
    """Re-fetch a LIVE reaction percentage at digest-send time instead of
    trusting whatever was archived when the per-company brief ran -- caught
    live: a reaction percentage frozen at 6pm (right after an after-close
    print) is materially different from the settled premarket/regular-session
    number by the time a digest reader actually sees it the next morning, and
    the gap varies unpredictably with how much the stock kept moving
    overnight. Falls back to the archived value if the live fetch fails, so a
    transient yfinance issue doesn't blank out a card that already had data."""
    try:
        move = fetch_live_reaction_move(ticker, report_time=report_time, company=company)
        pct = move.get("ah_move_pct")
        if pct is not None:
            return pct
    except Exception as exc:
        print(f"[digest] {ticker}: live reaction refresh failed ({exc}), using archived value", flush=True)
    return fallback


def load_digest_item(reporter: dict, report_date: str, summary_root: Path, date_dir: str) -> dict:
    ticker = reporter["ticker"]
    company = reporter["company"]

    # Primary: Convex, since Render cron services never share a filesystem --
    # the local file below only exists when this script happens to run in
    # the same environment that wrote it (local testing), not in production.
    convex_data = fetch_post_earnings_summary(ticker, report_date)
    if convex_data:
        report_time = convex_data.get("reportTime", reporter.get("report_time", ""))
        return {
            "ticker": convex_data.get("ticker", ticker),
            "company": convex_data.get("company", company),
            "report_time": report_time,
            "reaction_pct": _fresh_reaction_pct(ticker, company, report_time, convex_data.get("reactionPct")),
            "key_metrics": convex_data.get("keyMetrics", []),
        }

    path = _summary_path(summary_root, date_dir, ticker)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            report_time = data.get("report_time", reporter.get("report_time", ""))
            return {
                "ticker": data.get("ticker", ticker),
                "company": data.get("company", company),
                "report_time": report_time,
                "reaction_pct": _fresh_reaction_pct(ticker, company, report_time, data.get("reaction_pct")),
                "key_metrics": data.get("key_metrics", []),
            }
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[digest] {ticker}: failed to read persisted summary ({exc}), falling back", flush=True)

    # Final fallback: the per-company deep dive either hasn't run yet or its
    # send/archive failed. Reaction % (no LLM) plus cheap baseline facts (no
    # LLM) keep this ticker visible with at least some real content instead
    # of an empty card.
    print(f"[digest] {ticker}: no Convex or local summary found, using baseline facts", flush=True)
    move = fetch_live_reaction_move(ticker, report_time=reporter.get("report_time", ""), company=company)
    return {
        "ticker": ticker,
        "company": company,
        "report_time": reporter.get("report_time", ""),
        "reaction_pct": move.get("ah_move_pct"),
        "key_metrics": _basic_fact_bullets(ticker, company),
    }


def load_amc_items_for_date(target_day: date, watchlist: set) -> List[dict]:
    """Source a given day's After Close/TBD reporters straight from Convex's
    archive instead of the rolling earnings-calendar CSV, which drops dates
    as they age out of its window -- Convex is the durable record of who was
    actually processed that day. Used both for the same-day evening digest
    (target_day = today) and the legacy --session all combined digest
    (target_day = prior business day)."""
    rows = fetch_post_earnings_summaries_by_date(target_day.isoformat())
    items = []
    for row in rows:
        ticker = row.get("ticker", "")
        if ticker not in watchlist:
            continue
        report_time = row.get("reportTime", "")
        if not _matches_session(report_time, "amc"):
            continue
        company = row.get("company", ticker)
        items.append({
            "ticker": ticker,
            "company": company,
            "report_time": report_time,
            "reaction_pct": _fresh_reaction_pct(ticker, company, report_time, row.get("reactionPct")),
            "key_metrics": row.get("keyMetrics", []),
        })
    return items


def main() -> int:
    args = parse_args()
    today = _parse_date(args.for_date) if args.for_date else datetime.now(NY_TZ).date()
    prior_day = prior_business_day(today)

    watchlist = _resolve_watchlist(args.watchlist)
    if not watchlist:
        print("[digest] No watchlist resolved -- nothing to do", flush=True)
        return 0

    ensure_calendar_csv(args.calendar_csv)

    summary_root = WORKSPACE_ROOT / "outputs" / "post-earnings-deep-dive"
    items: List[dict] = []
    label = "Daily"

    if args.session in ("bmo", "all"):
        # Today's Before Open reporters: sourced from the calendar (still
        # fresh for "today"), enriched per-ticker from Convex/local/fallback,
        # reaction refreshed live at send time.
        bmo_reporters = load_coverage_reporters(args.calendar_csv, today, watchlist, session="bmo")
        bmo_items = [
            load_digest_item(r, today.isoformat(), summary_root, f"{today.isoformat()}-bmo")
            for r in bmo_reporters
        ]
        items += bmo_items
        print(f"[digest] {len(bmo_items)} BMO reporter(s) today ({today})", flush=True)
        if args.session == "bmo":
            label = "Morning"

    if args.session == "amc":
        # Today's After Close/TBD reporters, sourced from Convex (the
        # evening cron ~90 minutes earlier archived them under today's
        # date), reaction refreshed live at send time.
        amc_items = load_amc_items_for_date(today, watchlist)
        items += amc_items
        print(f"[digest] {len(amc_items)} AMC/TBD reporter(s) today ({today}, via Convex)", flush=True)
        label = "Evening"
    elif args.session == "all":
        # Legacy combined behavior: prior business day's AMC/TBD, since this
        # mode is for manual/ad-hoc use replicating the original design.
        amc_items = load_amc_items_for_date(prior_day, watchlist)
        items += amc_items
        print(f"[digest] {len(amc_items)} AMC/TBD reporter(s) from {prior_day} (via Convex)", flush=True)

    context = {
        "generated_at": datetime.now(NY_TZ),
        "items": items,
    }
    html_body = render_post_earnings_digest_email(context)

    output_dir = WORKSPACE_ROOT / "outputs" / "post-earnings-digest" / today.isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "digest.html").write_text(html_body, encoding="utf-8")

    recipient = os.environ.get("DEAL_ALERT_EMAIL_TO", "").strip()
    if not recipient:
        print("[digest] No DEAL_ALERT_EMAIL_TO set -- skipping send", flush=True)
        return 0

    subject = f"{label} post-earnings summary: {today.isoformat()} ({len(items)} covered)"
    recipients = parse_recipients(recipient)
    sender = os.environ.get("EARNINGS_EMAIL_FROM", "earnings-bot@localhost")
    reply_to = os.environ.get("EARNINGS_EMAIL_REPLY_TO", "")
    text_body = f"{subject}\n\n" + "\n".join(
        f"{item['ticker']} ({item['company']}): "
        f"{item['reaction_pct']:+.1f}%" if item.get("reaction_pct") is not None else f"{item['ticker']}: N/A"
        for item in items
    )
    message = create_email_message(subject, html_body, text_body, sender, recipients, reply_to)
    save_email_message(message, str(output_dir / "digest.eml"))

    if args.draft_only:
        print("[digest] Drafted only", flush=True)
        return 0

    api_key = os.environ.get("AGENTMAIL_API_KEY", "").strip()
    if not api_key:
        print("[digest] No AGENTMAIL_API_KEY set -- skipping send", flush=True)
        return 0
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
            text=text_body,
            html=html_body,
            reply_to=reply_to,
        )
        print(f"[digest] sent (message_id={result.get('message_id')})", flush=True)
    except Exception as exc:
        print(f"[digest] send failed: {exc}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
