# app/payments/services/order_service.py
# Takes payment for any business object that has a registered PayableAdapter
# (see payable_registry.py). A bill (PaymentOrder) is paid by one or more lines (PaymentLine):
# cash, bank transfer (VietQR), or a single Stripe gateway payment. Each cash/transfer line is
# backed by a PaymentTransaction created through the manual provider.
#
# NOTE: unlike most services here, this one commits. The payment providers (manual_service /
# stripe_service) call db.commit() themselves, so a single wrapping transaction is impossible.
# Instead we use a claim pattern:
#   1. lock the business object, then the order; insert the lines, flip the order
#      UNPAID -> PENDING, mirror that onto the business object, commit  (the "claim")
#   2. call the provider per line (concurrent /pay calls now get 409)
#   3. settle: PAID when completed lines cover the total; a transfer line waiting for the
#      cashier / bank feed keeps the order PENDING; if nothing was collected, back to UNPAID
# Anything left half-done is visible on the order (line statuses) and recoverable by
# confirming or cancelling the pending line.
#
# Lock order is always: business object first, then the order. Keep it that way.
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.payments import config
from app.payments.models.order import (
    PaymentEvent, PaymentLine, PaymentLineStatus, PaymentOrder, PaymentOrderState,
)
from app.payments.schemas.order import OrderResponse, PayOrderRequest, PaymentLineResponse
from app.payments.schemas.payment import PaymentStatus, PaymentUpdate
from app.payments.services.payable_registry import PayableAdapter, Quote, payable_registry
from app.payments.services.payment_service import payment_service
from app.payments.services.provider_registry import payment_provider_registry
from app.payments.services.shift_service import shift_service
from app.payments.utils.money import CENT, ZERO
from app.payments.utils.permissions import is_manager
from app.payments.utils.vietqr import build_transfer_instruction, make_memo
from app.user.models.user import User

logger = logging.getLogger(__name__)

LineStatus = PaymentLineStatus
OrderState = PaymentOrderState


@dataclass
class LineSpec:
    method: str
    amount: Decimal
    cash_tendered: Optional[Decimal] = None
    note: Optional[str] = None


def _split(result):
    """manual -> PaymentOut ; stripe -> {"payment": PaymentOut, "stripe": {...}}"""
    if isinstance(result, dict):
        return result["payment"], result.get("stripe")
    return result, None


def _is_completed(payment) -> bool:
    return getattr(payment.status, "value", payment.status) == "completed"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid(user: Optional[User]) -> Optional[int]:
    """None = the system (e.g. the bank feed confirmed a transfer automatically)."""
    return user.id if user else None


def _log(db: Session, order_id: int, event_type: str, actor_id: Optional[int],
         line_id: Optional[int] = None, data: Optional[dict] = None) -> None:
    db.add(PaymentEvent(
        order_id=order_id, line_id=line_id, event_type=event_type, actor_id=actor_id, data=data,
    ))


def _amount_paid(order: PaymentOrder) -> Decimal:
    return sum((p.amount for p in order.lines if p.status == LineStatus.COMPLETED), ZERO)


def _balance_due(order: PaymentOrder) -> Decimal:
    return (order.total - _amount_paid(order)).quantize(CENT)


def _method_label(order: PaymentOrder) -> Optional[str]:
    methods = {p.method for p in order.lines if p.status in (LineStatus.COMPLETED, LineStatus.PENDING)}
    if not methods:
        return None
    return methods.pop() if len(methods) == 1 else "split"


def _mark_paid(order: PaymentOrder, user: Optional[User]) -> None:
    order.state = OrderState.PAID
    order.paid_at = _now()
    order.paid_by_id = _uid(user)


def _find_line(order: PaymentOrder, line_id: int) -> PaymentLine:
    line = next((p for p in order.lines if p.id == line_id), None)
    if not line:
        raise HTTPException(404, "Payment line not found")
    return line


def _specs(request: PayOrderRequest, balance: Decimal) -> list[LineSpec]:
    if request.payments:
        return [
            LineSpec(p.method, Decimal(p.amount).quantize(CENT), p.cash_tendered, p.note)
            for p in request.payments
        ]
    return [LineSpec(request.payment_method, balance, request.cash_tendered)]


