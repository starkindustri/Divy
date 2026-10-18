"""App-wide state: the portfolio on disk plus the latest market quotes."""
import time

from PySide6.QtCore import QObject, Signal

from . import market
from .portfolio import Portfolio
from .workers import run_async


class AppState(QObject):
    portfolio_changed = Signal()
    quotes_changed = Signal()
    message = Signal(str)

    def __init__(self, path, portfolio: Portfolio):
        super().__init__()
        self.path = path
        self.portfolio = portfolio
        self.quotes = {}
        self.quote_errors = {}
        self.loading = False

    def commit(self):
        """Save after any change and tell the pages to redraw."""
        self.portfolio.save(self.path)
        self.portfolio_changed.emit()

    def replace_portfolio(self, portfolio: Portfolio):
        self.portfolio = portfolio
        self.commit()
        self.refresh_quotes()

    def refresh_quotes(self, symbols=None):
        symbols = list(symbols or self.portfolio.tickers())
        if not symbols:
            return
        self.loading = True
        self.message.emit("Updating prices…")
        run_async(lambda: market.fetch_quotes(symbols), self._got_quotes, self._failed)

    def _got_quotes(self, result):
        quotes, errors = result
        self.loading = False
        self.quotes.update(quotes)
        for sym in quotes:
            self.quote_errors.pop(sym, None)
        self.quote_errors.update(errors)
        stamp = time.strftime("%-I:%M %p")
        msg = f"Prices updated {stamp}"
        if errors:
            msg += " — couldn't load " + ", ".join(sorted(errors))
        self.message.emit(msg)
        self.quotes_changed.emit()

    def _failed(self, exc):
        self.loading = False
        self.message.emit(f"Couldn't update prices: {exc}")
