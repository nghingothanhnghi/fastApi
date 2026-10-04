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
    BilliardTable, TableSession, SessionItem, SessionStatus, TableStatus,
)
from app.billiard.schemas.session import BillResponse, SessionItemResponse
from app.billiard.utils.billing import CENT, billable_minutes, calculate_table_fee
from app.product.models.product import Product, ProductVariant
from app.user.models.user import User


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
        session.total_product_fee = sum((i.total_price for i in session.items), Decimal("0"))
        session.grand_total = session.total_table_fee + session.total_product_fee
        db.flush()
        return item

    @staticmethod
    def stop_session(db: Session, session_id: int, user: User) -> TableSession:
        session = SessionService.get_locked_session(db, session_id, user)
        if session.status != SessionStatus.ACTIVE:
            raise HTTPException(409, "Session is already completed")

        table = db.execute(
            select(BilliardTable).where(BilliardTable.id == session.table_id).with_for_update()
        ).scalar_one()

        end = datetime.now(timezone.utc)
        minutes = billable_minutes(session.start_time, end)
        fee = calculate_table_fee(session.hourly_rate, minutes, BillingPolicy(session.billing_policy))

        session.end_time = end
        session.status = SessionStatus.COMPLETED
        session.duration_minutes = minutes
        session.total_table_fee = fee
        session.total_product_fee = sum((i.total_price for i in session.items), Decimal("0"))
        session.grand_total = fee + session.total_product_fee
        session.stopped_by_id = user.id

        # Business rule: the bill is generated at STOP, so the table is freed now,
        # not after payment. Payment settles an already-completed session.
        table.status = TableStatus.AVAILABLE
        db.flush()
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
        return BillResponse(
            session_id=session.id,
            table_id=session.table_id,
            table_name=session.table.name,
            currency=config.CURRENCY,
            start_time=session.start_time,
            end_time=session.end_time,
            duration_minutes=session.duration_minutes,
            hourly_rate=session.hourly_rate,
            billing_policy=session.billing_policy,
            total_table_fee=session.total_table_fee,
            total_product_fee=session.total_product_fee,
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
            opened_by=session.opened_by.username if session.opened_by else None,
            stopped_by=session.stopped_by.username if session.stopped_by else None,
            paid_by=session.paid_by.username if session.paid_by else None,
        ).model_dump()


session_service = SessionService()