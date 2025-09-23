# app/utils/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from tzlocal import get_localzone
import threading
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone=get_localzone())
scheduler_lock = threading.Lock()

KNOWN_JOBS = [
    {"id": "transform_job", "name": "Transform Job"},
    {"id": "sensor_collect_job", "name": "Sensor Collect Job"},
]

JOB_REGISTRY = {}

def get_scheduler_health():
    with scheduler_lock:
        is_running = scheduler.running
        active_ids = {job.id for job in scheduler.get_jobs()}

        jobs_status = []
        running_count = 0
        stopped_count = 0

        for job_id, meta in JOB_REGISTRY.items():
            running = job_id in active_ids
            jobs_status.append({
                "id": job_id,
                "name": meta.get("name", job_id),
                "status": "running" if running else "stopped"
            })
            if running:
                running_count += 1
            else:
                stopped_count += 1

        return {
            "scheduler_running": is_running,
            "jobs": jobs_status,
            "job_count": len(active_ids),
            "running_count": running_count,
            "stopped_count": stopped_count,
        }


def start_scheduler():
    with scheduler_lock:
        if not scheduler.running:
            scheduler.start()
            print("[Scheduler] Started.")

def add_job(func, seconds: int, job_id: str, job_name: str = None):
    with scheduler_lock:
        existing = scheduler.get_job(job_id)
        if existing:
            logger.info(f"[Scheduler] Job '{job_id}' already exists.")
            return

        scheduler.add_job(func, IntervalTrigger(seconds=seconds), id=job_id, replace_existing=True)
        JOB_REGISTRY[job_id] = {
            "id": job_id,
            "name": job_name or job_id
        }
        logger.info(f"[Scheduler] Job '{job_id}' added (every {seconds}s)")


def remove_job(job_id: str):
    with scheduler_lock:
        job = scheduler.get_job(job_id)
        if job:
            scheduler.remove_job(job_id)
            logger.info(f"Removed job '{job_id}'")          


def add_cron_job(func, job_id: str, day_of_week: str, hour: int, minute: int = 0, job_name: str = None):
    """
    Register a job using a cron schedule. Example day_of_week: "tue,thu,sat".
    """
    with scheduler_lock:
        existing = scheduler.get_job(job_id)
        if existing:
            logger.info(f"[Scheduler] Job '{job_id}' already exists.")
            return

        trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
        scheduler.add_job(func, trigger, id=job_id, replace_existing=True)
        JOB_REGISTRY[job_id] = {
            "id": job_id,
            "name": job_name or job_id
        }
        logger.info(f"[Scheduler] Job '{job_id}' added (cron {day_of_week} {hour:02d}:{minute:02d})")