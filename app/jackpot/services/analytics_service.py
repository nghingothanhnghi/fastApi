from sqlalchemy import func
from collections import Counter
from sqlalchemy.orm import Session
from app.jackpot.models.draw import Ticket, Draw
from app.jackpot.services.rule_service import rule_service


class JackpotAnalyticsService:
    def ticket_count_by_draw(self, db: Session):
        rows = (
            db.query(
                Ticket.draw_id,
                func.count(Ticket.id).label("ticket_count"),
                Draw.draw_date
            )
            .join(Draw, Draw.id == Ticket.draw_id)
            .group_by(Ticket.draw_id, Draw.draw_date)
            .order_by(Draw.draw_date.desc())
            .all()
        )
        return [
            {"draw_id": draw_id, "draw_date": draw_date, "ticket_count": count}
            for draw_id, count, draw_date in rows
        ]

    def number_frequency(self, db: Session, limit: int = 10):
        """
        Returns hot and cold numbers across all draws.
        Ensures numbers with zero occurrence are included for cold stats.
        """
        draws = db.query(Draw).all()
        counter = Counter()
        for draw in draws:
            counter.update(draw.numbers)

        # Include zero-count numbers in the population
        number_range = rule_service.get_rules()["number_range"]
        for n in number_range:
            if n not in counter:
                counter[n] = 0

        # Sort for hot and cold
        hot = counter.most_common(limit)
        cold = sorted(counter.items(), key=lambda x: x[1])[:limit]

        return {
            "hot_numbers": [{"number": n, "count": c} for n, c in hot],
            "cold_numbers": [{"number": n, "count": c} for n, c in cold],
        }

    def sales_summary(self, db: Session):
        """
        Returns total tickets and revenue based on unit price from rules (default 10,000 per ticket).
        """
        unit_price = int(rule_service.get_rules().get("min_price", 10000))
        total_tickets = db.query(func.count(Ticket.id)).scalar() or 0
        total_revenue = total_tickets * unit_price
        return {
            "total_tickets": int(total_tickets),
            "unit_price": unit_price,
            "total_revenue": int(total_revenue)
        }

    def suggest_next_numbers(self, db: Session, top_k: int = 20):
        """
        Suggest a set of 6 numbers for the next period using a simple strategy:
        - Prefer less frequent (cold) numbers to diversify outcomes.
        - Avoid duplicating the latest draw numbers.
        """
        # Frequency map (with zeros ensured)
        draws = db.query(Draw).order_by(Draw.draw_date.desc()).all()
        latest_draw_numbers = set(draws[0].numbers) if draws else set()

        counter = Counter()
        for d in draws:
            counter.update(d.numbers)

        number_range = rule_service.get_rules()["number_range"]
        for n in number_range:
            if n not in counter:
                counter[n] = 0

        # Rank by ascending frequency (cold-first), then by number for determinism
        ranked = sorted(counter.items(), key=lambda x: (x[1], x[0]))

        # Take a pool of top_k coldest numbers (default 20), then pick 6 avoiding latest draw numbers
        pool = [n for n, c in ranked[:max(top_k, 6)] if n not in latest_draw_numbers]
        # Fallback if pool too small
        if len(pool) < 6:
            # Fill from remainder while still avoiding duplicates
            remainder = [n for n, _ in ranked if n not in latest_draw_numbers and n not in pool]
            pool.extend(remainder)

        suggestion = sorted(pool[:6])
        return {
            "suggested_numbers": suggestion,
            "strategy": "cold-first (avoid latest draw)",
        }


jackpot_analytics_service = JackpotAnalyticsService()