from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# Base schema (for creation if needed later)
class HydroActuatorLogBase(BaseModel):
    actuator_id: int
    action: str
    state: Optional[str] = None
    source: Optional[str] = "user"
    note: Optional[str] = None

# Output schema (for response)
class HydroActuatorLogOut(BaseModel):
    id: int
    timestamp: datetime

    model_config = {
        "from_attributes": True
    }
