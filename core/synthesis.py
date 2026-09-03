#!/usr/bin/env python3
"""LLM-based narrative synthesis for earnings emails.

Turns collected research snippets + hard financial facts into grounded
"what matters" / "market read-through" analyst commentary -- the kind of
editorial synthesis a template can't produce by itself. Every call is
strictly grounded in the facts/snippets it's given; the model is instructed
not to invent numbers, names, or events. Callers should treat a {} return as
"synthesis unavailable" and fall back to template text, not treat it as an
error to surface to the reader.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import date as _date
from html.parser import HTMLParser
from io import BytesIO
from typing import Any, Dict, List, Optional


_FISCAL_PERIOD_PATTERNS = (
    re.compile(r"\bFY\s*['’]?(\d{2,4})\s*[-–—:/ ]*Q([1-4])\b", re.IGNORECASE),
    re.compile(r"\bQ([1-4])\s*[-–—:/ ]*(?:FY\s*)?['’]?(\d{2,4})\b", re.IGNORECASE),
)

_VERIFIED_RELEASE_URLS = {
    ("WMT", "2026-08-20"): (
        "https://corporate.walmart.com/news/2026/08/20/"
        "walmart-releases-q2-fy27-earnings"
    ),
    ("AVGO", "2026-09-02"): (
        "https://investors.broadcom.com/news-releases/news-release-details/"
        "broadcom-inc-announces-third-quarter-fiscal-year-2026-financial"
    ),
    ("HPE", "2026-09-02"): (
        "https://www.sec.gov/Archives/edgar/data/1645590/"
        "000164559026000078/ex-991x922026x8k.htm"
    ),
    ("SNOW", "2026-09-02"): (
        "https://www.sec.gov/Archives/edgar/data/1640147/"
        "000164014726000033/fy2027q2earnings.htm"
    ),
}


class _ReleaseTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth and data.strip():
            self.parts.append(data.strip())


def _html_release_text(html: str, limit: int = 30_000) -> str:
    parser = _ReleaseTextParser()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()[:limit]


def _fetch_release_page_text(url: str) -> str:
    if not url.lower().startswith("https://"):
        return ""
    request = urllib.request.Request(url, headers={"User-Agent": "EarningsIntelligence/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = str(response.headers.get("content-type") or "").lower()
            payload = response.read(5_000_000)
    except Exception as exc:
        print(f"[synthesis] Direct official-release fetch failed for {url}: {exc}", flush=True)
        return ""
    if "html" in content_type:
        return _html_release_text(payload.decode("utf-8", errors="replace"))
    if "pdf" in content_type or url.lower().split("?", 1)[0].endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(payload))
            return re.sub(
                r"\s+",
                " ",
                " ".join((page.extract_text() or "") for page in reader.pages),
            ).strip()[:30_000]
        except Exception as exc:
            print(f"[synthesis] Official PDF extraction failed for {url}: {exc}", flush=True)
    return ""


def _normalize_fiscal_period(match: re.Match[str], pattern_index: int) -> str:
    year, quarter = match.groups() if pattern_index == 0 else (match.group(2), match.group(1))
    if len(year) == 2:
        year = f"20{year}"
    return f"Q{quarter} FY{year}"


def _extract_official_fiscal_period(
    results: List[Dict[str, Any]], report_date: str, company: str
) -> str:
    """Pick a fiscal period only when a current, company-specific release result supports it."""
    company_tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", company)
        if len(token) >= 4 and token.lower() not in {"company", "corporation", "incorporated", "holdings"}
    }
    scores: Dict[str, int] = {}
    for item in results:
        title = str(item.get("title") or "")
        snippet = str(item.get("snippet") or "")
        url = str(item.get("url") or "")
        combined = f"{title} {snippet} {url}"
        lower = combined.lower()
        if company_tokens and not any(token in lower for token in company_tokens):
            continue
        freshness = 0
        if report_date and (item.get("published_date") == report_date or report_date in combined):
            freshness += 5
        if any(term in lower for term in ("earnings release", "financial results", "quarterly results")):
            freshness += 2
        if any(token in url.lower() for token in company_tokens):
            freshness += 2
        for index, pattern in enumerate(_FISCAL_PERIOD_PATTERNS):
            for match in pattern.finditer(combined):
                label = _normalize_fiscal_period(match, index)
                scores[label] = max(scores.get(label, 0), freshness)
    if not scores:
        return ""
    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    if ranked[0][1] < 4 or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return ""
    return ranked[0][0]


def _official_release_grounding(
    ticker: str, company: str, report_date: str
) -> Dict[str, str]:
    """Run the configured LLMLayer-first discovery cascade for the current release."""
    try:
        from core.research import filter_results_for_entity, run_research_query_cascade

        research = run_research_query_cascade(
            query=(
                f"{company} ({ticker}) {report_date} official earnings release financial results "
                "revenue EPS fiscal quarter"
            ),
            max_results_per_provider=5,
            # A provider returning stale prior-quarter rows is not success for
            # same-day official-release discovery. LLMLayer still runs first,
            # but keep cascading until a current issuer result is available.
            min_results_before_tavily=1_000,
            min_results_before_tinyfish=1_000,
        )
        results = filter_results_for_entity(research.get("results", []), company, ticker)[:6]
    except Exception as exc:
        print(f"[synthesis] Official-release discovery failed for {ticker}: {exc}", flush=True)
        return {}

    evidence_lines = []
    for item in results:
        evidence_lines.append(
            " | ".join(
                value
                for value in (
                    str(item.get("title") or "").strip(),
                    str(item.get("url") or "").strip(),
                    str(item.get("snippet") or "").strip(),
                )
                if value
            )
        )
    fiscal_period = _extract_official_fiscal_period(results, report_date, company)
    source_text = ""
    source_url = ""
    date_variants = {report_date, report_date.replace("-", "/")}
    for item in results:
        combined = " ".join(str(item.get(key) or "") for key in ("title", "snippet", "url"))
        is_current = bool(
            report_date
            and (
                item.get("published_date") == report_date
                or any(variant and variant in combined for variant in date_variants)
            )
        )
        item_period = _extract_official_fiscal_period([item], report_date, company)
        is_period_match = bool(fiscal_period and item_period == fiscal_period)
        if not (is_current or is_period_match):
            continue
        candidate_text = str(item.get("raw_content") or "").strip()
        if len(candidate_text) < 1_000:
            candidate_text = _fetch_release_page_text(str(item.get("url") or ""))
        if len(candidate_text) >= 1_000:
            source_text = candidate_text[:30_000]
            source_url = str(item.get("url") or "")
            break

    print(
        f"[synthesis] Official grounding for {ticker}: provider={research.get('primary_provider') or 'none'} "
        f"period={fiscal_period or 'unresolved'} source={source_url or 'none'} chars={len(source_text)}",
        flush=True,
    )
    return {
        "fiscal_period": fiscal_period,
        "evidence": "\n".join(evidence_lines),
        "provider": str(research.get("primary_provider") or ""),
        "source_text": source_text,
        "source_url": source_url,
    }


def _normalize_bullets(items: Any) -> List[Dict[str, Any]]:
    """Normalize a bullets array into a consistent [{"text": str, "children":
    [str...]}] shape, accepting either that shape or plain strings (in case
    the model doesn't follow the nested format for every item)."""
    normalized: List[Dict[str, Any]] = []
    for item in items or []:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            children = [str(c).strip() for c in item.get("children", []) or [] if str(c).strip()]
        else:
            text = str(item).strip()
            children = []
        if text:
            normalized.append({"text": text, "children": children})
    return normalized


_SYSTEM_PROMPT = (
    "You are a sharp markets analyst writing a brief for an equity research inbox. "
    "You will be given hard financial facts and a set of web research snippets about "
    "a company's earnings. Write two short fields:\n"
    "- what_matters: 1-3 sentences on the specific business drivers investors are watching "
    "for this print (e.g. a product line, margins, guidance, a named KPI).\n"
    "- market_read_through: one sentence naming which other tickers or sectors this print "
    "is a read-through for, and why.\n"
    "Ground every claim strictly in the provided facts and snippets. Do not invent numbers, "
    "analyst names, or events that are not present in the input. If the input is too sparse "
    "to say something specific, write a shorter, more general but still accurate statement "
    "rather than fabricating detail. Respond with a JSON object with exactly these two keys."
)


def synthesize_narrative(
    ticker: str,
    company: str,
    context_label: str,
    facts: Dict[str, Any],
    research_snippets: List[Dict[str, str]],
    model: str = "",
) -> Dict[str, str]:
    """Returns {"what_matters": str, "market_read_through": str}, or {} if
    synthesis isn't available (no key, import failure, API error)."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}
    try:
        from openai import OpenAI
    except Exception:
        return {}

    fact_lines = [
        f"{key}: {value}"
        for key, value in facts.items()
        if value not in (None, "", "N/A") and not key.startswith("official_release_")
    ]
    snippet_lines = [
        f"- ({item.get('domain', 'unknown')}) {item.get('title', '')}: {item.get('snippet', '')}"
        for item in research_snippets[:6]
        if item.get("snippet") or item.get("title")
    ]

    user_content = (
        f"Company: {company} ({ticker})\n"
        f"Context: {context_label}\n\n"
        "Facts:\n" + ("\n".join(fact_lines) or "(none available)") + "\n\n"
        "Research snippets:\n" + ("\n".join(snippet_lines) or "(none available)")
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=350,
        )
        data = json.loads(response.choices[0].message.content)
        return {
            "what_matters": str(data.get("what_matters", "")).strip(),
            "market_read_through": str(data.get("market_read_through", "")).strip(),
        }
    except Exception as exc:
        print(f"[synthesis] LLM synthesis failed for {ticker}: {exc}", flush=True)
        return {}


def _deep_dive_system_prompt(mode: str) -> str:
    if mode == "post":
        timing = "the kind sent to an investment team the day a company reports"
        facts_desc = "prior-quarter actuals, this quarter's consensus/guidance going in, and the market's reaction"
        question_desc = "the 2-3 specific things this print revealed"
        next_test_desc = "the specific follow-through to watch next quarter"
    else:
        timing = "the kind sent to an investment team the day before a company reports"
        facts_desc = "prior-quarter actuals, consensus/guidance figures"
        question_desc = "the 2-3 specific business questions this print will answer"
        next_test_desc = "the specific open question this section's theme raises for the upcoming print"
    return (
        f"You are a senior equity research analyst writing a detailed earnings brief, {timing}. "
        f"You will be given hard financial facts ({facts_desc}) and a set of web research "
        "snippets covering the company's guidance and business drivers.\n\n"
        "Bullets throughout this brief use one consistent shape so related proof points can "
        "nest under a lead-in line: each bullet is an object {\"text\": \"...\", \"children\": "
        "[...]}. Use \"children\": [] for a normal standalone bullet. Use children when you "
        "have a natural lead-in followed by a group of specific proof points, e.g. {\"text\": "
        "\"Last quarter had the following proof points:\", \"children\": [\"Revenue increased "
        "11% to $7.1 billion\", ...]}. Don't force nesting where it isn't natural.\n\n"
        "Write a structured brief with:\n"
        f"- intro: 2-4 sentences framing {question_desc}. Fold in the report date/timing "
        "naturally as part of the prose.\n"
        "- financial_highlights: 4-7 bullets (using the shape above) with specific "
        "guided/consensus/reported figures (revenue, YoY%, margin, backlog/bookings growth, "
        "etc.) -- only include figures actually present in the input.\n"
        "- sections: 3-6 objects, each a distinct business theme SPECIFIC to this company (e.g. "
        "a named product line, an acquisition, a geography, a customer segment -- not generic "
        "filler like \"Overall performance\"). Each has:\n"
        "  - heading: short theme name (e.g. \"AI monetization\", \"Cloud backlog\")\n"
        "  - bullets: 2-5 bullets (using the shape above), each grounded in specific "
        "facts/snippets. End the list with one final bullet (no children) framed as \"The "
        f"next test is whether...\" -- {next_test_desc}\n"
        "- key_metrics: 4-7 short strings (plain strings, not the nested shape), each "
        "\"Category: what to watch\", summarizing the handful of numbers/KPIs that matter "
        "most across all sections.\n\n"
        "Writing style: use sentence case everywhere (headings, key_metrics labels, bullet "
        "lead-ins) -- capitalize only the first word and proper nouns/tickers/acronyms. Avoid "
        "Title Case throughout.\n\n"
        "Ground every claim strictly in the provided facts and snippets -- never invent a "
        "number, percentage, dollar figure, or named metric that isn't in the input. If the "
        "input doesn't support enough distinct themes for 3 sections, write fewer sections "
        "rather than inventing content. Respond with a JSON object with exactly these four keys."
    )


def synthesize_pre_earnings_brief(
    ticker: str,
    company: str,
    quarter: str,
    facts: Dict[str, Any],
    research_snippets: List[Dict[str, str]],
    model: str = "",
    mode: str = "pre",
) -> Dict[str, Any]:
    """Returns a structured earnings deep-dive brief (pre- or post-earnings,
    per `mode`): {"intro": str, "financial_highlights": [str...], "sections":
    [{"heading", "bullets", "next_test"}...], "key_metrics": [str...]}
    or {} if synthesis isn't available (no key, import failure, API error)."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}
    try:
        from openai import OpenAI
    except Exception:
        return {}

    fact_lines = [f"{key}: {value}" for key, value in facts.items() if value not in (None, "", "N/A")]
    snippet_lines = [
        f"- ({item.get('domain', 'unknown')}) {item.get('title', '')}: {item.get('snippet', '')}"
        for item in research_snippets[:14]
        if item.get("snippet") or item.get("title")
    ]

    report_label = "Report" if mode == "post" else "Upcoming report"
    user_content = (
        f"Company: {company} ({ticker})\n"
        f"{report_label}: {quarter}\n\n"
        "Facts:\n" + ("\n".join(fact_lines) or "(none available)") + "\n\n"
        "Research snippets:\n" + ("\n".join(snippet_lines) or "(none available)")
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": _deep_dive_system_prompt(mode)},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2200,
        )
        data = json.loads(response.choices[0].message.content)
        sections = []
        for item in data.get("sections", []) or []:
            if not isinstance(item, dict):
                continue
            heading = str(item.get("heading", "")).strip()
            bullets = _normalize_bullets(item.get("bullets", []))
            if not heading or not bullets:
                continue
            sections.append({"heading": heading, "bullets": bullets})
        return {
            "intro": str(data.get("intro", "")).strip(),
            "financial_highlights": _normalize_bullets(data.get("financial_highlights", [])),
            "sections": sections,
            "key_metrics": [str(b).strip() for b in data.get("key_metrics", []) or [] if str(b).strip()],
            "key_figures": [],
            "estimate_comparisons": [],
            "valuation_reference": {},
            "official_links": {},
        }
    except Exception as exc:
        print(f"[synthesis] Pre-earnings deep-dive synthesis failed for {ticker}: {exc}", flush=True)
        return {}


_DEEP_DIVE_WEB_SEARCH_PROMPT = """\
You are a senior equity research analyst writing a detailed {mode_label} brief for an
investment team, the kind sent {timing_phrase}. Use web search to find current, specific
figures about {company} ({ticker}) -- {research_focus}

Also search specifically for the official earnings press release, investor
presentation/deck, and earnings call transcript for this report (or, if this is a
pre-earnings brief, the most recent quarter's). Only include a URL you actually found via
search -- use null for any you can't find, never guess or construct one. For any real,
currently publicly-traded company being actively covered, at least one of these three
should normally be findable (its investor relations site alone usually has the press
release) -- if a search for it turns up nothing at all, that's a signal to search again with
a different query (e.g. "{company} investor relations", "{ticker} SEC 8-K") before giving up
and returning null for everything.

Cite your sources: after any specific figure, quote, or claim drawn from a particular
source, append an inline citation in this exact format: ([domain.com](https://full-url)) --
e.g. "Revenue grew 14% to $19.4B ([reuters.com](https://www.reuters.com/...))." Do this
consistently throughout intro, financial_highlights, and every section's bullets, not just
occasionally -- these citations are extracted programmatically into a Sources footer readers
rely on to verify the brief, so a brief with no inline citations anywhere produces an email
with no visible sourcing at all, which has happened before and should not recur.

Bullets throughout this brief use one consistent shape so related proof points can nest
under a lead-in line: "children": [] for a normal standalone bullet, or a lead-in "text"
followed by a group of specific proof points in "children" when that's natural, e.g. text:
"Last quarter, the software business had the following proof points:", children: ["Software
revenue increased 11% to $7.1 billion", "Hybrid Cloud revenue increased 13%", ...]. Don't
force nesting where it isn't natural -- most bullets should have empty children.

Before writing anything else, establish EXACTLY which period this report covers -- this is the
single most common source of error in briefs like this, so treat it as its own research step, not
an assumption:
1. Search for this company's actual fiscal calendar and confirm which specific fiscal quarter and
   period (start/end dates) this report covers. Many companies' fiscal years don't match the
   calendar year (e.g. Microsoft's fiscal year ends in June, so a report in late July is their
   fiscal Q4, covering April-June, not a calendar Q2 or Q3). Do not assume the calendar-quarter
   hint given to you below is correct -- it frequently isn't, for exactly this reason.
2. Once you know the real period, make sure every "actual" and every "consensus/estimate" figure
   you use is FOR THAT SAME PERIOD. A beat/miss comparison is meaningless if the actual is for one
   quarter and the consensus you're comparing it to is for a different one -- this is the second
   most common error, and it's easy to make by accident when a data source's "current quarter"
   label has quietly rolled forward or is otherwise misaligned. If a consensus/estimate figure
   given to you in Known facts below seems to be for a different period than the one you've
   confirmed via research (check it against the approximate period-end dates in the known facts,
   which are computed estimates, not verified facts), do not use it -- search for the correct,
   period-matched consensus figure instead, or omit that comparison and say so, but never silently
   pair mismatched-period figures together.
3. CapEx figures have the same problem in a different shape: press coverage frequently quotes CapEx
   guidance for a CALENDAR year (e.g. "$190B for calendar 2026"), which is a different number from
   the company's FISCAL year CapEx (e.g. Microsoft's fiscal 2026 runs July 2025-June 2026) -- caught
   live producing a full-year CapEx guidance figure off by ~$70B. Every CapEx figure you state as
   "full-year" or "FY guidance" must be for the SAME fiscal year as fiscal_quarter_label, not a
   calendar year -- if you can only find a calendar-year figure and can't confirm the fiscal-year
   equivalent, label it explicitly as calendar-year (e.g. "calendar-year 2026 CapEx guidance: $190B")
   rather than presenting it as the fiscal-year figure. If Known facts below gives you
   last_fy_capex_actual (last fiscal year's real total) and/or fy_capex_qtd_actual (this fiscal
   year's already-reported quarters summed), use those as a sanity check -- a fiscal-year CapEx
   figure should be a plausible continuation of that trend, not a disconnected number.
4. When a full-year CapEx guidance figure has changed from a previously reported number, determine
   WHY before stating it as a raise or cut: search specifically for whether the change reflects a
   real change in planned spending, or purely an accounting/presentation change (e.g. a shift
   between finance-lease and operating-lease classification, or a useful-life change) that alters
   the REPORTED number without changing the actual investment plan -- caught live: Microsoft's
   CapEx guidance appeared to drop from ~$190B to ~$175B, but management's own words were "our
   calendar year 2026 CapEx investment expectations remain unchanged... the shift from finance to
   operating leases adjusts our expectation to approximately $175 billion" -- i.e. the real plan
   didn't change, only the accounting presentation did. Never present a reclassification-driven
   number change as if it were a real raise or cut without saying so explicitly.
5. For the company's most current full-year (or next-period) CapEx guidance, also search for the
   analyst/Street CapEx estimate for that same period, if one is reported. These can diverge
   meaningfully (management guiding well below or above what analysts had modeled is itself a
   notable data point) -- when you find both, report them side by side as guide vs. estimate rather
   than only the one you found first.
- fiscal_quarter_label: this company's own correct fiscal-quarter label from step 1 above (e.g.
  "Q4 FY2026"). Use this consistently everywhere in this brief (intro, financial_highlights,
  sections, key_metrics) instead of the calendar-quarter hint, including when describing
  prior-quarter figures (e.g. don't call the prior quarter "Q2 FY2026" if it was actually "Q3
  FY2026").
- reporting_period_end: the actual period-end date (YYYY-MM-DD) you confirmed in step 1 for the
  quarter THIS report covers -- e.g. "2026-06-30" for a Microsoft fiscal Q4 2026 report. This is
  checked against an independently-computed estimate, so it must be your real, researched answer,
  not a copy of any hint given to you.
- intro: 2-3 sentences and no more than 110 words. Return one plain-text paragraph only: no
  Markdown headings, lists, finance-tool output, live quote dump, or generic agenda. Fold in the
  report date/timing naturally and frame {intro_focus}.
- financial_highlights: 4-6 bullets with specific figures (revenue, EPS, segment
  breakdowns, margins, backlog/bookings). {financial_highlights_instruction} Include a specific
  CapEx figure only when the company reports one and it is material to the investment setup. Do
  not substitute customer, industry, facility-announcement, or unrelated infrastructure spending
  for the company's own CapEx; omit CapEx entirely when no decision-useful company figure is
  available. If CapEx guidance changed
  this quarter (raised, lowered, or reaffirmed with a new number), state BOTH the previous
  guidance figure and the new/updated one, e.g. "CapEx guidance raised to $145B for FY2026, up
  from $125B previously" -- not just the new number alone, and per point 4 above, say explicitly
  if a change is a real change in spending plans vs. an accounting/presentation change. If you
  found both a company guide and an analyst/Street estimate for the same full-year period (point 5
  above), include a dedicated "CapEx guide vs. estimate" bullet stating both, e.g. "FY2027 CapEx
  guide: grows YoY (no specific figure given) vs. Street estimate of ~$255B." If net income
  diverges sharply from
  operating income (e.g. a large one-time gain/charge, tax item, or equity investment
  mark-to-market), state the specific driver by name and its dollar size -- never present a net
  income figure that implies an unusual margin without explaining why.
- sections: 2-4 objects, each a distinct business theme SPECIFIC to this company (a named
  product line, segment, acquisition, or initiative -- not generic filler like "Overall
  performance"). heading is a short theme name (e.g. "Google Cloud", "AI monetization").
  bullets are 2-4 items, each with a specific figure or fact you found -- end the list with
  one final bullet (empty children) framed as "The next test is whether..." -- {next_test_focus}
  Segment/business-line revenue figures (e.g. a cloud division, a specific product line) need
  their OWN specific search -- do not state a segment figure from general recall/training
  knowledge, which is exactly how stale, wrong-period numbers slip in (caught live: an AWS
  revenue figure understated by nearly half, evidently recalled from an earlier year rather
  than actually searched for this report). Before including a segment revenue figure, search
  specifically for it (e.g. "{company} AWS revenue Q1 2026", not just "{company} earnings"),
  and sanity-check it against the total revenue you already have as a known fact: a single
  segment's revenue should never exceed total company revenue, and if you're stating multiple
  segments, they should roughly account for the total (not obviously sum to far more or far
  less) -- if a figure you're about to use doesn't reconcile, that's a sign it's wrong or from
  the wrong period; search again rather than including it anyway.
- key_metrics: 4-6 short strings summarizing what matters most. Do not repeat a metric unless the
  second mention adds a distinct comparison or decision threshold. {key_metrics_instruction}
- key_figures: 4-6 compact display tiles, each with a short label and value. In post-earnings mode,
  prioritize reported revenue/product revenue, adjusted EPS, a key operating KPI, and the most
  decision-useful guidance figures. Put estimate deltas in estimate_comparisons rather than trying
  to cram both sides into these tiles. In pre-earnings mode, prioritize upcoming consensus and
  management guidance. Use only sourced figures already supported elsewhere in the brief.
- estimate_comparisons: in post-earnings mode, return 2-5 decision-useful rows comparing the
  reported result or new company guide with the PERIOD-MATCHED estimate that existed before the
  release. Each row must include metric, reported, estimate, variance, period, estimate_source,
  estimate_as_of, and source_url. Prefer a dated S&P Capital IQ/CIQ consensus when a source
  explicitly identifies it; otherwise use a clearly named current provider such as Visible Alpha,
  FactSet, LSEG, StreetAccount, Bloomberg, or Zacks. Never relabel a generic "Wall Street" figure
  as CIQ. Treat total revenue and product/segment revenue as different metrics and never compare
  one with the other. In pre-earnings mode, use the same rows for company guidance versus the
  upcoming consensus where available. If a source gives a range, preserve it and calculate the
  variance against the midpoint (say that explicitly). Every estimate needs a provider and an
  as-of/capture date; use an empty array rather than an unsourced comparison.
- valuation_reference: show enterprise value, estimated calendar-year revenue, and EV / CY revenue
  for reference. Return display-ready strings for enterprise_value, cy_revenue, ev_cy_revenue,
  basis, as_of, source, and source_url. Use the latest reliable regular-close EV by default; if you
  also calculate a pro-forma after-hours EV/multiple, label it as an estimate and state the price or
  share-count adjustment. Calendarize revenue only from period-matched fiscal actuals/consensus and
  explain the interpolation in basis. If true CY estimates are unavailable, use the nearest fiscal
  year only as a clearly labeled proxy -- never call a fiscal-year number CY. Recalculate the
  multiple yourself as EV divided by revenue and round to one decimal place. Use empty strings when
  the inputs cannot be sourced rather than inventing a valuation.
- official_links: press_release/investor_deck/transcript, each a URL you found via search,
  or null if you couldn't find one.
- financials: the same revenue/EPS/net income/CapEx figures already stated in prose above,
  restated as plain numbers (revenue, net income, and CapEx in raw USD, not "13.8" for "$13.8B" --
  e.g. 13800000000) so they can be stored and compared quarter over quarter. Use null for
  anything not found or not applicable in {mode_label} mode -- do not invent a figure just to
  fill a field. If this is a pre-earnings brief, revenue_consensus_usd is REQUIRED whenever a
  next-quarter consensus fact is provided to you below -- a pre-earnings brief that only reports
  what already happened, with no forward estimate, is missing its entire point.
  capex_guidance_analyst_estimate_usd is the Street/analyst full-year CapEx estimate (distinct from
  capex_guidance_updated_usd, which is the COMPANY's own guide) -- fill it whenever you found a
  specific analyst estimate figure for the same guidance period, null otherwise.

Writing style: use sentence case everywhere (headings, key_metrics labels, bullet
lead-ins) -- capitalize only the first word and proper nouns/tickers/acronyms (e.g. "AI
monetization", not "AI Monetization"; "Q2 2026 revenue guidance: $13.8B-$14.8B", not "Q2
2026 Revenue Guidance"). Avoid Title Case throughout.

Ground every claim in what you actually find via search -- never invent a number, metric,
or URL. If you can't find enough for 2 distinct sections, return fewer rather than inventing
content.
"""

_BULLET_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "children": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "children"],
    "additionalProperties": False,
}

