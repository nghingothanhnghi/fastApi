# transform_data/jobs/transform_job.py
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.migration.models.base_data import RawData
from app.transform_data.schemas.template import TransformRequest
from app.transform_data.services.transformer import transform_data
from app.transform_data.services.ai_mapper import suggest_mapping
from app.transform_data.services.template_service import get_template_by_client_id, create_template
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
                # Check for existing template
                template = get_template_by_client_id(db, item.client_id)

                if not template:
                    logger.info(f"[AI] No template found for {item.client_id}, calling AI mapper...")
                    suggested_mapping = suggest_mapping(item.payload, item.client_id)

                    # Save new template using service
                    create_template(db, {
                        "client_id": item.client_id,
                        "mapping": suggested_mapping
                    })
                    logger.info(f"[AI] Suggested and saved mapping for {item.client_id}")
                # Now perform transformation
                req = TransformRequest(client_id=item.client_id, raw_data=item.payload)
                transform_data(req, db)
                logger.info(f"[✓] Transformed record ID {item.id} (client_id={item.client_id})")

                # Mark as processed
                item.processed = True
                db.commit()

                logger.info(f"[✓] Transformed record ID {item.id} (client_id={item.client_id})")

            except ValueError as ve:
                logger.warning(f"[!] Skipping record ID {item.id}: {ve}")
            except Exception as e:
                logger.error(f"[!] Error on record ID {item.id}: {e}")
                db.rollback()
    finally:
        db.close()