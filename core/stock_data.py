#!/usr/bin/env python3
"""
Stock price data fetching and email-safe chart rendering.

Uses yfinance (free, no API key). Generates pure-HTML/table bar charts that
render correctly in all email clients without requiring image hosting.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

# Color defaults matching the shared email design
_BRAND = "#3454f4"
_BRAND_SOFT = "#e8ecfe"
_MUTED = "#63697a"
_INK = "#0b0d12"
_BORDER = "#e3e5ea"
_PANEL_ALT = "#f7f8fa"
_POSITIVE = "#12805c"
_NEGATIVE = "#c23b4b"
_NEUTRAL = "#b4790a"
_MONO_STACK = "ui-monospace,'SF Mono',SFMono-Regular,Consolas,'Liberation Mono',Menlo,monospace"


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_price_history(ticker: str, period_days: int = 375) -> List[Dict[str, Any]]:
    """Fetch daily OHLCV history from Yahoo Finance. Returns [] on any failure."""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{period_days}d", auto_adjust=True)
        if hist.empty:
            print(f"[stock_data] No history returned for {ticker}", flush=True)
            return []
        result: List[Dict[str, Any]] = []
        for date, row in hist.iterrows():
            result.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row.get("Volume", 0)),
            })
        print(f"[stock_data] Fetched {len(result)} days for {ticker}", flush=True)
        return result
    except Exception as exc:
        print(f"[stock_data] Failed to fetch {ticker}: {exc}", flush=True)
        return []


def _fetch_live_move_from_quote(ticker: str, report_time: str = "") -> Dict[str, Any]:
    """Pull the real-time pre/post-market or regular-session move from yfinance's
    live quote fields. Unlike daily OHLC bars, this is available the same day a
    company reports -- including immediately after an after-close print, before
    the next day's bar exists."""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        print(f"[stock_data] Live quote fetch failed for {ticker}: {exc}", flush=True)
        return {}

    has_prepost = bool(info.get("hasPrePostMarketData"))
    post_pct = info.get("postMarketChangePercent")
    post_price = info.get("postMarketPrice")
    pre_pct = info.get("preMarketChangePercent")
    pre_price = info.get("preMarketPrice")
    reg_pct = info.get("regularMarketChangePercent")
    reg_price = info.get("regularMarketPrice")
    prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
    market_state = str(info.get("marketState") or "").upper()

    # Prefer whichever session is LIVE right now per Yahoo's own marketState,
    # not just a guess from report_time -- caught live: fetching MSFT the
    # morning after an after-close beat returned a stale -0.7% "regular"
    # figure (last night's PRE-EARNINGS intraday move, i.e. from before the
    # print) instead of the correct +9.5% premarket reaction, because
    # postmarket data had gone None (that session had ended) and the old
    # fixed priority order (postmarket -> regular -> premarket) stopped at
    # the first non-None field -- "regular" -- without ever reaching
    # "premarket", which was the actually-live and correct session.
    if market_state == "PRE":
        candidates = [
            ("premarket", pre_pct, pre_price),
            ("postmarket", post_pct, post_price),
            ("regular", reg_pct, reg_price),
        ]
    elif market_state in ("POST", "POSTPOST"):
        candidates = [
            ("postmarket", post_pct, post_price),
            ("regular", reg_pct, reg_price),
            ("premarket", pre_pct, pre_price),
        ]
    elif market_state == "REGULAR":
        candidates = [
            ("regular", reg_pct, reg_price),
            ("postmarket", post_pct, post_price),
            ("premarket", pre_pct, pre_price),
        ]
    else:
        # CLOSED or unrecognized state (e.g. weekend/holiday) -- fall back to
        # the report-time heuristic since marketState alone can't disambiguate.
        report_norm = (report_time or "").strip().lower()
        if "close" in report_norm:
            candidates = [
                ("postmarket", post_pct, post_price),
                ("regular", reg_pct, reg_price),
                ("premarket", pre_pct, pre_price),
            ]
        elif "open" in report_norm:
            candidates = [
                ("regular", reg_pct, reg_price),
                ("premarket", pre_pct, pre_price),
                ("postmarket", post_pct, post_price),
            ]
        else:
            candidates = [
                ("postmarket", post_pct, post_price),
                ("regular", reg_pct, reg_price),
                ("premarket", pre_pct, pre_price),
            ]

    for label, pct, price in candidates:
        if pct is None:
            continue
        if label in {"postmarket", "premarket"} and not has_prepost:
            continue
        return {
            "ah_move_pct": round(float(pct), 2),
            "ah_price": round(float(price), 2) if price is not None else None,
            "pre_close": round(float(prev_close), 2) if prev_close is not None else None,
            "source": f"yfinance_live_{label}",
            "market_state": market_state,
        }
    return {}


