# System Architecture Documentation

## 🏗️ Detailed Architecture Diagrams

### 1. High-Level System Overview

```mermaid
graph TB
    subgraph "External Clients"
        WEB[Web Dashboard]
        MOBILE[Mobile App]
        IOT[IoT Devices]
        THIRD_PARTY[Third-party APIs]
    end

    subgraph "FastAPI Application Layer"
        GATEWAY[API Gateway]
        AUTH_MW[Auth Middleware]
        CORS_MW[CORS Middleware]
        ERROR_MW[Error Handler]
    end

    subgraph "Business Logic Layer"
        AUTH_SVC[Auth Service]
        USER_SVC[User Service]
        HYDRO_SVC[Hydro Service]
        ANDROID_SVC[Android Service]
        VISION_SVC[Vision Service]
        DATA_SVC[Data Service]
    end

    subgraph "Data Access Layer"
        ORM[SQLAlchemy ORM]
        CACHE[Redis Cache]
        FILE_SYS[File System]
    end

    subgraph "Infrastructure Layer"
        DB[(PostgreSQL)]
        STORAGE[File Storage]
        QUEUE[Task Queue]
        SCHEDULER[Background Jobs]
    end

    WEB --> GATEWAY
    MOBILE --> GATEWAY
    IOT --> GATEWAY
    THIRD_PARTY --> GATEWAY

    GATEWAY --> AUTH_MW
    AUTH_MW --> CORS_MW
    CORS_MW --> ERROR_MW

    ERROR_MW --> AUTH_SVC
    ERROR_MW --> USER_SVC
    ERROR_MW --> HYDRO_SVC
    ERROR_MW --> ANDROID_SVC
    ERROR_MW --> VISION_SVC
    ERROR_MW --> DATA_SVC

    AUTH_SVC --> ORM
    USER_SVC --> ORM
    HYDRO_SVC --> ORM
    ANDROID_SVC --> ORM
    VISION_SVC --> ORM
    DATA_SVC --> ORM

    ORM --> DB
    CACHE --> DB
    FILE_SYS --> STORAGE
    QUEUE --> SCHEDULER
```

### 2. Hydroponic System Architecture

```mermaid
graph LR
    subgraph "Sensors"
        PH[pH Sensor]
        TEMP[Temperature]
        HUMID[Humidity]
        WATER[Water Level]
        LIGHT[Light Sensor]
    end

    subgraph "Controllers"
        PUMP[Water Pump]
        FAN[Ventilation Fan]
        LED[LED Lights]
        HEATER[Heater]
        VALVE[Nutrient Valve]
    end

    subgraph "Hydro System Core"
        SENSOR_MGR[Sensor Manager]
        DEVICE_CTRL[Device Controller]
        RULES_ENGINE[Rules Engine]
        STATE_MGR[State Manager]
        SCHEDULER[Scheduler]
    end

    subgraph "Data Flow"
        COLLECTOR[Data Collector]
        PROCESSOR[Data Processor]
        STORAGE[(Database)]
        ALERTS[Alert System]
    end

    PH --> SENSOR_MGR
    TEMP --> SENSOR_MGR
    HUMID --> SENSOR_MGR
    WATER --> SENSOR_MGR
    LIGHT --> SENSOR_MGR

    SENSOR_MGR --> RULES_ENGINE
    RULES_ENGINE --> DEVICE_CTRL
    DEVICE_CTRL --> STATE_MGR

    DEVICE_CTRL --> PUMP
    DEVICE_CTRL --> FAN
    DEVICE_CTRL --> LED
    DEVICE_CTRL --> HEATER
    DEVICE_CTRL --> VALVE

    SENSOR_MGR --> COLLECTOR
    COLLECTOR --> PROCESSOR
    PROCESSOR --> STORAGE
    PROCESSOR --> ALERTS

    SCHEDULER --> RULES_ENGINE
    STATE_MGR --> STORAGE
```

