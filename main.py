from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import (
    devices, tap, health, scheduler_health , screen, object_detection, 
    hydro_system, sensor_data, user, auth, password_reset, roles
)

from app.middleware.error_handler import catch_exceptions_middleware
from app.core.logging_config import configure_logging
from app.init_db import init_db

from app.migration.controllers import ingest_api
from app.transform_data.controllers import transform_api, template_api

from app.utils.scheduler import start_scheduler, add_job
from app.transform_data.jobs.transform_job import transform_unprocessed_data
from app.hydro_system.scheduler import start_sensor_job

app = FastAPI()

# -----------------------------------------
# Initialization
# -----------------------------------------
init_db()
configure_logging()

# -----------------------------------------
# Middleware
# -----------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or restrict to frontend URL, Change to specific domain in production
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(catch_exceptions_middleware)

# -----------------------------------------
# Routers
# -----------------------------------------
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(roles.router)
app.include_router(password_reset.router)

app.include_router(devices.router, prefix="/devices", tags=["devices"])
app.include_router(tap.router, prefix="/tap")
app.include_router(health.router, prefix="/health")
app.include_router(screen.router, prefix="/screen")

app.include_router(scheduler_health.router)  # /scheduler/health

app.include_router(object_detection.router, prefix="/object-detection", tags=["object-detection"])

app.include_router(hydro_system.router)  # Handles /hydro/ endpoints
app.include_router(sensor_data.router)   # Handles /sensor/ endpoints

app.include_router(ingest_api.router)
app.include_router(transform_api.router)
app.include_router(template_api.router)

# -----------------------------------------
# Scheduler Jobs
# -----------------------------------------
try:
    start_scheduler()  # Start global scheduler
    start_sensor_job() # Register hydro system sensor job
    add_job(transform_unprocessed_data, seconds=10, job_id="transform_job") # Register data transformation job
except Exception as e:
    import logging
    logging.error(f"[Startup Error] Failed to start background jobs: {e}")