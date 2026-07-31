#!/usr/bin/env python3
"""
Extract ticker-level notes from AgentMail .eml messages into normalized JSON.

This script parses:
- plain text blocks like:
    Ticker: AAPL
    Priority: high
    Note: iPhone demand stable
- bullet lines like:
    - AAPL | high | iPhone demand stable
- CSV attachments with columns including ticker/symbol, priority, note/comment
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from typing import Dict, List


def normalize_priority(value: str) -> str:
    value = (value or "").strip().lower()
    if value in {"high", "medium", "low"}:
        return value
    if value in {"h", "med", "m"}:
        return {"h": "high", "med": "medium", "m": "medium"}[value]
    if value in {"l"}:
        return "low"
    return "unspecified"


def add_note(notes: Dict[str, List[dict]], ticker: str, priority: str, note: str, source: str) -> None:
    ticker = (ticker or "").strip().upper()
    if not ticker or not re.fullmatch(r"[A-Z]{1,6}", ticker):
        return
    payload = {
        "priority": normalize_priority(priority),
        "note": (note or "").strip(),
        "source": source,
    }
    if not payload["note"]:
        return
    notes.setdefault(ticker, []).append(payload)


def parse_block_style(text: str, notes: Dict[str, List[dict]], source: str) -> None:
    ticker = None
    priority = "unspecified"
    note_parts: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if ticker and note_parts:
                add_note(notes, ticker, priority, " ".join(note_parts), source)
            ticker = None
            priority = "unspecified"
            note_parts = []
            continue
        lower = line.lower()
        if lower.startswith("ticker:"):
            if ticker and note_parts:
                add_note(notes, ticker, priority, " ".join(note_parts), source)
                note_parts = []
            ticker = line.split(":", 1)[1].strip().upper()
        elif lower.startswith("priority:"):
            priority = line.split(":", 1)[1].strip()
        elif lower.startswith("note:"):
            note_parts.append(line.split(":", 1)[1].strip())
        elif ticker:
            note_parts.append(line)
    if ticker and note_parts:
        add_note(notes, ticker, priority, " ".join(note_parts), source)


def parse_pipe_bullets(text: str, notes: Dict[str, List[dict]], source: str) -> None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        parts = [part.strip() for part in line.lstrip("-").split("|")]
        if len(parts) < 2:
            continue
        ticker = parts[0]
        priority = parts[1] if len(parts) >= 2 else "unspecified"
        note = parts[2] if len(parts) >= 3 else ""
        add_note(notes, ticker, priority, note, source)


def find_column(headers: List[str], aliases: List[str]) -> str | None:
    normalized = {re.sub(r"[^a-z0-9]+", "", h.lower()): h for h in headers}
    for alias in aliases:
        key = re.sub(r"[^a-z0-9]+", "", alias.lower())
        if key in normalized:
            return normalized[key]
    return None


def parse_csv_attachment(content: bytes, notes: Dict[str, List[dict]], source: str) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        return
    ticker_col = find_column(reader.fieldnames, ["ticker", "symbol"])
    priority_col = find_column(reader.fieldnames, ["priority", "importance"])
    note_col = find_column(reader.fieldnames, ["note", "comment", "summary", "context"])
    if not ticker_col or not note_col:
        return
    for row in reader:
        add_note(
            notes,
            row.get(ticker_col, ""),
            row.get(priority_col, "unspecified") if priority_col else "unspecified",
            row.get(note_col, ""),
            source,
        )


def parse_eml_file(path: str, notes: Dict[str, List[dict]], messages: List[dict]) -> None:
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    file_name = os.path.basename(path)
    messages.append(
        {
            "file": file_name,
            "subject": str(msg.get("Subject", "")),
            "date": str(msg.get("Date", "")),
        }
    )

    for part in msg.walk():
        ctype = part.get_content_type()
        filename = part.get_filename() or ""
        if part.is_multipart():
            continue
        payload = part.get_payload(decode=True) or b""
        if ctype in {"text/plain", "text/markdown"} and not filename:
            text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            parse_block_style(text, notes, file_name)
            parse_pipe_bullets(text, notes, file_name)
        if filename.lower().endswith(".csv") or ctype == "text/csv":
            parse_csv_attachment(payload, notes, file_name + ":" + filename)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract AgentMail earnings notes from .eml files.")
    parser.add_argument("--eml-dir", required=True, help="Directory containing .eml files.")
    parser.add_argument("--output", required=True, help="Path to output JSON file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not os.path.isdir(args.eml_dir):
        print(f"[ERROR] EML directory not found: {args.eml_dir}")
        return 1

    notes: Dict[str, List[dict]] = {}
    messages: List[dict] = []

    eml_files = sorted(
        [
            os.path.join(args.eml_dir, name)
            for name in os.listdir(args.eml_dir)
            if name.lower().endswith(".eml")
        ]
    )
    if not eml_files:
        print(f"[ERROR] No .eml files found in: {args.eml_dir}")
        return 1

    for path in eml_files:
        parse_eml_file(path, notes, messages)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "messages": messages,
        "notes": notes,
    }
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    print(
        f"[OK] Extracted {sum(len(v) for v in notes.values())} notes for {len(notes)} tickers -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
