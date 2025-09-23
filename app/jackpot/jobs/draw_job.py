# app/jackpot/jobs/draw_job.py
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.jackpot.services.draw_service import draw_service
from app.jackpot.services.rule_service import rule_service
from app.core.logging_config import get_logger

logger = get_logger("jackpot.draw_job")

from datetime import datetime, time, timezone
from tzlocal import get_localzone


def draw_job():
    """
    Scheduled job to create a new jackpot draw on configured days & time (local timezone).
    Avoids duplicate draws for the same local date.
    """
    db: Session = SessionLocal()
    try:
        rules = rule_service.get_rules()
        local_tz = get_localzone()
        now_local = datetime.now(local_tz)
        current_day = now_local.strftime("%A")
        hh, mm = map(int, rules["draw_time"].split(":"))
        draw_time_local = time(hh, mm)

        logger.debug(
            f"[Jackpot] Running draw job — now_local={now_local.isoformat()}, day={current_day}, draw_days={rules['draw_days']}"
        )

        # Only run on allowed days
        if current_day not in rules["draw_days"]:
            logger.debug(f"[Jackpot] Skipping — today={current_day} is not a draw day.")
            return

        # Only run after configured draw time (local)
        if now_local.time() < draw_time_local:
            logger.debug(
                f"[Jackpot] Skipping — current time {now_local.strftime('%H:%M')} < draw time {draw_time_local}."
            )
            return

        # Prevent duplicate draws for today (compare dates in local tz)
        latest_draw = draw_service.get_latest_draw(db)
        if latest_draw:
            # draw_date stored as naive UTC; make it aware then convert to local
            latest_draw_utc = latest_draw.draw_date.replace(tzinfo=timezone.utc)
            if latest_draw_utc.astimezone(local_tz).date() == now_local.date():
                logger.info(
                    f"[Jackpot] Draw already exists for {now_local.date()} (id={latest_draw.id}). Skipping."
                )
                return

        # Create a new draw (stored in UTC)
        new_draw = draw_service.create_draw(db)
        logger.info(
            f"[Jackpot] ✅ Created new draw (id={new_draw.id}) at {new_draw.draw_date.isoformat()}"
        )

    except Exception as e:
        logger.error(f"[Jackpot] ❌ Draw job failed: {e}", exc_info=True)
    finally:
        db.close()
