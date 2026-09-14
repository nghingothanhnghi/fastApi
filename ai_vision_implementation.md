# AIoT Plant Vision Module — Implementation Plan + V1 Scaffold

## 0. What already exists (inspected)

- `app/ai_vision/**` — folder skeleton already present, every file empty. This is where the module belongs.
- Conventions used everywhere else in the repo that this module must follow:
  - Singleton service instances: `thing_service = ThingService()` at the bottom of each service file.
  - Schemas: `model_config = {"from_attributes": True}`, split into `*Base` / `*Create` / `*Update` / `*Out`.
  - `Depends(get_db)` from `app.database`, `get_logger(__name__)` from `app.core.logging_config`.
  - Background jobs: `app/utils/scheduler.add_job(...)` + the `resilient_job` decorator pattern (`app/hydro_system/jobs/base_job.py`) which opens/closes its own `SessionLocal()`.
  - Routers: plain `APIRouter(prefix=..., tags=[...])`, included in `main.py`.
  - `app/init_db.py` imports every model module once so `Base.metadata.create_all` picks it up.
- Reusable pieces this module must **not** duplicate:
  - Sensor data: `app.hydro_system.models.sensor_data.SensorData`
  - Flow telemetry: `app.hydro_system.services.flow_reading_service.flow_reading_service`
  - Irrigation sessions: `app.hydro_system.services.irrigation_session_service`
  - Auth: `app.user.utils.token.get_current_user`
  - Devices/locations: `app.hydro_system.models.device.HydroDevice`

## 1. Phasing (per the roadmap in the brief)

| Phase | Scope | Status here |
|---|---|---|
| V1 | Plant/camera CRUD, image ingestion + storage abstraction, mock detector, growth tracking, health scoring, sensor fusion, background inference job, REST API | **Implemented below** |
| V2 | Real leaf-health model, debounced anomaly detection with persisted baselines | Interfaces stubbed (`AnomalyService`, `PlantAnomaly` model), logic is intentionally simple (z-score vs rolling baseline) so it can be swapped |
| V3 | Disease/pest classifier | Slot exists: implement another `PlantVisionModel` subclass and register it in `InferenceManager.MODEL_REGISTRY` |
| V4 | Deeper sensor+vision fusion | `SensorFusionService.get_window()` is the extension point |
| V5–V7 | Growth prediction, AI-assisted irrigation/nutrient optimization | Out of scope for V1; `AIRecommendation` + `AutomationPolicy` boundary is designed so these only ever *recommend*, never call actuators directly |

## 2. Safety boundary (section 10 of the brief)

```
AI inference → VisionPrediction/PlantHealthRecord/PlantGrowthRecord/PlantAnomaly
                      → RecommendationService → AIRecommendation (status=pending)
                            → (future) AutomationPolicyService → existing irrigation_session_service / actuator_controller
```

**V1 ships only the top half.** `AIRecommendation` rows are always `status="pending_review"` and there is no code path from this module into `actuator_controller`, `hydro_schedule_service`, or `irrigation_session_service`'s write paths. That wiring is a deliberate, separate PR once a human has reviewed recommendation quality (per "Initially make AI automation recommendation-only").

## 3. Final file layout

```
app/ai_vision/
├── config.py
├── models/
│   ├── plant.py            Plant, Camera
│   ├── image.py            PlantImage
│   ├── vision_prediction.py VisionPrediction
│   ├── plant_health.py     PlantHealthRecord
│   ├── plant_growth.py     PlantGrowthRecord
│   ├── plant_anomaly.py    PlantAnomaly
│   ├── ai_recommendation.py AIRecommendation
│   └── inference_job.py    AIInferenceJob
├── schemas/                (mirrors models 1:1)
├── repositories/
│   ├── plant_repository.py
│   └── image_repository.py
├── ai/
│   ├── base/vision_model.py        PlantVisionModel (ABC)
│   └── inference/
│       ├── detector.py             MockYOLOPlantDetector
│       ├── classifier.py           MockLeafHealthClassifier
│       └── inference_manager.py    InferenceManager (model registry + versioning)
├── integrations/
│   ├── storage_client.py           ImageStorageService (ABC) + LocalImageStorage
│   ├── hydroponic_client.py        SensorFusionService (wraps existing SensorData/flow_reading_service)
│   └── camera_client.py            fetch_image_from_camera() stub for ESP32-CAM/IP cameras
├── services/
│   ├── plant_service.py
│   ├── image_service.py
│   ├── vision_service.py
│   ├── growth_service.py
│   ├── health_service.py
│   ├── anomaly_service.py
│   ├── recommendation_service.py
│   └── sensor_fusion_service.py    thin re-export of integrations.hydroponic_client
├── controllers/
│   ├── plant_controller.py
│   └── vision_controller.py
├── jobs/
│   └── inference_job.py            polls queued AIInferenceJob rows, runs pipeline
└── routes/
    ├── plant_router.py
    ├── image_router.py
    ├── inference_router.py
    ├── health_router.py
    └── recommendation_router.py
```

---

## 4. Code

### `app/ai_vision/config.py`

```python
# app/ai_vision/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() in ("true", "1", "yes")
AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "plant-detector")
AI_MODEL_VERSION = os.getenv("AI_MODEL_VERSION", "v1")
AI_CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.60"))

PLANT_HEALTH_WARNING_THRESHOLD = int(os.getenv("PLANT_HEALTH_WARNING_THRESHOLD", "70"))
PLANT_HEALTH_CRITICAL_THRESHOLD = int(os.getenv("PLANT_HEALTH_CRITICAL_THRESHOLD", "50"))

GROWTH_ANOMALY_THRESHOLD = float(os.getenv("GROWTH_ANOMALY_THRESHOLD", "0.30"))  # 30% deviation from baseline
SENSOR_WINDOW_MINUTES = int(os.getenv("AI_SENSOR_WINDOW_MINUTES", "15"))

IMAGE_MAX_SIZE_MB = int(os.getenv("IMAGE_MAX_SIZE_MB", "10"))
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Storage — local by default, swappable via ImageStorageService
AI_VISION_STORAGE_BACKEND = os.getenv("AI_VISION_STORAGE_BACKEND", "local")  # local | s3 | minio
AI_VISION_IMAGE_DIR = os.getenv("AI_VISION_IMAGE_DIR", "uploads/ai_vision")
AI_VISION_IMAGE_URL = os.getenv("AI_VISION_IMAGE_URL", "/static/ai_vision")

Path(AI_VISION_IMAGE_DIR).mkdir(parents=True, exist_ok=True)
```

### Models

