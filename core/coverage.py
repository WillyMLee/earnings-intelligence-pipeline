#!/usr/bin/env python3
"""
Ticker -> sector/portfolio-company mapping for the coverage universe.

This is real, queryable data (a dict), not the informal comment groupings
that used to be the only structure around `DEFAULT_COVERAGE_UNIVERSE` in
run_earnings_radar_automation.py. It exists so post-earnings summaries can be
tagged with a sector at write time, which is the prerequisite for any future
industry-trend aggregation (comparing beat rates, growth, etc. across a
sector) -- you can't aggregate by sector if nothing records what sector a
ticker belongs to.

Sector granularity here intentionally matches the original comment groupings
(one label per group) rather than a fully precise per-ticker classification --
good enough to be useful now, and refining it later doesn't require any
schema change since sector is just a string.
"""

from __future__ import annotations

from typing import Dict

_SECTOR_GROUPS: Dict[str, str] = {
    "AI Infrastructure & Semis": (
        "NVDA,AMD,AVGO,MRVL,INTC,QCOM,SMCI,DELL,HPE,ANET,CSCO,ORCL,IBM,MSFT,AMZN,GOOGL,META,"
        "TSM,ASML,ARM,AMAT,LRCX,KLAC,MU,WDC,STX,SNDK,VRT,ETN,CRWV,NBIS,IREN,CORZ,"
        "ALAB,CRDO,CLS,LITE,PSTG"
    ),
    "Vertical SaaS & Cybersecurity": "VEEV,AXON,APP,SHOP,ADBE,CRM,NOW,SNOW,PANW,CRWD,DDOG,NET,TEAM,INTU,FTNT,S,RBRK,IOT,PCOR",
    "SaaS Expansion": "ZS,OKTA,HUBS,GTLB,WDAY,TOST,BILL,MNDY,TTD",
    "Customer Engagement & Ad Tech": "BRZE,KVYO,ZETA",
    "Data Platforms": "MDB,CFLT,PLTR,ESTC",
    "Banks & Financials": "JPM,BAC,WFC,C,GS,MS,USB,AXP",
    "Payments & Fintech": "V,MA,PYPL,FIS,ADYEN",
    "Industrials": "CAT,DE,HON,EMR",
    "Defense & Aerospace": "RTX,LMT,BA,GE",
    "AI Power & Grid": "GEV,VST,CEG,NRG,OKLO",
    "Airlines": "DAL,UAL,AAL",
    "Consumer": "AAPL,TSLA,NFLX,WMT,COST,HD,MCD,SBUX,NKE,PG,KO,FDX,UPS",
}

# Neostellar portfolio companies and notable recent IPOs don't share a single
# group sector the way the rest of the universe does -- assign individually.
_INDIVIDUAL_SECTORS: Dict[str, str] = {
    "LIME": "Mobility & Transportation",
    "SKIL": "Vertical SaaS & Cybersecurity",
    "PSQH": "Consumer",
    "PEW": "Consumer",
    "SPCX": "Aerospace & Defense",
    "CBRS": "AI Infrastructure & Semis",
    "QNT": "Quantum Computing",
    "XNDU": "Quantum Computing",
}

# Portfolio holdings specifically (a subset of the tickers above) -- kept
# separate from sector because this is the join key a future merge with a
# separate private-company/portfolio-tracking system would use, not a sector
# classification.
PORTCO_TICKERS = frozenset({"LIME", "SKIL", "PSQH", "PEW", "CRWV"})

TICKER_SECTOR: Dict[str, str] = dict(_INDIVIDUAL_SECTORS)
for _sector, _tickers in _SECTOR_GROUPS.items():
    for _ticker in _tickers.split(","):
        _ticker = _ticker.strip().upper()
        if _ticker:
            TICKER_SECTOR.setdefault(_ticker, _sector)

_UNCLASSIFIED = "Unclassified"


def sector_for(ticker: str) -> str:
    return TICKER_SECTOR.get(ticker.strip().upper(), _UNCLASSIFIED)


def is_portco(ticker: str) -> bool:
    return ticker.strip().upper() in PORTCO_TICKERS


DASHBOARD_THEME_TICKERS = frozenset({
    "MSFT", "AMZN", "GOOGL", "META", "ORCL", "AAPL", "NVDA", "TSLA",
    "AMD", "AVGO", "ANET", "ARM", "MU", "LRCX", "KLAC", "WDC", "STX", "SNDK", "DELL",
    "ALAB", "CRDO", "CLS", "LITE", "PSTG",
    "CRM", "NOW", "SNOW", "ADBE", "TEAM", "HUBS", "WDAY", "GTLB", "MNDY", "BILL", "SHOP", "TOST",
    "PANW", "CRWD", "ZS", "FTNT", "OKTA", "NET", "S", "RBRK", "IOT", "PCOR",
    "PLTR", "DDOG", "MDB", "CFLT", "ESTC",
    "APP", "TTD", "ZETA", "BRZE", "KVYO", "MGNI", "PUBM", "RDDT",
    "LIME", "PEW", "CRWV", "PSQH", "SKIL",
    "VST", "CEG", "ETN", "NRG", "OKLO", "GEV",
    "JPM", "BAC", "WFC", "C", "GS", "MS", "AXP", "V", "MA", "PYPL", "COF", "SCHW", "BLK",
    "WMT", "COST", "HD", "LOW", "MCD", "SBUX", "NKE", "DIS", "NFLX", "UBER", "DASH", "ABNB", "BKNG",
    "BA", "CAT", "HON", "GE", "RTX", "LMT", "NOC", "UPS", "FDX", "UNP", "DE",
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ISRG", "AMGN", "GILD", "PFE",
})

# Companies moved out of dedicated pre/post email delivery while retaining
# full pre/post research and Convex archival for the website.
EMAIL_DEMOTED_TICKERS = frozenset({
    "AAL", "AXP", "BA", "BAC", "BILL", "C", "CAT", "DE", "EMR", "ESTC",
    "FDX", "FIS", "GE", "GS", "HON", "HUBS", "IBM", "JPM", "KO", "LMT",
    "MA", "MCD", "MS", "NKE", "OKTA", "PG", "PYPL", "RTX", "S", "SBUX",
    "SHOP", "TOST", "UAL", "USB", "V", "VEEV", "WFC",
})


def dashboard_only_tickers() -> frozenset[str]:
    """Focused site-analysis universe that never receives dedicated email."""
    from core.earnings_universe import EMAIL_DEEP_DIVE_TICKERS

    return frozenset(
        (DASHBOARD_THEME_TICKERS | EMAIL_DEMOTED_TICKERS) - EMAIL_DEEP_DIVE_TICKERS
    )
