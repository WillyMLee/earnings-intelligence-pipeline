# Roadmap & known limitations

Honest accounting of what's solid, what's a known gap, and what a next iteration should prioritize. Grouped by theme, not by priority — read the "why it matters" lines to judge that yourself for your own use case.

## Live research & scraping

This is the area with the most room to improve, and where the next real investment should go.

- **No headless-browser fallback for sites that block simple fetches.** SEC EDGAR and some IR pages return a 403 to a plain HTTP fetch even when the content is public. The current cascade (`core/research.py`) works around this by trying multiple search/fetch providers until one succeeds (TinyFish in particular proved effective at retrieving full page content other providers couldn't), but there's no last-resort real browser (Playwright/Puppeteer) fallback for the cases where none of them do. That would close the remaining gap for primary-source pages that actively block bot traffic.
- **Transcript excerpt extraction is keyword-window heuristic, not semantic.** `_extract_focused_excerpts()` grabs fixed-size windows of text around a small hardcoded keyword list (`capital expenditure`, `lease`, `useful life`, etc.) rather than actually understanding which passage answers the question at hand. It works, but it's brittle to phrasing the keyword list doesn't anticipate, and it can accidentally juxtapose unrelated passages that happen to share proximity to a keyword (see the segment-bleed item below). A proper fix would embed the query and the document into the same vector space and retrieve by similarity instead of literal string matching — real RAG instead of a regex.
- **Transcript cache is now durable; semantic retrieval is still the next step.** Focused transcript excerpts are cached by ticker + report date, so repeated and backfill runs do not repay the scrape cost. Retrieval within a transcript is still scored keyword-window selection rather than embedding similarity.
- **`TICKER_IS_PORTCO` / segment-level ground truth doesn't exist generically.** There's no free, reliable source for a specific company's segment-level revenue breakdown (confirmed: `yfinance`'s income statement is company-wide only) the way there is for total revenue or CapEx. A dated anchor for segment figures — even a small hand-maintained lookup table for the handful of companies whose segment breakouts matter most to your coverage — would let guardrail #7 catch *understatement*, not just the structurally-impossible-overstatement case it catches today.

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
