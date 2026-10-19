# migrate_billiard_shifts.py
#   python migrate_billiard_shifts.py
# Idempotent. Works on SQLite and PostgreSQL.
#  1. backs up SQLite
#  2. creates cash_shifts / cash_movements (checkfirst)
#  3. adds voided_at / voided_by_id / void_reason to session_payments
#  4. PostgreSQL only: adds the 'voided' value to the session payment status enum
import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

import app.init_db  # noqa: F401  registers all models
from app.database import Base, engine
from app.billiard import models as bm

PG = engine.url.get_backend_name() == "postgresql"
TS = "TIMESTAMP WITH TIME ZONE" if PG else "DATETIME"

NEW_TABLES = [bm.CashShift, bm.CashMovement]

# (table, column, ddl)
NEW_COLUMNS = [
    ("session_payments", "voided_at", TS),
    ("session_payments", "voided_by_id", "INTEGER REFERENCES users(id) ON DELETE SET NULL"),
    ("session_payments", "void_reason", "VARCHAR(255)"),
]


def backup_sqlite():
    if engine.url.get_backend_name() != "sqlite":
        print("Non-SQLite DB: take your own backup first.")
        return
    f = engine.url.database
    if f and os.path.exists(f):
        b = f"{f}.bak_{datetime.now():%Y%m%d_%H%M%S}"
        shutil.copy2(f, b)
        print(f"Backup written: {b}")


def has_column(table, col):
    return col in [c["name"] for c in inspect(engine).get_columns(table)]


def add_enum_values():
    if not PG:
        return
    # ALTER TYPE ... ADD VALUE must be committed before the value is used.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(text("ALTER TYPE sessionpaymentstatus ADD VALUE IF NOT EXISTS 'voided'"))
    print("enum: sessionpaymentstatus 'voided' ensured")


def main():
    backup_sqlite()
    add_enum_values()
    Base.metadata.create_all(bind=engine, tables=[m.__table__ for m in NEW_TABLES], checkfirst=True)
    print("new tables ready")
    with engine.begin() as conn:
        for table, col, ddl in NEW_COLUMNS:
            if has_column(table, col):
                print(f"{table}.{col}: exists")
            else:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
                print(f"{table}.{col}: added")
    print("Migration completed.")


if __name__ == "__main__":
    main()
