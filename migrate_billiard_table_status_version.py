"""Idempotent migration: table status versioning (stale device status protection).

Adds billiard_tables.status_version INTEGER NOT NULL DEFAULT 0. Existing tables start at version 0 and
the version then counts every status change. Backs up SQLite first. Safe to run twice.
"""
import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

from app.database import engine


def main():
    if engine.url.get_backend_name() == "sqlite" and engine.url.database and os.path.exists(engine.url.database):
        backup = f"{engine.url.database}.bak-{datetime.now():%Y%m%d%H%M%S}"
        shutil.copy2(engine.url.database, backup)
        print("backup:", backup)

    if "status_version" not in {c["name"] for c in inspect(engine).get_columns("billiard_tables")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE billiard_tables ADD COLUMN status_version INTEGER NOT NULL DEFAULT 0"))
        print("added billiard_tables.status_version")
    print("done")


if __name__ == "__main__":
    main()
