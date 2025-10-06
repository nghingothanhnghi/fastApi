# app/jackpot/services/draw_service.py
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from app.jackpot.models.draw import Draw, DrawType, DrawStatus, Ticket, PrizeResult
from app.jackpot.utils.helpers import generate_draw_numbers, get_next_draw_date
from app.jackpot.services.rule_service import rule_service
from app.core.logging_config import get_logger
import random

logger = get_logger(__name__)

class DrawService:

    def create_draw(
        self,
        db: Session,
        draw_type: DrawType = DrawType.automatic,
        numbers: Optional[List[int]] = None,
        bonus_number: Optional[int] = None,
        status: DrawStatus = DrawStatus.scheduled,
        draw_date: Optional[datetime] = None,
        current_jackpot1: Optional[float] = None,
        current_jackpot2: Optional[float] = None,
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
                current_jackpot1=current_jackpot1,
                current_jackpot2=current_jackpot2,
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
        - Complete any past scheduled draws that should have happened
        - If latest is completed/expired → schedule a new one in the FUTURE.
        - Always guarantee current draw_date > now.
        """
        rules = rule_service.get_rules()
        now = datetime.utcnow()

        # 🔧 First, complete any past scheduled draws that have passed their time
        past_scheduled_draws = db.query(Draw).filter(
            Draw.status == DrawStatus.scheduled,
            Draw.draw_date <= now
        ).all()

        for draw in past_scheduled_draws:
            logger.info(f"Auto-completing past scheduled draw ID {draw.id} (date: {draw.draw_date})")
            draw.status = DrawStatus.completed
            db.commit()

        latest_completed = self.get_latest_draw(db)
        latest_any = db.query(Draw).order_by(Draw.draw_date.desc()).first()

        # ✅ If there’s already a scheduled draw in the future → return it
        if latest_any and latest_any.status == DrawStatus.scheduled and latest_any.draw_date > now:
            return latest_any

        # Otherwise compute the next future draw date
        base_time = latest_completed.draw_date if latest_completed else now
        next_date = get_next_draw_date(base_time, rules["draw_days"], rules["draw_time"])

        # ✅ Ensure draw_date is strictly in the future
        while next_date <= now:
            next_date = get_next_draw_date(next_date, rules["draw_days"], rules["draw_time"])

        # Calculate jackpots
        base_jackpot1 = rules["jackpot1_min"]
        base_jackpot2 = rules["jackpot2_min"]
        if latest_completed and not self._has_jackpot_winner(db, latest_completed):
            # Rollover jackpots
            base_jackpot1 += float(latest_completed.current_jackpot1)
            base_jackpot2 += float(latest_completed.current_jackpot2)

        return self.create_draw(
            db,
            draw_type=DrawType.automatic,
            numbers=[],
            bonus_number=None,
            status=DrawStatus.scheduled,
            draw_date=next_date,
            current_jackpot1=base_jackpot1,
            current_jackpot2=base_jackpot2,
        )

    def _has_jackpot_winner(self, db: Session, draw: Draw) -> bool:
        """Check if the draw has any Jackpot1 or Jackpot2 winners."""
        return db.query(PrizeResult).filter(
            PrizeResult.ticket_id.in_(
                db.query(Ticket.id).filter(Ticket.draw_id == draw.id)
            ),
            PrizeResult.category.in_(["Jackpot1", "Jackpot2"])
        ).first() is not None
    
    def decide_next_draw_type(self, db: Session) -> Optional[DrawType]:
        """
        Decide which type the next draw should be, based on the last completed draw.
        Returns None if the next draw must be created manually from the frontend.
        """
        latest_draw = self.get_latest_draw(db)
        if not latest_draw:
            return DrawType.automatic

        if latest_draw.draw_type == DrawType.smart_auto:
            return DrawType.smart_auto

        if latest_draw.draw_type == DrawType.manual:
            # Manual draws are only created via frontend
            # return None
            # Manual chỉ áp dụng kỳ hiện tại, kỳ tiếp theo quay lại auto
            return DrawType.automatic

        return DrawType.automatic


# Export singleton
draw_service = DrawService()
