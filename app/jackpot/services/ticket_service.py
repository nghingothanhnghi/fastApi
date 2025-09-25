# app/jackpot/services/ticket_service.py
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.jackpot.models.draw import Ticket, PlayType
from app.jackpot.services.draw_service import draw_service
class TicketService:

    # def create_ticket(self, db: Session, user_id: int, numbers: list[int], play_type: PlayType, draw_id: int) -> Ticket:
    #     if play_type != PlayType.basic and len(numbers) < int(play_type[-1]):
    #         raise ValueError("Not enough numbers for selected Bao play type.")
    #     try:
    #         ticket = Ticket(user_id=user_id, numbers=numbers, play_type=play_type, draw_id=draw_id)
    #         db.add(ticket)
    #         db.commit()
    #         db.refresh(ticket)
    #         return ticket
    #     except SQLAlchemyError as e:
    #         db.rollback()
    #         raise e

    def create_ticket(
        self, 
        db: Session, 
        user_id: int, 
        numbers: list[int], 
        play_type: PlayType, 
        draw_id: Optional[int] = None
    ) -> Ticket:
        """
        Create a ticket for the user.
        If draw_id is not given, attach to the current or next active draw.
        """
        if play_type != PlayType.basic and len(numbers) < int(play_type[-1]):
            raise ValueError("Not enough numbers for selected Bao play type.")

        try:
            # pick or create current draw if not explicitly given
            if draw_id is None:
                draw = draw_service.get_or_create_current_draw(db)
                draw_id = draw.id

            ticket = Ticket(
                user_id=user_id, 
                numbers=numbers, 
                play_type=play_type, 
                draw_id=draw_id
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)
            return ticket
        except SQLAlchemyError as e:
            db.rollback()
            raise e

    def get_ticket(self, db: Session, ticket_id: int) -> Optional[Ticket]:
        return db.query(Ticket).filter(Ticket.id == ticket_id).first()

    def get_tickets_by_draw(self, db: Session, draw_id: int) -> List[Ticket]:
        return db.query(Ticket).filter(Ticket.draw_id == draw_id).all()

    def get_tickets_by_user(self, db: Session, user_id: int) -> List[Ticket]:
        return db.query(Ticket).filter(Ticket.user_id == user_id).all()

# Export singleton
ticket_service = TicketService()
