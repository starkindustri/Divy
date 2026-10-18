#!/usr/bin/env python3
"""US Dividend Calendar: a small Tkinter app using Nasdaq's public calendar feed.

Standard library only. Run:  python3 dividend_calendar.py
"""
import csv
import json
import threading
import tkinter as tk
import urllib.request
from datetime import date, timedelta
from tkinter import filedialog, messagebox, ttk

API = "https://api.nasdaq.com/api/calendar/dividends?date={}"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
REFRESH_MS = 5 * 60 * 1000

COLUMNS = [
    ("symbol", "Symbol", 70, "w"),
    ("companyName", "Company", 330, "w"),
    ("dividend_Ex_Date", "Ex-Date", 90, "center"),
    ("payment_Date", "Pay Date", 90, "center"),
    ("record_Date", "Record Date", 90, "center"),
    ("dividend_Rate", "Dividend ($)", 90, "e"),
    ("indicated_Annual_Dividend", "Annual ($)", 90, "e"),
    ("announcement_Date", "Announced", 90, "center"),
]
NUMERIC = {"dividend_Rate", "indicated_Annual_Dividend"}
DATES = {"dividend_Ex_Date", "payment_Date", "record_Date", "announcement_Date"}


def fetch_day(day):
    req = urllib.request.Request(API.format(day.isoformat()), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.load(resp)
    return (payload.get("data") or {}).get("calendar", {}).get("rows") or []


def sort_key(col, value):
    if value in (None, "", "N/A"):
        return (1, 0)
    if col in NUMERIC:
        try:
            return (0, float(value))
        except (TypeError, ValueError):
            return (1, 0)
    if col in DATES:
        try:
            m, d, y = str(value).split("/")
            return (0, (int(y), int(m), int(d)))
        except ValueError:
            return (1, 0)
    return (0, str(value).lower())


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("US Dividend Calendar")
        self.geometry("1050x600")
        self.day = date.today()
        self.rows = []
        self.sort_col, self.sort_rev = "symbol", False
        self.req_id = 0
        self._build()
        self.load()
        self.after(REFRESH_MS, self._auto_refresh)

    def _build(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="<", width=3, command=lambda: self.shift(-1)).pack(side="left")
        self.date_var = tk.StringVar(value=self.day.isoformat())
        entry = ttk.Entry(top, textvariable=self.date_var, width=11, justify="center")
        entry.pack(side="left", padx=4)
        entry.bind("<Return>", lambda e: self.goto_entry())
        ttk.Button(top, text=">", width=3, command=lambda: self.shift(1)).pack(side="left")
        ttk.Button(top, text="Today", command=self.goto_today).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Next trading day", command=self.next_trading).pack(side="left", padx=4)
        ttk.Button(top, text="Refresh", command=self.load).pack(side="left")

        ttk.Label(top, text="Filter:").pack(side="left", padx=(16, 4))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self.render())
        ttk.Entry(top, textvariable=self.filter_var, width=20).pack(side="left")
        ttk.Button(top, text="Export CSV", command=self.export).pack(side="right")

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8)
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS], show="headings")
        for key, title, width, anchor in COLUMNS:
            self.tree.heading(key, text=title, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "companyName"))
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.status = tk.StringVar(value="Loading...")
        ttk.Label(self, textvariable=self.status, anchor="w", padding=8).pack(fill="x")

    # navigation
    def set_day(self, d):
        self.day = d
        self.date_var.set(d.isoformat())
        self.load()

    def shift(self, n):
        self.set_day(self.day + timedelta(days=n))

    def goto_today(self):
        self.set_day(date.today())

    def next_trading(self):
        d = self.day + timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        self.set_day(d)

    def goto_entry(self):
        try:
            self.set_day(date.fromisoformat(self.date_var.get().strip()))
        except ValueError:
            messagebox.showerror("Invalid date", "Use the format YYYY-MM-DD.")

    # data
    def load(self):
        self.req_id += 1
        rid, day = self.req_id, self.day
        self.status.set("Loading {}...".format(day.isoformat()))

        def work():
            try:
                rows = fetch_day(day)
                self.after(0, lambda: self.loaded(rid, day, rows, None))
            except Exception as exc:  # network/parse errors shown in the status bar
                self.after(0, lambda: self.loaded(rid, day, None, exc))

        threading.Thread(target=work, daemon=True).start()

    def loaded(self, rid, day, rows, err):
        if rid != self.req_id:
            return  # a newer request superseded this one
        if err is not None:
            self.status.set("Error loading {}: {}".format(day.isoformat(), err))
            return
        self.rows = rows
        self.render()

    def _auto_refresh(self):
        if self.day == date.today():
            self.load()
        self.after(REFRESH_MS, self._auto_refresh)

    # display
    def visible_rows(self):
        q = self.filter_var.get().strip().lower()
        rows = self.rows
        if q:
            rows = [r for r in rows if q in str(r.get("symbol", "")).lower()
                    or q in str(r.get("companyName", "")).lower()]
        return sorted(rows, key=lambda r: sort_key(self.sort_col, r.get(self.sort_col)),
                      reverse=self.sort_rev)

    def render(self):
        self.tree.delete(*self.tree.get_children())
        rows = self.visible_rows()
        for r in rows:
            self.tree.insert("", "end", values=[self.fmt(k, r.get(k)) for k, *_ in COLUMNS])
        self.status.set("{} of {} companies paying dividends - ex-date {}  (Nasdaq data)".format(
            len(rows), len(self.rows), self.day.isoformat()))

    @staticmethod
    def fmt(col, v):
        if v in (None, ""):
            return ""
        if col in NUMERIC:
            try:
                return "{:.4f}".format(float(v)).rstrip("0").rstrip(".")
            except (TypeError, ValueError):
                return str(v)
        return str(v)

    def sort_by(self, col):
        self.sort_rev = (not self.sort_rev) if col == self.sort_col else False
        self.sort_col = col
        self.render()

    def export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile="dividends_{}.csv".format(self.day.isoformat()))
        if not path:
            return
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([c[1] for c in COLUMNS])
            for r in self.visible_rows():
                w.writerow([r.get(k, "") for k, *_ in COLUMNS])
        self.status.set("Exported to {}".format(path))


if __name__ == "__main__":
    App().mainloop()