### 3. Android Device Management Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant DeviceManager
    participant ADB
    participant AndroidDevice

    Client->>API: GET /devices
    API->>DeviceManager: list_devices()
    DeviceManager->>ADB: adb devices
    ADB-->>DeviceManager: device list
    DeviceManager-->>API: formatted device info
    API-->>Client: JSON response

    Client->>API: POST /devices/{id}/connect
    API->>DeviceManager: connect_device(id)
    DeviceManager->>ADB: adb connect {ip}
    ADB->>AndroidDevice: establish connection
    AndroidDevice-->>ADB: connection confirmed
    ADB-->>DeviceManager: connection status
    DeviceManager-->>API: success/failure
    API-->>Client: connection result

    Client->>API: GET /screen/{id}
    API->>DeviceManager: get_screen(id)
    DeviceManager->>ADB: adb exec-out screencap
    ADB->>AndroidDevice: capture screen
    AndroidDevice-->>ADB: screen data
    ADB-->>DeviceManager: image bytes
    DeviceManager-->>API: processed image
    API-->>Client: screen image
```

### 4. Object Detection Pipeline

```mermaid
graph TD
    subgraph "Input Sources"
        CAMERA[IP Camera]
        UPLOAD[File Upload]
        STREAM[Video Stream]
    end

    subgraph "Preprocessing"
        RESIZE[Image Resize]
        NORMALIZE[Normalization]
        AUGMENT[Data Augmentation]
    end

    subgraph "Model Inference"
        YOLO[YOLO Model]
        POSTPROCESS[Post-processing]
        NMS[Non-Max Suppression]
    end

    subgraph "Output Processing"
        BBOX[Bounding Boxes]
        LABELS[Class Labels]
        CONFIDENCE[Confidence Scores]
        ANNOTATE[Image Annotation]
    end

    subgraph "Storage & Analytics"
        RESULTS[(Results DB)]
        METRICS[Performance Metrics]
        LOGS[Detection Logs]
    end

    CAMERA --> RESIZE
    UPLOAD --> RESIZE
    STREAM --> RESIZE

    RESIZE --> NORMALIZE
    NORMALIZE --> AUGMENT
    AUGMENT --> YOLO

    YOLO --> POSTPROCESS
    POSTPROCESS --> NMS
    NMS --> BBOX

    BBOX --> LABELS
    LABELS --> CONFIDENCE
    CONFIDENCE --> ANNOTATE

    ANNOTATE --> RESULTS
    BBOX --> METRICS
    LABELS --> LOGS
```

### 5. Data Processing Pipeline

```mermaid
graph LR
    subgraph "Data Sources"
        SENSORS[Sensor Data]
        LOGS[Application Logs]
        IMAGES[Image Data]
        USER_DATA[User Input]
    end

    subgraph "Ingestion Layer"
        COLLECTOR[Data Collector]
        VALIDATOR[Data Validator]
        QUEUE[Message Queue]
    end

    subgraph "Processing Layer"
        ETL[ETL Pipeline]
        TRANSFORMER[Data Transformer]
        AGGREGATOR[Data Aggregator]
        CLEANER[Data Cleaner]
    end

    subgraph "Storage Layer"
        RAW_DB[(Raw Data)]
        PROCESSED_DB[(Processed Data)]
        ANALYTICS_DB[(Analytics)]
        CACHE[(Cache)]
    end

    subgraph "Output Layer"
        API_RESP[API Responses]
        REPORTS[Reports]
        ALERTS[Alerts]
        DASHBOARD[Dashboard]
    end

    SENSORS --> COLLECTOR
    LOGS --> COLLECTOR
    IMAGES --> COLLECTOR
    USER_DATA --> COLLECTOR

    COLLECTOR --> VALIDATOR
    VALIDATOR --> QUEUE
    QUEUE --> ETL

    ETL --> TRANSFORMER
    TRANSFORMER --> AGGREGATOR
    AGGREGATOR --> CLEANER

    CLEANER --> RAW_DB
    CLEANER --> PROCESSED_DB
    CLEANER --> ANALYTICS_DB
    CLEANER --> CACHE

    PROCESSED_DB --> API_RESP
    ANALYTICS_DB --> REPORTS
    PROCESSED_DB --> ALERTS
    CACHE --> DASHBOARD
