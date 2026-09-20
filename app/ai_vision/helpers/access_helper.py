# app/ai_vision/helpers/access_helper.py
from fastapi import HTTPException
from app.ai_vision.models.plant import VisionPlant, VisionCamera
from app.user.models.user import User
from app.user.enums.role_enum import RoleEnum


def ensure_plant_access(plant: VisionPlant, current_user: User) -> None:
    """Mirrors hydro_system.controllers.device_controller._ensure_device_access.
    SUPER_ADMIN bypasses; everyone else needs a client_id match. A plant with
    no client_id (legacy/orphaned row) is treated as inaccessible to non-admins
    rather than silently open."""
    if current_user.is_super_admin():
        return
    if plant.client_id is not None and plant.client_id == current_user.client_id:
        return
    raise HTTPException(status_code=403, detail="Not authorized for this plant")


def ensure_camera_access(camera: VisionCamera, current_user: User) -> None:
    if current_user.is_super_admin():
        return
    if camera.client_id is not None and camera.client_id == current_user.client_id:
        return
    raise HTTPException(status_code=403, detail="Not authorized for this camera")