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
        "TSM,ASML,ARM,AMAT,LRCX,KLAC,MU,WDC,STX,SNDK,VRT,ETN,CRWV,NBIS,IREN,CORZ"
    ),
    "Vertical SaaS & Cybersecurity": "VEEV,AXON,APP,SHOP,ADBE,CRM,NOW,SNOW,PANW,CRWD,DDOG,NET,TEAM,INTU,FTNT,S",
    "SaaS Expansion": "ZS,OKTA,HUBS,GTLB,WDAY,TOST,BILL,MNDY,TTD",
    "Data Platforms": "MDB,CFLT,PLTR,ESTC",
    "Banks & Financials": "JPM,BAC,WFC,C,GS,MS,USB,AXP",
    "Payments & Fintech": "V,MA,PYPL,FIS,ADYEN",
    "Industrials": "CAT,DE,HON,EMR",
    "Defense & Aerospace": "RTX,LMT,BA,GE",
    "AI Power & Grid": "GEV,VST,CEG,NRG,OKLO",
    "Airlines": "DAL,UAL,AAL",
    "Consumer": "AAPL,TSLA,NFLX,WMT,COST,HD,MCD,SBUX,NKE,PG,KO,FDX,UPS",
}

# Portfolio companies and notable recent IPOs don't share a single group
# sector the way the rest of the universe does -- assign individually.
# NOTE: the tickers below are illustrative placeholders. In a real deployment,
# replace _INDIVIDUAL_SECTORS and PORTCO_TICKERS with your own fund's actual
# holdings and sector calls -- this file is meant to be edited per-fund, not
# used as-is.
_INDIVIDUAL_SECTORS: Dict[str, str] = {
    "EXPCO1": "Mobility & Transportation",
    "EXPCO2": "Vertical SaaS & Cybersecurity",
    "EXPCO3": "Consumer",
    "EXPCO4": "Consumer",
    "SPCX": "Aerospace & Defense",
    "CBRS": "AI Infrastructure & Semis",
    "QNT": "Quantum Computing",
    "XNDU": "Quantum Computing",
}

# Portfolio holdings specifically (a subset of the tickers above) -- kept
# separate from sector because this is the join key a future merge with a
# separate private-company/portfolio-tracking system would use, not a sector
# classification.
PORTCO_TICKERS = frozenset({"EXPCO1", "EXPCO2", "EXPCO3", "EXPCO4", "CRWV"})

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
    "CRM", "NOW", "SNOW", "ADBE", "TEAM", "HUBS", "WDAY", "GTLB", "MNDY", "BILL", "SHOP", "TOST",
    "PANW", "CRWD", "ZS", "FTNT", "OKTA", "NET", "S",
    "PLTR", "DDOG", "MDB", "CFLT", "ESTC", "APP", "TTD",
    "VST", "CEG", "ETN", "NRG", "OKLO", "GEV",
    "JPM", "BAC", "WFC", "C", "GS", "MS", "AXP", "V", "MA", "PYPL", "COF", "SCHW", "BLK",
    "WMT", "COST", "HD", "LOW", "MCD", "SBUX", "NKE", "DIS", "NFLX", "UBER", "DASH", "ABNB", "BKNG",
    "BA", "CAT", "HON", "GE", "RTX", "LMT", "NOC", "UPS", "FDX", "UNP", "DE",
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ISRG", "AMGN", "GILD", "PFE",
})
