# app/payments/routes/shift_router.py  (HTTP only; rules live in shift_service)
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.user.models.user import User
from app.user.utils.token import get_current_user
from app.payments.schemas.shift import (
    CashMovementRequest, CloseShiftRequest, OpenShiftRequest, ShiftResponse, ShiftSummary,
)
from app.payments.services.shift_service import shift_service

router = APIRouter(prefix="/payments/shifts", tags=["Payments - Shifts"])


@router.post("/open", response_model=ShiftSummary, status_code=201)
def open_shift(
    request: OpenShiftRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Start a shift with an opening float. `409` if a shift is already open."""
    shift = shift_service.open_shift(db, current_user, request.opening_float, request.note)
    db.commit()
    db.refresh(shift)
    return shift_service.summary(db, shift)


@router.get("/current", response_model=Optional[ShiftSummary])
def current_shift(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The open shift with live drawer totals, or null when none is open."""
    if not current_user.client_id:
        return None
    shift = shift_service.get_open_shift(db, current_user.client_id)
    return shift_service.summary(db, shift) if shift else None


@router.get("", response_model=list[ShiftResponse])
def list_shifts(
    limit: int = Query(30, ge=1, le=200), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return [shift_service.to_response(s) for s in shift_service.list_shifts(db, current_user, limit, offset)]


@router.get("/{shift_id}", response_model=ShiftSummary)
def get_shift(shift_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return shift_service.summary(db, shift_service.get_shift(db, shift_id, current_user))


@router.post("/{shift_id}/movements", response_model=ShiftSummary, status_code=201)
def add_movement(
    shift_id: int, request: CashMovementRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Record cash put into (pay_in) or taken out of (pay_out) the drawer, with a reason."""
    shift = shift_service.add_movement(
        db, shift_id, current_user, request.type, request.amount, request.reason
    )
    db.commit()
    db.refresh(shift)
    return shift_service.summary(db, shift)


@router.post("/{shift_id}/close", response_model=ShiftSummary)
def close_shift(
    shift_id: int, request: CloseShiftRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Close the shift with the counted cash. Returns expected vs counted and the variance."""
    shift = shift_service.close_shift(db, shift_id, current_user, request.counted_cash, request.note)
    db.commit()
    db.refresh(shift)
    return shift_service.summary(db, shift)
