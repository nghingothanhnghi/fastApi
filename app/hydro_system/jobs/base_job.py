# app/hydro_system/jobs/base_job.py

import functools

from app.database import SessionLocal
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def resilient_job(name: str):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            db = SessionLocal()

            try:
                return fn(*args, db=db, **kwargs)

            except Exception as e:
                logger.error(
                    f"[JOB:{name}] Failed: {e}",
                    exc_info=True
                )

                db.rollback()

            finally:
                db.close()

        return wrapper

    return decorator