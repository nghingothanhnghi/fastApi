# AIoT Plant Vision Module — Current Architecture (V1, implemented)

> **Note on this document's history**: this file originally described the *pre-implementation plan* for `app/ai_vision`, including code blocks with `Plant`/`Camera` model names and a simple poll-based job queue. That draft is no longer accurate — the module has since been implemented and hardened. This revision describes what's actually in the codebase today. See `app/ai_vision/README.md` for the maintained, per-layer developer guide; this file stays focused on module-level status, decisions, and what's deferred.

## 0. Conventions this module follows

Same conventions as the rest of the repo:
- Singleton service instances: `thing_service = ThingService()` at the bottom of each service file.
- Schemas: `model_config = {"from_attributes": True}`, split into `*Base` / `*Create` / `*Update` / `*Out`.
- `Depends(get_db)` from `app.database`, `get_logger(__name__)` from `app.core.logging_config`.
- Background jobs: `app/utils/scheduler.add_job(...)`, registered in `main.py`.
- `app/init_db.py` imports every model module once so `Base.metadata.create_all` picks it up.

Reused pieces this module does **not** duplicate:
- Sensor data: `app.hydro_system.models.sensor_data.SensorData`
- Flow telemetry: `app.hydro_system.services.flow_reading_service.flow_reading_service`
- Irrigation sessions: `app.hydro_system.services.irrigation_session_service`
- Auth: `app.user.utils.token.get_current_user`
- Devices/locations: `app.hydro_system.models.device.HydroDevice`
- Hydro batch linkage (read-only): `app.ai_vision.integrations.hydro_batch_client.hydro_batch_client`

## 1. Phasing

| Phase | Scope | Status |
|---|---|---|
| V1 | Plant/camera CRUD, image ingestion + storage abstraction, mock detector, growth tracking, health scoring, sensor fusion, background inference job, REST API, auth + tenant scoping, image serving | **Implemented** |
| V1.1 | Debounced anomaly detection with persisted state | **Implemented** (originally scoped as V2 — done ahead of schedule, see §5) |
| V1.2 | Atomic job claiming + lease-based recovery | **Implemented** (not in the original plan at all — added because the naive poll-and-process draft had a double-processing race) |
| V2 | Real leaf-health model, real detector | Not started — interfaces (`PlantVisionModel`, `InferenceManager.MODEL_REGISTRY`) are ready to receive them |
| V3 | Disease/pest classifier | Slot exists: implement another `PlantVisionModel` subclass, register it |
| V4 | Deeper sensor+vision fusion | `SensorFusionService.get_window()` is the extension point |
| V5–V7 | Growth prediction, AI-assisted irrigation/nutrient optimization | Out of scope; see safety boundary below |

## 2. Safety boundary (unchanged from original plan, still correctly enforced)

```
→ RecommendationService → AIRecommendation (status=pending_review)
→ (future) AutomationPolicyService → irrigation_session_service / actuator_controller                            
```

`AIRecommendation.status` never leaves `pending_review` anywhere in this codebase — there is no code path from `app.ai_vision` into `actuator_controller`, `hydro_schedule_service`, or any irrigation write path. That wiring remains a deliberate future PR, gated on human review of recommendation quality.

## 3. Actual file layout