```python
# app/ai_vision/models/plant.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean, func
from sqlalchemy.orm import relationship
from app.database import Base


class Camera(Base):
    __tablename__ = "ai_vision_cameras"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    camera_type = Column(String(30), nullable=False, default="ip_camera")  # ip_camera | esp32_cam | upload
    stream_url = Column(String(500), nullable=True)
    location = Column(String(150), nullable=True)  # matches HydroDevice.location for correlation
    hydro_device_id = Column(Integer, ForeignKey("devices_hydro.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    plants = relationship("Plant", back_populates="camera")


class Plant(Base):
    __tablename__ = "ai_vision_plants"

    id = Column(Integer, primary_key=True, index=True)
    species = Column(String(100), nullable=False)
    variety = Column(String(100), nullable=True)
    location = Column(String(150), nullable=True)
    growing_system = Column(String(50), nullable=True)  # nft, dwc, ebb_flow, aeroponic...
    planted_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(30), nullable=False, default="growing")  # growing|harvested|removed

    # Optional link into the existing hydro batch/plant metadata, so vision
    # data can be correlated with GrowthStage/GrowthRecipe without duplicating them.
    hydro_plant_id = Column(Integer, ForeignKey("plants.id"), nullable=True)
    hydro_batch_id = Column(Integer, ForeignKey("plant_batches.id"), nullable=True)

    camera_id = Column(Integer, ForeignKey("ai_vision_cameras.id"), nullable=True)
    camera = relationship("Camera", back_populates="plants")

    expected_growth_profile = Column(JSON, nullable=True)  # e.g. {"canopy_growth_pct_per_day": 3.8}

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Plant(id={self.id}, species={self.species!r}, status={self.status})>"
```

```python
# app/ai_vision/models/image.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from app.database import Base


class PlantImage(Base):
    __tablename__ = "ai_vision_images"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)
    camera_id = Column(Integer, ForeignKey("ai_vision_cameras.id"), nullable=True)

    storage_path = Column(String(500), nullable=False)   # relative/backend key, never a full-res DB blob
    public_url = Column(String(500), nullable=True)
    image_hash = Column(String(64), nullable=True, index=True)  # sha256, for de-dupe
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    content_type = Column(String(50), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)

    processing_status = Column(String(20), nullable=False, default="uploaded", index=True)
    # uploaded -> queued -> processing -> completed -> failed

    captured_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<PlantImage(id={self.id}, plant_id={self.plant_id}, status={self.processing_status})>"
```

```python
# app/ai_vision/models/inference_job.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, func
from app.database import Base


class AIInferenceJob(Base):
    __tablename__ = "ai_vision_inference_jobs"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("ai_vision_images.id"), nullable=False, index=True)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(30), nullable=False)

    status = Column(String(20), nullable=False, default="queued", index=True)
    # queued | processing | completed | failed
    error_message = Column(Text, nullable=True)

    queued_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<AIInferenceJob(id={self.id}, image_id={self.image_id}, status={self.status})>"
```

```python
# app/ai_vision/models/vision_prediction.py
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, JSON, func
from app.database import Base


class VisionPrediction(Base):
    """Raw model output for one image. One image can have multiple predictions
    (e.g. a detector run and a health-classifier run)."""
    __tablename__ = "ai_vision_predictions"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("ai_vision_images.id"), nullable=False, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)

    model_name = Column(String(100), nullable=False)
    model_version = Column(String(30), nullable=False)
    task = Column(String(30), nullable=False)  # detection | health | growth

    confidence = Column(Float, nullable=True)
    inference_time_ms = Column(Float, nullable=True)

    # Structured, model-agnostic payload, e.g.
    # {"bbox": [...], "canopy_area_px": 41233, "leaf_color_index": 0.62, "damaged_regions": []}
    raw_output = Column(JSON, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

```python
# app/ai_vision/models/plant_growth.py
from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, func
from app.database import Base


class PlantGrowthRecord(Base):
    __tablename__ = "ai_vision_growth_records"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)
    image_id = Column(Integer, ForeignKey("ai_vision_images.id"), nullable=True)

    canopy_area_px = Column(Float, nullable=True)
    estimated_size_cm2 = Column(Float, nullable=True)
    leaf_count = Column(Integer, nullable=True)

    growth_pct_since_last = Column(Float, nullable=True)   # vs the previous record for this plant
    growth_rate_pct_per_day = Column(Float, nullable=True)
    baseline_growth_rate_pct_per_day = Column(Float, nullable=True)
    deviation_from_baseline_pct = Column(Float, nullable=True)

    model_version = Column(Float, nullable=True)  # kept simple; see VisionPrediction for full versioning
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

```python
# app/ai_vision/models/plant_health.py
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, JSON, func
from app.database import Base


class PlantHealthRecord(Base):
    __tablename__ = "ai_vision_health_records"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)
    image_id = Column(Integer, ForeignKey("ai_vision_images.id"), nullable=True)

    health_score = Column(Integer, nullable=False)  # 0-100
    status = Column(String(20), nullable=False, index=True)
    # healthy | normal | attention | warning | critical | unknown

    visual_indicators = Column(JSON, nullable=True)   # ["leaf_yellowing", "canopy_reduction"]
    possible_issues = Column(JSON, nullable=True)      # [{"issue": "...", "confidence": 0.7}]
    sensor_snapshot = Column(JSON, nullable=True)      # {"ph": 6.1, "ec": 1.8, "temperature": 27.2, ...}

    confidence = Column(Float, nullable=True)
    model_name = Column(String(100), nullable=True)
    model_version = Column(String(30), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

```python
# app/ai_vision/models/plant_anomaly.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, JSON, func
from app.database import Base


class PlantAnomaly(Base):
    __tablename__ = "ai_vision_anomalies"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)

    anomaly_type = Column(String(50), nullable=False)
    # growth_slowdown | abnormal_water_consumption | abnormal_flow | visual_change | sensor_deviation

    severity = Column(String(20), nullable=False, default="medium")  # low|medium|high
    description = Column(String(500), nullable=True)
    evidence = Column(JSON, nullable=True)   # the numbers that triggered it

    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    is_resolved = Column(Boolean, default=False)

    def __repr__(self):
        return f"<PlantAnomaly(plant_id={self.plant_id}, type={self.anomaly_type}, severity={self.severity})>"
```

```python
# app/ai_vision/models/ai_recommendation.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, func
from app.database import Base


class AIRecommendation(Base):
    __tablename__ = "ai_vision_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("ai_vision_plants.id"), nullable=False, index=True)
    health_record_id = Column(Integer, ForeignKey("ai_vision_health_records.id"), nullable=True)
    anomaly_id = Column(Integer, ForeignKey("ai_vision_anomalies.id"), nullable=True)

    recommendation = Column(String(500), nullable=False)
    reasons = Column(JSON, nullable=False)   # list[str] — must always be non-empty (explainability requirement)
    severity = Column(String(20), nullable=False, default="low")
    confidence = Column(Float, nullable=True)

    # Deliberately never "approved_and_executed" in V1 — see safety boundary in the plan.
    status = Column(String(30), nullable=False, default="pending_review")
    # pending_review | acknowledged | dismissed

    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

