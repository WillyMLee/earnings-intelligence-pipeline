#!/usr/bin/env python3
"""
Render and deliver a polished weekly earnings HTML email.
"""

from __future__ import annotations

import html
import os
import re
import smtplib
from email import policy
from email.message import EmailMessage
from typing import Any, Dict, Iterable, List, Optional


BRAND = "#3454f4"
BRAND_SOFT = "#e8ecfe"
POSITIVE = "#12805c"
POSITIVE_SOFT = "#e3f5ee"
NEGATIVE = "#c23b4b"
NEGATIVE_SOFT = "#fbe9ec"
NEUTRAL = "#b4790a"
NEUTRAL_SOFT = "#faf1de"
INK = "#0b0d12"
INK_SOFT = "#9aa3b2"
MUTED = "#63697a"
BORDER = "#e3e5ea"
PANEL = "#ffffff"
PANEL_ALT = "#f7f8fa"
PAGE_BG = "#f5f6f8"
FONT_STACK = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO_STACK = "ui-monospace,'SF Mono',SFMono-Regular,Consolas,'Liberation Mono',Menlo,monospace"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def parse_recipients(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def build_email_subject(context: Dict[str, Any]) -> str:
    start = context["week_start"].isoformat()
    end = context["week_end"].isoformat()
    span = (context["week_end"] - context["week_start"]).days
    if context.get("is_daily") or span <= 1:
        # Match what's actually shown in the body -- the uncapped day-grouped
        # count, not notable_events (which is capped and only used in the
        # weekly narrative section).
        today_count = sum(len(section["events"]) for section in context.get("notable_by_weekday", []))
        return f"Daily earnings radar: {start} ({today_count} reporters today)"
    notable_count = len(context.get("notable_events", []))
    return f"Weekly earnings radar: {start} to {end} ({notable_count} market signals)"


def section_label(title: str) -> str:
    return (
        f'<div style="padding-bottom:12px;margin-bottom:14px;border-bottom:1px solid {BORDER};">'
        f'<span style="font-size:11px;line-height:16px;color:{MUTED};text-transform:uppercase;'
        f'font-weight:700;letter-spacing:0.8px;">{esc(title)}</span>'
        f'</div>'
    )


def bold_lead(text: str, max_words: int = 4) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    for sep in (";", ":"):
        idx = text.find(sep)
        if 0 < idx <= 60:
            return f'<strong>{esc(text[:idx])}</strong>{esc(text[idx:])}'
    words = text.split(None, max_words)
    if len(words) <= max_words:
        return f'<strong>{esc(text)}</strong>'
    joined = " ".join(words[:max_words])
    rest = text[len(joined):]
    return f'<strong>{esc(joined)}</strong>{esc(rest)}'


def render_list(items: Iterable[str], color: str = BRAND) -> str:
    rows = "".join(
        "<tr>"
        f'<td valign="top" style="padding:3px 8px 5px 0;color:{color};font-size:13px;line-height:20px;">&#9632;</td>'
        f'<td valign="top" style="padding:3px 0 5px 0;color:{INK};font-size:13px;line-height:20px;">{bold_lead(item)}</td>'
        "</tr>"
        for item in items
        if str(item).strip()
    )
    if not rows:
        return ""
    return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:4px;">' + rows + "</table>"


def implication_color(label: str) -> str:
    lower = str(label or "").strip().lower()
    if "key" in lower or "read-through" in lower:
        return BRAND
    if "lower" in lower or "monitor" in lower:
        return NEUTRAL
    if "signal" in lower or "industry" in lower:
        return POSITIVE
    return NEGATIVE


def implication_soft_color(label: str) -> str:
    color = implication_color(label)
    return {BRAND: BRAND_SOFT, NEUTRAL: NEUTRAL_SOFT, POSITIVE: POSITIVE_SOFT, NEGATIVE: NEGATIVE_SOFT}.get(color, PANEL_ALT)


def render_badge(label: str, color: str, soft_color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:4px 11px;border-radius:999px;'
        f'background:{soft_color};color:{color};font-size:11px;line-height:16px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.4px;">{esc(label)}</span>'
    )


def mono(value: str) -> str:
    return f'<span style="font-family:{MONO_STACK};">{esc(value)}</span>'


def clamp_percent(value: float) -> int:
    return max(0, min(100, int(round(value))))


def render_metric_card(label: str, value: str, note: str, width_pct: str = "25%") -> str:
    return (
        f'<td width="{width_pct}" valign="top" style="padding:0 6px 12px 6px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PANEL_ALT};border:1px solid {BORDER};border-radius:14px;table-layout:fixed;">'
        '<tr><td height="160" valign="top" style="height:160px;padding:20px 18px 16px 18px;">'
        f'<div style="font-family:{MONO_STACK};font-size:32px;line-height:36px;color:{INK};font-weight:600;letter-spacing:-0.5px;">{esc(value)}</div>'
        f'<div style="padding-top:10px;font-size:13px;line-height:18px;color:{INK};font-weight:600;">{esc(label)}</div>'
        f'<div style="padding-top:6px;font-size:12px;line-height:17px;color:{MUTED};">{esc(note)}</div>'
        "</td></tr></table></td>"
    )


def render_metric_tile_grid(items: List[Dict[str, str]]) -> str:
    if not items:
        return ""
    cells = [
        render_metric_card(item.get("label", ""), item.get("value", ""), item.get("note", ""))
        for item in items
    ]
    return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>' + "".join(cells) + "</tr></table>"


def render_panel(title: str, subtitle: str, body: str) -> str:
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;background:{PANEL};border:1px solid {BORDER};border-radius:20px;">'
        f'<tr><td style="padding:24px 24px 6px 24px;font-size:30px;line-height:34px;color:{INK};font-weight:800;letter-spacing:0;">{esc(title)}</td></tr>'
        f'<tr><td style="padding:0 24px 18px 24px;color:{MUTED};font-size:14px;line-height:22px;">{esc(subtitle)}</td></tr>'
        f'<tr><td style="padding:0 24px 24px 24px;">{body}</td></tr>'
        "</table>"
    )