_ESTIMATE_COMPARISON_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "metric": {"type": "string"},
        "reported": {"type": "string"},
        "estimate": {"type": "string"},
        "variance": {"type": "string"},
        "period": {"type": "string"},
        "estimate_source": {"type": "string"},
        "estimate_as_of": {"type": "string"},
        "source_url": {"type": "string"},
    },
    "required": [
        "metric", "reported", "estimate", "variance", "period",
        "estimate_source", "estimate_as_of", "source_url",
    ],
    "additionalProperties": False,
}

_KEY_FIGURE_JSON_SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
    "required": ["label", "value"],
    "additionalProperties": False,
}

_VALUATION_REFERENCE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "enterprise_value": {"type": "string"},
        "cy_revenue": {"type": "string"},
        "ev_cy_revenue": {"type": "string"},
        "basis": {"type": "string"},
        "as_of": {"type": "string"},
        "source": {"type": "string"},
        "source_url": {"type": "string"},
    },
    "required": [
        "enterprise_value", "cy_revenue", "ev_cy_revenue", "basis",
        "as_of", "source", "source_url",
    ],
    "additionalProperties": False,
}

_DEEP_DIVE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "fiscal_quarter_label": {"type": "string"},
        "reporting_period_end": {"type": "string"},
        "intro": {"type": "string"},
        "financial_highlights": {"type": "array", "minItems": 4, "maxItems": 6, "items": _BULLET_JSON_SCHEMA},
        "sections": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "bullets": {"type": "array", "minItems": 2, "maxItems": 4, "items": _BULLET_JSON_SCHEMA},
                },
                "required": ["heading", "bullets"],
                "additionalProperties": False,
            },
        },
        "key_metrics": {"type": "array", "minItems": 4, "maxItems": 6, "items": {"type": "string"}},
        "key_figures": {"type": "array", "minItems": 4, "maxItems": 6, "items": _KEY_FIGURE_JSON_SCHEMA},
        "estimate_comparisons": {
            "type": "array", "maxItems": 5, "items": _ESTIMATE_COMPARISON_JSON_SCHEMA,
        },
        "valuation_reference": _VALUATION_REFERENCE_JSON_SCHEMA,
        "qa_highlights": {
            "type": "array", "maxItems": 4,
            "items": {"type": "object", "properties": {
                "analyst_question": {"type": "string"}, "answer_summary": {"type": "string"},
            }, "required": ["analyst_question", "answer_summary"], "additionalProperties": False},
        },
        "official_links": {
            "type": "object",
            "properties": {
                "press_release": {"type": ["string", "null"]},
                "investor_deck": {"type": ["string", "null"]},
                "transcript": {"type": ["string", "null"]},
            },
            "required": ["press_release", "investor_deck", "transcript"],
            "additionalProperties": False,
        },
        "financials": {
            "type": "object",
            "description": (
                "Structured, comparable figures for historical tracking -- separate from the "
                "prose bullets above so they can be stored and charted over time without "
                "re-parsing sentences. Use null for any figure not actually found/applicable "
                "(e.g. pre-earnings mode, or a company that doesn't report EPS the usual way) "
                "-- never invent a number to fill these in."
            ),
            "properties": {
                "revenue_actual_usd": {"type": ["number", "null"]},
                "revenue_consensus_usd": {"type": ["number", "null"]},
                "revenue_yoy_pct": {"type": ["number", "null"]},
                "net_income_actual_usd": {"type": ["number", "null"]},
                "eps_actual": {"type": ["number", "null"]},
                "eps_consensus": {"type": ["number", "null"]},
                "eps_surprise_pct": {"type": ["number", "null"]},
                "capex_actual_usd": {"type": ["number", "null"]},
                "capex_guidance_prior_usd": {"type": ["number", "null"]},
                "capex_guidance_updated_usd": {"type": ["number", "null"]},
                "capex_guidance_analyst_estimate_usd": {"type": ["number", "null"]},
            },
            "required": [
                "revenue_actual_usd", "revenue_consensus_usd", "revenue_yoy_pct",
                "net_income_actual_usd", "eps_actual", "eps_consensus", "eps_surprise_pct",
                "capex_actual_usd", "capex_guidance_prior_usd", "capex_guidance_updated_usd",
                "capex_guidance_analyst_estimate_usd",
            ],
            "additionalProperties": False,
        },
    },
    "required": [
        "intro", "financial_highlights", "sections", "key_metrics", "key_figures", "official_links",
        "financials", "fiscal_quarter_label", "reporting_period_end", "qa_highlights",
        "estimate_comparisons", "valuation_reference",
    ],
    "additionalProperties": False,
}


