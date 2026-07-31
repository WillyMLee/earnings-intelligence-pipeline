#!/usr/bin/env python3
"""
Render the per-company earnings deep-dive email: a plain, memo-style research
brief (not a card-based dashboard email), used both the day before a
coverage-universe company reports (pre-earnings) and the day it reports
(post-earnings).
"""

from __future__ import annotations

import html
import os
import re
from email import policy
from email.message import EmailMessage
from typing import Any, Dict, List, Tuple


INK = "#0b0d12"
MUTED = "#4b4f58"
BORDER = "#e3e5ea"
BRAND = "#3454f4"
FONT_STACK = "Aptos,Calibri,'Segoe UI',Arial,sans-serif"
BASE_SIZE = "11pt"
LINE_HEIGHT = "16pt"

_CITATION_RE = re.compile(r"\s*\(\[([^\]]+)\]\((https?://[^\s)]+)\)\)")


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


def _bullet_list(items: List[Dict[str, Any]]) -> str:
    if not items:
        return ""
    rows: List[str] = []
    for item in items:
        rows.append(
            "<tr>"
            f'<td valign="top" style="padding:0 6px 4px 0;color:{MUTED};font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};width:12px;">&#8226;</td>'
            f'<td valign="top" style="padding:0 0 4px 0;color:{INK};font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};">{esc(item.get("text", ""))}</td>'
            "</tr>"
        )
        for child in item.get("children", []) or []:
            rows.append(
                "<tr>"
                f'<td></td>'
                f'<td valign="top" style="padding:0 0 4px 0;">'
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
                f'<td valign="top" style="padding:0 6px 4px 4px;color:{MUTED};font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};width:12px;">&#9702;</td>'
                f'<td valign="top" style="padding:0 0 4px 0;color:{INK};font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};">{esc(child)}</td>'
                f'</tr></table>'
                f'</td>'
                "</tr>"
            )
    return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">' + "".join(rows) + "</table>"


def _section_heading(text: str) -> str:
    return f'<div style="padding:20px 0 6px 0;font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};font-weight:700;color:{INK};">{esc(text)}</div>'


def render_deep_dive_email(context: Dict[str, Any]) -> str:
    company = esc(context.get("company", ""))
    quarter = esc(context.get("quarter", ""))
    brief_label_raw = context.get("brief_label", "Pre-Earnings Summary")
    brief_label = esc(brief_label_raw)
    reaction_line = str(context.get("reaction_line", "") or "").strip()

    all_sources: List[str] = []

    intro_cleaned, intro_sources = strip_citations_flat([str(context.get("intro", ""))])
    all_sources.extend(intro_sources)
    intro_html = esc(intro_cleaned[0]) if intro_cleaned else ""

    highlights, hl_sources = strip_citations_nested(context.get("financial_highlights", []))
    all_sources.extend(hl_sources)
    highlights_html = _bullet_list(highlights)

    sections_html = ""
    for section in context.get("sections", []):
        heading = esc(section.get("heading", ""))
        bullets, sec_sources = strip_citations_nested(section.get("bullets", []))
        all_sources.extend(sec_sources)
        sections_html += _section_heading(heading) + _bullet_list(bullets)

    is_post = "post" in brief_label_raw.lower()
    key_metrics_label = "Key highlights" if is_post else "Key metrics to watch"
    key_metrics_html = ""
    key_metrics, km_sources = strip_citations_flat(context.get("key_metrics", []))
    all_sources.extend(km_sources)
    if key_metrics:
        key_metrics_html = _section_heading(key_metrics_label) + _bullet_list(
            [{"text": item, "children": []} for item in key_metrics]
        )

    sources_html = ""
    deduped_sources = list(dict.fromkeys(all_sources))
    if deduped_sources:
        source_rows = "".join(
            f'<div style="padding-bottom:2px;font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};">'
            f'<a href="{esc(url)}" style="color:{BRAND};text-decoration:none;">{esc(url)}</a></div>'
            for url in deduped_sources[:10]
        )
        sources_html = _section_heading("Sources") + source_rows

    reaction_html = (
        f'<tr><td style="padding-bottom:6px;font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};color:{INK};font-weight:700;">{esc(reaction_line)}</td></tr>'
        if reaction_line else ""
    )

    official_links = context.get("official_links") or {}
    link_labels = [
        ("press_release", "Press Release"),
        ("investor_deck", "Investor Deck"),
        ("transcript", "Transcript"),
    ]
    link_items = [
        f'<a href="{esc(official_links[key])}" style="color:{BRAND};text-decoration:none;font-weight:700;">{esc(label)}</a>'
        for key, label in link_labels
        if official_links.get(key)
    ]
    official_links_html = (
        f'<tr><td style="padding-bottom:8px;font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};">{" &nbsp;&middot;&nbsp; ".join(link_items)}</td></tr>'
        if link_items else ""
    )

    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#ffffff;font-family:{FONT_STACK};font-size:{BASE_SIZE};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;font-family:{FONT_STACK};font-size:{BASE_SIZE};">
<tr><td align="center" style="padding:20px 16px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="width:640px;max-width:640px;">

  <tr><td style="padding-bottom:8px;font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};font-weight:700;color:{INK};">
    {company} {quarter} {brief_label}
  </td></tr>
  {official_links_html}

  {reaction_html}
  <tr><td style="padding-bottom:4px;font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};color:{INK};">{intro_html}</td></tr>

  <tr><td>
    {_section_heading("Financial highlights")}
    {highlights_html}
  </td></tr>

  <tr><td>
    {sections_html}
  </td></tr>

  <tr><td>
    {key_metrics_html}
  </td></tr>

  <tr><td>
    {sources_html}
  </td></tr>

  <tr><td style="padding-top:16px;border-top:1px solid {BORDER};margin-top:12px;">
    <div style="padding-top:8px;font-size:{BASE_SIZE};line-height:{LINE_HEIGHT};color:{MUTED};">
      Figures are Street consensus/guidance unless noted as reported. This is not investment advice.
    </div>
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
    lines.append(f"# {company} {quarter} {brief_label}")
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
    if context.get("reaction_line"):
        lines.append(f"**{context['reaction_line']}**")
        lines.append("")
    intro_cleaned, intro_sources = strip_citations_flat([str(context.get("intro", ""))])
    all_sources.extend(intro_sources)
    if intro_cleaned and intro_cleaned[0]:
        lines.append(intro_cleaned[0])
        lines.append("")
    highlights, hl_sources = strip_citations_nested(context.get("financial_highlights", []))
    all_sources.extend(hl_sources)
    lines.append("## Financial highlights")
    lines.extend(_markdown_bullets(highlights))
    lines.append("")
    for section in context.get("sections", []):
        bullets, sec_sources = strip_citations_nested(section.get("bullets", []))
        all_sources.extend(sec_sources)
        lines.append(f"## {section.get('heading', '')}")
        lines.extend(_markdown_bullets(bullets))
        lines.append("")
    key_metrics, km_sources = strip_citations_flat(context.get("key_metrics", []))
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
