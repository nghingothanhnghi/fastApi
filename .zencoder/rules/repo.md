# Repository Guide

A concise overview to help tools and contributors understand how to run, build, and navigate this project.

## Tech Stack
- Backend: Python 3.13, FastAPI 0.115.x, Uvicorn
- DB: SQLite (dev) at `app/data/database.db` (PostgreSQL supported)
- CV/ML: Ultralytics YOLO (v8), OpenCV, PyTorch
- Frontends:
  - `farmApp/`: Vite + React + TypeScript
  - `frontend/`: Create React App (React 18)

## Key Entry Points
- Backend app entry: `main.py` (FastAPI application instance `app`)
- Database init: `app/init_db.py`
- Frontends:
  - `farmApp`: `npm run dev` (Vite on port 5173 by default)
  - `frontend`: `npm start` (CRA on port 3000 by default)

## Important Paths
- API code: `app/`
  - `api/endpoints/`: Routers
  - `core/`: config, logging
  - `middleware/`: error handling
  - `user/`, `hydro_system/`, `camera_object_detection/`, `android_system/`, `transform_data/`, `migration/`, `utils/`
- Data + Models:
  - SQLite file: `app/data/database.db`
  - YOLO weights: `yolov5su.pt`, `yolov8n.pt`
  - Dataset: `dataset/` (images, labels, `data.yaml`)
- Uploads: `uploads/profile_images/`

## Running the Backend (Windows PowerShell)
1) Create venv and activate
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
2) Install deps
```
pip install -r requirements.txt
```
3) Environment
- Copy `.env` (configure DB URL, email, ADB, secrets). Example vars:
```
DATABASE_URL=sqlite+aiosqlite:///./app/data/database.db
SECRET_KEY=change-me
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
UPLOAD_DIR=uploads/profile_images
STATIC_URL_BASE=/static/profile_images
ADB_HOST=127.0.0.1
ADB_PORT=5037
USE_MOCK_DEVICES=false
```
4) Initialize DB (optional if using SQLite file)
```
python app/init_db.py
```
5) Start API
```
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Running Frontends
- farmApp (Vite + TS)
```
cd farmApp
npm install
npm run dev   # http://localhost:5173
```
- frontend (CRA)
```
cd frontend
npm install
npm start     # http://localhost:3000
```

## Tests
- Pytest (from repo root)
```
pytest
```
Selected utilities:
- `app/tests/train_model.py` (model training)
- `app/tests/create_sample_data.py` (seed data)

## Background Jobs & Realtime
- Scheduling: APScheduler (sensor collection, data transformation)
- WebSockets: used in camera streaming and connection manager modules

## Build
- farmApp
```
cd farmApp
npm run build
npm run preview  # local preview
```
- frontend (CRA)
```
cd frontend
npm run build
```

## Ports
- API: 8000
- farmApp (Vite): 5173
- frontend (CRA): 3000

## Notes
- Runtime hints: `runtime.txt` specifies Python 3.13
- For production: prefer PostgreSQL, set `DATABASE_URL` accordingly
- Large ML deps (torch, ultralytics) may require GPU/CUDA for best performance

## Troubleshooting Quick Tips
- If Torch/Ultralytics install issues: ensure Python 3.10–3.12 or correct CUDA; CPU-only wheels may be slower
- If ADB features fail: confirm `adb` is installed and `ADB_PORT` reachable
- CORS/frontend API calls: configure FastAPI CORS middleware if needed