def synthesize_earnings_brief_with_web_search(
    ticker: str,
    company: str,
    quarter: str,
    mode: str,
    facts: Dict[str, Any],
    model: str = "",
    extra_instructions: str = "",
) -> Dict[str, Any]:
    """Same structured brief as synthesize_pre_earnings_brief, but uses the
    OpenAI Responses API's native web_search tool so the model researches and
    writes in one grounded pass -- much higher figure density than feeding it
    pre-fetched short snippets. mode is "pre" or "post". extra_instructions,
    if given, is appended verbatim -- used by
    synthesize_earnings_brief_with_review to fold in fix-it feedback from a
    prior review pass.

    Returns {} if unavailable (no key, import failure, API error, or no
    parseable JSON in the response) -- callers should fall back to the
    snippet-based synthesize_pre_earnings_brief / synthesize_narrative."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}
    try:
        from openai import OpenAI
    except Exception:
        return {}

    fact_lines = [f"{key}: {value}" for key, value in facts.items() if value not in (None, "", "N/A")]

    if mode == "post":
        mode_label = "post-earnings"
        timing_phrase = "the day results are reported"
        research_focus = (
            "the actual just-reported results (revenue, EPS, segment breakdowns), the "
            "consensus/expected figures they're being measured against, management's "
            "guidance for the next quarter/year, the stock's market reaction, and 2-4 major "
            "company-specific themes from the report or earnings call."
        )
        intro_focus = (
            "what this report actually revealed -- the 2-3 most important takeaways from "
            "the results and call, not what investors were watching for beforehand"
        )
        financial_highlights_instruction = (
            "This already happened -- report ACTUAL figures. If the Known facts below (or "
            "search) give you a consensus/estimate for a metric, you MUST state both the "
            "actual and that consensus figure with the beat/miss for THAT bullet, e.g. "
            "'Revenue: $90.8B actual vs. $89.3B consensus, a 1.7% beat' -- never report a bare "
            "actual number alone when a consensus figure for that same metric is available to "
            "you. Only report a bare actual (no comparison) when you genuinely could not find "
            "any consensus/estimate for that specific metric. Do not frame these as future "
            "guidance or targets -- they already happened."
        )
        next_test_focus = "the specific follow-through to watch next quarter, given what just happened"
        key_metrics_instruction = (
            "Each a \"Category: result\" summarizing the report's most important actual "
            "outcomes -- and, exactly like financial_highlights, actual vs. consensus with the "
            "beat/miss wherever a consensus figure is available, not a bare number. A "
            "retrospective highlight reel of this print, not a forward-looking watch list."
        )
    else:
        mode_label = "pre-earnings"
        timing_phrase = "the day before a company reports"
        research_focus = (
            "the prior quarter's actual segment results, current-quarter/full-year "
            "consensus estimates and guidance, capex/investment plans, backlog or bookings, "
            "and 2-4 major company-specific growth drivers with real usage/adoption metrics."
        )
        intro_focus = "the 2-3 specific business questions the upcoming report will answer"
        financial_highlights_instruction = (
            "This hasn't been reported yet -- use prior-quarter actuals and Street "
            "consensus/guidance for the upcoming quarter, framed as what to expect, not as "
            "results."
        )
        next_test_focus = "the specific open question this section's theme raises for the upcoming print"
        key_metrics_instruction = (
            "Each \"Category: what to watch\", summarizing the handful of numbers/KPIs that "
            "matter most across all sections going into the print."
        )

    prompt = _DEEP_DIVE_WEB_SEARCH_PROMPT.format(
        mode_label=mode_label,
        timing_phrase=timing_phrase,
        company=company,
        ticker=ticker,
        research_focus=research_focus,
        intro_focus=intro_focus,
        financial_highlights_instruction=financial_highlights_instruction,
        next_test_focus=next_test_focus,
        key_metrics_instruction=key_metrics_instruction,
    )
    if fact_lines:
        prompt += "\nKnown facts (incorporate these, don't contradict them):\n" + "\n".join(fact_lines)
        prompt += (
            "\n\nException: last_q_period_end and next_q_expected_period_end above are "
            "deterministically computed estimates for the period-verification step in point 1 "
            "above, not verified facts -- they exist so you have something concrete to check your "
            "research against, not something to state as-is or treat as certain. If your research "
            "gives a different, more specific period end, use your researched answer."
        )
    if mode == "post" and facts.get("market_reaction_pct") is not None:
        prompt += (
            f"\n\nThe stock's move following this report is already computed as "
            f"{facts['market_reaction_pct']}% (shown separately above the intro) -- "
            "do not restate a different share-price-move percentage from search results "
            "anywhere in the brief, even if you find one."
        )
    if mode == "post" and facts.get("official_release_evidence"):
        prompt += (
            "\n\nCURRENT OFFICIAL-RELEASE DISCOVERY (collected before synthesis through the "
            f"LLMLayer-first provider cascade; primary provider: "
            f"{facts.get('official_release_provider') or 'none'}):\n"
            f"{facts['official_release_evidence']}\n"
            "Use these current-release results to locate and prefer the issuer's own release. "
            "Do not reuse figures from a prior quarter merely because they rank higher in search."
        )
    if mode == "post" and facts.get("official_fiscal_quarter_label"):
        prompt += (
            "\n\nREQUIRED FISCAL-PERIOD GATE: current official-release search evidence identifies "
            f"this report as {facts['official_fiscal_quarter_label']}. The returned "
            "fiscal_quarter_label and every actual/consensus figure must belong to that exact "
            "period; otherwise this draft fails QA."
        )
    if mode == "post" and facts.get("official_release_source_text"):
        prompt += (
            f"\n\nDIRECT ISSUER RELEASE TEXT ({facts.get('official_release_source_url') or 'official source'}):\n"
            f"{facts['official_release_source_text']}\n\n--- end issuer release ---\n"
            "Treat this direct issuer text as the source of truth for actual revenue, EPS, "
            "growth rates, operating income, margins, cash flow, and guidance. If a search "
            "result conflicts with it, discard the search result."
        )
    prompt += (
        f"\n\nFiscal period (rough calendar-quarter guess ONLY -- verify and correct via "
        f"research per the fiscal_quarter_label instructions above): {quarter}"
    )
    if extra_instructions:
        prompt += (
            "\n\nA quality review of a prior draft of this brief flagged the following -- "
            f"research further and fix these specifically:\n{extra_instructions}"
        )

    # Post-earnings briefs depend on nuance (e.g. WHY a guidance figure moved
    # -- a real change vs. an accounting reclassification) that a generic
    # search snippet rarely captures. Caught live: MSFT's CapEx guidance was
    # only understood correctly after reading actual primary-source page
    # text, not summaries of it. Fetch a large excerpt of the real earnings
    # call transcript / press release (via TinyFish/Tavily/LLMLayer, which
    # actually return full page content unlike a snippet search) and hand it
    # to the model as grounding -- best-effort, never blocks synthesis if
    # unavailable.
    if mode == "post":
        transcript: Dict[str, str] = {}
        try:
            import sys
            from pathlib import Path
            workspace_root = Path(__file__).resolve().parents[1]
            if str(workspace_root) not in sys.path:
                sys.path.insert(0, str(workspace_root))
            from core.research import fetch_transcript_excerpt
            transcript = fetch_transcript_excerpt(
                ticker, company, quarter, report_date=str(facts.get("report_date") or "")
            )
        except Exception as exc:
            print(f"[synthesis] Transcript excerpt fetch failed for {ticker}: {exc}", flush=True)
        if transcript.get("text"):
            prompt += (
                f"\n\nPRIMARY SOURCE EXCERPT (fetched from {transcript.get('url')} -- this is real "
                "page content, not a search snippet summary. Ground your actual results, guidance "
                "figures, and any explanation for why a guidance number changed in this text "
                "specifically wherever it's relevant, and prefer it over other search results if "
                "they conflict, since it's more likely to be the primary source):\n\n"
                f"{transcript['text']}\n\n--- end excerpt ---"
            )
            if transcript.get("qa_text"):
                prompt += ("\n\nANALYST Q&A INSTRUCTIONS: Produce no more than four qa_highlights, only from the separately labeled analyst Q&A. Prioritize demand, guidance, margins, pricing, and sales cycles; paraphrase and include the analyst or firm when stated.")

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model or os.environ.get("OPENAI_WEB_SEARCH_MODEL", "gpt-4o-mini"),
            tools=[{"type": "web_search"}],
            input=prompt,
            max_output_tokens=8000,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "earnings_brief",
                    "schema": _DEEP_DIVE_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        if response.status == "incomplete":
            reason = getattr(response.incomplete_details, "reason", "unknown")
            print(f"[synthesis] Web-search deep-dive for {ticker} was cut off (reason={reason})", flush=True)
            return {}
        # strict=False: web-search synthesis occasionally embeds an
        # unescaped literal newline/tab inside a string value (technically
        # invalid JSON) -- tolerate it rather than losing the whole brief.
        data = json.loads(response.output_text, strict=False)
        if not data:
            return {}
        sections = []
        for item in data.get("sections", []) or []:
            if not isinstance(item, dict):
                continue
            heading = str(item.get("heading", "")).strip()
            bullets = _normalize_bullets(item.get("bullets", []))
            if not heading or not bullets:
                continue
            sections.append({"heading": heading, "bullets": bullets})
        qa_highlights = []
        for item in data.get("qa_highlights", []) or []:
            if not isinstance(item, dict): continue
            question, answer = str(item.get("analyst_question", "")).strip(), str(item.get("answer_summary", "")).strip()
            if question and answer: qa_highlights.append({"analyst_question": question, "answer_summary": answer})
        estimate_comparisons = []
        for item in data.get("estimate_comparisons", []) or []:
            if not isinstance(item, dict):
                continue
            cleaned = {
                key: str(item.get(key, "") or "").strip()
                for key in (
                    "metric", "reported", "estimate", "variance", "period",
                    "estimate_source", "estimate_as_of", "source_url",
                )
            }
            if cleaned["metric"] and cleaned["reported"] and cleaned["estimate"]:
                estimate_comparisons.append(cleaned)
        valuation_raw = data.get("valuation_reference") or {}
        valuation_reference = {
            key: str(valuation_raw.get(key, "") or "").strip()
            for key in (
                "enterprise_value", "cy_revenue", "ev_cy_revenue", "basis",
                "as_of", "source", "source_url",
            )
        } if isinstance(valuation_raw, dict) else {}
        return {
            "fiscal_quarter_label": str(data.get("fiscal_quarter_label", "")).strip(),
            "reporting_period_end": str(data.get("reporting_period_end", "")).strip(),
            "intro": str(data.get("intro", "")).strip(),
            "financial_highlights": _normalize_bullets(data.get("financial_highlights", [])),
            "sections": sections,
            "key_metrics": [str(b).strip() for b in data.get("key_metrics", []) or [] if str(b).strip()],
            "key_figures": [
                {"label": str(item.get("label", "")).strip(), "value": str(item.get("value", "")).strip()}
                for item in data.get("key_figures", []) or []
                if isinstance(item, dict) and str(item.get("label", "")).strip() and str(item.get("value", "")).strip()
            ],
            "estimate_comparisons": estimate_comparisons,
            "valuation_reference": valuation_reference,
            "official_links": _clean_official_links(data.get("official_links")),
            "financials": _clean_financials(data.get("financials")),
            "qa_highlights": qa_highlights,
        }
    except Exception as exc:
        print(f"[synthesis] Web-search deep-dive synthesis failed for {ticker}: {exc}", flush=True)
        return {}


_REVIEW_PROMPT = """\
You are doing a final quality gut-check on a {mode_label} earnings brief for {company} ({ticker}),
{quarter}, before it is sent to an investment team. You are auditing the brief below against the known
facts -- not researching from scratch.

