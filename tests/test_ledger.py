import unittest
from decimal import Decimal
from dataclasses import FrozenInstanceError
from brokerage.ledger import JournalEntry, Posting, Side
from brokerage import ledger


class LedgerTests(unittest.TestCase):
    def test_customer_balance_excludes_other_customers(self):
        deposit = JournalEntry("sam-deposit-001", (
            Posting("bank_cash", Side.DEBIT, Decimal("300.00")),
            Posting("customer_sam_cash_liability", Side.CREDIT, Decimal("300.00")),
        ))

        alex_balance = ledger.account_balance(
            (deposit,),
            "customer_alex_cash_liability",
            ledger.AccountType.LIABILITY,
        )

        self.assertEqual(alex_balance, Decimal("0.00"))

    def test_deposit_then_withdrawal_leaves_800_in_both_accounts(self):
        deposit = JournalEntry("deposit-001", (
            Posting("bank_cash", Side.DEBIT, Decimal("1000.00")),
            Posting("customer_alex_cash_liability", Side.CREDIT, Decimal("1000.00")),
        ))
        withdrawal = JournalEntry("withdrawal-001", (
            Posting("customer_alex_cash_liability", Side.DEBIT, Decimal("200.00")),
            Posting("bank_cash", Side.CREDIT, Decimal("200.00")),
        ))
        entries = (deposit, withdrawal)

        bank_balance = ledger.account_balance(
            entries, "bank_cash", ledger.AccountType.ASSET,
        )
        alex_balance = ledger.account_balance(
            entries, "customer_alex_cash_liability", ledger.AccountType.LIABILITY,
        )

        self.assertEqual(bank_balance, Decimal("800.00"))
        self.assertEqual(alex_balance, Decimal("800.00"))

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


class LedgerIdempotencyTests(unittest.TestCase):
    def make_deposit(self, reference="deposit-001", amount="1000.00"):
        return JournalEntry(reference, (
            Posting("bank_cash", Side.DEBIT, Decimal(amount)),
            Posting("customer_alex_cash_liability", Side.CREDIT, Decimal(amount)),
        ))

    def test_identical_retry_does_not_double_credit(self):
        book = ledger.Ledger()
        self.assertTrue(book.post(self.make_deposit()))
        # Build a separate object to simulate the same request arriving again.
        self.assertFalse(book.post(self.make_deposit()))
        self.assertEqual(len(book.entries), 1)
        self.assertEqual(ledger.account_balance(
            book.entries, "customer_alex_cash_liability", ledger.AccountType.LIABILITY,
        ), Decimal("1000.00"))

    def test_separate_references_are_separate_deposits(self):
        book = ledger.Ledger()
        self.assertTrue(book.post(self.make_deposit("deposit-001")))
        self.assertTrue(book.post(self.make_deposit("deposit-002")))
        self.assertEqual(len(book.entries), 2)
        self.assertEqual(ledger.account_balance(
            book.entries, "customer_alex_cash_liability", ledger.AccountType.LIABILITY,
        ), Decimal("2000.00"))

    def test_conflicting_retry_preserves_original_entry(self):
        book = ledger.Ledger()
        original = self.make_deposit()
        book.post(original)
        with self.assertRaises(ledger.DuplicateReferenceError):
            book.post(self.make_deposit(amount="2000.00"))
        self.assertEqual(book.entries, (original,))
        self.assertEqual(ledger.account_balance(
            book.entries, "customer_alex_cash_liability", ledger.AccountType.LIABILITY,
        ), Decimal("1000.00"))
