"""Apply numbered SQL migrations to a fresh or runner-managed database."""

import argparse
import hashlib
import os
from pathlib import Path

from brokerage.database import connect_db


def migrate() -> list[str]:
    applied = []
    directory = Path(__file__).resolve().parent.parent / "sql"
    with connect_db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(73928104)")
            cursor.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            cursor.execute("SELECT name, sha256 FROM schema_migrations")
            existing = dict(cursor.fetchall())
            cursor.execute("SELECT to_regclass('public.accounts')")
            if not existing and cursor.fetchone()[0] is not None:
                raise ValueError(
                    "This database was initialized manually. Keep using it as-is; "
                    "use a fresh database to verify the migration runner. No reset was performed."
                )
            files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
            names = {path.name for path in files}
            if existing.keys() - names:
                raise ValueError("Applied migration files are missing from the checkout")
            for path in files:
                source = path.read_text(encoding="utf-8")
                digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
                if path.name in existing:
                    if existing[path.name] != digest:
                        raise ValueError(f"Applied migration changed: {path.name}")
                    continue
                sql = source.strip()
                if not sql.startswith("BEGIN;") or not sql.endswith("COMMIT;"):
                    raise ValueError(f"Expected transaction wrapper in {path.name}")
                # Own the transaction so schema changes and history commit together.
                cursor.execute(sql[len("BEGIN;"):-len("COMMIT;")], prepare=False)
                cursor.execute("INSERT INTO schema_migrations (name, sha256) VALUES (%s, %s)",
                               (path.name, digest))
                applied.append(path.name)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply versioned SQL migrations without resetting data")
    parser.add_argument("--database", help="Override POSTGRES_DB for this command")
    args = parser.parse_args()
    if args.database:
        os.environ["POSTGRES_DB"] = args.database
    try:
        applied = migrate()
    except ValueError as error:
        parser.exit(1, f"Migration stopped: {error}\n")
    print(f"Applied {len(applied)} migrations" if applied else "Schema is up to date; no changes")
    for name in applied:
        print(f"  {name}")


if __name__ == "__main__":
    main()
