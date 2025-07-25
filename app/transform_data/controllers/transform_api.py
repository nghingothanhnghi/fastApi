# transform_data/controllers/transform_api.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.transform_data.schemas.template import TransformRequest, TransformResponse, SuggestMappingRequest, SuggestMappingResponse
from app.transform_data.services.transformer import transform_data
from app.transform_data.services.ai_mapper import suggest_mapping

router = APIRouter(prefix="/transform", tags=["Transform"])

@router.post("", response_model=TransformResponse)
def transform(req: TransformRequest, db: Session = Depends(get_db)):
    try:
        data = transform_data(req, db)
        return {"transformed_data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Unexpected error occurred during transformation.")
    
@router.post("/suggest-mapping", response_model=SuggestMappingResponse)
async def suggest_mapping_endpoint(req: SuggestMappingRequest):
    mapping = await suggest_mapping(req.raw_data, req.client_id)
    return {
        "client_id": req.client_id,
        "suggested_mapping": mapping
    }