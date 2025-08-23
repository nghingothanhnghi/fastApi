# Backend Guide (FastAPI)

This document explains the backend in detail: architecture, key modules, configuration, background jobs, and how to run/debug it. Frontend apps are intentionally omitted.

## 1) Architecture Overview

- **Framework**: FastAPI + Starlette
- **Runtime**: Python 3.13
- **Database**: SQLAlchemy (SQLite by default, PostgreSQL supported via `DATABASE_URL`)
- **Auth**: OAuth2 + JWT (python-jose)
- **Background Jobs**: APScheduler
- **Realtime**: WebSockets (hardware detection streaming)
- **CV/ML**: Ultralytics YOLO, OpenCV, Torch
- **File Serving**: Static files for profile images

### Request Lifecycle
1. App starts (`main.py`): initialize DB, configure logging, register middleware/routers, start jobs.
2. CORS middleware and custom error handler wrap requests.
3. Routers dispatch to domain modules (user, hydro, android, vision, data pipeline).
4. DB sessions are injected per-request via `Depends(get_db)`.

## 2) Entry Point: `main.py`

Key responsibilities:
- **Initialization**
  - `init_db()` — database bootstrapping
  - `configure_logging()` — global logging at INFO level
- **Middleware**
  - `CORSMiddleware` — currently allows all origins (restrict in production)
  - `catch_exceptions_middleware` — returns `{"detail": message}` on unhandled exceptions (500)
- **Routers (selected)**
  - User/Auth: `/auth`, user, roles, password reset
  - Devices/ADB: `/devices`, `/tap`, `/screen`, `/health`
  - Scheduler Health: `/scheduler/health`
  - Vision/Detection: `/object-detection`, hardware detection API + WebSocket
  - Hydro System: `/hydro/*`, `/sensor/*`, `/actuator/*`
  - Data Pipeline: ingest/transform/template APIs
- **Static Mount**
  - Serves profile images: `STATIC_URL_BASE` → `UPLOAD_DIR`
- **Background Jobs**
  - Global scheduler + hydro sensor collect job + data transform job
  - Starts hardware detection background tasks via `asyncio.create_task`

## 3) Configuration (`app/core/config.py`)

- Loads environment variables (`.env`).
- Key variables:
  - **ADB_HOST**, **ADB_PORT** — Android Debug Bridge
  - **USE_MOCK_DEVICES**, **USE_MOCK_HYDROSYSTEMMAINBOARD**, **USE_MOCK_AI** — feature flags
  - **UPLOAD_DIR**, **STATIC_URL_BASE** — static files
  - **OPENAI_API_KEY** — REQUIRED at startup (raises if missing)

Note: The app will fail fast if `OPENAI_API_KEY` is not set.

## 4) Database Layer (`app/database.py`)

- Reads **DATABASE_URL** from `.env` and raises if missing.
- Creates SQLAlchemy `engine`, `SessionLocal`, and `Base`.
- Provides `get_db()` dependency to inject DB sessions safely into request handlers.

Examples:
```python
# Example DATABASE_URLs
# SQLite (dev): sqlite:///./app/data/database.db
# SQLite (async): sqlite+aiosqlite:///./app/data/database.db
# PostgreSQL: postgresql://user:password@localhost:5432/dbname
```

## 5) Security & Auth

- **OAuth2PasswordBearer** (`tokenUrl="/auth/login"`).
- **JWT** via `python-jose`.
- `create_access_token(data, expires)` issues tokens.
- `get_current_user` decodes JWT and loads user from DB; raises 401 if invalid.
- `require_permission(permission)` dependency factory for RBAC checks.

Related files:
- `app/user/routes/auth_router.py` — login (`/auth/login`), `GET /auth/me`.
- `app/user/utils/token.py` — token creation/validation, dependencies.
- `app/user/models/*` — `User`, `Role`, `UserRole`, `PasswordReset`.

## 6) Middleware

- `CORSMiddleware` — currently `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`.
- `catch_exceptions_middleware` — logs and returns JSON 500 for uncaught exceptions.

## 7) Domain Modules

### 7.1 User Module (`app/user`)
- **Routes**: auth, user profile, roles, password reset.
- **Models**: user/role relations.
- **Schemas/Services/Utils**: Pydantic schemas, business logic, security helpers.

