from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.models.user import User

from app.billiard.services.table_service import table_service
from app.billiard.schemas.session import StartSessionResponse
from app.billiard.schemas.table import ActiveTableResponse

router = APIRouter(
    prefix="/tables",
    tags=["Billiard Tables"],
)


@router.post(
    "/{table_id}/start",
    response_model=StartSessionResponse,
)
async def start_table(
    table_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    session = await table_service.start_session(
        db=db,
        table_id=table_id,
    )

    await db.commit()

    return StartSessionResponse(
        session_id=session.id,
        table_id=session.table_id,
        start_time=session.start_time,
    )

@router.get(
    "/active",
    response_model=list[ActiveTableResponse],
)
async def active_tables(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    return await table_service.get_active_tables(db)