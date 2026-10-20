"""Portfolio and Income pages (the calendar is in calendar_page.py)."""
from datetime import date

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QValueAxis
from PySide6.QtCore import QMargins, Qt
from PySide6.QtGui import QCursor, QPainter
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QMessageBox,
                               QPushButton, QStackedWidget, QToolTip, QVBoxLayout, QWidget)

from . import theme
from .dialogs import DividendDialog, HoldingDialog, TradeDialog
from .widgets import (Column, FilterProxy, RecordsModel, StatCard, gain_color, make_table, money,
                      num, pct, selected_row, signed_money)

FREQ = {0: "—", 1: "Annual", 2: "Semi-annual", 4: "Quarterly", 12: "Monthly", 52: "Weekly"}
REFRESH_MS = 5 * 60 * 1000


class Page(QWidget):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("Page")
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(28, 24, 28, 20)
        self.root.setSpacing(16)
        self.header = QHBoxLayout()
        t = QLabel(title)
        t.setObjectName("PageTitle")
        self.header.addWidget(t)
        self.header.addStretch()
        self.root.addLayout(self.header)

    def button(self, text, fn, primary=False):
        b = QPushButton(text)
        if primary:
            b.setObjectName("Primary")
        b.clicked.connect(fn)
        self.header.addWidget(b)
        return b


# ---------------------------------------------------------------- Portfolio
HOLDING_COLUMNS = [
    Column("ticker", "Ticker", bold=lambda r: True, tip=lambda r: r["name"]),
    Column("shares", "Shares", lambda v: num(v, 4), "right"),
    Column("avg_cost", "Avg cost", money, "right"),
    Column("price", "Price", money, "right"),
    Column("day_pct", "Day", lambda v: pct(v, True), "right",
           color=lambda r: gain_color(r["day_pct"])),
    Column("value", "Value", money, "right"),
    Column("gain", "Gain", signed_money, "right", color=lambda r: gain_color(r["gain"])),
    Column("gain_pct", "Gain %", lambda v: pct(v, True), "right",
           color=lambda r: gain_color(r["gain_pct"])),
    Column("yield", "Yield", pct, "right"),
    Column("yoc", "YOC", pct, "right"),
    Column("income", "Income / yr", money, "right"),
    Column("freq", "Pays"),
    Column("drip", "DRIP", align="center", width="stretch",
           color=lambda r: theme.color("accent") if r["drip"] == "On" else theme.color("muted")),
]