```
app/ai_vision/
├── config.py
├── models/
│ ├── plant.py VisionPlant, VisionCamera ⚠️ renamed from Plant/Camera
│ ├── image.py PlantImage
│ ├── inference_job.py AIInferenceJob
│ ├── vision_prediction.py VisionPrediction
│ ├── plant_growth.py PlantGrowthRecord
│ ├── plant_health.py PlantHealthRecord
│ ├── plant_anomaly.py PlantAnomaly
│ ├── anomaly_tracker.py AnomalyTracker ⚠️ new — debounce state, not in original plan
│ └── ai_recommendation.py AIRecommendation
├── schemas/ (mirrors models 1:1, plus client_id on Plant/Camera Out schemas)
├── repositories/
│ ├── plant_repository.py PlantRepository, CameraRepository (+ get_all_by_client)
│ └── anomaly_repository.py AnomalyTrackerRepository ⚠️ new
├── ai/
│ ├── base/vision_model.py PlantVisionModel (ABC)
│ └── inference/
│ ├── detector.py MockYOLOPlantDetector
│ ├── classifier.py MockLeafHealthClassifier
│ └── inference_manager.py InferenceManager (model registry + versioning)
├── integrations/
│ ├── storage_client.py ImageStorageService (ABC) + LocalImageStorage
│ ├── hydroponic_client.py SensorFusionService (wraps SensorData/flow_reading_service)
│ ├── hydro_batch_client.py HydroBatchClient ⚠️ new — read-only PlantBatch lookup
│ └── camera_client.py fetch_image_from_camera() stub (still NotImplementedError, as planned)
├── services/
│ ├── plant_service.py + get_all_plants_by_client / get_all_cameras_by_client
│ ├── image_service.py
│ ├── inference_job_service.py ⚠️ new — atomic claim + lease expiry, replaces naive queueing
│ ├── vision_service.py
│ ├── growth_service.py + zero-baseline fallback (GROWTH_ANOMALY_ABS_PCT_PER_DAY)
│ ├── health_service.py
│ ├── anomaly_service.py ⚠️ now debounced via AnomalyTracker
│ └── recommendation_service.py
├── helpers/
│ └── access_helper.py ⚠️ new — ensure_plant_access / ensure_camera_access
├── controllers/
│ └── vision_controller.py single commit/rollback boundary for the whole pipeline
├── jobs/
│ └── inference_job.py polls queued jobs, requeues expired leases, claims before running
└── routes/
├── plant_router.py (+ camera_router) — all endpoints require get_current_user
├── image_router.py — requires get_current_user + ensure_plant_access
├── inference_router.py — requires get_current_user + ensure_plant_access
├── health_router.py — requires get_current_user + ensure_plant_access
└── recommendation_router.py — requires get_current_user + ensure_plant_access
```

Wired into `app/init_db.py` as:
```python
from .ai_vision.models import (
    VisionPlant, VisionCamera, PlantImage, AIInferenceJob,
    VisionPrediction, PlantGrowthRecord, PlantHealthRecord,
    PlantAnomaly, AnomalyTracker, AIRecommendation,
)
```

Wired into `main.py`: all five routers are included, and `AI_VISION_IMAGE_DIR` is mounted at `AI_VISION_IMAGE_URL` via `StaticFiles` (this mount was missing for a period after the routes were added — confirm it's present if you're diffing against an older checkout; uploaded images 404 without it).

## 4. What changed from the original plan, and why

### 4.1 `Plant`/`Camera` → `VisionPlant`/`VisionCamera`
The original names collided conceptually with `app.hydro_system.models.plant.Plant`. Renamed for clarity since both modules are imported side-by-side in `app/init_db.py` and elsewhere.

### 4.2 Tenant scoping (`client_id`)
Neither model originally had a `client_id`. Every other multi-tenant-aware module in this app (`HydroDevice`, `PaymentTransaction`, `Template`, etc.) scopes rows by `client_id` and checks `SUPER_ADMIN` bypass. `VisionPlant.client_id` / `VisionCamera.client_id` now follow the same convention (`app.ai_vision.helpers.access_helper.ensure_plant_access` / `ensure_camera_access`, modeled directly on `hydro_system.controllers.device_controller._ensure_device_access`). All routes now depend on `get_current_user` and enforce this. A plant/camera with `client_id=None` (e.g. a pre-migration legacy row) is treated as inaccessible to non-admins rather than silently open.

### 4.3 Atomic job claiming + lease recovery
The original design in this doc had the scheduler poll `AIInferenceJob` rows with `status == "queued"` and process them directly — with more than one scheduler-driven worker (or a slow request thread), two workers could grab and process the same job. `inference_job_service.claim()` now does an atomic conditional update (`UPDATE ... WHERE status='queued'`, `synchronize_session=False`) before any inference work starts, and `requeue_expired_leases()` recovers jobs left in `processing` past `AI_JOB_LEASE_SECONDS` (default 600s) if a worker crashes mid-run. `inference_job_service.get_or_create_active()` also makes re-ingesting/re-analyzing idempotent — it reuses an existing `queued`/`processing` job for an image instead of creating a duplicate.

