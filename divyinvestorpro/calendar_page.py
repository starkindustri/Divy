"""Dividend Calendar page: ex-dividend dates by day across US markets."""
import csv
import time
from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMenu, QMessageBox, QPushButton)

from . import calendar_data, settings, theme
from .pages import REFRESH_MS, Page
from .portfolio import data_dir
from .widgets import Column, FilterProxy, RecordsModel, long_date, make_table, money_in, selected_row
from .workers import run_async

CACHE_SECONDS = 10 * 60  # reuse a day's results for 10 min (Massive free plan: 5 requests/min)


def _owned_color(r):
    return theme.color("accent") if r["owned"] else None


def _index_color(r):
    return theme.color("accent") if r["indexes"] else theme.color("muted")


COLUMNS = [
    Column("symbol", "Symbol", width=80, bold=lambda r: True, color=_owned_color),
    Column("company", "Company", width="stretch", color=_owned_color),
    Column("exchange", "Exchange", width=105),
    Column("index_label", "Index", width=135, color=_index_color),
    Column("ex_date", "Ex-date", width=102),
    Column("pay_date", "Pay date", width=102),
    Column("dividend", "Dividend", align="right", width=96,
           display=lambda r: money_in(r["dividend"], r["currency"])),
    Column("annual", "Annual", align="right", width=96,
           display=lambda r: money_in(r["annual"], r["currency"])),
    Column("freq", "Frequency", width=92),
    Column("declared", "Declared", width=102),
]
# CSV export also includes the record date and currency
EXPORT_COLUMNS = COLUMNS + [Column("record_date", "Record date"), Column("currency", "Currency")]


