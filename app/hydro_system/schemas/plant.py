# app/hydro_system/schemas/plant.py

from pydantic import BaseModel

class PlantCreate(BaseModel):
    name: str
    description: str | None = None


class PlantOut(BaseModel):
    id: int
    name: str

    model_config = {
        "from_attributes": True
    }