class PortfolioPage(Page):
    def __init__(self, state):
        super().__init__("Portfolio")
        self.state = state
        self.button("Refresh prices", lambda: state.refresh_quotes())
        self.button("+  Add buy", self.add_buy, primary=True)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards = {k: StatCard(t) for k, t in [
            ("value", "Market value"), ("cost", "Cost basis"), ("gain", "Unrealized gain"),
            ("income", "Forward annual income"), ("yoc", "Yield on cost"),
            ("received", "Dividends received")]}
        for i, card in enumerate(self.cards.values()):
            grid.addWidget(card, 0, i)
        self.root.addLayout(grid)

        self.model = RecordsModel(HOLDING_COLUMNS)
        self.proxy = FilterProxy(["ticker", "name"])
        self.proxy.setSourceModel(self.model)
        self.table = make_table(self.model, self.proxy)
        self.table.sortByColumn(5, Qt.DescendingOrder)  # by value
        self.table.doubleClicked.connect(lambda _: self.open_selected())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)

        empty = QLabel("No holdings yet.\n\nClick “+ Add buy” to add your first position,\n"
                       "or use File ▸ Import Portfolio… to bring in a FreedomTracker file.")
        empty.setObjectName("Empty")
        empty.setAlignment(Qt.AlignCenter)
        self.stack = QStackedWidget()
        self.stack.addWidget(empty)
        self.stack.addWidget(self.table)
        self.root.addWidget(self.stack, 1)

        state.portfolio_changed.connect(self.refresh)
        state.quotes_changed.connect(self.refresh)
        self.refresh()

    def rows(self):
        out = []
        for h in self.state.portfolio.holdings:
            pos = h.position()
            q = self.state.quotes.get(h.ticker)
            price = q.price if q else None
            value = pos.shares * price if price is not None else None
            gain = value - pos.cost if value is not None else None
            adps = q.annual_dividend if q else None
            out.append({
                "ticker": h.ticker, "name": q.name if q else "",
                "shares": pos.shares, "avg_cost": pos.avg_cost if pos.shares else None,
                "price": price, "day_pct": q.change_pct if q else None,
                "prev": q.prev_close if q else None,
                "value": value, "cost": pos.cost, "gain": gain,
                "gain_pct": gain / pos.cost * 100 if gain is not None and pos.cost else None,
                "yield": q.dividend_yield if q else None,
                "yoc": adps / pos.avg_cost * 100 if adps is not None and pos.avg_cost else None,
                "income": adps * pos.shares if adps is not None else None,
                "freq": FREQ.get(q.frequency, "—") if q else "",
                "received": h.total_dividends,
                "drip": "On" if h.drip_enabled else "Off",
            })
        return out

    def refresh(self):
        rows = self.rows()
        self.model.set_rows(rows)
        self.stack.setCurrentIndex(1 if rows else 0)

        priced = [r for r in rows if r["value"] is not None]
        value = sum(r["value"] for r in priced)
        cost_priced = sum(r["cost"] for r in priced)
        cost = sum(r["cost"] for r in rows)
        gain = value - cost_priced
        day = sum(r["shares"] * (r["price"] - r["prev"]) for r in priced if r["prev"])
        income = sum(r["income"] or 0 for r in rows)
        received = sum(r["received"] for r in rows)
        missing = len(rows) - len(priced)

        self.cards["value"].set(money(value) if priced else "—",
                                f"{signed_money(day)} today" if priced else
                                ("Loading prices…" if self.state.loading else ""),
                                "positive" if day > 0 else "negative" if day < 0 else None)
        self.cards["cost"].set(money(cost), f"{len(rows)} holdings" if rows else "")
        self.cards["gain"].set(signed_money(gain) if priced else "—",
                               pct(gain / cost_priced * 100, True) if cost_priced else "",
                               "positive" if gain > 0 else "negative" if gain < 0 else None)
        self.cards["income"].set(money(income), f"{money(income / 12)} / month")
        self.cards["yoc"].set(pct(income / cost * 100) if cost else "—",
                              f"{missing} without prices" if missing and priced else "")
        self.cards["received"].set(money(received), "all time")

    def current_ticker(self):
        row = selected_row(self.table)
        return row["ticker"] if row else None

    def add_buy(self, ticker=None):
        TradeDialog(self.state, "buy", ticker or None, self).exec()

    def open_selected(self):
        t = self.current_ticker()
        if t:
            HoldingDialog(self.state, t, self).exec()

    def context_menu(self, pos):
        t = self.current_ticker()
        if not t:
            return
        h = self.state.portfolio.get(t)
        menu = QMenu(self)
        menu.addAction("Details…", self.open_selected)
        menu.addSeparator()
        menu.addAction("Buy more…", lambda: TradeDialog(self.state, "buy", t, self).exec())
        menu.addAction("Sell…", lambda: TradeDialog(self.state, "sell", t, self).exec())
        menu.addAction("Record dividend…", lambda: DividendDialog(self.state, t, self).exec())
        menu.addAction("Turn DRIP off" if h.drip_enabled else "Turn DRIP on",
                       lambda: self._toggle_drip(t))
        menu.addSeparator()
        menu.addAction(f"Remove {t}…", lambda: self._remove(t))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _toggle_drip(self, t):
        h = self.state.portfolio.get(t)
        h.drip_enabled = not h.drip_enabled
        self.state.commit()

    def _remove(self, t):
        if QMessageBox.question(self, "Remove holding",
                                f"Remove {t} and all of its transactions?") == QMessageBox.Yes:
            self.state.portfolio.remove_holding(t)
            self.state.commit()


# ---------------------------------------------------------------- Income
LOG_COLUMNS = [
    Column("date", "Date", width=110),
    Column("ticker", "Ticker", width=90, bold=lambda r: True),
    Column("dps", "Per share", lambda v: money(v, 4), "right", width=110),
    Column("shares", "Shares", lambda v: num(v, 4), "right", width=110),
    Column("cash", "Amount", money, "right", width=110),
    Column("reinvested", "Reinvested shares", lambda v: num(v, 6), "right", width="stretch"),
]


