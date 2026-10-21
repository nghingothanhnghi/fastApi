# app/payments/services/shift_service.py
# Shifts and the cash drawer. This service does NOT commit; the router commits.
#
# Expected cash in the drawer for a shift window [opened_at, closed_at or now]:
#   opening_float
#   + cash lines confirmed in the window          (net of change: line.amount, not tendered)
#   - cash lines voided in the window             (cash handed back, even if received in an earlier shift)
#   + pay-ins - pay-outs
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.payments.models.order import PaymentLine, PaymentLineStatus, PaymentOrder
from app.payments.models.shift import CashMovement, CashShift, MovementType, ShiftStatus
from app.payments.schemas.shift import (
    CashMovementResponse, MethodTotals, ShiftResponse, ShiftSummary,
)
from app.payments.utils.money import CENT, ZERO
from app.payments.utils.permissions import is_manager
from app.user.models.user import User


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes (stored as UTC); PostgreSQL returns aware ones."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _client_id(user: User) -> str:
    if not user.client_id:
        raise HTTPException(400, "User has no client; cannot use the cash drawer")
    return user.client_id


class ShiftService:

    # ---------------------------------------------------------------- lookup

    @staticmethod
    def get_open_shift(db: Session, client_id: str) -> Optional[CashShift]:
        return db.execute(
            select(CashShift).where(CashShift.client_id == client_id, CashShift.status == ShiftStatus.OPEN)
        ).scalar_one_or_none()

    @staticmethod
    def get_shift(db: Session, shift_id: int, user: User) -> CashShift:
        shift = db.get(CashShift, shift_id)
        # 404 (not 403) for other tenants: don't leak that the id exists
        if not shift or (not user.is_super_admin() and shift.client_id != user.client_id):
            raise HTTPException(404, "Shift not found")
        return shift

    @staticmethod
    def list_shifts(db: Session, user: User, limit: int = 30, offset: int = 0) -> list[CashShift]:
        q = select(CashShift).order_by(CashShift.id.desc()).limit(limit).offset(offset)
        if not user.is_super_admin():
            q = q.where(CashShift.client_id == user.client_id)
        return list(db.execute(q).scalars())

    @staticmethod
    def require_open_shift(db: Session, user: User) -> None:
        if ShiftService.get_open_shift(db, _client_id(user)) is None:
            raise HTTPException(409, "Open a shift before taking payments")

    # ------------------------------------------------------------- lifecycle

    @staticmethod
    def open_shift(db: Session, user: User, opening_float: Decimal, note: Optional[str]) -> CashShift:
        client_id = _client_id(user)
        if ShiftService.get_open_shift(db, client_id) is not None:
            raise HTTPException(409, "A shift is already open")
        shift = CashShift(
            client_id=client_id, status=ShiftStatus.OPEN, opened_at=_now(),
            opening_float=Decimal(opening_float).quantize(CENT), note=note, opened_by_id=user.id,
        )
        db.add(shift)
        try:
            db.flush()                       # uq_one_open_shift_per_client guards a race
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "A shift is already open")
        return shift

    @staticmethod
    def add_movement(
        db: Session, shift_id: int, user: User, kind: str, amount: Decimal, reason: str,
    ) -> CashShift:
        shift = ShiftService.get_shift(db, shift_id, user)
        if shift.status != ShiftStatus.OPEN:
            raise HTTPException(409, "Shift is closed")
        amount = Decimal(amount).quantize(CENT)
        if kind == MovementType.PAY_OUT.value:
            available = ShiftService._totals(db, shift)["expected_cash"]
            if amount > available:
                raise HTTPException(409, f"Pay-out {amount} is more than the cash in the drawer ({available})")
        shift.movements.append(CashMovement(
            type=MovementType(kind), amount=amount, reason=reason.strip(),
            created_by_id=user.id, created_at=_now(),
        ))
        db.flush()
        return shift

    @staticmethod
    def close_shift(
        db: Session, shift_id: int, user: User, counted_cash: Decimal, note: Optional[str],
    ) -> CashShift:
        shift = ShiftService.get_shift(db, shift_id, user)
        if shift.status != ShiftStatus.OPEN:
            raise HTTPException(409, "Shift is already closed")
        if shift.opened_by_id != user.id and not is_manager(user):
            raise HTTPException(403, "Only the cashier who opened the shift or a manager can close it")

        closed_at = _now()
        expected = ShiftService._totals(db, shift, until=closed_at)["expected_cash"]
        counted = Decimal(counted_cash).quantize(CENT)
        shift.status = ShiftStatus.CLOSED
        shift.closed_at = closed_at
        shift.closed_by_id = user.id
        shift.expected_cash = expected
        shift.counted_cash = counted
        shift.variance = (counted - expected).quantize(CENT)
        shift.close_note = note
        db.flush()
        return shift

    # --------------------------------------------------------------- numbers

    @staticmethod
    def _lines(db: Session, shift: CashShift, until: Optional[datetime]):
        """(received, voided) payment lines of this club inside the shift window."""
        end = until or shift.closed_at or _now()
        base = (
            select(PaymentLine)
            .join(PaymentOrder, PaymentOrder.id == PaymentLine.order_id)
            .where(PaymentOrder.client_id == shift.client_id)
        )
        received = list(db.execute(base.where(
            PaymentLine.status.in_((PaymentLineStatus.COMPLETED, PaymentLineStatus.VOIDED)),
            PaymentLine.confirmed_at >= shift.opened_at, PaymentLine.confirmed_at <= end,
        )).scalars())
        voided = list(db.execute(base.where(
            PaymentLine.status == PaymentLineStatus.VOIDED,
            PaymentLine.voided_at >= shift.opened_at, PaymentLine.voided_at <= end,
        )).scalars())
        return received, voided

    @staticmethod
    def _totals(db: Session, shift: CashShift, until: Optional[datetime] = None) -> dict:
        received, voided = ShiftService._lines(db, shift, until)
        end = until or shift.closed_at
        movements = [m for m in shift.movements if end is None or _aware(m.created_at) <= _aware(end)]

        def total(lines, method=None):
            return sum((l.amount for l in lines if method is None or l.method == method), ZERO)

        cash_sales, cash_voids = total(received, "cash"), total(voided, "cash")
        pay_ins = sum((m.amount for m in movements if m.type == MovementType.PAY_IN), ZERO)
        pay_outs = sum((m.amount for m in movements if m.type == MovementType.PAY_OUT), ZERO)
        methods = []
        for method in sorted({l.method for l in received} | {l.method for l in voided}):
            rec = [l for l in received if l.method == method]
            r_total, v_total = total(rec), total(voided, method)
            methods.append(MethodTotals(
                method=method, received_count=len(rec), received_total=r_total,
                voided_total=v_total, net_total=r_total - v_total,
            ))
        return {
            "cash_sales": cash_sales, "cash_voids": cash_voids, "pay_ins": pay_ins, "pay_outs": pay_outs,
            "change_given": sum((l.change_given or ZERO for l in received if l.method == "cash"), ZERO),
            "payments_count": len(received),
            "methods": methods,
            "movements": movements,
            "expected_cash": (shift.opening_float + cash_sales - cash_voids + pay_ins - pay_outs).quantize(CENT),
        }

    @staticmethod
    def to_response(shift: CashShift) -> ShiftResponse:
        return ShiftResponse(
            id=shift.id, status=shift.status.value, opened_at=shift.opened_at, closed_at=shift.closed_at,
            opening_float=shift.opening_float, expected_cash=shift.expected_cash,
            counted_cash=shift.counted_cash, variance=shift.variance, note=shift.note,
            close_note=shift.close_note,
            opened_by=shift.opened_by.username if shift.opened_by else None,
            closed_by=shift.closed_by.username if shift.closed_by else None,
        )

    @staticmethod
    def summary(db: Session, shift: CashShift) -> ShiftSummary:
        t = ShiftService._totals(db, shift)
        base = ShiftService.to_response(shift).model_dump()
        # Open shift: show the live expected cash. Closed: keep the frozen value.
        if shift.status == ShiftStatus.OPEN:
            base["expected_cash"] = t["expected_cash"]
        return ShiftSummary(
            **base,
            cash_sales=t["cash_sales"], cash_voids=t["cash_voids"],
            pay_ins=t["pay_ins"], pay_outs=t["pay_outs"], change_given=t["change_given"],
            payments_count=t["payments_count"], methods=t["methods"],
            movements=[
                CashMovementResponse(
                    id=m.id, type=m.type.value, amount=m.amount, reason=m.reason,
                    created_by=m.created_by.username if m.created_by else None, created_at=m.created_at,
                ) for m in t["movements"]
            ],
        )


shift_service = ShiftService()
