"""Main window and application entry point."""
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget)

from . import APP_NAME, __version__, icon, theme
from .dialogs import TradeDialog
from .pages import REFRESH_MS, CalendarPage, IncomePage, PortfolioPage
from .portfolio import Portfolio, data_dir, default_path
from .state import AppState


class MainWindow(QMainWindow):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.setWindowTitle(APP_NAME)
        self.resize(1320, 820)
        self.setMinimumSize(1000, 640)

        root = QWidget()
        root.setObjectName("Root")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 12)
        brand = QLabel(APP_NAME)
        brand.setObjectName("Brand")
        sub = QLabel("Dividend portfolio tracker")
        sub.setObjectName("BrandSub")
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.addItems(["Portfolio", "Income", "Dividend Calendar"])
        version = QLabel(f"Version {__version__}")
        version.setObjectName("BrandSub")
        for w in (brand, sub, self.nav):
            sl.addWidget(w)
        sl.addStretch()
        sl.addWidget(version)

        self.portfolio_page = PortfolioPage(state)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.portfolio_page)
        self.pages.addWidget(IncomePage(state))
        self.pages.addWidget(CalendarPage(state, self.buy))
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)

        lay.addWidget(sidebar)
        lay.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        state.message.connect(lambda m: self.statusBar().showMessage(m))
        self.statusBar().showMessage(f"Data file: {state.path}")
        self._menus()

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: state.refresh_quotes())
        self.timer.start(REFRESH_MS)
        QTimer.singleShot(0, state.refresh_quotes)

    def _menus(self):
        file_menu = self.menuBar().addMenu("File")
        for text, fn, key in [
            ("Add Buy…", lambda: self.buy(None), QKeySequence.New),
            ("Import Portfolio…", self.import_portfolio, None),
            ("Export Portfolio…", self.export_portfolio, None),
            ("Show Data Folder", self.show_data_folder, None),
        ]:
            act = QAction(text, self)
            act.triggered.connect(fn)
            if key:
                act.setShortcut(key)
            file_menu.addAction(act)
        view = self.menuBar().addMenu("View")
        for i, name in enumerate(["Portfolio", "Income", "Dividend Calendar"]):
            act = QAction(name, self)
            act.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            act.triggered.connect(lambda _=False, i=i: self.nav.setCurrentRow(i))
            view.addAction(act)
        refresh = QAction("Refresh Prices", self)
        refresh.setShortcut(QKeySequence.Refresh)
        refresh.triggered.connect(lambda: self.state.refresh_quotes())
        view.addAction(refresh)
        about = QAction(f"About {APP_NAME}", self)
        about.setMenuRole(QAction.AboutRole)
        about.triggered.connect(self.about)
        self.menuBar().addMenu("Help").addAction(about)

    def buy(self, ticker):
        TradeDialog(self.state, "buy", ticker, self).exec()

    def import_portfolio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import portfolio (DivyInvestorPro or FreedomTracker JSON)", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path) as f:
                incoming = Portfolio.from_dict(json.load(f))
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", f"Couldn't read that file:\n{exc}")
            return
        current = self.state.portfolio
        if current.holdings:
            ans = QMessageBox.question(
                self, "Import portfolio",
                f"Replace your current portfolio ({len(current.holdings)} holdings) with "
                f"{len(incoming.holdings)} holdings from this file?\n\n"
                "A backup of the current portfolio will be saved first.")
            if ans != QMessageBox.Yes:
                return
            current.save(data_dir() / f"portfolio.backup-{time.strftime('%Y%m%d-%H%M%S')}.json")
        self.state.replace_portfolio(incoming)
        self.statusBar().showMessage(f"Imported {len(incoming.holdings)} holdings from {path}")

    def export_portfolio(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export portfolio", f"divyinvestorpro-{time.strftime('%Y-%m-%d')}.json",
            "JSON (*.json)")
        if path:
            self.state.portfolio.save(Path(path))
            self.statusBar().showMessage(f"Exported to {path}")

    def show_data_folder(self):
        data_dir().mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir())))

    def about(self):
        QMessageBox.about(
            self, APP_NAME,
            f"<b>{APP_NAME}</b> {__version__}<br><br>"
            "Track dividend holdings, income and DRIP, and browse the US dividend calendar.<br><br>"
            "Prices and dividend history: Yahoo Finance. Dividend calendar: Nasdaq.<br>"
            "Data is delayed and for information only — not investment advice.")


def load_portfolio(path):
    """Load the saved portfolio; if it's unreadable, set it aside and start fresh."""
    try:
        return Portfolio.load(path), None
    except Exception as exc:
        broken = path.with_name(f"portfolio.unreadable-{time.strftime('%Y%m%d-%H%M%S')}.json")
        path.rename(broken)
        return Portfolio(), f"Your portfolio file couldn't be read ({exc}).\nIt was moved to:\n{broken}"


def main():
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationVersion(__version__)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(QPixmap.fromImage(icon.draw(512))))
    theme.apply(app)

    path = default_path()
    portfolio, problem = load_portfolio(path)
    state = AppState(path, portfolio)
    win = MainWindow(state)

    def retheme():
        theme.apply(app)
        state.portfolio_changed.emit()  # repaint tables and chart with new colors

    app.styleHints().colorSchemeChanged.connect(lambda _: retheme())
    win.show()
    if problem:
        QMessageBox.warning(win, APP_NAME, problem)
    return app.exec()
