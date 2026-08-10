# Roadmap & known limitations

Honest accounting of what's solid, what's a known gap, and what a next iteration should prioritize. Grouped by theme, not by priority — read the "why it matters" lines to judge that yourself for your own use case.

## Live research & scraping

This is the area with the most room to improve, and where the next real investment should go.

- **No headless-browser fallback for sites that block simple fetches.** SEC EDGAR and some IR pages return a 403 to a plain HTTP fetch even when the content is public. The current cascade (`core/research.py`) works around this by trying multiple search/fetch providers until one succeeds (TinyFish in particular proved effective at retrieving full page content other providers couldn't), but there's no last-resort real browser (Playwright/Puppeteer) fallback for the cases where none of them do. That would close the remaining gap for primary-source pages that actively block bot traffic.
- **Transcript excerpt extraction is keyword-window heuristic, not semantic.** `_extract_focused_excerpts()` grabs fixed-size windows of text around a small hardcoded keyword list (`capital expenditure`, `lease`, `useful life`, etc.) rather than actually understanding which passage answers the question at hand. It works, but it's brittle to phrasing the keyword list doesn't anticipate, and it can accidentally juxtapose unrelated passages that happen to share proximity to a keyword (see the segment-bleed item below). A proper fix would embed the query and the document into the same vector space and retrieve by similarity instead of literal string matching — real RAG instead of a regex.
- **Transcript cache is now durable; semantic retrieval is still the next step.** Focused transcript excerpts are cached by ticker + report date, so repeated and backfill runs do not repay the scrape cost. Retrieval within a transcript is still scored keyword-window selection rather than embedding similarity.
- **`TICKER_IS_PORTCO` / segment-level ground truth doesn't exist generically.** There's no free, reliable source for a specific company's segment-level revenue breakdown (confirmed: `yfinance`'s income statement is company-wide only) the way there is for total revenue or CapEx. A dated anchor for segment figures — even a small hand-maintained lookup table for the handful of companies whose segment breakouts matter most to your coverage — would let guardrail #7 catch *understatement*, not just the structurally-impossible-overstatement case it catches today.

## Historical actuals and company-profile backfill

This is the next major data project. It is deliberately recorded as outstanding rather than presenting partially inferred financials as complete.

### Quarterly actuals: Q1 2020 onward