def render_newsletter_digest(digest: Dict[str, Any]) -> str:
    rows: List[str] = []

    implication_label = str(digest.get("implication_label", "")).strip()
    if implication_label:
        rows.append(
            f'<div style="padding-top:10px;">'
            + render_badge(implication_label, implication_color(implication_label), implication_soft_color(implication_label))
            + '</div>'
        )

    view_text = str(digest.get("view", "") or "").strip()
    if view_text:
        rows.append(
            f'<div style="padding-top:10px;font-size:13px;line-height:21px;color:{INK};">'
            f'<span style="font-size:10px;font-weight:800;text-transform:uppercase;color:{BRAND};letter-spacing:0.5px;">VIEW</span>'
            f'<div style="margin-top:4px;">{esc(view_text)}</div>'
            f'</div>'
        )

    read_through = str(digest.get("read_through", "") or "").strip()
    if read_through:
        rows.append(
            f'<div style="padding-top:10px;font-size:13px;line-height:21px;color:{INK};">'
            f'<span style="font-size:10px;font-weight:800;text-transform:uppercase;color:{BRAND};letter-spacing:0.5px;">READ-THROUGH</span>'
            f'<div style="margin-top:4px;">{esc(read_through)}</div>'
            f'</div>'
        )

    watch_items = [str(item).strip() for item in digest.get("watch_items", []) if str(item).strip()]
    if watch_items:
        rows.append(
            f'<div style="padding-top:10px;">'
            f'<span style="font-size:10px;font-weight:800;text-transform:uppercase;color:{NEUTRAL};letter-spacing:0.5px;">WHAT TO WATCH</span>'
            + render_list(watch_items, NEUTRAL)
            + "</div>"
        )

    return (
        f'<div style="border-left:4px solid {BRAND};padding-left:12px;margin-bottom:4px;">'
        f'<div style="font-size:18px;line-height:24px;color:{INK};font-weight:800;">{esc(digest.get("headline", ""))}</div>'
        + "".join(rows)
        + "</div>"
    )


