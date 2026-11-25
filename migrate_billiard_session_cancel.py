"""Idempotent migration: cancelled sessions (roadmap item B).

Adds table_sessions.cancelled_at, cancelled_by_id and cancel_reason. The 'cancelled'
status already exists (migrate_billiard_phase1.py). Backs up SQLite first. Safe to run twice.
"""
import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

# NOTE: same import your other migrate_*.py scripts use
from app.database import engine

PG = engine.url.get_backend_name() == "postgresql"
TS = "TIMESTAMP WITH TIME ZONE" if PG else "DATETIME"

COLUMNS = {
    "cancelled_at": TS,
    "cancelled_by_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
    "cancel_reason": "VARCHAR(255)",
}


def main():
    if engine.url.get_backend_name() == "sqlite" and engine.url.database and os.path.exists(engine.url.database):
        backup = f"{engine.url.database}.bak-{datetime.now():%Y%m%d%H%M%S}"
        shutil.copy2(engine.url.database, backup)
        print("backup:", backup)

    existing = {c["name"] for c in inspect(engine).get_columns("table_sessions")}
    with engine.begin() as conn:
        for name, ddl in COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE table_sessions ADD COLUMN {name} {ddl}"))
                print(f"added table_sessions.{name}")
    print("done")


if __name__ == "__main__":
    main()
