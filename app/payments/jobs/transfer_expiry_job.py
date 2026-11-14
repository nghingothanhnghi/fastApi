# app/payments/jobs/transfer_expiry_job.py
# Cancels bank-transfer lines whose QR expired long ago and were never paid, so a bill does
# not stay "pending" forever. Registered in main.py (see config.TRANSFER_AUTO_CANCEL_GRACE_MINUTES).
import logging

from app.database import SessionLocal
from app.payments.services.order_service import payment_order_service

logger = logging.getLogger(__name__)


def expire_stale_transfer_lines_job() -> None:
    db = SessionLocal()
    try:
        cancelled = payment_order_service.expire_stale_transfer_lines(db)
        if cancelled:
            logger.info("[Payments] Cancelled %s expired bank-transfer line(s).", cancelled)
    except Exception as e:
        logger.error("[Payments] Transfer expiry job failed: %s", e, exc_info=True)
        db.rollback()
    finally:
        db.close()
