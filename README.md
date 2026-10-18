# DivyInvestorPro

A Mac desktop app for tracking a dividend portfolio, written in Python with PySide6 (Qt).
It follows the system light/dark appearance.

![Portfolio](docs/portfolio-dark.png)

## Features

- **Portfolio**: holdings with shares, average cost, live price, day change, gain, yield,
  yield on cost, forward annual income and payout frequency. Double-click a holding (or
  right-click it) to buy, sell, record a dividend, toggle DRIP, or see its full history.
- **DRIP**: recording a dividend with "Reinvest" on also logs the reinvestment purchase,
  so shares and cost basis grow automatically.
- **Income**: dividends received by month (last 12 months), year-to-date, forward estimate,
  and a log of every payment.
- **Dividend Calendar**: every US company going ex-dividend on a chosen day, with filter,
  "only my holdings", CSV export, and double-click to add a buy.
- **Import / export**: File ▸ Import Portfolio… reads DivyInvestorPro files and
  FreedomTracker portfolio JSON files (holdings, buys, sells, dividends, DRIP).

| Income | Calendar | Holding |
|---|---|---|
| ![](docs/income-light.png) | ![](docs/calendar-dark.png) | ![](docs/holding-dark.png) |

## Data sources

- Prices and dividend history: Yahoo Finance chart API (via `curl_cffi`).
- Dividend calendar: Nasdaq's public calendar API.

Both are free, unofficial and keyless; they can change or rate-limit without notice.
Quotes are delayed. Not investment advice.

Your portfolio is saved to `~/Library/Application Support/DivyInvestorPro/portfolio.json`
after every change (File ▸ Show Data Folder). Importing over an existing portfolio saves a
timestamped backup there first.

## Develop

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
.venv/bin/python -m unittest discover tests
```

## Build the Mac app

```bash
./build_mac.sh
```

Produces `dist/DivyInvestorPro.app` and `dist/DivyInvestorPro-<version>-Mac.dmg`. The app is
ad-hoc signed (no Apple Developer ID), so the first time you open it macOS will block it:
right-click the app ▸ Open, or allow it in System Settings ▸ Privacy & Security. The build
is for the Mac architecture it was built on (Apple Silicon here).

Bump the version in `divyinvestorpro/__init__.py`.

## Layout

```
divyinvestorpro/
  portfolio.py   data model, average-cost math, JSON storage (no UI)
  market.py      Yahoo quotes/dividends, Nasdaq calendar (no UI)
  state.py       shared app state: portfolio + latest quotes
  app.py         main window, menus, entry point
  pages.py       Portfolio, Income, Dividend Calendar pages
  dialogs.py     Buy/Sell, Record dividend, Holding details
  widgets.py     table model, stat cards, formatting
  theme.py       light/dark colors and stylesheet
  icon.py        app icon drawn in code
  workers.py     background network calls
tests/           unit tests for the portfolio math and quote estimates
tools/           icon export used by the build
dividend_calendar.py  the earlier standalone Tkinter calendar (superseded)
```
