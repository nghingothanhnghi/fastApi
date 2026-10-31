# FastAPI IoT Automation System

A comprehensive Python FastAPI server for IoT automation, featuring hydroponic system control, Android device management, computer vision object detection, AI-assisted plant-image analysis, and data processing pipelines.

## 🏗️ System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        WEB[Web Interface]
        MOBILE[Mobile App]
        API_CLIENT[API Clients]
    end

    subgraph "FastAPI Application"
        MAIN[main.py - FastAPI App]
        MIDDLEWARE[Middleware Layer]
        ROUTERS[API Routers]
    end

    subgraph "Core Modules"
        AUTH[Authentication & Authorization]
        USER[User Management]
        HYDRO[Hydro System Control]
        ANDROID[Android Device Management]
        VISION[Object Detection]
        AI_VISION[AI Plant Vision]
        DATA[Data Processing]
    end

    subgraph "Background Services"
        SCHEDULER[APScheduler Jobs]
        SENSOR_JOB[Sensor Data Collection]
        TRANSFORM_JOB[Data Transformation]
    end

    subgraph "Data Layer"
        DB[(Database - PostgreSQL/SQLite)]
        FILES[File Storage]
        MODELS[ML Models]
    end

    subgraph "External Systems"
        ADB[Android Debug Bridge]
        CAMERAS[IP Cameras]
        SENSORS[IoT Sensors]
        EMAIL[Email Service]
    end

    WEB --> MAIN
    MOBILE --> MAIN
    API_CLIENT --> MAIN
    
    MAIN --> MIDDLEWARE
    MIDDLEWARE --> ROUTERS
    ROUTERS --> AUTH
    ROUTERS --> USER
    ROUTERS --> HYDRO
    ROUTERS --> ANDROID
    ROUTERS --> VISION
    ROUTERS --> AI_VISION
    ROUTERS --> DATA
    
    MAIN --> SCHEDULER
    SCHEDULER --> SENSOR_JOB
    SCHEDULER --> TRANSFORM_JOB
    
    AUTH --> DB
    USER --> DB
    HYDRO --> DB
    ANDROID --> DB
    VISION --> DB
    AI_VISION --> DB
    DATA --> DB
    
    HYDRO --> SENSORS
    ANDROID --> ADB
    VISION --> CAMERAS
    VISION --> MODELS
    AI_VISION --> MODELS
    USER --> EMAIL
    
    SENSOR_JOB --> SENSORS
    TRANSFORM_JOB --> FILES
```

## 📋 Module Overview

### 🔐 Authentication & User Management
- **JWT-based authentication** with role-based access control
- **User registration, login, and profile management**
- **Password reset functionality** with email notifications
- **Role-based permissions** (Admin, User, etc.)

### 🌱 Hydroponic System Control
- **Real-time sensor monitoring** (pH, temperature, humidity, water level)
- **Automated device control** (pumps, lights, fans)
- **Rules engine** for automated responses
- **Scheduling system** for timed operations
- **State management** for system status tracking

### 📱 Android Device Management
- **ADB integration** for device control
- **Screen streaming** and remote interaction
- **Device discovery** and connection management
- **Mock device support** for testing
- **Tap simulation** and gesture control

### 👁️ Computer Vision & Object Detection
- **YOLO-based object detection** using Ultralytics
- **Real-time image processing** with OpenCV
- **Custom model training** support
- **Image annotation** and dataset management
- **Performance monitoring** and analytics

### 🌿 AI Plant Vision
- **Tenant-scoped plant/camera, image, and inference-job APIs**
- **Queued image analysis** with lease recovery and annotated output images
- **YOLO plant detection, HSV health signals, and classical-CV disease/pest proxies**
- **Growth, health, sensor-context, anomaly, recommendation, and read-only forecast records**
- Current models are heuristics/general-purpose models, not trained crop-diagnosis models; recommendations never control actuators automatically.

### 📊 Data Processing Pipeline
- **Data ingestion** from multiple sources
- **ETL transformations** with scheduled jobs
- **Migration tools** for data movement
- **Batch processing** capabilities
- **Data validation** and quality checks

## 🚀 Quick Start

### Prerequisites
- **Python 3.8+**
- **PostgreSQL** (or SQLite for development)
- **Android Debug Bridge (ADB)** for Android device control
- **CUDA-compatible GPU** (optional, for ML acceleration)

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd fastApi
```

