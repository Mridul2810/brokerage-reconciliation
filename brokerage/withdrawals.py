"""Cash withdrawals for the initial, fully available cash model."""

from decimal import Decimal

from brokerage.database import connect_db
from brokerage.ledger import JournalEntry, Posting, Side, _usd_cents
from brokerage.repository import SaveResult, _save_entry


class InsufficientFundsError(ValueError):
    """The customer does not have enough available cash."""


def withdraw(reference: str, customer: str, amount: Decimal) -> SaveResult:
    entry = JournalEntry(reference, (
        Posting(customer, Side.DEBIT, amount),
        Posting("bank_cash", Side.CREDIT, amount),
    ))

    with connect_db() as connection:
        with connection.cursor() as cursor:
            # Serialize withdrawal decisions for this customer until commit.
            cursor.execute(
                """SELECT account_type, EXISTS (
                       SELECT 1 FROM cash_account_pairs
                       WHERE reserved_account_id = accounts.account_id
                   ) FROM accounts WHERE code = %s FOR UPDATE""",
                (customer,),
            )
            account = cursor.fetchone()
            if account is None or account[0] != "liability":
                raise ValueError("Withdrawal requires an existing customer liability account")
            if account[1]:
                raise ValueError("Reserved cash cannot be withdrawn directly")

            cursor.execute(
                "SELECT entry_id FROM journal_entries WHERE reference = %s",
                (reference,),
            )
            if cursor.fetchone() is not None:
                # A retry must be checked before checking remaining funds.
                return _save_entry(connection, entry)

            cursor.execute(
                """SELECT COALESCE(SUM(CASE WHEN p.side = 'credit'
                       THEN p.amount_cents::NUMERIC ELSE -p.amount_cents::NUMERIC END), 0)
                   FROM postings p JOIN accounts a ON a.account_id = p.account_id
                   WHERE a.code = %s""",
                (customer,),
            )
            balance_cents = int(cursor.fetchone()[0])
            if balance_cents < _usd_cents(amount):
                raise InsufficientFundsError("Insufficient customer cash for withdrawal")

            result = _save_entry(connection, entry)

    return result