_MOVE_PATTERN = re.compile(
    r"(up|down|rose|fell|gained|dropped|slid|jumped|surged|plunged|climbed|tumbled)\s+"
    r"(?:as much as\s+)?(\d{1,3}(?:\.\d+)?)\s*%",
    re.I,
)
_AH_CONTEXT_PATTERN = re.compile(r"after.?hours|after.?market|post.?market|pre.?market|premarket", re.I)
_NEGATIVE_MOVE_WORDS = {"down", "fell", "dropped", "slid", "plunged", "tumbled"}


def _fetch_move_via_web_search(ticker: str, company: str = "") -> Dict[str, Any]:
    """Last-resort fallback when yfinance has no live quote data (e.g. thinly
    traded or non-US-primary tickers): search the web for a stated after-hours
    move and extract a percentage from the snippet."""
    try:
        import sys
        from pathlib import Path
        workspace_root = Path(__file__).resolve().parents[1]
        if str(workspace_root) not in sys.path:
            sys.path.insert(0, str(workspace_root))
        from core.research import run_research_query_cascade
    except Exception as exc:
        print(f"[stock_data] Could not load research module for AH fallback: {exc}", flush=True)
        return {}

    query = " ".join(
        part for part in (company, f"({ticker})" if ticker else "", "stock after hours move earnings reaction")
        if part
    ).strip()
    if not query:
        return {}

    try:
        research = run_research_query_cascade(query=query, max_results_per_provider=3)
    except Exception as exc:
        print(f"[stock_data] Web-search AH fallback failed for {ticker}: {exc}", flush=True)
        return {}

    for item in research.get("results", []) or []:
        text = " ".join(str(item.get(k, "")) for k in ("title", "snippet") if item.get(k)).strip()
        if not text or not _AH_CONTEXT_PATTERN.search(text):
            continue
        match = _MOVE_PATTERN.search(text)
        if not match:
            continue
        direction, pct_str = match.groups()
        pct = float(pct_str)
        if direction.lower() in _NEGATIVE_MOVE_WORDS:
            pct = -pct
        print(f"[stock_data] AH move for {ticker} resolved via web search: {pct:+.2f}%", flush=True)
        return {
            "ah_move_pct": round(pct, 2),
            "source": "web_search",
            "source_url": str(item.get("url", "")),
        }
    return {}


def fetch_live_reaction_move(ticker: str, report_time: str = "", company: str = "") -> Dict[str, Any]:
    """Fetch the most relevant earnings-reaction price move for a ticker that
    reported today: real-time yfinance quote fields first, web search as a
    fallback when structured data isn't available. Returns {} on failure."""
    result = _fetch_live_move_from_quote(ticker, report_time=report_time)
    if result:
        return result
    return _fetch_move_via_web_search(ticker, company=company)


