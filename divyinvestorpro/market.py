"""Market data: prices and dividend history (Yahoo Finance) and the
US dividend calendar (Nasdaq). Both are free, unofficial endpoints with no
API key, so callers should expect occasional failures.
"""
from __future__ import annotations

import bisect
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from curl_cffi import requests

CHART_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{}"
             "?range=2y&interval=1d&events=div")
CALENDAR_URL = "https://api.nasdaq.com/api/calendar/dividends?date={}"
NASDAQ_HEADERS = {"Accept": "application/json, text/plain, */*",
                  "Origin": "https://www.nasdaq.com",
                  "Referer": "https://www.nasdaq.com/"}
TIMEOUT = 20
PAYOUTS_PER_YEAR = (1, 2, 4, 12, 52)


def _get_json(url: str, headers: Optional[dict] = None) -> dict:
    resp = requests.get(url, headers=headers, impersonate="chrome", timeout=TIMEOUT)
    if resp.status_code == 404:
        raise LookupError("symbol not found")
    resp.raise_for_status()
    return resp.json()


@dataclass
class Quote:
    symbol: str
    name: str
    price: Optional[float]
    prev_close: Optional[float]
    close_dates: list = field(default_factory=list)   # ISO dates, ascending
    closes: list = field(default_factory=list)
    dividends: list = field(default_factory=list)     # (ex-date ISO, amount), ascending

    @property
    def change_pct(self) -> Optional[float]:
        if self.price is None or not self.prev_close:
            return None
        return (self.price / self.prev_close - 1) * 100

    @property
    def last_dividend(self) -> Optional[float]:
        return self.dividends[-1][1] if self.dividends else None

    def _recent(self, days: int = 365) -> list:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        return [d for d in self.dividends if d[0] > cutoff]

    @property
    def frequency(self) -> int:
        """Payouts per year, snapped to the nearest common schedule (0 = none lately)."""
        n = len(self._recent())
        if n == 0:
            return 0
        return min(PAYOUTS_PER_YEAR, key=lambda f: abs(f - n))

    @property
    def annual_dividend(self) -> float:
        """Forward estimate: latest payout times payouts per year."""
        freq = self.frequency
        return self.last_dividend * freq if freq else 0.0

    @property
    def ttm_dividend(self) -> float:
        return sum(a for _, a in self._recent())

    @property
    def dividend_yield(self) -> Optional[float]:
        if not self.price:
            return None
        return self.annual_dividend / self.price * 100

    def close_on(self, day: str) -> Optional[float]:
        """Closing price on `day`, or the last close before it."""
        i = bisect.bisect_right(self.close_dates, day)
        return self.closes[i - 1] if i else None


def fetch_quote(symbol: str) -> Quote:
    data = _get_json(CHART_URL.format(symbol))["chart"]
    if data.get("error"):
        raise LookupError(data["error"].get("description", "no data"))
    result = data["result"][0]
    meta = result["meta"]
    offset = meta.get("gmtoffset", 0)

    def to_day(ts):
        return datetime.fromtimestamp(ts + offset, tz=timezone.utc).date().isoformat()

    stamps = result.get("timestamp") or []
    raw_closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    pairs = [(to_day(t), c) for t, c in zip(stamps, raw_closes) if c is not None]
    divs = sorted((to_day(d["date"]), float(d["amount"]))
                  for d in (result.get("events", {}).get("dividends") or {}).values())

    price = meta.get("regularMarketPrice")
    prev = meta.get("previousClose")
    if prev is None and pairs:
        # previous close = last daily close before the latest trading day
        last_day = to_day(meta["regularMarketTime"]) if meta.get("regularMarketTime") else pairs[-1][0]
        earlier = [c for d, c in pairs if d < last_day]
        prev = earlier[-1] if earlier else None
    return Quote(
        symbol=symbol,
        name=meta.get("longName") or meta.get("shortName") or symbol,
        price=price,
        prev_close=prev,
        close_dates=[p[0] for p in pairs],
        closes=[p[1] for p in pairs],
        dividends=divs,
    )


def fetch_quotes(symbols) -> tuple:
    """Fetch several quotes in parallel. Returns ({symbol: Quote}, {symbol: error})."""
    quotes, errors = {}, {}
    symbols = list(dict.fromkeys(symbols))
    if not symbols:
        return quotes, errors
    with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as pool:
        futures = {s: pool.submit(fetch_quote, s) for s in symbols}
        for sym, fut in futures.items():
            try:
                quotes[sym] = fut.result()
            except Exception as exc:  # report per symbol, keep the rest
                errors[sym] = str(exc)
    return quotes, errors


def fetch_dividend_calendar(day: date) -> list:
    """Companies with an ex-dividend date of `day`, as Nasdaq reports them."""
    payload = _get_json(CALENDAR_URL.format(day.isoformat()), NASDAQ_HEADERS)
    return ((payload.get("data") or {}).get("calendar") or {}).get("rows") or []


MASSIVE_DIVIDENDS = "https://api.massive.com/stocks/v1/dividends"
MASSIVE_MAX_PAGES = 4  # the free plan allows 5 requests a minute


class ApiKeyError(Exception):
    pass


def fetch_massive_dividends(day: date, api_key: str, limit: int = 5000,
                            max_pages: int = MASSIVE_MAX_PAGES) -> list:
    """All US dividends with an ex-dividend date of `day`, from Massive (formerly Polygon.io)."""
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    url = MASSIVE_DIVIDENDS
    params = {"ex_dividend_date": day.isoformat(), "limit": limit, "sort": "ticker.asc"}
    results = []
    for _ in range(max_pages):
        resp = requests.get(url, params=params, headers=headers, impersonate="chrome", timeout=TIMEOUT)
        try:
            body = resp.json()
        except ValueError:
            body = {}
        error = str(body.get("error") or body.get("message") or "")
        # Massive answers a bad key with 401, 403, or (on this endpoint) 404 "Unknown API Key"
        if resp.status_code in (401, 403) or "api key" in error.lower():
            raise ApiKeyError("Massive didn't accept the API key. Check it in Settings.")
        if resp.status_code == 429:
            raise RuntimeError("Massive's free plan allows 5 requests a minute. "
                               "Wait a minute and press Refresh.")
        resp.raise_for_status()
        if body.get("status") == "ERROR":
            raise RuntimeError(error or "Massive returned an error")
        results += body.get("results") or []
        url, params = body.get("next_url"), None
        if not url or len(results) >= limit:
            break
    return results


def us_date_to_iso(value) -> Optional[str]:
    """Nasdaq's M/D/YYYY -> YYYY-MM-DD (None if blank or malformed)."""
    try:
        m, d, y = str(value).split("/")
        return date(int(y), int(m), int(d)).isoformat()
    except (ValueError, TypeError):
        return None