def render_event_stats(event: Any) -> str:
    rows = [
        ("Report", f"{event.report_date.isoformat()} {event.report_time}"),
        ("Sector", event.sector or "N/A"),
        ("Signal Score", str(event.score)),
        ("Implied Move", f"{event.implied_move_pct:.1f}%" if event.implied_move_pct is not None else "N/A"),
        ("Market Cap", f"{event.market_cap_b:.0f}B" if event.market_cap_b is not None and event.market_cap_b < 1000 else (f"{event.market_cap_b / 1000:.2f}T" if event.market_cap_b is not None else "N/A")),
    ]
    body = "".join(
        "<tr>"
        f'<td style="padding:10px 12px;border-top:1px solid {BORDER};color:{MUTED};font-size:12px;text-transform:uppercase;font-weight:700;">{esc(label)}</td>'
        f'<td style="padding:10px 12px;border-top:1px solid {BORDER};color:{INK};font-size:13px;font-weight:700;">{esc(value)}</td>'
        "</tr>"
        for label, value in rows
    )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {BORDER};border-radius:14px;overflow:hidden;">'
        f'<tr style="background:{PANEL_ALT};"><td style="padding:12px;color:{MUTED};font-size:12px;text-transform:uppercase;font-weight:700;">Metric</td>'
        f'<td style="padding:12px;color:{MUTED};font-size:12px;text-transform:uppercase;font-weight:700;">Value</td></tr>'
        + body
        + "</table>"
    )


def render_notable_event(event: Any) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;">'
        "<tr>"
        f'<td width="64%" valign="top" style="padding:0 14px 0 0;">{render_newsletter_digest(event.newsletter_digest or {})}</td>'
        f'<td width="36%" valign="top" style="padding:0 0 0 14px;">{render_event_stats(event)}</td>'
        "</tr></table>"
    )


def render_leaderboard(events: List[Any]) -> str:
    if not events:
        return f'<div style="color:{MUTED};font-size:14px;line-height:22px;">No ranked events available.</div>'
    sorted_events = sorted(
        events,
        key=lambda event: (event.implied_move_pct if event.implied_move_pct is not None else -1, event.score),
        reverse=True,
    )[:6]
    max_move = max((event.implied_move_pct or 0.0) for event in sorted_events) or 1.0
    rows: List[str] = []
    for event in sorted_events:
        move = event.implied_move_pct or 0.0
        fill = clamp_percent((move / max_move) * 100.0 if max_move else 0)
        rows.append(
            "<tr><td style=\"padding:0 0 14px 0;\">"
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="padding:0 0 6px 0;color:{INK};font-size:13px;font-weight:700;">{mono(event.ticker)} &middot; {esc(event.company)}</td>'
            f'<td align="right" style="padding:0 0 6px 0;color:{BRAND};font-size:13px;font-weight:700;">{move:.1f}%</td>'
            "</tr><tr><td colspan=\"2\">"
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#edf2f7;border-radius:999px;">'
            f'<tr><td width="{fill}%" style="height:10px;background:{BRAND};font-size:0;line-height:0;border-radius:999px;">&nbsp;</td><td width="{100 - fill}%"></td></tr>'
            "</table></td></tr></table></td></tr>"
        )
    return "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">" + "".join(rows) + "</table>"


def render_calendar_table(events: List[Any]) -> str:
    if not events:
        return f'<div style="color:{MUTED};font-size:14px;line-height:22px;">No weekly calendar entries found.</div>'
    rows = []
    for event in events:
        rows.append(
            "<tr>"
            f'<td style="padding:12px 14px;border-top:1px solid {BORDER};color:{INK};font-size:13px;font-weight:700;">{esc(event.report_date.isoformat())}</td>'
            f'<td style="padding:12px 14px;border-top:1px solid {BORDER};color:{INK};font-size:13px;">{esc(event.report_time)}</td>'
            f'<td style="padding:12px 14px;border-top:1px solid {BORDER};color:{INK};font-size:13px;font-weight:700;">{mono(event.ticker)}</td>'
            f'<td style="padding:12px 14px;border-top:1px solid {BORDER};color:{INK};font-size:13px;">{esc(event.company)}</td>'
            f'<td style="padding:12px 14px;border-top:1px solid {BORDER};color:{INK};font-size:13px;">{esc(event.sector or "-")}</td>'
            "</tr>"
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {BORDER};border-radius:14px;overflow:hidden;">'
        f'<tr style="background:{PANEL_ALT};">'
        f'<td style="padding:12px 14px;color:{MUTED};font-size:12px;text-transform:uppercase;font-weight:700;">Date</td>'
        f'<td style="padding:12px 14px;color:{MUTED};font-size:12px;text-transform:uppercase;font-weight:700;">Time</td>'
        f'<td style="padding:12px 14px;color:{MUTED};font-size:12px;text-transform:uppercase;font-weight:700;">Ticker</td>'
        f'<td style="padding:12px 14px;color:{MUTED};font-size:12px;text-transform:uppercase;font-weight:700;">Company</td>'
        f'<td style="padding:12px 14px;color:{MUTED};font-size:12px;text-transform:uppercase;font-weight:700;">Sector</td>'
        "</tr>"
        + "".join(rows)
        + "</table>"
    )


