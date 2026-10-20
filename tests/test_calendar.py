"""Tests for calendar row building, symbol matching and market filters."""
import unittest

from divyinvestorpro import calendar_data
from divyinvestorpro.reference import DOW_30, Reference, normalize

REF = Reference(
    names={"KO": "Coca-Cola", "AAPL": "Apple", "BRK.B": "Berkshire B", "ABRpD": "Arbor Pref D",
           "SCHD": "Schwab US Dividend Equity ETF", "ZZZ": "Tiny Co"},
    exchanges={"KO": "NYSE", "AAPL": "Nasdaq", "BRK.B": "NYSE", "ABRpD": "NYSE",
               "SCHD": "ETF", "ZZZ": "NYSE American"},
    sp500=frozenset({"KO", "AAPL", "BRK.B"}),
)

MASSIVE = [
    {"ticker": "KO", "cash_amount": 0.53, "frequency": 4, "distribution_type": "recurring",
     "ex_dividend_date": "2026-12-01", "pay_date": "2026-12-15", "record_date": "2026-12-01",
     "declaration_date": "2026-10-16", "currency": "USD"},
    {"ticker": "BRK.B", "cash_amount": 2.0, "frequency": 0, "distribution_type": "special",
     "ex_dividend_date": "2026-12-01"},
    {"ticker": "SCHD", "cash_amount": 0.26, "frequency": 4, "ex_dividend_date": "2026-12-01"},
    {"ticker": "ABRpD", "cash_amount": 0.39, "frequency": 4, "distribution_type": "recurring",
     "ex_dividend_date": "2026-12-01"},
    {"ticker": "NEWCO", "cash_amount": 0.10, "frequency": 12, "distribution_type": "recurring",
     "ex_dividend_date": "2026-12-01"},
]


class SymbolTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("BRK/B"), "BRK.B")
        self.assertEqual(normalize("brk-b"), "BRK.B")
        self.assertEqual(normalize("ABR^D"), "ABRpD")
        self.assertEqual(normalize("ABRpD"), "ABRpD")
        self.assertEqual(normalize("AAPL"), "AAPL")
        self.assertEqual(normalize("PEP"), "PEP")  # a real 'P' isn't a preferred marker

    def test_dow_has_30(self):
        self.assertEqual(len(DOW_30), 30)


class MassiveRowTests(unittest.TestCase):
    def setUp(self):
        self.rows = {r["symbol"]: r for r in calendar_data.from_massive(MASSIVE, REF)}

    def test_tags_and_annual(self):
        ko = self.rows["KO"]
        self.assertEqual((ko["exchange"], ko["company"]), ("NYSE", "Coca-Cola"))
        self.assertEqual(ko["indexes"], ["Dow 30", "S&P 500"])
        self.assertAlmostEqual(ko["annual"], 2.12)
        self.assertEqual(ko["freq"], "Quarterly")
        self.assertEqual(ko["declared"], "2026-10-16")

    def test_special_dividend_has_no_annual(self):
        brk = self.rows["BRK.B"]
        self.assertIsNone(brk["annual"])
        self.assertEqual(brk["freq"], "Special")

    def test_unknown_and_preferred(self):
        self.assertEqual(self.rows["NEWCO"]["exchange"], "OTC / other")
        self.assertEqual(self.rows["ABRpD"]["exchange"], "NYSE")
        self.assertEqual(self.rows["SCHD"]["exchange"], "ETF")

    def test_market_filters(self):
        rows = list(self.rows.values())

        def pick(market):
            return sorted(r["symbol"] for r in rows if calendar_data.MARKETS[market](r))

        self.assertEqual(pick("NYSE"), ["ABRpD", "BRK.B", "KO"])
        self.assertEqual(pick("ETFs"), ["SCHD"])
        self.assertEqual(pick("Dow 30"), ["KO"])
        self.assertEqual(pick("S&P 500"), ["BRK.B", "KO"])
        self.assertEqual(len(pick("All US markets")), 5)
        self.assertEqual(pick("OTC / other"), ["NEWCO"])

    def test_currency_display(self):
        from divyinvestorpro.widgets import money_in
        self.assertEqual(money_in(0.53, "USD"), "$0.5300")
        self.assertEqual(money_in(0.0225, "CAD"), "0.0225 CAD")
        self.assertEqual(money_in(None, "CAD"), "—")

    def test_without_reference_data(self):
        rows = calendar_data.from_massive(MASSIVE[:1], None)
        self.assertEqual((rows[0]["exchange"], rows[0]["indexes"]), ("OTC / other", []))


class NasdaqRowTests(unittest.TestCase):
    def test_nasdaq_rows(self):
        raw = [{"symbol": "AAPL", "companyName": "Apple Inc.", "dividend_Ex_Date": "11/9/2026",
                "payment_Date": "11/12/2026", "record_Date": "11/9/2026",
                "dividend_Rate": 0.27, "indicated_Annual_Dividend": 1.08,
                "announcement_Date": "10/29/2026"}]
        r = calendar_data.from_nasdaq(raw, REF)[0]
        self.assertEqual((r["exchange"], r["ex_date"], r["annual"]), ("Nasdaq", "2026-11-09", 1.08))
        self.assertEqual(r["indexes"], ["Dow 30", "S&P 500"])


if __name__ == "__main__":
    unittest.main()