```python
# app/ai_vision/models/__init__.py
from .plant import Plant, Camera
from .image import PlantImage
from .inference_job import AIInferenceJob
from .vision_prediction import VisionPrediction
from .plant_growth import PlantGrowthRecord
from .plant_health import PlantHealthRecord
from .plant_anomaly import PlantAnomaly
from .ai_recommendation import AIRecommendation

__all__ = [
    "Plant", "Camera", "PlantImage", "AIInferenceJob", "VisionPrediction",
    "PlantGrowthRecord", "PlantHealthRecord", "PlantAnomaly", "AIRecommendation",
]
```

**Wire into `app/init_db.py`** (add alongside the existing imports):
```python
from .ai_vision.models import (
    Plant, Camera, PlantImage, AIInferenceJob, VisionPrediction,
    PlantGrowthRecord, PlantHealthRecord, PlantAnomaly, AIRecommendation,
)
```

### Schemas (representative — repeat the pattern for the rest)

```python
# app/ai_vision/schemas/plant_schema.py
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class CameraCreate(BaseModel):
    name: str
    camera_type: str = "ip_camera"
    stream_url: Optional[str] = None
    location: Optional[str] = None
    hydro_device_id: Optional[int] = None


class CameraOut(CameraCreate):
    id: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PlantCreate(BaseModel):
    species: str
    variety: Optional[str] = None
    location: Optional[str] = None
    growing_system: Optional[str] = None
    planted_at: Optional[datetime] = None
    camera_id: Optional[int] = None
    hydro_plant_id: Optional[int] = None
    hydro_batch_id: Optional[int] = None
    expected_growth_profile: Optional[Dict[str, Any]] = None


class PlantUpdate(BaseModel):
    status: Optional[str] = None
    camera_id: Optional[int] = None
    expected_growth_profile: Optional[Dict[str, Any]] = None


class PlantOut(PlantCreate):
    id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
```

```python
# app/ai_vision/schemas/image_schema.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PlantImageOut(BaseModel):
    id: int
    plant_id: int
    camera_id: Optional[int]
    public_url: Optional[str]
    width: Optional[int]
    height: Optional[int]
    processing_status: str
    captured_at: datetime

    model_config = {"from_attributes": True}


class InferenceJobOut(BaseModel):
    id: int
    image_id: int
    model_name: str
    model_version: str
    status: str
    error_message: Optional[str] = None
    queued_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
```

```python
# app/ai_vision/schemas/health_schema.py
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class PlantHealthOut(BaseModel):
    plant_id: int
    health_score: int
    status: str
    visual_indicators: List[str] = []
    possible_issues: List[Dict[str, Any]] = []
    sensor_snapshot: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
```

```python
# app/ai_vision/schemas/growth_schema.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PlantGrowthOut(BaseModel):
    plant_id: int
    canopy_area_px: Optional[float]
    growth_pct_since_last: Optional[float]
    growth_rate_pct_per_day: Optional[float]
    baseline_growth_rate_pct_per_day: Optional[float]
    deviation_from_baseline_pct: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}
```

```python
# app/ai_vision/schemas/anomaly_schema.py
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class PlantAnomalyOut(BaseModel):
    id: int
    plant_id: int
    anomaly_type: str
    severity: str
    description: Optional[str]
    evidence: Optional[Dict[str, Any]]
    detected_at: datetime
    is_resolved: bool

    model_config = {"from_attributes": True}
```

```python
# app/ai_vision/schemas/recommendation_schema.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AIRecommendationOut(BaseModel):
    id: int
    plant_id: int
    recommendation: str
    reasons: List[str]
    severity: str
    confidence: Optional[float]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

### `app/ai_vision/repositories/plant_repository.py`

```python
# app/ai_vision/repositories/plant_repository.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.ai_vision.models.plant import Plant, Camera


class PlantRepository:
    def create(self, db: Session, **kwargs) -> Plant:
        plant = Plant(**kwargs)
        db.add(plant)
        db.commit()
        db.refresh(plant)
        return plant

    def get(self, db: Session, plant_id: int) -> Optional[Plant]:
        return db.query(Plant).filter(Plant.id == plant_id).first()

    def get_all(self, db: Session, status: Optional[str] = None) -> List[Plant]:
        query = db.query(Plant)
        if status:
            query = query.filter(Plant.status == status)
        return query.order_by(Plant.created_at.desc()).all()

    def update(self, db: Session, plant_id: int, updates: dict) -> Optional[Plant]:
        plant = self.get(db, plant_id)
        if not plant:
            return None
        for k, v in updates.items():
            setattr(plant, k, v)
        db.commit()
        db.refresh(plant)
        return plant


class CameraRepository:
    def create(self, db: Session, **kwargs) -> Camera:
        camera = Camera(**kwargs)
        db.add(camera)
        db.commit()
        db.refresh(camera)
        return camera

    def get(self, db: Session, camera_id: int) -> Optional[Camera]:
        return db.query(Camera).filter(Camera.id == camera_id).first()

    def get_all(self, db: Session) -> List[Camera]:
        return db.query(Camera).filter(Camera.is_active == True).all()


plant_repository = PlantRepository()
camera_repository = CameraRepository()
```

### AI abstraction layer

```python
# app/ai_vision/ai/base/vision_model.py
from abc import ABC, abstractmethod
from typing import Dict, Any
import numpy as np


class PlantVisionModel(ABC):
    """Every AI model (detector, health classifier, disease classifier...)
    implements this so InferenceManager can swap versions without touching
    any caller. Never call this directly from a router — go through
    InferenceManager so model_name/model_version get recorded consistently."""

    name: str
    version: str
    task: str  # "detection" | "health" | "growth" | "disease"

    @abstractmethod
    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        """Return a JSON-serializable dict. Must include a 'confidence' key."""
        raise NotImplementedError
```

```python
# app/ai_vision/ai/inference/detector.py
import time
import numpy as np
from typing import Dict, Any
from app.ai_vision.ai.base.vision_model import PlantVisionModel


class MockYOLOPlantDetector(PlantVisionModel):
    """Placeholder detector. Swap this for a real Ultralytics YOLO model
    (see app/camera_object_detection/controllers/detector.py for the
    existing YOLO-loading pattern already used elsewhere in this repo)
    without changing anything downstream — InferenceManager only depends
    on `predict()`'s return shape."""

    name = "plant-detector"
    version = "v1-mock"
    task = "detection"

    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        h, w = image.shape[:2]
        # Deterministic-ish placeholder so growth tracking has *something*
        # consistent to diff against until a real model is plugged in.
        canopy_area_px = float((image.mean() / 255.0) * (h * w) * 0.4)
        return {
            "confidence": 0.75,
            "bbox": [0, 0, w, h],
            "canopy_area_px": canopy_area_px,
            "leaf_count": None,  # unreliable without a real model — report None, not a guess
            "image_width": w,
            "image_height": h,
        }
