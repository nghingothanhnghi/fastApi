# app/migration/services/data_ingestion.py
from sqlalchemy.orm import Session
from app.migration.models.base_data import RawData
from app.migration.schemas.base_data import RawDataIn

def save_data(db: Session, data_in: RawDataIn) -> RawData:
    data = RawData(client_id=data_in.client_id, payload=data_in.payload)
    db.add(data)
    db.commit()
    db.refresh(data)
    return data