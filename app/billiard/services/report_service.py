# app/billiard/services/report_service.py
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.billiard.models import BilliardTable, TableSession, SessionStatus, PaymentState
from app.billiard.schemas.report import TableUsageReport, TableUsageRow
from app.billiard.services.table_service import scope_tables
from app.user.models.user import User


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


class ReportService:

    @staticmethod
    def table_usage(
        db: Session, user: User,
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None,
    ) -> TableUsageReport:
        # Date filters live in the JOIN condition so tables with zero sessions still appear.
        cond = [TableSession.table_id == BilliardTable.id, TableSession.status == SessionStatus.COMPLETED]
        if start_date:
            cond.append(TableSession.end_time >= start_date)
        if end_date:
            cond.append(TableSession.end_time <= end_date)

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
        return TableUsageReport(period_start=start_date, period_end=end_date, rows=rows, totals=totals)


report_service = ReportService()