from sqlalchemy.orm import Session
from app.jackpot.services.draw_service import draw_service
from app.jackpot.services.ticket_service import ticket_service
from app.jackpot.services.prize_service import prize_service

class JackpotController:

    def create_draw(self, db: Session):
        return draw_service.create_draw(db)

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

# Export singleton
jackpot_controller = JackpotController()
