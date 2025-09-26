from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.database import get_db
from app.jackpot.controllers.jackpot_controller import jackpot_controller
from app.jackpot.schemas.draw import DrawSchema, DrawCreateSchema
from app.jackpot.schemas.ticket import TicketCreateSchema, TicketSchema, TicketWithPrizeSchema
from app.jackpot.schemas.prize import PrizeResultSchema, PrizeHistorySummarySchema
from app.jackpot.schemas.rules import JackpotRuleSchema
from app.jackpot.schemas.analytics import (
    TicketCountByDrawItem,
    NumberFrequencyResponse,
    SalesSummaryResponse,
    NextSuggestionResponse,
)

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
    
@router.get("/draw/latest", response_model=DrawSchema)
def get_latest_draw(db: Session = Depends(get_db)):
    draw = jackpot_controller.get_latest_draw(db)
    if not draw:
        raise HTTPException(status_code=404, detail="No draws found")
    return draw

@router.get("/draw/current", response_model=DrawSchema)
def get_current_draw(db: Session = Depends(get_db)):
    """
    Returns the active scheduled draw (creates one if none exists).
    Use this for buying tickets.
    """
    return jackpot_controller.get_current_draw(db)

# -------------------- TICKET --------------------
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

@router.get("/tickets/user/{user_id}", response_model=list[TicketWithPrizeSchema])
def get_user_tickets(user_id: int, db: Session = Depends(get_db)):
    return jackpot_controller.get_user_tickets(db, user_id)


# -------------------- RULES --------------------
@router.get("/rules", response_model=JackpotRuleSchema)
def get_rules():
    return jackpot_controller.get_rules()

# -------------------- PRIZE HISTORY --------------------
@router.get("/prizes/history", response_model=PrizeHistorySummarySchema)
def get_prize_history(
    range: str = Query("month", enum=["month", "quarter", "year"]),
    db: Session = Depends(get_db)
):
    return jackpot_controller.get_prize_history(db, range)

# -------------------- ANALYTICS --------------------
@router.get("/analytics/ticket-count", response_model=List[TicketCountByDrawItem])
def get_ticket_count_by_draw(db: Session = Depends(get_db)):
    """
    Returns a list of draws with ticket counts.
    """
    return jackpot_controller.get_ticket_count_by_draw(db)


@router.get("/analytics/number-frequency", response_model=NumberFrequencyResponse)
def get_number_frequency(limit: int = Query(10, ge=1, le=55), db: Session = Depends(get_db)):
    """
    Returns hot/cold number frequencies from past draws.
    """
    return jackpot_controller.get_number_frequency(db, limit)


@router.get("/analytics/sales-summary", response_model=SalesSummaryResponse)
def get_sales_summary(db: Session = Depends(get_db)):
    """Total tickets sold and total revenue (price from rules)."""
    return jackpot_controller.get_sales_summary(db)


@router.get("/analytics/next-suggestion", response_model=NextSuggestionResponse)
def suggest_next_numbers(top_k: int = Query(20, ge=6, le=55), db: Session = Depends(get_db)):
    """
    Suggest 6 numbers for the next draw using a cold-first strategy (avoid latest draw numbers).
    - top_k: pool size of coldest numbers to choose from (default 20)
    """
    return jackpot_controller.suggest_next_numbers(db, top_k)
