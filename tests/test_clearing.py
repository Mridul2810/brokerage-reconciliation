import tempfile
import unittest
from pathlib import Path

from brokerage.clearing import read_clearing_csv


HEADER = "reference,account,symbol,quantity,price_cents,settlement_status\n"


class ClearingCsvTests(unittest.TestCase):
    def read(self, contents):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clearing.csv"
            path.write_text(contents, encoding="utf-8")
            return read_clearing_csv(path, "alex_cash")

    def test_valid_file_preserves_duplicates_for_reconciliation(self):
        row = "fill-001,alex_cash,AAPL,2,4800,settled\n"
        records = self.read(HEADER + row + row)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].quantity, 2)
        self.assertEqual(records[0].price_cents, 4800)

    def test_wrong_header_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "CSV header"):
            self.read("reference,quantity\nfill-001,2\n")

    def test_invalid_rows_report_line_number(self):
        for row in ("fill-001,alex_cash,AAPL,2.5,4800,settled",
                    "fill-001,alex_cash,AAPL,2,4800",
                    "fill-001,alex_cash,AAPL,2,4800,settled,extra",
                    "fill-001,alex_cash,AAPL,2,0,settled"):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, "CSV line 2"):
                self.read(HEADER + row + "\n")

    def test_out_of_scope_account_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the requested scope"):
            self.read(HEADER + "fill-001,sam_cash,AAPL,2,4800,settled\n")
