# transform_data/jobs/transform_job.py
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.migration.models.base_data import RawData
from app.transform_data.schemas.template import TransformRequest
from app.transform_data.services.transformer import transform_data
import logging

logger = logging.getLogger(__name__)

def transform_unprocessed_data():
    db: Session = SessionLocal()
    try:
        items = db.query(RawData).filter_by(processed=False).all()
        logger.info(f"[Job] Found {len(items)} unprocessed records")

        for item in items:
            if not item.client_id:
                logger.warning(f"[Skip] Missing client_id for record ID {item.id}")
                continue

            try:
                req = TransformRequest(client_id=item.client_id, raw_data=item.payload)
                transformed = transform_data(req, db)
                logger.info(f"[✓] Transformed record ID {item.id} (client_id={item.client_id})")

                # Mark as processed
                item.processed = True
                db.commit()

            except ValueError as ve:
                logger.warning(f"[!] Skipping record ID {item.id}: {ve}")
            except Exception as e:
                logger.error(f"[!] Error on record ID {item.id}: {e}")
                db.rollback()
    finally:
        db.close()