def fetch_financial_snapshot(ticker: str) -> Dict[str, Any]:
    """Fetch a compact revenue/margin/guidance snapshot: last reported quarter's
    actual revenue + YoY growth, trailing gross margin, current price/market cap,
    and Street consensus revenue + YoY growth for the quarter and full year
    currently in progress (i.e. what's being previewed or was just reported).

    Consensus figures are a live snapshot, not a point-in-time record -- once a
    company reports, Yahoo's "current quarter" estimate rolls forward to the
    next quarter, so a same-day post-earnings fetch is the only reliable window
    to catch the consensus that applied to the quarter just reported.

    Important known gap: yfinance's "0q" estimate row (next_q_revenue_consensus)
    has no attached period-end date -- it's just yfinance's own internal notion
    of "the current/next quarter," which can silently misalign for companies
    with non-calendar fiscal years or around the rollover window. This function
    computes `next_q_expected_period_end` as a same-length-quarter estimate from
    the last REPORTED period (which does have a real date), purely as a
    verifiable anchor for the synthesis prompt to check research against -- it
    is not itself a verified fact and should never be presented to a reader as
    one.
    """
    result: Dict[str, Any] = {}
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)

        try:
            info = t.info or {}
            result["price"] = info.get("currentPrice") or info.get("regularMarketPrice")
            market_cap = info.get("marketCap")
            if result.get("price") is None or not market_cap:
                try:
                    fast = t.fast_info
                    result["price"] = (
                        result.get("price")
                        or fast.get("last_price")
                        or fast.get("lastPrice")
                    )
                    market_cap = (
                        market_cap
                        or fast.get("market_cap")
                        or fast.get("marketCap")
                    )
                except Exception:
                    pass
            if not market_cap and result.get("price"):
                shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
                if shares:
                    market_cap = float(result["price"]) * float(shares)
            if market_cap:
                result["market_cap_b"] = round(market_cap / 1_000_000_000, 2)
            gross_margin = info.get("grossMargins")
            if gross_margin is not None:
                result["gross_margin_pct"] = round(gross_margin * 100, 1)
        except Exception:
            pass

        try:
            qf = t.quarterly_income_stmt
            if qf is not None and "Total Revenue" in qf.index:
                row = qf.loc["Total Revenue"].dropna()
                if len(row) >= 1:
                    last_revenue = float(row.iloc[0])
                    result["last_q_revenue"] = last_revenue
                    idx = row.index[0]
                    result["last_q_label"] = idx.strftime("%b %Y") if hasattr(idx, "strftime") else str(idx)
                    result["last_q_period_end"] = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
                    if len(row) >= 5:
                        yoy_base = float(row.iloc[4])
                        if yoy_base:
                            result["last_q_yoy_pct"] = round((last_revenue - yoy_base) / yoy_base * 100, 1)
                    # Deterministic, dated anchor for the next quarter -- NOT a
                    # verified fact, just three calendar months past the last
                    # ACTUAL reported period (which does have a real date), so
                    # the synthesis prompt has something concrete to check its
                    # own search results against instead of blindly trusting
                    # yfinance's undated "0q" label below.
                    if hasattr(idx, "strftime"):
                        try:
                            import pandas as pd
                            next_end = idx + pd.DateOffset(months=3)
                            result["next_q_expected_period_end"] = next_end.strftime("%Y-%m-%d")
                        except Exception:
                            pass
        except Exception:
            pass

        try:
            # Dated CapEx anchors -- caught live against MSFT: the synthesis
            # model conflated a CALENDAR-year CapEx guidance figure quoted in
            # press coverage (e.g. "$190B for calendar 2026") with the
            # FISCAL-year figure the rest of the brief is framed around,
            # producing a full-year CapEx guidance number off by ~$70B. These
            # facts give the prompt real, dated fiscal-year numbers to check
            # newfound figures against, the same pattern used for revenue
            # above.
            acf = t.cashflow
            if acf is not None and "Capital Expenditure" in acf.index:
                arow = acf.loc["Capital Expenditure"].dropna()
                if len(arow) >= 1:
                    result["last_fy_capex_actual"] = abs(float(arow.iloc[0]))
                    aidx = arow.index[0]
                    result["last_fy_capex_period_end"] = (
                        aidx.strftime("%Y-%m-%d") if hasattr(aidx, "strftime") else str(aidx)
                    )

            qcf = t.quarterly_cashflow
            if qcf is not None and "Capital Expenditure" in qcf.index:
                qrow = qcf.loc["Capital Expenditure"].dropna()
                if len(qrow) >= 1:
                    last_fy_end = result.get("last_fy_capex_period_end")
                    if last_fy_end:
                        try:
                            import pandas as pd
                            fy_end_date = pd.Timestamp(last_fy_end)
                            qtd_quarters = [v for i, v in qrow.items() if i > fy_end_date]
                            if qtd_quarters:
                                result["fy_capex_qtd_actual"] = abs(float(sum(qtd_quarters)))
                                result["fy_capex_qtd_quarters"] = len(qtd_quarters)
                        except Exception:
                            pass
        except Exception:
            pass

        try:
            est = t.revenue_estimate
            if est is not None and not est.empty:
                if "0q" in est.index:
                    row = est.loc["0q"]
                    avg = row.get("avg")
                    growth = row.get("growth")
                    if avg is not None:
                        result["next_q_revenue_consensus"] = float(avg)
                    if growth is not None:
                        result["next_q_yoy_pct"] = round(float(growth) * 100, 1)
                if "0y" in est.index:
                    row = est.loc["0y"]
                    avg = row.get("avg")
                    growth = row.get("growth")
                    if avg is not None:
                        result["fy_revenue_consensus"] = float(avg)
                    if growth is not None:
                        result["fy_yoy_pct"] = round(float(growth) * 100, 1)
        except Exception:
            pass
    except Exception as exc:
        print(f"[stock_data] Financial snapshot fetch failed for {ticker}: {exc}", flush=True)
    return result


