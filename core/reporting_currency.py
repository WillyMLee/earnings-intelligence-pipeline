"""Dated USD convenience translations, retaining source amounts and FX evidence."""
from __future__ import annotations

import copy
import json
import math
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
CURRENCIES = {"SPOT": "EUR", "ADYEN": "EUR", "ADYEN.AS": "EUR", "000660.KS": "KRW", "000660": "KRW", "SK HYNIX": "KRW", "SKHYNIX": "KRW"}
SNAPSHOT_AMOUNTS = ("last_q_revenue", "next_q_revenue_consensus", "fy_revenue_consensus", "last_fy_capex_actual", "fy_capex_qtd_actual")
def financial_currency(ticker: str, snap: dict | None = None) -> str:
    return str((snap or {}).get("financial_currency") or CURRENCIES.get(ticker.upper(), "USD")).upper()


def financial_symbol(currency: str) -> str:
    return {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "KRW": "\u20a9", "JPY": "\u00a5", "CNY": "\u00a5", "INR": "\u20b9", "TWD": "NT$", "HKD": "HK$", "CAD": "C$", "AUD": "A$"}.get(currency, currency + " ")


def _fetch(url: str) -> bytes:
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    request = urllib.request.Request(url, headers={"User-Agent": "EarningsIntelligence/1.0"})
    with urllib.request.urlopen(request, context=context, timeout=20) as response:
        return response.read()


@lru_cache(maxsize=1)
def _ecb_days() -> tuple:
    root = ET.fromstring(_fetch(ECB_URL))
    return tuple((node.attrib["time"], {row.attrib["currency"]: float(row.attrib["rate"]) for row in node if "currency" in row.attrib}) for node in root.iter() if "time" in node.attrib)


def _valid_rate(currency: str, as_of: str, day: str, rate: float, source: str, url: str) -> dict:
    age = (date.fromisoformat(as_of) - date.fromisoformat(day)).days
    if age < 0 or age > 7 or not math.isfinite(rate) or rate <= 0:
        raise ValueError(f"No recent {currency}/USD FX observation on or before {as_of}")
    return {"source_currency": currency, "target_currency": "USD", "usd_per_unit": rate, "rate_date": day, "requested_date": as_of, "source": source, "source_url": url, "method": "single dated reference rate; convenience translation, not accounting restatement"}


@lru_cache(maxsize=128)
def get_usd_rate(currency: str, as_of: str) -> dict:
    currency = currency.upper()
    as_of = min(as_of, datetime.now(ZoneInfo("America/New_York")).date().isoformat())
    date.fromisoformat(as_of)
    if currency == "USD":
        return _valid_rate("USD", as_of, as_of, 1.0, "USD identity", "")
    try:
        candidates = [(day, rates) for day, rates in _ecb_days() if day <= as_of and "USD" in rates and (currency == "EUR" or currency in rates)]
        if candidates:
            day, rates = max(candidates, key=lambda row: row[0])
            rate = rates["USD"] / (1.0 if currency == "EUR" else rates[currency])
            return {**_valid_rate(currency, as_of, day, rate, "European Central Bank daily reference rates", ECB_URL), "reference_base": "EUR", "usd_per_eur": rates["USD"], "source_units_per_eur": 1.0 if currency == "EUR" else rates[currency]}
    except (ValueError, OSError, ET.ParseError):
        pass
    start = (date.fromisoformat(as_of) - timedelta(days=7)).isoformat()
    url = f"https://api.frankfurter.dev/v2/rates?base={currency.lower()}&quotes=usd&from={start}&to={as_of}&expand=providers"
    rows = json.loads(_fetch(url))
    rows = [row for row in rows if str(row.get("date", "")) <= as_of and str(row.get("base", "")).upper() == currency and str(row.get("quote", "")).upper() == "USD"]
    if not rows:
        raise ValueError(f"No verified {currency}/USD conversion rate for {as_of}")
    row = max(rows, key=lambda value: value["date"])
    return {**_valid_rate(currency, as_of, row["date"], float(row["rate"]), "Frankfurter daily reference (central-bank composite)", url), "provider_observations": row.get("providers", [])}


def _numeric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def usd_amount(value: float) -> str:
    for scale, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= scale:
            return f"${value / scale:,.2f}{suffix}"
    return f"${value:,.2f}"


