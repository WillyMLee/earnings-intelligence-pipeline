#!/usr/bin/env python3
"""
Cloud-friendly earnings radar automation runner.

This is the Render/Railway counterpart to the local PowerShell scheduler. It
fetches the latest calendar, selects either today's or this week's report window
in New York time, and then invokes the weekly earnings email workflow.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
WORKSPACE_ROOT = PROJECT_ROOT  # core/ and pipelines/ are now siblings under repo root
NY_TZ = ZoneInfo("America/New_York")

DEFAULT_COVERAGE_UNIVERSE = (
    # AI infrastructure, semis, neoclouds
    "NVDA,AMD,AVGO,MRVL,INTC,QCOM,SMCI,DELL,HPE,ANET,CSCO,ORCL,IBM,MSFT,AMZN,GOOGL,META,"
    "TSM,ASML,ARM,AMAT,LRCX,KLAC,MU,WDC,STX,SNDK,VRT,ETN,CRWV,NBIS,IREN,CORZ,"
    # vertical SaaS + cybersecurity + internet
    "VEEV,AXON,APP,SHOP,ADBE,CRM,NOW,SNOW,PANW,CRWD,DDOG,NET,TEAM,INTU,FTNT,S,"
    # SaaS expansion: identity, devops, HR/ops, ad-tech
    "ZS,OKTA,HUBS,GTLB,WDAY,TOST,BILL,MNDY,TTD,"
    # database and data platforms
    "MDB,CFLT,PLTR,ESTC,"
    # banks and financial services — NIM, credit quality, capital markets
    "JPM,BAC,WFC,C,GS,MS,USB,AXP,"
    # payments and fintech
    "V,MA,PYPL,FIS,ADYEN,"
    # industrials — demand cycles, supply chain, capex trends
    "CAT,DE,HON,EMR,"
    # defense and aerospace — defense budgets, program execution
    "RTX,LMT,BA,GE,"
    # AI power and grid — generators and storage serving data center demand
    "GEV,VST,CEG,NRG,OKLO,"
    # airlines — consumer travel demand, fare pricing, cost trends
    "DAL,UAL,AAL,"
    # consumer bellwethers: discretionary + staples + restaurants + logistics
    "AAPL,TSLA,NFLX,WMT,COST,HD,MCD,SBUX,NKE,PG,KO,FDX,UPS,"
    # Portfolio companies (illustrative placeholders -- replace with your
    # fund's actual holdings; see core/coverage.py for where these tie in)
    "EXPCO1,EXPCO2,EXPCO3,EXPCO4,"
    # notable recent IPOs being tracked separately (not portco holdings)
    "SPCX,CBRS,QNT,XNDU"
)
DEFAULT_FOCUS_SECTORS = (
    "AI Infrastructure,Neocloud,Vertical SaaS,Semis,Data Centers,Cloud,"
    "Enterprise Software,Internet,Cybersecurity,Ad Tech,"
    "Banks & Financials,Payments & Fintech,"
    "Industrials,Defense & Aerospace,"
    "AI Power & Grid,Data Center Power,"
    "Airlines,"
    "Consumer Discretionary,Consumer Staples,Restaurants,Logistics"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily or weekly earnings radar automation.")
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--draft-only", action="store_true", help="Draft artifacts without sending email.")
    parser.add_argument("--today", help="Override New York date for tests, formatted YYYY-MM-DD.")
    parser.add_argument("--calendar-output", default="", help="Optional normalized calendar output path.")
    parser.add_argument("--output-dir", default="", help="Optional workflow artifact directory.")
    parser.add_argument("--python", default=sys.executable or "python", help="Python executable to use.")
    return parser.parse_args()


def run_command(command: List[str]) -> None:
    print("[earnings-radar] Running:", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def env_value(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def resolve_today(override: str = ""):
    if override:
        return datetime.strptime(override, "%Y-%m-%d").date()
    return datetime.now(NY_TZ).date()


def resolve_window(mode: str, today):
    if mode == "weekly":
        # Weekly runs Sunday evening to preview the upcoming week, so
        # "this week's Monday" (today - weekday()) would resolve to the week
        # that just ended when today is Sunday (weekday()==6). Find the next
        # Monday on/after today instead -- for a Monday run this still
        # resolves to today itself, unchanged from before.
        days_until_monday = (0 - today.weekday()) % 7
        start = today + timedelta(days=days_until_monday)
        end = start + timedelta(days=6)
    else:
        # Daily is a same-day pulse, not a re-display of the whole week --
        # the weekly radar already covers the full week comprehensively
        # (uncapped, by day), and re-showing it every morning was redundant.
        start = end = today
    return start, end


def main() -> int:
    args = parse_args()
    today = resolve_today(args.today)
    start, end = resolve_window(args.mode, today)

    data_dir = PROJECT_ROOT / "data"
    output_root = WORKSPACE_ROOT / "outputs" / "earnings-automation"
    output_dir = Path(args.output_dir) if args.output_dir else output_root / args.mode
    calendar_output = Path(args.calendar_output) if args.calendar_output else data_dir / "latest_earnings_calendar.csv"
    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    fetch_args = [
        args.python,
        str(SCRIPT_DIR / "fetch_earnings_calendar.py"),
        "--output",
        str(calendar_output),
    ]
    calendar_input = env_value("EARNINGS_CALENDAR_CSV")
    if calendar_input and Path(calendar_input).exists():
        fetch_args.extend(["--input-csv", calendar_input])
    run_command(fetch_args)

    recipient_env = "DEAL_ALERT_EMAIL_TO" if args.mode == "daily" else "WEEKLY_BRIEFING_EMAIL_TO"
    recipient = env_value(recipient_env)
    if not recipient:
        raise RuntimeError(f"Missing required recipient env var: {recipient_env}")

    workflow_args = [
        args.python,
        str(SCRIPT_DIR / "run_weekly_earnings_workflow.py"),
        "--calendar-csv",
        str(calendar_output),
        "--week-start",
        start.isoformat(),
        "--week-end",
        end.isoformat(),
        "--watchlist",
        env_value("EARNINGS_COVERAGE_UNIVERSE", DEFAULT_COVERAGE_UNIVERSE),
        "--focus-sectors",
        env_value("EARNINGS_FOCUS_SECTORS", DEFAULT_FOCUS_SECTORS),
        "--top-n",
        "10" if args.mode == "daily" else "15",
        "--notable-count",
        "5" if args.mode == "daily" else "8",
        "--research-limit",
        env_value("EARNINGS_RESEARCH_LIMIT", "1"),
        "--output-dir",
        str(output_dir),
        "--delivery-provider",
        env_value("EMAIL_PROVIDER", "agentmail"),
        "--email-to",
        recipient,
        "--today",
        today.isoformat(),
    ]
    if args.mode == "daily":
        workflow_args.append("--daily")
    else:
        workflow_args.append("--live-research")

    agentmail_json = env_value("EARNINGS_AGENTMAIL_JSON")
    agentmail_eml_dir = env_value("EARNINGS_AGENTMAIL_EML_DIR")
    if agentmail_json and Path(agentmail_json).exists():
        workflow_args.extend(["--agentmail-json", agentmail_json])
    elif agentmail_eml_dir and Path(agentmail_eml_dir).exists():
        workflow_args.extend(["--agentmail-eml-dir", agentmail_eml_dir])
    if not args.draft_only:
        workflow_args.append("--send-email")

    run_command(workflow_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
