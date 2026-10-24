"""Store validated journal entries in PostgreSQL."""

from dataclasses import dataclass

from brokerage.database import connect_db
from brokerage.ledger import DuplicateReferenceError, JournalEntry, _usd_cents


@dataclass(frozen=True)
class SaveResult:
    entry_id: int
    created: bool


def save_entry(entry: JournalEntry) -> SaveResult:
    """Save atomically, accepting identical retries and rejecting conflicts.

    Posting order is significant, matching the in-memory ledger's policy.
    Uses PostgreSQL's default READ COMMITTED isolation level.
    """
    if not isinstance(entry, JournalEntry):
        raise TypeError("Entry must be a JournalEntry")

    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO journal_entries (reference) VALUES (%s)
                   ON CONFLICT (reference) DO NOTHING RETURNING entry_id""",
                (entry.reference,),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                cursor.execute(
                    "SELECT entry_id FROM journal_entries WHERE reference = %s",
                    (entry.reference,),
                )
                entry_id = cursor.fetchone()[0]
                cursor.execute(
                    """SELECT a.code, p.side, p.amount_cents
                       FROM postings p JOIN accounts a ON a.account_id = p.account_id
                       WHERE p.entry_id = %s ORDER BY p.posting_id""",
                    (entry_id,),
                )
                stored_postings = cursor.fetchall()
                incoming_postings = [
                    (p.account, p.side.value, _usd_cents(p.amount))
                    for p in entry.postings
                ]
                if stored_postings != incoming_postings:
                    raise DuplicateReferenceError(
                        f"Reference {entry.reference!r} already has different contents"
                    )
                return SaveResult(entry_id, created=False)

            entry_id = inserted[0]

            for posting in entry.postings:
                cursor.execute(
                    "SELECT account_id FROM accounts WHERE code = %s",
                    (posting.account,),
                )
                account = cursor.fetchone()
                if account is None:
                    raise ValueError(f"Unknown ledger account: {posting.account}")

                cursor.execute(
                    """INSERT INTO postings (entry_id, account_id, side, amount_cents)
                       VALUES (%s, %s, %s, %s)""",
                    (entry_id, account[0], posting.side.value, _usd_cents(posting.amount)),
                )

    # The connection context has committed successfully before we return an ID.
    return SaveResult(entry_id, created=True)
