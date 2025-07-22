# app/migration/controllers/ingest_api.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.migration.schemas.base_data import RawDataIn, RawDataOut
from app.migration.services.data_ingestion import save_data

router = APIRouter(prefix="/ingest", tags=["Migration"])

@router.post("/", response_model=RawDataOut)
def ingest_data(data: RawDataIn, db: Session = Depends(get_db)):
    return save_data(db, data)