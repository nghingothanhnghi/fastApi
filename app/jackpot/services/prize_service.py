# app/jackpot/services/prize_service.py
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import func
from app.jackpot.models.draw import PrizeResult, Ticket, Draw, DrawStatus
from app.jackpot.utils.helpers import count_matches, calculate_jackpot_probabilities
from app.jackpot.services.rule_service import rule_service  # ✅ import rules

class PrizeService:
    def check_ticket(
        self,
        db: Session,
        ticket: Ticket,
        draw: Draw,
    ) -> Optional[PrizeResult]:
        """
        Check a ticket against a completed draw.
        Returns a PrizeResult if ticket wins, otherwise None.
        """
        if draw.status != DrawStatus.completed:
            return None

        matched = count_matches(ticket.numbers, draw.numbers)
        has_bonus = draw.bonus_number in ticket.numbers

        # ✅ fetch rules dynamically from RuleService
        prize_tables = rule_service.get_prize_tables()
        play_type = ticket.play_type or "basic"
        table = prize_tables.get(play_type, {})

        prize_rule = table.get((matched, has_bonus))
        if not prize_rule:
            return None

        # ✅ resolve value: int or lambda
        jackpot1_value = float(draw.current_jackpot1)
        jackpot2_value = float(draw.current_jackpot2)
        if callable(prize_rule):
            try:
                argcount = prize_rule.__code__.co_argcount
                if argcount == 1:
                    # could be jackpot1 OR jackpot2
                    prize_value = prize_rule(jackpot1_value)
                elif argcount == 2:
                    prize_value = prize_rule(jackpot1_value, jackpot2_value)
                else:
                    prize_value = prize_rule(jackpot2_value)
            except Exception:
                return None
        else:
            prize_value = prize_rule

        # ✅ assign category
        if matched == 6 and not has_bonus:
            category = "Jackpot1"
        elif matched == 5 and has_bonus:
            category = "Jackpot2"
        elif matched == 5:
            category = "First"
        elif matched == 4:
            category = "Second"
        elif matched == 3:
            category = "Third"
        else:
            return None  # no prize    

        try:
            result = PrizeResult(
                ticket_id=ticket.id,
                category=category,
                prize_value=prize_value,
            )
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
                func.count(PrizeResult.id),
                func.sum(PrizeResult.prize_value),
            )
            .join(Ticket)
            .join(Draw)
            .filter(Draw.draw_date >= start_date)
            .filter(Draw.status == DrawStatus.completed)  # ✅ only completed draws
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

            
            # new nested structure
            "Jackpot1": {"count": 0, "value": 0.0},
            "Jackpot2": {"count": 0, "value": 0.0},
            "First": {"count": 0, "value": 0.0},
            "Second": {"count": 0, "value": 0.0},
            "Third": {"count": 0, "value": 0.0},

            # totals
            "totals": {"winners": 0, "value": 0.0},
            
            "probabilities": calculate_jackpot_probabilities(
                n=55, k=6, bonus=True
            ),  # ✅ keep theoretical probabilities
        }

        for category, count, total_value in rows:
            count = int(count or 0)
            value = float(total_value or 0.0)

            # ✅ update new nested structure
            if category in summary:
                summary[category]["count"] = count
                summary[category]["value"] = value

            # ✅ update old flat keys for backward compatibility
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

            # ✅ update overall totals
            summary["totals"]["winners"] += count
            summary["totals"]["value"] += value
            summary["totalPrizeValue"] += value  # keep old format in sync

        return summary


# Export singleton
prize_service = PrizeService()
