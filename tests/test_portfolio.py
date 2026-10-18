"""Unit tests for the portfolio math. Run: .venv/bin/python -m unittest discover tests"""
import json
import tempfile
import unittest
from pathlib import Path

from divyinvestorpro.market import Quote, us_date_to_iso
from divyinvestorpro.portfolio import Portfolio

FREEDOMTRACKER_SAMPLE = {
    "version": "6.15",
    "tickers": [
        {"ticker": "SPYI", "drip_enabled": True,
         "buys": [{"date": "2026-01-15", "shares": 100.0, "price": 50.0}],
         "drip_tx": [{"date": "2026-02-17", "shares_added": 1.0, "reinvest_price": 50.0,
                      "div_amount_per_share": 0.5, "cash_used": 50.0}],
         "sells": [],
         "dividends": [{"date": "2026-02-17", "cash": 50.0, "div_per_share": 0.5,
                        "shares_owned": 100.0}]},
        {"ticker": "SCHD", "drip_enabled": False,
         "buys": [{"date": "2026-01-15", "shares": 50.0, "price": 27.0}],
         "drip_tx": [], "sells": [], "dividends": []},
    ],
    "monthly_income_goal": 3000.0,
}


class PortfolioTests(unittest.TestCase):
    def test_average_cost_and_realized_gain(self):
        p = Portfolio()
        p.add_buy("abc", "2026-01-01", 10, 10)
        p.add_buy("ABC", "2026-02-01", 10, 20)
        p.add_sell("ABC", "2026-03-01", 5, 30)
        pos = p.get("ABC").position()
        self.assertAlmostEqual(pos.shares, 15)
        self.assertAlmostEqual(pos.avg_cost, 15)
        self.assertAlmostEqual(pos.cost, 225)
        self.assertAlmostEqual(pos.realized, 75)

    def test_cannot_oversell(self):
        p = Portfolio()
        p.add_buy("ABC", "2026-01-01", 10, 10)
        with self.assertRaises(ValueError):
            p.add_sell("ABC", "2026-03-01", 11, 10)
        with self.assertRaises(ValueError):  # sell dated before the buy
            p.add_sell("ABC", "2025-12-01", 1, 10)
        self.assertEqual(p.get("ABC").sells, [])

    def test_removing_buy_that_covers_a_sell_is_refused(self):
        p = Portfolio()
        h = p.add_buy("ABC", "2026-01-01", 10, 10)
        p.add_sell("ABC", "2026-02-01", 10, 12)
        with self.assertRaises(ValueError):
            p.remove_transaction("ABC", h.buys[0])
        self.assertEqual(len(h.buys), 1)

    def test_dividend_with_drip(self):
        p = Portfolio()
        p.add_buy("ABC", "2026-01-01", 100, 10)
        div, drip = p.record_dividend("ABC", "2026-02-01", 0.25, 100, reinvest_price=12.5)
        self.assertEqual(div.cash, 25.0)
        self.assertAlmostEqual(drip.shares_added, 2.0)
        pos = p.get("ABC").position()
        self.assertAlmostEqual(pos.shares, 102)
        self.assertAlmostEqual(pos.cost, 1025)
        self.assertEqual(p.dividends_by_month(), {"2026-02": 25.0})
        self.assertAlmostEqual(p.dividend_log()[0]["reinvested"], 2.0)

    def test_shares_as_of_date(self):
        p = Portfolio()
        p.add_buy("ABC", "2026-01-01", 10, 10)
        p.add_buy("ABC", "2026-03-01", 5, 10)
        h = p.get("ABC")
        self.assertEqual(h.position("2026-02-15").shares, 10)
        self.assertEqual(h.position("2026-03-01").shares, 15)

    def test_imports_freedomtracker_file_and_round_trips(self):
        p = Portfolio.from_dict(FREEDOMTRACKER_SAMPLE)
        self.assertEqual(p.tickers(), ["SPYI", "SCHD"])
        self.assertAlmostEqual(p.get("SPYI").position().shares, 101)
        self.assertTrue(p.get("SPYI").drip_enabled)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "portfolio.json"
            p.save(path)
            again = Portfolio.load(path)
            self.assertEqual(json.loads(path.read_text())["tickers"], p.to_dict()["tickers"])
        self.assertEqual(again.to_dict(), p.to_dict())


class QuoteTests(unittest.TestCase):
    def test_dividend_estimates(self):
        from datetime import date, timedelta
        today = date.today()
        divs = [((today - timedelta(days=30 * i)).isoformat(), 0.5) for i in range(12, 0, -1)]
        divs[-1] = (divs[-1][0], 0.6)
        q = Quote("X", "X", price=60.0, prev_close=59.0, dividends=divs,
                  close_dates=["2026-01-02", "2026-01-05"], closes=[10.0, 11.0])
        self.assertEqual(q.frequency, 12)
        self.assertAlmostEqual(q.annual_dividend, 7.2)
        self.assertAlmostEqual(q.dividend_yield, 12.0)
        self.assertEqual(q.close_on("2026-01-03"), 10.0)
        self.assertIsNone(q.close_on("2025-12-31"))

    def test_us_date(self):
        self.assertEqual(us_date_to_iso("9/5/2026"), "2026-09-05")
        self.assertIsNone(us_date_to_iso("N/A"))


if __name__ == "__main__":
    unittest.main()
