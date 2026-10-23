"""Issuer announcements supersede estimated market-data calendar dates.

Refresh the registered issuers' announcements on every calendar fetch. The
verified seed events also support replay after a provider drops past dates.
Never carry an estimate from a displaced date to the confirmed date.
"""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta


ISSUERS = {
    "SPOT": {"company": "Spotify", "index": "https://investors.spotify.com/news/default.aspx"},
    "META": {"company": "Meta Platforms", "index": "https://investor.atmeta.com/investor-news/default.aspx"},
    "SPCX": {"company": "SpaceX", "index": "https://ir.spacex.com/updates/default.aspx"},
    "NFLX": {"company": "Netflix", "index": "https://ir.netflix.net/investor-news-and-events/financial-releases/default.aspx"},
}
VERIFIED_EVENTS = [
    {"Ticker": "SPOT", "Company Name": "Spotify", "Report Date": "2026-10-22", "Report Time": "Before Open", "Source URL": "https://investors.spotify.com/files/content_files/Q3-2026-Shareholder-Deck-FINAL.pdf"},
    {"Ticker": "META", "Company Name": "Meta Platforms", "Report Date": "2026-10-21", "Report Time": "After Close", "Source URL": "https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-to-Announce-Third-Quarter-2026-Results/default.aspx"},
    {"Ticker": "SPCX", "Company Name": "SpaceX", "Report Date": "2026-10-20", "Report Time": "After Close", "Source URL": "https://ir.spacex.com/updates/releases-details/2026/SpaceX-to-Post-Third-Quarter-2026-Results-and-Host-Webcast-on-October-20-2026-2026-QssQGye3im/default.aspx"},
    {"Ticker": "NFLX", "Company Name": "Netflix", "Report Date": "2026-10-20", "Report Time": "After Close", "Source URL": "https://ir.netflix.net/investor-news-and-events/financial-releases/press-release-details/2026/Netflix-to-Announce-Third-Quarter-2026-Financial-Results/default.aspx"},
]
MONTHS = {name: index for index, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
DATE_PATTERN = r"(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})"


def fetch_page(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 EarningsCalendar/1.0"})
    with urllib.request.urlopen(request, timeout=12) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_announcement(ticker: str, source_url: str, page: str) -> dict | None:
    """Use the result-posting sentence, never the page's publication date."""
    text = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", page, flags=re.I | re.S)
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())
    match = re.search(r"(?:will\s+(?:post|release|report|announce)|plans\s+to\s+(?:post|release|report)|(?:financial\s+)?results\s+will\s+be\s+(?:posted|released|reported|announced))\b.{0,450}?" + DATE_PATTERN, text, re.I)
    if not match or not re.search(r"results|earnings", match.group(), re.I):
        return None
    try:
        report_date = date(int(match[3]), MONTHS[match[1].title()], int(match[2]))
    except (ValueError, KeyError):
        return None
    sentence = text[max(0, match.start() - 50):match.end() + 180].lower()
    session = "TBD"
    if re.search(r"after (?:the )?(?:market )?close|1:01 p\.m\. pacific", sentence):
        session = "After Close"
    elif re.search(r"before (?:the )?(?:market )?open", sentence):
        session = "Before Open"
    return {"Ticker": ticker, "Company Name": ISSUERS[ticker]["company"], "Report Date": report_date.isoformat(), "Report Time": session, "Source URL": source_url}


def discover_issuer_events(ticker: str) -> list[dict]:
    index = ISSUERS[ticker]["index"]
    page = fetch_page(index)
    urls = []
    for href in re.findall(r'href=["\']([^"\']+)', page, flags=re.I):
        url = urllib.parse.urljoin(index, html.unescape(href))
        if urllib.parse.urlparse(url).hostname != urllib.parse.urlparse(index).hostname:
            continue
        if re.search(r"(?:to-announce|to-post|to-release).*(?:results|earnings)", url, re.I) and url not in urls:
            urls.append(url)
    if not urls:
        # Some issuer news lists render through JavaScript. Search discovers
        # links only; the actual issuer page must still supply the date.
        from core.research import run_research_query_cascade
        domain = urllib.parse.urlparse(index).hostname
        results = run_research_query_cascade(
            query=f"{ISSUERS[ticker]['company']} to post announce quarterly financial results webcast {date.today().year}",
            include_domains=[domain], max_results_per_provider=3,
        )
        for item in results.get("results", []):
            url = item.get("url", "")
            if urllib.parse.urlparse(url).hostname == domain and url not in urls:
                urls.append(url)
    events = []
    for url in sorted(urls, reverse=True)[:3]:
        event = parse_announcement(ticker, url, fetch_page(url))
        if event:
            events.append(event)
    return events


def reconcile_official_events(rows: list[dict], events: list[dict]) -> list[dict]:
    result = list(rows)
    for event in events:
        confirmed_date = date.fromisoformat(event["Report Date"])
        # A date shift within six weeks represents the same quarterly report.
        # Keep other quarters; remove the superseded event, not just append.
        same_event = lambda row: row["Ticker"] == event["Ticker"] and abs((date.fromisoformat(row["Report Date"]) - confirmed_date).days) <= 42
        matching = next((row for row in result if row["Ticker"] == event["Ticker"] and row["Report Date"] == event["Report Date"]), {})
        result = [row for row in result if not same_event(row)]
        result.append({**matching, **event})
    return sorted(result, key=lambda row: (row["Report Date"], row["Ticker"]))


def supplement_official_calendar(rows: list[dict], today: date | None = None) -> list[dict]:
    today = today or date.today()
    events = list(VERIFIED_EVENTS)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {ticker: executor.submit(discover_issuer_events, ticker) for ticker in ISSUERS}
        for ticker, future in futures.items():
            try:
                events.extend(future.result())
            except Exception as exc:
                print(f"[calendar] {ticker}: issuer refresh unavailable ({type(exc).__name__}); retaining verified events", flush=True)
    unique = {(event["Ticker"], event["Report Date"]): event for event in events
              if today - timedelta(days=60) <= date.fromisoformat(event["Report Date"]) <= today + timedelta(days=120)}
    for event in unique.values():
        print(f"[calendar] Confirmed {event['Ticker']} {event['Report Date']} {event['Report Time']}: {event['Source URL']}", flush=True)
    return reconcile_official_events(rows, list(unique.values()))
