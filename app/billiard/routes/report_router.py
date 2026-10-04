# app/billiard/routes/report_router.py
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.user.enums.role_enum import RoleEnum
from app.user.models.user import User
from app.user.utils.role_requirements import require_roles
from app.billiard.schemas.report import TableUsageReport
from app.billiard.services.report_service import report_service

router = APIRouter(prefix="/reports", tags=["Billiard Reports"])


@router.get("/tables/usage", response_model=TableUsageReport)
def table_usage(
    start_date: Optional[datetime] = Query(None, description="Filter by session end_time >="),
    end_date: Optional[datetime] = Query(None, description="Filter by session end_time <="),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)),
):
    return report_service.table_usage(db, current_user, start_date, end_date)