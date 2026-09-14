# AI Vision Module — Phase 1 (V1) Drop-in

## How to apply

1. Copy `app/ai_vision/` from this archive into your repo, overwriting the empty stub files.
2. Replace your `app/init_db.py` and `main.py` with the versions in this archive
   (they are your existing files with only the AI Vision additions applied —
   diff them against your current copies before overwriting if you've changed
   either file since the version pasted into this conversation).
3. Add the contents of `env.additions.txt` to your `.env`.
4. Install the one new dependency this module needs beyond what you already have:
   `opencv-python` (already a dependency via `app/camera_object_detection`, so
   likely nothing to install) and `numpy` (same).
5. Restart the app. `init_db()` will create the new tables:
   `ai_vision_plants`, `ai_vision_cameras`, `ai_vision_images`,
   `ai_vision_inference_jobs`, `ai_vision_predictions`,
   `ai_vision_growth_records`, `ai_vision_health_records`,
   `ai_vision_anomalies`, `ai_vision_recommendations`.

## Smoke test

```bash
# 1. Create a camera + plant
curl -X POST localhost:8000/api/v1/cameras -H "Content-Type: application/json" \
  -d '{"name": "Greenhouse A Cam 1", "location": "Greenhouse A"}'

curl -X POST localhost:8000/api/v1/plants -H "Content-Type: application/json" \
  -d '{"species": "Lettuce", "location": "Greenhouse A", "camera_id": 1}'

# 2. Upload an image (queues inference automatically)
curl -X POST "localhost:8000/api/v1/vision/images?plant_id=1" \
  -F "file=@/path/to/plant.jpg"

# 3. Either wait ~15s for the background job, or force it synchronously:
curl -X POST localhost:8000/api/v1/vision/analyze/1

# 4. Check results
curl localhost:8000/api/v1/plants/1/health
curl localhost:8000/api/v1/plants/1/growth
curl localhost:8000/api/v1/plants/1/anomalies
curl localhost:8000/api/v1/plants/1/recommendations
```

## What's real vs. mocked in this phase

- Real: DB schema, image storage + validation, async job queue on your existing
  scheduler, growth-vs-baseline math, health scoring pipeline, sensor fusion
  against your actual `SensorData`/`flow_reading_service`, explainable
  recommendations, REST API.
- Mocked (by design, swap later): `MockYOLOPlantDetector` and
  `MockLeafHealthClassifier` in `app/ai_vision/ai/inference/` — replace their
  `predict()` bodies with real model calls; nothing else changes.

## Explicitly NOT included in this phase

- No write path into `actuator_controller` / `irrigation_session_service`.
  `AIRecommendation.status` never leaves `pending_review` here.
- No S3/MinIO storage backend (interface exists in `integrations/storage_client.py`).
- No debounced/rolling-window anomaly detection (current version fires on a
  single threshold-crossing sample).
- No React dashboard, no automated tests, no live ESP32-CAM pull.

## Fix log

- **2026-09-14**: Renamed `app/ai_vision/models/plant.py`'s `Plant`/`Camera`
  classes to `VisionPlant`/`VisionCamera`. Your existing
  `hydro_system.models.plant_batch.PlantBatch.plant = relationship("Plant")`
  does a *string-based* lookup against SQLAlchemy's shared declarative
  registry — having two classes both named `Plant` made that lookup
  ambiguous and broke mapper configuration for the *entire app* (not just
  ai_vision), which is why it surfaced on `/sensor/data` and `/auth/me`
  too. Table names (`ai_vision_plants`, `ai_vision_cameras`) are unchanged,
  so if you already ran the previous version and it got as far as creating
  tables, no migration is needed — only the Python class names changed.
  Verified via a standalone repro that reconfigures SQLAlchemy's mapper
  registry with both your `PlantBatch.plant = relationship("Plant")` and
  this module present: fails with the exact reported error before the
  rename, configures cleanly after.
