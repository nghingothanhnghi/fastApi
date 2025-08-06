from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import (
    devices, tap, health, scheduler_health , screen,
)

from app.user.routes import (user_router, roles_router, auth_router, password_reset_router)

from app.camera_object_detection.routes import ( object_detection_router, hardware_detection_router)
from app.camera_object_detection.websocket import router as hardware_ws_router

from app.hydro_system.routes import ( system_router, sensor_router, actuator_router)

from app.middleware.error_handler import catch_exceptions_middleware
from app.core.logging_config import configure_logging
from app.init_db import init_db

from app.migration.controllers import ingest_api
from app.transform_data.controllers import transform_api, template_api

from app.utils.scheduler import start_scheduler, add_job
from app.transform_data.jobs.transform_job import transform_unprocessed_data
from app.hydro_system.scheduler import start_sensor_job
from app.camera_object_detection.websocket.background_tasks import start_hardware_detection_background_tasks

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
app.include_router(auth_router.router)
app.include_router(user_router.router)
app.include_router(roles_router.router)
app.include_router(password_reset_router.router)

app.include_router(devices.router, prefix="/devices", tags=["devices"])
app.include_router(tap.router, prefix="/tap")
app.include_router(health.router, prefix="/health")
app.include_router(screen.router, prefix="/screen")

app.include_router(scheduler_health.router)  # /scheduler/health

# app.include_router(object_detection.router, prefix="/object-detection", tags=["object-detection"])
app.include_router(object_detection_router.router, prefix="/object-detection", tags=["object-detection"])
app.include_router(hardware_detection_router.router, prefix="/hardware-detection", tags=["hardware-detection"])
app.include_router(hardware_ws_router.router, prefix="/hardware-detection", tags=["hardware-detection-websocket"])


# app.include_router(hydro_system.router)  # Handles /hydro/ endpoints
# app.include_router(sensor_data.router)   # Handles /sensor/ endpoints

app.include_router(system_router.router)  # Handles /hydro/ endpoints
app.include_router(sensor_router.router)   # Handles /sensor/ endpoints
app.include_router(actuator_router.router)   # Handles /actuator/ endpoints


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
    
    # Start hardware detection WebSocket background tasks
    import asyncio
    asyncio.create_task(start_hardware_detection_background_tasks())
except Exception as e:
    import logging
    logging.error(f"[Startup Error] Failed to start background jobs: {e}")