# app/hydro_system/services/system_state_service.py

from app.utils.scheduler import get_scheduler_health

class SystemStateService:

    def is_scheduler_running(self) -> bool:
        health = get_scheduler_health()

        return (
            health["scheduler_running"]
            and health["running_count"] > 0
        )

    def get_scheduler_status(self):
        return get_scheduler_health()

system_state_service = SystemStateService()