def render_agentmail_highlights(items: List[Dict[str, str]]) -> str:
    if not items:
        return f'<div style="color:{MUTED};font-size:14px;line-height:22px;">No AgentMail notes provided.</div>'
    rows = []
    for item in items[:12]:
        rows.append(
            "<tr>"
            f'<td valign="top" style="padding:0 10px 10px 0;color:{BRAND};font-size:16px;line-height:22px;">&#8226;</td>'
            f'<td valign="top" style="padding:0 0 10px 0;color:{INK};font-size:14px;line-height:22px;"><span style="font-weight:800;">{esc(item["ticker"])}</span> ({esc(item["priority"])}): {esc(item["note"])}</td>'
            "</tr>"
        )
    return "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">" + "".join(rows) + "</table>"


def render_warning_list(warnings: List[str]) -> str:
    if not warnings:
        return f'<div style="color:{MUTED};font-size:14px;line-height:22px;">No data warnings.</div>'
    rows = []
    for item in warnings:
        rows.append(
            "<tr>"
            f'<td valign="top" style="padding:0 10px 10px 0;color:{NEGATIVE};font-size:16px;line-height:22px;">&#8226;</td>'
            f'<td valign="top" style="padding:0 0 10px 0;color:{INK};font-size:14px;line-height:22px;">{esc(item)}</td>'
            "</tr>"
        )
    return "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">" + "".join(rows) + "</table>"


def _render_event_block(event: Any) -> str:
    mcap = event.market_cap_b
    if mcap is not None:
        mcap_str = f"{mcap:.0f}B" if mcap < 1000 else f"{mcap / 1000:.1f}T"
    else:
        mcap_str = "N/A"
    meta_parts = [
        f"{event.report_date.day} {event.report_date.strftime('%b')}" if hasattr(event.report_date, "strftime") else str(event.report_date),
        event.report_time or "TBD",
        f"Mkt cap {mcap_str}",
    ]
    if event.implied_move_pct is not None:
        meta_parts.append(f"Impl. move {event.implied_move_pct:.1f}%")
    meta_line = " · ".join(meta_parts)
    snap = getattr(event, "financial_snapshot", None) or {}
    stat_grid = render_stat_grid(
        available_stat_fields(build_stat_grid_fields(snap, mcap), limit=3),
        margin="6px 0 10px 0",
    )
    what_matters = str(getattr(event, "what_matters", "") or "").strip()
    what_matters_html = (
        f'<div style="padding-bottom:10px;font-size:12px;line-height:18px;color:{INK};">{esc(what_matters)}</div>'
        if what_matters else ""
    )
    return (
        f'<div style="padding:0 0 24px 0;">'
        f'<div style="font-size:11px;font-weight:700;color:{MUTED};text-transform:uppercase;letter-spacing:0.4px;padding-bottom:6px;">{esc(meta_line)}</div>'
        + stat_grid
        + what_matters_html
        + render_newsletter_digest(event.newsletter_digest or {})
        + "</div>"
    )


def fmt_price(value: Optional[float]) -> str:
    return f"${value:,.2f}" if value is not None else "N/A"