def _validate_specs(specs: list[LineSpec], balance: Decimal) -> None:
    total = sum((s.amount for s in specs), ZERO).quantize(CENT)
    if total != balance:
        raise HTTPException(422, f"Payment lines add up to {total} but the amount due is {balance}")
    for s in specs:
        if s.method == "cash":
            tendered = s.cash_tendered if s.cash_tendered is not None else s.amount
            if tendered < s.amount:
                raise HTTPException(422, f"Cash tendered {tendered} is less than the cash amount {s.amount}")


def _settle(db: Session, order: PaymentOrder, adapter: PayableAdapter, obj: Any, actor: Optional[User]) -> None:
    """Derive the order state from its lines and mirror it onto the business object. Caller commits."""
    open_lines = [p for p in order.lines if p.status == LineStatus.PENDING]
    completed = [p for p in order.lines if p.status == LineStatus.COMPLETED]
    order.method = _method_label(order)

    if completed:
        order.payment_id = completed[0].payment_id
        order.payment_reference = completed[0].payment_reference

    was_paid = order.state == OrderState.PAID
    if not open_lines and _balance_due(order) <= 0:
        if not was_paid:
            _mark_paid(order, actor)
            _log(db, order.id, "order_paid", _uid(actor),
                 data={"amount": str(order.total), "method": order.method})
    else:
        if was_paid:                   # a void took money back: the order is no longer settled
            order.paid_at = None
            order.paid_by_id = None
        if not open_lines and not completed:
            # Nothing collected and nothing waiting: let the cashier start over.
            order.state = OrderState.UNPAID
            order.method = None
            order.payment_id = None
            order.payment_reference = None
        else:
            order.state = OrderState.PENDING
    adapter.apply_state(db, obj, order)


