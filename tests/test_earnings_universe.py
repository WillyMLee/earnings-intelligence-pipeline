from core.earnings_universe import (
    EMAIL_DEEP_DIVE_TICKERS,
    NEOSTELLAR_ADDITIONS,
    SP500_TICKERS,
    TRACKED_TICKERS,
    filter_tracked_rows,
    normalize_ticker,
)
from core.coverage import EMAIL_DEMOTED_TICKERS, dashboard_only_tickers, sector_for


def test_canonical_universe_is_bounded_and_complete():
    assert len(SP500_TICKERS) == 503
    assert len(NEOSTELLAR_ADDITIONS) == 48
    assert len(TRACKED_TICKERS) == 551
    assert len(EMAIL_DEEP_DIVE_TICKERS) == 88
    assert not SP500_TICKERS.intersection(NEOSTELLAR_ADDITIONS)
    assert EMAIL_DEEP_DIVE_TICKERS <= TRACKED_TICKERS


def test_priority_coverage_is_retained_and_russell_noise_is_excluded():
    required = {
        "AAPL", "CRM", "CRWD", "DDOG", "MU", "SNDK", "STX", "WDC",
        "ARM", "ASML", "CRWV", "SNOW", "TSM",
        "CHYM", "FIG", "LIME", "PEW", "PSQH", "SKIL",
        "ALAB", "BRZE", "CLS", "CRDO", "IOT", "KVYO", "LITE",
        "PCOR", "PSTG", "RBRK", "ZETA",
    }
    excluded = {"FLWS", "YI", "FEAM", "AAFR", "LONA", "ALLR"}
    assert required <= TRACKED_TICKERS
    assert not excluded.intersection(TRACKED_TICKERS)


def test_email_deep_dive_matches_the_approved_narrower_list():
    retained = {"COST", "HD", "WMT", "TSLA", "UPS", "NFLX", "DAL"}
    additions = {"ALAB", "BRZE", "CLS", "CRDO", "IOT", "KVYO", "LITE", "PCOR", "PSTG", "RBRK", "ZETA"}
    demoted = {"AAL", "AXP", "BA", "BAC", "BILL", "C", "CAT", "DE", "EMR", "ESTC", "FDX", "FIS", "GE", "GS", "HON", "HUBS", "IBM", "JPM", "KO", "LMT", "MA", "MCD", "MS", "NKE", "OKTA", "PG", "PYPL", "RTX", "S", "SBUX", "SHOP", "TOST", "UAL", "USB", "V", "VEEV", "WFC"}
    assert retained | additions <= EMAIL_DEEP_DIVE_TICKERS
    assert not demoted.intersection(EMAIL_DEEP_DIVE_TICKERS)
    assert demoted <= TRACKED_TICKERS


def test_demoted_and_thematic_names_keep_site_analysis_without_email():
    site_only = dashboard_only_tickers()
    additions = {"ALAB", "BRZE", "CLS", "CRDO", "IOT", "KVYO", "LITE", "PCOR", "PSTG", "RBRK", "ZETA"}
    assert EMAIL_DEMOTED_TICKERS <= site_only
    assert not site_only.intersection(EMAIL_DEEP_DIVE_TICKERS)
    assert not {ticker for ticker in additions if sector_for(ticker) == "Unclassified"}


def test_provider_rows_are_normalized_and_filtered():
    rows = [
        {"Ticker": "BRK.B", "Company Name": "Berkshire Hathaway"},
        {"Ticker": "FLWS", "Company Name": "1-800-Flowers"},
        {"Ticker": " snow ", "Company Name": "Snowflake"},
    ]
    assert [row["Ticker"] for row in filter_tracked_rows(rows)] == ["BRK-B", "SNOW"]
    assert normalize_ticker("bf.b") == "BF-B"
