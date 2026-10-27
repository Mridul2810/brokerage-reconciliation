"""Compare buy executions from the same account scope and observation point."""

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class TradeRecord:
    reference: str
    account: str
    symbol: str
    quantity: int
    price_cents: int
    settlement_status: str

    def __post_init__(self) -> None:
        for name in ("reference", "account", "symbol"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Trade {name} is required")
        for name in ("quantity", "price_cents"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"Trade {name} must be a positive integer")
        if self.settlement_status not in ("pending", "settled"):
            raise ValueError("Trade settlement status must be pending or settled")


@dataclass(frozen=True)
class ReconciliationBreak:
    reference: str
    kind: str
    field: str
    internal: str
    clearing: str


def _group(records: list[TradeRecord]) -> dict[str, list[TradeRecord]]:
    grouped = defaultdict(list)
    for record in records:
        grouped[record.reference].append(record)
    return grouped


def reconcile(
    internal: list[TradeRecord], clearing: list[TradeRecord],
) -> list[ReconciliationBreak]:
    """Report differences without modifying either source.

    Reference is the shared execution ID. Repeated IDs are ambiguous: report
    duplicate counts and do not guess which copy to compare. Callers must supply
    complete, comparable scopes; absence alone does not establish the root cause.
    """
    internal_by_ref = _group(internal)
    clearing_by_ref = _group(clearing)
    breaks = []
    fields = ("account", "symbol", "quantity", "price_cents", "settlement_status")

    for reference in sorted(internal_by_ref.keys() | clearing_by_ref.keys()):
        ours = internal_by_ref.get(reference, [])
        theirs = clearing_by_ref.get(reference, [])
        if len(ours) > 1 or len(theirs) > 1:
            if len(ours) > 1:
                breaks.append(ReconciliationBreak(
                    reference, "duplicate_internal", "record_count", str(len(ours)), str(len(theirs)),
                ))
            if len(theirs) > 1:
                breaks.append(ReconciliationBreak(
                    reference, "duplicate_clearing", "record_count", str(len(ours)), str(len(theirs)),
                ))
            continue
        if not theirs:
            breaks.append(ReconciliationBreak(
                reference, "missing_in_clearing", "record_count", "1", "0",
            ))
            continue
        if not ours:
            breaks.append(ReconciliationBreak(
                reference, "missing_in_internal", "record_count", "0", "1",
            ))
            continue
        for field in fields:
            internal_value = getattr(ours[0], field)
            clearing_value = getattr(theirs[0], field)
            if internal_value != clearing_value:
                breaks.append(ReconciliationBreak(
                    reference, "field_mismatch", field, str(internal_value), str(clearing_value),
                ))
    return breaks
