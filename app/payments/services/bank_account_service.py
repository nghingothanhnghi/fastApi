"""Per-club receiving bank accounts. Services flush; the router commits."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.payments.models.bank_account import PaymentBankAccount, PaymentBankAccountEvent
from app.payments.schemas.bank_account import BankAccountCreate, BankAccountRename
from app.payments.utils.qr_image import QrReaderUnavailable, decode_qr
from app.payments.utils.vietqr_parser import ParsedBankQr, parse_vietqr


class BankAccountService:
    # ---- reads -------------------------------------------------------------
    @staticmethod
    def get_active(db: Session, client_id: int) -> PaymentBankAccount | None:
        return db.scalar(
            select(PaymentBankAccount).where(
                PaymentBankAccount.client_id == client_id, PaymentBankAccount.is_active.is_(True)
            )
        )

    @staticmethod
    def active_id(db: Session, client_id: int) -> int | None:
        acc = BankAccountService.get_active(db, client_id)
        return acc.id if acc else None

    @staticmethod
    def list_accounts(db: Session, client_id: int) -> list[PaymentBankAccount]:
        return list(
            db.scalars(
                select(PaymentBankAccount)
                .where(PaymentBankAccount.client_id == client_id)
                .order_by(PaymentBankAccount.id.desc())
            )
        )

    @staticmethod
    def _get(db: Session, client_id: int, account_id: int) -> PaymentBankAccount:
        acc = db.get(PaymentBankAccount, account_id)
        if not acc or acc.client_id != client_id:  # 404, never 403, for other tenants
            raise HTTPException(404, "Bank account not found")
        return acc

    @staticmethod
    def list_events(db: Session, client_id: int, limit: int = 100) -> list[PaymentBankAccountEvent]:
        return list(
            db.scalars(
                select(PaymentBankAccountEvent)
                .where(PaymentBankAccountEvent.client_id == client_id)
                .order_by(PaymentBankAccountEvent.id.desc())
                .limit(limit)
            )
        )

    # ---- writes ------------------------------------------------------------
    @staticmethod
    def _log(db: Session, client_id: int, account_id: int | None, event: str, actor_id: int | None, data=None):
        db.add(
            PaymentBankAccountEvent(
                client_id=client_id, account_id=account_id, event_type=event, actor_id=actor_id, data=data
            )
        )

    @staticmethod
    def create(db: Session, client_id: int, body: BankAccountCreate, actor_id: int | None) -> PaymentBankAccount:
        duplicate = db.scalar(
            select(PaymentBankAccount).where(
                PaymentBankAccount.bank_bin == body.bank_bin,
                PaymentBankAccount.account_no == body.account_no,
                PaymentBankAccount.is_active.is_(True),
            )
        )
        if duplicate:
            raise HTTPException(409, "This bank account is already in use")

        old = BankAccountService.get_active(db, client_id)
        if old:
            old.is_active = False
            db.flush()  # free the one-active-per-club slot before inserting

        acc = PaymentBankAccount(
            client_id=client_id,
            bank_bin=body.bank_bin,
            bank_code=(body.bank_code or None) and body.bank_code.upper(),
            account_no=body.account_no,
            account_name=body.account_name,
            is_active=True,
            created_by_id=actor_id,
        )
        db.add(acc)
        try:
            db.flush()
        except IntegrityError:
            raise HTTPException(409, "This bank account is already in use")

        if old:
            BankAccountService._log(db, client_id, acc.id, "account_replaced", actor_id, {"old_id": old.id})
        else:
            BankAccountService._log(db, client_id, acc.id, "account_created", actor_id)
        return acc

    @staticmethod
    def rename(db: Session, client_id: int, account_id: int, body: BankAccountRename, actor_id: int | None):
        acc = BankAccountService._get(db, client_id, account_id)
        before = {"account_name": acc.account_name, "bank_code": acc.bank_code}
        acc.account_name = body.account_name
        if body.bank_code is not None:
            acc.bank_code = body.bank_code.upper() or None
        db.flush()
        BankAccountService._log(db, client_id, acc.id, "account_renamed", actor_id, before)
        return acc

    @staticmethod
    def deactivate(db: Session, client_id: int, account_id: int, actor_id: int | None):
        acc = BankAccountService._get(db, client_id, account_id)
        if acc.is_active:
            acc.is_active = False
            db.flush()
            BankAccountService._log(db, client_id, acc.id, "account_deactivated", actor_id)
        return acc

    # ---- QR upload (parse only, nothing saved) -----------------------------
    @staticmethod
    def parse_qr(image_bytes: bytes) -> ParsedBankQr:
        try:
            return parse_vietqr(decode_qr(image_bytes))
        except QrReaderUnavailable as exc:
            raise HTTPException(501, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))


bank_account_service = BankAccountService()
