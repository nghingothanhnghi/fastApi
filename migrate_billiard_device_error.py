"""Idempotent migration: device_error events (roadmap item G).

Adds billiard_devices.last_error (VARCHAR 255) and last_error_at (timestamp).
Backs up SQLite first. Safe to run twice.
"""
import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

from app.database import engine

COLUMNS = {
    "last_error": "VARCHAR(255)",
    "last_error_at": "TIMESTAMP WITH TIME ZONE" if engine.url.get_backend_name() == "postgresql" else "DATETIME",
}


def main():
    if engine.url.get_backend_name() == "sqlite" and engine.url.database and os.path.exists(engine.url.database):
        backup = f"{engine.url.database}.bak-{datetime.now():%Y%m%d%H%M%S}"
        shutil.copy2(engine.url.database, backup)
        print("backup:", backup)

    existing = {c["name"] for c in inspect(engine).get_columns("billiard_devices")}
    with engine.begin() as conn:
        for name, ddl in COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE billiard_devices ADD COLUMN {name} {ddl}"))
                print(f"added billiard_devices.{name}")
    print("done")


if __name__ == "__main__":
    main()