```

```python
# app/ai_vision/ai/inference/classifier.py
import numpy as np
from typing import Dict, Any
from app.ai_vision.ai.base.vision_model import PlantVisionModel


class MockLeafHealthClassifier(PlantVisionModel):
    name = "plant-health"
    version = "v1-mock"
    task = "health"

    def predict(self, image: np.ndarray) -> Dict[str, Any]:
        # Placeholder color heuristic: greener average pixel -> healthier.
        # Replace with a trained classifier's output; keep the same keys.
        avg_bgr = image.reshape(-1, 3).mean(axis=0) if image.ndim == 3 else [0, 0, 0]
        green_ratio = float(avg_bgr[1] / (sum(avg_bgr) + 1e-6))

        visual_indicators = []
        if green_ratio < 0.30:
            visual_indicators.append("leaf_yellowing")

        return {
            "confidence": 0.65,
            "leaf_color_index": green_ratio,
            "visual_indicators": visual_indicators,
            "possible_issues": (
                [{"issue": "possible_nutrient_deficiency", "confidence": 0.4}]
                if "leaf_yellowing" in visual_indicators else []
            ),
        }
```

```python
# app/ai_vision/ai/inference/inference_manager.py
import time
import numpy as np
from typing import Dict, Any, List
from app.ai_vision.ai.inference.detector import MockYOLOPlantDetector
from app.ai_vision.ai.inference.classifier import MockLeafHealthClassifier
from app.ai_vision.ai.base.vision_model import PlantVisionModel
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class InferenceManager:
    """Central place that knows which model version is 'current' for each
    task. Swapping plant-detector v1 -> v2 means changing MODEL_REGISTRY,
    not any service/router. Every result is timestamped with the exact
    model_name/model_version used, per the model-versioning requirement."""

    MODEL_REGISTRY: Dict[str, PlantVisionModel] = {
        "detection": MockYOLOPlantDetector(),
        "health": MockLeafHealthClassifier(),
    }

    def run(self, task: str, image: np.ndarray) -> Dict[str, Any]:
        model = self.MODEL_REGISTRY.get(task)
        if not model:
            raise ValueError(f"No model registered for task '{task}'")

        start = time.time()
        output = model.predict(image)
        elapsed_ms = (time.time() - start) * 1000

        return {
            "model_name": model.name,
            "model_version": model.version,
            "task": task,
            "inference_time_ms": elapsed_ms,
            "confidence": output.get("confidence"),
            "raw_output": output,
        }

    def run_all(self, tasks: List[str], image: np.ndarray) -> List[Dict[str, Any]]:
        return [self.run(task, image) for task in tasks]


inference_manager = InferenceManager()
```

### Storage + sensor fusion integrations

```python
# app/ai_vision/integrations/storage_client.py
import os
import hashlib
import shutil
from abc import ABC, abstractmethod
from uuid import uuid4
from fastapi import UploadFile, HTTPException, status
from app.ai_vision import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ImageStorageService(ABC):
    @abstractmethod
    def save(self, file: UploadFile) -> dict:
        """Returns {"storage_path", "public_url", "file_size_bytes", "image_hash"}"""
        raise NotImplementedError


class LocalImageStorage(ImageStorageService):
    """Same shape as app/product/services/image_service.py's approach —
    kept here rather than reused directly because the target directory,
    URL prefix, and validation rules are AI-vision-specific."""

    def save(self, file: UploadFile) -> dict:
        if not file or not file.filename:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No file provided")
        if file.content_type not in config.ALLOWED_IMAGE_MIME_TYPES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported content type '{file.content_type}'")

        ext = os.path.splitext(file.filename)[1] or ".jpg"
        filename = f"{uuid4().hex}{ext}"
        file_path = os.path.join(config.AI_VISION_IMAGE_DIR, filename)

        file.file.seek(0, os.SEEK_END)
        size_bytes = file.file.tell()
        file.file.seek(0)
        if size_bytes > config.IMAGE_MAX_SIZE_MB * 1024 * 1024:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Image exceeds {config.IMAGE_MAX_SIZE_MB}MB limit")

        hasher = hashlib.sha256()
        try:
            with open(file_path, "wb") as buffer:
                for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
                    hasher.update(chunk)
                    buffer.write(chunk)
        except Exception:
            logger.exception("Failed to save AI vision image", extra={"path": file_path})
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Unable to save image")

        return {
            "storage_path": file_path,
            "public_url": f"{config.AI_VISION_IMAGE_URL.rstrip('/')}/{filename}",
            "file_size_bytes": size_bytes,
            "image_hash": hasher.hexdigest(),
        }


def get_image_storage_service() -> ImageStorageService:
    # Swap on config.AI_VISION_STORAGE_BACKEND when S3/MinIO backends are added.
    return LocalImageStorage()


image_storage_service = get_image_storage_service()
```

```python
# app/ai_vision/integrations/hydroponic_client.py
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.hydro_system.models.sensor_data import SensorData
from app.hydro_system.models.device import HydroDevice
from app.hydro_system.services.flow_reading_service import flow_reading_service
from app.ai_vision import config


class SensorFusionService:
    """Reuses the existing hydro_system sensor/flow infrastructure — does not
    duplicate SensorData or HydroFlowReading. This is the only place the
    ai_vision module reaches into hydro_system's data layer."""

    def get_window(
        self, db: Session, location: Optional[str], timestamp: datetime
    ) -> Dict[str, Any]:
        """Average sensor readings in the window ending at `timestamp`,
        for whichever hydro device matches the camera's location."""
        window_start = timestamp - timedelta(minutes=config.SENSOR_WINDOW_MINUTES)

        query = db.query(SensorData).filter(
            SensorData.created_at >= window_start,
            SensorData.created_at <= timestamp,
        )
        if location:
            query = query.join(HydroDevice, SensorData.device_id == HydroDevice.id).filter(
                HydroDevice.location == location
            )

        readings = query.all()
        if not readings:
            return {}

        def avg(field):
            values = [getattr(r, field) for r in readings if getattr(r, field) is not None]
            return round(sum(values) / len(values), 2) if values else None

        snapshot = {
            "window_start": window_start,
            "window_end": timestamp,
            "temperature": avg("temperature"),
            "humidity": avg("humidity"),
            "light": avg("light"),
            "moisture": avg("moisture"),
            "water_level": avg("water_level"),
            "ec": avg("ec"),
            "ppm": avg("ppm"),
        }

        device_ids = {r.device_id for r in readings if r.device_id}
        flow_rates = []
        for device_id in device_ids:
            flow_map = flow_reading_service.get_latest_for_device(db, device_id)
            flow_rates.extend(flow_map.values() if isinstance(flow_map, dict) else [])
        if flow_rates:
            snapshot["flow_rate"] = round(sum(flow_rates) / len(flow_rates), 2)

        return snapshot


