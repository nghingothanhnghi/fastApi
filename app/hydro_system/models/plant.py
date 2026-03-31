
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Boolean, JSON, Text
from datetime import datetime
from sqlalchemy.orm import relationship
from app.database import Base

class Plant(Base):
    __tablename__ = "plants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)