def fmt_revenue_b(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    billions = value / 1_000_000_000
    if billions >= 1:
        return f"${billions:,.2f}B"
    return f"${value / 1_000_000:,.1f}M"


def extract_iso_date(text: str) -> str:
    """Extract YYYY-MM-DD from a date string in various formats."""
    if not text:
        return ""
    iso = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if iso:
        return iso.group(0)
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    m = re.search(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", text, re.I)
    if m:
        month_num = months.get(m.group(1).lower())
        if month_num:
            try:
                return f"{m.group(3)}-{month_num:02d}-{int(m.group(2)):02d}"
            except Exception:
                pass
    return ""


def build_stock_context(
    ticker: str,
    earnings_date: str = "",
    history: Optional[List[Dict[str, Any]]] = None,
    report_time: str = "",
    company: str = "",
) -> Dict[str, Any]:
    """
    Build a stock context dict for email rendering.

    earnings_date: ISO YYYY-MM-DD string. If provided, computes pre-earnings
    close and post-earnings reaction move.

    The reaction move is resolved live first (yfinance real-time quote fields,
    falling back to a web search) since the next day's daily bar -- needed by
    the historical fallback below -- doesn't exist yet on the report day itself,
    which is exactly when this is most often called (same-day post-earnings
    automation). The daily-bar method only kicks in for older/backfilled events.
    """
    if history is None:
        history = fetch_price_history(ticker)
    if not history:
        return {}

    closes = [item["close"] for item in history]
    highs = [item["high"] for item in history]
    lows = [item["low"] for item in history]

    current_price = closes[-1]
    high_52w = max(highs)
    low_52w = min(lows)
    yoy_change_pct = ((closes[-1] - closes[0]) / closes[0] * 100) if closes[0] else None

    pre_close: Optional[float] = None
    post_open: Optional[float] = None
    ah_move_pct: Optional[float] = None
    move_source = ""

    if earnings_date:
        live = fetch_live_reaction_move(ticker, report_time=report_time, company=company)
        if live.get("ah_move_pct") is not None:
            ah_move_pct = live["ah_move_pct"]
            pre_close = live.get("pre_close")
            post_open = live.get("ah_price")
            move_source = live.get("source", "")

        if ah_move_pct is None:
            pre_items = [it for it in history if it["date"] <= earnings_date]
            if pre_items:
                pre_close = pre_items[-1]["close"]
            post_items = [it for it in history if it["date"] > earnings_date]
            if post_items:
                post_open = post_items[0]["open"]
            if pre_close and post_open:
                ah_move_pct = (post_open - pre_close) / pre_close * 100
                move_source = "daily_bars"

    return {
        "ticker": ticker,
        "current_price": current_price,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "yoy_change_pct": yoy_change_pct,
        "pre_close": pre_close,
        "post_open": post_open,
        "ah_move_pct": ah_move_pct,
        "ah_move_source": move_source,
        "history": history,
        "earnings_date": earnings_date,
    }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_price(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def fmt_pct(value: Optional[float], force_sign: bool = True) -> str:
    if value is None:
        return "N/A"
    sign = "+" if (force_sign and value >= 0) else ""
    return f"{sign}{value:.1f}%"


# ---------------------------------------------------------------------------
# Chart rendering
# ---------------------------------------------------------------------------

def _aggregate_weekly(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return last trading day per ISO week (Mon–Sun), sorted chronologically."""
    weekly: Dict[str, Dict[str, Any]] = {}
    for item in history:
        date = datetime.strptime(item["date"], "%Y-%m-%d")
        key = date.strftime("%G-W%V")
        weekly[key] = item
    return list(weekly.values())


def _render_chart(
    history: List[Dict[str, Any]],
    earnings_date: str = "",
    chart_height: int = 72,
    brand: str = _BRAND,
    brand_soft: str = _BRAND_SOFT,
    muted: str = _MUTED,
    neutral: str = _NEUTRAL,
) -> str:
    """Render a weekly price bar chart as an email-safe HTML table."""
    weekly = _aggregate_weekly(history)[-52:]
    if len(weekly) < 4:
        return ""

    closes = [it["close"] for it in weekly]
    min_c = min(closes)
    max_c = max(closes)
    price_range = max_c - min_c or 1.0

    earnings_week = ""
    if earnings_date:
        try:
            ed = datetime.strptime(earnings_date, "%Y-%m-%d")
            earnings_week = ed.strftime("%G-W%V")
        except Exception:
            pass

    cells: List[str] = []
    for i, item in enumerate(weekly):
        close = item["close"]
        bar_h = max(4, int(round((close - min_c) / price_range * (chart_height - 4)))) + 4
        empty_h = chart_height - bar_h
        is_latest = i == len(weekly) - 1

        item_date = datetime.strptime(item["date"], "%Y-%m-%d")
        item_week = item_date.strftime("%G-W%V")
        is_earnings = bool(earnings_week) and item_week == earnings_week

        if is_earnings:
            fill = neutral
        elif is_latest or i >= len(weekly) - 4:
            fill = brand
        else:
            fill = brand_soft

        w = f"{100 / len(weekly):.2f}%"
        cells.append(
            f'<td width="{w}" valign="bottom" style="padding:0 1px 0 0;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="height:{chart_height}px;">'
            f'<tr><td height="{empty_h}" style="height:{empty_h}px;font-size:0;line-height:0;">&nbsp;</td></tr>'
            f'<tr><td bgcolor="{fill}" height="{bar_h}" style="height:{bar_h}px;background:{fill};'
            f'border-radius:2px 2px 0 0;font-size:0;line-height:0;">&nbsp;</td></tr>'
            f'</table></td>'
        )

    first_label = weekly[0]["date"][:7]
    last_label = weekly[-1]["date"][:7]
    earnings_label = f'<span style="color:{neutral};font-weight:700;">&#9632; Earnings</span> &nbsp;' if earnings_week else ""

    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="table-layout:fixed;">'
        f'<tr>{"".join(cells)}</tr>'
        f'</table>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;">'
        f'<tr>'
        f'<td style="font-size:10px;line-height:14px;color:{muted};">{html.escape(first_label)}</td>'
        f'<td align="center" style="font-size:10px;line-height:14px;color:{muted};">{earnings_label}</td>'
        f'<td align="right" style="font-size:10px;line-height:14px;color:{muted};">{html.escape(last_label)}</td>'
        f'</tr>'
        f'</table>'
    )


def _metric_cells(metrics: List[tuple[str, str]]) -> str:
    cells = []
    for label, value_html in metrics:
        cells.append(
            f'<td valign="top" style="padding:0 20px 16px 0;white-space:nowrap;">'
            f'<div style="font-size:10px;line-height:14px;color:{_MUTED};text-transform:uppercase;'
            f'font-weight:700;letter-spacing:0.3px;">{html.escape(label)}</div>'
            f'<div style="padding-top:5px;font-size:15px;line-height:20px;color:{_INK};">{value_html}</div>'
            f'</td>'
        )
    return "".join(cells)


# ---------------------------------------------------------------------------
# Public render functions
# ---------------------------------------------------------------------------

def render_price_section_pre(
    stock_ctx: Dict[str, Any],
    implied_move: str = "",
) -> str:
    """Pre-earnings price section: current price, 52W range, 1Y return, implied move + chart."""
    if not stock_ctx:
        return ""

    current = fmt_price(stock_ctx.get("current_price"))
    high = fmt_price(stock_ctx.get("high_52w"))
    low = fmt_price(stock_ctx.get("low_52w"))
    yoy_val = stock_ctx.get("yoy_change_pct")
    yoy = fmt_pct(yoy_val)
    yoy_color = _POSITIVE if (yoy_val or 0) >= 0 else _NEGATIVE
    implied = implied_move.strip().lstrip("±") if implied_move else ""

    metrics: List[tuple[str, str]] = [
        ("Last Close", f'<strong style="color:{_INK};">{html.escape(current)}</strong>'),
        ("52W High", html.escape(high)),
        ("52W Low", html.escape(low)),
        ("1Y Return", f'<strong style="color:{yoy_color};">{html.escape(yoy)}</strong>'),
    ]
    if implied:
        metrics.append(("Implied Move", f'<strong style="color:{_NEUTRAL};">±{html.escape(implied)}</strong>'))

    history = stock_ctx.get("history", [])
    chart = _render_chart(history, earnings_date=stock_ctx.get("earnings_date", ""))

    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr>{_metric_cells(metrics)}</tr>'
        f'</table>'
        + chart
    )


def render_price_section_post(
    stock_ctx: Dict[str, Any],
    ah_move_display: str = "",
) -> str:
    """Post-earnings price section: pre-close, AH/open, 52W range, 1Y return + chart."""
    if not stock_ctx:
        return ""

    pre = fmt_price(stock_ctx.get("pre_close"))
    post = fmt_price(stock_ctx.get("post_open"))
    high = fmt_price(stock_ctx.get("high_52w"))
    low = fmt_price(stock_ctx.get("low_52w"))
    yoy_val = stock_ctx.get("yoy_change_pct")
    yoy = fmt_pct(yoy_val)
    yoy_color = _POSITIVE if (yoy_val or 0) >= 0 else _NEGATIVE

    ah_pct = stock_ctx.get("ah_move_pct")
    ah_display = ah_move_display or fmt_pct(ah_pct)
    ah_color = _POSITIVE if (ah_pct or 0) >= 0 else _NEGATIVE

    metrics: List[tuple[str, str]] = [
        ("Pre-Earnings", f'<strong style="color:{_INK};">{html.escape(pre)}</strong>'),
        ("AH Move", f'<strong style="color:{ah_color};">{html.escape(ah_display)}</strong>'),
        ("Next Open", f'<strong style="color:{_INK};">{html.escape(post)}</strong>'),
        ("52W High", html.escape(high)),
        ("52W Low", html.escape(low)),
        ("1Y Return", f'<strong style="color:{yoy_color};">{html.escape(yoy)}</strong>'),
    ]

    history = stock_ctx.get("history", [])
    chart = _render_chart(history, earnings_date=stock_ctx.get("earnings_date", ""))

    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr>{_metric_cells(metrics)}</tr>'
        f'</table>'
        + chart
    )
