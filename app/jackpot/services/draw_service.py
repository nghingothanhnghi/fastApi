# app/jackpot/services/draw_service.py
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from app.jackpot.models.draw import Draw, DrawType, DrawStatus, Ticket
from app.jackpot.utils.helpers import generate_draw_numbers, get_next_draw_date
from app.jackpot.services.rule_service import rule_service
import random

class DrawService:

    def create_draw(
        self,
        db: Session,
        draw_type: DrawType = DrawType.automatic,
        numbers: Optional[List[int]] = None,
        bonus_number: Optional[int] = None,
        status: DrawStatus = DrawStatus.completed,
        draw_date: Optional[datetime] = None,
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
            elif not numbers or bonus_number is None:
                numbers, bonus_number = generate_draw_numbers()

            # Always compute scheduled draw_date if not provided
            if not draw_date:
                rules = rule_service.get_rules()
                draw_date = get_next_draw_date(datetime.utcnow(), rules["draw_days"], rules["draw_time"])

            draw = Draw(
                draw_date=draw_date or datetime.utcnow(),
                numbers=numbers or [],
                bonus_number=bonus_number,
                draw_type=draw_type,
                status=status,
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
        return (
            db.query(Draw)
            .filter(Draw.status == DrawStatus.completed)
            .order_by(Draw.draw_date.desc())
            .first())

    def get_all_draws(self, db: Session) -> List[Draw]:
        return db.query(Draw).order_by(Draw.draw_date.desc()).all()
    

    def get_or_create_current_draw(self, db: Session) -> Draw:
        """
        Ensure there is always a scheduled draw.
        - If DB is empty → create first scheduled draw.
        - If latest is completed or past its draw_date → schedule a new one.
        """
        latest = db.query(Draw).order_by(Draw.draw_date.desc()).first()
        rules = rule_service.get_rules()
        now = datetime.utcnow()

        # No draws yet OR last draw is completed/expired
        if (
            not latest
            or latest.status == DrawStatus.completed
            or latest.status == DrawStatus.cancelled
            or latest.draw_date <= now
        ):
            next_date = get_next_draw_date(now, rules["draw_days"], rules["draw_time"])
            return self.create_draw(
                db,
                draw_type=DrawType.automatic,
                numbers=[],
                bonus_number=None,
                status=DrawStatus.scheduled,
                draw_date=next_date,
            )

        return latest

# Export singleton
draw_service = DrawService()
