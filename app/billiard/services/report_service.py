# app/billiard/services/report_service.py
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.billiard import config
from app.billiard.models import BilliardTable, TableSession, SessionStatus, PaymentState
from app.billiard.schemas.report import TableUsageReport, TableUsageRow
from app.billiard.services.table_service import scope_tables
from app.user.models.user import User


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def _to_local(dt: datetime) -> datetime:
    """Naive input = already club-local time. Aware input = convert to club-local."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=config.LOCAL_TZ)
    return dt.astimezone(config.LOCAL_TZ)


def _to_utc(dt_local: datetime) -> datetime:
    return dt_local.astimezone(timezone.utc)


def _resolve_range(
    start_date: Optional[datetime], end_date: Optional[datetime]
) -> tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
    """
    Returns (start_utc, end_exclusive_utc, display_end_local).

    - Dates are interpreted in the club's timezone (not UTC).
    - A date-only end_date (00:00:00) means "through the end of that day".
    - Upper bound is EXCLUSIVE (`< end_exclusive`) so nothing is missed.
    """
    start_utc = None
    if start_date:
        start_utc = _to_utc(_to_local(start_date))

    end_exclusive_utc = None
    display_end_local = None
    if end_date:
        end_local = _to_local(end_date)
        if end_local.time() == time(0, 0):
            end_exclusive_local = end_local + timedelta(days=1)   # whole day included
        else:
            end_exclusive_local = end_local + timedelta(microseconds=1)  # exact instant, inclusive
        end_exclusive_utc = _to_utc(end_exclusive_local)
        display_end_local = (end_exclusive_local - timedelta(seconds=1)).replace(tzinfo=None)

    return start_utc, end_exclusive_utc, display_end_local


class ReportService:

    @staticmethod
    def table_usage(
        db: Session, user: User,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None,
    ) -> TableUsageReport:
        start_utc, end_exclusive_utc, display_end = _resolve_range(start_date, end_date)

        # Date filters live in the JOIN condition so tables with zero sessions still appear.
        cond = [TableSession.table_id == BilliardTable.id, TableSession.status == SessionStatus.COMPLETED]
        if start_utc:
            cond.append(TableSession.end_time >= start_utc)
        if end_exclusive_utc:
            cond.append(TableSession.end_time < end_exclusive_utc)

        paid = TableSession.payment_state == PaymentState.PAID

        def paid_sum(col):
            return func.coalesce(func.sum(case((paid, col), else_=0)), 0)

        stmt = (
            select(
                BilliardTable.id, BilliardTable.name,
                func.count(TableSession.id),
                func.coalesce(func.sum(TableSession.duration_minutes), 0),
                paid_sum(TableSession.total_table_fee),
                paid_sum(TableSession.total_product_fee),
                paid_sum(TableSession.grand_total),
                func.coalesce(func.sum(case((paid, 0), else_=TableSession.grand_total)), 0),
            )
            .select_from(BilliardTable)
            .outerjoin(TableSession, and_(*cond))
            .group_by(BilliardTable.id, BilliardTable.name)
            .order_by(BilliardTable.name)
        )
        rows = [
            TableUsageRow(
                table_id=r[0], table_name=r[1], times_played=int(r[2]), total_minutes=int(r[3]),
                table_revenue=_d(r[4]), product_revenue=_d(r[5]),
                total_revenue=_d(r[6]), unpaid_total=_d(r[7]),
            )
            for r in db.execute(scope_tables(stmt, user)).all()
        ]
        totals = TableUsageRow(
            table_id=0, table_name="TOTAL",
            times_played=sum(r.times_played for r in rows),
            total_minutes=sum(r.total_minutes for r in rows),
            table_revenue=sum((r.table_revenue for r in rows), Decimal("0")),
            product_revenue=sum((r.product_revenue for r in rows), Decimal("0")),
            total_revenue=sum((r.total_revenue for r in rows), Decimal("0")),
            unpaid_total=sum((r.unpaid_total for r in rows), Decimal("0")),
        )
        return TableUsageReport(
            period_start=start_date,
            period_end=display_end,   # real inclusive end (e.g. 2026-10-05T23:59:59), not the echoed midnight
            rows=rows,
            totals=totals,
        )


report_service = ReportService()