class PaymentOrderService:

    # ---------------------------------------------------------------- lookup

    @staticmethod
    def get_order(db: Session, source_type: str, source_id: str, *, lock: bool = False) -> Optional[PaymentOrder]:
        q = select(PaymentOrder).where(
            PaymentOrder.source_type == source_type, PaymentOrder.source_id == str(source_id)
        )
        if lock:
            q = q.with_for_update()
        return db.execute(q).scalar_one_or_none()

    @staticmethod
    def _get_or_create(db: Session, source_type: str, source_id: str, quote: Quote) -> PaymentOrder:
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        if order is None:
            order = PaymentOrder(
                client_id=quote.client_id, source_type=source_type, source_id=source_id,
                currency=quote.currency, total=quote.total, state=OrderState.UNPAID,
            )
            db.add(order)
            try:
                db.flush()
            except IntegrityError:           # two first payments raced; the other one wins
                db.rollback()
                raise HTTPException(409, "A payment for this order is already being set up; try again")
        else:
            order.total = quote.total        # the business is the source of truth for the amount
            order.currency = quote.currency
        return order

    # ------------------------------------------------------------------ pay

    @staticmethod
    def pay(db: Session, source_type: str, source_id: str, request: PayOrderRequest, user: User):
        """Returns (order, gateway). `gateway` is the Stripe payload, None for cash/transfer."""
        source_id = str(source_id)
        adapter = payable_registry.get(source_type)
        obj = adapter.load(db, source_id, user, lock=True)
        adapter.check_payable(obj)
        quote = adapter.quote(obj)
        if quote.total <= 0:
            raise HTTPException(409, "Nothing to pay")

        order = PaymentOrderService._get_or_create(db, source_type, source_id, quote)
        if order.state == OrderState.PAID:
            raise HTTPException(409, "Already paid")
        if config.REQUIRE_OPEN_SHIFT:
            shift_service.require_open_shift(db, user)

        if request.payment_method == "stripe":
            return PaymentOrderService._pay_gateway(db, order, adapter, obj, quote, user)

        if order.state == OrderState.PENDING:
            open_lines = [p for p in order.lines if p.status == LineStatus.PENDING]
            if open_lines or not order.lines:
                raise HTTPException(409, "A payment is already in progress")
            # Only completed lines so far (e.g. a transfer was cancelled): pay the rest.

        balance = _balance_due(order)
        if balance <= 0:
            raise HTTPException(409, "Nothing to pay")
        specs = _specs(request, balance)
        _validate_specs(specs, balance)

        # --- phase 1: the claim ---------------------------------------------------
        for s in specs:
            tendered = change = None
            if s.method == "cash":
                tendered = s.cash_tendered if s.cash_tendered is not None else s.amount
                change = (tendered - s.amount).quantize(CENT)
            order.lines.append(PaymentLine(
                method=s.method, amount=s.amount, status=LineStatus.PENDING,
                cash_tendered=tendered, change_given=change, note=s.note, created_by_id=user.id,
            ))
        db.flush()                                   # assign line ids
        for line in order.lines:
            if line.status == LineStatus.PENDING and line.method == "bank_transfer" and not line.transfer_memo:
                line.transfer_memo = make_memo(order.id, line.id)
                line.expires_at = _now() + timedelta(minutes=config.TRANSFER_EXPIRE_MINUTES)
            if line.status == LineStatus.PENDING:
                _log(db, order.id, "line_created", user.id, line.id,
                     {"method": line.method, "amount": str(line.amount)})
        order.state = OrderState.PENDING
        order.method = _method_label(order)
        adapter.apply_state(db, obj, order)

        order_id = order.id
        new_ids = [p.id for p in order.lines if p.status == LineStatus.PENDING and p.payment_id is None]
        db.commit()                                  # expires the instances above

        # --- phase 2: one provider payment per line ---------------------------------
        provider = payment_provider_registry.get_provider("manual")
        failed_at: Optional[int] = None
        for idx, line_id in enumerate(new_ids):
            try:
                line = db.get(PaymentLine, line_id)
                method, amount = line.method, line.amount
                result = provider.create_payment(
                    db,
                    user_id=user.id,
                    client_id=quote.client_id,
                    amount=float(amount),             # PaymentTransaction.amount is Float
                    currency=quote.currency,
                    extra_metadata={
                        **quote.metadata, "payment_order_id": order_id, "method": method, "line_id": line_id,
                    },
                )
                payment, _ = _split(result)
                line = db.get(PaymentLine, line_id)
                line.payment_id = payment.id
                line.payment_reference = payment.reference_id
                auto = method == "cash" or not config.BANK_TRANSFER_REQUIRES_CONFIRMATION
                if auto:
                    provider.confirm_payment(db, payment.reference_id)   # commits
                    line = db.get(PaymentLine, line_id)
                    line.status = LineStatus.COMPLETED
                    line.confirmed_by_id = user.id
                    line.confirmed_at = _now()
                    _log(db, order_id, "cash_received" if method == "cash" else "transfer_confirmed",
                         user.id, line_id, {
                             "amount": str(line.amount),
                             "cash_tendered": str(line.cash_tendered) if line.cash_tendered is not None else None,
                             "change_given": str(line.change_given) if line.change_given is not None else None})
                else:
                    _log(db, order_id, "transfer_awaiting", user.id, line_id,
                         {"amount": str(line.amount), "memo": line.transfer_memo})
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Order %s/%s: recording payment line %s failed", source_type, source_id, line_id)
                failed_at = idx
                break

        if failed_at is not None:
            # Mark the failed line and any not-yet-processed ones so nothing looks "awaiting".
            for line_id in new_ids[failed_at:]:
                line = db.get(PaymentLine, line_id)
                if line is not None and line.status == LineStatus.PENDING and line.payment_id is None:
                    line.status = LineStatus.FAILED
                    _log(db, order_id, "line_failed", user.id, line_id)
            db.commit()

        obj = adapter.load(db, source_id, user, lock=True)
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        _settle(db, order, adapter, obj, user)
        db.commit()

        if failed_at is not None:
            raise HTTPException(500, "Some payment lines could not be recorded; check the order and retry the balance")

        db.refresh(order)
        return order, None

    # --------------------------------------------------------------- gateway

    @staticmethod
    def _pay_gateway(db: Session, order: PaymentOrder, adapter: PayableAdapter, obj: Any,
                     quote: Quote, user: User):
        """Stripe: a single payment for the whole bill, settled later by confirm_gateway."""
        if order.state == OrderState.PENDING:
            raise HTTPException(409, "A payment is already in progress")
        if order.lines:
            raise HTTPException(409, "This order already has cash/transfer payments; pay the balance with those methods")

        source_type, source_id, order_id = order.source_type, order.source_id, order.id
        provider_name = config.PAYMENT_METHODS["stripe"]

        order.state = OrderState.PENDING
        order.method = "stripe"
        adapter.apply_state(db, obj, order)
        db.commit()                           # the claim

        try:
            provider = payment_provider_registry.get_provider(provider_name)
            result = provider.create_payment(
                db,
                user_id=user.id,
                client_id=quote.client_id,
                amount=float(quote.total),    # PaymentTransaction.amount is Float
                currency=quote.currency,
                extra_metadata={**quote.metadata, "payment_order_id": order_id, "method": "stripe"},
            )
            payment, gateway = _split(result)
        except Exception:
            db.rollback()
            PaymentOrderService._release_claim(db, source_type, source_id)
            raise

        try:
            obj = adapter.load(db, source_id, user, lock=True)
            order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
            order.payment_id = payment.id
            order.payment_reference = payment.reference_id
            if _is_completed(payment):
                _mark_paid(order, user)
            adapter.apply_state(db, obj, order)
            db.commit()
        except Exception:
            # Payment exists but bookkeeping failed: reconcile via payment_order_id in its metadata.
            logger.exception("Order %s/%s: payment %s recorded but order update failed",
                             source_type, source_id, getattr(payment, "reference_id", None))
            db.rollback()
            raise

        db.refresh(order)
        return order, gateway

    @staticmethod
    def _release_claim(db: Session, source_type: str, source_id: str) -> None:
        """The provider failed before any payment existed: let the cashier retry."""
        adapter = payable_registry.get(source_type)
        obj = adapter.load(db, source_id, None, lock=True)
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        if order is not None and order.state == OrderState.PENDING and order.payment_id is None and not order.lines:
            order.state = OrderState.UNPAID
            order.method = None
            adapter.apply_state(db, obj, order)
        db.commit()

    @staticmethod
    def confirm_gateway(db: Session, source_type: str, source_id: str, user: User) -> PaymentOrder:
        """For gateway payments (Stripe): re-check the provider and settle the order."""
        source_id = str(source_id)
        adapter = payable_registry.get(source_type)
        obj = adapter.load(db, source_id, user, lock=True)
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        if order is None:
            raise HTTPException(409, "No pending gateway payment")
        if order.state == OrderState.PAID:
            return order
        reference = order.payment_reference
        if order.state != OrderState.PENDING or not reference or order.method != "stripe":
            raise HTTPException(409, "No pending gateway payment")

        provider = payment_provider_registry.get_provider(config.PAYMENT_METHODS["stripe"])
        payment = provider.confirm_payment(db, reference)   # commits internally
        if payment is None:
            raise HTTPException(404, "Payment transaction not found")

        obj = adapter.load(db, source_id, user, lock=True)
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        status = getattr(payment.status, "value", payment.status)
        if status == "completed":
            _mark_paid(order, user)
        elif status in ("failed", "refunded"):   # let the cashier retry
            order.state = OrderState.UNPAID
            order.payment_id = None
            order.payment_reference = None
            order.method = None
        adapter.apply_state(db, obj, order)
        db.commit()
        db.refresh(order)
        return order

    # --------------------------------------------------- transfer line actions

    @staticmethod
    def confirm_transfer(db: Session, source_type: str, source_id: str, line_id: int, user: User,
                         note: Optional[str] = None) -> PaymentOrder:
        """Cashier confirms the bank transfer arrived (the manual 'received' tick)."""
        source_id = str(source_id)
        adapter = payable_registry.get(source_type)
        obj = adapter.load(db, source_id, user, lock=True)
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        if order is None:
            raise HTTPException(404, "Payment line not found")
        line = _find_line(order, line_id)
        if line.method != "bank_transfer":
            raise HTTPException(409, "Only bank transfer lines are confirmed this way")
        if line.status == LineStatus.COMPLETED:
            return order                                    # idempotent
        if line.status != LineStatus.PENDING:
            raise HTTPException(409, f"Payment line is {line.status.value}")

        reference = line.payment_reference
        if reference:
            manual = payment_provider_registry.get_provider("manual")
            if manual.confirm_payment(db, reference) is None:    # commits internally
                raise HTTPException(404, "Payment transaction not found")

        obj = adapter.load(db, source_id, user, lock=True)
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        line = _find_line(order, line_id)
        line.status = LineStatus.COMPLETED
        line.confirmed_by_id = user.id
        line.confirmed_at = _now()
        if note:
            line.note = note
        _log(db, order.id, "transfer_confirmed", user.id, line_id,
             {"amount": str(line.amount), "memo": line.transfer_memo, "note": note})
        _settle(db, order, adapter, obj, user)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def confirm_transfer_from_bank(
        db: Session, line_id: int, bank_tx_id: int, details: dict, actor: Optional[User] = None,
    ) -> PaymentOrder:
        """Confirm a pending transfer line because the bank reported the money.

        actor=None is the automatic path (SePay webhook); a manager can also assign a bank
        transaction to a line by hand. No tenant check here: the caller has already matched
        the line (by memo) or checked the manager's tenant.
        """
        line = db.get(PaymentLine, line_id)
        if line is None:
            raise HTTPException(404, "Payment line not found")
        source_type, source_id = line.order.source_type, line.order.source_id

        adapter = payable_registry.get(source_type)
        obj = adapter.load(db, source_id, None, lock=True)          # system caller: no tenant check
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        line = _find_line(order, line_id)
        if line.method != "bank_transfer":
            raise HTTPException(409, "Only bank transfer lines can be confirmed by a bank transaction")
        if line.status != LineStatus.PENDING:
            raise HTTPException(409, f"Payment line is {line.status.value}")

        reference = line.payment_reference
        if reference:
            manual = payment_provider_registry.get_provider("manual")
            if manual.confirm_payment(db, reference) is None:    # commits internally
                raise HTTPException(404, "Payment transaction not found")

        obj = adapter.load(db, source_id, None, lock=True)
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        line = _find_line(order, line_id)
        line.status = LineStatus.COMPLETED
        line.confirmed_by_id = _uid(actor)
        line.confirmed_at = _now()
        _log(db, order.id, "transfer_auto_confirmed" if actor is None else "transfer_assigned_from_bank",
             _uid(actor), line_id,
             {"amount": str(line.amount), "memo": line.transfer_memo, "bank_transaction_id": bank_tx_id, **details})
        _settle(db, order, adapter, obj, actor)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def cancel_line(db: Session, source_type: str, source_id: str, line_id: int, user: User,
                    reason: Optional[str] = None) -> PaymentOrder:
        """Void a line that is still waiting (e.g. the customer decided to pay cash instead)."""
        source_id = str(source_id)
        adapter = payable_registry.get(source_type)
        obj = adapter.load(db, source_id, user, lock=True)
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        if order is None:
            raise HTTPException(404, "Payment line not found")
        line = _find_line(order, line_id)
        if line.status != LineStatus.PENDING:
            raise HTTPException(409, "Only a pending payment line can be cancelled")

        payment_id = line.payment_id
        if payment_id:
            existing = payment_service.get_payment(db, payment_id)
            meta = {**(existing.extra_metadata or {}), "cancelled": True, "cancel_reason": reason} if existing else None
            payment_service.update_payment_status(
                db, payment_id, PaymentUpdate(status=PaymentStatus.FAILED, extra_metadata=meta),
            )                                               # commits internally; keeps the reconciliation metadata

        obj = adapter.load(db, source_id, user, lock=True)
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        line = _find_line(order, line_id)
        line.status = LineStatus.CANCELLED
        if reason:
            line.note = reason
        _log(db, order.id, "line_cancelled", user.id, line_id, {"reason": reason})
        _settle(db, order, adapter, obj, user)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def void_line(db: Session, source_type: str, source_id: str, line_id: int, user: User,
                  reason: str) -> PaymentOrder:
        """Manager-only: reverse a completed line (cash handed back / transfer returned).

        The order goes back to part-paid or unpaid so it can be paid again. In the cash drawer
        a cash void counts as money out in the shift in which it happens.
        """
        if not is_manager(user):
            raise HTTPException(403, "Only a manager can void a payment")
        reason = (reason or "").strip()
        if len(reason) < 3:
            raise HTTPException(422, "A reason is required to void a payment")

        source_id = str(source_id)
        adapter = payable_registry.get(source_type)
        obj = adapter.load(db, source_id, user, lock=True)
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        if order is None:
            raise HTTPException(404, "Payment line not found")
        line = _find_line(order, line_id)
        if line.status != LineStatus.COMPLETED:
            raise HTTPException(409, "Only a completed payment line can be voided (cancel a pending one instead)")

        reference = line.payment_reference
        if reference:
            manual = payment_provider_registry.get_provider("manual")
            manual.refund_payment(db, reference)            # marks the PaymentTransaction refunded; commits

        obj = adapter.load(db, source_id, user, lock=True)
        order = PaymentOrderService.get_order(db, source_type, source_id, lock=True)
        line = _find_line(order, line_id)
        line.status = LineStatus.VOIDED
        line.voided_at = _now()
        line.voided_by_id = user.id
        line.void_reason = reason
        _log(db, order.id, "line_voided", user.id, line_id,
             {"method": line.method, "amount": str(line.amount), "reason": reason})
        _settle(db, order, adapter, obj, user)
        db.commit()
        db.refresh(order)
        return order

    # ------------------------------------------------------------------- reads

    @staticmethod
    def list_events(db: Session, source_type: str, source_id: str, user: User) -> list[PaymentEvent]:
        adapter = payable_registry.get(source_type)
        adapter.load(db, str(source_id), user, lock=False)    # tenant check
        order = PaymentOrderService.get_order(db, source_type, source_id)
        if order is None:
            return []
        return (
            db.query(PaymentEvent).filter(PaymentEvent.order_id == order.id).order_by(PaymentEvent.id).all()
        )

    @staticmethod
    def line_view(line: PaymentLine) -> PaymentLineResponse:
        transfer = None
        if line.method == "bank_transfer" and line.status == LineStatus.PENDING and line.transfer_memo:
            transfer = build_transfer_instruction(line.amount, line.transfer_memo, line.expires_at)
        return PaymentLineResponse(
            id=line.id, method=line.method, amount=line.amount, status=line.status.value,
            cash_tendered=line.cash_tendered, change_given=line.change_given,
            payment_reference=line.payment_reference, note=line.note,
            confirmed_at=line.confirmed_at, voided_at=line.voided_at, void_reason=line.void_reason,
            transfer=transfer,
        )

    @staticmethod
    def amount_paid(order: Optional[PaymentOrder]) -> Decimal:
        return _amount_paid(order) if order is not None else ZERO

    @staticmethod
    def line_views(order: Optional[PaymentOrder]) -> list[PaymentLineResponse]:
        return [PaymentOrderService.line_view(p) for p in order.lines] if order is not None else []

    @staticmethod
    def build_view(source_type: str, source_id: str, quote: Quote, order: Optional[PaymentOrder]) -> dict:
        """The payment side of a business object as one response. `quote` (not the stored
        snapshot) supplies total/currency so the view is always current."""
        paid = PaymentOrderService.amount_paid(order)
        return OrderResponse(
            source_type=source_type, source_id=str(source_id),
            order_id=order.id if order else None,
            currency=quote.currency, total=quote.total,
            state=order.state.value if order else OrderState.UNPAID.value,
            method=order.method if order else None,
            paid_at=order.paid_at if order else None,
            amount_paid=paid, balance_due=max(quote.total - paid, ZERO),
            payments=PaymentOrderService.line_views(order),
        ).model_dump()

    @staticmethod
    def get_view(db: Session, source_type: str, source_id: str, user: User) -> dict:
        adapter = payable_registry.get(source_type)
        obj = adapter.load(db, str(source_id), user, lock=False)
        order = PaymentOrderService.get_order(db, source_type, source_id)
        return PaymentOrderService.build_view(source_type, source_id, adapter.quote(obj), order)


payment_order_service = PaymentOrderService()
