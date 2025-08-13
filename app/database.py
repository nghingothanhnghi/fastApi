# backend/app/database.py
import os
from typing import Generator
from sqlalchemy import create_engine
# from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv

# DATABASE_URL = "sqlite:///./database.db"  # Example for SQLite

# ✅ Load environment variables from .env
load_dotenv()

# ✅ Read database URL from .env
DATABASE_URL = os.getenv("DATABASE_URL")

# ✅ Raise error if not defined
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the .env file")

# ✅ SQLite-specific connect args
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
