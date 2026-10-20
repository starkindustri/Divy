"""Builds Dividend Calendar rows from Massive (all US exchanges) or, without an API key,
Nasdaq's free calendar (Nasdaq-listed only), tagged with exchange and index membership."""
from __future__ import annotations

from datetime import date
from typing import Optional

from . import market, reference

FREQ_LABELS = {1: "Annual", 2: "Semi-annual", 4: "Quarterly", 12: "Monthly", 52: "Weekly"}

# Market filter choices: label -> predicate over a row
MARKETS = {
    "All US markets": lambda r: True,
    "NYSE": lambda r: r["exchange"] == "NYSE",
    "Nasdaq": lambda r: r["exchange"] == "Nasdaq",
    "NYSE American": lambda r: r["exchange"] == "NYSE American",
    "ETFs": lambda r: r["exchange"] == "ETF",
    "Dow 30": lambda r: "Dow 30" in r["indexes"],
    "S&P 500": lambda r: "S&P 500" in r["indexes"],
}


def _float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _tags(ref: Optional[reference.Reference], symbol: str, fallback_exchange: str = "Other"):
    if ref is None:
        return fallback_exchange, [], ""
    return ref.exchange(symbol) or fallback_exchange, ref.indexes(symbol), ref.name(symbol)


def from_massive(raw: list, ref) -> list:
    rows = []
    for r in raw:
        sym = r.get("ticker", "")
        exchange, indexes, name = _tags(ref, sym)
        cash = _float(r.get("cash_amount"))
        freq = r.get("frequency") or 0
        kind = r.get("distribution_type") or ""
        recurring = kind in ("recurring", "") and freq in FREQ_LABELS
        rows.append({
            "symbol": sym, "company": name, "exchange": exchange, "indexes": indexes,
            "index_label": " · ".join(indexes).replace("Dow 30 · ", "Dow · "),
            "ex_date": r.get("ex_dividend_date"), "pay_date": r.get("pay_date"),
            "record_date": r.get("record_date"), "declared": r.get("declaration_date"),
            "dividend": cash, "annual": cash * freq if cash is not None and recurring else None,
            "freq": FREQ_LABELS.get(freq, "") if kind in ("recurring", "") else kind.capitalize(),
            "currency": r.get("currency") or "USD",
        })
    return rows


def from_nasdaq(raw: list, ref) -> list:
    rows = []
    for r in raw:
        sym = r.get("symbol", "")
        exchange, indexes, _ = _tags(ref, sym, fallback_exchange="Nasdaq")
        rows.append({
            "symbol": sym, "company": r.get("companyName", ""), "exchange": exchange,
            "indexes": indexes, "index_label": " · ".join(indexes).replace("Dow 30 · ", "Dow · "),
            "ex_date": market.us_date_to_iso(r.get("dividend_Ex_Date")),
            "pay_date": market.us_date_to_iso(r.get("payment_Date")),
            "record_date": market.us_date_to_iso(r.get("record_Date")),
            "declared": market.us_date_to_iso(r.get("announcement_Date")),
            "dividend": _float(r.get("dividend_Rate")),
            "annual": _float(r.get("indicated_Annual_Dividend")),
            "freq": "", "currency": "USD",
        })
    return rows


def load_day(day: date, api_key: str, ref_path) -> dict:
    """Fetch one day's calendar. Returns {"rows", "source", "warning"}; runs off the UI thread."""
    warning = ""
    try:
        ref = reference.load(ref_path)
    except Exception as exc:  # calendar still works, just without exchange/index tags
        ref, warning = None, f"Exchange and index tags unavailable ({exc})"
    if api_key:
        rows = from_massive(market.fetch_massive_dividends(day, api_key), ref)
        source = "Massive · all US exchanges"
    else:
        rows = from_nasdaq(market.fetch_dividend_calendar(day), ref)
        source = "Nasdaq · Nasdaq-listed only"
    return {"rows": rows, "source": source, "warning": warning}
