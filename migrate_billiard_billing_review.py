"""Idempotent migration: billing review for device-requested packages (follow-up to roadmap item F).

Adds table_sessions.billing_review_state, requested_package_id, billing_review_reason,
billing_review_resolution, billing_review_note, billing_reviewed_by_id, billing_reviewed_at.
Backs up SQLite first. Safe to run twice. Existing sessions keep NULL = no review.
"""
import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

from app.database import engine

COLUMNS = {
    "billing_review_state": "VARCHAR(20)",
    "requested_package_id": "INTEGER",
    "billing_review_reason": "VARCHAR(255)",
    "billing_review_resolution": "VARCHAR(30)",
    "billing_review_note": "VARCHAR(255)",
    "billing_reviewed_by_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
    "billing_reviewed_at": "TIMESTAMP WITH TIME ZONE" if engine.url.get_backend_name() == "postgresql" else "DATETIME",
}


def main():
    if engine.url.get_backend_name() == "sqlite" and engine.url.database and os.path.exists(engine.url.database):
        backup = f"{engine.url.database}.bak-{datetime.now():%Y%m%d%H%M%S}"
        shutil.copy2(engine.url.database, backup)
        print("backup:", backup)

    insp = inspect(engine)
    existing = {c["name"] for c in insp.get_columns("table_sessions")}
    with engine.begin() as conn:
        for name, ddl in COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE table_sessions ADD COLUMN {name} {ddl}"))
                print(f"added table_sessions.{name}")
        if "ix_table_sessions_billing_review_state" not in {i["name"] for i in insp.get_indexes("table_sessions")}:
            conn.execute(text("CREATE INDEX ix_table_sessions_billing_review_state ON table_sessions (billing_review_state)"))
            print("added index ix_table_sessions_billing_review_state")
    print("done")


if __name__ == "__main__":
    main()
