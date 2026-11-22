"""Idempotent migration: per-club bank accounts.

Creates payment_bank_accounts and payment_bank_account_events (via create_all),
adds payment_lines.bank_account_id, and seeds one account per club from the old
PAYMENT_BANK_* env values if set (clubs = distinct client_id in payment_orders).
Backs up SQLite first. Safe to run twice.
"""
import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

# NOTE: same imports your other migrate_*.py scripts use
from app.database import Base, engine
from app.payments import config  # same source the app uses (.env is loaded there)
from app.payments.models.bank_account import PaymentBankAccount, PaymentBankAccountEvent  # noqa: F401


def main():
    if engine.url.get_backend_name() == "sqlite" and engine.url.database and os.path.exists(engine.url.database):
        backup = f"{engine.url.database}.bak-{datetime.now():%Y%m%d%H%M%S}"
        shutil.copy2(engine.url.database, backup)
        print("backup:", backup)

    Base.metadata.create_all(
        engine,
        tables=[PaymentBankAccount.__table__, PaymentBankAccountEvent.__table__],
    )

    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("payment_lines")}
    with engine.begin() as conn:
        if "bank_account_id" not in cols:
            conn.execute(text("ALTER TABLE payment_lines ADD COLUMN bank_account_id INTEGER"))
            print("added payment_lines.bank_account_id")

        b_bin = (config.BANK_BIN or "").strip()
        b_no = (config.BANK_ACCOUNT_NO or "").strip()
        if b_bin and b_no:
            clients = [r[0] for r in conn.execute(text("SELECT DISTINCT client_id FROM payment_orders"))]
            for cid in clients:
                exists = conn.execute(
                    text("SELECT 1 FROM payment_bank_accounts WHERE client_id=:c"), {"c": cid}
                ).first()
                taken = conn.execute(
                    text("SELECT 1 FROM payment_bank_accounts WHERE bank_bin=:b AND account_no=:n AND is_active=1"),
                    {"b": b_bin, "n": b_no},
                ).first()
                if exists or taken:
                    continue  # one active row per real account: the first club keeps it
                conn.execute(
                    text(
                        "INSERT INTO payment_bank_accounts "
                        "(client_id, bank_bin, bank_code, account_no, account_name, is_active) "
                        "VALUES (:c, :b, :code, :n, :name, 1)"
                    ),
                    {
                        "c": cid, "b": b_bin, "n": b_no,
                        "code": config.BANK_CODE or None,
                        "name": config.BANK_ACCOUNT_NAME or "Account",
                    },
                )
                print("seeded club", cid)
    print("done")


if __name__ == "__main__":
    main()