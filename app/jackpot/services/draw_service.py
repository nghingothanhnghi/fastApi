# app/jackpot/services/draw_service.py
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from app.jackpot.models.draw import Draw, DrawType, DrawStatus, Ticket
from app.jackpot.utils.helpers import generate_draw_numbers
import random

class DrawService:

    def create_draw(self, db: Session) -> Draw:
        try:
            numbers, bonus_number = generate_draw_numbers()
            draw = Draw(draw_date=datetime.utcnow(), numbers=numbers, bonus_number=bonus_number)
            db.add(draw)
            db.commit()
            db.refresh(draw)
            return draw
        except SQLAlchemyError as e:
            db.rollback()
            raise e
        
    def create_draw(
        self,
        db: Session,
        draw_type: DrawType = DrawType.automatic,
        numbers: Optional[List[int]] = None,
        bonus_number: Optional[int] = None
    ) -> Draw:
        """
        Creates a draw. If numbers are not provided, will auto-generate based on draw_type.
        """
        try:
            if draw_type == DrawType.manual:
                if not numbers:
                    raise ValueError("Manual draw must include numbers")
                if bonus_number is None:
                    raise ValueError("Manual draw must include bonus number")
            elif draw_type == DrawType.smart_auto:
                numbers, bonus_number = self.generate_smart_numbers(db)
            else:
                numbers, bonus_number = generate_draw_numbers()

            draw = Draw(
                draw_date=datetime.utcnow(),
                numbers=numbers,
                bonus_number=bonus_number,
                draw_type=draw_type,
                status=DrawStatus.completed
            )
            db.add(draw)
            db.commit()
            db.refresh(draw)
            return draw
        except SQLAlchemyError as e:
            db.rollback()
            raise e

    def generate_smart_numbers(self, db: Session) -> Tuple[List[int], int]:
        """
        Example "smart" strategy:
        Pick random numbers that minimize overlap with existing tickets (lower payout risk).
        """
        tickets = db.query(Ticket).all()
        ticket_combos = [tuple(sorted(t.numbers)) for t in tickets]

        # Generate many random combinations and pick one with least overlap
        candidates = []
        for _ in range(2000):  # generate many possibilities
            nums, bonus = generate_draw_numbers()
            candidates.append((nums, bonus))

        # Count how many tickets match each candidate (rough approximation)
        def count_matches(candidate):
            candidate_nums = set(candidate[0])
            return sum(1 for combo in ticket_combos if len(candidate_nums.intersection(combo)) >= 3)

        candidates.sort(key=count_matches)
        return random.choice(candidates[:50])  # pick from top 50 least risky        

    def get_draw(self, db: Session, draw_id: int) -> Optional[Draw]:
        return db.query(Draw).filter(Draw.id == draw_id).first()

    def get_latest_draw(self, db: Session) -> Optional[Draw]:
        return db.query(Draw).order_by(Draw.draw_date.desc()).first()

    def get_all_draws(self, db: Session) -> List[Draw]:
        return db.query(Draw).order_by(Draw.draw_date.desc()).all()

# Export singleton
draw_service = DrawService()
