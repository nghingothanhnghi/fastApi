# app/billiard/services/session_service.py
from datetime import datetime, timezone
from decimal import Decimal
import math

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billiard.models.session import (
    TableSession,
    SessionStatus,
)
from app.billiard.models.session_item import SessionItem
from app.billiard.models.table import (
    BilliardTable,
    TableStatus,
)

from app.product.models import Product


class SessionService:

    @staticmethod
    async def get_active_session(
        db: AsyncSession,
        session_id: int,
    ) -> TableSession:

        result = await db.execute(
            select(TableSession)
            .where(TableSession.id == session_id)
        )

        session = result.scalar_one_or_none()

        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found",
            )

        if session.status != SessionStatus.ACTIVE:
            raise HTTPException(
                status_code=409,
                detail="Session is already completed",
            )

        return session

    @staticmethod
    async def add_item(
        db: AsyncSession,
        session_id: int,
        product_id: int,
        quantity: int,
    ) -> SessionItem:

        if quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity must be greater than zero",
            )

        session = await SessionService.get_active_session(
            db,
            session_id,
        )

        result = await db.execute(
            select(Product)
            .where(Product.id == product_id)
        )

        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found",
            )

        if not product.is_active:
            raise HTTPException(
                status_code=400,
                detail="Product is not available",
            )

        # Adapt this to your Product module's actual price field.
        unit_price = Decimal(product.price)

        total_price = unit_price * quantity

        item = SessionItem(
            session_id=session.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
        )

        db.add(item)

        session.total_product_fee += total_price
        session.grand_total = (
            session.total_table_fee
            + session.total_product_fee
        )

        await db.flush()
        await db.refresh(item)

        return item

    @staticmethod
    def calculate_table_fee(
        hourly_rate: Decimal,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[int, Decimal]:

        duration_seconds = (
            end_time - start_time
        ).total_seconds()

        duration_minutes = max(
            1,
            math.ceil(duration_seconds / 60),
        )

        hours = Decimal(duration_minutes) / Decimal(60)

        fee = hourly_rate * hours

        return duration_minutes, fee.quantize(
            Decimal("0.01")
        )

    @staticmethod
    async def stop_session(
        db: AsyncSession,
        session_id: int,
    ) -> TableSession:

        session = await SessionService.get_active_session(
            db,
            session_id,
        )

        result = await db.execute(
            select(BilliardTable)
            .where(BilliardTable.id == session.table_id)
            .with_for_update()
        )

        table = result.scalar_one()

        end_time = datetime.now(timezone.utc)

        duration_minutes, table_fee = (
            SessionService.calculate_table_fee(
                table.hourly_rate,
                session.start_time,
                end_time,
            )
        )

        session.end_time = end_time
        session.status = SessionStatus.COMPLETED

        session.total_table_fee = table_fee

        session.grand_total = (
            session.total_table_fee
            + session.total_product_fee
        )

        # Important:
        # table is released after STOP, not after PAY.
        #
        # If your business wants the table occupied until
        # payment is completed, keep PLAYING here instead.
        table.status = TableStatus.AVAILABLE

        await db.flush()

        return session

session_service = SessionService()