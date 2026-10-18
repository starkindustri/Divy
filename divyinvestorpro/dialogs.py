"""Dialogs for buying, selling, logging dividends and viewing one holding."""
from PySide6.QtCore import QDate, QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (QCheckBox, QDateEdit, QDialog, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout)

from . import market
from .portfolio import Dividend
from .widgets import Column, RecordsModel, StatCard, make_table, money, num, selected_row
from .workers import run_async


def _spin(decimals, maximum=1e9, prefix=""):
    s = QDoubleSpinBox()
    s.setDecimals(decimals)
    s.setRange(0, maximum)
    s.setPrefix(prefix)
    s.setGroupSeparatorShown(True)
    s.setMinimumWidth(180)
    return s


def _date_edit(day=None):
    d = QDateEdit(QDate.fromString(day, "yyyy-MM-dd") if day else QDate.currentDate())
    d.setCalendarPopup(True)
    d.setDisplayFormat("yyyy-MM-dd")
    d.setMaximumDate(QDate.currentDate().addDays(366))
    return d


def _iso(date_edit):
    return date_edit.date().toString("yyyy-MM-dd")


def _buttons(dialog, ok_text):
    row = QHBoxLayout()
    row.addStretch()
    cancel = QPushButton("Cancel")
    cancel.clicked.connect(dialog.reject)
    ok = QPushButton(ok_text)
    ok.setObjectName("Primary")
    ok.setDefault(True)
    ok.clicked.connect(dialog.accept)
    row.addWidget(cancel)
    row.addWidget(ok)
    return row


class TradeDialog(QDialog):
    """Buy (new or existing ticker) or sell shares."""

    def __init__(self, state, kind, ticker=None, parent=None):
        super().__init__(parent)
        self.state, self.kind = state, kind
        self.setWindowTitle("Buy shares" if kind == "buy" else "Sell shares")
        self.setMinimumWidth(420)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(14)
        title = QLabel(self.windowTitle())
        title.setObjectName("Section")
        lay.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        self.ticker = QLineEdit(ticker or "")
        self.ticker.setPlaceholderText("e.g. SCHD")
        self.ticker.setValidator(QRegularExpressionValidator(QRegularExpression(r"[A-Za-z0-9.\-^]{1,12}")))
        self.ticker.textEdited.connect(lambda t: self.ticker.setText(t.upper()))
        self.ticker.editingFinished.connect(self._lookup)
        if ticker and kind == "sell":
            self.ticker.setReadOnly(True)
        self.date = _date_edit()
        self.shares = _spin(6)
        self.price = _spin(4, prefix="$")
        self.total = QLabel("$0.00")
        self.hint = QLabel("")
        self.hint.setObjectName("Muted")
        form.addRow("Ticker", self.ticker)
        form.addRow("Date", self.date)
        form.addRow("Shares", self.shares)
        form.addRow("Price per share", self.price)
        form.addRow("Total", self.total)
        lay.addLayout(form)
        lay.addWidget(self.hint)
        lay.addLayout(_buttons(self, "Add buy" if kind == "buy" else "Record sale"))

        for w in (self.shares, self.price):
            w.valueChanged.connect(self._update_total)
        self.date.dateChanged.connect(self._update_hint)
        if ticker:
            self._lookup()
            self.shares.setFocus()

    def _update_total(self):
        self.total.setText(money(self.shares.value() * self.price.value()))

    def _update_hint(self):
        holding = self.state.portfolio.get(self.ticker.text())
        if self.kind == "sell" and holding:
            held = holding.position(_iso(self.date)).shares
            self.hint.setText(f"You held {num(held, 6)} shares on this date.")
            self.shares.setMaximum(held)

    def _set_price(self, quote):
        try:
            if quote.price and self.price.value() == 0:
                self.price.setValue(quote.price)
            self.hint.setText(self.hint.text() or quote.name)
        except RuntimeError:
            pass  # dialog closed before the quote arrived

    def _lookup(self):
        sym = self.ticker.text().strip().upper()
        self._update_hint()
        if not sym:
            return
        if sym in self.state.quotes:
            self._set_price(self.state.quotes[sym])
        else:
            run_async(lambda: market.fetch_quote(sym), self._set_price, lambda e: None)

    def accept(self):
        sym = self.ticker.text().strip().upper()
        try:
            if self.kind == "buy":
                self.state.portfolio.add_buy(sym, _iso(self.date), self.shares.value(), self.price.value())
            else:
                self.state.portfolio.add_sell(sym, _iso(self.date), self.shares.value(), self.price.value())
        except ValueError as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return
        self.state.commit()
        if sym not in self.state.quotes:
            self.state.refresh_quotes([sym])
        super().accept()


