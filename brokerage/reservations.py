"""Reserve available customer cash without moving bank cash."""

from decimal import Decimal

from brokerage.database import connect_db
from brokerage.ledger import JournalEntry, Posting, Side, _usd_cents
from brokerage.repository import SaveResult, _save_entry
from brokerage.withdrawals import InsufficientFundsError


def reserve_cash(reference: str, available_account: str, amount: Decimal) -> SaveResult:
    with connect_db() as connection:
        with connection.cursor() as cursor:
            # Withdrawals lock this same available account before checking funds.
            cursor.execute("""
                SELECT a.account_type, r.code, r.account_type
                FROM cash_account_pairs pair
                JOIN accounts a ON a.account_id = pair.available_account_id
                JOIN accounts r ON r.account_id = pair.reserved_account_id
                WHERE a.code = %s
                FOR UPDATE OF a
            """, (available_account,))
            pair = cursor.fetchone()
            if pair is None:
                raise ValueError("Available account requires a configured reserved account")
            if pair[0] != "liability" or pair[2] != "liability":
                raise ValueError("Available and reserved cash accounts must be liabilities")

            entry = JournalEntry(reference, (
                Posting(available_account, Side.DEBIT, amount),
                Posting(pair[1], Side.CREDIT, amount),
            ))
            cursor.execute(
                "SELECT entry_id FROM journal_entries WHERE reference = %s", (reference,),
            )
            if cursor.fetchone() is not None:
                return _save_entry(connection, entry)

            cursor.execute("""
                SELECT COALESCE(SUM(CASE WHEN p.side = 'credit'
                    THEN p.amount_cents::NUMERIC ELSE -p.amount_cents::NUMERIC END), 0)
                FROM postings p JOIN accounts a ON a.account_id = p.account_id
                WHERE a.code = %s
            """, (available_account,))
            if int(cursor.fetchone()[0]) < _usd_cents(amount):
                raise InsufficientFundsError("Insufficient available cash for reservation")
            result = _save_entry(connection, entry)

    return result
