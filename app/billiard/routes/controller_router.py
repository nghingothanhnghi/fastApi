# app/billiard/routes/controller_router.py  (HTTP only)
# Firmware endpoints authenticate with X-Device-Id / X-Device-Key headers
# (NOT the user JWT). /status is for admins/managers using the POS.
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.user.enums.role_enum import RoleEnum
from app.user.models.user import User
from app.user.utils.role_requirements import require_roles
from app.billiard.models import BilliardDevice
from app.billiard.schemas.device import ControllerState, DeviceStatusOut, DeviceRegisterIn, DeviceRegisterOut, HydroCandidateOut
from app.billiard.schemas.event import DeviceEventIn, EventBatchIn, EventBatchResult
from app.billiard.services.device_auth import authenticate_device
from app.billiard.services.device_service import device_service
from app.billiard.services.event_service import event_service

router = APIRouter(prefix="/billiard/controller", tags=["Billiard Controller"])

_manager = require_roles(RoleEnum.ADMIN, RoleEnum.MANAGER)

def get_device(
    x_device_id: str = Header(...),
    x_device_key: str = Header(...),
    db: Session = Depends(get_db),
) -> BilliardDevice:
    return authenticate_device(db, x_device_id, x_device_key)


@router.post("/events", response_model=EventBatchResult)
def post_event(event: DeviceEventIn, db: Session = Depends(get_db), device: BilliardDevice = Depends(get_device)):
    """One live event (button press while online). Same pipeline as /sync."""
    return event_service.ingest(db, device, [event])


@router.post("/sync", response_model=EventBatchResult)
def sync(batch: EventBatchIn, db: Session = Depends(get_db), device: BilliardDevice = Depends(get_device)):
    """Replay the offline queue. Safe to retry: duplicates are acknowledged, not re-applied."""
    if batch.device_id != device.device_id:
        raise HTTPException(403, "device_id does not match credentials")
    return event_service.ingest(db, device, batch.events)


@router.get("/state", response_model=ControllerState)
def get_state(db: Session = Depends(get_db), device: BilliardDevice = Depends(get_device)):
    state = device_service.build_state(db, device)
    db.commit()   # persists last_seen from authentication
    return state


@router.get("/status", response_model=list[DeviceStatusOut])
def get_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(_manager),
):
    out = []
    for d in device_service.list_devices(db, current_user):
        item = DeviceStatusOut.model_validate(d)
        item.status = device_service.effective_status(d)   # offline after 90s of silence
        out.append(item)
    return out

@router.get("/hydro-candidates", response_model=list[HydroCandidateOut])
def hydro_candidates(db: Session = Depends(get_db), current_user: User = Depends(_manager)):
    return device_service.hydro_candidates(db, current_user)

@router.post("/register", response_model=DeviceRegisterOut, status_code=201)
def register(data: DeviceRegisterIn, db: Session = Depends(get_db), current_user: User = Depends(_manager)):
    dev, key = device_service.register(db, data, current_user)
    db.commit()
    db.refresh(dev)
    return DeviceRegisterOut(**DeviceStatusOut.model_validate(dev).model_dump(), api_key=key)
