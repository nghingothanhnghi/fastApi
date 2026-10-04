from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.models.user import User
from app.billiard.services.session_service import session_service
from app.billiard.schemas.session import PaySessionRequest, PaymentResponse, SessionItemResponse, StopSessionResponse, AddSessionItemRequest

router = APIRouter(
    prefix="/sessions",
    tags=["Billiard Sessions"],
)


@router.post("/{session_id}/items")
async def add_item(
    session_id: int,
    request: AddSessionItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    item = await session_service.add_item(
        db=db,
        session_id=session_id,
        product_id=request.product_id,
        quantity=request.quantity,
    )

    await db.commit()

    return {
        "id": item.id,
        "session_id": item.session_id,
        "product_id": item.product_id,
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "total_price": item.total_price,
    }

@router.post(
    "/{session_id}/stop",
    response_model=StopSessionResponse,
)
async def stop_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    session = await session_service.stop_session(
        db=db,
        session_id=session_id,
    )

    await db.commit()

    duration_minutes = (
        session.end_time - session.start_time
    ).total_seconds() / 60

    return StopSessionResponse(
        session_id=session.id,
        table_id=session.table_id,
        start_time=session.start_time,
        end_time=session.end_time,
        duration_minutes=round(duration_minutes),
        total_table_fee=session.total_table_fee,
        total_product_fee=session.total_product_fee,
        grand_total=session.grand_total,
        items=[
            SessionItemResponse(
                id=item.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
            )
            for item in session.items
        ],
    )

@router.post(
    "/{session_id}/pay",
    response_model=PaymentResponse,
)
async def pay_session(
    session_id: int,
    request: PaySessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):

    payment = await BilliardPaymentService.pay_session(
        db=db,
        session_id=session_id,
        payment_method=request.payment_method,
        user_id=current_user.id,
    )

    await db.commit()

    return PaymentResponse(
        payment_id=payment.id,
        session_id=session_id,
        amount=payment.amount,
        payment_method=payment.payment_method,
        status=payment.status,
    )