class DividendDialog(QDialog):
    """Log a dividend payment, optionally reinvesting it (DRIP)."""

    def __init__(self, state, ticker, parent=None):
        super().__init__(parent)
        self.state, self.ticker = state, ticker
        self.holding = state.portfolio.get(ticker)
        self.quote = state.quotes.get(ticker)
        self.setWindowTitle(f"Record dividend — {ticker}")
        self.setMinimumWidth(440)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(14)
        title = QLabel(f"Record a {ticker} dividend")
        title.setObjectName("Section")
        lay.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        self.date = _date_edit()
        self.dps = _spin(6, prefix="$")
        self.shares = _spin(6)
        self.cash = QLabel()
        self.reinvest = QCheckBox("Reinvest (DRIP)")
        self.reinvest.setChecked(self.holding.drip_enabled)
        self.reinvest_price = _spin(4, prefix="$")
        self.added = QLabel()
        self.added.setObjectName("Muted")
        form.addRow("Payment date", self.date)
        form.addRow("Dividend per share", self.dps)
        form.addRow("Shares owned", self.shares)
        form.addRow("Cash received", self.cash)
        form.addRow("", self.reinvest)
        form.addRow("Reinvest price", self.reinvest_price)
        form.addRow("", self.added)
        lay.addLayout(form)
        lay.addLayout(_buttons(self, "Record dividend"))

        if self.quote and self.quote.last_dividend:
            self.dps.setValue(self.quote.last_dividend)
        self.date.dateChanged.connect(self._date_changed)
        for w in (self.dps, self.shares, self.reinvest_price):
            w.valueChanged.connect(self._update)
        self.reinvest.toggled.connect(self._update)
        self._date_changed()

    def _date_changed(self):
        day = _iso(self.date)
        self.shares.setValue(self.holding.position(day).shares)
        price = None
        if self.quote:
            price = self.quote.close_on(day) or self.quote.price
        if price:
            self.reinvest_price.setValue(price)
        self._update()

    def _update(self):
        cash = round(self.dps.value() * self.shares.value(), 2)
        self.cash.setText(money(cash))
        on = self.reinvest.isChecked()
        self.reinvest_price.setEnabled(on)
        p = self.reinvest_price.value()
        self.added.setText(f"Adds {num(cash / p, 6)} shares" if on and p > 0 else "")

    def accept(self):
        price = self.reinvest_price.value() if self.reinvest.isChecked() else None
        if self.reinvest.isChecked() and not price:
            QMessageBox.warning(self, self.windowTitle(), "Enter the reinvestment price.")
            return
        try:
            self.state.portfolio.record_dividend(self.ticker, _iso(self.date), self.dps.value(),
                                                 self.shares.value(), price)
        except ValueError as exc:
            QMessageBox.warning(self, self.windowTitle(), str(exc))
            return
        self.state.commit()
        super().accept()


TX_COLUMNS = [
    Column("date", "Date", width=110),
    Column("type", "Type", width=110),
    Column("shares", "Shares", lambda v: num(v, 6), "right", width=110),
    Column("price", "Price / Div", lambda v: money(v, 4), "right", width=110),
    Column("amount", "Amount", money, "right", width="stretch"),
]


