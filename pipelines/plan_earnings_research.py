#!/usr/bin/env python3
"""Print a deterministic earnings-research plan for QA or orchestration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.earnings_orchestration import build_earnings_research_plan  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an earnings research workflow plan.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--company", default="")
    parser.add_argument("--report-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--report-time", default="", help="BMO, AMC, or a provider-specific label")
    parser.add_argument("--mode", choices=("pre", "post"), required=True)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_earnings_research_plan(
        ticker=args.ticker,
        company=args.company,
        report_date=args.report_date,
        report_time=args.report_time,
        mode=args.mode,
    )
    print(json.dumps(plan, indent=None if args.compact else 2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

