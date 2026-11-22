from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

# NOTE: get_db / get_current_user: same imports as app/payments/routes/shift_router.py
from app.database import get_db
from app.user.utils.token import get_current_user
from app.payments.utils.permissions import is_manager

from app.payments.schemas.bank_account import (
    BankAccountCreate,
    BankAccountEventOut,
    BankAccountOut,
    BankAccountRename,
    ParsedBankQrOut,
)
from app.payments.services.bank_account_service import bank_account_service as svc

router = APIRouter(prefix="/payments/bank-accounts", tags=["Payments: bank accounts"])

MAX_QR_BYTES = 5 * 1024 * 1024


def _manager_only(user):
    if not is_manager(user):
        raise HTTPException(403, "Only a manager or admin can change bank accounts")


@router.get("/current", response_model=BankAccountOut | None)
def current(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return svc.get_active(db, user.client_id)


@router.get("", response_model=list[BankAccountOut])
def list_accounts(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _manager_only(user)
    return svc.list_accounts(db, user.client_id)


@router.get("/events", response_model=list[BankAccountEventOut])
def events(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _manager_only(user)
    return svc.list_events(db, user.client_id)


@router.post("", response_model=BankAccountOut, status_code=201)
def create(body: BankAccountCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _manager_only(user)
    acc = svc.create(db, user.client_id, body, user.id)
    db.commit()
    return acc


@router.post("/parse-qr", response_model=ParsedBankQrOut)
async def parse_qr(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Read a bank QR image. Nothing is saved: show the result, let the user confirm, then POST /."""
    _manager_only(user)
    data = await file.read(MAX_QR_BYTES + 1)
    if len(data) > MAX_QR_BYTES:
        raise HTTPException(413, "Image is larger than 5 MB")
    parsed = svc.parse_qr(data)
    return ParsedBankQrOut(
        bank_bin=parsed.bank_bin, account_no=parsed.account_no, amount=parsed.amount, memo=parsed.memo
    )


@router.patch("/{account_id}", response_model=BankAccountOut)
def rename(account_id: int, body: BankAccountRename, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _manager_only(user)
    acc = svc.rename(db, user.client_id, account_id, body, user.id)
    db.commit()
    return acc


@router.post("/{account_id}/deactivate", response_model=BankAccountOut)
def deactivate(account_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _manager_only(user)
    acc = svc.deactivate(db, user.client_id, account_id, user.id)
    db.commit()
    return acc
