# app/billiard/services/table_service.py
from datetime import datetime, timezone
from decimal import Decimal
import math

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billiard.models.table import (
    BilliardTable,
    TableStatus,
)
from app.billiard.models.session import (
    TableSession,
    SessionStatus,
)


class TableService:

    @staticmethod
    async def get_active_tables(
        db: AsyncSession,
    ):
        result = await db.execute(
            select(TableSession)
            .join(BilliardTable)
            .where(
                TableSession.status == SessionStatus.ACTIVE
            )
        )

        sessions = result.scalars().all()

        response = []

        now = datetime.now(timezone.utc)

        for session in sessions:

            table = session.table

            elapsed_seconds = (
                now - session.start_time
            ).total_seconds()

            elapsed_minutes = max(
                1,
                math.ceil(elapsed_seconds / 60),
            )

            current_table_fee = (
                table.hourly_rate
                * Decimal(elapsed_minutes)
                / Decimal(60)
            ).quantize(Decimal("0.01"))

            current_total = (
                current_table_fee
                + session.total_product_fee
        )

        response.append({
            "id": table.id,
            "name": table.name,
            "status": table.status,
            "session_id": session.id,
            "start_time": session.start_time.isoformat(),
            "elapsed_minutes": elapsed_minutes,
            "current_table_fee": current_table_fee,
            "current_product_fee": session.total_product_fee,
            "current_total": current_total,
        })

        return response

    
    @staticmethod
    async def start_session(
        db: AsyncSession,
        table_id: int,
    ) -> TableSession:

        result = await db.execute(
            select(BilliardTable)
            .where(BilliardTable.id == table_id)
            .with_for_update()
        )

        table = result.scalar_one_or_none()

        if not table:
            raise HTTPException(
                status_code=404,
                detail="Billiard table not found",
            )

        if table.status != TableStatus.AVAILABLE:
            raise HTTPException(
                status_code=409,
                detail=f"Table is {table.status.value}",
            )

        now = datetime.now(timezone.utc)

        session = TableSession(
            table_id=table.id,
            start_time=now,
            status=SessionStatus.ACTIVE,
        )

        table.status = TableStatus.PLAYING

        db.add(session)

        await db.flush()
        await db.refresh(session)

        return session



table_service = TableService()