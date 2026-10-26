"""Opt-in tests against a separately initialized brokerage_test database."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from psycopg.errors import CheckViolation

from brokerage.database import connect_db
from brokerage.corrections import reverse_entry
from brokerage.ledger import DuplicateReferenceError, JournalEntry, Posting, Side
from brokerage.repository import get_balance, save_entry
from brokerage.withdrawals import InsufficientFundsError, withdraw


@unittest.skipUnless(os.environ.get("RUN_DB_TESTS") == "1", "Database tests are opt-in")
class RepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = patch.dict(os.environ, {"POSTGRES_DB": "brokerage_test"})
        settings.start()
        cls.addClassCleanup(settings.stop)
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                if cursor.fetchone()[0] != "brokerage_test":
                    raise RuntimeError("Database tests require brokerage_test")
                cursor.execute("""
                    INSERT INTO accounts (code, account_type)
                    VALUES ('bank_cash', 'asset'),
                           ('customer_alex_cash_liability', 'liability')
                    ON CONFLICT (code) DO NOTHING
                """)

    def setUp(self):
        self.reference = f"test-{uuid4()}"

    def funded_customer(self):
        customer = f"withdrawal_customer_{uuid4().hex}"
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO accounts (code, account_type) VALUES (%s, 'liability')",
                    (customer,),
                )
        save_entry(self.deposit(amount="100.00", customer=customer))
        return customer

    def test_reversal_restores_balance_and_retry_adds_nothing(self):
        customer = self.funded_customer()
        reference = f"reversal-{uuid4()}"
        first = reverse_entry(self.reference, reference)
        retry = reverse_entry(self.reference, reference)
        self.assertTrue(first.created)
        self.assertFalse(retry.created)
        self.assertEqual(first.entry_id, retry.entry_id)
        self.assertEqual(get_balance(customer), Decimal("0.00"))
        self.assertEqual(self.stored_postings(), [("debit", 10000), ("credit", 10000)])

    def test_second_reversal_reference_is_rejected(self):
        customer = self.funded_customer()
        reverse_entry(self.reference, f"reversal-{uuid4()}")
        with self.assertRaisesRegex(ValueError, "already been reversed"):
            reverse_entry(self.reference, f"reversal-{uuid4()}")
        self.assertEqual(get_balance(customer), Decimal("0.00"))

    def test_unknown_original_cannot_be_reversed(self):
        with self.assertRaisesRegex(ValueError, "Unknown journal reference"):
            reverse_entry(f"missing-{uuid4()}", f"reversal-{uuid4()}")

    def test_withdrawal_leaves_20_and_retry_does_not_spend_again(self):
        customer = self.funded_customer()
        reference = f"withdraw-{uuid4()}"
        first = withdraw(reference, customer, Decimal("80.00"))
        retry = withdraw(reference, customer, Decimal("80.00"))
        self.assertTrue(first.created)
        self.assertFalse(retry.created)
        self.assertEqual(first.entry_id, retry.entry_id)
        self.assertEqual(get_balance(customer), Decimal("20.00"))

    def test_insufficient_withdrawal_saves_no_entry(self):
        customer = self.funded_customer()
        reference = f"withdraw-{uuid4()}"
        with self.assertRaises(InsufficientFundsError):
            withdraw(reference, customer, Decimal("100.01"))
        self.assertEqual(get_balance(customer), Decimal("100.00"))
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM journal_entries WHERE reference = %s", (reference,))
                self.assertEqual(cursor.fetchone()[0], 0)

    def test_concurrent_withdrawals_cannot_both_spend_80_from_100(self):
        customer = self.funded_customer()
        start = Barrier(2, timeout=10)

        def attempt(reference):
            start.wait()
            try:
                return withdraw(reference, customer, Decimal("80.00")).created
            except InsufficientFundsError:
                return False

        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(attempt, f"withdraw-{uuid4()}")
            second = workers.submit(attempt, f"withdraw-{uuid4()}")
            results = [first.result(timeout=20), second.result(timeout=20)]
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(get_balance(customer), Decimal("20.00"))

    def test_withdrawal_conflict_is_rejected_even_when_funds_are_low(self):
        customer = self.funded_customer()
        reference = f"withdraw-{uuid4()}"
        withdraw(reference, customer, Decimal("80.00"))
        with self.assertRaises(DuplicateReferenceError):
            withdraw(reference, customer, Decimal("90.00"))
        self.assertEqual(get_balance(customer), Decimal("20.00"))

    def test_database_balances_follow_stored_account_types(self):
        suffix = uuid4().hex
        asset = f"test_cash_{suffix}"
        liability = f"test_customer_{suffix}"
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO accounts (code, account_type) VALUES (%s, 'asset'), (%s, 'liability')",
                    (asset, liability),
                )

        self.assertEqual(get_balance(asset), Decimal("0.00"))
        self.assertEqual(get_balance(liability), Decimal("0.00"))
        save_entry(JournalEntry(self.reference, (
            Posting(asset, Side.DEBIT, Decimal("100.00")),
            Posting(liability, Side.CREDIT, Decimal("100.00")),
        )))
        self.assertEqual(get_balance(asset), Decimal("100.00"))
        self.assertEqual(get_balance(liability), Decimal("100.00"))

    def test_balance_for_unknown_account_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown ledger account"):
            get_balance(f"missing_{uuid4().hex}")

    def deposit(self, amount="50.00", customer="customer_alex_cash_liability"):
        return JournalEntry(self.reference, (
            Posting("bank_cash", Side.DEBIT, Decimal(amount)),
            Posting(customer, Side.CREDIT, Decimal(amount)),
        ))

    def stored_postings(self):
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT p.side, p.amount_cents
                    FROM postings p JOIN journal_entries j ON j.entry_id = p.entry_id
                    WHERE j.reference = %s ORDER BY p.posting_id
                """, (self.reference,))
                return cursor.fetchall()

    def test_identical_retry_keeps_one_pair_of_postings(self):
        first = save_entry(self.deposit())
        retry = save_entry(self.deposit())
        self.assertTrue(first.created)
        self.assertFalse(retry.created)
        self.assertEqual(first.entry_id, retry.entry_id)
        self.assertEqual(self.stored_postings(), [("debit", 5000), ("credit", 5000)])

    def test_concurrent_identical_requests_create_one_entry(self):
        start = Barrier(2, timeout=10)

        def submit_deposit():
            start.wait()
            return save_entry(self.deposit())

        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(submit_deposit)
            second = workers.submit(submit_deposit)
            results = [first.result(timeout=20), second.result(timeout=20)]

        self.assertEqual(sum(result.created for result in results), 1)
        self.assertEqual(results[0].entry_id, results[1].entry_id)
        self.assertEqual(self.stored_postings(), [("debit", 5000), ("credit", 5000)])

    def test_conflict_preserves_original_amount(self):
        save_entry(self.deposit())
        with self.assertRaises(DuplicateReferenceError):
            save_entry(self.deposit("75.00"))
        self.assertEqual(self.stored_postings(), [("debit", 5000), ("credit", 5000)])

    def test_missing_account_rolls_back_entry_and_first_posting(self):
        with self.assertRaisesRegex(ValueError, "Unknown ledger account"):
            save_entry(self.deposit(customer="missing_test_account"))
        self.assertEqual(self.stored_postings(), [])
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM journal_entries WHERE reference = %s",
                    (self.reference,),
                )
                self.assertEqual(cursor.fetchone()[0], 0)

    def test_committed_entry_rejects_additional_balanced_postings(self):
        saved = save_entry(self.deposit())
        with self.assertRaisesRegex(CheckViolation, "same transaction"):
            with connect_db() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO postings (entry_id, account_id, side, amount_cents)
                        SELECT %s, account_id,
                               CASE WHEN code = 'bank_cash' THEN 'debit' ELSE 'credit' END,
                               100
                        FROM accounts
                        WHERE code IN ('bank_cash', 'customer_alex_cash_liability')
                    """, (saved.entry_id,))
        self.assertEqual(self.stored_postings(), [("debit", 5000), ("credit", 5000)])
