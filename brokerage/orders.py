"""Whole-share buy limit orders with atomic cash reservations."""

import re
from dataclasses import dataclass
from decimal import Decimal

from brokerage.database import connect_db
from brokerage.ledger import DuplicateReferenceError, JournalEntry, Posting, Side, _usd_cents
from brokerage.repository import _save_entry
from brokerage.reservations import _reserve_cash


@dataclass(frozen=True)
class OrderResult:
    reference: str
    status: str
    created: bool


def create_buy_order(
    reference: str, available_account: str, symbol: str,
    quantity: int, limit_price: Decimal,
) -> OrderResult:
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("An order reference is required")
    if not isinstance(symbol, str) or re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", symbol) is None:
        raise ValueError("Use an uppercase symbol of at most 10 characters")
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("Quantity must be a positive whole number of shares")
    # Reuse the posting's USD precision and positive-amount validation.
    validated_price = Posting(available_account, Side.DEBIT, limit_price)
    price_cents = _usd_cents(validated_price.amount)
    total_cents = quantity * price_cents
    if total_cents > 9223372036854775807:
        raise ValueError("Order value exceeds the supported integer-cents range")
    dollars, cents = divmod(total_cents, 100)
    reservation_amount = Decimal(f"{dollars}.{cents:02d}")

    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT account_id FROM accounts WHERE code = %s FOR UPDATE",
                (available_account,),
            )
            account = cursor.fetchone()
            if account is None:
                raise ValueError(f"Unknown ledger account: {available_account}")

            cursor.execute("""
                SELECT available_account_id, symbol, quantity, limit_price_cents, status
                FROM buy_orders WHERE reference = %s
            """, (reference,))
            existing = cursor.fetchone()
            if existing is not None:
                if existing[:4] != (account[0], symbol, quantity, price_cents):
                    raise DuplicateReferenceError("Order reference already has different contents")
                return OrderResult(reference, existing[4], created=False)

            reservation = _reserve_cash(
                connection, f"order-reserve:{reference}", available_account, reservation_amount,
            )
            if not reservation.created:
                raise ValueError("Order reservation reference already belongs to another entry")
            cursor.execute("""
                INSERT INTO buy_orders
                    (reference, available_account_id, symbol, quantity,
                     limit_price_cents, reservation_entry_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (reference, account[0], symbol, quantity, price_cents, reservation.entry_id))

    return OrderResult(reference, "reserved", created=True)


def cancel_buy_order(reference: str) -> OrderResult:
    """Cancel an unexecuted order and release only its original reservation."""
    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT available_account_id FROM buy_orders WHERE reference = %s",
                (reference,),
            )
            order = cursor.fetchone()
            if order is None:
                raise ValueError(f"Unknown buy order: {reference}")

            # Match creation's lock order: customer account, then order.
            cursor.execute("SELECT account_id FROM accounts WHERE account_id = %s FOR UPDATE", (order[0],))
            cursor.execute(
                "SELECT status, reservation_entry_id FROM buy_orders WHERE reference = %s FOR UPDATE",
                (reference,),
            )
            status, reservation_id = cursor.fetchone()
            if status == "cancelled":
                return OrderResult(reference, status, created=False)
            if status != "reserved":
                raise ValueError("Only unexecuted reserved orders can be cancelled")

            cursor.execute("""
                SELECT a.code, p.side, p.amount_cents
                FROM postings p JOIN accounts a ON a.account_id = p.account_id
                WHERE p.entry_id = %s ORDER BY p.posting_id
            """, (reservation_id,))
            postings = []
            for account, side, cents in cursor.fetchall():
                dollars, remainder = divmod(cents, 100)
                amount = Decimal(f"{dollars}.{remainder:02d}")
                opposite = Side.CREDIT if side == "debit" else Side.DEBIT
                postings.append(Posting(account, opposite, amount))
            release = JournalEntry(f"order-release:{reference}", tuple(postings))
            result = _save_entry(connection, release)
            if not result.created:
                raise ValueError("Cancellation reference already belongs to another entry")
            cursor.execute("""
                UPDATE buy_orders SET status = 'cancelled', cancellation_entry_id = %s
                WHERE reference = %s
            """, (result.entry_id, reference))

    return OrderResult(reference, "cancelled", created=True)
