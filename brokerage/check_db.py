"""Read-only connection check: python -m brokerage.check_db."""

from brokerage.database import connect_db


def main() -> None:
    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            database, user = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM accounts")
            account_count = cursor.fetchone()[0]

    print(f"Connected to {database} as {user}")
    print(f"Ledger accounts: {account_count}")


if __name__ == "__main__":
    main()
