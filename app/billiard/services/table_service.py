# app/billiard/services/table_service.py
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from app.billiard import config
from app.billiard.models import BilliardTable, TableSession, SessionStatus
from app.billiard.models.session import BILLING_REVIEW_REQUIRED
from app.billiard.schemas.table import TableCreate, TableUpdate
from app.billiard.services.billing_service import billing_service, package_overtime_minutes
from app.billiard.services.package_service import package_service
from app.billiard.services import session_lifecycle, table_lifecycle
from app.billiard.services.session_lifecycle import open_session
from app.billiard.utils.billing import as_utc, billable_minutes
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
    def update_table(
        db: Session,
        table_id: int,
        data: TableUpdate,
        user: User,
    ) -> BilliardTable:
        stmt = scope_tables(
            select(BilliardTable)
            .where(BilliardTable.id == table_id)
            .with_for_update(),
            user,
        )

        table = db.execute(stmt).scalar_one_or_none()

        if not table:
            raise HTTPException(404, "Billiard table not found")

        update_data = data.model_dump(exclude_unset=True, exclude_none=True)

        # Prevent duplicate table names within the same client.
        if "name" in update_data:
            exists = db.execute(
                select(BilliardTable.id).where(
                    BilliardTable.client_id == table.client_id,
                    BilliardTable.name == update_data["name"],
                    BilliardTable.id != table_id,
                )
            ).first()

            if exists:
                raise HTTPException(
                    409,
                    f"Table '{update_data['name']}' already exists",
                )

        for field, value in update_data.items():
            setattr(table, field, value)

        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                409,
                f"Table '{update_data.get('name', table.name)}' already exists",
            )

        return table    

    @staticmethod
    def deactivate_table(
        db: Session,
        table_id: int,
        user: User,
    ) -> BilliardTable:
        stmt = scope_tables(
            select(BilliardTable)
            .where(BilliardTable.id == table_id)
            .with_for_update(),
            user,
        )

        table = db.execute(stmt).scalar_one_or_none()

        if not table:
            raise HTTPException(404, "Billiard table not found")

        if not table.is_active:
            raise HTTPException(409, "Billiard table is already inactive")

        # Check the session record, not just table.status.
        active_session = db.execute(
            select(TableSession.id).where(
                TableSession.table_id == table_id,
                TableSession.status == SessionStatus.ACTIVE,
            )
        ).first()

        if active_session:
            raise HTTPException(
                409,
                "Cannot deactivate a table with an active session",
            )

        table.is_active = False
        db.flush()

        return table

    # action -> lifecycle function. The service never writes table.status itself.
    _STATUS_ACTIONS = {
        "reserve": table_lifecycle.mark_reserved,
        "maintenance": table_lifecycle.mark_maintenance,
        "release": table_lifecycle.release,
    }

    @staticmethod
    def set_status(db: Session, table_id: int, action: str, user: User) -> BilliardTable:
        """Reserve a table, put it in maintenance, or release it. Status only:
        no reservation data is stored (see ROADMAP_PLAN.md, section 5 #1)."""
        change = TableService._STATUS_ACTIONS[action]
        table = db.execute(
            scope_tables(select(BilliardTable).where(BilliardTable.id == table_id).with_for_update(), user)
        ).scalar_one_or_none()
        if not table:
            raise HTTPException(404, "Billiard table not found")

        # Check the session record too, not only table.status (same rule as deactivate_table).
        if db.execute(
            select(TableSession.id).where(
                TableSession.table_id == table_id, TableSession.status == SessionStatus.ACTIVE
            )
        ).first():
            raise HTTPException(409, "Table has an active session, stop its session first")

        try:
            change(table)
        except ValueError as e:
            raise HTTPException(409, str(e))
        db.flush()
        return table

    @staticmethod
    def list_tables(db: Session, user: User) -> list[BilliardTable]:
        stmt = scope_tables(
            select(BilliardTable)
            .where(BilliardTable.is_active.is_(True))
            .order_by(BilliardTable.name), 
            user,
            )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def start_session(
        db: Session, table_id: int, user: User, planned_minutes: int | None = None,
        package_id: int | None = None,
    ) -> TableSession:
        # Row lock serializes concurrent starts on the same table (PostgreSQL);
        # the partial unique index is the backstop on every engine.
        stmt = scope_tables(
            select(BilliardTable).where(BilliardTable.id == table_id).with_for_update(), user
        )
        table = db.execute(stmt).scalar_one_or_none()
        if not table:
            raise HTTPException(404, "Billiard table not found")

        package = None
        if package_id is not None:
            package = package_service.find_for_club(db, package_id, table.client_id)   # other club = 404
            if package is None:
                raise HTTPException(404, "Package not found")
            if not package.is_active:
                raise HTTPException(400, "Package is not available")

        # Single owner of table.status transitions (see table_lifecycle).
        # Raises ValueError if the table is inactive or not AVAILABLE.
        try:
            session = open_session(db, table, user.id, planned_minutes=planned_minutes, package=package)  # mark_playing + snapshot
        except ValueError as e:                          # inactive / not AVAILABLE / bad planned_minutes
            raise HTTPException(409, str(e))
        except IntegrityError:
            db.rollback()
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
            table_fee = billing_service.table_fee(s, minutes)   # same function as the final bill
            product_fee = s.total_product_fee
            discount = session_lifecycle.discount_amount(s, table_fee + product_fee)
            ends_at = as_utc(s.ends_at) if s.ends_at else None
            pkg = s.package_snapshot or None
            remaining = int((ends_at - now).total_seconds()) if ends_at else None
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
                "ends_at": ends_at,
                "remaining_seconds": remaining,
                "is_overtime": bool(ends_at and now > ends_at),
                "package_name": pkg["name"] if pkg else None,
                "overtime_minutes": package_overtime_minutes(pkg, minutes) if pkg else None,
                "needs_billing_review": s.billing_review_state == BILLING_REVIEW_REQUIRED,
                "requested_package_id": s.requested_package_id,
                "billing_review_reason": s.billing_review_reason,
                "current_discount": discount,
                "current_total": table_fee + product_fee - discount,
            })
        return out


table_service = TableService()