def fmt_revenue_compact(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    billions = value / 1_000_000_000
    return f"${billions:,.1f}B" if billions >= 1 else f"${value / 1_000_000:,.0f}M"


def render_stat_cell(label: str, value: str) -> str:
    return (
        f'<td width="33.33%" valign="top" style="padding:0 12px 8px 0;">'
        f'<div style="font-size:9px;font-weight:700;color:{MUTED};text-transform:uppercase;letter-spacing:0.3px;">{esc(label)}</div>'
        f'<div style="padding-top:2px;font-size:13px;font-weight:600;color:{INK};white-space:nowrap;">{esc(value)}</div>'
        "</td>"
    )


def _yoy_suffix(pct: Optional[float]) -> str:
    return f" ({pct:+.0f}%)" if pct is not None else ""


def build_stat_grid_fields(snapshot: Dict[str, Any], market_cap_b: Optional[float]) -> List[tuple]:
    mcap_value = (
        f"{market_cap_b:.0f}B" if market_cap_b is not None and market_cap_b < 1000
        else (f"{market_cap_b / 1000:.1f}T" if market_cap_b is not None else "N/A")
    )
    revenue_value = "N/A"
    if snapshot.get("last_q_revenue") is not None:
        revenue_value = fmt_revenue_compact(snapshot["last_q_revenue"]) + _yoy_suffix(snapshot.get("last_q_yoy_pct"))
    gross_margin_value = (
        f"{snapshot['gross_margin_pct']:.0f}%" if snapshot.get("gross_margin_pct") is not None else "N/A"
    )
    next_quarter_value = "N/A"
    if snapshot.get("next_q_revenue_consensus") is not None:
        next_quarter_value = fmt_revenue_compact(snapshot["next_q_revenue_consensus"]) + _yoy_suffix(snapshot.get("next_q_yoy_pct"))
    fiscal_year_value = "N/A"
    if snapshot.get("fy_revenue_consensus") is not None:
        fiscal_year_value = fmt_revenue_compact(snapshot["fy_revenue_consensus"]) + _yoy_suffix(snapshot.get("fy_yoy_pct"))
    return [
        ("Price", fmt_price(snapshot.get("price"))),
        ("Mkt Cap", mcap_value),
        ("Revenue (YoY)", revenue_value),
        ("Gross Margin", gross_margin_value),
        ("Next Qtr Est (YoY)", next_quarter_value),
        ("FY Est (YoY)", fiscal_year_value),
    ]


def available_stat_fields(fields: List[tuple], limit: Optional[int] = None) -> List[tuple]:
    available = [(label, value) for label, value in fields if value != "N/A"]
    return available[:limit] if limit is not None else available


def render_stat_grid(fields: List[tuple], margin: str = "8px 0 0 0") -> str:
    if not fields:
        return ""
    rows = []
    for start in range(0, len(fields), 3):
        row = fields[start:start + 3]
        rows.append("<tr>" + "".join(render_stat_cell(label, value) for label, value in row) + "</tr>")
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:{margin};border:1px solid {BORDER};border-radius:10px;background:{PANEL_ALT};overflow:hidden;">'
        + "".join(rows)
        + "</table>"
    )


def render_notable_row(event: Any) -> str:
    snap = event.financial_snapshot or {}
    stat_grid = render_stat_grid(
        available_stat_fields(build_stat_grid_fields(snap, event.market_cap_b))
    )

    what_matters = str(getattr(event, "what_matters", "") or "").strip()
    what_matters_html = ""
    if what_matters:
        what_matters_html = (
            f'<div style="margin-top:10px;padding-top:10px;border-top:1px solid {BORDER};">'
            f'<span style="font-size:10px;font-weight:700;color:{MUTED};text-transform:uppercase;letter-spacing:0.4px;">What Matters</span>'
            f'<div style="padding-top:2px;font-size:12px;line-height:18px;color:{INK};">{esc(what_matters)}</div>'
            f'</div>'
        )

    return (
        f'<tr><td style="padding:14px 14px 14px 14px;border-top:1px solid {BORDER};">'
        f'<div style="font-size:13px;font-weight:700;color:{INK};">{mono(event.ticker)} &middot; {esc(event.company)}'
        f'<span style="font-weight:400;color:{MUTED};"> &middot; {esc(event.report_time or "TBD")}</span></div>'
        f'{stat_grid}'
        f'{what_matters_html}'
        "</td></tr>"
    )


def classify_reaction_sentiment(reaction_pct: Optional[float]) -> str:
    if reaction_pct is None:
        return "Unclear"
    if reaction_pct >= 2:
        return "Positive"
    if reaction_pct <= -2:
        return "Negative"
    return "Mixed"


def _sentiment_colors(sentiment: str) -> tuple:
    return {
        "Positive": (POSITIVE, POSITIVE_SOFT),
        "Negative": (NEGATIVE, NEGATIVE_SOFT),
        "Mixed": (NEUTRAL, NEUTRAL_SOFT),
    }.get(sentiment, (MUTED, PANEL_ALT))


