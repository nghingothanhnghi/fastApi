# migrate_payments_orders.py
#   python migrate_payments_orders.py
# Moves an existing database to the Payments-module layout. Idempotent. SQLite and PostgreSQL.
#
# What changed: payment lines, the audit trail, cash shifts and the bank feed now belong to the
# Payments module and are keyed by (source_type, source_id) instead of a billiard session id.
#
#   old (billiard)                       new (payments)
#   session_payments                 ->  payment_lines   (child of payment_orders)
#   session_payment_events           ->  payment_events
#   (new)                                payment_orders
#   bank_transactions.session_id     ->  bank_transactions.order_id
#   cash_shifts / cash_movements         unchanged (same tables, now owned by payments)
#   table_sessions                       + payment_order_id
#
# DEMO DATA ONLY: the old payment lines / events / bank transactions are DELETED, not converted.
# Sessions that were already PAID keep their paid state and still show as paid (the bill treats a
# paid session without an order as settled). Sessions left PENDING by a deleted line are reset to
# UNPAID so the cashier can take payment again. Do not run this on a database whose old payment
# lines you need to keep.
import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

import app.init_db  # noqa: F401  registers all models
from app.database import Base, engine
from app.payments.models import bank_transaction, order, shift  # noqa: F401

PG = engine.url.get_backend_name() == "postgresql"

PAYMENT_TABLES = [
    order.PaymentOrder.__table__, order.PaymentLine.__table__, order.PaymentEvent.__table__,
    shift.CashShift.__table__, shift.CashMovement.__table__, bank_transaction.BankTransaction.__table__,
]
# Dropped children first. CASCADE is PostgreSQL only; SQLite has no FK enforcement here.
LEGACY_TABLES = ["session_payment_events", "session_payments"]
# PostgreSQL enum types that only the dropped table used.
LEGACY_ENUMS = ["sessionpaymentstatus"]


def backup_sqlite():
    if engine.url.get_backend_name() != "sqlite":
        print("Non-SQLite DB: take your own backup first.")
        return
    f = engine.url.database
    if f and os.path.exists(f):
        b = f"{f}.bak_{datetime.now():%Y%m%d_%H%M%S}"
        shutil.copy2(f, b)
        print(f"Backup written: {b}")


def columns(table):
    insp = inspect(engine)
    return [c["name"] for c in insp.get_columns(table)] if insp.has_table(table) else []


def row_count(conn, table):
    return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def drop_legacy(conn):
    cascade = " CASCADE" if PG else ""
    # bank_transactions changed shape (session_id -> order_id): drop the old one so it is recreated.
    stale_bank = "bank_transactions" in inspect(engine).get_table_names() and "order_id" not in columns("bank_transactions")
    for table in (["bank_transactions"] if stale_bank else []) + LEGACY_TABLES:
        if not inspect(engine).has_table(table):
            print(f"{table}: not present")
            continue
        n = row_count(conn, table)
        conn.execute(text(f"DROP TABLE {table}{cascade}"))
        print(f"{table}: dropped ({n} demo rows deleted)")
    if PG:
        for enum in LEGACY_ENUMS:
            conn.execute(text(f"DROP TYPE IF EXISTS {enum}"))


def add_order_column(conn):
    if "payment_order_id" in columns("table_sessions"):
        print("table_sessions.payment_order_id: exists")
        return
    conn.execute(text(
        "ALTER TABLE table_sessions ADD COLUMN payment_order_id INTEGER "
        "REFERENCES payment_orders(id) ON DELETE SET NULL"
    ))
    print("table_sessions.payment_order_id: added")


def reset_orphan_pending(conn):
    """A PENDING session whose payment lines were deleted can never settle: let the cashier retry."""
    result = conn.execute(text(
        "UPDATE table_sessions SET payment_state = 'unpaid', payment_method = NULL, "
        "payment_id = NULL, payment_reference = NULL "
        "WHERE payment_state = 'pending' AND payment_order_id IS NULL"
    ))
    print(f"table_sessions: {result.rowcount} orphaned pending sessions reset to unpaid")


def main():
    backup_sqlite()
    with engine.begin() as conn:
        drop_legacy(conn)
    Base.metadata.create_all(bind=engine, tables=PAYMENT_TABLES, checkfirst=True)
    print("payment tables ready: " + ", ".join(t.name for t in PAYMENT_TABLES))
    with engine.begin() as conn:
        add_order_column(conn)
        reset_orphan_pending(conn)
    print("Migration completed.")


if __name__ == "__main__":
    main()
