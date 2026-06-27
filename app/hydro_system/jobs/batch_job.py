# app/hydro_system/jobs/batch_job.py

from app.hydro_system.jobs.base_job import resilient_job
from app.hydro_system.services.automation_service import automation_service
from app.core.logging_config import get_logger

logger = get_logger(__name__)

@resilient_job("batch_stage_update")
def update_batch_stages(*, db):
    automation_service.run_growth_cycle(db)

    logger.info(
        "Batch stages updated via AutomationService"
    )