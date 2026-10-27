import unittest
from dataclasses import replace

from brokerage.reconciliation import TradeRecord, reconcile


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.trade = TradeRecord("fill-001", "alex_cash", "AAPL", 2, 4800, "settled")

    def test_matching_records_ignore_file_order(self):
        second = replace(self.trade, reference="fill-002", symbol="MSFT")
        self.assertEqual(reconcile([self.trade, second], [second, self.trade]), [])

    def test_missing_records_are_reported_in_both_directions(self):
        external_only = replace(self.trade, reference="fill-002")
        breaks = reconcile([self.trade], [external_only])
        self.assertEqual([(b.reference, b.kind) for b in breaks], [
            ("fill-001", "missing_in_clearing"), ("fill-002", "missing_in_internal"),
        ])

    def test_duplicate_clearing_records_are_not_overwritten(self):
        breaks = reconcile([self.trade], [self.trade, replace(self.trade, quantity=3)])
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0].kind, "duplicate_clearing")
        self.assertEqual(breaks[0].clearing, "2")

    def test_duplicate_internal_records_are_reported(self):
        breaks = reconcile([self.trade, self.trade], [self.trade])
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0].kind, "duplicate_internal")

    def test_quantity_mismatch_preserves_both_values(self):
        breaks = reconcile([self.trade], [replace(self.trade, quantity=3)])
        self.assertEqual(len(breaks), 1)
        self.assertEqual((breaks[0].field, breaks[0].internal, breaks[0].clearing),
                         ("quantity", "2", "3"))

    def test_account_symbol_price_and_status_are_compared(self):
        other = replace(self.trade, account="sam_cash", symbol="MSFT",
                        price_cents=4900, settlement_status="pending")
        breaks = reconcile([self.trade], [other])
        self.assertEqual([b.field for b in breaks],
                         ["account", "symbol", "price_cents", "settlement_status"])

    def test_equal_aggregate_totals_can_still_have_trade_breaks(self):
        second = replace(self.trade, reference="fill-002", quantity=3)
        clearing = [replace(self.trade, quantity=3), replace(second, quantity=2)]
        self.assertEqual(sum(t.quantity * t.price_cents for t in clearing),
                         sum(t.quantity * t.price_cents for t in [self.trade, second]))
        self.assertEqual([b.field for b in reconcile([self.trade, second], clearing)],
                         ["quantity", "quantity"])

    def test_invalid_records_are_rejected_before_comparison(self):
        for change in ({"quantity": 0}, {"quantity": True}, {"price_cents": -1},
                       {"reference": ""}, {"settlement_status": "unknown"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.trade, **change)
