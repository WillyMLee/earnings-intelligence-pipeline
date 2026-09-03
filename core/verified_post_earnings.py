"""Issuer-release-verified post-earnings fallbacks for exceptional reruns.

The normal path remains researched synthesis plus automated review. This
catalog is deliberately date-specific: it lets a verified correction run
proceed when the model provider is unavailable without turning an old release
or a pre-earnings snapshot into a purported set of reported results.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


CATALOG_PATH = Path(__file__).resolve().parent.parent / "cloudflare" / "verified-post-corrections.json"


@lru_cache(maxsize=1)
def _catalog() -> Dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def verified_post_earnings_brief(ticker: str, report_date: str) -> Dict[str, Any]:
    """Return a reviewed brief in the synthesis schema, or {} when absent."""
    item = (_catalog().get(report_date) or {}).get(ticker.upper())
    if not isinstance(item, dict):
        return {}
    return {
        "fiscal_quarter_label": item["quarter"],
        "intro": item["intro"],
        "financial_highlights": copy.deepcopy(item["financialHighlights"]),
        "sections": copy.deepcopy(item["sections"]),
        "key_metrics": list(item["keyMetrics"]),
        "key_figures": copy.deepcopy(item.get("keyFigures") or []),
        "official_links": dict(item["officialLinks"]),
        "financials": dict(item["financials"]),
        "_qa_approved": True,
        "_qa_issues": [],
        "_verified_fallback": True,
    }
