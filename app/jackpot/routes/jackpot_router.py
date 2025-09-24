from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.jackpot.controllers.jackpot_controller import jackpot_controller
from app.jackpot.schemas.draw import DrawSchema, DrawCreateSchema
from app.jackpot.schemas.ticket import TicketCreateSchema, TicketSchema, TicketWithPrizeSchema
from app.jackpot.schemas.prize import PrizeResultSchema, PrizeHistorySummarySchema
from app.jackpot.schemas.rules import JackpotRuleSchema

router = APIRouter(prefix="/jackpot", tags=["Jackpot 6/55"])

@router.post("/draw", response_model=DrawSchema)
def create_draw(draw_in: DrawCreateSchema, db: Session = Depends(get_db)):
    try:
        return jackpot_controller.create_draw(
            db,
            draw_type=draw_in.draw_type,
            numbers=draw_in.numbers,
            bonus_number=draw_in.bonus_number
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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

@router.get("/rules", response_model=JackpotRuleSchema)
def get_rules():
    return jackpot_controller.get_rules()

@router.get("/prizes/history", response_model=PrizeHistorySummarySchema)
def get_prize_history(
    range: str = Query("month", enum=["month", "quarter", "year"]),
    db: Session = Depends(get_db)
):
    return jackpot_controller.get_prize_history(db, range)

@router.get("/tickets/user/{user_id}", response_model=list[TicketWithPrizeSchema])
def get_user_tickets(user_id: int, db: Session = Depends(get_db)):
    return jackpot_controller.get_user_tickets(db, user_id)
