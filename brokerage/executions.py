"""Simulated full fills; settlement remains a separate operation."""

from dataclasses import dataclass
from decimal import Decimal

from brokerage.database import connect_db
from brokerage.ledger import DuplicateReferenceError, JournalEntry, Posting, Side, _usd_cents
from brokerage.repository import _save_entry


@dataclass(frozen=True)
class ExecutionResult:
    reference: str
    created: bool


def _dollars(cents: int) -> Decimal:
    dollars, remainder = divmod(cents, 100)
    return Decimal(f"{dollars}.{remainder:02d}")


def execute_buy_order(reference: str, order_reference: str, price: Decimal) -> ExecutionResult:
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("An execution reference is required")
    price_cents = _usd_cents(Posting("trade_price", Side.DEBIT, price).amount)

    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT available_account_id FROM buy_orders WHERE reference = %s",
                (order_reference,),
            )
            account = cursor.fetchone()
            if account is None:
                raise ValueError(f"Unknown buy order: {order_reference}")
            cursor.execute("SELECT code FROM accounts WHERE account_id = %s FOR UPDATE", (account[0],))
            available_code = cursor.fetchone()[0]
            cursor.execute("""
                SELECT quantity, limit_price_cents, status, reservation_entry_id
                FROM buy_orders WHERE reference = %s FOR UPDATE
            """, (order_reference,))
            quantity, limit_cents, status, reservation_id = cursor.fetchone()

            cursor.execute(
                "SELECT order_reference, price_cents FROM trade_executions WHERE reference = %s",
                (reference,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if existing != (order_reference, price_cents):
                    raise DuplicateReferenceError("Execution reference already has different contents")
                return ExecutionResult(reference, created=False)
            if status != "reserved":
                raise ValueError("Only reserved, unexecuted orders can be filled")
            if price_cents > limit_cents:
                raise ValueError("Execution price exceeds the buy limit price")

            cursor.execute("""
                SELECT a.code FROM postings p JOIN accounts a ON a.account_id = p.account_id
                WHERE p.entry_id = %s AND p.side = 'credit'
            """, (reservation_id,))
            reserved_code = cursor.fetchone()[0]
            cost = quantity * price_cents
            unused = quantity * limit_cents - cost
            postings = [
                Posting(reserved_code, Side.DEBIT, _dollars(cost)),
                Posting("clearing_trade_payable", Side.CREDIT, _dollars(cost)),
            ]
            if unused:
                postings.extend((
                    Posting(reserved_code, Side.DEBIT, _dollars(unused)),
                    Posting(available_code, Side.CREDIT, _dollars(unused)),
                ))
            cash = _save_entry(connection, JournalEntry(f"trade-execution:{reference}", tuple(postings)))
            if not cash.created:
                raise ValueError("Execution cash reference already belongs to another entry")
            cursor.execute("""
                INSERT INTO trade_executions
                    (reference, order_reference, quantity, price_cents, cash_entry_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (reference, order_reference, quantity, price_cents, cash.entry_id))
            cursor.execute("UPDATE buy_orders SET status = 'executed' WHERE reference = %s", (order_reference,))

    return ExecutionResult(reference, created=True)


def pending_positions(available_account: str) -> list[tuple[str, int]]:
    return _positions(available_account, "pending")


def settled_positions(available_account: str) -> list[tuple[str, int]]:
    return _positions(available_account, "settled")


def _positions(available_account: str, status: str) -> list[tuple[str, int]]:
    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT o.symbol, SUM(e.quantity)
                FROM trade_executions e JOIN buy_orders o ON o.reference = e.order_reference
                JOIN accounts a ON a.account_id = o.available_account_id
                WHERE a.code = %s AND e.settlement_status = %s
                GROUP BY o.symbol ORDER BY o.symbol
            """, (available_account, status))
            return [(symbol, int(quantity)) for symbol, quantity in cursor.fetchall()]
