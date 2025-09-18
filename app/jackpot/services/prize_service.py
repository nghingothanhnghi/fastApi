from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.jackpot.models.draw import PrizeResult, Ticket, Draw
from app.jackpot.utils.helpers import count_matches

PRIZE_TABLE_BASIC = {
    (6, False): ("Jackpot1", None),
    (5, True): ("Jackpot2", None),
    (5, False): ("First", 40_000_000),
    (4, False): ("Second", 500_000),
    (3, False): ("Third", 50_000),
}

class PrizeService:

    def check_ticket(
        self,
        db: Session,
        ticket: Ticket,
        draw: Draw,
        jackpot1_value: float = 30_000_000_000,
        jackpot2_value: float = 3_000_000_000
    ) -> Optional[PrizeResult]:
        matched = count_matches(ticket.numbers, draw.numbers)
        has_bonus = draw.bonus_number in ticket.numbers
        prize_info = PRIZE_TABLE_BASIC.get((matched, has_bonus))

        if not prize_info:
            return None

        category, base_value = prize_info
        prize_value = base_value or (jackpot1_value if category == "Jackpot1" else jackpot2_value)

        try:
            result = PrizeResult(ticket_id=ticket.id, category=category, prize_value=prize_value)
            db.add(result)
            db.commit()
            db.refresh(result)
            return result
        except SQLAlchemyError as e:
            db.rollback()
            raise e

# Export singleton
prize_service = PrizeService()
