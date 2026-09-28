# app/hydro_system/routes/actuator_router.py
# Description: This file contains the routes for hydro actuators.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.user.utils.token import get_current_user
from app.user.models.user import User
from app.hydro_system.schemas.actuator import (
    HydroActuatorCreate,
    HydroActuatorUpdate,
    HydroActuatorOut,
)
from app.hydro_system.services.actuator_service import hydro_actuator_service
from app.hydro_system.services.recipe_engine_service import recipe_engine_service

router = APIRouter(prefix="/actuators", tags=["Hydro - Actuators"])

def _reapply_schedules(db: Session, device_ids) -> None:
    """Regenerate plant_auto schedules for each distinct device, then commit once."""
    for device_id in {d for d in device_ids if d is not None}:
        recipe_engine_service.reapply_for_device(db, device_id)
    db.commit()

@router.post("/", response_model=HydroActuatorOut)
def create_actuator(actuator_in: HydroActuatorCreate, db: Session = Depends(get_db)):
    actuator = hydro_actuator_service.create_actuator(db, actuator_in)
    # A new actuator has no plant_auto schedule until the next stage change
    # unless we re-apply the current stage's recipes now.
    _reapply_schedules(db, [actuator.device_id])
    db.refresh(actuator)
    return actuator

@router.get("/{actuator_id}", response_model=HydroActuatorOut)
def read_actuator(actuator_id: int, db: Session = Depends(get_db)):
    actuator = hydro_actuator_service.get_actuator(db, actuator_id)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    return actuator

@router.get("/device/{device_id}", response_model=list[HydroActuatorOut])
def list_actuators_by_device(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),):
    return hydro_actuator_service.get_actuators_by_device(db, device_id)

def _update_and_reapply(actuator_id: int, actuator_in: HydroActuatorUpdate, db: Session):
    changed = actuator_in.dict(exclude_unset=True)
    actuator = hydro_actuator_service.update_actuator(db, actuator_id, actuator_in)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    # Only type / active-state changes affect which recipes match this actuator
    if "type" in changed or "is_active" in changed:
        _reapply_schedules(db, [actuator.device_id])
        db.refresh(actuator)
    return actuator

@router.put("/{actuator_id}", response_model=HydroActuatorOut)
def update_actuator(actuator_id: int, actuator_in: HydroActuatorUpdate, db: Session = Depends(get_db)):
    return _update_and_reapply(actuator_id, actuator_in, db)

# PATCH is used to partially update an existing resource. It allows you to modify only a subset of fields without affecting other fields.
@router.patch("/{actuator_id}", response_model=HydroActuatorOut)
def patch_actuator(
    actuator_id: int,
    actuator_in: HydroActuatorUpdate,
    db: Session = Depends(get_db)
):
    return _update_and_reapply(actuator_id, actuator_in, db)


@router.delete("/{actuator_id}")
def delete_actuator(actuator_id: int, db: Session = Depends(get_db)):
    # Schedules of the actuator are removed by the ORM cascade.
    actuator = hydro_actuator_service.delete_actuator(db, actuator_id)
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    return {"detail": "Actuator deleted successfully"}

# bulk create feature (instead of posting 4x times)
@router.post("/bulk", response_model=list[HydroActuatorOut])
def create_actuators_bulk(actuators_in: list[HydroActuatorCreate], db: Session = Depends(get_db)):
    created = [hydro_actuator_service.create_actuator(db, actuator) for actuator in actuators_in]
    # Re-apply once per device after ALL actuators exist
    _reapply_schedules(db, [a.device_id for a in created])
    for a in created:
        db.refresh(a)
    return created