### 4.4 Transaction boundaries
Originally, several services called `db.commit()` directly (e.g. inside `growth_service`, `health_service`). This meant a failure partway through the pipeline (say, health scoring throwing after growth tracking already committed) left inconsistent partial state. Pipeline-stage services (`vision_service`, `growth_service`, `health_service`, `anomaly_service`, `recommendation_service`) now only `db.flush()`; `vision_controller.run_full_pipeline` owns the single `commit()` on success or `rollback()` + failure-status commit on exception. `image_service.ingest_image` and `plant_service`/`repository` CRUD methods still commit directly, since those are standalone operations, not pipeline stages.

### 4.5 Debounced anomaly detection (this doc's original "V2" — already done)
The original plan explicitly deferred debouncing: *"current `AnomalyService` fires on a single sample crossing a threshold... V2 increment."* This is now implemented via `AnomalyTracker` (one row per `(plant_id, anomaly_type)`, persisted so it survives restarts and is safe across scheduler workers). A `PlantAnomaly` is only created once `consecutive_count` reaches `config.ANOMALY_DEBOUNCE_COUNT` (default 3); a single clean reading resets the streak to 0. See `app/ai_vision/repositories/anomaly_repository.py` and `app/ai_vision/models/anomaly_tracker.py`.

### 4.6 Zero-baseline growth deviation
`growth_service.is_growth_anomalous` originally divided by `baseline_growth_rate_pct_per_day`, which is undefined (and previously silently treated as "never anomalous") when the baseline is exactly 0. It now falls back to comparing the absolute growth rate against `config.GROWTH_ANOMALY_ABS_PCT_PER_DAY` (default 15.0) in that case, so a plant with a flat historical baseline that suddenly starts changing size isn't silently ignored.

### 4.7 Hydro batch linkage
Not in the original plan at all. `app/ai_vision/integrations/hydro_batch_client.py` gives `VisionPlant` a one-way, read-only path to look up `PlantBatch`/`Plant` info from `hydro_system`, used by `plant_service.link_or_create_from_hydro_batch()` (idempotent — returns the existing linked `VisionPlant` if one already exists for that batch). `hydro_system` never imports anything from `ai_vision`, preserving the existing one-directional dependency convention.

## 5. What's still genuinely deferred (not silently dropped, just not built)

- **Real models**: `MockYOLOPlantDetector` / `MockLeafHealthClassifier` are placeholders with the exact I/O contract (`predict(image) -> dict` with a `confidence` key) a real model needs to satisfy. Swapping them is a `MODEL_REGISTRY` change in `inference_manager.py`, nothing downstream should need to change.
- **Object storage backends (S3/MinIO)**: `ImageStorageService` ABC exists; only `LocalImageStorage` is implemented. `config.AI_VISION_STORAGE_BACKEND` is read but unused beyond documenting intent.
- **Automation policy / actuator wiring**: still deliberately not built — see §2.
- **Live camera pull**: `camera_client.fetch_image_from_camera()` still raises `NotImplementedError`; upload is the only ingestion path.
- **React dashboard, automated tests, TimescaleDB**: not included.
- **`postorocessing/` directory typo**: preserved intentionally until a dedicated rename PR, so as not to churn imports alongside unrelated changes.

## 6. `.env` reference

```env
AI_ENABLED=true
AI_MODEL_NAME=plant-detector
AI_MODEL_VERSION=v1-mock
AI_CONFIDENCE_THRESHOLD=0.60
AI_JOB_LEASE_SECONDS=600

PLANT_HEALTH_WARNING_THRESHOLD=70
PLANT_HEALTH_CRITICAL_THRESHOLD=50

GROWTH_ANOMALY_THRESHOLD=0.30
GROWTH_ANOMALY_ABS_PCT_PER_DAY=15.0
ANOMALY_DEBOUNCE_COUNT=3

AI_SENSOR_WINDOW_MINUTES=15

IMAGE_MAX_SIZE_MB=10
AI_VISION_STORAGE_BACKEND=local
AI_VISION_IMAGE_DIR=uploads/ai_vision
AI_VISION_IMAGE_URL=/static/ai_vision
```

## 7. For implementation detail, go to the source

This doc intentionally no longer inlines full code — it drifted out of sync with the real implementation once before. For anything below module-level status:
- Per-layer responsibilities and extension rules → `app/ai_vision/README.md`
- Exact model fields → `app/ai_vision/models/*.py`
- Exact endpoint contracts → `app/ai_vision/routes/*.py` + `app/ai_vision/schemas/*.py`