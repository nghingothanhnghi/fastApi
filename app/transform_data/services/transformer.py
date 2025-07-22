# app/transform_data/services/transformer.py
from sqlalchemy.orm import Session
from app.transform_data.models.template import Template
from app.transform_data.schemas.template import TransformRequest

def transform_data(req: TransformRequest, db: Session) -> dict:
    template = db.query(Template).filter(Template.client_id == req.client_id).first()
    if not template:
        raise ValueError(f"No template found for client_id: {req.client_id}")

    transformed = {}
    for target_field, source_path in template.mapping.items():
        value = req.raw_data.get(source_path)
        if value is None:
            raise ValueError(f"Missing field '{source_path}' in raw data")
        transformed[target_field] = value

    return transformed