class CalendarPage(Page):
    def __init__(self, state, on_buy, on_settings):
        super().__init__("Dividend Calendar")
        self.state, self.on_buy, self.on_settings = state, on_buy, on_settings
        self.req = 0
        self.cache = {}  # (day, api_key) -> (fetched_at, result)
        self.loaded = False

        self.button("Refresh", lambda: self.load(force=True))
        self.button("Export CSV…", self.export)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        prev, nxt = QPushButton("‹"), QPushButton("›")
        for b in (prev, nxt):
            b.setFixedWidth(40)
        start = date.today()
        while start.weekday() >= 5:  # nothing goes ex-dividend on weekends
            start += timedelta(days=1)
        self.date = QDateEdit(QDate(start.year, start.month, start.day))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("ddd, MMM d, yyyy")
        self.date.setMinimumWidth(170)
        today = QPushButton("Today")
        nxt_trading = QPushButton("Next trading day")
        prev.clicked.connect(lambda: self.date.setDate(self.date.date().addDays(-1)))
        nxt.clicked.connect(lambda: self.date.setDate(self.date.date().addDays(1)))
        today.clicked.connect(lambda: self.date.setDate(QDate.currentDate()))
        nxt_trading.clicked.connect(self.next_trading_day)
        self.date.dateChanged.connect(lambda _: self.load())
        for w in (prev, self.date, nxt, today, nxt_trading):
            bar.addWidget(w)
        bar.addSpacing(16)
        self.market = QComboBox()
        self.market.addItems(list(calendar_data.MARKETS))
        self.market.setMinimumWidth(150)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by symbol or company")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(210)
        self.mine = QCheckBox("Only my holdings")
        bar.addWidget(self.market)
        bar.addWidget(self.search)
        bar.addWidget(self.mine)
        bar.addStretch()
        self.root.addLayout(bar)

        # shown while there's no Massive key: explains the Nasdaq-only fallback
        self.banner = QFrame()
        self.banner.setObjectName("Card")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 10, 14, 10)
        msg = QLabel("Showing Nasdaq-listed stocks only. Add a free Massive API key to include "
                     "NYSE, NYSE American and ETFs.")
        msg.setWordWrap(True)
        add_key = QPushButton("Add API key…")
        add_key.setObjectName("Primary")
        add_key.clicked.connect(self.on_settings)
        bl.addWidget(msg, 1)
        bl.addWidget(add_key)
        self.root.addWidget(self.banner)

        self.model = RecordsModel(COLUMNS)
        self.proxy = FilterProxy(["symbol", "company"])
        self.proxy.setSourceModel(self.model)
        self.table = make_table(self.model, self.proxy)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.doubleClicked.connect(lambda _: self.buy_selected())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)
        self.root.addWidget(self.table, 1)
        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        self.root.addWidget(self.info)
        self.source = ""

        self.search.textChanged.connect(lambda t: (self.proxy.set_text(t), self.update_info()))
        self.market.currentTextChanged.connect(lambda _: self.apply_filters())
        self.mine.toggled.connect(lambda _: self.apply_filters())
        state.portfolio_changed.connect(self.mark_owned)
        state.settings_changed.connect(lambda: self.load(force=True) if self.loaded else None)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.auto_refresh)
        self.timer.start(REFRESH_MS)
        self._update_banner()

    def showEvent(self, e):
        super().showEvent(e)
        if not self.loaded:  # fetch the first time the page is opened
            self.load()

    def day(self):
        return self.date.date().toPython()

    def next_trading_day(self):
        d = self.day() + timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        self.date.setDate(QDate(d.year, d.month, d.day))

    def auto_refresh(self):
        if self.loaded and self.day() == date.today() and self.isVisible():
            self.load(force=True)

    def _update_banner(self):
        self.banner.setVisible(not settings.massive_key())

    # loading
    def load(self, force=False):
        self.loaded = True
        self._update_banner()
        key = settings.massive_key()
        self.req += 1
        req, day = self.req, self.day()
        hit = self.cache.get((day, key))
        if hit and not force and time.time() - hit[0] < CACHE_SECONDS:
            self._show(hit[1], day)
            return
        self.info.setText(f"Loading {long_date(day)}…")
        ref_path = data_dir() / "reference.json"
        run_async(lambda: (req, day, key, calendar_data.load_day(day, key, ref_path)),
                  self._loaded, lambda e: self._failed(req, day, e))

    def _loaded(self, result):
        req, day, key, data = result
        self.cache[(day, key)] = (time.time(), data)
        if req == self.req:
            self._show(data, day)

    def _show(self, data, day):
        owned = set(self.state.portfolio.tickers())
        rows = [dict(r, owned=r["symbol"] in owned) for r in data["rows"]]
        self.source = data["source"] + (f" · {data['warning']}" if data["warning"] else "")
        self.model.set_rows(rows)
        self.update_info()

    def _failed(self, req, day, exc):
        if req == self.req:
            self.model.set_rows([])
            self.info.setText(f"Couldn't load the calendar for {long_date(day)}: {exc}")

    # filtering
    def apply_filters(self):
        market = calendar_data.MARKETS[self.market.currentText()]
        mine = self.mine.isChecked()
        self.proxy.set_predicate(lambda r: market(r) and (r["owned"] or not mine))
        self.update_info()

    def mark_owned(self):
        owned = set(self.state.portfolio.tickers())
        for r in self.model.rows:
            r["owned"] = r["symbol"] in owned
        self.model.set_rows(self.model.rows)
        self.update_info()

    def update_info(self):
        total = self.model.rowCount()
        shown = self.proxy.rowCount()
        owned = sum(1 for r in self.model.rows if r["owned"])
        when = long_date(self.day(), weekday=True)
        if total == 0:
            note = " (markets are closed on weekends)" if self.day().weekday() >= 5 else ""
            self.info.setText(f"No ex-dividend dates on {when}{note}. · Source: {self.source}")
            return
        text = f"{shown} of {total} go ex-dividend on {when}"
        if owned:
            text += f" · {owned} in your portfolio (highlighted)"
        self.info.setText(f"{text} · Source: {self.source} · Double-click a row to add a buy")

    # actions
    def buy_selected(self):
        row = selected_row(self.table)
        if row:
            self.on_buy(row["symbol"])

    def context_menu(self, pos):
        row = selected_row(self.table)
        if not row:
            return
        menu = QMenu(self)
        menu.addAction(f"Add a buy of {row['symbol']}…", self.buy_selected)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", f"dividends_{self.day().isoformat()}.csv", "CSV files (*.csv)")
        if not path:
            return
        rows = [self.proxy.index(i, 0).data(Qt.UserRole) for i in range(self.proxy.rowCount())]
        try:
            with open(path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow([c.title for c in EXPORT_COLUMNS])
                for r in rows:
                    w.writerow(["" if r.get(c.key) is None else r[c.key] for c in EXPORT_COLUMNS])
        except OSError as exc:
            QMessageBox.warning(self, "Export CSV", str(exc))
            return
        self.info.setText(f"Exported {len(rows)} rows to {path}")
