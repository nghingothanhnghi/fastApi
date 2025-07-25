# app/transform_data/controllers/template_api.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.transform_data.schemas.template import TemplateCreate, TemplateOut, TemplateUpdate
from app.transform_data.services import template_service

router = APIRouter(prefix="/templates", tags=["Templates"])

@router.post("", response_model=TemplateOut)
def create_template(
    template_data: TemplateCreate,
    db: Session = Depends(get_db)
):
    """Create a new transformation template for a client"""
    try:
        return template_service.create_template(db, template_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[TemplateOut])
def get_all_templates(db: Session = Depends(get_db)):
    """Get all transformation templates"""
    return template_service.get_all_templates(db)


@router.get("/{client_id}", response_model=TemplateOut)
def get_template(client_id: str, db: Session = Depends(get_db)):
    """Get transformation template for a specific client"""
    template = template_service.get_template_by_client_id(db, client_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found for client_id: {client_id}"
        )
    return template


@router.put("/{client_id}", response_model=TemplateOut)
def update_template(
    client_id: str,
    template_update: TemplateUpdate,
    db: Session = Depends(get_db)
):
    """Update transformation template for a client"""
    template = template_service.update_template(db, client_id, template_update)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found for client_id: {client_id}"
        )
    return template


@router.delete("/{client_id}")
def delete_template(client_id: str, db: Session = Depends(get_db)):
    """Delete transformation template for a client"""
    success = template_service.delete_template(db, client_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found for client_id: {client_id}"
        )
    return {"detail": f"Template deleted for client_id: {client_id}"}
