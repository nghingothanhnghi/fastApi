"""Idempotent migration: audit record for billing review decisions.

Adds table_sessions.billing_review_audit (JSON). Existing sessions keep NULL.
Backs up SQLite first. Safe to run twice.
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

    if "billing_review_audit" not in {c["name"] for c in inspect(engine).get_columns("table_sessions")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE table_sessions ADD COLUMN billing_review_audit JSON"))
        print("added table_sessions.billing_review_audit")
    print("done")


if __name__ == "__main__":
    main()
