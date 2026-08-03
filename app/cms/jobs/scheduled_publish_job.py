# app/cms/jobs/scheduled_publish_job.py
# Periodic job: flips any CmsPost with status='scheduled' whose scheduled_at
# has passed over to status='published'. Registered in main.py via
# app.utils.scheduler.add_job(..., seconds=60).

from app.database import SessionLocal
from app.cms.services.post_service import post_service
from app.core.logging_config import get_logger

logger = get_logger("cms.scheduled_publish_job")


def publish_scheduled_posts_job():
    db = SessionLocal()
    try:
        published_count = post_service.publish_due_scheduled_posts(db)
        if published_count:
            logger.info(f"[CMS] Auto-published {published_count} scheduled post(s).")
    except Exception as e:
        logger.error(f"[CMS] Scheduled publish job failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()