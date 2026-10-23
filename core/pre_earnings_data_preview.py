"""A sourced, deterministic preview when researched narrative fails review.

Only captured provider fields enter this template. No rejected model prose,
invented guidance, fiscal calendarization or reconstructed actuals are reused.
"""
from __future__ import annotations

import math
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def build_data_preview(ticker: str, company: str, report_date: str, snap: dict, eps_estimate=None) -> dict:
    from core.reporting_currency import financial_currency, financial_symbol
    currency = financial_currency(ticker, snap)
    symbol = financial_symbol(currency)
    revenue = _number(snap.get("next_q_revenue_consensus"))
    eps = _number(eps_estimate)
    if (revenue is None or revenue <= 0) and eps is None:
        return {}
    captured = datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")
    analysis_url = f"https://finance.yahoo.com/quote/{quote(ticker)}/analysis/"
    quote_url = f"https://finance.yahoo.com/quote/{quote(ticker)}/"
    calendar_url = "https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey=demo"
    highlights, metrics = [], []

    def add(text: str, url: str, domain: str):
        metrics.append(text)
        highlights.append({"text": f"{text} ([{domain}]({url}))", "children": []})

    if revenue is not None and revenue > 0:
        add(f"Upcoming revenue estimate: {symbol}{revenue / 1e9:,.2f} billion (Yahoo Finance consensus snapshot).", analysis_url, "finance.yahoo.com")
    if eps is not None:
        add(f"Calendar EPS estimate: {symbol}{eps:.2f} (Alpha Vantage; may differ from subsequently revised consensus).", calendar_url, "alphavantage.co")
    prior = _number(snap.get("last_q_revenue"))
    if prior is not None and prior > 0:
        label = str(snap.get("last_q_label") or snap.get("last_q_period_end") or "last available quarter")
        add(f"Prior reported revenue: {symbol}{prior / 1e9:,.2f} billion (provider period: {label}).", quote_url + "financials/", "finance.yahoo.com")
    margin = _number(snap.get("gross_margin_pct"))
    if margin is not None:
        add(f"Trailing-twelve-month GAAP gross margin: {margin:.1f}% (not quarterly non-GAAP margin).", quote_url + "key-statistics/", "finance.yahoo.com")
    price = _number(snap.get("price"))
    if price is not None and price > 0:
        add(f"Snapshot share price: ${price:,.2f}; captured {captured}.", quote_url, "finance.yahoo.com")
    if len(highlights) < 3:
        return {}
    return {
        "fiscal_quarter_label": "Upcoming report",
        "intro": f"{company} reports on {report_date}. This data preview summarizes provider estimates and the available financial baseline as of {captured}.",
        "financial_highlights": highlights[:5],
        "sections": [{"heading": "Report setup", "bullets": highlights[:2]}],
        "key_metrics": metrics[:5],
        "financials": {"revenue_consensus_usd": revenue, "eps_consensus": eps} if currency == "USD" else {},
        "official_links": {},
        "estimate_comparisons": [], "valuation_reference": {},
        "_qa_approved": True, "_qa_issues": [], "_data_preview": True,
    }