class HoldingDialog(QDialog):
    """One holding: position summary, DRIP switch, and its full transaction history."""

    def __init__(self, state, ticker, parent=None):
        super().__init__(parent)
        self.state, self.ticker = state, ticker
        self.setWindowTitle(ticker)
        self.resize(720, 560)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(14)
        head = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("PageTitle")
        self.name = QLabel()
        self.name.setObjectName("Muted")
        names = QVBoxLayout()
        names.addWidget(self.title)
        names.addWidget(self.name)
        head.addLayout(names)
        head.addStretch()
        self.drip = QCheckBox("DRIP — reinvest dividends")
        self.drip.toggled.connect(self._toggle_drip)
        head.addWidget(self.drip)
        lay.addLayout(head)

        cards = QHBoxLayout()
        self.c_shares, self.c_cost, self.c_divs, self.c_real = (
            StatCard("Shares"), StatCard("Cost basis"), StatCard("Dividends received"),
            StatCard("Realized gain"))
        for c in (self.c_shares, self.c_cost, self.c_divs, self.c_real):
            cards.addWidget(c)
        lay.addLayout(cards)

        self.model = RecordsModel(TX_COLUMNS)
        self.table = make_table(self.model)
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        delete = QPushButton("Delete selected")
        delete.setObjectName("Danger")
        delete.clicked.connect(self._delete)
        row.addWidget(delete)
        row.addStretch()
        for text, fn in (("Sell…", lambda: TradeDialog(state, "sell", ticker, self).exec()),
                         ("Record dividend…", lambda: DividendDialog(state, ticker, self).exec())):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        buy = QPushButton("Buy…")
        buy.setObjectName("Primary")
        buy.clicked.connect(lambda: TradeDialog(state, "buy", ticker, self).exec())
        row.addWidget(buy)
        lay.addLayout(row)

        state.portfolio_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        h = self.state.portfolio.get(self.ticker)
        if h is None:
            self.close()
            return
        q = self.state.quotes.get(self.ticker)
        pos = h.position()
        self.title.setText(h.ticker)
        self.name.setText(q.name if q else "")
        self.drip.blockSignals(True)
        self.drip.setChecked(h.drip_enabled)
        self.drip.blockSignals(False)
        self.c_shares.set(num(pos.shares, 6), f"avg cost {money(pos.avg_cost)}")
        self.c_cost.set(money(pos.cost))
        self.c_divs.set(money(h.total_dividends), f"{len(h.dividends)} payments")
        self.c_real.set(money(pos.realized),
                        tone="positive" if pos.realized > 0 else "negative" if pos.realized < 0 else None)

        rows = [{"date": b.date, "type": "Buy", "shares": b.shares, "price": b.price,
                 "amount": b.shares * b.price, "tx": b} for b in h.buys]
        rows += [{"date": s.date, "type": "Sell", "shares": -s.shares, "price": s.price,
                  "amount": s.shares * s.price, "tx": s} for s in h.sells]
        rows += [{"date": d.date, "type": "Dividend", "shares": d.shares_owned,
                  "price": d.div_per_share, "amount": d.cash, "tx": d} for d in h.dividends]
        rows += [{"date": d.date, "type": "DRIP buy", "shares": d.shares_added,
                  "price": d.reinvest_price, "amount": d.cash_used, "tx": d} for d in h.drip_tx]
        self.model.set_rows(sorted(rows, key=lambda r: r["date"], reverse=True))

    def _toggle_drip(self, on):
        self.state.portfolio.get(self.ticker).drip_enabled = on
        self.state.commit()

    def _delete(self):
        row = selected_row(self.table)
        if row is None:
            return
        tx = row["tx"]
        h = self.state.portfolio.get(self.ticker)
        linked = None
        if isinstance(tx, Dividend):
            linked = next((d for d in h.drip_tx
                           if d.date == tx.date and round(d.cash_used, 2) == round(tx.cash, 2)), None)
        msg = f"Delete this {row['type'].lower()} from {row['date']}?"
        if linked:
            msg += "\nIts DRIP reinvestment will be deleted too."
        if QMessageBox.question(self, "Delete transaction", msg) != QMessageBox.Yes:
            return
        try:
            if linked:
                self.state.portfolio.remove_transaction(self.ticker, linked)
            self.state.portfolio.remove_transaction(self.ticker, tx)
        except ValueError as exc:
            QMessageBox.warning(self, "Can't delete", f"{exc}\n\nDelete the later sale first.")
        self.state.commit()

    def done(self, result):
        try:
            self.state.portfolio_changed.disconnect(self.refresh)
        except (RuntimeError, TypeError):
            pass
        super().done(result)
