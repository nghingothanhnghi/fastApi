# app/migration/models/base_data.py
from sqlalchemy import Column, Integer, JSON, Boolean, String
from app.database import Base

class RawData(Base):
    __tablename__ = "raw_data"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String, index=True)  # Assuming client_id is an integer
    payload = Column(JSON, nullable=False)
    processed = Column(Boolean, default=False)


def __repr__(self):
    return f"<RawData id={self.id} client_id={self.client_id} processed={self.processed}>"    