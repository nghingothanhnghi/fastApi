# app/ai_vision/helpers/access_helper.py
from typing import Optional, Dict, Any
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai_vision.models.plant import VisionPlant, VisionCamera
from app.ai_vision.repositories.plant_repository import camera_repository
from app.ai_vision.integrations.hydro_batch_client import hydro_batch_client
from app.user.models.user import User


def ensure_plant_access(plant: VisionPlant, current_user: User) -> None:
    """SUPER_ADMIN bypasses; everyone else needs a client_id match. A plant
    with no client_id is inaccessible to non-admins rather than silently open."""
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


def ensure_hydro_device_access(info: Optional[Dict[str, Any]], current_user: User) -> None:
    """Same rule as hydro device_controller._ensure_device_access:
    SUPER_ADMIN, device owner, or same client_id."""
    if info is None:
        raise HTTPException(status_code=404, detail="Hydro device not found")
    if current_user.is_super_admin():
        return
    if info.get("user_id") == current_user.id:
        return
    cid = info.get("client_id")
    if cid is not None and cid == current_user.client_id:
        return
    raise HTTPException(status_code=403, detail="Not authorized for this hydro device")


def ensure_hydro_batch_access(info: Optional[Dict[str, Any]], current_user: User) -> None:
    """A batch has no tenant of its own; ownership is the owner of its zone
    (device). Batches without a zone can't be verified -> admin only."""
    if info is None:
        raise HTTPException(status_code=404, detail="Hydro batch not found")
    if current_user.is_super_admin():
        return
    if info.get("zone_id") is None:
        raise HTTPException(status_code=403, detail="Batch has no zone; ownership cannot be verified")
    if info.get("zone_user_id") == current_user.id:
        return
    cid = info.get("zone_client_id")
    if cid is not None and cid == current_user.client_id:
        return
    raise HTTPException(status_code=403, detail="Not authorized for this hydro batch")


def ensure_links_access(
    db: Session,
    current_user: User,
    *,
    camera_id: Optional[int] = None,
    hydro_device_id: Optional[int] = None,
    hydro_batch_id: Optional[int] = None,
) -> None:
    """Validate every cross-reference a request tries to attach."""
    if camera_id is not None:
        camera = camera_repository.get(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
        ensure_camera_access(camera, current_user)
    if hydro_device_id is not None:
        ensure_hydro_device_access(hydro_batch_client.get_device(db, hydro_device_id), current_user)
    if hydro_batch_id is not None:
        ensure_hydro_batch_access(hydro_batch_client.get_batch_with_plant(db, hydro_batch_id), current_user)