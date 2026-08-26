#!/usr/bin/env python3
"""Public-repo entry point for resumable transcript/consensus prefetch batches."""

from __future__ import annotations

import argparse, csv, json, sys, time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.research import fetch_transcript_excerpt  # noqa: E402
from core.stock_data import fetch_financial_snapshot  # noqa: E402
from pipelines.earnings_archive import archive_pre_earnings_snapshot  # noqa: E402


def _optional_number(value):
    text = str(value or "").strip()
    if not text: return None
    try: return float(text.replace("$", "").replace(",", ""))
    except ValueError: return None


def consensus_refresh_due(event, prior, today):
    """Refresh once daily only while the report is close enough to matter."""
    try:
        days = (date.fromisoformat(event["report_date"]) - today).days
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= days <= 21 and (
        prior.get("consensus") != "archived"
        or prior.get("consensusCapturedOn") != today.isoformat()
    )


def parse_args():
    p = argparse.ArgumentParser(description="Warm transcript and consensus inputs in small resumable batches.")
    p.add_argument("--calendar-csv", required=True); p.add_argument("--start", default=""); p.add_argument("--end", default="")
    p.add_argument("--watchlist", default=""); p.add_argument("--batch-size", type=int, default=10); p.add_argument("--pause-seconds", type=float, default=.75)
    p.add_argument("--resume-file", default="data/earnings-input-backfill-state.json"); p.add_argument("--transcripts", action="store_true")
    p.add_argument("--consensus", action="store_true"); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--rotate-daily", action="store_true", help="Rotate the starting event so repeated misses cannot starve the queue."); return p.parse_args()


def main():
    args = parse_args()
    if not args.transcripts and not args.consensus: raise SystemExit("Choose --transcripts and/or --consensus.")
    allowed = {t.strip().upper() for t in args.watchlist.split(",") if t.strip()}
    with open(args.calendar_csv, "r", encoding="utf-8-sig", newline="") as source: rows = list(csv.DictReader(source))
    events = sorted([{"ticker": str(r.get("Ticker", "")).upper(), "company": str(r.get("Company Name", "") or r.get("Ticker", "")), "report_date": str(r.get("Report Date", "")), "eps_estimate": _optional_number(r.get("EPS Estimate")), "revenue_estimate": _optional_number(r.get("Revenue Estimate"))} for r in rows if r.get("Ticker") and r.get("Report Date") and (not allowed or str(r.get("Ticker")).upper() in allowed) and (not args.start or str(r.get("Report Date")) >= args.start) and (not args.end or str(r.get("Report Date")) <= args.end)], key=lambda e:(e["report_date"],e["ticker"]))
    state_path=Path(args.resume_file); state=json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"completed":{}}; completed=state.setdefault("completed",{})
    def needs_work(event):
        prior=completed.get(f"{event['ticker']}:{event['report_date']}",{})
        return (args.transcripts and "transcript_v2" not in prior) or (
            args.consensus and consensus_refresh_due(event, prior, date.today())
        )
    pending=[e for e in events if needs_work(e)]
    if args.rotate_daily and pending:
        offset=(date.today().toordinal()*max(1,args.batch_size))%len(pending); pending=pending[offset:]+pending[:offset]
    transcript_only=args.transcripts and not args.consensus
    batch=pending if transcript_only else pending[:max(1,args.batch_size)]
    print(f"[backfill] {len(events)} eligible; processing {len(batch)}")
    uncached_attempts=0
    for i,event in enumerate(batch):
        key=f"{event['ticker']}:{event['report_date']}"
        if args.dry_run:
            if i<max(1,args.batch_size): print(f"[dry-run] {key} {event['company']}")
            continue
        performed_remote_attempt=False
        outcome={**completed.get(key,{}),"completedAt":datetime.now().isoformat(timespec="seconds")}
        if args.transcripts:
            artifact=fetch_transcript_excerpt(event["ticker"],event["company"],"",event["report_date"]); cache_hit=bool(artifact.get("cache_hit")); outcome["transcript_v2"]="cached" if cache_hit else "fetched" if artifact else "not_found"
            if not cache_hit: uncached_attempts+=1; performed_remote_attempt=True
        if args.consensus:
            days=(date.fromisoformat(event["report_date"])-date.today()).days
            if 0<=days<=21:
                snap=fetch_financial_snapshot(event["ticker"]); sources=[]
                if event.get("revenue_estimate") is not None: snap["next_q_revenue_consensus"]=event["revenue_estimate"]; sources.append("calendar revenue estimate")
                elif snap.get("next_q_revenue_consensus") is not None: sources.append("yfinance revenue estimate")
                kwargs={"ticker":event["ticker"],"report_date":event["report_date"],"snap":snap,"consensus_source":" + ".join(sources + (["calendar EPS estimate"] if event.get("eps_estimate") is not None else [])),"captured_at":datetime.now().isoformat(timespec="seconds")}
                if event.get("eps_estimate") is not None: kwargs["eps_consensus"]=event["eps_estimate"]
                outcome["consensus"]=archive_pre_earnings_snapshot(**kwargs).get("status","unknown")
                if outcome["consensus"] == "archived": outcome["consensusCapturedOn"] = date.today().isoformat()
            else: outcome["consensus"]="skipped_outside_21_day_window"
        completed[key]=outcome; state_path.parent.mkdir(parents=True,exist_ok=True); state_path.write_text(json.dumps(state,indent=2,sort_keys=True),encoding="utf-8"); print(f"[backfill] {key}: {outcome}")
        if transcript_only and uncached_attempts>=max(1,args.batch_size): break
        if i<len(batch)-1 and performed_remote_attempt and args.pause_seconds>0: time.sleep(args.pause_seconds)
    return 0


if __name__ == "__main__": raise SystemExit(main())
