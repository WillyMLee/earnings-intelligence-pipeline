"""Separate issuer financial units from the listed share's quote currency."""
def financial_currency(ticker: str, snap: dict | None = None) -> str:
    return str((snap or {}).get("financial_currency") or {"SPOT": "EUR"}.get(ticker.upper(), "USD")).upper()


def financial_symbol(currency: str) -> str:
    return {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3"}.get(currency, currency + " ")
