"""Opt-in tests against a separately initialized brokerage_test database."""

import os
import unittest
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from psycopg.errors import CheckViolation

from brokerage.database import connect_db
from brokerage.corrections import reverse_entry
from brokerage.reservations import reserve_cash
from brokerage.orders import cancel_buy_order, create_buy_order
from brokerage.executions import execute_buy_order, pending_positions, settled_positions
from brokerage.settlement import settle_execution
from brokerage.clearing import load_internal_trades
from brokerage.reports import get_report, save_report
from brokerage.investigations import record_event
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

    def funded_cash_pair(self):
        available = self.funded_customer()
        reserved = f"reserved_{uuid4().hex}"
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO accounts (code, account_type) VALUES (%s, 'liability') RETURNING account_id",
                    (reserved,),
                )
                reserved_id = cursor.fetchone()[0]
                cursor.execute("""
                    INSERT INTO cash_account_pairs (available_account_id, reserved_account_id)
                    SELECT account_id, %s FROM accounts WHERE code = %s
                """, (reserved_id, available))
        return available, reserved

    def test_buy_order_reserves_quantity_times_limit_price(self):
        available, reserved = self.funded_cash_pair()
        result = create_buy_order(f"order-{uuid4()}", available, "AAPL", 2, Decimal("30.00"))
        self.assertTrue(result.created)
        self.assertEqual(result.status, "reserved")
        self.assertEqual(get_balance(available), Decimal("40.00"))
        self.assertEqual(get_balance(reserved), Decimal("60.00"))

    def executed_trade(self):
        available, reserved = self.funded_cash_pair()
        order, execution = f"order-{uuid4()}", f"fill-{uuid4()}"
        create_buy_order(order, available, "AAPL", 2, Decimal("30.00"))
        execute_buy_order(execution, order, Decimal("25.00"))
        return available, execution

    def test_internal_reconciliation_snapshot_tracks_settlement(self):
        available, execution = self.executed_trade()
        before = load_internal_trades(available)
        self.assertEqual(len(before), 1)
        self.assertEqual((before[0].reference, before[0].quantity, before[0].price_cents,
                          before[0].settlement_status), (execution, 2, 2500, "pending"))
        settle_execution(execution)
        after = load_internal_trades(available)
        self.assertEqual(after[0].settlement_status, "settled")
        self.assertEqual(before[0].settlement_status, "pending")

    def test_saved_report_preserves_evidence_after_live_settlement(self):
        available, execution = self.executed_trade()
        internal = load_internal_trades(available)
        clearing = [replace(internal[0], quantity=3)]
        bank_before = get_balance("bank_cash")
        run_id = save_report(available, "synthetic.csv", internal, clearing)
        saved_report = get_report(run_id)
        self.assertEqual(saved_report["breaks"][0]["status"], "open")
        self.assertEqual(saved_report["clearing_records"][0]["quantity"], 3)
        self.assertEqual(get_balance("bank_cash"), bank_before)
        settle_execution(execution)
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT internal_records, clearing_records FROM reconciliation_runs WHERE run_id = %s", (run_id,))
                stored_internal, stored_clearing = cursor.fetchone()
                self.assertEqual(stored_internal[0]["settlement_status"], "pending")
                self.assertEqual(stored_clearing[0]["quantity"], 3)
                cursor.execute("SELECT field, internal_value, clearing_value FROM reconciliation_breaks WHERE run_id = %s", (run_id,))
                self.assertEqual(cursor.fetchall(), [("quantity", "2", "3")])

    def test_matching_report_is_saved_with_no_breaks(self):
        available, execution = self.executed_trade()
        records = load_internal_trades(available)
        run_id = save_report(available, "matching.csv", records, records)
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM reconciliation_breaks WHERE run_id = %s", (run_id,))
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute("SELECT clearing_records_sha256 FROM reconciliation_runs WHERE run_id = %s", (run_id,))
                self.assertEqual(len(cursor.fetchone()[0]), 64)

    def make_quantity_break(self):
        available, execution = self.executed_trade()
        records = load_internal_trades(available)
        run = save_report(available, "faulty.csv", records, [replace(records[0], quantity=3)])
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT break_id FROM reconciliation_breaks WHERE run_id = %s", (run,))
                return cursor.fetchone()[0]

    def test_investigation_history_preserves_original_break(self):
        break_id = self.make_quantity_break()
        record_event(f"note-{uuid4()}", break_id, "investigating", "test_operator", "Checking quantity")
        record_event(f"note-{uuid4()}", break_id, "resolved", "test_operator", "Synthetic input error documented")
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status FROM investigation_events WHERE break_id = %s ORDER BY event_id", (break_id,))
                self.assertEqual(cursor.fetchall(), [("investigating",), ("resolved",)])
                cursor.execute("SELECT internal_value, clearing_value FROM reconciliation_breaks WHERE break_id = %s", (break_id,))
                self.assertEqual(cursor.fetchone(), ("2", "3"))

    def test_investigation_retry_and_conflict(self):
        break_id = self.make_quantity_break()
        reference = f"note-{uuid4()}"
        first = record_event(reference, break_id, "investigating", "test_operator", "Checking quantity")
        retry = record_event(reference, break_id, "investigating", "test_operator", "Checking quantity")
        self.assertTrue(first.created)
        self.assertFalse(retry.created)
        self.assertEqual(first.event_id, retry.event_id)
        with self.assertRaises(DuplicateReferenceError):
            record_event(reference, break_id, "investigating", "test_operator", "Different note")

    def test_investigation_cannot_skip_directly_to_resolved(self):
        break_id = self.make_quantity_break()
        with self.assertRaisesRegex(ValueError, "Cannot change"):
            record_event(f"note-{uuid4()}", break_id, "resolved", "test_operator", "Premature closure")

    def test_resolved_investigation_can_be_reopened_with_new_event(self):
        break_id = self.make_quantity_break()
        for status in ("investigating", "resolved", "investigating"):
            record_event(f"note-{uuid4()}", break_id, status, "test_operator", f"Move to {status}")
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status FROM investigation_events WHERE break_id = %s ORDER BY event_id", (break_id,))
                self.assertEqual(cursor.fetchall(), [("investigating",), ("resolved",), ("investigating",)])

    def test_settlement_moves_bank_cash_and_pending_shares_atomically(self):
        available, execution = self.executed_trade()
        bank_before = get_balance("bank_cash")
        payable_before = get_balance("clearing_trade_payable")
        self.assertEqual(pending_positions(available), [("AAPL", 2)])
        self.assertTrue(settle_execution(execution).created)
        self.assertEqual(get_balance("bank_cash"), bank_before - Decimal("50.00"))
        self.assertEqual(get_balance("clearing_trade_payable"), payable_before - Decimal("50.00"))
        self.assertEqual(get_balance(available), Decimal("50.00"))
        self.assertEqual(pending_positions(available), [])
        self.assertEqual(settled_positions(available), [("AAPL", 2)])

    def test_settlement_retry_does_not_pay_twice(self):
        available, execution = self.executed_trade()
        first = settle_execution(execution)
        bank_after = get_balance("bank_cash")
        retry = settle_execution(execution)
        self.assertFalse(retry.created)
        self.assertEqual(first.entry_id, retry.entry_id)
        self.assertEqual(get_balance("bank_cash"), bank_after)
        self.assertEqual(settled_positions(available), [("AAPL", 2)])

    def test_concurrent_settlements_pay_once(self):
        available, execution = self.executed_trade()
        bank_before = get_balance("bank_cash")
        start = Barrier(2, timeout=10)

        def settle():
            start.wait()
            return settle_execution(execution)

        with ThreadPoolExecutor(max_workers=2) as workers:
            first, second = workers.submit(settle), workers.submit(settle)
            results = [first.result(timeout=20), second.result(timeout=20)]
        self.assertEqual(sum(result.created for result in results), 1)
        self.assertEqual(results[0].entry_id, results[1].entry_id)
        self.assertEqual(get_balance("bank_cash"), bank_before - Decimal("50.00"))
        self.assertEqual(settled_positions(available), [("AAPL", 2)])

    def test_unknown_execution_cannot_be_settled(self):
        with self.assertRaisesRegex(ValueError, "Unknown execution"):
            settle_execution(f"missing-{uuid4()}")

    def test_full_fill_releases_price_improvement_and_records_pending_shares(self):
        available, reserved = self.funded_cash_pair()
        reference = f"order-{uuid4()}"
        create_buy_order(reference, available, "AAPL", 2, Decimal("30.00"))
        bank_before = get_balance("bank_cash")
        payable_before = get_balance("clearing_trade_payable")
        result = execute_buy_order(f"fill-{uuid4()}", reference, Decimal("25.00"))
        self.assertTrue(result.created)
        self.assertEqual(get_balance(available), Decimal("50.00"))
        self.assertEqual(get_balance(reserved), Decimal("0.00"))
        self.assertEqual(get_balance("bank_cash"), bank_before)
        self.assertEqual(get_balance("clearing_trade_payable") - payable_before, Decimal("50.00"))
        self.assertEqual(pending_positions(available), [("AAPL", 2)])

    def test_execution_retry_and_conflict_do_not_duplicate_shares(self):
        available, reserved = self.funded_cash_pair()
        order = f"order-{uuid4()}"
        execution = f"fill-{uuid4()}"
        create_buy_order(order, available, "AAPL", 2, Decimal("30.00"))
        execute_buy_order(execution, order, Decimal("30.00"))
        self.assertFalse(execute_buy_order(execution, order, Decimal("30.00")).created)
        with self.assertRaises(DuplicateReferenceError):
            execute_buy_order(execution, order, Decimal("25.00"))
        self.assertEqual(pending_positions(available), [("AAPL", 2)])
        self.assertEqual(get_balance(reserved), Decimal("0.00"))

    def test_execution_above_limit_leaves_order_reserved(self):
        available, reserved = self.funded_cash_pair()
        order = f"order-{uuid4()}"
        create_buy_order(order, available, "AAPL", 2, Decimal("30.00"))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            execute_buy_order(f"fill-{uuid4()}", order, Decimal("30.01"))
        self.assertEqual(get_balance(reserved), Decimal("60.00"))
        self.assertEqual(pending_positions(available), [])
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status FROM buy_orders WHERE reference = %s", (order,))
                self.assertEqual(cursor.fetchone()[0], "reserved")

    def test_cancelled_order_cannot_be_executed(self):
        available, reserved = self.funded_cash_pair()
        order = f"order-{uuid4()}"
        create_buy_order(order, available, "AAPL", 2, Decimal("30.00"))
        cancel_buy_order(order)
        with self.assertRaisesRegex(ValueError, "Only reserved"):
            execute_buy_order(f"fill-{uuid4()}", order, Decimal("25.00"))
        self.assertEqual(get_balance(available), Decimal("100.00"))
        self.assertEqual(pending_positions(available), [])

    def test_executed_order_cannot_be_cancelled_or_filled_again(self):
        available, reserved = self.funded_cash_pair()
        order = f"order-{uuid4()}"
        create_buy_order(order, available, "AAPL", 2, Decimal("30.00"))
        execute_buy_order(f"fill-{uuid4()}", order, Decimal("25.00"))
        with self.assertRaisesRegex(ValueError, "Only unexecuted"):
            cancel_buy_order(order)
        with self.assertRaisesRegex(ValueError, "Only reserved"):
            execute_buy_order(f"fill-{uuid4()}", order, Decimal("25.00"))
        self.assertEqual(pending_positions(available), [("AAPL", 2)])
        self.assertEqual(get_balance(available), Decimal("50.00"))

    def test_cancellation_releases_only_its_order_and_retry_adds_nothing(self):
        available, reserved = self.funded_cash_pair()
        reserve_cash(f"standalone-{uuid4()}", available, Decimal("10.00"))
        reference = f"order-{uuid4()}"
        create_buy_order(reference, available, "AAPL", 2, Decimal("30.00"))
        first = cancel_buy_order(reference)
        retry = cancel_buy_order(reference)
        self.assertTrue(first.created)
        self.assertEqual(first.status, "cancelled")
        self.assertFalse(retry.created)
        self.assertEqual(get_balance(available), Decimal("90.00"))
        self.assertEqual(get_balance(reserved), Decimal("10.00"))
        replay = create_buy_order(reference, available, "AAPL", 2, Decimal("30.00"))
        self.assertFalse(replay.created)
        self.assertEqual(replay.status, "cancelled")
        self.assertEqual(get_balance(available), Decimal("90.00"))

    def test_concurrent_cancellations_release_cash_once(self):
        available, reserved = self.funded_cash_pair()
        reference = f"order-{uuid4()}"
        create_buy_order(reference, available, "AAPL", 2, Decimal("30.00"))
        start = Barrier(2, timeout=10)

        def cancel():
            start.wait()
            return cancel_buy_order(reference)

        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(cancel)
            second = workers.submit(cancel)
            results = [first.result(timeout=20), second.result(timeout=20)]
        self.assertEqual(sum(result.created for result in results), 1)
        self.assertEqual(get_balance(available), Decimal("100.00"))
        self.assertEqual(get_balance(reserved), Decimal("0.00"))

    def test_order_reservation_cannot_be_generically_reversed(self):
        available, reserved = self.funded_cash_pair()
        reference = f"order-{uuid4()}"
        create_buy_order(reference, available, "AAPL", 2, Decimal("30.00"))
        with self.assertRaisesRegex(ValueError, "order workflow"):
            reverse_entry(f"order-reserve:{reference}", f"reversal-{uuid4()}")
        self.assertEqual(get_balance(reserved), Decimal("60.00"))

    def test_unknown_order_cancellation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown buy order"):
            cancel_buy_order(f"missing-{uuid4()}")

    def test_buy_order_retry_and_changed_quantity(self):
        available, reserved = self.funded_cash_pair()
        reference = f"order-{uuid4()}"
        create_buy_order(reference, available, "AAPL", 2, Decimal("30.00"))
        retry = create_buy_order(reference, available, "AAPL", 2, Decimal("30.00"))
        self.assertFalse(retry.created)
        with self.assertRaises(DuplicateReferenceError):
            create_buy_order(reference, available, "AAPL", 3, Decimal("30.00"))
        self.assertEqual(get_balance(reserved), Decimal("60.00"))

    def test_unfunded_order_does_not_create_order_or_reservation(self):
        available, reserved = self.funded_cash_pair()
        reference = f"order-{uuid4()}"
        with self.assertRaises(InsufficientFundsError):
            create_buy_order(reference, available, "AAPL", 2, Decimal("60.00"))
        self.assertEqual(get_balance(available), Decimal("100.00"))
        self.assertEqual(get_balance(reserved), Decimal("0.00"))
        with connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM buy_orders WHERE reference = %s", (reference,))
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute("SELECT COUNT(*) FROM journal_entries WHERE reference = %s", (f"order-reserve:{reference}",))
                self.assertEqual(cursor.fetchone()[0], 0)

    def test_reservation_moves_cash_without_changing_bank_cash(self):
        available, reserved = self.funded_cash_pair()
        bank_before = get_balance("bank_cash")
        reserve_cash(f"reserve-{uuid4()}", available, Decimal("60.00"))
        self.assertEqual(get_balance(available), Decimal("40.00"))
        self.assertEqual(get_balance(reserved), Decimal("60.00"))
        self.assertEqual(get_balance("bank_cash"), bank_before)

    def test_reservation_retry_and_conflict_preserve_balances(self):
        available, reserved = self.funded_cash_pair()
        reference = f"reserve-{uuid4()}"
        first = reserve_cash(reference, available, Decimal("80.00"))
        retry = reserve_cash(reference, available, Decimal("80.00"))
        self.assertTrue(first.created)
        self.assertFalse(retry.created)
        self.assertEqual(first.entry_id, retry.entry_id)
        with self.assertRaises(DuplicateReferenceError):
            reserve_cash(reference, available, Decimal("90.00"))
        self.assertEqual(get_balance(available), Decimal("20.00"))
        self.assertEqual(get_balance(reserved), Decimal("80.00"))

    def test_reservation_and_withdrawal_compete_for_same_available_cash(self):
        available, reserved = self.funded_cash_pair()
        start = Barrier(2, timeout=10)

        def attempt(operation):
            start.wait()
            try:
                operation(f"cash-request-{uuid4()}", available, Decimal("80.00"))
                return True
            except InsufficientFundsError:
                return False

        with ThreadPoolExecutor(max_workers=2) as workers:
            reservation = workers.submit(attempt, reserve_cash)
            withdrawal = workers.submit(attempt, withdraw)
            reserved_ok = reservation.result(timeout=20)
            withdrawn_ok = withdrawal.result(timeout=20)
        self.assertEqual(sum((reserved_ok, withdrawn_ok)), 1)
        self.assertEqual(get_balance(available), Decimal("20.00"))
        self.assertEqual(get_balance(reserved), Decimal("80.00") if reserved_ok else Decimal("0.00"))

    def test_reserved_cash_cannot_be_spent_by_withdrawing_available_cash(self):
        available, reserved = self.funded_cash_pair()
        reserve_cash(f"reserve-{uuid4()}", available, Decimal("60.00"))
        with self.assertRaises(InsufficientFundsError):
            withdraw(f"withdraw-{uuid4()}", available, Decimal("50.00"))
        self.assertEqual(get_balance(available), Decimal("40.00"))
        self.assertEqual(get_balance(reserved), Decimal("60.00"))

    def test_direct_withdrawal_from_reserved_account_is_rejected(self):
        available, reserved = self.funded_cash_pair()
        reserve_cash(f"reserve-{uuid4()}", available, Decimal("60.00"))
        with self.assertRaisesRegex(ValueError, "Reserved cash cannot be withdrawn"):
            withdraw(f"withdraw-{uuid4()}", reserved, Decimal("10.00"))
        self.assertEqual(get_balance(reserved), Decimal("60.00"))

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
