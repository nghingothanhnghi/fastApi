# migrate_billiard_phase1.py
#   python migrate_billiard_phase1.py
# Idempotent. Works on SQLite and PostgreSQL.
#  1. backs up SQLite
#  2. creates the new tables (checkfirst)
#  3. adds new columns to billiard_tables / table_sessions
#  4. PostgreSQL only: new enum values, nullable audit columns, ON DELETE rules
# SQLite cannot ALTER a column to nullable or change an FK. App DB has foreign_keys
# OFF (no PRAGMA in app/database.py) so ON DELETE never fires there anyway; rebuild the
# DB from models if you need the exact schema on SQLite.
import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

import app.init_db  # noqa: F401  registers all models
from app.database import Base, engine
from app.billiard import models as bm

PG = engine.url.get_backend_name() == "postgresql"
TS = "TIMESTAMP WITH TIME ZONE" if PG else "DATETIME"
TRUE = "TRUE" if PG else "1"

NEW_TABLES = [
    bm.BilliardPackage, bm.BilliardPackageItem, bm.PricingRule, bm.TableGame,
    bm.BilliardDevice, bm.DeviceEvent, bm.DeviceLocalIdMap,
]

# (table, column, ddl)
NEW_COLUMNS = [
    ("billiard_tables", "is_active", f"BOOLEAN NOT NULL DEFAULT {TRUE}"),
    ("billiard_tables", "updated_at", TS),
    ("table_sessions", "start_time_source", "VARCHAR(10) NOT NULL DEFAULT 'server'"),
    ("table_sessions", "end_time_source", "VARCHAR(10) NOT NULL DEFAULT 'server'"),
    ("table_sessions", "ends_at", TS),
    ("table_sessions", "pricing_snapshot", "JSON"),
    ("table_sessions", "package_id", "INTEGER REFERENCES billiard_packages(id) ON DELETE SET NULL"),
    ("table_sessions", "package_name", "VARCHAR(100)"),
    ("table_sessions", "package_price", "NUMERIC(12,2)"),
    ("table_sessions", "discount", "NUMERIC(12,2) NOT NULL DEFAULT 0"),
]

# (table, column, referenced table, ondelete, make_nullable)
FK_RULES = [
    ("table_sessions", "table_id", "billiard_tables", "RESTRICT", False),
    ("table_sessions", "opened_by_id", "users", "SET NULL", True),
    ("table_sessions", "stopped_by_id", "users", "SET NULL", False),
    ("table_sessions", "paid_by_id", "users", "SET NULL", False),
    ("table_sessions", "payment_id", "payment_transactions", "SET NULL", False),
    ("session_items", "session_id", "table_sessions", "CASCADE", False),
    ("session_items", "product_id", "products", "SET NULL", True),
    ("session_items", "variant_id", "product_variants", "SET NULL", False),
    ("session_items", "added_by_id", "users", "SET NULL", True),
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
        c.execute(text("ALTER TYPE tablestatus ADD VALUE IF NOT EXISTS 'maintenance'"))
        c.execute(text("ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'cancelled'"))
    print("enums: maintenance / cancelled ensured")


def apply_fk_rules(conn):
    if not PG:
        print("SQLite: skipping ON DELETE / nullable changes (see header note)")
        return
    insp = inspect(conn)
    for table, col, ref, ondelete, nullable in FK_RULES:
        if nullable:
            conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN {col} DROP NOT NULL"))
        for fk in insp.get_foreign_keys(table):
            if fk["constrained_columns"] == [col]:
                if (fk.get("options") or {}).get("ondelete", "").upper() == ondelete:
                    break
                conn.execute(text(f'ALTER TABLE {table} DROP CONSTRAINT "{fk["name"]}"'))
                conn.execute(text(
                    f"ALTER TABLE {table} ADD FOREIGN KEY ({col}) "
                    f"REFERENCES {ref}(id) ON DELETE {ondelete}"))
                print(f"{table}.{col}: ON DELETE {ondelete}")
                break


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
        # Fails loudly if a tenant already has duplicate table names: fix data, re-run.
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_billiard_table_name_per_client "
            "ON billiard_tables (client_id, name)"))
        apply_fk_rules(conn)
    print("Migration completed.")


if __name__ == "__main__":
    main()