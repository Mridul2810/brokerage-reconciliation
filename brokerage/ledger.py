"""Initial accounting model: balanced USD journal entries."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Side(Enum):
    DEBIT = "debit"
    CREDIT = "credit"


@dataclass(frozen=True)
class Posting:
    account: str
    side: Side
    amount: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.account, str) or not self.account.strip():
            raise ValueError("An account name is required")
        if not isinstance(self.side, Side):
            raise ValueError("Side must be Side.DEBIT or Side.CREDIT")
        if not isinstance(self.amount, Decimal):
            raise TypeError("Use Decimal constructed from a string for amounts")
        if not self.amount.is_finite() or self.amount <= 0:
            raise ValueError("Amount must be finite and positive")
        if self.amount.as_tuple().exponent < -2:
            raise ValueError("USD postings support at most two decimal places")


@dataclass(frozen=True)
class JournalEntry:
    reference: str
    postings: tuple[Posting, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not self.reference.strip():
            raise ValueError("A reference is required")
        if not isinstance(self.postings, tuple):
            raise TypeError("Postings must be an immutable tuple")
        if len(self.postings) < 2:
            raise ValueError("A journal entry needs at least two postings")
        if not all(isinstance(posting, Posting) for posting in self.postings):
            raise TypeError("Every posting must be a Posting")
        # Convert validated USD amounts to integer cents for exact summation.
        # Decimal addition otherwise depends on the active precision context.
        totals = {Side.DEBIT: 0, Side.CREDIT: 0}
        for posting in self.postings:
            parts = posting.amount.as_tuple()
            coefficient = int("".join(str(digit) for digit in parts.digits))
            cents = coefficient * 10 ** (parts.exponent + 2)
            totals[posting.side] += cents
        if totals[Side.DEBIT] != totals[Side.CREDIT]:
            raise ValueError("Journal entry must balance: debits must equal credits")
