# app/transform_data/controllers/template_api.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.transform_data.models.template import Template
from app.transform_data.schemas.template import TemplateCreate, TemplateOut, TemplateUpdate

router = APIRouter(prefix="/templates", tags=["Templates"])

@router.post("", response_model=TemplateOut)
def create_template(
    template_data: TemplateCreate,
    db: Session = Depends(get_db)
):
    """Create a new transformation template for a client"""
    # Check if template already exists for this client
    existing = db.query(Template).filter(Template.client_id == template_data.client_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template already exists for client_id: {template_data.client_id}"
        )
    
    template = Template(
        client_id=template_data.client_id,
        mapping=template_data.mapping
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template

@router.get("", response_model=List[TemplateOut])
def get_all_templates(db: Session = Depends(get_db)):
    """Get all transformation templates"""
    return db.query(Template).all()

@router.get("/{client_id}", response_model=TemplateOut)
def get_template(client_id: str, db: Session = Depends(get_db)):
    """Get transformation template for a specific client"""
    template = db.query(Template).filter(Template.client_id == client_id).first()
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
    template = db.query(Template).filter(Template.client_id == client_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found for client_id: {client_id}"
        )
    
    template.mapping = template_update.mapping
    db.commit()
    db.refresh(template)
    return template

@router.delete("/{client_id}")
def delete_template(client_id: str, db: Session = Depends(get_db)):
    """Delete transformation template for a client"""
    template = db.query(Template).filter(Template.client_id == client_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found for client_id: {client_id}"
        )
    
    db.delete(template)
    db.commit()
    return {"detail": f"Template deleted for client_id: {client_id}"}