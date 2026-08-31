#!/usr/bin/env python3
"""
Run an end-to-end weekly earnings workflow:
- load the calendar
- merge optional AgentMail notes
- optionally enrich top market read-throughs with live research
- build markdown + HTML email
- draft or send the weekly email
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import agentmail_delivery
from earnings_archive import archive_weekly_brief
from build_weekly_earnings_brief import (
    build_markdown,
    build_weekly_context,
    enrich_financial_snapshots,
    enrich_market_caps,
    enrich_notable_what_matters,
    financial_snapshot_quality,
    load_agentmail_notes,
    load_events,
    monday_of_week,
    parse_csv_list,
    parse_date,
    score_events,
)
from extract_agentmail_earnings import parse_eml_file
from render_weekly_earnings_email import (
    build_email_subject,
    create_email_message,
    parse_recipients,
    render_weekly_email,
    save_email_message,
    send_email_message,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]  # pipelines/ is now a direct child of repo root
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from core.research import (
    filter_results_for_entity,
    run_research_query,
    run_research_query_cascade,
)


def write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the weekly earnings email workflow.")
    parser.add_argument("--calendar-csv", required=True, help="Path to earnings calendar CSV export.")
    parser.add_argument("--agentmail-json", help="Path to extracted AgentMail notes JSON.")
    parser.add_argument("--agentmail-eml-dir", help="Directory of .eml files to extract AgentMail notes from.")
    parser.add_argument("--week-start", help="Week start date (YYYY-MM-DD). Default: current week Monday.")
    parser.add_argument("--week-end", help="Week end date (YYYY-MM-DD). Default: week-start + 6 days.")
    parser.add_argument("--watchlist", default="", help="Comma-separated coverage universe tickers.")
    parser.add_argument("--focus-sectors", default="", help="Comma-separated coverage themes/sectors.")
    parser.add_argument("--top-n", type=int, default=15, help="Top N key names to show.")
    parser.add_argument("--notable-count", type=int, default=5, help="Number of market read-through narratives to render.")
    parser.add_argument("--daily", action="store_true", help="Render as the Daily Earnings Radar (weekday-sectioned notable table) instead of the Weekly Earnings Radar.")
    parser.add_argument("--today", help="Today's date (YYYY-MM-DD) for daily-mode weekday highlighting. Default: --week-start.")
    parser.add_argument(
        "--live-research",
        action="store_true",
        help="Pull live web context for the top notable names before drafting the email.",
    )
    parser.add_argument(
        "--research-limit",
        type=int,
        default=2,
        help="Max results per provider for each researched ticker.",
    )

    parser.add_argument("--output-dir", default="work", help="Directory for generated artifacts.")
    parser.add_argument("--summary-output", help="Optional markdown summary output path.")
    parser.add_argument("--html-output", help="Optional HTML email preview path.")
    parser.add_argument("--manifest-output", help="Optional workflow manifest path.")
    parser.add_argument("--draft-eml", help="Optional .eml draft output path.")

    parser.add_argument("--email-to", help="Comma-separated recipients for draft/send.")
    parser.add_argument("--email-from", help="From address for draft/send.")
    parser.add_argument("--reply-to", help="Optional reply-to address.")
    parser.add_argument("--email-subject", help="Override email subject.")
    parser.add_argument("--send-email", action="store_true", help="Send after drafting.")
    parser.add_argument(
        "--delivery-provider",
        choices=["smtp", "agentmail"],
        default="",
        help="Email delivery backend when --send-email is used.",
    )
    parser.add_argument("--smtp-host", default="", help="SMTP host override.")
    parser.add_argument("--smtp-port", type=int, default=0, help="SMTP port.")
    parser.add_argument("--smtp-username", default="", help="SMTP username override.")
    parser.add_argument("--smtp-password", default="", help="SMTP password override.")
    parser.add_argument("--smtp-starttls", action="store_true", help="Force STARTTLS.")
    parser.add_argument("--smtp-ssl", action="store_true", help="Force SMTP SSL.")
    parser.add_argument("--agentmail-inbox-id", default="", help="Existing AgentMail inbox ID/email.")
    parser.add_argument("--agentmail-display-name", default="", help="AgentMail inbox display name.")
    parser.add_argument("--agentmail-username", default="", help="AgentMail username to create if needed.")
    parser.add_argument("--agentmail-domain", default="", help="AgentMail domain override.")
    parser.add_argument("--agentmail-client-id", default="", help="AgentMail client_id for inbox reuse.")
    return parser.parse_args()


def slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "weekly_earnings"


def resolve_output_paths(
    args: argparse.Namespace,
    start: date,
    end: date,
    wants_email_artifacts: bool = False,
) -> Dict[str, str]:
    base = f"weekly_earnings_{slugify(start.isoformat())}_{slugify(end.isoformat())}"
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    draft_default = ""
    if args.email_to or args.send_email or wants_email_artifacts:
        draft_default = os.path.join(output_dir, f"{base}_email.eml")

    return {
        "summary": args.summary_output or os.path.join(output_dir, f"{base}_summary.md"),
        "html": args.html_output or os.path.join(output_dir, f"{base}_email.html"),
        "manifest": args.manifest_output or os.path.join(output_dir, f"{base}_workflow.json"),
        "draft_eml": args.draft_eml or draft_default,
    }


def resolve_email_settings(args: argparse.Namespace) -> Dict[str, Any]:
    smtp_ssl = args.smtp_ssl or env_bool("EARNINGS_SMTP_SSL", False)
    smtp_starttls = args.smtp_starttls or env_bool("EARNINGS_SMTP_STARTTLS", not smtp_ssl)
    env_provider = os.environ.get("EMAIL_PROVIDER", "").strip().lower()
    if env_provider not in {"smtp", "agentmail"}:
        env_provider = ""
    return {
        "to": args.email_to or os.environ.get("WEEKLY_BRIEFING_EMAIL_TO", ""),
        "host": args.smtp_host or os.environ.get("EARNINGS_SMTP_HOST", ""),
        "port": args.smtp_port or int(os.environ.get("EARNINGS_SMTP_PORT", "587")),
        "username": args.smtp_username or os.environ.get("EARNINGS_SMTP_USERNAME", ""),
        "password": args.smtp_password or os.environ.get("EARNINGS_SMTP_PASSWORD", ""),
        "from": args.email_from or os.environ.get("EARNINGS_EMAIL_FROM", "earnings-bot@localhost"),
        "reply_to": args.reply_to or os.environ.get("EARNINGS_EMAIL_REPLY_TO", ""),
        "use_ssl": smtp_ssl,
        "use_starttls": smtp_starttls,
        "delivery_provider": args.delivery_provider
        or env_provider
        or ("agentmail" if os.environ.get("AGENTMAIL_API_KEY") else "smtp"),
        "agentmail_api_key": os.environ.get("AGENTMAIL_API_KEY", ""),
        "agentmail_inbox_id": args.agentmail_inbox_id or os.environ.get("AGENTMAIL_INBOX_ID", ""),
        "agentmail_display_name": args.agentmail_display_name,
        "agentmail_username": args.agentmail_username,
        "agentmail_domain": args.agentmail_domain,
        "agentmail_client_id": args.agentmail_client_id,
    }


def resolve_week(args: argparse.Namespace) -> Tuple[date, date]:
    if args.week_start:
        start = parse_date(args.week_start)
        if not start:
            raise ValueError(f"Invalid --week-start date: {args.week_start}")
    else:
        start = monday_of_week(date.today())

    if args.week_end:
        end = parse_date(args.week_end)
        if not end:
            raise ValueError(f"Invalid --week-end date: {args.week_end}")
    else:
        end = start + timedelta(days=6)

    if end < start:
        raise ValueError("--week-end must be on or after --week-start.")
    return start, end


def extract_agentmail_notes_from_eml(eml_dir: str) -> Dict[str, List[dict]]:
    if not os.path.isdir(eml_dir):
        raise ValueError(f"EML directory not found: {eml_dir}")
    notes: Dict[str, List[dict]] = {}
    messages: List[dict] = []
    for name in sorted(os.listdir(eml_dir)):
        if not name.lower().endswith(".eml"):
            continue
        parse_eml_file(os.path.join(eml_dir, name), notes, messages)
    return notes


def resolve_agentmail_notes(args: argparse.Namespace) -> Dict[str, List[dict]]:
    if args.agentmail_json:
        return load_agentmail_notes(args.agentmail_json)
    if args.agentmail_eml_dir:
        return extract_agentmail_notes_from_eml(args.agentmail_eml_dir)
    return {}


def enrich_notable_events_with_research(
    events: List[Any],
    notable_count: int,
    research_limit: int,
    coverage_tickers: "set[str] | None" = None,
) -> Dict[str, Any]:
    ranked = sorted(events, key=lambda event: (-event.score, event.report_date, event.ticker))
    results_by_ticker: Dict[str, Dict[str, Any]] = {}
    for event in ranked[: max(1, notable_count)]:
        # Skip live research for names not in the coverage universe unless they have AgentMail notes
        in_universe = coverage_tickers is None or event.ticker in coverage_tickers
        if not in_universe and not event.agentmail_notes:
            results_by_ticker[event.ticker] = {"query": "", "result_count": 0, "errors": [], "skipped": True}
            continue
        query = " ".join(
            part
            for part in (
                event.company,
                f"({event.ticker})",
                "earnings preview expectations analyst notes",
            )
            if part
        )
        research = run_research_query_cascade(
            query=query,
            max_results_per_provider=max(1, research_limit),
        )
        event.research_hits = filter_results_for_entity(
            research.get("results", []) or [],
            company=event.company,
            ticker=event.ticker,
        )
        results_by_ticker[event.ticker] = {
            "query": research.get("query", ""),
            "result_count": len(event.research_hits),
            "errors": research.get("errors", []) or [],
            "skipped": False,
        }
    return results_by_ticker


def run_workflow(args: argparse.Namespace) -> Dict[str, Any]:
    start, end = resolve_week(args)
    agentmail_notes = resolve_agentmail_notes(args)
    email_settings = resolve_email_settings(args)
    wants_email_artifacts = bool(args.email_to or args.send_email or email_settings["to"])
    paths = resolve_output_paths(args, start, end, wants_email_artifacts=wants_email_artifacts)

    events, warnings = load_events(args.calendar_csv)
    week_events = [event for event in events if start <= event.report_date <= end]

    coverage_tickers: "set[str] | None" = (
        {t.strip().upper() for t in args.watchlist.split(",") if t.strip()}
        if args.watchlist
        else None
    )

    if args.daily:
        # The daily radar only ever displays coverage-universe names, so score
        # first (coverage tagging doesn't need market cap) and skip the
        # expensive full-calendar market-cap enrichment entirely -- financial
        # snapshot fetch below fills market cap for the names actually shown.
        score_events(
            week_events,
            agentmail_notes=agentmail_notes,
            watchlist=parse_csv_list(args.watchlist),
            focus_sectors=parse_csv_list(args.focus_sectors),
        )
        research_summary: Dict[str, Any] = {"enabled": False, "tickers": {}}
        print(f"[workflow] Enriching financial snapshots for coverage-universe events...", flush=True)
        enrich_financial_snapshots(week_events)
        print(f"[workflow] Synthesizing what-matters narrative for coverage-universe events...", flush=True)
        enrich_notable_what_matters(week_events)
    else:
        print(f"[workflow] Enriching market caps for {len(week_events)} events via yfinance...", flush=True)
        enrich_market_caps(week_events)
        score_events(
            week_events,
            agentmail_notes=agentmail_notes,
            watchlist=parse_csv_list(args.watchlist),
            focus_sectors=parse_csv_list(args.focus_sectors),
        )
        print("[workflow] Enriching financial snapshots for weekly coverage events...", flush=True)
        enrich_financial_snapshots(week_events)
        research_summary = {"enabled": bool(args.live_research), "tickers": {}}
        if args.live_research and week_events:
            research_summary["tickers"] = enrich_notable_events_with_research(
                week_events,
                notable_count=args.notable_count,
                research_limit=args.research_limit,
                coverage_tickers=coverage_tickers,
            )

    metric_quality = financial_snapshot_quality(week_events)
    if metric_quality["missing_tickers"]:
        warnings.append(
            "Company metrics unavailable for: "
            + ", ".join(metric_quality["missing_tickers"])
            + "."
        )
    if (
        args.send_email
        and not args.daily
        and metric_quality["coverage_event_count"] > 0
        and metric_quality["events_with_company_metrics"] == 0
    ):
        raise RuntimeError(
            "Weekly email blocked: no company-specific financial metrics were available "
            "from the live provider or either cached Convex snapshot."
        )

    today_override = parse_date(args.today) if args.today else start
    context = build_weekly_context(
        events=week_events,
        top_n=max(1, args.top_n),
        week_start=start,
        week_end=end,
        agentmail_notes=agentmail_notes,
        warnings=warnings,
        notable_count=max(1, args.notable_count),
        is_daily=args.daily,
        today=today_override,
    )
    markdown = build_markdown(
        events=week_events,
        top_n=max(1, args.top_n),
        week_start=start,
        week_end=end,
        agentmail_notes=agentmail_notes,
        warnings=warnings,
    )
    write_text(paths["summary"], markdown)

    html_body = render_weekly_email(context)
    write_text(paths["html"], html_body)

    recipients = parse_recipients(email_settings["to"])
    subject = args.email_subject or build_email_subject(context)
    delivery = {
        "status": "skipped",
        "recipients": recipients,
        "subject": subject,
        "draft_eml": paths["draft_eml"],
        "provider": email_settings["delivery_provider"],
    }

    if args.send_email and not recipients:
        raise ValueError("--send-email requires recipients via --email-to or WEEKLY_BRIEFING_EMAIL_TO.")

    if recipients:
        message = create_email_message(
            subject=subject,
            html_body=html_body,
            text_body=markdown,
            sender=email_settings["from"],
            recipients=recipients,
            reply_to=email_settings["reply_to"],
        )
        if paths["draft_eml"]:
            save_email_message(message, paths["draft_eml"])
            delivery["status"] = "drafted"
        if args.send_email:
            try:
                if email_settings["delivery_provider"] == "agentmail":
                    if not email_settings["agentmail_api_key"]:
                        raise ValueError("AGENTMAIL_API_KEY is required for AgentMail delivery.")
                    inbox = agentmail_delivery.ensure_inbox(
                        api_key=email_settings["agentmail_api_key"],
                        inbox_id=email_settings["agentmail_inbox_id"],
                        display_name=email_settings["agentmail_display_name"],
                        username=email_settings["agentmail_username"],
                        domain=email_settings["agentmail_domain"],
                        client_id=email_settings["agentmail_client_id"],
                    )
                    send_result = agentmail_delivery.send_message(
                        api_key=email_settings["agentmail_api_key"],
                        inbox_id=str(inbox.get("inbox_id") or inbox.get("email", "")),
                        to=recipients,
                        subject=subject,
                        text=markdown,
                        html=html_body,
                        reply_to=email_settings["reply_to"],
                    )
                    delivery["agentmail"] = {
                        "inbox_id": inbox.get("inbox_id"),
                        "inbox_email": inbox.get("email"),
                        "message_id": send_result.get("message_id"),
                        "thread_id": send_result.get("thread_id"),
                    }
                else:
                    send_email_message(
                        message=message,
                        smtp_host=email_settings["host"],
                        smtp_port=email_settings["port"],
                        smtp_username=email_settings["username"],
                        smtp_password=email_settings["password"],
                        use_starttls=email_settings["use_starttls"],
                        use_ssl=email_settings["use_ssl"],
                    )
                delivery["status"] = "sent"
            except Exception as err:
                delivery["status"] = "failed"
                delivery["error"] = str(err)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "event_count": len(week_events),
        "metric_quality": metric_quality,
        "delivery": delivery,
        "research": {
            "enabled": research_summary["enabled"],
            "tickers": research_summary.get("tickers", {}),
        },
        "outputs": {
            "summary_markdown": paths["summary"],
            "email_html": paths["html"],
            "draft_eml": paths["draft_eml"] or None,
        },
    }
    try:
        manifest["archive"] = archive_weekly_brief(
            context=context,
            manifest=manifest,
            summary_markdown=markdown,
            email_html=html_body,
            coverage_universe_csv=args.watchlist,
            coverage_themes_csv=args.focus_sectors,
        )
    except Exception as err:
        manifest["archive"] = {"status": "failed", "error": str(err)}

    write_json(paths["manifest"], manifest)
    manifest["outputs"]["manifest"] = paths["manifest"]
    return manifest


def main() -> int:
    args = parse_args()
    try:
        manifest = run_workflow(args)
    except Exception as err:
        print(f"[ERROR] {err}")
        return 1

    print(f"[OK] Wrote summary markdown: {manifest['outputs']['summary_markdown']}")
    print(f"[OK] Wrote email HTML: {manifest['outputs']['email_html']}")
    if manifest["outputs"].get("draft_eml"):
        print(f"[OK] Wrote email draft: {manifest['outputs']['draft_eml']}")
    print(f"[OK] Delivery status: {manifest['delivery']['status']}")
    if manifest["delivery"].get("error"):
        print(f"[ERROR] Delivery error: {manifest['delivery']['error']}")
    archive = manifest.get("archive", {})
    print(f"[OK] Archive status: {archive.get('status', 'unknown')}")
    if archive.get("error"):
        print(f"[ERROR] Archive error: {archive['error']}")
    print(f"[OK] Wrote workflow manifest: {manifest['outputs']['manifest']}")
    if args.send_email and manifest["delivery"]["status"] == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