Check specifically for:
- Contradictions: does any figure (stock move %, revenue, EPS, margin, date) conflict with another
  figure stated elsewhere in the brief, or with the known facts below?
- Placeholders/gaps: any bullet saying something wasn't disclosed/found/available when it plausibly
  should be knowable for a company this size, or a metric named in key_metrics that isn't backed by a
  specific figure anywhere else in the brief.
- Generic filler: any section whose bullets are vague claims without a specific number, name, or fact.
- Thinness: does the brief feel sparse for a company of this size (very few sections, very short
  bullets) given what should be publicly available.
- Unexplained margins: if net income diverges sharply from operating income (implying an unusually
  high or low margin), does the brief say why (e.g. a one-time gain, equity mark-to-market swing, tax
  item)? An unusual margin isn't automatically wrong -- but stating it without the driver is a gap.
- Vague CapEx: if the company reports capital expenditures, is there a specific figure (not just
  "significant increases")?
- Missing beat/miss framing (post-earnings only): if this is a post-earnings brief and the known
  facts below include a consensus/estimate for a metric that also appears in financial_highlights
  or key_metrics, does that bullet state both the actual and the consensus with the beat/miss --
  not just the bare actual number? A bullet like "Revenue: $19.64B" with no comparison, when a
  consensus figure for revenue was available in the known facts, is a gap to flag.
