"""Canonical Neostellar earnings coverage universe.

The market-data provider is a source of dates, not an authority on which
companies the product follows. The allowlist lives in one JSON file shared
with the dashboard so ingestion and presentation cannot drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


UNIVERSE_PATH = (
    Path(__file__).resolve().parents[1]
    / "dashboard"
    / "src"
    / "data"
    / "neostellarEarningsUniverse.json"
)


def normalize_ticker(value: Any) -> str:
    return str(value or "").strip().upper().replace(".", "-")


with UNIVERSE_PATH.open("r", encoding="utf-8") as source:
    _UNIVERSE = json.load(source)

SP500_TICKERS = frozenset(normalize_ticker(value) for value in _UNIVERSE["sp500"])
NEOSTELLAR_ADDITIONS = frozenset(
    normalize_ticker(value) for value in _UNIVERSE["thematicAdditions"]
)
TRACKED_TICKERS = frozenset(SP500_TICKERS | NEOSTELLAR_ADDITIONS)
EMAIL_DEEP_DIVE_TICKERS = frozenset(
    normalize_ticker(value) for value in _UNIVERSE["emailDeepDive"]
)

# Backward-compatible name consumed by the pre/post email jobs. It must remain
# the limited email watchlist, never the broader website-analysis universe.
DEFAULT_COVERAGE_UNIVERSE = ",".join(sorted(EMAIL_DEEP_DIVE_TICKERS))


def filter_tracked_rows(
    rows: Iterable[Dict[str, Any]], ticker_key: str = "Ticker"
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        ticker = normalize_ticker(row.get(ticker_key))
        if ticker not in TRACKED_TICKERS:
            continue
        filtered.append({**row, ticker_key: ticker})
    return filtered
