from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from app.jackpot.models.draw import Draw
from app.jackpot.utils.helpers import generate_draw_numbers

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

    def get_draw(self, db: Session, draw_id: int) -> Optional[Draw]:
        return db.query(Draw).filter(Draw.id == draw_id).first()

    def get_latest_draw(self, db: Session) -> Optional[Draw]:
        return db.query(Draw).order_by(Draw.draw_date.desc()).first()

    def get_all_draws(self, db: Session) -> List[Draw]:
        return db.query(Draw).order_by(Draw.draw_date.desc()).all()

# Export singleton
draw_service = DrawService()
