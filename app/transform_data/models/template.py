# app/transform_data/models/template.py
from sqlalchemy import Column, Integer, String, JSON, DateTime, func
from app.database import Base

class Template(Base):
    __tablename__ = "templates"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String, index=True, unique=True)
    mapping = Column(JSON)  # Defines field mapping rules

    # ✅ Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

def __repr__(self):
    return f"<Template id={self.id} client_id={self.client_id}>"    