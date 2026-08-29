# new tiny table, used only to make bootstrap atomic across any DB engine
from sqlalchemy import Column, Integer
from app.database import Base

class SystemInitLock(Base):
    __tablename__ = "system_init_lock"
    id = Column(Integer, primary_key=True)  # always inserted as id=1