- Estimate-scoreboard quality: in post-earnings mode, are there at least two period-matched
  estimate_comparisons, each naming the actual/guide, estimate, variance, estimate provider,
  estimate as-of date, and source URL? Flag total-revenue versus product/segment-revenue
  mismatches. Never accept a row labeled CIQ unless the cited source explicitly says the estimate
  is from S&P Capital IQ.
- Valuation reference: is EV / CY revenue shown with a dated enterprise value, a genuinely
  calendarized revenue estimate, the arithmetic basis, and named source? Flag a fiscal-year
  estimate mislabeled as CY, an unexplained after-hours adjustment, or a multiple that does not
  reconcile to the stated EV and revenue inputs.
- Wrong or inconsistent fiscal quarter: does fiscal_quarter_label match what's actually used
  throughout the brief (title/quarter references in intro, financial_highlights, sections)? Watch
  specifically for companies whose fiscal year doesn't match the calendar (e.g. Microsoft's fiscal
  year ends in June) -- a report in late July should be labeled that company's fiscal Q4, not a
  calendar Q2/Q3. If the brief's own quarter references are inconsistent with each other, flag it.
- Official-source conflicts (post-earnings only): when known facts include
  official_release_source_text, compare every actual result, growth rate, cash-flow figure, and
  guidance number in the brief against that issuer text. Flag any mismatch; do not accept a stale
  prior-year or prior-quarter figure just because it appears in another search result.
- Missing forward estimate (pre-earnings only): if this is a pre-earnings brief, does it actually
  state what the Street/consensus expects for the upcoming report (revenue, EPS), or does it only
  describe the prior quarter's results? A pre-earnings brief with no forward-looking estimate has
  missed its entire point.
- Missing CapEx before/after (either mode, if CapEx guidance was updated): if the brief mentions
  CapEx guidance changing this period, does it state both the previous figure and the new one, or
  only the new number alone?

Known facts:
{fact_lines}

Brief to audit (JSON):
{brief_json}