Use SEC filings as the primary fact layer. The [SEC's EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) need no API key, expose XBRL facts from 10-Q, 10-K, 8-K, 20-F, 40-F and 6-K filings, and provide a nightly `companyfacts.zip` bulk archive. Fetch this server-side because `data.sec.gov` does not support browser CORS.

1. **One-time backfill:** download the nightly Company Facts ZIP once, filter it to the covered CIKs, and materialize quarters from Q1 2020. Do not make thousands of repeated filing requests.
2. **Incremental refresh:** after filing days, refresh one Company Facts document per reporting company, cache it by CIK, and skip unchanged accessions. Keep the worker comfortably below the SEC's [10 requests/second ceiling](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits); four requests/second with identification and retry/backoff is the intended operating limit.
3. **Primary-source fallback:** only when standardized XBRL is absent or ambiguous, inspect the filed 8-K earnings-release exhibit, 10-Q/10-K, shareholder letter, or investor-relations release. Store the exact source URL and accession with every fallback fact.
4. **Derive after normalization:** calculate gross margin, EBITDA margin, net margin, sequential growth and year-over-year growth from normalized facts. Never ask a model to calculate ratios that code can calculate deterministically.

Canonical quarterly fields:

- Revenue; gross profit; net income.
- EBITDA and adjusted EBITDA only when explicitly company-reported, kept as distinct concepts. Do not manufacture adjusted EBITDA from GAAP tags.
- Cash plus short-term investments, with the components retained; total debt split between current and long-term when available.
- ARR and NRR only when the company reports them, with definition text and source because these KPIs are not standardized.
- Derived gross margin, EBITDA margin and net margin, plus QoQ and YoY growth for each compatible metric.

Each stored fact needs ticker, CIK, fiscal year/quarter, period start/end, unit, form, filed date, accession, source URL, taxonomy tag, value and confidence. Duration facts in Q2/Q3 filings can be year-to-date; create standalone quarters by subtracting prior YTD values only when the periods align. Prefer amended/restated accessions over stale values and preserve the old provenance for auditability. The current coverage universe is roughly 147 companies, or about 3,800 company-quarter rows through Q3 2026 before duplicates and restatements—small enough for an inexpensive nightly materialization job.

### Company summaries and product/service bullets

Build a compact source packet for each company from the latest 10-K/20-F business description and official product pages. Hash that packet and only regenerate a profile when the source hash changes. A profile record should contain:

- A two-to-four sentence executive summary.
- Structured `productsAndServices[]` entries with a short boldable name and one-sentence plain-English description.
- Source URLs, source filing accession, `updatedAt`, and source hash.

This non-urgent enrichment is a good fit for the [OpenAI Batch API](https://developers.openai.com/api/reference/resources/batches), which processes asynchronous JSONL batches within its completion window at a discounted batch rate. Run one structured-output request per changed company, validate length/duplication/source coverage, and review failures separately instead of paying to regenerate the whole universe. Refresh annually after the 10-K/20-F and selectively after a material product change.

### Dashboard integration still outstanding

- Add a `quarterlyFinancials` archive table and idempotent upsert keyed by company, metric, period and filing accession.
- Replace the current sparse company Trends view with metric toggles for absolute values, margins, QoQ and YoY growth from Q1 2020 onward; show unavailable EBITDA/ARR/NRR as unavailable rather than zero.
- Render the profile executive summary and product/service bullets from the versioned profile record.
- Add freshness and provenance affordances so a reader can distinguish filed GAAP facts, company-reported non-GAAP/KPI facts and model-written descriptions.
- Run reconciliation QA on a representative set of calendar-year companies, non-calendar fiscal years, foreign issuers, banks, insurers and REITs before broad deployment.

## Guardrail gaps (known, not yet fixed)

- **Segment-vs-company-wide figure bleed.** Because the focused-excerpt extraction (above) can juxtapose a segment-level figure with company-wide commentary in the same window, a model has been observed misattributing a segment's operating income/growth rate to the company-wide `financials` fields. No deterministic check catches this today. A reasonable next step: cross-reference `revenue_yoy_pct` (and similar derived fields) against the independently-known prior-period actual for implausible drift, the same pattern already used for revenue/consensus divergence.
- **`net_income_actual_usd` / `eps_actual` intermittently come back null** even when the same figures appear correctly in prose. Low-severity (the prose captures it), but it means the structured historical-tracking record has gaps that don't show up unless you go looking.
- **`capex_actual_usd` has an unresolved unit ambiguity**: some runs populate it with the quarter's actual CapEx, others with the full fiscal year's actual, depending on what the model happened to emphasize. This breaks quarter-over-quarter comparability for exactly the field structured tracking exists to make comparable. Fix: split into two explicit fields (`capex_actual_usd` for the quarter, `capex_fy_actual_usd` for the year) rather than overloading one field's meaning.
- **Archive schema drift risk.** The Python-side structured `financials` schema (`core/synthesis.py`) and the archive table schema (`convex/schema.js`) are two independently-maintained lists of fields with no shared source of truth — it's possible (and has happened) for a new field to be added to one and not the other, silently dropping it on write. Worth generating one from the other, or at minimum a CI check that diffs them.

## Feature roadmap (deferred, sequenced)

These were explicitly sequenced as "later, once real multi-quarter data exists" — premature before the archive has accumulated enough history to make them meaningful:

1. **Sector/industry trend aggregation** — beat-rate and growth comparisons across a sector, now that every post-earnings summary is tagged with one (`core/coverage.py`).
2. **A research UI** for browsing the archive interactively instead of only receiving push emails.
3. **Merge with private-company/portfolio tracking** — if your fund also tracks private portfolio companies elsewhere, `PORTCO_TICKERS` in `core/coverage.py` is deliberately shaped as the join key for that merge, but no cross-system wiring exists yet.

## Smaller, lower-priority items

- Render cron schedules are hardcoded in UTC assuming EDT (no DST-adjustment logic) — they'll drift an hour during EST months. Fine for a fund that's paying attention every quarter; a real fix would compute the UTC offset per-run rather than hardcoding it.
- Local development doesn't have the archive-write credential configured by default, so local test runs silently skip archiving rather than erroring — convenient for iteration, but means "it ran without errors locally" isn't proof the archive write actually works; that still needs a real (or staging) credential to verify end to end.
