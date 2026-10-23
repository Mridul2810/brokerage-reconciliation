"""Initial accounting model: balanced USD journal entries."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


def _usd_cents(amount: Decimal) -> int:
    """Convert a validated posting amount to cents without rounding."""
    parts = amount.as_tuple()
    coefficient = int("".join(str(digit) for digit in parts.digits))
    return coefficient * 10 ** (parts.exponent + 2)


class Side(Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class AccountType(Enum):
    ASSET = "asset"
    LIABILITY = "liability"


class DuplicateReferenceError(ValueError):
    """A reference was reused with different journal contents."""


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
            totals[posting.side] += _usd_cents(posting.amount)
        if totals[Side.DEBIT] != totals[Side.CREDIT]:
            raise ValueError("Journal entry must balance: debits must equal credits")


class Ledger:
    """Single-process, in-memory journal; not durable or concurrency-safe."""

    def __init__(self) -> None:
        self._entries: dict[str, JournalEntry] = {}

    @property
    def entries(self) -> tuple[JournalEntry, ...]:
        return tuple(self._entries.values())

    def post(self, entry: JournalEntry) -> bool:
        """Return True for a new entry, False for an identical retry.

        Posting order is part of the retry comparison in this initial model.
        """
        if not isinstance(entry, JournalEntry):
            raise TypeError("Entry must be a JournalEntry")
        existing = self._entries.get(entry.reference)
        if existing is not None:
            if existing != entry:
                raise DuplicateReferenceError(
                    f"Reference {entry.reference!r} already has different contents"
                )
            return False
        self._entries[entry.reference] = entry
        return True


def account_balance(
    entries: tuple[JournalEntry, ...],
    account: str,
    account_type: AccountType,
) -> Decimal:
    """Derive an account's balance from its postings; do not change entries."""
    if not isinstance(account_type, AccountType):
        raise TypeError("Account type must be an AccountType")
    if not isinstance(account, str) or not account.strip():
        raise ValueError("An account name is required")

    increasing_side = (
        Side.DEBIT if account_type == AccountType.ASSET else Side.CREDIT
    )
    balance_cents = 0
    for entry in entries:
        for posting in entry.postings:
            if posting.account != account:
                continue
            cents = _usd_cents(posting.amount)
            if posting.side == increasing_side:
                balance_cents += cents
            else:
                balance_cents -= cents

    # Construct from text to preserve exact cents regardless of Decimal precision.
    sign = "-" if balance_cents < 0 else ""
    dollars, cents = divmod(abs(balance_cents), 100)
    return Decimal(f"{sign}{dollars}.{cents:02d}")