### 7.2 Hydroponic System (`app/hydro_system`)
- **Sensors & Control**: `sensors.py` reads values, `controllers/actuator_controller.py` applies rules.
- **Scheduler**: `scheduler.py` registers `sensor_collect_job` (every 60s), persists `SensorData`, and triggers automation.
- **State**: `state_manager.py` stores flags like scheduler state.
- **Routes**: `/hydro/*`, `/sensor/*`, `/actuator/*` for status, control, and data endpoints.

### 7.3 Android System (`app/android_system`)
- **Device control** via ADB: `device_manager.py`, `interaction_controller.py`.
- **Screen streaming**: `screen_streamer.py` (served under `/screen`).
- **Config/Mocks**: `config.py`, `mock_devices.py` for testing.

### 7.4 Computer Vision (`app/camera_object_detection`)
- **Routes**: `/object-detection` operations; hardware detection endpoints.
- **WebSocket**: live streaming/updates (`websocket/router`).
- **Utils**: OpenCV/YOLO helpers.

### 7.5 Data Pipeline & Migration
- **Transform Data**: `transform_data/controllers`, `jobs/transform_job.py` (registered every 10s), schemas, services.
- **Migration**: tooling to ingest/move data between systems (`migration/controllers`).

### 7.6 Generic Utilities (`app/utils`)
- **Scheduler**: Global APScheduler with concurrency protection and health reporting.
- **Background Tasks**: hardware detection task orchestration.
- **ADB**: clients/setup helpers.
- **Email**: SMTP-based email sending (used for password reset etc.).

## 8) Background Jobs & Health

- **Global Scheduler**: started on app startup (`start_scheduler`).
- **Jobs Registered**:
  - `sensor_collect_job` (Hydro) — every 60s, reads sensors, persists, runs automation rules.
  - `transform_job` (Data) — every 10s, processes untransformed data.
- **Health Endpoint**: `/scheduler/health` — returns scheduler state and known job statuses.

## 9) Static Files

- Ensures `UPLOAD_DIR` exists and mounts it at `STATIC_URL_BASE`.
- Used to serve profile images or uploaded assets.

## 10) API Health & System Endpoints

- `GET /health` — app health, reports ADB connectivity status.
- Selected prefixes:
  - **/auth** — login, current user, etc.
  - **/devices**, **/tap**, **/screen** — Android device operations.
  - **/object-detection** — CV endpoints.
  - **/hydro**, **/sensor**, **/actuator** — hydro system.

## 11) Logging (`app/core/logging_config.py`)

- Configures root logging to `INFO`.
- `get_logger(name)` helper to get module-specific loggers.

## 12) Running the Backend (Windows PowerShell)

1. Create and activate virtual env
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
2. Install dependencies
```powershell
pip install -r requirements.txt
```
3. Create `.env` (minimal required)
```env
# Database (choose one)
DATABASE_URL=sqlite:///./app/data/database.db
# DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# Auth
SECRET_KEY=change-me
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=43200

# Static
UPLOAD_DIR=uploads/profile_images
STATIC_URL_BASE=/static/profile_images

# Android
ADB_HOST=127.0.0.1
ADB_PORT=5037
USE_MOCK_DEVICES=true
USE_MOCK_HYDROSYSTEMMAINBOARD=true
USE_MOCK_AI=true

# Required for startup
OPENAI_API_KEY=your-api-key
```
4. Initialize DB (optional for SQLite)
```powershell
python app/init_db.py
```
5. Run the app
```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 13) Notes & Gotchas

- **Required envs**: `DATABASE_URL` (DB bootstrap) and `OPENAI_API_KEY` (startup check) must be set.
- **CORS**: currently wide open; set allowed origins for production.
- **Schedulers**: long-running background tasks start at app boot; inspect logs if they fail at startup.
- **ADB**: features depending on ADB require a working `adb` on PATH or mocks enabled.
- **ML deps**: Torch/Ultralytics may be heavy; GPU acceleration optional but recommended.

## 14) Files of Interest

- `main.py` — app startup and wiring
- `app/core/config.py` — environment config (enforces OPENAI_API_KEY)
- `app/database.py` — SQLAlchemy engine/sessions (enforces DATABASE_URL)
- `app/utils/scheduler.py` — APScheduler wrapper + health
- `app/hydro_system/scheduler.py` — sensor collection job
- `app/user/routes/auth_router.py` — login and current-user endpoints
- `app/middleware/error_handler.py` — exception handling middleware