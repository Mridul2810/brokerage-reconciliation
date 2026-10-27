"""Persist reconciliation evidence without modifying financial records."""

import hashlib
import json
from dataclasses import asdict

from psycopg.types.json import Jsonb

from brokerage.database import connect_db
from brokerage.reconciliation import TradeRecord, reconcile


def save_report(
    account: str, clearing_source: str,
    internal: list[TradeRecord], clearing: list[TradeRecord],
) -> int:
    if not account.strip() or not clearing_source.strip():
        raise ValueError("An account and clearing source are required")
    if any(record.account != account for record in internal + clearing):
        raise ValueError("Report records must belong to the requested account")
    internal_data = [asdict(record) for record in internal]
    clearing_data = [asdict(record) for record in clearing]
    # Fingerprint the parsed records, including duplicates and their ordering.
    canonical = json.dumps(clearing_data, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    breaks = reconcile(internal, clearing)

    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO reconciliation_runs
                    (account_code, clearing_source, clearing_records_sha256,
                     internal_records, clearing_records)
                VALUES (%s, %s, %s, %s, %s) RETURNING run_id
            """, (account, clearing_source, fingerprint, Jsonb(internal_data), Jsonb(clearing_data)))
            run_id = cursor.fetchone()[0]
            for item in breaks:
                cursor.execute("""
                    INSERT INTO reconciliation_breaks
                        (run_id, reference, kind, field, internal_value, clearing_value)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (run_id, item.reference, item.kind, item.field, item.internal, item.clearing))
    return run_id
