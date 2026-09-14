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

- **2026-09-14 (2)**: Fixed two bugs hit during first real pipeline run:
  1. `SensorFusionService.get_window()` (`integrations/hydroponic_client.py`)
     returned raw `datetime` objects for `window_start`/`window_end`, which
     then get stored in `PlantHealthRecord.sensor_snapshot` — a JSON column.
     SQLite's JSON serializer can't handle `datetime` directly. Fixed by
     calling `.isoformat()` on both before they go into the dict.
  2. `run_full_pipeline`'s `except` block (`controllers/vision_controller.py`)
     tried to `db.commit()` a "failed" status update without first calling
     `db.rollback()`. Since the *original* failure was mid-flush, the
     session's transaction was already dead, so the second commit raised a
     `PendingRollbackError` that masked the real error in the HTTP response.
     Fixed by calling `db.rollback()` at the top of the except block.

  Both reproduced and verified fixed against a live SQLite JSON column
  before repackaging (not just reasoned about) — see conversation for the
  repro script.

- **2026-09-14 (3)**: Fixed a falsy-zero bug in `services/growth_service.py`
  found while reviewing real `/plants/{id}/growth` output: `if baseline_rate:`
  and `if configured:` both treat a legitimate `0.0` the same as "not set",
  because `0.0` is falsy in Python. This meant a plant with genuinely flat
  growth (baseline = 0.0%/day) always got `deviation_from_baseline_pct: null`
  instead of the correct `0.0`. Fixed to explicitly check `is not None`, and
  to handle true division-by-zero (nonzero growth off a zero baseline is
  mathematically undefined as a percentage) as its own case rather than
  lumping it in with "no baseline yet". Verified against four cases
  (flat/flat, nonzero-off-zero-baseline, normal case, no-baseline-yet)
  before repackaging.

## Verified end-to-end (2026-09-14)

Full pipeline confirmed working against a real running instance and real
`SensorData`: camera create -> plant create -> image upload (auto-queues
inference) -> async background job AND manual `/vision/analyze/{id}` both
completing successfully -> growth tracking with baseline math -> health
scoring fused with real sensor readings -> anomaly detection -> evidence-based
recommendation with `status: "pending_review"`. Not just "should work" —
walked through with real curl output at every step.

## Known limitations found during this verification (not yet fixed)

1. **Mock health classifier has a hard ceiling of "normal" status.**
   `MockLeafHealthClassifier` can set at most one `visual_indicator`
   (`leaf_yellowing`) and one `possible_issue` (`possible_nutrient_deficiency`),
   capping the total score deduction at `-25` (100 -> 75). Since
   `PLANT_HEALTH_WARNING_THRESHOLD=70`, a score of 75 is always `"normal"` —
   `"warning"`/`"critical"` are structurally unreachable via any image with
   this mock model. Practical effect: `anomaly_service.check_health()` can
   never fire from HTTP testing today; only `check_growth()` can. This isn't
   a bug in the scoring formula itself, just a limitation of the placeholder
   classifier — resolves itself once a real trained classifier is wired in
   (Phase 2), but worth knowing before assuming the health-anomaly branch
   has been exercised.

2. **Growth deviation reports `null` instead of a number when the baseline
   is exactly `0.0`, even for a genuinely extreme change.** Confirmed with
   real data: a `-638%/day` growth rate against a `0.0` baseline produced
   `deviation_from_baseline_pct: null` rather than any anomaly-triggering
   value, because expressing "how much did it deviate" as a percentage of
   zero is undefined (see the 2026-09-14 (3) fix above — this is that fix
   working as designed, not a regression, but it has a real blind spot).
   A large absolute change right after a run of perfectly flat data can
   currently produce a `null` deviation and silently skip the anomaly
   check. Fix for Phase 2: fall back to an absolute-change threshold
   (e.g. `abs(canopy_area_new - canopy_area_old) > X px`) when
   `baseline_growth_rate_pct_per_day == 0`, instead of only ever working
   in percentage terms.

3. **`/vision/analyze/{image_id}` and the background poller can both run
   the pipeline on the same image if you call the endpoint manually before
   the ~15s poller gets to it first.** Not a bug — `AI_ENABLED=true` means
   every upload auto-queues, and `/vision/analyze/{id}` is documented as
   "runs synchronously, always" for admin/debug use — but it means you can
   end up with two separate growth/health/anomaly records for one image if
   you don't wait for the queued job to finish first. Decide in Phase 2
   whether `/vision/analyze/{id}` should instead re-use/cancel an
   already-`completed` job for the same image rather than always creating
   a fresh one.
