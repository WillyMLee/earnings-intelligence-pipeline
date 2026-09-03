#!/usr/bin/env python3
"""
Render the per-company earnings deep-dive email in the same polished visual
system as the daily and weekly earnings-intelligence briefs. The renderer is
used both before and after a coverage-universe company reports.
"""

from __future__ import annotations

import html
import os
import re
from email import policy
from email.message import EmailMessage
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse


INK = "#0b0d12"
INK_SOFT = "#9aa3b2"
MUTED = "#63697a"
BORDER = "#e3e5ea"
BRAND = "#3454f4"
BRAND_SOFT = "#e8ecfe"
POSITIVE = "#12805c"
POSITIVE_SOFT = "#e3f5ee"
NEGATIVE = "#c23b4b"
NEGATIVE_SOFT = "#fbe9ec"
NEUTRAL = "#a56b00"
NEUTRAL_SOFT = "#faf1de"
SOFT = "#f7f8fa"
PAGE_BG = "#f5f6f8"
FONT_STACK = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
BASE_SIZE = "13px"
LINE_HEIGHT = "21px"

_CITATION_RE = re.compile(r"\s*\(\[([^\]]+)\]\((https?://[^\s)]+)\)\)")


def _compact_text(value: Any, max_chars: int = 420) -> str:
    """Keep generated prose compact and prevent raw tool/Markdown output
    from leaking into an email paragraph."""
    text = html.unescape(str(value or "")).replace("\r", "\n")
    text = re.split(r"\n\s*#{1,6}\s+", text, maxsplit=1)[0]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    text = paragraphs[0] if paragraphs else text
    text = re.sub(r"(?m)^\s*[-*]\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    shortened = text[: max_chars + 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return shortened + "…"


def esc(value: Any) -> str:
    # Web-search synthesis occasionally echoes already-HTML-escaped text
    # scraped from a page's raw HTML (e.g. a literal "&amp;"). Unescape first
    # so it doesn't get double-encoded into "&amp;amp;".
    text = "" if value is None else str(value)
    return html.escape(html.unescape(text))


def parse_recipients(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def build_email_subject(company: str, ticker: str, quarter: str, brief_label: str = "Pre-Earnings Summary") -> str:
    # The ticker stays in the subject line (useful for scanning an inbox list)
    # even though the in-body title drops it for a cleaner, more prose-like read.
    return f"{company} ({ticker}) {quarter} | {brief_label}"


def _strip_text_citations(text: str, urls: List[str]) -> str:
    for match in _CITATION_RE.finditer(text):
        url = match.group(2)
        if url not in urls:
            urls.append(url)
    return _CITATION_RE.sub("", text).strip()


def strip_citations_nested(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Web-search synthesis embeds inline markdown citations like
    '([ig.com](https://...))'. Strip them from bullet/child text (keeps prose
    readable) and collect the URLs into a separate list for a Sources footer
    instead. Operates on the nested {"text", "children"} bullet shape."""
    urls: List[str] = []
    cleaned: List[Dict[str, Any]] = []
    for item in items:
        text = _strip_text_citations(str(item.get("text", "")), urls)
        children = [_strip_text_citations(str(c), urls) for c in item.get("children", []) or []]
        cleaned.append({"text": text, "children": children})
    return cleaned, urls


def strip_citations_flat(items: List[str]) -> Tuple[List[str], List[str]]:
    urls: List[str] = []
    cleaned = [_strip_text_citations(str(item), urls) for item in items]
    return cleaned, urls


def _bullet_text_html(value: Any) -> str:
    text = _compact_text(value, max_chars=360)
    prefix, separator, rest = text.partition(":")
    if separator and 2 <= len(prefix) <= 72:
        return f"<strong>{esc(prefix)}</strong>:{esc(rest)}"
    return esc(text)


def _bullet_list(items: List[Dict[str, Any]], limit: int = 6, child_limit: int = 2) -> str:
    if not items:
        return ""
    rows: List[str] = []
    for item in items[:limit]:
        rows.append(
            "<tr>"
            f'<td valign="top" style="padding:3px 9px 7px 0;color:{BRAND};font-size:10px;line-height:{LINE_HEIGHT};width:12px;">&#9632;</td>'
            f'<td valign="top" style="padding:0 0 9px 0;color:{INK};font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};">{_bullet_text_html(item.get("text", ""))}</td>'
            "</tr>"
        )
        for child in (item.get("children", []) or [])[:child_limit]:
            rows.append(
                "<tr>"
                f'<td></td>'
                f'<td valign="top" style="padding:0 0 4px 0;">'
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
                f'<td valign="top" style="padding:1px 8px 5px 4px;color:{MUTED};font-size:12px;line-height:{LINE_HEIGHT};width:12px;">&#8226;</td>'
                f'<td valign="top" style="padding:0 0 7px 0;color:{MUTED};font-size:12px;line-height:19px;">{esc(_compact_text(child, 300))}</td>'
                f'</tr></table>'
                f'</td>'
                "</tr>"
            )
    return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">' + "".join(rows) + "</table>"


def _section_heading(text: str) -> str:
    return (
        f'<div style="padding:0 0 11px 0;margin-bottom:14px;border-bottom:1px solid {BORDER};">'
        f'<span style="font-size:11px;line-height:16px;color:{MUTED};text-transform:uppercase;'
        f'font-weight:800;letter-spacing:0.8px;">{esc(text)}</span></div>'
    )


def _section_card(title: str, body: str, accent: str = BRAND) -> str:
    if not body:
        return ""
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="width:100%;border:1px solid {BORDER};border-radius:14px;background:#ffffff;">'
        f'<tr><td style="padding:20px 22px 11px 22px;border-left:4px solid {accent};border-radius:14px;">'
        f'{_section_heading(title)}{body}</td></tr></table>'
    )


def _key_figures_html(items: List[Dict[str, Any]]) -> str:
    figures = [item for item in items if item.get("label") and item.get("value")][:6]
    if not figures:
        return ""
    rows: List[str] = []
    for start in range(0, len(figures), 3):
        cells: List[str] = []
        for item in figures[start : start + 3]:
            cells.append(
                '<td class="metric-cell" width="33.33%" valign="top" style="padding:0 6px 12px 6px;">'
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{SOFT};border:1px solid {BORDER};border-radius:12px;">'
                '<tr><td valign="top" style="height:76px;padding:15px 14px 13px 14px;">'
                f'<div style="font-size:10px;line-height:14px;color:{MUTED};text-transform:uppercase;font-weight:800;letter-spacing:0.5px;">{esc(item["label"])}</div>'
                f'<div style="padding-top:7px;font-size:18px;line-height:23px;font-weight:750;color:{INK};letter-spacing:-0.2px;">{esc(item["value"])}</div>'
                "</td></tr></table></td>"
            )
        while len(cells) < 3:
            cells.append('<td width="33.33%"></td>')
        rows.append(f'<tr>{"".join(cells)}</tr>')
    return (
        f'{_section_heading("Key figures")}'
        '<table class="metric-grid" role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 -6px;">'
        f'{"".join(rows)}</table>'
    )


def _reaction_html(reaction_line: str, reaction_pct: Any) -> str:
    if not reaction_line:
        return ""
    try:
        value = float(reaction_pct)
    except (TypeError, ValueError):
        lower = reaction_line.lower()
        value = -2.0 if "down" in lower else (2.0 if "up" in lower else 0.0)
    if value >= 2:
        label, color, soft = "Positive reaction", POSITIVE, POSITIVE_SOFT
    elif value <= -2:
        label, color, soft = "Negative reaction", NEGATIVE, NEGATIVE_SOFT
    else:
        label, color, soft = "Muted reaction", NEUTRAL, NEUTRAL_SOFT
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{soft};border-radius:12px;">'
        f'<tr><td style="padding:15px 18px;border-left:4px solid {color};border-radius:12px;">'
        f'<div style="font-size:10px;line-height:14px;color:{color};font-weight:800;text-transform:uppercase;letter-spacing:0.6px;">{label}</div>'
        f'<div style="padding-top:4px;font-size:14px;line-height:21px;color:{INK};font-weight:750;">{esc(reaction_line)}</div>'
        '</td></tr></table>'
    )


def _estimate_scoreboard_html(items: List[Dict[str, Any]]) -> str:
    comparisons = [item for item in items if isinstance(item, dict) and item.get("metric")][:5]
    if not comparisons:
        return ""
    rows: List[str] = []
    for item in comparisons:
        variance_text = str(item.get("variance", "") or "")
        variance_lower = variance_text.lower().strip()
        variance_color = (
            NEGATIVE if variance_lower.startswith("-") or any(word in variance_lower for word in ("miss", "below"))
            else (NEUTRAL if any(word in variance_lower for word in ("inline", "in line", "flat")) else POSITIVE)
        )
        source_url = str(item.get("source_url", "") or "").strip()
        source_label = str(item.get("estimate_source", "") or "Estimate source").strip()
        source_html = (
            f'<a href="{esc(source_url)}" style="color:{BRAND};text-decoration:none;font-weight:750;">{esc(source_label)}</a>'
            if source_url else esc(source_label)
        )
        metadata = " &nbsp;&middot;&nbsp; ".join(
            part for part in (esc(item.get("period", "")), esc(item.get("estimate_as_of", ""))) if part
        )
        metadata_html = (
            f'<span style="font-size:10px;color:{MUTED};font-weight:600;"> &nbsp;&middot;&nbsp; {metadata}</span>'
            if metadata else ""
        )
        rows.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;background:{SOFT};border:1px solid {BORDER};border-radius:11px;">'
            f'<tr><td colspan="3" style="padding:13px 14px 8px 14px;font-size:13px;line-height:18px;color:{INK};font-weight:800;">{esc(item.get("metric", ""))}'
            f'{metadata_html}</td></tr>'
            '<tr>'
            f'<td class="comparison-cell" width="34%" valign="top" style="padding:5px 14px 13px 14px;"><div style="font-size:9px;color:{MUTED};font-weight:800;text-transform:uppercase;letter-spacing:0.5px;">Reported / guide</div><div style="padding-top:4px;font-size:16px;line-height:21px;color:{INK};font-weight:800;">{esc(item.get("reported", ""))}</div></td>'
            f'<td class="comparison-cell" width="33%" valign="top" style="padding:5px 14px 13px 14px;border-left:1px solid {BORDER};"><div style="font-size:9px;color:{MUTED};font-weight:800;text-transform:uppercase;letter-spacing:0.5px;">Estimate</div><div style="padding-top:4px;font-size:16px;line-height:21px;color:{INK};font-weight:800;">{esc(item.get("estimate", ""))}</div></td>'
            f'<td class="comparison-cell" width="33%" valign="top" style="padding:5px 14px 13px 14px;border-left:1px solid {BORDER};"><div style="font-size:9px;color:{MUTED};font-weight:800;text-transform:uppercase;letter-spacing:0.5px;">Variance</div><div style="padding-top:4px;font-size:16px;line-height:21px;color:{variance_color};font-weight:800;">{esc(variance_text)}</div></td>'
            '</tr>'
            f'<tr><td colspan="3" style="padding:0 14px 12px 14px;font-size:10px;line-height:15px;color:{MUTED};">Source: {source_html}</td></tr>'
            '</table>'
        )
    return _section_card("Estimate scoreboard", "".join(rows))


def _valuation_reference_html(item: Dict[str, Any]) -> str:
    if not isinstance(item, dict) or not item.get("ev_cy_revenue"):
        return ""
    fields = [
        ("Enterprise value", item.get("enterprise_value", "")),
        ("CY revenue estimate", item.get("cy_revenue", "")),
        ("EV / CY revenue", item.get("ev_cy_revenue", "")),
    ]
    cells = "".join(
        f'<td class="valuation-cell" width="33.33%" valign="top" style="padding:0 6px 10px 6px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BRAND_SOFT};border-radius:10px;">'
        f'<tr><td style="height:64px;padding:13px 12px;"><div style="font-size:9px;line-height:13px;color:{BRAND};font-weight:800;text-transform:uppercase;letter-spacing:0.5px;">{label}</div>'
        f'<div style="padding-top:5px;font-size:16px;line-height:21px;color:{INK};font-weight:800;">{esc(value)}</div></td></tr></table></td>'
        for label, value in fields
    )
    source_url = str(item.get("source_url", "") or "").strip()
    source_label = str(item.get("source", "") or "Valuation source").strip()
    source_html = (
        f'<a href="{esc(source_url)}" style="color:{BRAND};text-decoration:none;font-weight:750;">{esc(source_label)}</a>'
        if source_url else esc(source_label)
    )
    body = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 -6px;"><tr>{cells}</tr></table>'
        f'<div style="padding:2px 0 3px 0;font-size:11px;line-height:17px;color:{MUTED};"><strong style="color:{INK};">Basis:</strong> {esc(item.get("basis", ""))}</div>'
        f'<div style="padding:3px 0 4px 0;font-size:10px;line-height:15px;color:{MUTED};">As of {esc(item.get("as_of", ""))} &nbsp;&middot;&nbsp; {source_html}</div>'
    )
    return _section_card("Valuation reference", body, NEUTRAL)


def render_deep_dive_email(context: Dict[str, Any]) -> str:
    company = esc(context.get("company", ""))
    ticker = esc(context.get("ticker", ""))
    quarter = esc(context.get("quarter", ""))
    brief_label_raw = context.get("brief_label", "Pre-Earnings Summary")
    brief_label = esc(brief_label_raw)
    reaction_line = str(context.get("reaction_line", "") or "").strip()

    all_sources: List[str] = []

    intro_cleaned, intro_sources = strip_citations_flat([str(context.get("intro", ""))])
    all_sources.extend(intro_sources)
    intro_html = esc(_compact_text(intro_cleaned[0], 620)) if intro_cleaned else ""

    highlights, hl_sources = strip_citations_nested(context.get("financial_highlights", []))
    all_sources.extend(hl_sources)
    highlights_html = _bullet_list(highlights, limit=6)

    sections_html = ""
    for section in context.get("sections", [])[:3]:
        heading = str(section.get("heading", "") or "").strip()
        bullets, sec_sources = strip_citations_nested(section.get("bullets", []))
        all_sources.extend(sec_sources)
        section_body = _bullet_list(bullets, limit=4)
        if heading and section_body:
            sections_html += f'<div class="content-gap" style="height:14px;line-height:14px;">&nbsp;</div>{_section_card(heading, section_body)}'

    is_post = "post" in brief_label_raw.lower()
    key_metrics_label = "Key highlights" if is_post else "Key metrics to watch"
    key_metrics_html = ""
    key_metrics, km_sources = strip_citations_flat(context.get("key_metrics", [])[:6])
    all_sources.extend(km_sources)
    if key_metrics:
        key_metrics_html = _section_card(
            key_metrics_label,
            _bullet_list([{"text": item, "children": []} for item in key_metrics]),
            NEUTRAL if not is_post else BRAND,
        )

    for comparison in context.get("estimate_comparisons", []) or []:
        if isinstance(comparison, dict) and comparison.get("source_url"):
            all_sources.append(str(comparison["source_url"]))
    valuation_source_url = (context.get("valuation_reference") or {}).get("source_url")
    if valuation_source_url:
        all_sources.append(str(valuation_source_url))

    sources_html = ""
    deduped_sources = list(dict.fromkeys(all_sources))
    if deduped_sources:
        source_rows = "".join(
            f'<div style="padding-bottom:2px;font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};">'
            f'<a href="{esc(url)}" style="color:{BRAND};text-decoration:none;font-weight:700;">{esc(urlparse(url).netloc.replace("www.", "") or url)}</a></div>'
            for url in deduped_sources[:10]
        )
        sources_html = _section_card("Additional sources", source_rows, MUTED)

    official_links = context.get("official_links") or {}
    link_labels = [
        ("press_release", "Press Release"),
        ("investor_deck", "Investor Deck"),
        ("transcript", "Transcript"),
    ]
    link_items = [
        f'<a href="{esc(official_links[key])}" style="display:inline-block;margin:0 7px 7px 0;padding:8px 12px;border:1px solid {BORDER};border-radius:8px;background:#ffffff;color:{BRAND};text-decoration:none;font-size:12px;line-height:16px;font-weight:750;">{esc(label)} &nbsp;&#8594;</a>'
        for key, label in link_labels
        if official_links.get(key)
    ]
    official_links_html = (
        f'<div style="padding-top:14px;">{"".join(link_items)}</div>'
        if link_items else ""
    )
    report_date = esc(context.get("report_date_label", ""))
    key_figures_html = _key_figures_html(context.get("key_figures", []) or [])
    estimate_comparisons = context.get("estimate_comparisons", []) or []
    estimate_scoreboard_html = _estimate_scoreboard_html(estimate_comparisons)
    valuation_reference = context.get("valuation_reference", {}) or {}
    valuation_html = _valuation_reference_html(valuation_reference)
    reaction_html = _reaction_html(reaction_line, context.get("reaction_pct"))
    mode_label = "Post-earnings" if is_post else "Pre-earnings"
    correction_badge = (
        f'<span style="display:inline-block;margin-left:8px;padding:3px 8px;border-radius:999px;background:{BRAND};color:#ffffff;font-size:9px;line-height:13px;font-weight:800;letter-spacing:0.6px;vertical-align:middle;">CORRECTION</span>'
        if "correction" in brief_label_raw.lower() else ""
    )
    intro_card = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BRAND_SOFT};border-radius:12px;">'
        f'<tr><td style="padding:17px 19px;">'
        f'<div style="font-size:10px;line-height:14px;color:{BRAND};font-weight:800;text-transform:uppercase;letter-spacing:0.7px;">Executive read</div>'
        f'<div style="padding-top:6px;font-size:14px;line-height:22px;color:{INK};">{intro_html}</div>'
        '</td></tr></table>' if intro_html else ""
    )
    highlights_card = _section_card("Financial highlights", highlights_html)

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    @media only screen and (max-width:620px) {{
      .email-shell {{ width:100% !important; }}
      .outer-pad {{ padding:0 !important; }}
      .header-pad {{ padding:24px 20px 22px !important; }}
      .body-pad {{ padding:22px 16px 24px !important; }}
      .metric-cell {{ display:block !important;width:100% !important;box-sizing:border-box !important; }}
      .comparison-cell {{ padding-left:8px !important;padding-right:8px !important; }}
      .valuation-cell {{ display:block !important;width:100% !important;box-sizing:border-box !important;border-left:0 !important; }}
      .metric-grid {{ margin:0 !important; }}
      .email-title {{ font-size:25px !important;line-height:30px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:{PAGE_BG};font-family:{FONT_STACK};font-size:{BASE_SIZE};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE_BG};font-family:{FONT_STACK};font-size:{BASE_SIZE};">
<tr><td class="outer-pad" align="center" style="padding:24px 12px 32px 12px;">
<table class="email-shell" role="presentation" align="center" width="680" cellpadding="0" cellspacing="0" style="width:680px;max-width:680px;margin:0 auto;">

  <!-- BRANDED HEADER -->
  <tr><td class="header-pad" style="background:{INK};border-radius:16px 16px 0 0;padding:28px 32px 25px 32px;">
    <div style="font-size:10px;line-height:16px;color:{INK_SOFT};text-transform:uppercase;font-weight:800;letter-spacing:1px;">Earnings intelligence &nbsp;&middot;&nbsp; {esc(mode_label)}{correction_badge}</div>
    <div class="email-title" style="padding-top:9px;font-size:30px;line-height:36px;color:#ffffff;font-weight:800;letter-spacing:-0.45px;">{company or ticker}</div>
    <div style="padding-top:8px;font-size:13px;line-height:20px;color:{INK_SOFT};"><span style="color:#ffffff;font-weight:750;">{ticker}</span> &nbsp;&middot;&nbsp; {quarter}{f' &nbsp;&middot;&nbsp; {report_date}' if report_date else ''}</div>
  </td></tr>

  <!-- ANALYSIS BODY -->
  <tr><td class="body-pad" style="background:#ffffff;padding:24px 28px 30px 28px;">
    {reaction_html}
    {f'<div style="height:14px;line-height:14px;">&nbsp;</div>' if reaction_html and intro_card else ''}
    {intro_card}
    {official_links_html}

    {f'<div style="height:20px;line-height:20px;">&nbsp;</div>{key_figures_html}' if key_figures_html else ''}
    {f'<div style="height:12px;line-height:12px;">&nbsp;</div>{estimate_scoreboard_html}' if estimate_scoreboard_html else ''}
    {f'<div style="height:14px;line-height:14px;">&nbsp;</div>{valuation_html}' if valuation_html else ''}
    {f'<div style="height:12px;line-height:12px;">&nbsp;</div>{highlights_card}' if highlights_card else ''}
    {sections_html}
    {f'<div style="height:14px;line-height:14px;">&nbsp;</div>{key_metrics_html}' if key_metrics_html else ''}
    {f'<div style="height:14px;line-height:14px;">&nbsp;</div>{sources_html}' if sources_html else ''}
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:{SOFT};border-radius:0 0 16px 16px;padding:17px 28px 19px 28px;border-top:1px solid {BORDER};">
    <div style="font-size:11px;line-height:18px;color:{MUTED};">Earnings Intelligence &middot; Figures are Street consensus/guidance unless noted as reported. This is not investment advice.</div>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _markdown_bullets(items: List[Dict[str, Any]], indent: str = "") -> List[str]:
    lines: List[str] = []
    for item in items:
        lines.append(f"{indent}- {item.get('text', '')}")
        for child in item.get("children", []) or []:
            lines.append(f"{indent}  - {child}")
    return lines


def render_markdown_summary(context: Dict[str, Any]) -> str:
    lines: List[str] = []
    all_sources: List[str] = []
    company = context.get("company", "")
    quarter = context.get("quarter", "")
    brief_label = context.get("brief_label", "Pre-Earnings Summary")
    ticker = context.get("ticker", "")
    lines.append(f"# {ticker or company} {quarter} {brief_label}")
    lines.append("")
    if context.get("report_date_label"):
        lines.append(str(context["report_date_label"]))
        lines.append("")
    official_links = context.get("official_links") or {}
    link_bits = [
        f"[{label}]({official_links[key]})"
        for key, label in (("press_release", "Press Release"), ("investor_deck", "Investor Deck"), ("transcript", "Transcript"))
        if official_links.get(key)
    ]
    if link_bits:
        lines.append(" | ".join(link_bits))
        lines.append("")
    figures = [item for item in context.get("key_figures", []) or [] if item.get("label") and item.get("value")][:6]
    if figures:
        lines.append(" | ".join(f"**{item['label']}:** {item['value']}" for item in figures))
        lines.append("")
    if context.get("reaction_line"):
        lines.append(f"**{context['reaction_line']}**")
        lines.append("")
    intro_cleaned, intro_sources = strip_citations_flat([str(context.get("intro", ""))])
    all_sources.extend(intro_sources)
    if intro_cleaned and intro_cleaned[0]:
        lines.append(_compact_text(intro_cleaned[0], 620))
        lines.append("")
    comparisons = [item for item in context.get("estimate_comparisons", []) or [] if isinstance(item, dict)]
    if comparisons:
        lines.append("## Estimate scoreboard")
        for item in comparisons[:5]:
            lines.append(
                f"- **{item.get('metric', '')}:** {item.get('reported', '')} vs. "
                f"{item.get('estimate', '')}; {item.get('variance', '')} "
                f"({item.get('estimate_source', '')}, {item.get('estimate_as_of', '')})"
            )
            if item.get("source_url"):
                all_sources.append(str(item["source_url"]))
        lines.append("")
    valuation = context.get("valuation_reference") or {}
    if isinstance(valuation, dict) and valuation.get("ev_cy_revenue"):
        lines.append("## Valuation reference")
        lines.append(
            f"- Enterprise value: {valuation.get('enterprise_value', '')}\n"
            f"- CY revenue estimate: {valuation.get('cy_revenue', '')}\n"
            f"- EV / CY revenue: {valuation.get('ev_cy_revenue', '')}\n"
            f"- Basis: {valuation.get('basis', '')}\n"
            f"- As of: {valuation.get('as_of', '')}; source: {valuation.get('source', '')}"
        )
        if valuation.get("source_url"):
            all_sources.append(str(valuation["source_url"]))
        lines.append("")
    highlights, hl_sources = strip_citations_nested(context.get("financial_highlights", []))
    all_sources.extend(hl_sources)
    lines.append("## Financial highlights")
    lines.extend(_markdown_bullets(highlights[:6]))
    lines.append("")
    for section in context.get("sections", [])[:3]:
        bullets, sec_sources = strip_citations_nested(section.get("bullets", []))
        all_sources.extend(sec_sources)
        lines.append(f"## {section.get('heading', '')}")
        lines.extend(_markdown_bullets(bullets[:4]))
        lines.append("")
    key_metrics, km_sources = strip_citations_flat(context.get("key_metrics", [])[:6])
    all_sources.extend(km_sources)
    if key_metrics:
        lines.append("## " + ("Key highlights" if "post" in brief_label.lower() else "Key metrics to watch"))
        for item in key_metrics:
            lines.append(f"- {item}")
        lines.append("")
    deduped_sources = list(dict.fromkeys(all_sources))
    if deduped_sources:
        lines.append("## Sources")
        for url in deduped_sources[:10]:
            lines.append(f"- {url}")
        lines.append("")
    return "\n".join(lines)


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
