# app/billiard/services/table_service.py
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from app.billiard import config
from app.billiard.config import BillingPolicy
from app.billiard.models import BilliardTable, TableSession, SessionStatus
from app.billiard.schemas.table import TableCreate
from app.billiard.services.table_lifecycle import mark_playing
from app.billiard.utils.billing import as_utc, billable_minutes, calculate_table_fee
from app.user.models.user import User


def scope_tables(stmt, user: User):
    """Tenant isolation: SUPER_ADMIN sees all, everyone else only their client_id."""
    if user.is_super_admin():
        return stmt
    return stmt.where(BilliardTable.client_id == user.client_id)


class TableService:

    @staticmethod
    def create_table(db: Session, data: TableCreate, user: User) -> BilliardTable:
        exists = db.execute(
            select(BilliardTable.id).where(
                BilliardTable.client_id == user.client_id, BilliardTable.name == data.name
            )
        ).first()
        if exists:
            raise HTTPException(409, f"Table '{data.name}' already exists")
        table = BilliardTable(name=data.name, hourly_rate=data.hourly_rate, client_id=user.client_id)
        db.add(table)
        try:
            db.flush()
        except IntegrityError:
            # uq_billiard_table_name_per_client: lost a race with a concurrent create
            db.rollback()
            raise HTTPException(409, f"Table '{data.name}' already exists")
        return table

    @staticmethod
    def list_tables(db: Session, user: User) -> list[BilliardTable]:
        stmt = scope_tables(select(BilliardTable).order_by(BilliardTable.name), user)
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def start_session(db: Session, table_id: int, user: User) -> TableSession:
        # Row lock serializes concurrent starts on the same table (PostgreSQL);
        # the partial unique index is the backstop on every engine.
        stmt = scope_tables(
            select(BilliardTable).where(BilliardTable.id == table_id).with_for_update(), user
        )
        table = db.execute(stmt).scalar_one_or_none()
        if not table:
            raise HTTPException(404, "Billiard table not found")

        # Single owner of table.status transitions (see table_lifecycle).
        # Raises ValueError if the table is inactive or not AVAILABLE.
        try:
            mark_playing(table)
        except ValueError as e:
            raise HTTPException(409, str(e))

        session = TableSession(
            table_id=table.id,
            start_time=datetime.now(timezone.utc),
            status=SessionStatus.ACTIVE,
            hourly_rate=table.hourly_rate,                 # snapshot
            billing_policy=config.BILLING_POLICY.value,    # snapshot
            opened_by_id=user.id,
        )
        db.add(session)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()   # also discards the PLAYING status set above
            raise HTTPException(409, "Table already has an active session")
        return session

    @staticmethod
    def get_active_tables(db: Session, user: User) -> list[dict]:
        stmt = (
            select(TableSession)
            .join(BilliardTable, TableSession.table_id == BilliardTable.id)
            .options(contains_eager(TableSession.table))
            .where(TableSession.status == SessionStatus.ACTIVE)
            .order_by(BilliardTable.name)
        )
        sessions = db.execute(scope_tables(stmt, user)).scalars().unique().all()

        now = datetime.now(timezone.utc)
        out = []
        for s in sessions:
            minutes = billable_minutes(as_utc(s.start_time), now)
            table_fee = calculate_table_fee(s.hourly_rate, minutes, BillingPolicy(s.billing_policy))
            product_fee = s.total_product_fee
            out.append({
                "id": s.table.id,
                "name": s.table.name,
                "status": s.table.status,
                "session_id": s.id,
                "start_time": as_utc(s.start_time),
                "elapsed_minutes": minutes,
                "hourly_rate": s.hourly_rate,
                "current_table_fee": table_fee,
                "current_product_fee": product_fee,
                "current_total": table_fee + product_fee,
            })
        return out


table_service = TableService()