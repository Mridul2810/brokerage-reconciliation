"""Reverse an entire entry while preserving its original postings."""

from decimal import Decimal

from brokerage.database import connect_db
from brokerage.ledger import JournalEntry, Posting, Side
from brokerage.repository import SaveResult, _save_entry


def reverse_entry(original_reference: str, reversal_reference: str) -> SaveResult:
    if original_reference == reversal_reference:
        raise ValueError("A reversal needs its own reference")

    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT entry_id FROM journal_entries WHERE reference = %s FOR UPDATE",
                (original_reference,),
            )
            original = cursor.fetchone()
            if original is None:
                raise ValueError(f"Unknown journal reference: {original_reference}")
            original_id = original[0]

            cursor.execute(
                "SELECT 1 FROM journal_reversals WHERE reversal_entry_id = %s",
                (original_id,),
            )
            if cursor.fetchone() is not None:
                raise ValueError("Reversing a reversal is not supported")

            cursor.execute("""
                SELECT j.reference FROM journal_reversals r
                JOIN journal_entries j ON j.entry_id = r.reversal_entry_id
                WHERE r.original_entry_id = %s
            """, (original_id,))
            prior_reversal = cursor.fetchone()
            if prior_reversal is not None and prior_reversal[0] != reversal_reference:
                raise ValueError("This journal entry has already been reversed")

            cursor.execute("""
                SELECT a.code, p.side, p.amount_cents
                FROM postings p JOIN accounts a ON a.account_id = p.account_id
                WHERE p.entry_id = %s ORDER BY p.posting_id
            """, (original_id,))
            postings = []
            for account, side, cents in cursor.fetchall():
                dollars, remainder = divmod(cents, 100)
                amount = Decimal(f"{dollars}.{remainder:02d}")
                opposite = Side.CREDIT if side == "debit" else Side.DEBIT
                postings.append(Posting(account, opposite, amount))
            reversal = JournalEntry(reversal_reference, tuple(postings))

            if prior_reversal is not None:
                return _save_entry(connection, reversal)

            # A new reversal must not reuse an unrelated entry, even if it matches.
            result = _save_entry(connection, reversal)
            if not result.created:
                raise ValueError("Reversal reference already belongs to another entry")
            cursor.execute("""
                INSERT INTO journal_reversals (original_entry_id, reversal_entry_id)
                VALUES (%s, %s)
            """, (original_id, result.entry_id))

    return result
