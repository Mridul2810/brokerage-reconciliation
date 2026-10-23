import unittest
from decimal import Decimal
from dataclasses import FrozenInstanceError
from brokerage.ledger import JournalEntry, Posting, Side


class LedgerTests(unittest.TestCase):
    def test_posting_cannot_be_modified(self):
        posting = Posting("bank_cash", Side.DEBIT, Decimal("1000.00"))

        with self.assertRaises(FrozenInstanceError):
            posting.amount = Decimal("500.00")

    def test_balanced_deposit_is_accepted(self):
        entry = JournalEntry("deposit-001", (
            Posting("bank_cash", Side.DEBIT, Decimal("1000.00")),
            Posting("customer_liability", Side.CREDIT, Decimal("1000.00")),
        ))
        self.assertEqual(entry.reference, "deposit-001")

    def test_unbalanced_entry_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must balance"):
            JournalEntry("bad-deposit", (
                Posting("bank_cash", Side.DEBIT, Decimal("1000.00")),
                Posting("customer_liability", Side.CREDIT, Decimal("999.99")),
            ))

    def test_invalid_amounts_are_rejected(self):
        for amount in ("0", "-1", "NaN", "Infinity", "1.001"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                Posting("bank_cash", Side.DEBIT, Decimal(amount))

    def test_float_is_rejected(self):
        with self.assertRaises(TypeError):
            Posting("bank_cash", Side.DEBIT, 0.1)

    def test_multiple_postings_can_balance(self):
        JournalEntry("split-deposit", (
            Posting("bank_cash", Side.DEBIT, Decimal("1000.00")),
            Posting("customer_a_liability", Side.CREDIT, Decimal("600.00")),
            Posting("customer_b_liability", Side.CREDIT, Decimal("400.00")),
        ))
