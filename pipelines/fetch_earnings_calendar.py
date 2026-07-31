#!/usr/bin/env python3
"""
Fetch and normalize an earnings calendar CSV.

Preferred source order:
1. Existing local CSV supplied via --input-csv
2. Alpha Vantage official earnings calendar endpoint
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Dict, Iterable, List


OUTPUT_HEADERS = [
    "Ticker",
    "Company Name",
    "Report Date",
    "Report Time",
    "Sector",
    "EPS Estimate",
    "Revenue Estimate",
    "Implied Move",
    "Market Cap",
]


def write_rows(path: str, rows: Iterable[Dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in OUTPUT_HEADERS})


_CORPORATE_SUFFIXES = {
    "incorporated", "inc", "inc.",
    "corporation", "corp", "corp.",
    "company", "co", "co.",
    "group",
    "holdings", "holding",
    "limited", "ltd", "ltd.",
    "plc", "llc",
    "n.v.", "nv", "s.a.", "sa", "ag", "se",
}


def _strip_corporate_suffix(name: str) -> str:
    """Emails should say "Intel", not "Intel Corporation" -- the honorific
    doesn't help identify the company and just adds noise. Strips trailing
    corporate-entity words one at a time (so compound suffixes like "Group
    Incorporated" fully resolve to nothing extra: American Airlines Group
    Incorporated -> American Airlines Group -> American Airlines)."""
    words = name.split()
    while len(words) > 1 and words[-1].lower().rstrip(".,") in _CORPORATE_SUFFIXES:
        words.pop()
    result = " ".join(words)
    return result if result else name


def normalize_company_name(name: str, ticker: str = "") -> str:
    """Alpha Vantage returns company names in ALL CAPS (e.g. "AMERICAN EXPRESS
    COMPANY"), which every downstream email/dashboard renders verbatim.
    Title-case for display, but restore the ticker itself if title-casing it
    would mangle a ticker-derived acronym embedded in the name (RTX
    Corporation, PNC Financial Services Group -> "Rtx"/"Pnc" otherwise). Also
    strips the trailing corporate suffix regardless of input casing."""
    text = str(name or "").strip()
    if not text:
        return text
    if text == text.upper():
        titled = text.title()
        # .title() capitalizes the letter after an apostrophe too (MCDONALD'S
        # -> "Mcdonald'S") -- fix the common possessive case.
        titled = re.sub(r"'S\b", "'s", titled)
        ticker_clean = ticker.strip().upper()
        if ticker_clean:
            titled = re.sub(rf"\b{re.escape(ticker_clean.title())}\b", ticker_clean, titled)
    else:
        # Already mixed/lower case (e.g. hand-supplied via --input-csv) -- no
        # title-casing needed, but still strip the corporate suffix below.
        titled = text
    return _strip_corporate_suffix(titled)


def normalize_time_of_day(value: str) -> str:
    text = str(value or "").strip().lower()
    if text == "pre-market":
        return "Before Open"
    if text == "post-market":
        return "After Close"
    return "TBD"


def normalize_alpha_vantage_rows(text: str) -> List[Dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    rows: List[Dict[str, str]] = []
    for raw in reader:
        ticker = str(raw.get("symbol", "")).strip().upper()
        if not ticker:
            continue
        rows.append(
            {
                "Ticker": ticker,
                "Company Name": normalize_company_name(str(raw.get("name", "")).strip(), ticker),
                "Report Date": str(raw.get("reportDate", "")).strip(),
                "Report Time": normalize_time_of_day(raw.get("timeOfTheDay", "")),
                "Sector": "",
                "EPS Estimate": str(raw.get("estimate", "")).strip(),
                "Revenue Estimate": "",
                "Implied Move": "",
                "Market Cap": "",
            }
        )
    return rows


def fetch_alpha_vantage_csv(api_key: str, horizon: str = "3month") -> str:
    params = urllib.parse.urlencode(
        {
            "function": "EARNINGS_CALENDAR",
            "horizon": horizon,
            "apikey": api_key,
        }
    )
    url = f"https://www.alphavantage.co/query?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", errors="replace")


def copy_csv(input_csv: str, output: str) -> int:
    with open(input_csv, "r", encoding="utf-8-sig", newline="") as src:
        text = src.read()
    rows = list(csv.DictReader(io.StringIO(text)))
    write_rows(output, rows)
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and normalize an earnings calendar CSV.")
    parser.add_argument("--output", required=True, help="Normalized CSV output path.")
    parser.add_argument("--input-csv", default="", help="Existing CSV to normalize/copy.")
    parser.add_argument(
        "--alpha-vantage-api-key",
        default=os.environ.get("ALPHA_VANTAGE_API_KEY", "demo"),
        help="Alpha Vantage API key. Defaults to env or demo.",
    )
    parser.add_argument(
        "--horizon",
        default="3month",
        choices=["3month", "6month", "12month"],
        help="Alpha Vantage earnings calendar horizon.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.input_csv and os.path.exists(args.input_csv):
        count = copy_csv(args.input_csv, args.output)
        print(f"[OK] Normalized existing earnings CSV: {args.output} ({count} rows)")
        return 0

    payload = fetch_alpha_vantage_csv(args.alpha_vantage_api_key, horizon=args.horizon)
    rows = normalize_alpha_vantage_rows(payload)
    write_rows(args.output, rows)
    print(
        f"[OK] Fetched Alpha Vantage earnings calendar: {args.output} ({len(rows)} rows) at {datetime.now().isoformat()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
