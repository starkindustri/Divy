"""Shared UI pieces: formatting helpers, stat cards and a generic table model."""
import math

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHeaderView, QLabel, QTableView,
                               QVBoxLayout)

from . import theme

SORT_ROLE = Qt.UserRole + 1


# formatting
def money(v, dp=2):
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.{dp}f}"


def signed_money(v):
    if v is None:
        return "—"
    return ("+" if v > 0 else "") + money(v)


def pct(v, signed=False):
    if v is None:
        return "—"
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def num(v, dp=4):
    if v is None:
        return "—"
    return f"{v:,.{dp}f}".rstrip("0").rstrip(".")


def gain_color(v):
    if v is None or abs(v) < 1e-9:
        return None
    return theme.color("positive" if v > 0 else "negative")


class StatCard(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        self.value = QLabel("—")
        self.value.setObjectName("CardValue")
        self.sub = QLabel("")
        self.sub.setObjectName("CardSub")
        for w in (t, self.value, self.sub):
            lay.addWidget(w)

    def set(self, value, sub="", tone=None):
        self.value.setText(value)
        self.sub.setText(sub or " ")  # keep the line so cards stay aligned
        c = {"positive": "positive", "negative": "negative"}.get(tone)
        self.value.setStyleSheet(f"color: {theme.colors()[c]};" if c else "")


class Column:
    """One table column: how to display, align, sort, and color a row value."""

    def __init__(self, key, title, fmt=str, align="left", color=None, bold=None, width=None,
                 tip=None):
        self.key, self.title, self.fmt, self.tip = key, title, fmt, tip
        self.align = {"left": Qt.AlignLeft, "right": Qt.AlignRight,
                      "center": Qt.AlignHCenter}[align] | Qt.AlignVCenter
        self.color, self.bold, self.width = color, bold, width
        self.numeric = align == "right"


class RecordsModel(QAbstractTableModel):
    def __init__(self, columns):
        super().__init__()
        self.columns = columns
        self.rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal:
            return None
        col = self.columns[section]
        if role == Qt.DisplayRole:
            return col.title
        if role == Qt.TextAlignmentRole:
            return int(col.align)
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = self.columns[index.column()]
        value = row.get(col.key)
        if role == Qt.ToolTipRole and col.tip:
            return col.tip(row) or None
        if role == Qt.DisplayRole or (role == Qt.ToolTipRole and col.width == "stretch"):
            return "—" if value is None and col.numeric else col.fmt(value) if value is not None else ""
        if role == SORT_ROLE:
            if col.numeric:
                return -math.inf if value is None else float(value)
            return "" if value is None else str(value).lower()
        if role == Qt.TextAlignmentRole:
            return int(col.align)
        if role == Qt.ForegroundRole and col.color:
            return col.color(row)
        if role == Qt.FontRole and col.bold and col.bold(row):
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.UserRole:
            return row
        return None


class FilterProxy(QSortFilterProxyModel):
    """Sorts on raw values and filters by text across `keys` plus an optional predicate."""

    def __init__(self, keys):
        super().__init__()
        self.keys = keys
        self.text = ""
        self.predicate = None
        self.setSortRole(SORT_ROLE)

    def set_text(self, text):
        self.text = text.strip().lower()
        self.invalidateFilter()

    def set_predicate(self, fn):
        self.predicate = fn
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, parent):
        row = self.sourceModel().rows[source_row]
        if self.predicate and not self.predicate(row):
            return False
        if not self.text:
            return True
        return any(self.text in str(row.get(k, "")).lower() for k in self.keys)


def make_table(model, proxy=None):
    view = QTableView()
    view.setModel(proxy or model)
    view.setSortingEnabled(proxy is not None)
    view.setAlternatingRowColors(True)
    view.setShowGrid(False)
    view.setSelectionBehavior(QAbstractItemView.SelectRows)
    view.setSelectionMode(QAbstractItemView.SingleSelection)
    view.setEditTriggers(QAbstractItemView.NoEditTriggers)
    view.verticalHeader().setVisible(False)
    view.verticalHeader().setDefaultSectionSize(34)
    header = view.horizontalHeader()
    header.setHighlightSections(False)
    header.setSectionResizeMode(QHeaderView.Interactive)
    header.setMinimumSectionSize(48)
    for i, col in enumerate(model.columns):
        if col.width == "stretch":
            header.setSectionResizeMode(i, QHeaderView.Stretch)
        elif col.width:
            view.setColumnWidth(i, col.width)
        else:
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
    return view


def selected_row(view):
    idx = view.currentIndex()
    if not idx.isValid() or not view.selectionModel().isSelected(idx):
        return None
    return idx.data(Qt.UserRole)