_UNITS = {"": 1, "thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9, "trillion": 1e12, "tn": 1e12, "t": 1e12}
_NUMBER = r"-?\d[\d,]*(?:\.\d+)?"
_UNIT = r"trillion|billion|million|thousand|bn|tn|[KMBT]"


def _translate_text(text: str, fx: dict, originals: list) -> str:
    currency = fx["source_currency"]
    tokens = [re.escape(currency), re.escape(financial_symbol(currency).strip())]
    if currency == "EUR": tokens += ["euros?"]
    if currency == "KRW": tokens += ["won"]
    token = "(?:" + "|".join(set(tokens)) + ")"
    prefix = re.compile(r"(?<![\w/])" + token + r"\s*(?P<low>" + _NUMBER + r")(?:\s*(?:to|[-–—])\s*(?:" + token + r"\s*)?(?P<high>" + _NUMBER + r"))?\s*(?P<unit>" + _UNIT + r")?(?!\w)", re.I)
    suffix = re.compile(r"(?<![\w/])(?P<low>" + _NUMBER + r")(?:\s*(?:to|[-–—])\s*(?P<high>" + _NUMBER + r"))?\s*(?P<unit>" + _UNIT + r")?\s+" + token + r"(?!\w)", re.I)
    protected = []
    def replace(match):
        scale = _UNITS[(match.group("unit") or "").lower()]
        low = float(match.group("low").replace(",", "")) * scale * fx["usd_per_unit"]
        converted = usd_amount(low)
        if match.group("high"):
            converted += "–" + usd_amount(float(match.group("high").replace(",", "")) * scale * fx["usd_per_unit"])
        original = match.group().strip()
        originals.append({"native": original, "usd": converted})
        protected.append(converted + f" ({original})")
        return f"@@FX_AMOUNT_{len(protected)-1}@@"
    text = prefix.sub(replace, text)
    text = suffix.sub(replace, text)
    for index, value in enumerate(protected): text = text.replace(f"@@FX_AMOUNT_{index}@@", value)
    return text


def normalize_brief(ticker: str, brief: dict, source_currency: str, as_of: str) -> dict:
    """Convert approved native research once, after source and QA checks."""
    if brief.get("currency_normalization") or source_currency == "USD":
        return copy.deepcopy(brief)
    fx = dict(get_usd_rate(source_currency, as_of))
    result = copy.deepcopy(brief)
    originals = []
    def visit(value):
        if isinstance(value, str): return _translate_text(value, fx, originals)
        if isinstance(value, list): return [visit(item) for item in value]
        if isinstance(value, dict): return {key: visit(item) for key, item in value.items()}
        return value
    for field in ("intro", "financial_highlights", "sections", "qa_highlights", "key_metrics", "key_figures", "estimate_comparisons", "valuation_reference"):
        if field in result: result[field] = visit(result[field])
    result["intro"] = re.sub(r"Financial results are in euros unless explicitly labeled otherwise\.", "Financial results are USD-normalized with the native amounts retained.", result.get("intro", ""), flags=re.I)
    for figure in result.get("key_figures") or []:
        if isinstance(figure, dict):
            figure["label"] = str(figure.get("label") or "").replace(f"({source_currency})", "(USD)")
    valuation = result.get("valuation_reference") or {}
    if valuation:
        def dollar_value(value):
            match = re.search(r"\$\s*(" + _NUMBER + r")\s*(" + _UNIT + r")?", str(value or ""), re.I)
            return float(match[1].replace(",", "")) * _UNITS[(match[2] or "").lower()] if match else None
        enterprise_value = dollar_value(valuation.get("enterprise_value"))
        revenue = dollar_value(valuation.get("cy_revenue"))
        valuation["ev_cy_revenue"] = f"~{enterprise_value / revenue:.1f}x (USD-normalized inputs)" if enterprise_value is not None and revenue and revenue > 0 else ""
    if result.get("key_metrics"):
        result["key_metrics"][0] += f"; USD-normalized at 1 {source_currency}=${fx['usd_per_unit']:.8g} ({fx['rate_date']})"
    native = copy.deepcopy(result.get("financials") or {})
    result["financials"] = {key: value * fx["usd_per_unit"] if _numeric(value) and (key.endswith("_usd") or key in {"eps_actual", "eps_consensus"}) else value for key, value in native.items()}
    note = f"USD convenience translation: 1 {source_currency} = ${fx['usd_per_unit']:.10g}, reference date {fx['rate_date']}. Original amounts are retained in parentheses. Reported growth rates and margins are unchanged; these are not issuer-reported USD results. EPS retains the issuer's original share basis; FX conversion does not adjust ADR/GDR ratios."
    result.setdefault("sections", []).append({"heading": "Currency normalization", "bullets": [{"text": note, "children": [f"FX source: [{fx['source']}]({fx['source_url']})"]}]})
    result["currency_normalization"] = {**fx, "native_financials": native, "native_valuation_reference": copy.deepcopy(brief.get("valuation_reference") or {}), "original_amounts": originals}
    return result


def normalize_snapshot(ticker: str, snapshot: dict, as_of: str) -> dict:
    if snapshot.get("currency_normalization"):
        return copy.deepcopy(snapshot)
    native = copy.deepcopy(snapshot)
    result = copy.deepcopy(snapshot)
    currency = financial_currency(ticker, native)
    quote_currency = str(native.get("quote_currency") or "USD").upper()
    fx = get_usd_rate(currency, as_of)
    quote_fx = get_usd_rate(quote_currency, as_of)
    for field in SNAPSHOT_AMOUNTS:
        if _numeric(result.get(field)): result[field] *= fx["usd_per_unit"]
    for field in ("price", "market_cap_b", "enterprise_value_b"):
        if _numeric(result.get(field)): result[field] *= quote_fx["usd_per_unit"]
    result["financial_currency"] = "USD"
    result["quote_currency"] = "USD"
    if currency != "USD" or quote_currency != "USD":
        result["currency_normalization"] = {**fx, "quote_fx": quote_fx, "native_snapshot": native}
    return result
