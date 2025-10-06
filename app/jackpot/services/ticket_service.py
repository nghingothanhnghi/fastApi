# app/jackpot/services/ticket_service.py
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from app.jackpot.models.draw import Ticket, PlayType, Draw
from datetime import datetime
class TicketService:

    def create_ticket(
        self, 
        db: Session, 
        user_id: int, 
        numbers: list[int], 
        play_type: PlayType, 
        draw_id: Optional[int] = None
    ) -> Ticket:
        # ✅ 1. Resolve which draw this ticket should belong to
        if draw_id is None:
            # Find the next available draw (future draw_date)
            next_draw = (
                db.query(Draw)
                .filter(Draw.draw_date >= datetime.utcnow())
                .order_by(Draw.draw_date.asc())
                .first()
            )
            if not next_draw:
                raise ValueError("No upcoming draw available.")
            draw_id = next_draw.id
        else:
            # Validate provided draw_id is still valid (future draw)
            selected_draw = db.query(Draw).filter(Draw.id == draw_id).first()
            if not selected_draw:
                raise ValueError(f"Draw {draw_id} not found.")
            if selected_draw.draw_date < datetime.utcnow():
                raise ValueError(f"Draw {draw_id} is already closed.")

        # ✅ 2. Validate Bao play type requires enough numbers
        if play_type != PlayType.basic and len(numbers) < int(play_type[-1]):
            raise ValueError("Not enough numbers for selected Bao play type.")

        # ✅ 3. Create ticket safely
        try:
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
        # return db.query(Ticket).filter(Ticket.user_id == user_id).all()
        return (
            db.query(Ticket)
            .options(
                joinedload(Ticket.draw),       # load the related draw
                joinedload(Ticket.result)      # load prize result if you need it
            )
            .filter(Ticket.user_id == user_id)
            .all()
        )

# Export singleton
ticket_service = TicketService()
