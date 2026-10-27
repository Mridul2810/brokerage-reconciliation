"""Manual settlement simulation; no market calendar or external transfers."""

from brokerage.database import connect_db
from brokerage.executions import _dollars
from brokerage.ledger import JournalEntry, Posting, Side
from brokerage.repository import SaveResult, _save_entry


def settle_execution(execution_reference: str) -> SaveResult:
    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT o.available_account_id FROM trade_executions e
                JOIN buy_orders o ON o.reference = e.order_reference
                WHERE e.reference = %s
            """, (execution_reference,))
            account = cursor.fetchone()
            if account is None:
                raise ValueError(f"Unknown execution: {execution_reference}")
            cursor.execute("SELECT account_id FROM accounts WHERE account_id = %s FOR UPDATE", (account[0],))
            cursor.execute("""
                SELECT quantity, price_cents, settlement_status, settlement_entry_id
                FROM trade_executions WHERE reference = %s FOR UPDATE
            """, (execution_reference,))
            quantity, price_cents, status, settlement_id = cursor.fetchone()
            if status == "settled":
                return SaveResult(settlement_id, created=False)

            cost = _dollars(quantity * price_cents)
            entry = JournalEntry(f"trade-settlement:{execution_reference}", (
                Posting("clearing_trade_payable", Side.DEBIT, cost),
                Posting("bank_cash", Side.CREDIT, cost),
            ))
            result = _save_entry(connection, entry)
            if not result.created:
                raise ValueError("Settlement cash reference already belongs to another entry")
            cursor.execute("""
                UPDATE trade_executions
                SET settlement_status = 'settled', settlement_entry_id = %s,
                    settled_at = CURRENT_TIMESTAMP
                WHERE reference = %s
            """, (result.entry_id, execution_reference))

    return result