def render_digest_row(item: Dict[str, Any]) -> str:
    ticker = str(item.get("ticker", ""))
    company = str(item.get("company", ""))
    report_time = str(item.get("report_time", "") or "TBD")
    reaction_pct = item.get("reaction_pct")
    sentiment = classify_reaction_sentiment(reaction_pct)
    color, soft_color = _sentiment_colors(sentiment)

    if reaction_pct is not None:
        arrow = "&#9650;" if reaction_pct >= 0 else "&#9660;"
        reaction_html = f'<span style="color:{color};font-weight:700;">{arrow} {abs(reaction_pct):.1f}%</span>'
    else:
        reaction_html = f'<span style="color:{MUTED};">N/A</span>'

    highlights = [str(m).strip() for m in item.get("key_metrics", []) or [] if str(m).strip()][:3]
    highlights_html = ""
    if highlights:
        rows = "".join(
            f'<tr><td valign="top" style="padding:2px 6px 2px 0;color:{MUTED};font-size:12px;line-height:18px;width:10px;">&#8226;</td>'
            f'<td valign="top" style="padding:2px 0;color:{INK};font-size:12px;line-height:18px;">{esc(text)}</td></tr>'
            for text in highlights
        )
        highlights_html = f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;">{rows}</table>'

    return (
        f'<tr><td style="padding:14px 14px 14px 14px;border-top:1px solid {BORDER};">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td valign="top">'
        f'<div style="font-size:13px;font-weight:700;color:{INK};">{mono(ticker)} &middot; {esc(company)}'
        f'<span style="font-weight:400;color:{MUTED};"> &middot; {esc(report_time)}</span></div>'
        f'</td>'
        f'<td align="right" valign="top" style="white-space:nowrap;">'
        f'{reaction_html} &nbsp;{render_badge(sentiment, color, soft_color)}'
        f'</td>'
        '</tr></table>'
        f'{highlights_html}'
        "</td></tr>"
    )


def render_post_earnings_digest_email(context: Dict[str, Any]) -> str:
    title = "Daily Post-Earnings Summary"
    generated = context["generated_at"].strftime("%Y-%m-%d %H:%M")
    items = context.get("items", [])

    rows_html = "".join(render_digest_row(item) for item in items)
    no_items = (
        f'<tr><td style="padding:24px 32px 12px 32px;color:{MUTED};font-size:14px;line-height:22px;">'
        f'No coverage universe reporters completed as of this send.'
        f'</td></tr>'
        if not items else ""
    )
    table = (
        f'<tr><td style="padding:0 32px 20px 32px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid {BORDER};border-radius:12px;overflow:hidden;">'
        f'{rows_html}'
        f'</table></td></tr>'
        if items else ""
    )

    return f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:{PAGE_BG};font-family:{FONT_STACK};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE_BG};font-family:{FONT_STACK};">
<tr><td align="center" style="padding:24px 0 32px 0;">
<table role="presentation" align="center" width="640" cellpadding="0" cellspacing="0" style="width:640px;max-width:640px;margin:0 auto;">

  <!-- HEADER -->
  <tr><td style="background:{INK};border-radius:16px 16px 0 0;padding:28px 32px 24px 32px;">
    <div style="font-size:28px;line-height:34px;color:#ffffff;font-weight:700;letter-spacing:-0.3px;">{esc(title)}</div>
    <div style="padding-top:12px;font-size:13px;line-height:20px;color:{INK_SOFT};">{esc(str(len(items)))} covered &nbsp;&middot;&nbsp; Generated {esc(generated)}</div>
  </td></tr>

  <!-- BODY -->
  <tr><td style="background:#ffffff;padding:12px 0 12px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    {table}
    {no_items}
  </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:{PANEL_ALT};border-radius:0 0 16px 16px;padding:18px 32px;border-top:1px solid {BORDER};">
    <div style="font-size:11px;line-height:18px;color:{MUTED};">Example Capital &middot; Earnings Intelligence &middot; {esc(generated)}</div>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def render_weekday_section(section: Dict[str, Any], is_today: bool) -> str:
    events = section.get("events", [])
    if not events:
        return ""
    accent = BRAND if is_today else BORDER
    label_color = INK if is_today else MUTED
    today_badge = (
        f' <span style="display:inline-block;margin-left:6px;padding:2px 8px;border-radius:999px;'
        f'background:{BRAND_SOFT};color:{BRAND};font-size:10px;font-weight:700;letter-spacing:0.4px;">TODAY</span>'
        if is_today else ""
    )
    header = (
        f'<tr><td style="padding:20px 32px 0 32px;">'
        f'<div style="border-left:4px solid {accent};padding-left:10px;margin-bottom:10px;">'
        f'<span style="font-size:12px;line-height:16px;color:{label_color};text-transform:uppercase;font-weight:800;letter-spacing:0.6px;">'
        f'{esc(section["weekday_label"])} &middot; {esc(section["date_label"])}</span>{today_badge}'
        f'</div></td></tr>'
    )
    rows_html = "".join(render_notable_row(e) for e in events)
    table = (
        f'<tr><td style="padding:0 32px 20px 32px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid {BORDER};border-radius:12px;overflow:hidden;">'
        f'{rows_html}'
        f'</table></td></tr>'
    )
    return header + table