2. **Create virtual environment**
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Environment setup**
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
# DATABASE_URL=postgresql://user:password@localhost/dbname
# ADB_HOST=127.0.0.1
# ADB_PORT=5037
# USE_MOCK_DEVICES=true
```

5. **Initialize database**
```bash
python app/init_db.py
```

6. **Run the application**
```bash
# Development
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production
python main.py
```

## 📡 API Endpoints

### Authentication
- `POST /auth/login` - User login
- `POST /auth/register` - User registration
- `POST /auth/refresh` - Token refresh
- `POST /password-reset/request` - Request password reset
- `POST /password-reset/confirm` - Confirm password reset

### User Management
- `GET /users/me` - Get current user profile
- `PUT /users/me` - Update user profile
- `GET /roles` - List available roles

### Hydroponic System
- `GET /hydro/status` - Get system status
- `POST /hydro/control` - Control devices
- `GET /sensor/data` - Get sensor readings
- `POST /sensor/data` - Submit sensor data

### Android Devices
- `GET /devices` - List connected devices
- `POST /devices/{device_id}/connect` - Connect to device
- `GET /screen/{device_id}` - Get device screen
- `POST /tap` - Simulate tap gesture

### Object Detection
- `POST /object-detection/detect` - Detect objects in image
- `GET /object-detection/models` - List available models
- `POST /object-detection/train` - Start model training

### AI Plant Vision
- `POST /api/v1/plants` and `POST /api/v1/cameras` - Create AI-vision entities
- `POST /api/v1/vision/images?plant_id={plant_id}` - Upload an image and queue analysis
- `POST /api/v1/vision/analyze/{image_id}` - Run a manually requested analysis
- `GET /api/v1/ai/inference/{job_id}` - Retrieve inference-job status and image URLs
- `GET /api/v1/plants/{plant_id}/growth-predictions` - Retrieve growth forecasts
- `GET /api/v1/plants/{plant_id}/recommendations` - List recommendations, newest first
- `PATCH /api/v1/plants/{plant_id}/recommendations/{recommendation_id}/status` - Review a recommendation (`{"status": "acknowledged" | "dismissed"}`)

### System Health
- `GET /health` - Application health check
- `GET /scheduler/health` - Scheduler status

## 🔧 Configuration

### Environment Variables
```env
# Database
DATABASE_URL=postgresql://user:password@localhost/dbname

# Android Debug Bridge
ADB_HOST=127.0.0.1
ADB_PORT=5037
USE_MOCK_DEVICES=false

# File Upload
UPLOAD_DIR=uploads/profile_images
STATIC_URL_BASE=/static/profile_images

# Email (for password reset)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Security
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# AI plant vision
AI_ENABLED=true
AI_USE_REAL_MODELS=true
AI_DETECTOR_WEIGHTS=yolov8n.pt
AI_JOB_LEASE_SECONDS=600
AI_VISION_IMAGE_DIR=uploads/ai_vision
AI_VISION_IMAGE_URL=/static/ai_vision
```

### Scheduler Jobs
The application runs several background jobs:
- **Sensor data collection** (every 30 seconds)
- **Data transformation** (every 10 seconds)
- **System health monitoring** (every 5 minutes)

## 🧪 Testing

### Run Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest test_model.py

# Run with coverage
pytest --cov=app tests/
```

### Create Sample Data
```bash
python create_sample_data.py
```

### Model Training
```bash
python train_model.py
```

## 📁 Project Structure

```
fastApi/
├── app/
│   ├── data/          # Database
│   ├── android_system/         # Android device management
│   ├── camera_object_detection/# Computer vision module
│   ├── ai_vision/              # Plant-image analysis module
│   ├── core/                   # Core configuration
│   ├── hydro_system/          # Hydroponic system control
│   ├── middleware/            # Custom middleware
│   ├── migration/             # Data migration tools
│   ├── models/                # Database models
│   ├── transform_data/        # Data processing pipeline
│   ├── user/                  # User management
│   ├── utils/                 # Utility functions
│   ├── database.py            # Database configuration
│   └── init_db.py            # Database initialization
├── dataset/                   # ML training datasets
├── main.py                    # FastAPI application entry point
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables
└── README.md                  # This file
```

## 🔒 Security Features

- **JWT token authentication** with refresh tokens
- **Password hashing** using bcrypt
- **Role-based access control** (RBAC)
- **CORS middleware** configuration
- **Input validation** using Pydantic
- **SQL injection protection** via SQLAlchemy ORM
- **Rate limiting** and error handling

## 🚀 Deployment

### Docker Deployment
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Production Considerations
- Use **PostgreSQL** for production database
- Configure **reverse proxy** (Nginx)
- Set up **SSL certificates**
- Enable **logging** and monitoring
- Configure **backup strategies**
- Use **environment-specific** configurations

## 📚 Additional Documentation

- [Super Admin Guide](SUPER_ADMIN_GUIDE.md) - Administrative functions
- [Training Guide](TRAINING_GUIDE.md) - ML model training
- [Dataset README](dataset/README.md) - Dataset information

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🔧 Local Setup Guide
