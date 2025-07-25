# app/transform_data/services/template_service.py
from sqlalchemy.orm import Session
from app.transform_data.models.template import Template
from app.transform_data.schemas.template import TemplateCreate, TemplateUpdate
from typing import List


def get_all_templates(db: Session) -> List[Template]:
    return db.query(Template).all()


def get_template_by_client_id(db: Session, client_id: str) -> Template | None:
    return db.query(Template).filter(Template.client_id == client_id).first()


def create_template(db: Session, template_data: TemplateCreate) -> Template:
    if get_template_by_client_id(db, template_data.client_id):
        raise ValueError(f"Template already exists for client_id: {template_data.client_id}")

    template = Template(
        client_id=template_data.client_id,
        mapping=template_data.mapping
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def update_template(db: Session, client_id: str, template_update: TemplateUpdate) -> Template:
    template = get_template_by_client_id(db, client_id)
    if not template:
        return None

    template.mapping = template_update.mapping
    db.commit()
    db.refresh(template)
    return template


def delete_template(db: Session, client_id: str) -> bool:
    template = get_template_by_client_id(db, client_id)
    if not template:
        return False

    db.delete(template)
    db.commit()
    return True