If the brief is internally consistent, adequately specific, and reasonably complete, set pass=true and
issues=[]. Otherwise set pass=false, list each concrete issue found (specific enough to act on, e.g.
"stock move stated as -6.48% in the intro but the header reaction line says +4.2%"), and suggest up to
3 targeted web-search queries that would resolve the gaps or contradictions.
"""

_REVIEW_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "pass": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "follow_up_queries": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["pass", "issues", "follow_up_queries"],
    "additionalProperties": False,
}


def review_earnings_brief(
    ticker: str,
    company: str,
    quarter: str,
    mode: str,
    facts: Dict[str, Any],
    brief: Dict[str, Any],
    model: str = "",
) -> Dict[str, Any]:
    """Gut-check an already-synthesized brief for internal contradictions, gaps, and
    generic filler before it ships. Returns {"pass": bool, "issues": [...],
    "follow_up_queries": [...]}. Fails open (pass=True) on any error -- this is a
    quality gate, not a hard dependency, so a review outage should never block a send
    that would otherwise have gone out fine."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"pass": True, "issues": [], "follow_up_queries": []}
    try:
        from openai import OpenAI
    except Exception:
        return {"pass": True, "issues": [], "follow_up_queries": []}

    fact_lines = "\n".join(
        f"{key}: {value}" for key, value in facts.items() if value not in (None, "", "N/A")
    ) or "(none available)"
    mode_label = "post-earnings" if mode == "post" else "pre-earnings"

    prompt = _REVIEW_PROMPT.format(
        mode_label=mode_label,
        company=company,
        ticker=ticker,
        quarter=quarter,
        fact_lines=fact_lines,
        brief_json=json.dumps(brief, indent=2),
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model or os.environ.get("OPENAI_REVIEW_MODEL", "gpt-4o-mini"),
            input=prompt,
            max_output_tokens=1500,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "brief_review",
                    "schema": _REVIEW_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        if response.status == "incomplete":
            return {"pass": True, "issues": [], "follow_up_queries": []}
        data = json.loads(response.output_text, strict=False)
        return {
            "pass": bool(data.get("pass", True)),
            "issues": [str(i).strip() for i in data.get("issues", []) or [] if str(i).strip()],
            "follow_up_queries": [
                str(q).strip() for q in data.get("follow_up_queries", []) or [] if str(q).strip()
            ],
        }
    except Exception as exc:
        print(f"[review] Review call failed for {ticker}: {exc}", flush=True)
        return {"pass": True, "issues": [], "follow_up_queries": []}


_DOLLAR_B_RE = re.compile(r"\$\s*([\d,]+\.?\d*)\s*(?:B|billion)\b", re.IGNORECASE)

# Matches the render layer's inline citation format, e.g. "([reuters.com](https://...))"
# -- kept in sync with render_pre_earnings_deep_dive_email.py's _CITATION_RE, which strips
# these out of prose and collects them into a Sources footer. Used here only to check
# citations exist at all, not to render anything.
_INLINE_CITATION_RE = re.compile(r"\(\[([^\]]+)\]\((https?://[^\s)]+)\)\)")


def _first_dollar_billions(text: str) -> "float | None":
    match = _DOLLAR_B_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _all_dollar_billions(text: str) -> List[float]:
    values = []
    for match in _DOLLAR_B_RE.finditer(text):
        try:
            values.append(float(match.group(1).replace(",", "")))
        except ValueError:
            pass
    return values


_NON_OPERATING_DRIVER_TERMS = (
    "one-time", "one time", "unrealized", "equity securities", "equity investment",
    "oi&e", "other income", "mark-to-market", "mark to market", "impairment",
    "divestiture", "tax benefit", "gain on", "non-operating", "nonoperating",
)


def _sanity_check_brief(brief: Dict[str, Any], mode: str = "post", facts: Optional[Dict[str, Any]] = None) -> List[str]:
    """Deterministic numeric plausibility check, independent of the LLM
    reviewer -- a backstop for the exact failure mode observed live: the
    reviewer correctly flagged an implausible net income figure, but the
    enrichment re-run kept the same wrong number instead of fixing it.

    An unusually high net margin isn't actually impossible for a real company
    (large one-time gains -- e.g. equity mark-to-market swings -- can genuinely
    produce this), so this doesn't assume the number itself is wrong. It only
    flags the relationship as needing a named driver: if no bullet anywhere in
    the brief explains *why* net income diverges from operating income (a
    one-time gain, an equity swing, a tax item, etc.), that's the actual gap to
    fix, whether by finding the real explanation or by finding the correct
    figure."""
    issues: List[str] = []
    highlight_bullets = brief.get("financial_highlights", []) or []
    all_texts = [str(b.get("text", "")) for b in highlight_bullets if isinstance(b, dict)]
    all_texts += [str(m) for m in brief.get("key_metrics", []) or []]
    for section in brief.get("sections", []) or []:
        for bullet in section.get("bullets", []) or []:
            if isinstance(bullet, dict):
                all_texts.append(str(bullet.get("text", "")))
                all_texts.extend(str(c) for c in bullet.get("children", []) or [])

    # Prefer the structured financials the synthesizer returns (reliable --
    # no parsing involved). Only fall back to regex-parsing prose when
    # structured data isn't present, e.g. the snippet-based fallback
    # synthesizer, which doesn't return a "financials" object.
    financials = brief.get("financials") or {}
    revenue_usd = financials.get("revenue_actual_usd")
    net_income_usd = financials.get("net_income_actual_usd")
    if isinstance(revenue_usd, (int, float)) and isinstance(net_income_usd, (int, float)):
        revenue = revenue_usd / 1_000_000_000
        net_income = net_income_usd / 1_000_000_000
    else:
        revenue = None
        net_income = None
        for text in all_texts:
            lower = text.lower()
            if revenue is None and lower.startswith("revenue"):
                revenue = _first_dollar_billions(text)
            if net_income is None and ("net income" in lower or "net profit" in lower):
                net_income = _first_dollar_billions(text)

    if revenue and net_income and (net_income > revenue or net_income / revenue > 0.5):
        has_driver = any(term in text.lower() for text in all_texts for term in _NON_OPERATING_DRIVER_TERMS)
        if not has_driver:
            issues.append(
                f"Net income (${net_income}B) implies an unusually high margin against revenue "
                f"(${revenue}B), but no bullet anywhere explains why (e.g. a one-time gain, equity "
                "mark-to-market swing, or tax item). Either find and state the specific driver by "
                "name and size, or if this figure can't be verified, correct it."
            )

    # A large gap between the model's own "actual" and "consensus" revenue
    # figures (both in the same financials object) is itself suspicious --
    # caught live: a brief reported revenue_actual_usd 24% below its own
    # revenue_consensus_usd, survived two review rounds unresolved, and would
    # have corrupted the historical record with a fabricated "miss."
    revenue_actual = financials.get("revenue_actual_usd")
    revenue_consensus = financials.get("revenue_consensus_usd")
    if (
        isinstance(revenue_actual, (int, float))
        and isinstance(revenue_consensus, (int, float))
        and revenue_consensus
        and abs(revenue_actual - revenue_consensus) / revenue_consensus > 0.15
    ):
        pct = (revenue_actual - revenue_consensus) / revenue_consensus * 100
        issues.append(
            f"financials.revenue_actual_usd (${revenue_actual / 1_000_000_000:.2f}B) diverges from "
            f"financials.revenue_consensus_usd (${revenue_consensus / 1_000_000_000:.2f}B) by "
            f"{pct:+.0f}% -- real beats/misses this large are rare and should be double-checked "
            "against the actual reported figure, not a different revenue line item (e.g. net vs. "
            "total revenue) mistaken for it."
        )

    # Caught live against MSFT: a next-quarter consensus fact was available
    # (next_q_revenue_consensus), but the pre-earnings brief never used it --
    # it read as entirely retrospective, with zero forward estimate, which
    # defeats the purpose of a pre-earnings brief. Only require this when the
    # fact was actually given; don't demand data that was never available.
    if mode == "pre" and facts and facts.get("next_q_revenue_consensus") is not None:
        if financials.get("revenue_consensus_usd") is None:
            issues.append(
                "This is a pre-earnings brief and a next-quarter revenue consensus fact "
                f"(${facts['next_q_revenue_consensus'] / 1_000_000_000:.2f}B) was provided, but "
                "financials.revenue_consensus_usd is null and no forward-looking revenue estimate "
                "appears anywhere in the brief -- it reads as entirely retrospective. State the "
                "consensus estimate for the upcoming quarter explicitly."
            )

    # Caught live against MSFT: the model can confidently state a fiscal
    # quarter/period that's still wrong (or drift back to a wrong one under
    # review pressure that itself has bad date arithmetic). Cross-check its
    # self-reported reporting_period_end against our independently computed,
    # dated anchor -- a large gap (>45 days, more than a stray day or two of
    # rounding) means the two disagree about which period is even being
    # discussed, which undermines every actual/consensus figure in the brief.
    reported_end = str(brief.get("reporting_period_end", "")).strip()
    expected_end = facts.get("next_q_expected_period_end") if facts else None
    if reported_end and expected_end:
        try:
            reported_date = _date.fromisoformat(reported_end[:10])
            expected_date = _date.fromisoformat(str(expected_end)[:10])
            gap_days = abs((reported_date - expected_date).days)
            if gap_days > 45:
                issues.append(
                    f"reporting_period_end ({reported_end}) is {gap_days} days away from the "
                    f"independently computed expected period end ({expected_end}) based on the "
                    "last actually-reported quarter -- this suggests the brief may be discussing "
                    "the wrong fiscal period. Re-verify via search which specific period this "
                    "report covers, and make sure every actual/consensus figure matches that period."
                )
        except (ValueError, TypeError):
            pass

    official_period = str((facts or {}).get("official_fiscal_quarter_label") or "").strip()
    reported_period = str(brief.get("fiscal_quarter_label") or "").strip()
    if official_period and reported_period and official_period.lower() != reported_period.lower():
        issues.append(
            f"fiscal_quarter_label ({reported_period}) conflicts with the current official-release "
            f"evidence ({official_period}). Rebuild the brief using only figures for {official_period}."
        )

    official_text = str((facts or {}).get("official_release_source_text") or "")
    if official_text and financials:
        revenue_match = re.search(r"\bRevenue\s+of\s+\$([\d,.]+)\s+billion\b", official_text, re.IGNORECASE)
        if revenue_match and isinstance(financials.get("revenue_actual_usd"), (int, float)):
            official_revenue = float(revenue_match.group(1).replace(",", "")) * 1_000_000_000
            if abs(financials["revenue_actual_usd"] - official_revenue) / official_revenue > 0.005:
                issues.append(
                    f"financials.revenue_actual_usd conflicts with the issuer release: the brief has "
                    f"${financials['revenue_actual_usd'] / 1_000_000_000:.2f}B but the release states "
                    f"${official_revenue / 1_000_000_000:.2f}B."
                )
        eps_match = re.search(r"\bAdjusted EPS\d*\s+of\s+\$([\d,.]+)\b", official_text, re.IGNORECASE)
        if eps_match and isinstance(financials.get("eps_actual"), (int, float)):
            official_eps = float(eps_match.group(1).replace(",", ""))
            if abs(financials["eps_actual"] - official_eps) > 0.005:
                issues.append(
                    f"financials.eps_actual conflicts with the issuer release: the brief has "
                    f"${financials['eps_actual']:.2f} but the release states adjusted EPS of "
                    f"${official_eps:.2f}."
                )

        percentage_checks = (
            (("walmart u.s. comp", "u.s. comparable", "u.s. comp sales"), r"Walmart U\.S\. comp sales\D{0,40}([\d.]+)%"),
            (("global ecommerce", "ecommerce sales"), r"eCommerce sales\D{0,40}([\d.]+)%"),
            (("membership fee",), r"Membership fee revenue\D{0,40}([\d.]+)%"),
            (("operating income",), r"Operating income\D{0,80}([\d.]+)%"),
        )
        for aliases, source_pattern in percentage_checks:
            source_match = re.search(source_pattern, official_text, re.IGNORECASE)
            if not source_match:
                continue
            expected_pct = float(source_match.group(1))
            for metric in (str(value) for value in brief.get("key_metrics", []) or []):
                if not any(alias in metric.lower() for alias in aliases):
                    continue
                metric_pcts = [float(value) for value in re.findall(r"([\d.]+)%", metric)]
                if metric_pcts and abs(metric_pcts[0] - expected_pct) >= 0.05:
                    issues.append(
                        f"Key metric '{metric}' conflicts with the issuer release, which states "
                        f"{expected_pct:g}% for that category."
                    )

        for metric in (str(value) for value in brief.get("key_metrics", []) or []):
            if "capex" not in metric.lower() and "capital expenditure" not in metric.lower():
                continue
            amount_match = re.search(r"\$([\d,.]+)\s*(?:billion|million|[BM])\b", metric, re.IGNORECASE)
            if amount_match and amount_match.group(1).replace(",", "") not in official_text.replace(",", ""):
                issues.append(
                    f"Key metric '{metric}' states a CapEx amount that does not appear in the direct "
                    "issuer release text. Remove it or replace it with a source-supported figure."
                )

        eps_actual = financials.get("eps_actual")
        eps_consensus = financials.get("eps_consensus")
        if isinstance(eps_actual, (int, float)) and isinstance(eps_consensus, (int, float)):
            for metric in (str(value) for value in brief.get("key_metrics", []) or []):
                if "eps" not in metric.lower():
                    continue
                lower = metric.lower()
                wrong_direction = (
                    eps_actual > eps_consensus and any(term in lower for term in ("below", "miss", "fell short"))
                ) or (
                    eps_actual < eps_consensus and any(term in lower for term in ("above", "beat", "exceed"))
                )
                if wrong_direction:
                    issues.append(
                        f"Key metric '{metric}' states the wrong EPS beat/miss direction for "
                        f"${eps_actual:.2f} actual versus ${eps_consensus:.2f} consensus."
                    )

    # Caught live against MSFT: a stray, unrelated dollar figure elsewhere in
    # the report (e.g. a backlog/RPO number) got mislabeled as CapEx,
    # producing a CapEx figure wildly out of scale with every other CapEx
    # mention in the same brief. A quarterly-vs-annual CapEx spread is
    # normally within about 5x; a much larger spread is a strong signal one of
    # the numbers isn't really CapEx.
    capex_texts = [t for t in all_texts if "capex" in t.lower() or "capital expenditure" in t.lower()]
    capex_values = sorted({round(v, 1) for t in capex_texts for v in _all_dollar_billions(t)})
    if len(capex_values) >= 2 and capex_values[0] > 0 and capex_values[-1] / capex_values[0] > 8:
        issues.append(
            f"CapEx-labeled figures in this brief span an implausible range (${capex_values[0]}B to "
            f"${capex_values[-1]}B) -- this has previously turned out to be a stray, unrelated figure "
            "(e.g. backlog/RPO) mislabeled as CapEx. Verify every CapEx figure actually refers to "
            "capital expenditures, not a different metric, and remove/correct any that don't."
        )

    # Caught live against MSFT: financials.capex_guidance_prior_usd and
    # capex_guidance_updated_usd were correctly populated in the structured
    # data (verified accurate), but no bullet anywhere in financial_highlights
    # or sections actually stated either figure -- the guide-vs-prior context
    # was invisible to anyone reading the actual email. Structured-field
    # correctness alone doesn't guarantee the prose a reader sees says
    # anything -- this generalizes past just CapEx: any populated guide/prior
    # pair needs to actually appear in the text, not just the JSON.
    capex_prior = financials.get("capex_guidance_prior_usd")
    capex_updated = financials.get("capex_guidance_updated_usd")
    if isinstance(capex_prior, (int, float)) and isinstance(capex_updated, (int, float)):
        prose_billions = {v for text in all_texts for v in _all_dollar_billions(text)}
        prior_b = capex_prior / 1_000_000_000
        updated_b = capex_updated / 1_000_000_000
        prior_mentioned = any(abs(v - prior_b) < 2 for v in prose_billions)
        updated_mentioned = any(abs(v - updated_b) < 2 for v in prose_billions)
        if not (prior_mentioned and updated_mentioned):
            issues.append(
                f"financials.capex_guidance_prior_usd (${prior_b:.0f}B) and "
                f"capex_guidance_updated_usd (${updated_b:.0f}B) are populated in the structured "
                "data, but the prose (financial_highlights/sections) doesn't clearly state both "
                "figures -- a reader of the actual email would never see this. State both figures "
                "explicitly in a bullet, not just in the structured financials."
            )

    # Caught live against AMZN: a "revenue" bullet stated AWS at $20.3B when
    # the real, verified figure was $37.59B (nearly half) -- evidently
    # recalled from an earlier year rather than actually searched for this
    # report. A single segment/product-line's revenue can never legitimately
    # exceed the company's total revenue -- if one does, that's a structural
    # impossibility worth flagging even though this check can't catch every
    # wrong segment figure (it can't detect UNDERstatement, only figures that
    # are impossibly large; the prompt's explicit "search this specific
    # figure, don't rely on recall" instruction is the primary defense for
    # understatement, this is a backstop for the detectable half).
    total_revenue_b = None
    financials_revenue = financials.get("revenue_actual_usd")
    if isinstance(financials_revenue, (int, float)):
        total_revenue_b = financials_revenue / 1_000_000_000
    elif facts and isinstance(facts.get("last_q_revenue"), (int, float)):
        total_revenue_b = facts["last_q_revenue"] / 1_000_000_000
    if total_revenue_b:
        for section in brief.get("sections", []) or []:
            for bullet in section.get("bullets", []) or []:
                if not isinstance(bullet, dict):
                    continue
                text = str(bullet.get("text", ""))
                if "revenue" not in text.lower():
                    continue
                for value in _all_dollar_billions(text):
                    if value > total_revenue_b * 1.05:
                        issues.append(
                            f"A bullet in section '{section.get('heading', '')}' states a revenue "
                            f"figure (${value}B) that EXCEEDS total company revenue (${total_revenue_b:.1f}B) "
                            "-- a single segment/product line can never legitimately exceed total "
                            "revenue. This figure is wrong (likely from a different period or metric) "
                            "-- search again for the correct, current figure rather than reusing it."
                        )

    # Caught live against AMZN: a pre-earnings brief came back with real,
    # accurate figures (proving web search worked) but zero official_links
    # AND zero inline citations anywhere in the prose -- the rendered email
    # had no "Press Release / Investor Deck / Transcript" line and no
    # Sources footer at all, since both are populated from what the model
    # itself returns (official_links is a schema field; the Sources footer
    # is extracted from inline "([domain](url))" citations in the prose --
    # see render_pre_earnings_deep_dive_email.py). Neither is guaranteed by
    # the model just because search happened; both need to be checked.
    official_links = brief.get("official_links") or {}
    has_official_link = any(official_links.get(k) for k in ("press_release", "investor_deck", "transcript"))
    citation_texts = list(all_texts) + [str(brief.get("intro", ""))]
    has_inline_citation = any(_INLINE_CITATION_RE.search(t) for t in citation_texts)
    if not has_official_link and not has_inline_citation:
        issues.append(
            "This brief has no official_links (press_release/investor_deck/transcript all null) "
            "AND no inline citations anywhere in the prose -- the sent email will have no visible "
            "sourcing at all (no links line, no Sources footer). Find and include at least one "
            "official link, and add inline citations in the '([domain](url))' format after claims "
            "drawn from search results, per the instructions above."
        )

    if mode == "post":
        comparisons = [
            item for item in brief.get("estimate_comparisons", []) or []
            if isinstance(item, dict)
        ]
        if len(comparisons) < 2:
            issues.append(
                "Post-earnings brief has fewer than two period-matched estimate comparisons. "
                "Add a sourced scoreboard (normally revenue and adjusted EPS, plus guidance where available)."
            )
        for item in comparisons:
            missing = [
                key for key in ("metric", "reported", "estimate", "variance", "period", "estimate_source", "estimate_as_of", "source_url")
                if not str(item.get(key, "") or "").strip()
            ]
            if missing:
                issues.append(
                    f"Estimate comparison for '{item.get('metric') or 'unnamed metric'}' is missing "
                    f"{', '.join(missing)}. Every comparison needs traceable provider/date/source metadata."
                )
            if "ciq" in str(item.get("estimate_source", "")).lower() or "capital iq" in str(item.get("estimate_source", "")).lower():
                source_context = " ".join(str(item.get(key, "")) for key in ("estimate_source", "source_url"))
                if "capital" not in source_context.lower() and "ciq" not in source_context.lower():
                    issues.append(
                        f"Estimate comparison for '{item.get('metric') or 'unnamed metric'}' labels the source CIQ "
                        "without source evidence explicitly identifying S&P Capital IQ."
                    )

        valuation = brief.get("valuation_reference") or {}
        required_valuation = ("enterprise_value", "cy_revenue", "ev_cy_revenue", "basis", "as_of", "source", "source_url")
        if not isinstance(valuation, dict) or any(not str(valuation.get(key, "") or "").strip() for key in required_valuation):
            issues.append(
                "Post-earnings brief is missing a complete sourced EV / CY revenue reference. "
                "Provide dated EV, calendarized revenue, the multiple, methodology, and source; if using a fiscal-year "
                "proxy, label it explicitly instead of calling it CY."
            )

    return issues


def _drop_flagged_key_metrics(brief: Dict[str, Any], issues: List[str]) -> Dict[str, Any]:
    flagged_metrics = set()
    for issue in issues:
        match = re.match(r"Key metric '(.+)' (?:conflicts|states)", issue)
        if match:
            flagged_metrics.add(match.group(1))
    if not flagged_metrics:
        return brief
    cleaned = dict(brief)
    cleaned["key_metrics"] = [
        metric for metric in brief.get("key_metrics", []) or [] if str(metric) not in flagged_metrics
    ]
    return cleaned


def earnings_brief_delivery_issues(
    brief: Dict[str, Any], mode: str, facts: Dict[str, Any]
) -> List[str]:
    """Public deterministic delivery check for non-web-search fallbacks."""
    return _sanity_check_brief(brief, mode=mode, facts=facts)


def synthesize_earnings_brief_with_review(
    ticker: str,
    company: str,
    quarter: str,
    mode: str,
    facts: Dict[str, Any],
    model: str = "",
) -> Dict[str, Any]:
    """Primary web-search synthesis, followed by an automated gut-check review
    before the brief is handed back to the caller for sending. Each round combines
    the LLM reviewer's findings with a deterministic numeric sanity check (revenue
    vs. net income plausibility) -- the LLM reviewer can correctly flag a bad number
    without the following re-synthesis actually fixing it, so the sanity check keeps
    re-flagging it independently of what the model claims to have corrected. Bounded
    to 2 revision rounds so a stubborn brief can't loop cost/latency indefinitely.
    Same return shape as synthesize_earnings_brief_with_web_search ({} if
    unavailable)."""
    working_facts = dict(facts)
    if mode == "post":
        report_date = str(working_facts.get("report_date") or "")
        verified_url = _VERIFIED_RELEASE_URLS.get((ticker.upper(), report_date), "")
        verified_text = _fetch_release_page_text(verified_url) if verified_url else ""
        if verified_text:
            working_facts["official_release_source_text"] = verified_text
            working_facts["official_release_source_url"] = verified_url
            verified_period = _extract_official_fiscal_period(
                [{"title": "", "snippet": verified_text, "url": verified_url, "published_date": report_date}],
                report_date,
                company,
            )
            if verified_period:
                working_facts["official_fiscal_quarter_label"] = verified_period
            print(
                f"[synthesis] Loaded verified issuer release for {ticker}: source={verified_url} "
                f"chars={len(verified_text)} period={verified_period or 'unresolved'}",
                flush=True,
            )
        grounding = _official_release_grounding(
            ticker, company, report_date
        )
        if grounding.get("evidence"):
            working_facts["official_release_evidence"] = grounding["evidence"]
            working_facts["official_release_provider"] = grounding.get("provider", "")
        if grounding.get("fiscal_period") and not working_facts.get("official_fiscal_quarter_label"):
            working_facts["official_fiscal_quarter_label"] = grounding["fiscal_period"]
        if grounding.get("source_text") and not working_facts.get("official_release_source_text"):
            working_facts["official_release_source_text"] = grounding["source_text"]
            working_facts["official_release_source_url"] = grounding.get("source_url", "")

    brief = synthesize_earnings_brief_with_web_search(
        ticker, company, quarter, mode, working_facts, model=model
    )
    if not brief or not brief.get("sections"):
        return brief

    if mode == "post" and not working_facts.get("official_release_source_text"):
        release_url = str((brief.get("official_links") or {}).get("press_release") or "").strip()
        release_text = _fetch_release_page_text(release_url) if release_url else ""
        if release_text:
            working_facts["official_release_source_text"] = release_text
            working_facts["official_release_source_url"] = release_url
            recovered_period = _extract_official_fiscal_period(
                [
                    {
                        "title": "",
                        "snippet": release_text,
                        "url": release_url,
                        "published_date": working_facts.get("report_date"),
                    }
                ],
                str(working_facts.get("report_date") or ""),
                company,
            )
            if recovered_period:
                working_facts["official_fiscal_quarter_label"] = recovered_period
            print(
                f"[synthesis] Recovered direct issuer release from initial brief for {ticker}: "
                f"source={release_url} chars={len(release_text)} period={recovered_period or 'unresolved'}",
                flush=True,
            )
            rebuilt = synthesize_earnings_brief_with_web_search(
                ticker,
                company,
                quarter,
                mode,
                working_facts,
                model=model,
                extra_instructions="Rebuild this draft against the newly fetched direct issuer release.",
            )
            if rebuilt and rebuilt.get("sections"):
                brief = rebuilt

    sanity_issues: List[str] = []
    for attempt in range(2):
        review = review_earnings_brief(ticker, company, quarter, mode, working_facts, brief, model=model)
        sanity_issues = _sanity_check_brief(brief, mode=mode, facts=working_facts)
        issues = list(review.get("issues", [])) + sanity_issues
        if review.get("pass", True) and not issues:
            brief = dict(brief)
            brief["_qa_approved"] = True
            brief["_qa_issues"] = []
            return brief

        print(
            f"[review] {ticker}: {len(issues)} issue(s) found (attempt {attempt + 1}/2), "
            f"re-running with enrichment: {issues}",
            flush=True,
        )
        extra = "; ".join(issues)
        if review.get("follow_up_queries"):
            extra += ". Also specifically research: " + "; ".join(review["follow_up_queries"])
        revised = synthesize_earnings_brief_with_web_search(
            ticker, company, quarter, mode, working_facts, model=model, extra_instructions=extra
        )
        if not revised or not revised.get("sections"):
            blocked = dict(brief)
            blocked["_qa_approved"] = False
            blocked["_qa_issues"] = issues or ["revision failed after review"]
            return blocked
        brief = revised

    # Re-review the final revision. Previously, only the deterministic subset
    # was checked here, which meant unresolved reviewer findings could be lost
    # and a questionable brief could still be sent with a caveat.
    final_review = review_earnings_brief(ticker, company, quarter, mode, working_facts, brief, model=model)
    final_issues = list(final_review.get("issues", [])) + _sanity_check_brief(
        brief, mode=mode, facts=working_facts
    )
    cleaned_brief = _drop_flagged_key_metrics(brief, final_issues)
    if cleaned_brief is not brief:
        brief = cleaned_brief
        final_review = review_earnings_brief(ticker, company, quarter, mode, working_facts, brief, model=model)
        final_issues = list(final_review.get("issues", [])) + _sanity_check_brief(
            brief, mode=mode, facts=working_facts
        )

    brief = dict(brief)
    brief["_qa_approved"] = not final_issues and final_review.get("pass", True)
    brief["_qa_issues"] = final_issues
    if final_issues:
        # Keep dubious structured figures out of Convex, and let the caller's
        # delivery gate block the email entirely instead of asking the reader
        # to sort out an automated warning.
        financials = dict(brief.get("financials") or {})
        for key in ("revenue_actual_usd", "revenue_consensus_usd", "revenue_yoy_pct", "net_income_actual_usd"):
            financials[key] = None
        brief["financials"] = financials

    return brief


def _clean_official_links(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for key in ("press_release", "investor_deck", "transcript"):
        url = str(value.get(key) or "").strip()
        if url.lower().startswith("http"):
            cleaned[key] = url
    return cleaned


_FINANCIALS_KEYS = (
    "revenue_actual_usd", "revenue_consensus_usd", "revenue_yoy_pct",
    "net_income_actual_usd", "eps_actual", "eps_consensus", "eps_surprise_pct",
    "capex_actual_usd", "capex_guidance_prior_usd", "capex_guidance_updated_usd",
    "capex_guidance_analyst_estimate_usd",
)


def _clean_financials(value: Any) -> Dict[str, Any]:
    """Structured comparable figures for historical tracking -- keeps only
    the known keys, and only when they're a real number (not a string, not a
    hallucinated non-numeric placeholder)."""
    if not isinstance(value, dict):
        return {key: None for key in _FINANCIALS_KEYS}
    cleaned: Dict[str, Any] = {}
    for key in _FINANCIALS_KEYS:
        raw = value.get(key)
        cleaned[key] = raw if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
    return cleaned
