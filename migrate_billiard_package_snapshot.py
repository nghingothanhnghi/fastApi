"""Idempotent migration: packages in billing (roadmap item F).

Adds table_sessions.package_snapshot (JSON) and session_items.from_package (BOOLEAN, default false).
The package_id / package_name / package_price columns already exist (migrate_billiard_phase1.py).
Backs up SQLite first. Safe to run twice.
"""
import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

from app.database import engine

# (table, column, DDL)
COLUMNS = [
    ("table_sessions", "package_snapshot", "JSON"),   # same type as pricing_snapshot (migrate_billiard_phase1.py)
    ("session_items", "from_package", "BOOLEAN NOT NULL DEFAULT FALSE" if engine.url.get_backend_name() == "postgresql"
     else "BOOLEAN NOT NULL DEFAULT 0"),
]


def main():
    if engine.url.get_backend_name() == "sqlite" and engine.url.database and os.path.exists(engine.url.database):
        backup = f"{engine.url.database}.bak-{datetime.now():%Y%m%d%H%M%S}"
        shutil.copy2(engine.url.database, backup)
        print("backup:", backup)

    insp = inspect(engine)
    with engine.begin() as conn:
        for table, name, ddl in COLUMNS:
            if name not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                print(f"added {table}.{name}")
    print("done")


if __name__ == "__main__":
    main()
