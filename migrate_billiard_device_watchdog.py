"""Idempotent migration: offline heartbeat job (roadmap item H).

Adds billiard_devices.status_changed_at and creates billiard_device_status_log.
Backs up SQLite first. Safe to run twice.
"""
import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

import app.billiard.models  # noqa: F401  (registers the tables)
from app.billiard.models import DeviceStatusLog
from app.database import engine

TS = "TIMESTAMP WITH TIME ZONE" if engine.url.get_backend_name() == "postgresql" else "DATETIME"


def main():
    if engine.url.get_backend_name() == "sqlite" and engine.url.database and os.path.exists(engine.url.database):
        backup = f"{engine.url.database}.bak-{datetime.now():%Y%m%d%H%M%S}"
        shutil.copy2(engine.url.database, backup)
        print("backup:", backup)

    insp = inspect(engine)
    if "status_changed_at" not in {c["name"] for c in insp.get_columns("billiard_devices")}:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE billiard_devices ADD COLUMN status_changed_at {TS}"))
        print("added billiard_devices.status_changed_at")

    if not insp.has_table("billiard_device_status_log"):
        DeviceStatusLog.__table__.create(bind=engine)
        print("created billiard_device_status_log")
    print("done")


if __name__ == "__main__":
    main()
