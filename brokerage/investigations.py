"""Append operator observations; resolution is not an automatic financial repair."""

from dataclasses import dataclass

from brokerage.database import connect_db
from brokerage.ledger import DuplicateReferenceError


@dataclass(frozen=True)
class InvestigationResult:
    event_id: int
    created: bool


def record_event(reference: str, break_id: int, status: str, actor: str, note: str) -> InvestigationResult:
    for name, value in (("reference", reference), ("actor", actor), ("note", note)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Investigation {name} is required")
    if type(break_id) is not int or break_id <= 0:
        raise ValueError("Break ID must be a positive integer")
    if status not in ("open", "investigating", "resolved"):
        raise ValueError("Status must be open, investigating, or resolved")

    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT break_id FROM reconciliation_breaks WHERE break_id = %s FOR UPDATE", (break_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"Unknown reconciliation break: {break_id}")
            cursor.execute("""
                SELECT event_id, break_id, status, actor, note
                FROM investigation_events WHERE reference = %s
            """, (reference,))
            existing = cursor.fetchone()
            if existing is not None:
                if existing[1:] != (break_id, status, actor, note):
                    raise DuplicateReferenceError("Investigation reference already has different contents")
                return InvestigationResult(existing[0], created=False)

            cursor.execute("""
                SELECT status FROM investigation_events WHERE break_id = %s
                ORDER BY event_id DESC LIMIT 1
            """, (break_id,))
            latest = cursor.fetchone()
            current = latest[0] if latest else "open"
            allowed = {
                "open": {"open", "investigating"},
                "investigating": {"investigating", "resolved"},
                "resolved": {"resolved", "investigating"},
            }
            if status not in allowed[current]:
                raise ValueError(f"Cannot change investigation from {current} to {status}")
            cursor.execute("""
                INSERT INTO investigation_events (reference, break_id, status, actor, note)
                VALUES (%s, %s, %s, %s, %s) RETURNING event_id
            """, (reference, break_id, status, actor, note))
            event_id = cursor.fetchone()[0]

    return InvestigationResult(event_id, created=True)
