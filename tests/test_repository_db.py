"""Opt-in tests against a separately initialized brokerage_test database."""

import os
import unittest
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from brokerage.database import connect_db
from brokerage.ledger import DuplicateReferenceError, JournalEntry, Posting, Side
from brokerage.repository import save_entry


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