def render_weekly_email(context: Dict[str, Any]) -> str:
    title = str(context.get("title", "Weekly Earnings Radar")).strip() or "Weekly Earnings Radar"
    is_daily = bool(context.get("is_daily"))
    week_start = context["week_start"]
    week_end = context["week_end"]
    generated = context["generated_at"].strftime("%Y-%m-%d %H:%M")

    if is_daily:
        today = context.get("today") or week_start
        date_label = f"{today.strftime('%A')}, {today.day} {today.strftime('%B %Y')}" if hasattr(today, "strftime") else str(today)
        sections = context.get("notable_by_weekday", [])
        total_notable = sum(len(section["events"]) for section in sections)

        sections_html = "".join(
            render_weekday_section(section, is_today=(section["date"] == today)) for section in sections
        )
        no_signals = (
            f'<tr><td style="padding:24px 32px 12px 32px;color:{MUTED};font-size:14px;line-height:22px;">'
            f'No coverage universe reporters today.'
            f'</td></tr>'
            if total_notable == 0 else ""
        )

        return f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:{PAGE_BG};font-family:{FONT_STACK};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE_BG};font-family:{FONT_STACK};">
<tr><td align="center" style="padding:24px 0 32px 0;">
<table role="presentation" align="center" width="640" cellpadding="0" cellspacing="0" style="width:640px;max-width:640px;margin:0 auto;">

  <!-- HEADER -->
  <tr><td style="background:{INK};border-radius:16px 16px 0 0;padding:28px 32px 24px 32px;">
    <div style="font-size:10px;line-height:16px;color:{INK_SOFT};text-transform:uppercase;font-weight:700;letter-spacing:1px;">{esc(title)}</div>
    <div style="padding-top:8px;font-size:28px;line-height:34px;color:#ffffff;font-weight:700;letter-spacing:-0.3px;">{esc(date_label)}</div>
    <div style="padding-top:12px;font-size:13px;line-height:20px;color:{INK_SOFT};">{esc(str(total_notable))} notable reporters today &nbsp;&middot;&nbsp; Generated {esc(generated)}</div>
  </td></tr>

  <!-- BODY -->
  <tr><td style="background:#ffffff;padding:0 0 12px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    {sections_html}
    {no_signals}
  </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:{PANEL_ALT};border-radius:0 0 16px 16px;padding:18px 32px;border-top:1px solid {BORDER};">
    <div style="font-size:11px;line-height:18px;color:{MUTED};">Example Capital &middot; Earnings Intelligence &middot; {esc(generated)}</div>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    # ── WEEKLY LAYOUT ────────────────────────────────────────────────────────
    week_today = context.get("today") or week_start
    day_sections = context.get("notable_by_weekday", [])
    day_sections_html = "".join(
        render_weekday_section(section, is_today=(section["date"] == week_today)) for section in day_sections
    )
    coverage_calendar_section = ""
    if any(section["events"] for section in day_sections):
        coverage_calendar_section = f"""
  <tr><td style="background:#ffffff;padding:8px 32px 0 32px;">
    {section_label("Coverage Universe, By Day")}
    <div style="font-size:12px;color:{MUTED};padding-bottom:4px;">Every coverage-universe reporter this week -- nothing dropped for a ranking cutoff</div>
  </td></tr>
  <tr><td style="background:#ffffff;padding:0 0 12px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    {day_sections_html}
  </table>
  </td></tr>"""

    notable_html = "".join(
        f'<div style="padding:0 0 20px 0;">{_render_event_block(event)}</div>'
        for event in context.get("notable_events", [])
    ) or f'<div style="color:{MUTED};font-size:14px;line-height:22px;">No market signals surfaced for the current period.</div>'

    date_range = f"{week_start.isoformat()} – {week_end.isoformat()}"
    total_events = len(context.get("events", []))
    coverage_hits = len([e for e in context.get("events", []) if "coverage universe" in e.score_reasons.lower()])

    has_vol_data = any(e.implied_move_pct is not None for e in context.get("ranked_events", []))
    volatility_section = ""
    if has_vol_data:
        volatility_section = f"""
    <tr><td style="padding:0 32px 28px 32px;">
      <div style="border:1px solid {BORDER};border-radius:14px;overflow:hidden;">
        <div style="background:{PANEL_ALT};padding:16px 20px 12px 20px;">
          {section_label("Volatility Watch")}
          <div style="font-size:12px;color:{MUTED};padding-bottom:8px;">Names where options imply the most movement this week</div>
        </div>
        <div style="padding:16px 20px;">{render_leaderboard(context.get("ranked_events", []))}</div>
      </div>
    </td></tr>"""

    return f"""<!doctype html>
<html>
<body style="margin:0;padding:0;background:{PAGE_BG};font-family:{FONT_STACK};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE_BG};font-family:{FONT_STACK};">
<tr><td align="center" style="padding:24px 0 32px 0;">
<table role="presentation" align="center" width="680" cellpadding="0" cellspacing="0" style="width:680px;max-width:680px;margin:0 auto;">

  <!-- HEADER -->
  <tr><td style="background:{INK};border-radius:16px 16px 0 0;padding:28px 32px 24px 32px;">
    <div style="font-size:10px;line-height:16px;color:{INK_SOFT};text-transform:uppercase;font-weight:700;letter-spacing:1px;">{esc(title)}</div>
    <div style="padding-top:8px;font-size:28px;line-height:34px;color:#ffffff;font-weight:700;letter-spacing:-0.3px;">{esc(date_range)}</div>
    <div style="padding-top:12px;font-size:13px;line-height:20px;color:{INK_SOFT};">{esc(str(total_events))} events &nbsp;&middot;&nbsp; {esc(str(coverage_hits))} in coverage universe &nbsp;&middot;&nbsp; Generated {esc(generated)}</div>
  </td></tr>

  <!-- SUMMARY METRICS -->
  <tr><td style="background:#ffffff;padding:22px 28px 8px 28px;">
    {render_metric_tile_grid(context.get("summary_cards", []))}
  </td></tr>

  {coverage_calendar_section}

  <!-- MARKET READ-THROUGHS -->
  <tr><td style="background:#ffffff;padding:8px 32px 0 32px;border-top:1px solid {BORDER};">
    <div style="padding-top:20px;">{section_label("Key Market Signals This Week")}</div>
  </td></tr>
  <tr><td style="background:#ffffff;padding:0 32px 28px 32px;">
    {notable_html}
  </td></tr>

  {volatility_section}

  <!-- FULL CALENDAR -->
  <tr><td style="background:#ffffff;padding:0 32px 28px 32px;border-top:1px solid {BORDER};">
    <div style="padding-top:24px;">
      {section_label("Full Weekly Calendar")}
      {render_calendar_table(context.get("events", []))}
    </div>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:{PANEL_ALT};border-radius:0 0 16px 16px;padding:18px 32px;border-top:1px solid {BORDER};">
    <div style="font-size:11px;line-height:18px;color:{MUTED};">Example Capital &middot; Earnings Intelligence &middot; {esc(generated)}</div>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def create_email_message(
    subject: str,
    html_body: str,
    text_body: str,
    sender: str,
    recipients: List[str],
    reply_to: str = "",
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def save_email_message(message: EmailMessage, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(message.as_bytes(policy=policy.SMTP))


def send_email_message(
    message: EmailMessage,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str = "",
    smtp_password: str = "",
    use_starttls: bool = True,
    use_ssl: bool = False,
    timeout_seconds: int = 60,
) -> None:
    if not smtp_host:
        raise ValueError("SMTP host is required to send email.")
    if use_ssl and use_starttls:
        raise ValueError("Choose either SSL or STARTTLS, not both.")

    if use_ssl:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout_seconds)
    else:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=timeout_seconds)

    try:
        server.ehlo()
        if use_starttls:
            server.starttls()
            server.ehlo()
        if smtp_username:
            server.login(smtp_username, smtp_password)
        server.send_message(message)
    finally:
        server.quit()
