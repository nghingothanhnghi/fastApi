# app/jackpot/models/draw.py
from sqlalchemy import Column, Integer, DateTime, ForeignKey, Enum, Numeric, ARRAY, String, JSON
from sqlalchemy.orm import relationship
from app.database import Base
import enum

class PlayType(str, enum.Enum):
    basic = "basic"
    bao5 = "bao5"
    bao7 = "bao7"
    bao8 = "bao8"
    bao9 = "bao9"

class Draw(Base):
    __tablename__ = "jackpot_draws"

    id = Column(Integer, primary_key=True, index=True)
    draw_date = Column(DateTime)
    numbers = Column(JSON, nullable=False)
    bonus_number = Column(Integer)

    tickets = relationship("Ticket", back_populates="draw")

class Ticket(Base):
    __tablename__ = "jackpot_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    numbers = Column(JSON, nullable=False)
    play_type = Column(Enum(PlayType))
    draw_id = Column(Integer, ForeignKey("jackpot_draws.id"))

    draw = relationship("Draw", back_populates="tickets")
    result = relationship("PrizeResult", back_populates="ticket", uselist=False)

class PrizeResult(Base):
    __tablename__ = "jackpot_prizes"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("jackpot_tickets.id"))
    category = Column(String)  # Jackpot1, Jackpot2, First, Second, Third
    prize_value = Column(Numeric)

    ticket = relationship("Ticket", back_populates="result")
