#!/usr/bin/env python3
"""
Archive generated earnings radar briefs to Convex.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.earnings_universe import TRACKED_TICKERS, normalize_ticker


CALENDAR_ARCHIVE_WINDOW_DAYS = 7
FINANCIAL_SNAPSHOT_ARTIFACT_KIND = "financial_snapshot_v1"


def _iso(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value or "")


def _list_from_csv(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def archive_earnings_calendar(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Archive the already-fetched normalized calendar for dashboard progress queries."""
    convex_url = os.environ.get("CONVEX_URL", "").strip()
    archive_token = os.environ.get("EARNINGS_ARCHIVE_TOKEN", "").strip() or os.environ.get("ADMIN_TOKEN", "").strip()
    if not convex_url or not archive_token:
        return {"status": "skipped", "reason": "Convex archive credentials not configured"}
    events = []
    for row in rows:
        ticker, report_date = normalize_ticker(row.get("Ticker", "")), str(row.get("Report Date", "")).strip()
        if ticker not in TRACKED_TICKERS or not report_date: continue
        event = {"ticker": ticker, "company": str(row.get("Company Name", "") or ticker), "reportDate": report_date, "reportTime": str(row.get("Report Time", "") or "TBD")}
        for source, target in (("EPS Estimate", "epsEstimate"), ("Revenue Estimate", "revenueEstimateUsd")):
            try:
                if str(row.get(source, "")).strip(): event[target] = float(str(row[source]).replace("$", "").replace(",", ""))
            except ValueError: pass
        events.append(event)
    if not events: return {"status": "skipped", "reason": "No events"}
    events.sort(key=lambda event: (event["reportDate"], event["ticker"], event["reportTime"], event["company"]))
    content_hash = hashlib.sha256(
        json.dumps(events, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    existing = _convex_request(
        convex_url=convex_url,
        kind="query",
        path="earningsCalendar:listWindow",
        args={"start": "0001-01-01", "end": "9999-12-31"},
    )
    existing_rows = existing if isinstance(existing, list) else []
    retained_by_key: Dict[str, Dict[str, Any]] = {}
    for row in existing_rows:
        ticker = normalize_ticker(row.get("ticker", ""))
        report_date = str(row.get("reportDate", "")).strip()
        if ticker not in TRACKED_TICKERS or not report_date:
            continue
        retained = {
            "ticker": ticker,
            "company": str(row.get("company", "") or ticker),
            "reportDate": report_date,
            "reportTime": str(row.get("reportTime", "") or "TBD"),
        }
        for field in ("sector", "epsEstimate", "revenueEstimateUsd"):
            if row.get(field) is not None:
                retained[field] = row[field]
        retained_by_key[f"{ticker}:{report_date}"] = retained
    for event in events:
        retained_by_key[f"{event['ticker']}:{event['reportDate']}"] = event
    archived_events = sorted(
        retained_by_key.values(),
        key=lambda event: (event["reportDate"], event["ticker"], event["reportTime"], event["company"]),
    )
    all_dates = [str(row.get("reportDate", "")) for row in existing_rows if row.get("reportDate")]
    all_dates.extend(event["reportDate"] for event in archived_events)
    first_date = date.fromisoformat(min(all_dates))
    last_date = date.fromisoformat(max(all_dates))
    results = []
    window_start = first_date
    while window_start <= last_date:
        window_end = min(window_start + timedelta(days=CALENDAR_ARCHIVE_WINDOW_DAYS - 1), last_date)
        start_text, end_text = window_start.isoformat(), window_end.isoformat()
        window_events = [event for event in archived_events if start_text <= event["reportDate"] <= end_text]
        results.append(
            _convex_request(
                convex_url=convex_url,
                kind="mutation",
                path="earningsCalendar:replaceWindow",
                args={
                    "adminToken": archive_token,
                    "windowStart": start_text,
                    "windowEnd": end_text,
                    "events": window_events,
                },
            )
        )
        window_start = window_end + timedelta(days=1)
    return {
        "status": "archived",
        "events": len(archived_events),
        "currentEvents": len(events),
        "contentHash": content_hash,
        "windows": len(results),
        "results": results,
    }


def _event_payload(event: Any) -> Dict[str, Any]:
    return {
        "ticker": getattr(event, "ticker", ""),
        "company": getattr(event, "company", ""),
        "reportDate": _iso(getattr(event, "report_date", "")),
        "reportTime": getattr(event, "report_time", ""),
        "sector": getattr(event, "sector", ""),
        "epsEstimate": getattr(event, "eps_estimate", ""),
        "revenueEstimate": getattr(event, "revenue_estimate", ""),
        "impliedMovePct": getattr(event, "implied_move_pct", None),
        "marketCapB": getattr(event, "market_cap_b", None),
        "score": getattr(event, "score", 0),
        "scoreReasons": getattr(event, "score_reasons", ""),
        "priorityLabel": getattr(event, "priority_label", ""),
        "agentmailNotes": getattr(event, "agentmail_notes", []) or [],
        "researchHits": getattr(event, "research_hits", []) or [],
        "newsletterDigest": getattr(event, "newsletter_digest", {}) or {},
    }


def _convex_request(convex_url: str, kind: str, path: str, args: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{convex_url.rstrip('/')}/api/{kind}"
    body = json.dumps({"path": path, "args": args, "format": "json"}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Convex {kind} {path} returned HTTP {err.code}: {detail}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"Convex {kind} {path} network error: {err}") from err

    if payload.get("status") != "success":
        raise RuntimeError(payload.get("errorMessage") or f"Convex {kind} {path} failed")
    return payload["value"] if "value" in payload else {}


def build_archive_payload(
    *,
    context: Dict[str, Any],
    manifest: Dict[str, Any],
    summary_markdown: str,
    email_html: str,
    coverage_universe_csv: str,
    coverage_themes_csv: str,
) -> Dict[str, Any]:
    period_start = _iso(context["week_start"])
    period_end = _iso(context["week_end"])
    mode = "daily" if period_start == period_end else "weekly"
    run_key = f"{mode}:{period_start}:{period_end}"
    delivery = manifest.get("delivery", {}) or {}
    events = [_event_payload(event) for event in context.get("events", [])]
    notable = [_event_payload(event) for event in context.get("notable_events", [])]

    return {
        "runKey": run_key,
        "mode": mode,
        "generatedAt": str(manifest.get("generated_at") or datetime.utcnow().isoformat()),
        "periodStart": period_start,
        "periodEnd": period_end,
        "title": str(context.get("title") or "Earnings Radar"),
        "subject": delivery.get("subject"),
        "deliveryStatus": str(delivery.get("status") or "unknown"),
        "recipients": list(delivery.get("recipients") or []),
        "eventCount": float(len(events)),
        "marketSignalCount": float(len(notable)),
        "coverageThemes": _list_from_csv(coverage_themes_csv),
        "coverageUniverse": _list_from_csv(coverage_universe_csv),
        "summaryMarkdown": summary_markdown,
        "emailHtml": email_html,
        "manifest": manifest,
        "events": events,
        "notableEvents": notable,
        "research": manifest.get("research", {}) or {},
    }


def archive_post_earnings_summary(
    *,
    ticker: str,
    company: str,
    quarter: str,
    report_date: str,
    report_time: str,
    reaction_pct: Any,
    reaction_line: str,
    key_metrics: List[str],
    sector: str = "",
    is_portco: bool = False,
    financials: Any = None,
) -> Dict[str, Any]:
    """Write a compact post-earnings summary to Convex so it can be read back
    by a different Render cron later (crons never share a filesystem, even a
    few hours apart). Returns {"status": "skipped", ...} if Convex isn't
    configured -- callers should treat this as non-fatal.

    `financials`, if given, is the structured comparable-figures dict from
    synthesize_earnings_brief_with_review() -- revenue_actual_usd,
    revenue_consensus_usd, revenue_yoy_pct, net_income_actual_usd,
    eps_actual, eps_consensus, eps_surprise_pct. This is what makes historical
    trend queries (listByTicker) actually usable -- without it there's
    nothing numeric to chart quarter over quarter."""
    convex_url = os.environ.get("CONVEX_URL", "").strip()
    archive_token = (
        os.environ.get("EARNINGS_ARCHIVE_TOKEN", "").strip()
        or os.environ.get("ADMIN_TOKEN", "").strip()
    )
    if not convex_url:
        return {"status": "skipped", "reason": "CONVEX_URL not configured"}
    if not archive_token:
        return {"status": "skipped", "reason": "EARNINGS_ARCHIVE_TOKEN not configured"}

    financials = financials or {}
    result = _convex_request(
        convex_url=convex_url,
        kind="mutation",
        path="postEarningsSummaries:upsertSummary",
        args={
            "adminToken": archive_token,
            "ticker": ticker,
            "company": company,
            "quarter": quarter,
            "reportDate": report_date,
            "reportTime": report_time,
            "reactionPct": reaction_pct,
            "reactionLine": reaction_line,
            "keyMetrics": key_metrics,
            "sector": sector,
            "isPortco": is_portco,
            "revenueActualUsd": financials.get("revenue_actual_usd"),
            "revenueConsensusUsd": financials.get("revenue_consensus_usd"),
            "revenueYoyPct": financials.get("revenue_yoy_pct"),
            "netIncomeActualUsd": financials.get("net_income_actual_usd"),
            "epsActual": financials.get("eps_actual"),
            "epsConsensus": financials.get("eps_consensus"),
            "epsSurprisePct": financials.get("eps_surprise_pct"),
            "capexActualUsd": financials.get("capex_actual_usd"),
            "capexGuidancePriorUsd": financials.get("capex_guidance_prior_usd"),
            "capexGuidanceUpdatedUsd": financials.get("capex_guidance_updated_usd"),
        },
    )
    return {"status": "archived", "result": result}


def fetch_post_earnings_summary(ticker: str, report_date: str) -> Dict[str, Any]:
    """Read back a previously archived post-earnings summary. Returns {} if
    Convex isn't configured, the request fails, or no row exists -- callers
    should fall back to a cheap reaction-only lookup in that case."""
    convex_url = os.environ.get("CONVEX_URL", "").strip()
    if not convex_url:
        return {}
    try:
        result = _convex_request(
            convex_url=convex_url,
            kind="query",
            path="postEarningsSummaries:getSummary",
            args={"ticker": ticker, "reportDate": report_date},
        )
    except RuntimeError as exc:
        print(f"[earnings-archive] Convex lookup failed for {ticker}/{report_date}: {exc}", flush=True)
        return {}
    return result or {}


def fetch_post_earnings_summaries_by_date(report_date: str) -> List[Dict[str, Any]]:
    """Read back every archived post-earnings summary for a given date, not
    filtered by ticker -- used to source a prior day's After Close reporters
    for the digest, since the rolling earnings-calendar CSV drops old dates
    (Convex is the durable record of who was actually processed, the
    calendar is only reliable for "what's upcoming"). Returns [] if Convex
    isn't configured or the request fails."""
    convex_url = os.environ.get("CONVEX_URL", "").strip()
    if not convex_url:
        return []
    try:
        result = _convex_request(
            convex_url=convex_url,
            kind="query",
            path="postEarningsSummaries:listByReportDate",
            args={"reportDate": report_date},
        )
    except RuntimeError as exc:
        print(f"[earnings-archive] Convex date lookup failed for {report_date}: {exc}", flush=True)
        return []
    return result if isinstance(result, list) else []


def fetch_post_earnings_summaries_by_ticker(ticker: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Read back a ticker's archived post-earnings summaries, most recent
    first -- the "map against previous" historical view. Returns [] if
    Convex isn't configured or the request fails."""
    convex_url = os.environ.get("CONVEX_URL", "").strip()
    if not convex_url:
        return []
    try:
        result = _convex_request(
            convex_url=convex_url,
            kind="query",
            path="postEarningsSummaries:listByTicker",
            args={"ticker": ticker, "limit": limit},
        )
    except RuntimeError as exc:
        print(f"[earnings-archive] Convex ticker lookup failed for {ticker}: {exc}", flush=True)
        return []
    return result if isinstance(result, list) else []


_UNSET = object()


def archive_pre_earnings_snapshot(*, ticker: str, report_date: str, snap: Any = None, eps_consensus: Any = _UNSET, consensus_source: str = "", captured_at: str = "") -> Dict[str, Any]:
    """Persist the reusable pre-earnings market snapshot before providers roll
    forward. Daily/weekly radar reads this first so a transient live-data miss
    does not turn a previously captured figure back into N/A."""
    convex_url = os.environ.get("CONVEX_URL", "").strip()
    archive_token = os.environ.get("EARNINGS_ARCHIVE_TOKEN", "").strip() or os.environ.get("ADMIN_TOKEN", "").strip()
    if not convex_url or not archive_token:
        return {"status": "skipped", "reason": "Convex archive credentials not configured"}
    args: Dict[str, Any] = {"adminToken": archive_token, "ticker": ticker, "reportDate": report_date}
    if snap is not None:
        args.update({
            "revenueConsensusUsd": snap.get("next_q_revenue_consensus"),
            "revenueConsensusYoyPct": snap.get("next_q_yoy_pct"),
            "fyRevenueConsensusUsd": snap.get("fy_revenue_consensus"),
            "fyRevenueConsensusYoyPct": snap.get("fy_yoy_pct"),
        })
    if eps_consensus is not _UNSET:
        args["epsConsensus"] = eps_consensus
    if consensus_source: args["consensusSource"] = consensus_source
    args["capturedAt"] = captured_at or datetime.now().isoformat(timespec="seconds")
    result = _convex_request(convex_url=convex_url, kind="mutation", path="preEarningsSnapshots:upsertSnapshot", args=args)
    artifact_result = None
    if snap is not None:
        artifact_payload = dict(snap)
        artifact_payload["_captured_at"] = args["capturedAt"]
        artifact_result = _convex_request(
            convex_url=convex_url,
            kind="mutation",
            path="researchArtifacts:upsertArtifact",
            args={
                "adminToken": archive_token,
                "kind": FINANCIAL_SNAPSHOT_ARTIFACT_KIND,
                "ticker": normalize_ticker(ticker),
                "reportDate": report_date,
                "title": "Reusable financial snapshot",
                "text": json.dumps(artifact_payload, ensure_ascii=False, sort_keys=True, default=str),
                "provider": consensus_source or "market-data snapshot",
            },
        )
    return {"status": "archived", "result": result, "artifact": artifact_result}


def load_financial_snapshot_artifact(*, ticker: str, report_date: str) -> Dict[str, Any]:
    """Read the complete reusable card snapshot from the existing artifact store."""
    convex_url = os.environ.get("CONVEX_URL", "").strip()
    normalized = normalize_ticker(ticker)
    if not convex_url or not normalized or not report_date:
        return {}
    try:
        result = _convex_request(
            convex_url=convex_url,
            kind="query",
            path="researchArtifacts:getArtifact",
            args={"kind": FINANCIAL_SNAPSHOT_ARTIFACT_KIND, "ticker": normalized, "reportDate": report_date},
        )
    except RuntimeError as exc:
        print(f"[earnings-archive] Convex financial-snapshot lookup failed: {exc}", flush=True)
        return {}
    if not isinstance(result, dict) or not result.get("text"):
        return {}
    try:
        payload = json.loads(result["text"])
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    payload.setdefault("_captured_at", result.get("updatedAt", ""))
    return payload


def archive_weekly_brief(
    *,
    context: Dict[str, Any],
    manifest: Dict[str, Any],
    summary_markdown: str,
    email_html: str,
    coverage_universe_csv: str,
    coverage_themes_csv: str,
) -> Dict[str, Any]:
    convex_url = os.environ.get("CONVEX_URL", "").strip()
    archive_token = (
        os.environ.get("EARNINGS_ARCHIVE_TOKEN", "").strip()
        or os.environ.get("ADMIN_TOKEN", "").strip()
    )
    if not convex_url:
        return {"status": "skipped", "reason": "CONVEX_URL not configured"}
    if not archive_token:
        return {"status": "skipped", "reason": "EARNINGS_ARCHIVE_TOKEN not configured"}

    payload = build_archive_payload(
        context=context,
        manifest=manifest,
        summary_markdown=summary_markdown,
        email_html=email_html,
        coverage_universe_csv=coverage_universe_csv,
        coverage_themes_csv=coverage_themes_csv,
    )
    result = _convex_request(
        convex_url=convex_url,
        kind="mutation",
        path="earningsArchive:upsertBrief",
        args={"adminToken": archive_token, **payload},
    )
    return {"status": "archived", "result": result, "run_key": payload["runKey"]}
