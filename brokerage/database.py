"""Local PostgreSQL connection settings."""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


def connect_db() -> psycopg.Connection:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_file, override=False)

    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Set POSTGRES_PASSWORD in the project's .env file")

    return psycopg.connect(
        host="127.0.0.1",
        port=5433,
        dbname="brokerage",
        user="brokerage",
        password=password,
        connect_timeout=5,
    )
