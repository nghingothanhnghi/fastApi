from sqlalchemy.orm import Session
from app.jackpot.services.draw_service import draw_service
from app.jackpot.services.ticket_service import ticket_service
from app.jackpot.services.prize_service import prize_service
from app.jackpot.services.rule_service import rule_service
from app.jackpot.services.analytics_service import jackpot_analytics_service

from app.jackpot.schemas.prize import PrizeHistorySummarySchema
from app.jackpot.schemas.ticket import TicketWithPrizeSchema
from app.jackpot.models.draw import DrawType
from typing import Optional, List
class JackpotController:

    def create_draw(
        self,
        db: Session,
        draw_type: DrawType = DrawType.automatic,
        numbers: Optional[List[int]] = None,
        bonus_number: Optional[int] = None
    ):
        return draw_service.create_draw(
            db,
            draw_type=draw_type,
            numbers=numbers,
            bonus_number=bonus_number
        )
    
    def get_latest_draw(self, db: Session):
        return draw_service.get_latest_draw(db)
    
    def get_current_draw(self, db: Session):
        """Return or create the active scheduled draw (for ticket purchase)."""
        return draw_service.get_or_create_current_draw(db)    

    def buy_ticket(self, db: Session, user_id: int, numbers: list[int], play_type):
        draw = draw_service.get_or_create_current_draw(db)  # 🔑 scheduled or create one
        if not draw:
            raise ValueError("No active draw available.")
        return ticket_service.create_ticket(db, user_id, numbers, play_type, draw.id)

    def check_ticket(self, db: Session, ticket_id: int):
        ticket = ticket_service.get_ticket(db, ticket_id)
        if not ticket:
            return None
        return prize_service.check_ticket(db, ticket, ticket.draw)
    
    def get_rules(self):
        return rule_service.get_rules()

    def get_prize_history(self, db: Session, range: str) -> PrizeHistorySummarySchema:
        """
        Return aggregated prize history summary for the given range (month/quarter/year).
        """
        summary = prize_service.get_prizes_in_range(db, range)
        return PrizeHistorySummarySchema(**summary)
    
    def get_user_tickets(self, db: Session, user_id: int) -> list[TicketWithPrizeSchema]:
        tickets = ticket_service.get_tickets_by_user(db, user_id)
        results = []
        for t in tickets:
            results.append(TicketWithPrizeSchema(ticket=t, prize=t.result))
        return results
    def get_ticket_count_by_draw(self, db: Session):
        return jackpot_analytics_service.ticket_count_by_draw(db)

    def get_number_frequency(self, db: Session, limit: int = 10):
        return jackpot_analytics_service.number_frequency(db, limit)

    def get_sales_summary(self, db: Session):
        return jackpot_analytics_service.sales_summary(db)

    def suggest_next_numbers(self, db: Session, top_k: int = 20):
        return jackpot_analytics_service.suggest_next_numbers(db, top_k)

# Export singleton
jackpot_controller = JackpotController()
