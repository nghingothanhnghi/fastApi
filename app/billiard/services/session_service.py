# app/billiard/services/session_service.py
# Billiard rules only. Product/Payment modules stay the source of truth for their domains.
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billiard import config
from app.billiard.config import BillingPolicy
from app.billiard.models import (
    BilliardTable, PaymentState, TableSession, SessionItem, SessionStatus,
)
from app.billiard.schemas.session import BillResponse, SessionItemResponse
from app.billiard.services import session_lifecycle
from app.billiard.utils.billing import CENT
from app.payments.services.order_service import payment_order_service
from app.product.models.product import Product, ProductVariant
from app.user.models.user import User


def _discount_percent(session: TableSession):
    """The percent when the discount was given as a percent (None for a fixed amount)."""
    spec = session_lifecycle.discount_spec(session)
    return Decimal(str(spec["value"])) if spec and spec["type"] == "percent" else None


class SessionService:

    @staticmethod
    def get_locked_session(db: Session, session_id: int, user: User) -> TableSession:
        """Load + row-lock a session (serializes add_item / stop / pay), with tenant check."""
        session = db.execute(
            select(TableSession).where(TableSession.id == session_id).with_for_update()
        ).scalar_one_or_none()
        # 404 (not 403) for other tenants: don't leak that the id exists
        if not session or (not user.is_super_admin() and session.table.client_id != user.client_id):
            raise HTTPException(404, "Session not found")
        return session

    @staticmethod
    def add_item(
        db: Session, session_id: int, product_id: int, quantity: int,
        variant_id: int | None, user: User,
    ) -> SessionItem:
        session = SessionService.get_locked_session(db, session_id, user)
        if session.status != SessionStatus.ACTIVE:
            raise HTTPException(409, "Items can only be added to an active session")

        product = db.get(Product, product_id)
        if not product:
            raise HTTPException(404, "Product not found")
        if product.is_active is False:
            raise HTTPException(400, "Product is not available")

        price, name = product.base_price, product.name
        if variant_id is not None:
            variant = db.get(ProductVariant, variant_id)
            if not variant or variant.product_id != product.id:
                raise HTTPException(400, "Variant does not belong to this product")
            price, name = variant.price, f"{product.name} - {variant.name}"

        # Price is frozen NOW. Receipts read SessionItem.*, never Product.*.
        unit_price = Decimal(str(price)).quantize(CENT)
        item = SessionItem(
            product_id=product.id, variant_id=variant_id, product_name=name,
            quantity=quantity, unit_price=unit_price, total_price=unit_price * quantity,
            added_by_id=user.id,
        )
        session.items.append(item)
        session_lifecycle.recompute_totals(session)
        db.flush()
        return item

    @staticmethod
    def stop_session(db: Session, session_id: int, user: User) -> TableSession:
        session = SessionService.get_locked_session(db, session_id, user)
        if session.status == SessionStatus.CANCELLED:
            raise HTTPException(409, "Session was cancelled")
        if session.status != SessionStatus.ACTIVE:
            raise HTTPException(409, "Session is already completed")
        table = db.execute(
            select(BilliardTable).where(BilliardTable.id == session.table_id).with_for_update()
        ).scalar_one()
        session_lifecycle.finalize_stop(db, session, table, user.id)
        return session

    @staticmethod
    def set_discount(
        db: Session, session_id: int, amount, percent, reason: str | None, user: User,
    ) -> TableSession:
        """Give, change or remove (amount 0) a discount. The route restricts this to ADMIN/MANAGER.
        Allowed on an ACTIVE session, or a COMPLETED one that has no payment order yet:
        once a payment order exists its total is fixed and the discount can no longer change."""
        session = SessionService.get_locked_session(db, session_id, user)
        if session.status == SessionStatus.CANCELLED:
            raise HTTPException(409, "Session was cancelled")
        if session.status == SessionStatus.COMPLETED and (
            session.payment_order_id is not None or session.payment_state != PaymentState.UNPAID
        ):
            raise HTTPException(409, "A payment was already started for this session, the discount can no longer change")
        try:
            session_lifecycle.apply_discount(session, amount=amount, percent=percent, reason=reason, by_id=user.id)
        except ValueError as e:
            raise HTTPException(422, str(e))
        db.flush()
        return session

    @staticmethod
    def cancel_session(db: Session, session_id: int, reason: str, user: User) -> TableSession:
        """Cancel a session opened by mistake. The route restricts this to ADMIN/MANAGER;
        only ACTIVE sessions can be cancelled (a completed one is a payment void, not a cancel)."""
        session = SessionService.get_locked_session(db, session_id, user)
        if session.status == SessionStatus.CANCELLED:
            raise HTTPException(409, "Session is already cancelled")
        if session.status != SessionStatus.ACTIVE:
            raise HTTPException(409, "Only an active session can be cancelled")
        table = db.execute(
            select(BilliardTable).where(BilliardTable.id == session.table_id).with_for_update()
        ).scalar_one()
        session_lifecycle.cancel_session(db, session, table, user.id, reason)
        return session

    @staticmethod
    def get_session(db: Session, session_id: int, user: User) -> TableSession:
        session = db.get(TableSession, session_id)
        if not session or (not user.is_super_admin() and session.table.client_id != user.client_id):
            raise HTTPException(404, "Session not found")
        return session

    @staticmethod
    def build_bill(session: TableSession) -> dict:
        """Built purely from session snapshots; safe for old receipts."""
        snap = session.pricing_snapshot or {}
        order = session.payment_order
        amount_paid = payment_order_service.amount_paid(order)
        # Legacy sessions (paid before the Payments module kept the bill) have no order.
        if order is None and session.payment_state.value == "paid":
            amount_paid = session.grand_total
        return BillResponse(
            session_id=session.id,
            table_id=session.table_id,
            table_name=session.table.name,
            currency=config.CURRENCY,
            status=session.status.value,
            start_time=session.start_time,
            end_time=session.end_time,
            duration_minutes=session.duration_minutes,
            hourly_rate=session.hourly_rate,
            billing_policy=session.billing_policy,
            pricing_rule_name=snap.get("rule_name"),
            pricing_params=snap.get("params") or {},
            total_table_fee=session.total_table_fee,
            total_product_fee=session.total_product_fee,
            discount=session.discount or Decimal("0"),
            discount_percent=_discount_percent(session),
            discount_reason=session.discount_reason,
            discounted_by=session.discounted_by.username if session.discounted_by else None,
            grand_total=session.grand_total,
            items=[
                SessionItemResponse(
                    id=i.id, product_id=i.product_id, variant_id=i.variant_id,
                    product_name=i.product_name, quantity=i.quantity,
                    unit_price=i.unit_price, total_price=i.total_price,
                ) for i in session.items
            ],
            payment_state=session.payment_state.value,
            payment_method=session.payment_method,
            payment_reference=session.payment_reference,
            paid_at=session.paid_at,
            amount_paid=amount_paid,
            balance_due=max(session.grand_total - amount_paid, Decimal("0")),
            payments=payment_order_service.line_views(order),
            opened_by=session.opened_by.username if session.opened_by else None,
            stopped_by=session.stopped_by.username if session.stopped_by else None,
            paid_by=session.paid_by.username if session.paid_by else None,
            cancelled_at=session.cancelled_at,
            cancelled_by=session.cancelled_by.username if session.cancelled_by else None,
            cancel_reason=session.cancel_reason,
        ).model_dump()


session_service = SessionService()