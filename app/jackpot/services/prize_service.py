# app/jackpot/services/prize_service.py
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import func
from app.jackpot.models.draw import PrizeResult, Ticket, Draw
from app.jackpot.utils.helpers import count_matches, calculate_jackpot_probabilities

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
        
    def get_prizes_in_range(self, db: Session, range: str) -> dict:
        """
        Returns aggregated prize statistics for a given time range.
        Range: 'month', 'quarter', or 'year'
        """
        now = datetime.utcnow()
        if range == "month":
            start_date = now - timedelta(days=30)
        elif range == "quarter":
            start_date = now - timedelta(days=90)
        else:
            start_date = now - timedelta(days=365)

        rows = (
            db.query(
                PrizeResult.category,
                func.count(PrizeResult.id),  # ensure count() never returns None
                func.sum(PrizeResult.prize_value)
            )
            .join(Ticket)
            .join(Draw)
            .filter(Draw.draw_date >= start_date)
            .group_by(PrizeResult.category)
            .all()
        )

        summary = {
            "totalJackpot1": 0,
            "totalJackpot2": 0,
            "totalFirst": 0,
            "totalSecond": 0,
            "totalThird": 0,
            "totalPrizeValue": 0.0,
            "probabilities": calculate_jackpot_probabilities(n=55, k=6, bonus=True)  # ✅ add theoretical probabilities
        }

        for category, count, total_value in rows:
            count = int(count or 0)
            if category == "Jackpot1":
                summary["totalJackpot1"] = count
            elif category == "Jackpot2":
                summary["totalJackpot2"] = count
            elif category == "First":
                summary["totalFirst"] = count
            elif category == "Second":
                summary["totalSecond"] = count
            elif category == "Third":
                summary["totalThird"] = count

            if total_value:
                summary["totalPrizeValue"] += float(total_value)

        return summary  

# Export singleton
prize_service = PrizeService()
