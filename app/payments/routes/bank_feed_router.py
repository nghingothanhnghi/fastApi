# app/payments/routes/bank_feed_router.py
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.payments import config
from app.payments.schemas.bank_feed import (
    AssignBankTransactionRequest, BankTransactionResponse, IgnoreBankTransactionRequest,
)
from app.payments.services.bank_feed_service import bank_feed_service
from app.payments.utils.sepay import SepayAuthError, SepayNotConfigured, verify_request
from app.database import get_db
from app.user.models.user import User
from app.user.utils.token import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments/bank-feed", tags=["Payments - Bank Feed"])


async def _raw_body(request: Request) -> bytes:
    # HMAC is computed over the exact bytes SePay sent, so read the body unparsed.
    return await request.body()


@router.post("/sepay")
def sepay_webhook(request: Request, body: bytes = Depends(_raw_body), db: Session = Depends(get_db)):
    """SePay webhook: a transfer reached the receiving bank account.

    Authenticated by HMAC-SHA256 (SEPAY_WEBHOOK_SECRET) or an API key (SEPAY_API_KEY).
    Always answers {"success": true} once the transaction is stored, even if it could not be
    matched: SePay retries for hours on anything else, and unmatched money is kept for a manager.
    """
    try:
        verify_request(
            request.headers, body,
            secret=config.SEPAY_WEBHOOK_SECRET, api_key=config.SEPAY_API_KEY,
            tolerance_seconds=config.SEPAY_TIMESTAMP_TOLERANCE_SECONDS,
        )
    except SepayNotConfigured:
        raise HTTPException(503, "SePay webhook is not configured")
    except SepayAuthError as e:
        raise HTTPException(401, str(e))

    try:
        payload = json.loads(body)
        tx, duplicate = bank_feed_service.process_sepay(db, payload)
    except ValueError as e:                       # bad JSON / missing id / bad amount
        raise HTTPException(400, str(e))
    logger.info("SePay tx %s -> %s%s", tx.external_id, tx.status, " (duplicate)" if duplicate else "")
    return {"success": True}


@router.get("/transactions", response_model=list[BankTransactionResponse])
def list_transactions(
    status: Optional[str] = Query(None, description="matched | unmatched | needs_review | ignored"),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Manager: bank transactions, e.g. `?status=needs_review` for money that needs a decision."""
    return bank_feed_service.list_transactions(db, current_user, status, limit, offset)


@router.post("/transactions/{tx_id}/assign", response_model=BankTransactionResponse)
def assign_transaction(
    tx_id: int, request: AssignBankTransactionRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Manager: link a transaction to a pending transfer line (exact amount only) and confirm it."""
    return bank_feed_service.assign(db, tx_id, request.line_id, current_user)


@router.post("/transactions/{tx_id}/ignore", response_model=BankTransactionResponse)
def ignore_transaction(
    tx_id: int, request: IgnoreBankTransactionRequest | None = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Manager: dismiss a transaction (e.g. a refund was made, or it is not a bill payment)."""
    return bank_feed_service.ignore(db, tx_id, current_user, request.note if request else None)
