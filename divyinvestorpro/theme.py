"""Light/dark color tokens and the app stylesheet. Follows the macOS appearance."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

LIGHT = {
    "bg": "#f4f6f8", "surface": "#ffffff", "surface2": "#f7f8fa", "border": "#e3e6eb",
    "text": "#1b2230", "muted": "#6b7380", "accent": "#1f8a5b", "accent_text": "#ffffff",
    "selected": "#e2f3ea", "positive": "#178a4c", "negative": "#cf3f3a",
}
DARK = {
    "bg": "#13161b", "surface": "#1b1f26", "surface2": "#20252d", "border": "#2b313b",
    "text": "#e7eaf0", "muted": "#9aa3b1", "accent": "#3dbb83", "accent_text": "#0d1512",
    "selected": "#1d3a2d", "positive": "#3dbb83", "negative": "#f06a63",
}

STYLE = """
QMainWindow, QDialog {{ background: {bg}; }}
QWidget#Root, QWidget#Page {{ background: {bg}; }}
QWidget {{ color: {text}; font-size: 13px; }}
QLabel {{ background: transparent; }}
QLabel#Muted {{ color: {muted}; }}
QLabel#PageTitle {{ font-size: 24px; font-weight: 700; }}
QLabel#Section {{ font-size: 15px; font-weight: 600; }}
QLabel#Brand {{ font-size: 17px; font-weight: 700; padding: 22px 18px 4px 18px; }}
QLabel#BrandSub {{ color: {muted}; font-size: 11px; padding: 0 18px 16px 18px; }}
QLabel#Empty {{ color: {muted}; font-size: 14px; padding: 40px; }}

QWidget#Sidebar {{ background: {surface}; border-right: 1px solid {border}; }}
QListWidget#Nav {{ background: transparent; border: none; outline: 0; }}
QListWidget#Nav::item {{ padding: 10px 14px; margin: 2px 10px; border-radius: 8px; color: {muted}; }}
QListWidget#Nav::item:hover {{ background: {surface2}; }}
QListWidget#Nav::item:selected {{ background: {selected}; color: {accent}; font-weight: 600; }}

QFrame#Card {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
QLabel#CardTitle {{ color: {muted}; font-size: 12px; }}
QLabel#CardValue {{ font-size: 21px; font-weight: 700; }}
QLabel#CardSub {{ color: {muted}; font-size: 12px; }}

QTableView {{ background: {surface}; alternate-background-color: {surface2};
    border: 1px solid {border}; border-radius: 12px; gridline-color: transparent;
    selection-background-color: {selected}; selection-color: {text}; outline: 0; }}
QTableView::item {{ padding: 4px 6px; border: none; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {surface}; color: {muted}; border: none;
    border-bottom: 1px solid {border}; padding: 9px 6px; font-weight: 600; }}
QTableCornerButton::section {{ background: {surface}; border: none; }}

QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 8px;
    padding: 7px 14px; }}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:pressed {{ background: {surface2}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton#Primary {{ background: {accent}; color: {accent_text}; border: 1px solid {accent};
    font-weight: 600; }}
QPushButton#Primary:hover {{ border-color: {text}; }}
QPushButton#Danger {{ color: {negative}; }}

QLineEdit, QDateEdit, QDoubleSpinBox {{ background: {surface}; border: 1px solid {border};
    border-radius: 8px; padding: 6px 8px; selection-background-color: {accent}; }}
QLineEdit:focus, QDateEdit:focus, QDoubleSpinBox:focus {{ border-color: {accent}; }}
QDateEdit::drop-down {{ border: none; width: 22px; }}
QCheckBox {{ spacing: 8px; }}

QStatusBar {{ background: {surface}; color: {muted}; border-top: 1px solid {border}; }}
QMenu {{ background: {surface}; border: 1px solid {border}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {selected}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
"""

_current = dict(LIGHT)


def colors() -> dict:
    return _current


def color(name: str) -> QColor:
    return QColor(_current[name])


def is_dark() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def apply(app) -> None:
    _current.clear()
    _current.update(DARK if is_dark() else LIGHT)
    c = _current
    pal = QPalette()
    for role, key in [(QPalette.Window, "bg"), (QPalette.Base, "surface"),
                      (QPalette.AlternateBase, "surface2"), (QPalette.Text, "text"),
                      (QPalette.WindowText, "text"), (QPalette.Button, "surface"),
                      (QPalette.ButtonText, "text"), (QPalette.Highlight, "accent"),
                      (QPalette.HighlightedText, "accent_text"),
                      (QPalette.PlaceholderText, "muted"), (QPalette.ToolTipBase, "surface"),
                      (QPalette.ToolTipText, "text")]:
        pal.setColor(role, QColor(c[key]))
    app.setPalette(pal)
    app.setStyleSheet(STYLE.format(**c))
