from fastapi import APIRouter
from app.utils.scheduler import get_scheduler_health

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])

@router.get("/health", summary="Scheduler health check")

def scheduler_health():
    return get_scheduler_health()