sensor_fusion_service = SensorFusionService()
```

```python
# app/ai_vision/integrations/camera_client.py
import numpy as np
import cv2
from typing import Optional
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def load_image_from_path(storage_path: str) -> Optional[np.ndarray]:
    img = cv2.imread(storage_path)
    if img is None:
        logger.error(f"Could not decode image at {storage_path}")
    return img


def fetch_image_from_camera(stream_url: str) -> Optional[np.ndarray]:
    """Stub for pulling a single frame from an ESP32-CAM/IP camera snapshot
    endpoint. Wire this up the same way app/android_system's device_manager
    talks to hardware — i.e. behind a client object, mockable via
    USE_MOCK_DEVICES-style flag, once real camera hardware is available."""
    raise NotImplementedError("Live camera pull not wired up yet — use image upload for now")
```

### Services

```python
# app/ai_vision/services/plant_service.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.ai_vision.repositories.plant_repository import plant_repository, camera_repository
from app.ai_vision.models.plant import Plant, Camera


class PlantService:
    def create_plant(self, db: Session, **kwargs) -> Plant:
        return plant_repository.create(db, **kwargs)

    def get_plant(self, db: Session, plant_id: int) -> Optional[Plant]:
        return plant_repository.get(db, plant_id)

    def get_all_plants(self, db: Session, status: Optional[str] = None) -> List[Plant]:
        return plant_repository.get_all(db, status)

    def update_plant(self, db: Session, plant_id: int, updates: dict) -> Optional[Plant]:
        return plant_repository.update(db, plant_id, updates)

    def create_camera(self, db: Session, **kwargs) -> Camera:
        return camera_repository.create(db, **kwargs)

    def get_all_cameras(self, db: Session) -> List[Camera]:
        return camera_repository.get_all(db)


plant_service = PlantService()
```

```python
# app/ai_vision/services/image_service.py
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException, status
from app.ai_vision.models.image import PlantImage
from app.ai_vision.models.inference_job import AIInferenceJob
from app.ai_vision.integrations.storage_client import image_storage_service
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ImageService:
    def ingest_image(self, db: Session, plant_id: int, file: UploadFile, camera_id: int = None) -> PlantImage:
        plant = plant_service.get_plant(db, plant_id)
        if not plant:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plant {plant_id} not found")

        stored = image_storage_service.save(file)

        image = PlantImage(
            plant_id=plant_id,
            camera_id=camera_id,
            storage_path=stored["storage_path"],
            public_url=stored["public_url"],
            image_hash=stored["image_hash"],
            content_type=file.content_type,
            file_size_bytes=stored["file_size_bytes"],
            processing_status="uploaded",
        )
        db.add(image)
        db.commit()
        db.refresh(image)

        # Queue inference immediately rather than running it inline — heavy
        # AI work must never block the upload request.
        if config.AI_ENABLED:
            self.queue_inference(db, image)

        logger.info("AI vision image ingested", extra={"image_id": image.id, "plant_id": plant_id})
        return image

    def queue_inference(self, db: Session, image: PlantImage) -> AIInferenceJob:
        job = AIInferenceJob(
            image_id=image.id,
            model_name=config.AI_MODEL_NAME,
            model_version=config.AI_MODEL_VERSION,
            status="queued",
        )
        image.processing_status = "queued"
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def get_image(self, db: Session, image_id: int) -> PlantImage:
        image = db.query(PlantImage).filter(PlantImage.id == image_id).first()
        if not image:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
        return image

    def get_job(self, db: Session, job_id: int) -> AIInferenceJob:
        job = db.query(AIInferenceJob).filter(AIInferenceJob.id == job_id).first()
        if not job:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Inference job not found")
        return job


image_service = ImageService()
```

```python
# app/ai_vision/services/vision_service.py
from sqlalchemy.orm import Session
from app.ai_vision.models.image import PlantImage
from app.ai_vision.models.vision_prediction import VisionPrediction
from app.ai_vision.ai.inference.inference_manager import inference_manager
from app.ai_vision.integrations.camera_client import load_image_from_path
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class VisionService:
    def run_predictions(self, db: Session, image: PlantImage) -> list[VisionPrediction]:
        cv_image = load_image_from_path(image.storage_path)
        if cv_image is None:
            raise ValueError(f"Could not load image at {image.storage_path}")

        results = inference_manager.run_all(["detection", "health"], cv_image)

        predictions = []
        for result in results:
            prediction = VisionPrediction(
                image_id=image.id,
                plant_id=image.plant_id,
                model_name=result["model_name"],
                model_version=result["model_version"],
                task=result["task"],
                confidence=result["confidence"],
                inference_time_ms=result["inference_time_ms"],
                raw_output=result["raw_output"],
            )
            db.add(prediction)
            predictions.append(prediction)

        db.commit()
        for p in predictions:
            db.refresh(p)

        logger.info(
            "Vision predictions completed",
            extra={"image_id": image.id, "plant_id": image.plant_id, "count": len(predictions)},
        )
        return predictions


vision_service = VisionService()
```

```python
# app/ai_vision/services/growth_service.py
from sqlalchemy.orm import Session
from typing import Optional, List
from app.ai_vision.models.plant_growth import PlantGrowthRecord
from app.ai_vision.models.vision_prediction import VisionPrediction
from app.ai_vision.models.image import PlantImage
from app.ai_vision import config


