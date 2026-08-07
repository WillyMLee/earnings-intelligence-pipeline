from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence


COMPANY_STOPWORDS = {
    "company",
    "co",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "ltd",
    "limited",
    "plc",
    "group",
    "holdings",
    "technology",
    "technologies",
}


def _request_json(
    method: str,
    url: str,
    headers: Dict[str, str],
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 25,
) -> Dict[str, Any]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{url} returned HTTP {err.code}: {body}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"{url} network error: {err}") from err
    return json.loads(raw) if raw else {}


def _truncate(value: str, limit: int = 280) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _to_iso_date(value: str) -> str:
    if not value:
        return ""
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        pass
    # Some providers (e.g. LLMLayer) return relative strings like "5 hours ago"
    # instead of a date -- not parseable, so don't truncate it into fake ISO-ish
    # garbage. Leave it blank; published_at still carries the original text.
    candidate = value[:10]
    return candidate if candidate[:1].isdigit() and "-" in candidate else ""


def _domain_from_url(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _coalesce_snippet(item: Dict[str, Any]) -> str:
    highlights = item.get("highlights") or []
    if isinstance(highlights, list):
        for candidate in highlights:
            text = _truncate(str(candidate or ""))
            if text:
                return text
    for key in ("summary", "content", "snippet", "text", "description"):
        text = _truncate(str(item.get(key, "") or ""))
        if text:
            return text
    fetch_payload = item.get("fetch") or {}
    if isinstance(fetch_payload, dict):
        for key in ("text", "description"):
            text = _truncate(str(fetch_payload.get(key, "") or ""))
            if text:
                return text
    return ""


def _coalesce_raw_content(item: Dict[str, Any], limit: int = 45000) -> str:
    """Unlike _coalesce_snippet (truncated to 280 chars for display), this
    preserves the actual full page content some providers return -- e.g.
    Tavily's include_raw_content="markdown" fetches the entire page, but
    every call site was discarding all but the first 280 characters of it
    before this existed, which meant "the AI reading the transcript" never
    actually had the transcript to read. Only used by callers that
    specifically need real page text (see fetch_transcript_excerpt below),
    not the default snippet-based research flow."""
    for key in ("raw_content", "content", "markdown", "full_text", "text"):
        text = str(item.get(key, "") or "").strip()
        if len(text) > 200:
            return text[:limit]
    fetch_payload = item.get("fetch") or {}
    if isinstance(fetch_payload, dict):
        for key in ("raw_content", "content", "text"):
            text = str(fetch_payload.get(key, "") or "").strip()
            if len(text) > 200:
                return text[:limit]
    return ""


def _normalize_result(provider: str, item: Dict[str, Any]) -> Dict[str, str]:
    url = str(item.get("url") or item.get("final_url") or item.get("link") or "").strip()
    published = str(
        item.get("published_at")
        or item.get("publishedDate")
        or item.get("published_date")
        or item.get("date")
        or (item.get("fetch") or {}).get("published_date", "")
    ).strip()
    return {
        "provider": provider,
        "title": str(item.get("title") or "Untitled source").strip(),
        "url": url,
        "domain": str(item.get("site_name") or item.get("source") or _domain_from_url(url)).strip(),
        "published_at": published,
        "published_date": _to_iso_date(published),
        "snippet": _coalesce_snippet(item),
        "raw_content": _coalesce_raw_content(item),
    }


def _entity_tokens(company: str, ticker: str) -> List[str]:
    tokens: List[str] = []
    clean_ticker = str(ticker or "").strip().upper()
    if len(clean_ticker) >= 3:
        tokens.append(clean_ticker)
    for token in str(company or "").replace("&", " ").split():
        normalized = "".join(ch for ch in token.lower() if ch.isalnum())
        if len(normalized) < 4 or normalized in COMPANY_STOPWORDS:
            continue
        tokens.append(normalized)
    deduped: List[str] = []
    seen = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def filter_results_for_entity(
    results: Iterable[Dict[str, str]],
    company: str,
    ticker: str,
) -> List[Dict[str, str]]:
    tokens = _entity_tokens(company, ticker)
    if not tokens:
        return list(results)

    matched: List[Dict[str, str]] = []
    for item in results:
        combined = " ".join(
            str(item.get(key, "") or "")
            for key in ("title", "snippet", "url", "domain")
        )
        combined_lower = combined.lower()
        combined_upper = combined.upper()
        if any(
            token in combined_upper if token.isupper() else token in combined_lower
            for token in tokens
        ):
            matched.append(item)
    return matched


def search_tavily(
    query: str,
    max_results: int = 3,
    include_domains: Optional[Sequence[str]] = None,
) -> List[Dict[str, str]]:
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []
    payload: Dict[str, Any] = {
        "query": query,
        "topic": "finance",
        "search_depth": "advanced",
        "chunks_per_source": 2,
        "max_results": max(1, min(int(max_results), 10)),
        "include_raw_content": "markdown",
    }
    if include_domains:
        payload["include_domains"] = [domain for domain in include_domains if domain]
    response = _request_json(
        "POST",
        "https://api.tavily.com/search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    return [_normalize_result("tavily", item) for item in response.get("results", []) or []]


def search_exa(
    query: str,
    max_results: int = 3,
    include_domains: Optional[Sequence[str]] = None,
) -> List[Dict[str, str]]:
    api_key = os.environ.get("EXA_API_KEY", "").strip()
    if not api_key:
        return []
    payload: Dict[str, Any] = {
        "query": query,
        "type": "auto",
        "numResults": max(1, min(int(max_results), 10)),
        "contents": {
            "text": True,
            "highlights": True,
            "summary": True,
        },
    }
    if include_domains:
        payload["includeDomains"] = [domain for domain in include_domains if domain]
    response = _request_json(
        "POST",
        "https://api.exa.ai/search",
        headers={
            "x-api-key": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    return [_normalize_result("exa", item) for item in response.get("results", []) or []]


def search_tinyfish(
    query: str,
    max_results: int = 3,
    include_domains: Optional[Sequence[str]] = None,
) -> List[Dict[str, str]]:
    api_key = os.environ.get("TINYFISH_API_KEY", "").strip()
    if not api_key:
        return []

    location = os.environ.get("TINYFISH_LOCATION", "US").strip() or "US"
    language = os.environ.get("TINYFISH_LANGUAGE", "en").strip() or "en"

    scoped_query = query
    if include_domains:
        domains = [domain for domain in include_domains if domain]
        if len(domains) == 1:
            scoped_query = f"{query} site:{domains[0]}"
        elif domains:
            # Space-joined "site:a site:b" is interpreted as AND by most search
            # backends -- impossible to satisfy across >1 distinct domain, so
            # a multi-domain hint silently matched nothing and fell through to
            # an unrestricted search. OR them explicitly instead.
            scoped_query = f"{query} (" + " OR ".join(f"site:{d}" for d in domains) + ")"

    fetch_config = json.dumps({"format": "markdown", "ttl": 0})
    params = urllib.parse.urlencode(
        {
            "query": scoped_query,
            "location": location,
            "language": language,
            "page": 0,
            "include_thumbnail": "false",
            "fetch": fetch_config,
        }
    )
    response = _request_json(
        "GET",
        f"https://api.search.tinyfish.ai?{params}",
        headers={
            "X-API-Key": api_key,
            "Accept": "application/json",
        },
    )
    return [
        _normalize_result("tinyfish", item)
        for item in (response.get("results", []) or [])[: max(1, min(int(max_results), 10))]
    ]


def search_llmlayer(
    query: str,
    max_results: int = 3,
    include_domains: Optional[Sequence[str]] = None,
) -> List[Dict[str, str]]:
    api_key = os.environ.get("LLMLAYER_API_KEY", "").strip()
    if not api_key:
        return []
    payload: Dict[str, Any] = {
        "query": query,
        "search_type": "news",
        "location": "us",
    }
    if include_domains:
        payload["domain_filter"] = [domain for domain in include_domains if domain]
    response = _request_json(
        "POST",
        "https://api.llmlayer.dev/api/v2/web_search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    return [
        _normalize_result("llmlayer", item)
        for item in (response.get("results", []) or [])[: max(1, min(int(max_results), 10))]
    ]


_TRANSCRIPT_HOST_HINTS = (
    "fool.com",
    "seekingalpha.com",
    "alphastreet.com",
    "investing.com",
    "einvestingforbeginners.com",
)


_TRANSCRIPT_FOCUS_KEYWORDS = (
    "capital expenditure",
    "capex",
    "useful life",
    "lease",
    "reclassif",
    "guidance", "outlook", "gross margin", "operating margin", "free cash flow",
    "backlog", "bookings", "demand", "pricing", "capacity", "customer growth",
    "artificial intelligence", "question-and-answer", "q&a", "analyst",
)
# Deliberately excludes generic terms like "guidance" and "outlook" -- caught
# live: those appear repeatedly in boilerplate forward-looking-statements
# disclaimers near the top of every call, crowding out the extraction budget
# before it ever reaches the specific CapEx/lease passage later in the call.


def _extract_focused_excerpts(text: str, max_total: int = 8000, window: int = 1200) -> str:
    """Pull windows of text around guidance/CapEx-relevant keywords instead
    of a blind head-slice of the transcript -- caught live: injecting a full
    40,000-char transcript into the synthesis prompt caused the model's
    structured JSON output to break entirely (empty brief), likely from
    combined prompt size + web_search tool use + strict schema output
    exceeding what a "mini" model handles reliably. A focused excerpt covers
    the same nuance (the exact passage this exists for is usually a few
    hundred words around "capital expenditure"/"lease"/"guidance") in a
    fraction of the size, and skips boilerplate operator/intro text the
    model doesn't need anyway."""
    normalized = text.replace("\r\n", "\n")
    chunks: List[tuple[int, int, str]] = []
    step = max(400, window - 250)
    for start in range(0, len(normalized), step):
        chunk = normalized[start : start + window].strip()
        if len(chunk) < 180:
            continue
        lower = chunk.lower()
        keyword_hits = sum(1 for keyword in _TRANSCRIPT_FOCUS_KEYWORDS if keyword in lower)
        numeric_evidence = int("$" in chunk) + int("%" in chunk) + int(any(char.isdigit() for char in chunk))
        qa_signal = int("question-and-answer" in lower or "operator" in lower or "analyst" in lower)
        boilerplate_penalty = 4 if "forward-looking statements" in lower and keyword_hits < 2 else 0
        score = keyword_hits * 3 + numeric_evidence + qa_signal * 2 - boilerplate_penalty
        if score > 1:
            chunks.append((score, start, chunk))
    if not chunks:
        return normalized[:max_total]
    selected: List[tuple[int, str]] = []
    for _score, start, chunk in sorted(chunks, key=lambda item: (-item[0], item[1])):
        if any(abs(start - prior_start) < step for prior_start, _ in selected):
            continue
        selected.append((start, chunk))
        if sum(len(piece) for _, piece in selected) >= max_total:
            break
    selected.sort(key=lambda item: item[0])
    pieces: List[str] = []
    remaining = max_total
    for _start, chunk in selected:
        if remaining < 180:
            break
        piece = chunk[:remaining].strip()
        pieces.append(piece)
        remaining -= len(piece)
    return "\n[...]\n".join(pieces)


_QA_SECTION_RE = re.compile(
    r"(?:question[\s-]*(?:and|&)[\s-]*answer(?:[\s-]+session)?|questions[\s-]*(?:and|&)[\s-]*answers|analyst\s+q\s*&\s*a)",
    re.IGNORECASE,
)


def _extract_transcript_sections(text: str, max_total: int = 8000) -> Dict[str, str]:
    """Keep prepared remarks and analyst Q&A inside separate prompt budgets."""
    normalized = text.replace("\r\n", "\n")
    match = _QA_SECTION_RE.search(normalized)
    if not match:
        excerpt = _extract_focused_excerpts(normalized, max_total=max_total)
        return {"text": excerpt, "prepared_text": excerpt, "qa_text": ""}
    prepared_budget = max(1200, int(max_total * 0.42))
    qa_budget = max(1600, max_total - prepared_budget - 60)
    prepared = _extract_focused_excerpts(normalized[:match.start()], max_total=prepared_budget)
    qa = _extract_focused_excerpts(normalized[match.start():], max_total=qa_budget)
    return {"text": f"[PREPARED REMARKS]\n{prepared}\n\n[ANALYST Q&A]\n{qa}"[:max_total], "prepared_text": prepared, "qa_text": qa}


def _convex_artifact_request(kind: str, path: str, args: Dict[str, Any]) -> Any:
    convex_url = os.environ.get("CONVEX_URL", "").strip()
    if not convex_url:
        return None
    payload = _request_json("POST", f"{convex_url.rstrip('/')}/api/{kind}", {"Accept": "application/json", "Content-Type": "application/json"}, {"path": path, "args": args, "format": "json"}, 30)
    if payload.get("status") != "success":
        raise RuntimeError(payload.get("errorMessage") or f"Convex {path} failed")
    return payload.get("value")


def _load_cached_transcript(ticker: str, report_date: str, max_chars: int) -> Dict[str, str]:
    if not report_date:
        return {}
    try:
        cached = _convex_artifact_request("query", "researchArtifacts:getArtifact", {"kind": "transcript_excerpt_v2", "ticker": ticker.upper(), "reportDate": report_date})
        cached_qa = _convex_artifact_request("query", "researchArtifacts:getArtifact", {"kind": "transcript_qa_excerpt_v2", "ticker": ticker.upper(), "reportDate": report_date})
    except Exception as exc:
        print(f"[research] Transcript cache read failed for {ticker} (non-fatal): {exc}", flush=True)
        return {}
    if not isinstance(cached, dict) or not cached.get("text"):
        return {}
    return {"url": str(cached.get("url") or ""), "title": str(cached.get("title") or ""), "text": str(cached.get("text") or "")[:max_chars], "qa_text": str(cached_qa.get("text") or "") if isinstance(cached_qa, dict) else "", "provider": str(cached.get("provider") or "cache"), "cache_hit": "true"}


def _store_cached_transcript(ticker: str, report_date: str, artifact: Dict[str, str]) -> None:
    token = os.environ.get("EARNINGS_ARCHIVE_TOKEN", "").strip() or os.environ.get("ADMIN_TOKEN", "").strip()
    if not report_date or not token or not artifact.get("text"):
        return
    try:
        _convex_artifact_request("mutation", "researchArtifacts:upsertArtifact", {"adminToken": token, "kind": "transcript_excerpt_v2", "ticker": ticker.upper(), "reportDate": report_date, "url": artifact.get("url", ""), "title": artifact.get("title", ""), "text": artifact["text"], "provider": artifact.get("provider", "")})
        if artifact.get("qa_text"):
            _convex_artifact_request("mutation", "researchArtifacts:upsertArtifact", {"adminToken": token, "kind": "transcript_qa_excerpt_v2", "ticker": ticker.upper(), "reportDate": report_date, "url": artifact.get("url", ""), "title": artifact.get("title", ""), "text": artifact["qa_text"], "provider": artifact.get("provider", "")})
    except Exception as exc:
        print(f"[research] Transcript cache write failed for {ticker} (non-fatal): {exc}", flush=True)


def fetch_transcript_excerpt(
    ticker: str,
    company: str,
    quarter: str,
    report_date: str = "",
    max_chars: int = 8000,
) -> Dict[str, str]:
    """Find and return a focused excerpt of the ACTUAL earnings-call
    transcript text (not a ~280-char snippet) for grounding nuanced guidance
    figures that are easy to garble from search snippets alone -- caught
    live: MSFT's CapEx guidance ("investment plan unchanged, reported figure
    shifts due to a lease-accounting reclassification") was only understood
    correctly after reading the actual transcript language, not summary
    snippets. Every research provider's raw page content was being discarded
    down to ~280 chars before this existed (see _coalesce_raw_content), which
    meant "the AI reading the transcript" never had the transcript to read
    even when a provider had actually fetched it. The excerpt itself is
    keyword-focused (see _extract_focused_excerpts), not a blind head-slice
    -- a full 40k-char transcript dump was tried first and broke the
    downstream model's structured JSON output entirely.

    Tries Tavily first (explicitly requests full raw markdown page content
    via include_raw_content), then TinyFish, then LLMLayer -- stops as soon
    as a result has enough real content to be worth using. Returns {} if no
    provider is configured or none returned substantial transcript content;
    callers should treat that as "no transcript available" and fall back to
    whatever other research they already do, not as an error.

    report_date (YYYY-MM-DD), when given, is used INSTEAD of `quarter` in the
    query -- caught live: `quarter` here is often still the caller's rough,
    frequently-wrong calendar-quarter guess (the exact thing the rest of this
    pipeline treats as unreliable), and searching with a wrong quarter number
    returned a real but WRONG-PERIOD transcript (the prior quarter's call)
    with high confidence, which would have silently grounded the brief in
    stale data. report_date is reliable (it's the actual scheduled/known
    report date) and disambiguates just as well without that risk."""
    cached = _load_cached_transcript(ticker, report_date, max_chars)
    if cached:
        print(f"[research] Transcript excerpt cache hit for {ticker} {report_date}", flush=True)
        return cached

    # "earnings call transcript" alone tends to surface the company's own
    # press-release page (which has the headline numbers but not CFO/analyst
    # Q&A commentary) over an actual transcript -- caught live: this missed
    # the specific CFO quote explaining a CapEx guidance change. Biasing the
    # query toward "prepared remarks" / "Q&A" pulls transcript-focused pages
    # (Motley Fool, Seeking Alpha, AlphaStreet, Investing.com all publish
    # full transcripts under this framing) instead.
    # Include both the date and the quarter guess for redundant specificity
    # -- a bare date alone was observed to dilute company relevance enough
    # that the search drifted to an unrelated company's transcript from
    # around the same date (now also guarded against by _mentions_entity
    # below, but a better-targeted query needs it less often).
    period_hint = " ".join(part for part in (report_date, quarter) if part)
    query = f"{company} ({ticker}) {period_hint} earnings call transcript prepared remarks Q&A CFO"
    providers = []
    if os.environ.get("TAVILY_API_KEY", "").strip():
        providers.append(("tavily", search_tavily))
    if os.environ.get("TINYFISH_API_KEY", "").strip():
        providers.append(("tinyfish", search_tinyfish))
    if os.environ.get("LLMLAYER_API_KEY", "").strip():
        providers.append(("llmlayer", search_llmlayer))

    entity_tokens = _entity_tokens(company, ticker)

    def _mentions_entity(text: str) -> bool:
        # Verify the fetched page is actually ABOUT this company, not just
        # that it matched the search query -- caught live: a query built
        # around a report date pulled a completely different company's
        # ("Fortrea") transcript from around the same date. filter_results_
        # for_entity() below checks title/snippet/url, but a mismatched
        # snippet-vs-content situation is exactly the failure mode being
        # guarded against here, so also check the actual fetched text.
        if not entity_tokens:
            return True
        lower = text.lower()
        upper = text.upper()
        return any(token in upper if token.isupper() else token in lower for token in entity_tokens)

    best: Dict[str, str] = {}
    best_len = 0
    for provider_name, search_fn in providers:
        try:
            results = search_fn(query=query, max_results=3, include_domains=_TRANSCRIPT_HOST_HINTS)
            if not results:
                results = search_fn(query=query, max_results=3)
        except Exception as exc:
            print(f"[research] Transcript search via {provider_name} failed: {exc}", flush=True)
            continue
        results = filter_results_for_entity(results, company, ticker)
        for item in results:
            raw = item.get("raw_content", "")
            if len(raw) > best_len and _mentions_entity(raw):
                sections = _extract_transcript_sections(raw, max_total=max_chars)
                best = {
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "text": sections["text"],
                    "qa_text": sections["qa_text"],
                    "provider": item.get("provider", provider_name),
                }
                best_len = len(raw)
        if best_len > 2000:
            break

    if best_len < 500:
        return {}
    print(
        f"[research] Transcript excerpt for {ticker} found via {best.get('provider')} "
        f"({best_len} chars from {best.get('url')})",
        flush=True,
    )
    _store_cached_transcript(ticker, report_date, best)
    return best


def merge_sources(
    existing_sources: Iterable[Dict[str, Any]],
    research_results: Iterable[Dict[str, str]],
    prefix: str = "R",
) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    seen = set()

    for source in existing_sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", "")).strip()
        key = url or str(source.get("title", "")).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "id": str(source.get("id", f"{prefix}{len(merged) + 1}")).strip(),
                "title": str(source.get("title", "Untitled")).strip(),
                "url": url,
                "date": str(source.get("date", "")).strip(),
                "note": str(source.get("note", "")).strip(),
            }
        )

    for item in research_results:
        url = str(item.get("url", "")).strip()
        key = url or str(item.get("title", "")).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        note_parts = [part for part in (item.get("provider", "").upper(), item.get("snippet", "")) if part]
        merged.append(
            {
                "id": f"{prefix}{len(merged) + 1}",
                "title": str(item.get("title", "Untitled")).strip(),
                "url": url,
                "date": str(item.get("published_date", "")).strip(),
                "note": _truncate(" | ".join(note_parts), 220),
            }
        )

    return merged


def _dedup_append(
    item: Dict[str, str],
    collected: List[Dict[str, str]],
    seen_urls: "set[str]",
    provider_name: str,
) -> None:
    url = str(item.get("url", "")).strip()
    key = url or f"{item.get('title', '')}|{provider_name}"
    if not key or key in seen_urls:
        return
    seen_urls.add(key)
    collected.append(item)


def _sort_collected(collected: List[Dict[str, str]]) -> None:
    collected.sort(
        key=lambda item: (
            item.get("published_date", "") or "",
            item.get("provider", ""),
            item.get("title", ""),
        ),
        reverse=True,
    )


# Exa has credits again, but per direct instruction it's being held back from
# the cascade for now (LLMLayer is primary). Flip this back to True to
# re-enable it -- the rest of the cascade logic doesn't need to change.
_EXA_ENABLED = False


def run_research_query_cascade(
    query: str,
    max_results_per_provider: int = 2,
    include_domains: Optional[Sequence[str]] = None,
    min_results_before_tavily: int = 2,
    min_results_before_tinyfish: int = 1,
) -> Dict[str, Any]:
    """Cascade: LLMLayer first (primary), Exa held back for now, Tavily only
    if still under threshold, Tinyfish as last resort."""
    collected: List[Dict[str, str]] = []
    errors: List[str] = []
    seen_urls: "set[str]" = set()
    providers_used: List[str] = []

    if os.environ.get("LLMLAYER_API_KEY", "").strip():
        try:
            for item in search_llmlayer(query=query, max_results=max_results_per_provider, include_domains=include_domains):
                _dedup_append(item, collected, seen_urls, "llmlayer")
            providers_used.append("llmlayer")
        except Exception as err:
            errors.append(f"llmlayer: {err}")

    if _EXA_ENABLED and len(collected) < min_results_before_tavily and os.environ.get("EXA_API_KEY", "").strip():
        try:
            for item in search_exa(query=query, max_results=max_results_per_provider, include_domains=include_domains):
                _dedup_append(item, collected, seen_urls, "exa")
            providers_used.append("exa")
        except Exception as err:
            errors.append(f"exa: {err}")

    if len(collected) < min_results_before_tavily and os.environ.get("TAVILY_API_KEY", "").strip():
        try:
            for item in search_tavily(query=query, max_results=max_results_per_provider, include_domains=include_domains):
                _dedup_append(item, collected, seen_urls, "tavily")
            providers_used.append("tavily")
        except Exception as err:
            errors.append(f"tavily: {err}")

    if len(collected) < min_results_before_tinyfish and os.environ.get("TINYFISH_API_KEY", "").strip():
        try:
            for item in search_tinyfish(query=query, max_results=max_results_per_provider, include_domains=include_domains):
                _dedup_append(item, collected, seen_urls, "tinyfish")
            providers_used.append("tinyfish")
        except Exception as err:
            errors.append(f"tinyfish: {err}")

    _sort_collected(collected)
    return {
        "query": query,
        "results": collected,
        "errors": errors,
        "provider_count": len(providers_used),
    }


def run_research_query(
    query: str,
    max_results_per_provider: int = 2,
    include_domains: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    providers = (
        ("llmlayer", search_llmlayer),
        ("tavily", search_tavily),
        ("tinyfish", search_tinyfish),
    )
    if _EXA_ENABLED:
        providers = (("exa", search_exa),) + providers
    collected: List[Dict[str, str]] = []
    errors: List[str] = []
    seen_urls: "set[str]" = set()

    for provider_name, provider_fn in providers:
        try:
            results = provider_fn(
                query=query,
                max_results=max_results_per_provider,
                include_domains=include_domains,
            )
        except Exception as err:
            errors.append(f"{provider_name}: {err}")
            continue
        for item in results:
            _dedup_append(item, collected, seen_urls, provider_name)

    _sort_collected(collected)
    return {
        "query": query,
        "results": collected,
        "errors": errors,
        "provider_count": len([name for name, _ in providers if os.environ.get(f"{name.upper()}_API_KEY")]),
    }
