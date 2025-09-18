from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.jackpot.controllers import jackpot_controller
from app.jackpot.schemas.draw import DrawSchema
from app.jackpot.schemas.ticket import TicketCreateSchema, TicketSchema
from app.jackpot.schemas.prize import PrizeResultSchema

router = APIRouter(prefix="/jackpot", tags=["Jackpot 6/55"])

@router.post("/draw", response_model=DrawSchema)
def create_draw(db: Session = Depends(get_db)):
    return jackpot_controller.create_draw(db)

@router.post("/ticket", response_model=TicketSchema)
def buy_ticket(ticket_in: TicketCreateSchema, db: Session = Depends(get_db)):
    try:
        return jackpot_controller.buy_ticket(
            db, ticket_in.user_id, ticket_in.numbers, ticket_in.play_type
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ticket/{ticket_id}/check", response_model=PrizeResultSchema)
def check_ticket(ticket_id: int, db: Session = Depends(get_db)):
    result = jackpot_controller.check_ticket(db, ticket_id)
    if not result:
        raise HTTPException(status_code=404, detail="No prize for this ticket")
    return result

@router.get("/draw/latest", response_model=DrawSchema)
def get_latest_draw(db: Session = Depends(get_db)):
    draw = jackpot_controller.get_latest_draw(db)
    if not draw:
        raise HTTPException(status_code=404, detail="No draws found")
    return draw