class GrowthService:
    def record_growth(self, db: Session, image: PlantImage, detection_prediction: VisionPrediction) -> PlantGrowthRecord:
        canopy_area = detection_prediction.raw_output.get("canopy_area_px")

        previous = (
            db.query(PlantGrowthRecord)
            .filter(PlantGrowthRecord.plant_id == image.plant_id)
            .order_by(PlantGrowthRecord.created_at.desc())
            .first()
        )

        growth_pct = None
        growth_rate = None
        deviation_pct = None
        baseline_rate = None

        if previous and previous.canopy_area_px and canopy_area:
            growth_pct = round(((canopy_area - previous.canopy_area_px) / previous.canopy_area_px) * 100, 2)

            days_elapsed = max((image.captured_at - previous.created_at).total_seconds() / 86400, 1 / 24)
            growth_rate = round(growth_pct / days_elapsed, 3)

            baseline_rate = self._get_baseline_rate(db, image.plant_id)
            if baseline_rate:
                deviation_pct = round(((growth_rate - baseline_rate) / baseline_rate) * 100, 2)

        record = PlantGrowthRecord(
            plant_id=image.plant_id,
            image_id=image.id,
            canopy_area_px=canopy_area,
            growth_pct_since_last=growth_pct,
            growth_rate_pct_per_day=growth_rate,
            baseline_growth_rate_pct_per_day=baseline_rate,
            deviation_from_baseline_pct=deviation_pct,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def _get_baseline_rate(self, db: Session, plant_id: int) -> Optional[float]:
        """Baseline = plant's own expected_growth_profile if set, else the
        trailing average of its last 5 growth_rate readings. Configurable,
        never hard-coded, per the brief."""
        from app.ai_vision.models.plant import Plant

        plant = db.query(Plant).filter(Plant.id == plant_id).first()
        if plant and plant.expected_growth_profile:
            configured = plant.expected_growth_profile.get("canopy_growth_pct_per_day")
            if configured:
                return configured

        recent: List[PlantGrowthRecord] = (
            db.query(PlantGrowthRecord)
            .filter(PlantGrowthRecord.plant_id == plant_id, PlantGrowthRecord.growth_rate_pct_per_day.isnot(None))
            .order_by(PlantGrowthRecord.created_at.desc())
            .limit(5)
            .all()
        )
        rates = [r.growth_rate_pct_per_day for r in recent]
        return round(sum(rates) / len(rates), 3) if rates else None

    def is_growth_anomalous(self, deviation_from_baseline_pct: Optional[float]) -> bool:
        if deviation_from_baseline_pct is None:
            return False
        return abs(deviation_from_baseline_pct) / 100 >= config.GROWTH_ANOMALY_THRESHOLD


growth_service = GrowthService()
```

```python
# app/ai_vision/services/health_service.py
from sqlalchemy.orm import Session
from datetime import datetime
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.models.vision_prediction import VisionPrediction
from app.ai_vision.models.image import PlantImage
from app.ai_vision.integrations.hydroponic_client import sensor_fusion_service
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision import config


class HealthService:
    def compute_health(
        self, db: Session, image: PlantImage, health_prediction: VisionPrediction
    ) -> PlantHealthRecord:
        raw = health_prediction.raw_output
        visual_indicators = raw.get("visual_indicators", [])
        possible_issues = raw.get("possible_issues", [])

        plant = plant_service.get_plant(db, image.plant_id)
        sensor_snapshot = sensor_fusion_service.get_window(
            db, location=plant.location if plant else None, timestamp=image.captured_at or datetime.utcnow()
        )

        # Simple, explainable scoring: start at 100, subtract per indicator/issue.
        # This is the seam to swap in a trained regression head later —
        # `visual_indicators`/`possible_issues`/`sensor_snapshot` stay the same shape.
        score = 100
        score -= 15 * len(visual_indicators)
        score -= 10 * len(possible_issues)
        score = max(0, min(100, score))

        status = self._score_to_status(score)

        record = PlantHealthRecord(
            plant_id=image.plant_id,
            image_id=image.id,
            health_score=score,
            status=status,
            visual_indicators=visual_indicators,
            possible_issues=possible_issues,
            sensor_snapshot=sensor_snapshot,
            confidence=health_prediction.confidence,
            model_name=health_prediction.model_name,
            model_version=health_prediction.model_version,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def _score_to_status(score: int) -> str:
        if score >= 90:
            return "healthy"
        if score >= config.PLANT_HEALTH_WARNING_THRESHOLD:
            return "normal"
        if score >= config.PLANT_HEALTH_CRITICAL_THRESHOLD:
            return "warning"
        return "critical"


health_service = HealthService()
```

```python
# app/ai_vision/services/anomaly_service.py
from sqlalchemy.orm import Session
from app.ai_vision.models.plant_anomaly import PlantAnomaly
from app.ai_vision.models.plant_growth import PlantGrowthRecord
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.services.growth_service import growth_service
from app.ai_vision import config


class AnomalyService:
    """V1 keeps this intentionally simple (direct threshold comparison) —
    the brief's debounce/persistence requirement is the next increment:
    only raise once N consecutive readings cross the threshold, tracked via
    a rolling count per (plant_id, anomaly_type), not on a single sample."""

    def check_growth(self, db: Session, growth_record: PlantGrowthRecord) -> list[PlantAnomaly]:
        anomalies = []
        if growth_service.is_growth_anomalous(growth_record.deviation_from_baseline_pct):
            anomalies.append(self._create(
                db, growth_record.plant_id, "growth_slowdown",
                severity="medium" if growth_record.deviation_from_baseline_pct > -50 else "high",
                description=(
                    f"Growth rate deviates {growth_record.deviation_from_baseline_pct}% "
                    f"from baseline {growth_record.baseline_growth_rate_pct_per_day}%/day"
                ),
                evidence={
                    "growth_rate_pct_per_day": growth_record.growth_rate_pct_per_day,
                    "baseline_growth_rate_pct_per_day": growth_record.baseline_growth_rate_pct_per_day,
                    "deviation_from_baseline_pct": growth_record.deviation_from_baseline_pct,
                },
            ))
        return anomalies

    def check_health(self, db: Session, health_record: PlantHealthRecord) -> list[PlantAnomaly]:
        anomalies = []
        if health_record.status in ("warning", "critical"):
            anomalies.append(self._create(
                db, health_record.plant_id, "visual_change",
                severity="high" if health_record.status == "critical" else "medium",
                description=f"Health score dropped to {health_record.health_score} ({health_record.status})",
                evidence={
                    "health_score": health_record.health_score,
                    "visual_indicators": health_record.visual_indicators,
                    "sensor_snapshot": health_record.sensor_snapshot,
                },
            ))
        return anomalies

    def _create(self, db: Session, plant_id: int, anomaly_type: str, severity: str, description: str, evidence: dict) -> PlantAnomaly:
        anomaly = PlantAnomaly(
            plant_id=plant_id, anomaly_type=anomaly_type, severity=severity,
            description=description, evidence=evidence,
        )
        db.add(anomaly)
        db.commit()
        db.refresh(anomaly)
        return anomaly


anomaly_service = AnomalyService()
```

```python
# app/ai_vision/services/recommendation_service.py
from sqlalchemy.orm import Session
from typing import Optional
from app.ai_vision.models.ai_recommendation import AIRecommendation
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.models.plant_anomaly import PlantAnomaly


class RecommendationService:
    """Every recommendation must cite the evidence that produced it — never
    emit a bare instruction. This is enforced by requiring a non-empty
    `reasons` list at the model level."""

    def from_health_and_anomalies(
        self, db: Session, health_record: PlantHealthRecord, anomalies: list[PlantAnomaly]
    ) -> Optional[AIRecommendation]:
        if health_record.status not in ("warning", "critical") and not anomalies:
            return None

        reasons = []
        if "leaf_yellowing" in (health_record.visual_indicators or []):
            reasons.append("Visual leaf yellowing detected")
        for issue in (health_record.possible_issues or []):
            reasons.append(f"Possible issue flagged: {issue.get('issue')} (confidence {issue.get('confidence')})")

        sensor = health_record.sensor_snapshot or {}
        ec = sensor.get("ec")
        if ec is not None and ec < 1.2:
            reasons.append(f"EC ({ec}) is below the configured baseline")

        for anomaly in anomalies:
            reasons.append(anomaly.description)

        if not reasons:
            reasons.append(f"Health score is {health_record.health_score} ({health_record.status})")

        text = self._build_text(health_record, reasons)

        recommendation = AIRecommendation(
            plant_id=health_record.plant_id,
            health_record_id=health_record.id,
            anomaly_id=anomalies[0].id if anomalies else None,
            recommendation=text,
            reasons=reasons,
            severity="high" if health_record.status == "critical" else "medium",
            confidence=health_record.confidence,
            status="pending_review",
        )
        db.add(recommendation)
        db.commit()
        db.refresh(recommendation)
        return recommendation

    @staticmethod
    def _build_text(health_record: PlantHealthRecord, reasons: list[str]) -> str:
        if "leaf_yellowing" in (health_record.visual_indicators or []):
            return "Inspect nutrient concentration and lighting for this plant."
        if health_record.status == "critical":
            return "Manually inspect this plant as soon as possible."
        return "Review this plant's recent images and sensor history."


recommendation_service = RecommendationService()
```

### Controllers (thin orchestration)

```python
# app/ai_vision/controllers/vision_controller.py
from sqlalchemy.orm import Session
from app.ai_vision.services.image_service import image_service
from app.ai_vision.services.vision_service import vision_service
from app.ai_vision.services.growth_service import growth_service
from app.ai_vision.services.health_service import health_service
from app.ai_vision.services.anomaly_service import anomaly_service
from app.ai_vision.services.recommendation_service import recommendation_service
from app.ai_vision.models.inference_job import AIInferenceJob
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def run_full_pipeline(db: Session, job: AIInferenceJob) -> None:
    """The single place that wires detection -> growth -> health -> anomaly
    -> recommendation together, so the background job and any future manual
    "re-analyze" endpoint both go through the same code path."""
    from datetime import datetime

    image = image_service.get_image(db, job.image_id)
    job.status = "processing"
    job.started_at = datetime.utcnow()
    image.processing_status = "processing"
    db.commit()

    try:
        predictions = vision_service.run_predictions(db, image)
        by_task = {p.task: p for p in predictions}

        if "detection" in by_task:
            growth_record = growth_service.record_growth(db, image, by_task["detection"])
            growth_anomalies = anomaly_service.check_growth(db, growth_record)
        else:
            growth_anomalies = []

        if "health" in by_task:
            health_record = health_service.compute_health(db, image, by_task["health"])
            health_anomalies = anomaly_service.check_health(db, health_record)
            recommendation_service.from_health_and_anomalies(
                db, health_record, growth_anomalies + health_anomalies
            )

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        image.processing_status = "completed"
        db.commit()

    except Exception as e:
        logger.error(f"AI vision pipeline failed for image {image.id}: {e}", exc_info=True)
        job.status = "failed"
        job.error_message = str(e)
        image.processing_status = "failed"
        db.commit()
```

### Background worker (reuses the existing scheduler, no new infra)

```python
# app/ai_vision/jobs/inference_job.py
from app.database import SessionLocal
from app.ai_vision.models.inference_job import AIInferenceJob
from app.ai_vision.controllers.vision_controller import run_full_pipeline
from app.core.logging_config import get_logger

logger = get_logger("ai_vision.inference_job")


def process_queued_inference_jobs():
    """Polling worker, same pattern as app/cms/jobs/scheduled_publish_job.py.
    Swap for a real queue consumer (Celery/RQ against Redis, if the project
    adds one) without changing run_full_pipeline()."""
    db = SessionLocal()
    try:
        jobs = db.query(AIInferenceJob).filter(AIInferenceJob.status == "queued").limit(10).all()
        for job in jobs:
            run_full_pipeline(db, job)
        if jobs:
            logger.info(f"[AIVision] Processed {len(jobs)} queued inference job(s)")
    except Exception as e:
        logger.error(f"[AIVision] Inference job poll failed: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()
```

**Wire into `main.py`** (same place the other periodic jobs are registered):
```python
from app.ai_vision.jobs.inference_job import process_queued_inference_jobs
...
add_job(process_queued_inference_jobs, job_id="ai_vision_inference_job", seconds=15,
        job_name="AI Vision Inference Job")
```

### Routes

```python
# app/ai_vision/routes/plant_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.ai_vision.services.plant_service import plant_service
from app.ai_vision.schemas.plant_schema import PlantCreate, PlantUpdate, PlantOut, CameraCreate, CameraOut

router = APIRouter(prefix="/api/v1/plants", tags=["AI Vision - Plants"])


@router.post("", response_model=PlantOut)
def create_plant(data: PlantCreate, db: Session = Depends(get_db)):
    return plant_service.create_plant(db, **data.model_dump())


@router.get("", response_model=List[PlantOut])
def list_plants(status: Optional[str] = None, db: Session = Depends(get_db)):
    return plant_service.get_all_plants(db, status)


@router.get("/{plant_id}", response_model=PlantOut)
def get_plant(plant_id: int, db: Session = Depends(get_db)):
    plant = plant_service.get_plant(db, plant_id)
    if not plant:
        raise HTTPException(404, "Plant not found")
    return plant


@router.patch("/{plant_id}", response_model=PlantOut)
def update_plant(plant_id: int, data: PlantUpdate, db: Session = Depends(get_db)):
    plant = plant_service.update_plant(db, plant_id, data.model_dump(exclude_unset=True))
    if not plant:
        raise HTTPException(404, "Plant not found")
    return plant


camera_router = APIRouter(prefix="/api/v1/cameras", tags=["AI Vision - Cameras"])


@camera_router.post("", response_model=CameraOut)
def create_camera(data: CameraCreate, db: Session = Depends(get_db)):
    return plant_service.create_camera(db, **data.model_dump())


@camera_router.get("", response_model=List[CameraOut])
def list_cameras(db: Session = Depends(get_db)):
    return plant_service.get_all_cameras(db)
```

```python
# app/ai_vision/routes/image_router.py
from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.ai_vision.services.image_service import image_service
from app.ai_vision.schemas.image_schema import PlantImageOut

router = APIRouter(prefix="/api/v1/vision/images", tags=["AI Vision - Images"])


@router.post("", response_model=PlantImageOut)
def upload_image(
    plant_id: int = Query(...),
    camera_id: int = Query(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Ingest an image and queue AI inference. Inference always runs
    asynchronously — see /api/v1/ai/inference/{job_id} for status."""
    return image_service.ingest_image(db, plant_id, file, camera_id)


@router.get("/{image_id}", response_model=PlantImageOut)
def get_image(image_id: int, db: Session = Depends(get_db)):
    return image_service.get_image(db, image_id)
```

```python
# app/ai_vision/routes/inference_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.ai_vision.services.image_service import image_service
from app.ai_vision.controllers.vision_controller import run_full_pipeline
from app.ai_vision.schemas.image_schema import InferenceJobOut

router = APIRouter(prefix="/api/v1", tags=["AI Vision - Inference"])


@router.post("/vision/analyze/{image_id}", response_model=InferenceJobOut)
def analyze_image_now(image_id: int, db: Session = Depends(get_db)):
    """Manual re-analyze — runs synchronously for admin/debug use. Regular
    ingestion always goes through the async queue (image_router)."""
    image = image_service.get_image(db, image_id)
    job = image_service.queue_inference(db, image)
    run_full_pipeline(db, job)
    db.refresh(job)
    return job


@router.get("/ai/inference/{job_id}", response_model=InferenceJobOut)
def get_inference_job(job_id: int, db: Session = Depends(get_db)):
    return image_service.get_job(db, job_id)
```

```python
# app/ai_vision/routes/health_router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.ai_vision.models.plant_health import PlantHealthRecord
from app.ai_vision.models.plant_growth import PlantGrowthRecord
from app.ai_vision.models.plant_anomaly import PlantAnomaly
from app.ai_vision.schemas.health_schema import PlantHealthOut
from app.ai_vision.schemas.growth_schema import PlantGrowthOut
from app.ai_vision.schemas.anomaly_schema import PlantAnomalyOut

router = APIRouter(prefix="/api/v1/plants", tags=["AI Vision - Health & Growth"])


@router.get("/{plant_id}/health", response_model=PlantHealthOut)
def get_latest_health(plant_id: int, db: Session = Depends(get_db)):
    record = (
        db.query(PlantHealthRecord)
        .filter(PlantHealthRecord.plant_id == plant_id)
        .order_by(PlantHealthRecord.created_at.desc())
        .first()
    )
    return record


@router.get("/{plant_id}/growth", response_model=List[PlantGrowthOut])
def get_growth_history(plant_id: int, limit: int = Query(50, le=500), db: Session = Depends(get_db)):
    return (
        db.query(PlantGrowthRecord)
        .filter(PlantGrowthRecord.plant_id == plant_id)
        .order_by(PlantGrowthRecord.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/{plant_id}/anomalies", response_model=List[PlantAnomalyOut])
def get_anomalies(plant_id: int, db: Session = Depends(get_db)):
    return (
        db.query(PlantAnomaly)
        .filter(PlantAnomaly.plant_id == plant_id)
        .order_by(PlantAnomaly.detected_at.desc())
        .all()
    )
```

```python
# app/ai_vision/routes/recommendation_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.ai_vision.models.ai_recommendation import AIRecommendation
from app.ai_vision.schemas.recommendation_schema import AIRecommendationOut

router = APIRouter(prefix="/api/v1/plants", tags=["AI Vision - Recommendations"])


@router.get("/{plant_id}/recommendations", response_model=List[AIRecommendationOut])
def get_recommendations(plant_id: int, db: Session = Depends(get_db)):
    return (
        db.query(AIRecommendation)
        .filter(AIRecommendation.plant_id == plant_id)
        .order_by(AIRecommendation.created_at.desc())
        .all()
    )
```

**Wire into `main.py`:**
```python
from app.ai_vision.routes import plant_router as ai_plant_router
from app.ai_vision.routes import image_router as ai_image_router
from app.ai_vision.routes import inference_router as ai_inference_router
from app.ai_vision.routes import health_router as ai_health_router
from app.ai_vision.routes import recommendation_router as ai_recommendation_router
...
app.include_router(ai_plant_router.router)
app.include_router(ai_plant_router.camera_router)
app.include_router(ai_image_router.router)
app.include_router(ai_inference_router.router)
app.include_router(ai_health_router.router)
app.include_router(ai_recommendation_router.router)

# static mount, same pattern as MEDIA_URL/QR_CODE_URL
from app.ai_vision import config as ai_vision_config
os.makedirs(ai_vision_config.AI_VISION_IMAGE_DIR, exist_ok=True)
app.mount(ai_vision_config.AI_VISION_IMAGE_URL, StaticFiles(directory=ai_vision_config.AI_VISION_IMAGE_DIR), name="ai_vision_images")
```

---

## 5. `.env` additions

```env
AI_ENABLED=true
AI_MODEL_NAME=plant-detector
AI_MODEL_VERSION=v1-mock
AI_CONFIDENCE_THRESHOLD=0.60

PLANT_HEALTH_WARNING_THRESHOLD=70
PLANT_HEALTH_CRITICAL_THRESHOLD=50
GROWTH_ANOMALY_THRESHOLD=0.30
AI_SENSOR_WINDOW_MINUTES=15

IMAGE_MAX_SIZE_MB=10
AI_VISION_STORAGE_BACKEND=local
AI_VISION_IMAGE_DIR=uploads/ai_vision
AI_VISION_IMAGE_URL=/static/ai_vision
```

## 6. What's intentionally deferred (say so explicitly rather than hand-waving)

- **Real models**: `MockYOLOPlantDetector` / `MockLeafHealthClassifier` are placeholders with the exact I/O contract a real model needs to satisfy (`predict(image) -> dict` with a `confidence` key). Swapping them is a `MODEL_REGISTRY` change in `inference_manager.py`.
- **Object storage backends (S3/MinIO)**: `ImageStorageService` ABC exists; only `LocalImageStorage` is implemented. Add `S3ImageStorage` and switch on `AI_VISION_STORAGE_BACKEND`.
- **Debounced anomaly detection**: current `AnomalyService` fires on a single sample crossing a threshold. Add a rolling-window count keyed on `(plant_id, anomaly_type)` before promoting to "V2" per the brief's explicit debounce requirement.
- **Automation policy / actuator wiring**: deliberately not built — `AIRecommendation.status` never leaves `pending_review` in this codebase. Wire to `irrigation_session_service`/`actuator_controller` only after recommendation quality has been reviewed, and gate it behind an explicit opt-in per plant/zone.
- **React dashboard, tests, live camera pull, TimescaleDB**: not included in this pass — the API surface above (`/api/v1/plants/*`, `/api/v1/vision/*`, `/api/v1/ai/*`) is what the dashboard and test suite would target next.
