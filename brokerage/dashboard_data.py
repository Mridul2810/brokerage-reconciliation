"""Read models for the local operations dashboard."""

from psycopg.rows import dict_row

from brokerage.database import connect_db


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    dollars, remainder = divmod(abs(cents), 100)
    return f"{sign}{dollars}.{remainder:02d}"


def account_summary(account: str) -> dict:
    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("""
                SELECT a.account_id, a.account_type, pair.reserved_account_id
                FROM accounts a LEFT JOIN cash_account_pairs pair
                ON pair.available_account_id = a.account_id WHERE a.code = %s
            """, (account,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Unknown ledger account: {account}")
            account_id, account_type, reserved_id = row
            if account_type != "liability" or reserved_id is None:
                raise ValueError("Summary requires a configured available-cash account")
            cursor.execute("""
                SELECT account_id, SUM(CASE WHEN side = 'credit'
                    THEN amount_cents::NUMERIC ELSE -amount_cents::NUMERIC END)
                FROM postings WHERE account_id IN (%s, %s) GROUP BY account_id
            """, (account_id, reserved_id))
            balances = {identifier: int(cents) for identifier, cents in cursor.fetchall()}
            available, reserved = balances.get(account_id, 0), balances.get(reserved_id, 0)
            cursor.execute("""
                SELECT o.symbol, e.settlement_status, SUM(e.quantity)
                FROM trade_executions e JOIN buy_orders o ON o.reference = e.order_reference
                WHERE o.available_account_id = %s
                GROUP BY o.symbol, e.settlement_status ORDER BY o.symbol, e.settlement_status
            """, (account_id,))
            positions = [{"symbol": symbol, "status": status, "quantity": int(quantity)}
                         for symbol, status, quantity in cursor.fetchall()]
    return {"account": account, "currency": "USD", "available_usd": _money(available),
            "reserved_usd": _money(reserved), "total_cash_usd": _money(available + reserved),
            "positions": positions}


def list_reports(account: str) -> list[dict]:
    with connect_db() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
                SELECT r.run_id, r.clearing_source, r.created_at,
                       COUNT(b.break_id) AS break_count,
                       COUNT(b.break_id) FILTER (WHERE COALESCE(latest.status, 'open') <> 'resolved') AS unresolved_count
                FROM reconciliation_runs r
                LEFT JOIN reconciliation_breaks b ON b.run_id = r.run_id
                LEFT JOIN LATERAL (
                    SELECT status FROM investigation_events WHERE break_id = b.break_id
                    ORDER BY event_id DESC LIMIT 1
                ) latest ON TRUE
                WHERE r.account_code = %s
                GROUP BY r.run_id ORDER BY r.run_id DESC LIMIT 50
            """, (account,))
            return cursor.fetchall()
