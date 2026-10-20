"""Which exchange each US ticker trades on, and Dow 30 / S&P 500 membership.

Listings come from Nasdaq's public stock screener (Nasdaq, NYSE, NYSE American and
ETFs); S&P 500 members from Wikipedia. Both are cached on disk for a week.
The Dow 30 changes rarely and has no free machine-readable source, so it's kept here.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from curl_cffi import requests

# Dow Jones Industrial Average members as of June 29, 2026 (Alphabet replaced Verizon).
DOW_AS_OF = "2026-06-29"
DOW_30 = frozenset("""
    AAPL AMGN AMZN AXP BA CAT CRM CSCO CVX DIS GOOGL GS HD HON IBM
    JNJ JPM KO MCD MMM MRK MSFT NKE NVDA PG SHW TRV UNH V WMT
""".split())

CACHE_DAYS = 7
SCREENER = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&exchange={}&download=true"
ETF_SCREENER = "https://api.nasdaq.com/api/screener/etf?download=true"
SP500_PAGE = ("https://en.wikipedia.org/w/api.php?action=parse&page=List_of_S%26P_500_companies"
              "&prop=text&format=json&formatversion=2")
NASDAQ_HEADERS = {"Accept": "application/json, text/plain, */*",
                  "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
EXCHANGES = {"nasdaq": "Nasdaq", "nyse": "NYSE", "amex": "NYSE American"}


def normalize(symbol: str) -> str:
    """One spelling for share classes and preferreds across sources:
    Nasdaq 'BRK/B' and Wikipedia 'BRK-B' -> 'BRK.B'; Nasdaq 'ABR^D' -> 'ABRpD' (Massive's form)."""
    s = str(symbol).strip()
    m = re.fullmatch(r"([A-Za-z]+)p([A-Za-z]*)", s)
    if m and s != s.upper():  # already Massive's preferred form, e.g. 'ABRpD'
        return f"{m.group(1).upper()}p{m.group(2).upper()}"
    return s.upper().replace("/", ".").replace("-", ".").replace("^", "p")


@dataclass
class Reference:
    names: dict = field(default_factory=dict)       # symbol -> company name
    exchanges: dict = field(default_factory=dict)   # symbol -> "NYSE" | "Nasdaq" | ...
    sp500: frozenset = frozenset()
    dow: frozenset = DOW_30
    fetched_at: float = 0.0

    def exchange(self, symbol):
        return self.exchanges.get(normalize(symbol))

    def name(self, symbol):
        return self.names.get(normalize(symbol), "")

    def indexes(self, symbol):
        s = normalize(symbol)
        return [label for label, members in (("Dow 30", self.dow), ("S&P 500", self.sp500))
                if s in members]

    def to_dict(self):
        return {"names": self.names, "exchanges": self.exchanges, "sp500": sorted(self.sp500),
                "fetched_at": self.fetched_at}

    @classmethod
    def from_dict(cls, d):
        return cls(names=d.get("names", {}), exchanges=d.get("exchanges", {}),
                   sp500=frozenset(d.get("sp500", [])), fetched_at=d.get("fetched_at", 0.0))


def _get(url, headers=None):
    resp = requests.get(url, headers=headers, impersonate="chrome", timeout=40)
    resp.raise_for_status()
    return resp.json()


def fetch_sp500() -> frozenset:
    html = _get(SP500_PAGE)["parse"]["text"]
    start = html.find('id="constituents"')
    table = html[start:html.find("</table>", start)] if start >= 0 else ""
    # first cell of each row is the ticker, usually linked
    symbols = re.findall(r"<tr>\s*<td[^>]*>\s*(?:<a[^>]*>)?([A-Z][A-Z.\-]{0,6})(?:</a>)?\s*</td>", table)
    if len(symbols) < 450:
        raise ValueError(f"S&P 500 list looks wrong ({len(symbols)} symbols)")
    return frozenset(normalize(s) for s in symbols)


def fetch_reference() -> Reference:
    ref = Reference(fetched_at=time.time())
    etf = _get(ETF_SCREENER, NASDAQ_HEADERS)["data"]
    for row in (etf.get("data") or {}).get("rows") or []:
        s = normalize(row["symbol"])
        ref.names[s] = row.get("companyName", "")
        ref.exchanges[s] = "ETF"
    for code, label in EXCHANGES.items():
        rows = _get(SCREENER.format(code), NASDAQ_HEADERS)["data"]["rows"]
        for row in rows:
            s = normalize(row["symbol"])
            ref.names[s] = row.get("name", "")
            ref.exchanges[s] = label
    ref.sp500 = fetch_sp500()
    return ref


def load(cache_path: Path, max_age_days: float = CACHE_DAYS) -> Reference:
    """Cached reference data; refetches when stale, and falls back to a stale cache offline."""
    cached = None
    if cache_path.exists():
        try:
            cached = Reference.from_dict(json.loads(cache_path.read_text()))
        except (ValueError, OSError):
            cached = None
    if cached and time.time() - cached.fetched_at < max_age_days * 86400:
        return cached
    try:
        fresh = fetch_reference()
    except Exception:
        if cached:
            return cached
        raise
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(fresh.to_dict()))
    return fresh