```

### 6. Authentication & Authorization Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant AuthService
    participant Database
    participant TokenService

    User->>Frontend: Login Request
    Frontend->>API: POST /auth/login
    API->>AuthService: authenticate(credentials)
    AuthService->>Database: verify user
    Database-->>AuthService: user data
    AuthService->>TokenService: generate_tokens(user)
    TokenService-->>AuthService: access & refresh tokens
    AuthService-->>API: authentication result
    API-->>Frontend: tokens + user info
    Frontend-->>User: login success

    Note over Frontend: Store tokens securely

    User->>Frontend: Protected Resource Request
    Frontend->>API: GET /protected (with token)
    API->>AuthService: verify_token(token)
    AuthService->>TokenService: validate_token(token)
    TokenService-->>AuthService: token valid
    AuthService->>Database: get user permissions
    Database-->>AuthService: user roles
    AuthService-->>API: authorization result
    API-->>Frontend: protected data
    Frontend-->>User: display data
```

### 7. Background Job Architecture

```mermaid
graph TB
    subgraph "Scheduler Core"
        APSCHEDULER[APScheduler]
        JOB_STORE[Job Store]
        EXECUTOR[Thread Executor]
    end

    subgraph "Job Types"
        SENSOR_JOB[Sensor Data Collection]
        TRANSFORM_JOB[Data Transformation]
        CLEANUP_JOB[Database Cleanup]
        HEALTH_JOB[Health Monitoring]
        BACKUP_JOB[Data Backup]
    end

    subgraph "Job Management"
        SCHEDULER_API[Scheduler API]
        JOB_MONITOR[Job Monitor]
        ERROR_HANDLER[Error Handler]
        RETRY_LOGIC[Retry Logic]
    end

    subgraph "External Systems"
        SENSORS[IoT Sensors]
        DATABASE[(Database)]
        FILE_SYS[File System]
        EMAIL[Email Service]
    end

    APSCHEDULER --> JOB_STORE
    APSCHEDULER --> EXECUTOR
    EXECUTOR --> SENSOR_JOB
    EXECUTOR --> TRANSFORM_JOB
    EXECUTOR --> CLEANUP_JOB
    EXECUTOR --> HEALTH_JOB
    EXECUTOR --> BACKUP_JOB

    SCHEDULER_API --> APSCHEDULER
    JOB_MONITOR --> APSCHEDULER
    ERROR_HANDLER --> RETRY_LOGIC

    SENSOR_JOB --> SENSORS
    TRANSFORM_JOB --> DATABASE
    CLEANUP_JOB --> DATABASE
    HEALTH_JOB --> EMAIL
    BACKUP_JOB --> FILE_SYS
```

## 🔧 Component Interactions

### Database Schema Overview

```mermaid
erDiagram
    User ||--o{ UserRole : has
    User ||--o{ SensorData : creates
    User ||--o{ DetectionResult : owns
    
    UserRole ||--|| Role : references
    
    SensorData ||--|| HydroSystem : belongs_to
    HydroSystem ||--o{ Device : contains
    
    DetectionResult ||--|| ObjectModel : uses
    ObjectModel ||--o{ TrainingData : trained_on
    
    MigrationJob ||--o{ TransformJob : triggers
    TransformJob ||--o{ ProcessedData : produces
```

### API Request Flow

```mermaid
graph TD
    REQUEST[HTTP Request] --> CORS[CORS Middleware]
    CORS --> AUTH[Auth Middleware]
    AUTH --> VALIDATION[Request Validation]
    VALIDATION --> ROUTER[Route Handler]
    ROUTER --> SERVICE[Business Logic]
    SERVICE --> REPOSITORY[Data Access]
    REPOSITORY --> DATABASE[(Database)]
    DATABASE --> REPOSITORY
    REPOSITORY --> SERVICE
    SERVICE --> RESPONSE[HTTP Response]
    RESPONSE --> CLIENT[Client]
    
    AUTH --> TOKEN_VERIFY[Token Verification]
    TOKEN_VERIFY --> PERMISSION[Permission Check]
    PERMISSION --> ROUTER
    
    SERVICE --> CACHE[Cache Layer]
    CACHE --> SERVICE
    
    SERVICE --> BACKGROUND[Background Jobs]
    BACKGROUND --> QUEUE[Task Queue]
```

This architecture documentation provides a comprehensive view of how all the components in your FastAPI IoT automation system work together. The diagrams show the relationships between different modules, data flow, and system interactions.