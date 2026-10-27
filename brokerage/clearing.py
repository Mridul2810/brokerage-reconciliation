"""Read validated clearing CSV records and internal execution snapshots."""

import csv
import re
from pathlib import Path

from brokerage.database import connect_db
from brokerage.reconciliation import TradeRecord


FIELDS = ("reference", "account", "symbol", "quantity", "price_cents", "settlement_status")


def read_clearing_csv(path: Path, account: str) -> list[TradeRecord]:
    records = []
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or tuple(reader.fieldnames) != FIELDS:
            raise ValueError(f"CSV header must be: {','.join(FIELDS)}")
        for row in reader:
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Wrong number of columns")
                if row["account"] != account:
                    raise ValueError("CSV contains an account outside the requested scope")
                for field in ("quantity", "price_cents"):
                    if re.fullmatch(r"[0-9]+", row[field]) is None:
                        raise ValueError(f"{field} must contain integer digits")
                records.append(TradeRecord(
                    row["reference"], row["account"], row["symbol"],
                    int(row["quantity"]), int(row["price_cents"]), row["settlement_status"],
                ))
            except ValueError as error:
                raise ValueError(f"CSV line {reader.line_num}: {error}") from error
    return records


def load_internal_trades(account: str) -> list[TradeRecord]:
    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SELECT account_id FROM accounts WHERE code = %s", (account,))
            if cursor.fetchone() is None:
                raise ValueError(f"Unknown ledger account: {account}")
            cursor.execute("""
                SELECT e.reference, a.code, o.symbol, e.quantity, e.price_cents,
                       e.settlement_status
                FROM trade_executions e JOIN buy_orders o ON o.reference = e.order_reference
                JOIN accounts a ON a.account_id = o.available_account_id
                WHERE a.code = %s ORDER BY e.reference
            """, (account,))
            return [TradeRecord(*row) for row in cursor.fetchall()]
