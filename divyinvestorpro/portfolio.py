"""Portfolio data model: holdings, their transactions, and the math on them.

The JSON layout of each holding ("tickers" -> buys / sells / dividends / drip_tx)
matches FreedomTracker's portfolio files, so those can be imported directly.
Dates are ISO strings (YYYY-MM-DD), which also sort correctly as strings.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional

from . import APP_NAME

DATA_VERSION = 1
EPS = 1e-6


@dataclass
class Buy:
    date: str
    shares: float
    price: float


@dataclass
class Sell:
    date: str
    shares: float
    price: float


@dataclass
class Dividend:
    date: str
    cash: float
    div_per_share: float
    shares_owned: float


@dataclass
class Drip:
    date: str
    shares_added: float
    reinvest_price: float
    div_amount_per_share: float
    cash_used: float


@dataclass
class Position:
    shares: float
    cost: float          # cost basis of the shares still held
    realized: float      # realized gain/loss from sells

    @property
    def avg_cost(self) -> float:
        return self.cost / self.shares if self.shares > EPS else 0.0


def _build(cls, raw: dict):
    """Create a record from a dict, ignoring keys this version doesn't know."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in raw.items() if k in names})


@dataclass
class Holding:
    ticker: str
    drip_enabled: bool = False
    buys: list = field(default_factory=list)
    sells: list = field(default_factory=list)
    dividends: list = field(default_factory=list)
    drip_tx: list = field(default_factory=list)

    def _share_events(self):
        # On the same day, additions are applied before sells.
        events = [(b.date, 0, "buy", b) for b in self.buys]
        events += [(d.date, 0, "drip", d) for d in self.drip_tx]
        events += [(s.date, 1, "sell", s) for s in self.sells]
        return sorted(events, key=lambda e: (e[0], e[1]))

    def position(self, as_of: Optional[str] = None) -> Position:
        """Replay transactions (up to and including `as_of`) using average cost."""
        shares = cost = realized = 0.0
        for day, _, kind, tx in self._share_events():
            if as_of and day > as_of:
                break
            if kind == "buy":
                shares += tx.shares
                cost += tx.shares * tx.price
            elif kind == "drip":
                shares += tx.shares_added
                cost += tx.cash_used
            else:
                if tx.shares > shares + EPS:
                    raise ValueError(
                        f"{self.ticker}: selling {tx.shares:g} shares on {day} "
                        f"but only {shares:g} are held")
                avg = cost / shares if shares > EPS else 0.0
                realized += (tx.price - avg) * tx.shares
                cost -= avg * tx.shares
                shares -= tx.shares
        if shares < EPS:
            shares = cost = 0.0
        return Position(shares, cost, realized)

    @property
    def total_dividends(self) -> float:
        return sum(d.cash for d in self.dividends)

    def first_buy_date(self) -> Optional[str]:
        return min((b.date for b in self.buys), default=None)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Holding":
        return cls(
            ticker=str(raw["ticker"]).upper().strip(),
            drip_enabled=bool(raw.get("drip_enabled", False)),
            buys=[_build(Buy, r) for r in raw.get("buys", [])],
            sells=[_build(Sell, r) for r in raw.get("sells", [])],
            dividends=[_build(Dividend, r) for r in raw.get("dividends", [])],
            drip_tx=[_build(Drip, r) for r in raw.get("drip_tx", [])],
        )


@dataclass
class Portfolio:
    holdings: list = field(default_factory=list)

    # lookup
    def get(self, ticker: str) -> Optional[Holding]:
        ticker = ticker.upper().strip()
        return next((h for h in self.holdings if h.ticker == ticker), None)

    def tickers(self) -> list:
        return [h.ticker for h in self.holdings]

    # changes
    def add_buy(self, ticker: str, day: str, shares: float, price: float) -> Holding:
        if shares <= 0 or price < 0:
            raise ValueError("Shares must be positive and price can't be negative.")
        ticker = ticker.upper().strip()
        if not ticker:
            raise ValueError("Enter a ticker symbol.")
        holding = self.get(ticker)
        if holding is None:
            holding = Holding(ticker)
            self.holdings.append(holding)
        holding.buys.append(Buy(day, shares, price))
        return holding

    def add_sell(self, ticker: str, day: str, shares: float, price: float) -> None:
        holding = self._require(ticker)
        if shares <= 0 or price < 0:
            raise ValueError("Shares must be positive and price can't be negative.")
        sell = Sell(day, shares, price)
        holding.sells.append(sell)
        try:
            holding.position()
        except ValueError:
            holding.sells.remove(sell)
            raise

    def record_dividend(self, ticker: str, day: str, div_per_share: float,
                        shares_owned: float, reinvest_price: Optional[float] = None):
        """Log a dividend; if `reinvest_price` is given, also log the DRIP purchase."""
        holding = self._require(ticker)
        if div_per_share <= 0 or shares_owned <= 0:
            raise ValueError("Dividend per share and shares owned must be positive.")
        cash = round(div_per_share * shares_owned, 2)
        dividend = Dividend(day, cash, div_per_share, shares_owned)
        holding.dividends.append(dividend)
        drip = None
        if reinvest_price:
            drip = Drip(day, cash / reinvest_price, reinvest_price, div_per_share, cash)
            holding.drip_tx.append(drip)
        return dividend, drip

    def remove_transaction(self, ticker: str, tx) -> None:
        """Remove one transaction; refuses if that would leave sells uncovered."""
        holding = self._require(ticker)
        for name in ("buys", "sells", "dividends", "drip_tx"):
            items = getattr(holding, name)
            for i, item in enumerate(items):
                if item is tx:
                    del items[i]
                    try:
                        holding.position()
                    except ValueError:
                        items.insert(i, tx)
                        raise
                    return
        raise KeyError("Transaction not found")

    def remove_holding(self, ticker: str) -> None:
        self.holdings = [h for h in self.holdings if h.ticker != ticker.upper()]

    def _require(self, ticker: str) -> Holding:
        holding = self.get(ticker)
        if holding is None:
            raise ValueError(f"You don't hold {ticker.upper()}.")
        return holding

    # reports
    def dividends_by_month(self) -> dict:
        out = defaultdict(float)
        for h in self.holdings:
            for d in h.dividends:
                out[d.date[:7]] += d.cash
        return dict(out)

    def dividend_log(self) -> list:
        """All dividends, newest first, with any matching DRIP reinvestment."""
        rows = []
        for h in self.holdings:
            drips = {(d.date, round(d.cash_used, 2)): d for d in h.drip_tx}
            for d in h.dividends:
                drip = drips.get((d.date, round(d.cash, 2)))
                rows.append({
                    "date": d.date, "ticker": h.ticker, "dps": d.div_per_share,
                    "shares": d.shares_owned, "cash": d.cash,
                    "reinvested": drip.shares_added if drip else None,
                })
        return sorted(rows, key=lambda r: r["date"], reverse=True)

    # serialization
    def to_dict(self) -> dict:
        return {"app": APP_NAME, "version": DATA_VERSION,
                "tickers": [h.to_dict() for h in self.holdings]}

    @classmethod
    def from_dict(cls, raw: dict) -> "Portfolio":
        holdings = [Holding.from_dict(t) for t in raw.get("tickers", [])]
        for h in holdings:
            h.position()  # fail early on inconsistent data
        return cls(holdings)

    @classmethod
    def load(cls, path: Path) -> "Portfolio":
        if not path.exists():
            return cls()
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            os.replace(tmp, path)
        except BaseException:
            os.unlink(tmp)
            raise


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


def default_path() -> Path:
    return data_dir() / "portfolio.json"
