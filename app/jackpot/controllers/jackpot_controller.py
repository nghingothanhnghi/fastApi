from sqlalchemy.orm import Session
from app.jackpot.services.draw_service import draw_service
from app.jackpot.services.ticket_service import ticket_service
from app.jackpot.services.prize_service import prize_service
from app.jackpot.services.rule_service import rule_service

from app.jackpot.schemas.prize import PrizeHistorySummarySchema
from app.jackpot.schemas.ticket import TicketWithPrizeSchema

class JackpotController:

    def create_draw(self, db: Session):
        return draw_service.create_draw(db)
    
    def get_latest_draw(self, db: Session):
        return draw_service.get_latest_draw(db)

    def buy_ticket(self, db: Session, user_id: int, numbers: list[int], play_type):
        draw = draw_service.get_latest_draw(db)
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

# Export singleton
jackpot_controller = JackpotController()