class IncomePage(Page):
    def __init__(self, state):
        super().__init__("Income")
        self.state = state

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.c_total, self.c_12m, self.c_ytd, self.c_fwd = (
            StatCard("Received, all time"), StatCard("Last 12 months"),
            StatCard("This year"), StatCard("Forward annual estimate"))
        for c in (self.c_total, self.c_12m, self.c_ytd, self.c_fwd):
            cards.addWidget(c)
        self.root.addLayout(cards)

        chart_card = QFrame()
        chart_card.setObjectName("Card")
        cl = QVBoxLayout(chart_card)
        cl.setContentsMargins(14, 12, 14, 8)
        lbl = QLabel("Dividends received by month")
        lbl.setObjectName("Section")
        cl.addWidget(lbl)
        self.chart = QChart()
        self.chart.legend().hide()
        self.chart.setBackgroundVisible(False)
        self.chart.setMargins(QMargins(0, 6, 0, 0))
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setMinimumHeight(230)
        self.chart_view.setStyleSheet("background: transparent;")
        cl.addWidget(self.chart_view)
        self.root.addWidget(chart_card, 3)

        lbl = QLabel("Dividend log")
        lbl.setObjectName("Section")
        self.root.addWidget(lbl)
        self.model = RecordsModel(LOG_COLUMNS)
        self.table = make_table(self.model)
        self.root.addWidget(self.table, 2)

        state.portfolio_changed.connect(self.refresh)
        state.quotes_changed.connect(self.refresh)
        self.refresh()

    @staticmethod
    def last_12_months():
        y, m = date.today().year, date.today().month
        out = []
        for _ in range(12):
            out.append(f"{y:04d}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        return out[::-1]

    def refresh(self):
        p = self.state.portfolio
        by_month = p.dividends_by_month()
        months = self.last_12_months()
        this_year = str(date.today().year)
        self.c_total.set(money(sum(by_month.values())))
        self.c_12m.set(money(sum(by_month.get(m, 0) for m in months)))
        self.c_ytd.set(money(sum(v for k, v in by_month.items() if k.startswith(this_year))))
        fwd = 0.0
        for h in p.holdings:
            q = self.state.quotes.get(h.ticker)
            if q:
                fwd += q.annual_dividend * h.position().shares
        self.c_fwd.set(money(fwd), f"{money(fwd / 12)} / month")
        self.model.set_rows(p.dividend_log())
        self._draw_chart(months, [by_month.get(m, 0.0) for m in months])

    def _draw_chart(self, months, values):
        c = theme.colors()
        self.chart.removeAllSeries()
        for axis in self.chart.axes():
            self.chart.removeAxis(axis)
        bars = QBarSet("Received")
        bars.append(values)
        bars.setColor(theme.color("accent"))
        bars.setBorderColor(theme.color("accent"))
        labels = [date(int(m[:4]), int(m[5:]), 1).strftime("%b %y") for m in months]
        bars.hovered.connect(lambda on, i: QToolTip.showText(
            QCursor.pos(), f"{labels[i]}: {money(values[i])}") if on else QToolTip.hideText())
        series = QBarSeries()
        series.setBarWidth(0.6)
        series.append(bars)
        self.chart.addSeries(series)

        x = QBarCategoryAxis()
        x.append(labels)
        y = QValueAxis()
        y.setRange(0, max(values + [1.0]) * 1.1)
        y.setLabelFormat("$%.0f")
        y.setTickCount(5)
        y.applyNiceNumbers()
        for axis in (x, y):
            axis.setLabelsColor(theme.color("muted"))
            axis.setLinePenColor(theme.color("border"))
            axis.setGridLineColor(theme.color("border"))
        x.setGridLineVisible(False)
        self.chart.addAxis(x, Qt.AlignBottom)
        self.chart.addAxis(y, Qt.AlignLeft)
        series.attachAxis(x)
        series.attachAxis(y)
        self.chart_view.setBackgroundBrush(theme.color("surface"))
        self.chart_view.setStyleSheet(f"background: {c['surface']}; border: none;")
