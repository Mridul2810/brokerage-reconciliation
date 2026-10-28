"""Repeatable portfolio demonstration using its own customer account."""

from dataclasses import replace
from decimal import Decimal

from brokerage.clearing import load_internal_trades
from brokerage.dashboard_data import account_summary
from brokerage.database import connect_db
from brokerage.executions import execute_buy_order, settled_positions
from brokerage.investigations import record_event
from brokerage.ledger import DuplicateReferenceError, JournalEntry, Posting, Side
from brokerage.orders import create_buy_order
from brokerage.reconciliation import TradeRecord, reconcile
from brokerage.reports import save_report
from brokerage.repository import save_entry
from brokerage.settlement import settle_execution
from brokerage.withdrawals import InsufficientFundsError, withdraw


ACCOUNT = "portfolio_demo_cash"
RESERVED = "portfolio_demo_reserved"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_demo() -> dict:
    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO accounts (code, account_type)
                VALUES ('bank_cash', 'asset'), (%s, 'liability'), (%s, 'liability')
                ON CONFLICT (code) DO NOTHING
            """, (ACCOUNT, RESERVED))
            cursor.execute("""
                SELECT code, account_id, account_type FROM accounts
                WHERE code IN ('bank_cash', %s, %s)
            """, (ACCOUNT, RESERVED))
            accounts = {code: (identifier, kind) for code, identifier, kind in cursor.fetchall()}
            require(accounts["bank_cash"][1] == "asset"
                    and accounts[ACCOUNT][1] == accounts[RESERVED][1] == "liability",
                    "Existing demo accounts have incompatible types")
            cursor.execute("""
                INSERT INTO cash_account_pairs (available_account_id, reserved_account_id)
                VALUES (%s, %s) ON CONFLICT (available_account_id) DO NOTHING
            """, (accounts[ACCOUNT][0], accounts[RESERVED][0]))
            cursor.execute("SELECT reserved_account_id FROM cash_account_pairs WHERE available_account_id = %s",
                           (accounts[ACCOUNT][0],))
            require(cursor.fetchone()[0] == accounts[RESERVED][0], "Existing demo account pair is incompatible")

    def deposit(amount):
        return JournalEntry("portfolio-demo-deposit", (
            Posting("bank_cash", Side.DEBIT, Decimal(amount)),
            Posting(ACCOUNT, Side.CREDIT, Decimal(amount)),
        ))

    save_entry(deposit("1000.00"))
    require(not save_entry(deposit("1000.00")).created, "Identical deposit retry was not recognized")
    try:
        save_entry(deposit("1001.00"))
    except DuplicateReferenceError:
        print("PASS: conflicting deposit rejected")
    else:
        raise RuntimeError("Conflicting deposit was accepted")
    try:
        withdraw("portfolio-demo-overdraft", ACCOUNT, Decimal("2000.00"))
    except InsufficientFundsError:
        print("PASS: insufficient-funds withdrawal rejected")
    else:
        raise RuntimeError("Overspending was accepted")

    broken = JournalEntry("portfolio-demo-rollback", (
        Posting("bank_cash", Side.DEBIT, Decimal("10.00")),
        Posting("portfolio_demo_missing_account", Side.CREDIT, Decimal("10.00")),
    ))
    try:
        save_entry(broken)
    except ValueError as error:
        require("Unknown ledger account" in str(error), "Unexpected rollback scenario error")
    else:
        raise RuntimeError("Missing-account posting was accepted")
    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM journal_entries WHERE reference IN (%s, %s)",
                           ("portfolio-demo-rollback", "portfolio-demo-overdraft"))
            require(cursor.fetchone()[0] == 0, "Rejected operations left journal records")
    print("PASS: partial-write failure rolled back")

    create_buy_order("portfolio-demo-order", ACCOUNT, "AAPL", 2, Decimal("50.00"))
    execute_buy_order("portfolio-demo-fill", "portfolio-demo-order", Decimal("48.00"))
    settle_execution("portfolio-demo-fill")
    require(not settle_execution("portfolio-demo-fill").created, "Settlement retry paid twice")
    summary = account_summary(ACCOUNT)
    require(summary["available_usd"] == "904.00" and summary["reserved_usd"] == "0.00",
            "Demo account no longer matches the expected cash scenario")
    require(settled_positions(ACCOUNT) == [("AAPL", 2)], "Unexpected settled shares")
    print("PASS: deposit → reservation → fill → settlement; USD 904.00 and 2 settled shares")

    internal = load_internal_trades(ACCOUNT)
    # Independently specified synthetic external facts, not a database export.
    clearing = [TradeRecord("portfolio-demo-fill", ACCOUNT, "AAPL", 2, 4800, "settled")]
    faulty = [replace(clearing[0], quantity=3)]
    require(len(reconcile(internal, faulty)) == 1, "Expected exactly one quantity break")
    require(reconcile(internal, clearing) == [], "Expected a matching clearing comparison")
    bad_run = save_report(ACCOUNT, "synthetic-wrong-quantity", internal, faulty)
    good_run = save_report(ACCOUNT, "synthetic-matching", internal, clearing)
    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT break_id FROM reconciliation_breaks WHERE run_id = %s", (bad_run,))
            break_id = cursor.fetchone()[0]
    record_event(f"portfolio-investigate-{bad_run}", break_id, "investigating", "demo_operator",
                 "Synthetic clearing input reports 3 shares; internal execution records 2.")
    record_event(f"portfolio-resolve-{bad_run}", break_id, "resolved", "demo_operator",
                 f"Matching synthetic input verified in run {good_run}; original evidence preserved.")
    print(f"PASS: break preserved in run {bad_run}; matching evidence in run {good_run}")
    print(f"Dashboard account: {ACCOUNT}")
    return {"account": ACCOUNT, "break_run": bad_run, "matching_run": good_run}


if __name__ == "__main__":
    run_demo()
