"""Verify fresh setup without resetting existing databases."""

import os
import subprocess
import sys
from uuid import uuid4

from psycopg import sql

from brokerage.database import connect_db


def run(module: str, *arguments: str, database: str, database_tests: bool = False) -> None:
    environment = dict(os.environ, POSTGRES_DB=database)
    if database_tests:
        environment["RUN_DB_TESTS"] = "1"
    subprocess.run([sys.executable, "-m", module, *arguments], env=environment, check=True)


def main() -> None:
    database = f"brokerage_verify_{uuid4().hex[:12]}"
    previous_database = os.environ.get("POSTGRES_DB")
    os.environ["POSTGRES_DB"] = "postgres"
    try:
        connection = connect_db()
        try:
            # PostgreSQL requires CREATE DATABASE outside a transaction block.
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        finally:
            connection.close()
    finally:
        if previous_database is None:
            os.environ.pop("POSTGRES_DB", None)
        else:
            os.environ["POSTGRES_DB"] = previous_database

    print(f"Created verification database: {database}", flush=True)
    print("It will be retained for inspection; existing databases are unchanged.", flush=True)
    try:
        for attempt in range(1, 3):
            print(f"\nMigration pass {attempt}/2", flush=True)
            run("brokerage.migrate", database=database)
        for attempt in range(1, 3):
            print(f"\nPortfolio demo pass {attempt}/2", flush=True)
            run("brokerage.portfolio_demo", database=database)
        # The existing test harness deliberately selects brokerage_test.
        print("\nFull test suite (database tests use brokerage_test)", flush=True)
        run("unittest", "discover", "-s", "tests", "-v",
            database="brokerage_test", database_tests=True)
    except subprocess.CalledProcessError as error:
        print(f"\nVerification stopped. Database retained: {database}", file=sys.stderr)
        raise SystemExit(error.returncode) from error
    print(f"\nVERIFICATION PASSED. Fresh database: {database}", flush=True)


if __name__ == "__main__":
    main()
