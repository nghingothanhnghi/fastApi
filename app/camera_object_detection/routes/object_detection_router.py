# backend/app/api/endpoints/object_detection_router.py
# This file is part of the backend API for a camera object detection system.
# It provides endpoints for object detection, model training, and historical data retrieval.

from fastapi import APIRouter, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, Depends, Form, Query
from fastapi.responses import JSONResponse, Response
from typing import List, Dict, Any, Optional
import numpy as np
import cv2
import shutil
import base64
import json
import os
import torch
import time
from pathlib import Path
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.logging_config import get_logger
from app.camera_object_detection.utils.image_processing import decode_base64_image, encode_image_to_base64
from app.database import get_db
from app.camera_object_detection.controllers.detector import ObjectDetector, get_detector
from app.camera_object_detection.services.detection_service import DetectionService
from app.camera_object_detection.schemas.detection import (
    DetectionResultSchema, 
    DetectionFilterSchema, 
    DetectionStatsSchema,
    DetectionResultWithObjectsSchema
)
from app.camera_object_detection.config import MODELS_DIR
from ultralytics import YOLO
from tempfile import TemporaryDirectory

# Initialize router
router = APIRouter()
logger = get_logger(__name__)

@router.post("/detect")
async def detect_objects(
    file: UploadFile = File(...),
    model_name: str = "default",
    save_to_db: bool = Query(True, description="Save detection results to database"),
    detector: ObjectDetector = Depends(get_detector),
    db: Session = Depends(get_db)
):
    """Detect objects from uploaded image file"""
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        results = detector.detect_objects(img)
        
        # Save to database if requested
        if save_to_db:
            try:
                detection_result = DetectionService.save_detection_result(
                    db=db,
                    model_name=model_name,
                    image_source="upload",
                    detections=results["detections"],
                    image_filename=file.filename,
                    image_size=results.get("image_size"),
                    processing_time_ms=results.get("processing_time_ms"),
                    annotated_image=results["annotated_image"]
                )
                results["detection_id"] = detection_result.id
                logger.info(f"Saved detection result with ID: {detection_result.id}")
            except Exception as db_error:
                logger.error(f"Failed to save detection to database: {db_error}")
                # Continue without failing the request
        
        return results
    except Exception as e:
        logger.error(f"Error in /detect: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/detect-base64")
async def detect_objects_base64(
    data: Dict[str, Any],
    model_name: str = "default",
    save_to_db: bool = Query(True, description="Save detection results to database"),
    detector: ObjectDetector = Depends(get_detector),
    db: Session = Depends(get_db)
):
    """Detect objects from base64 encoded image"""
    try:
        if "image" not in data:
            raise HTTPException(status_code=400, detail="No image data provided")
        
        img = decode_base64_image(data["image"])
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image data")

        results = detector.detect_objects(img)
        
        # Save to database if requested
        if save_to_db:
            try:
                detection_result = DetectionService.save_detection_result(
                    db=db,
                    model_name=model_name,
                    image_source="base64",
                    detections=results["detections"],
                    image_size=results.get("image_size"),
                    processing_time_ms=results.get("processing_time_ms"),
                    annotated_image=results["annotated_image"]
                )
                results["detection_id"] = detection_result.id
                logger.info(f"Saved detection result with ID: {detection_result.id}")
            except Exception as db_error:
                logger.error(f"Failed to save detection to database: {db_error}")
                # Continue without failing the request
        
        return results
    except Exception as e:
        logger.error(f"Error in /detect-base64: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    """WebSocket endpoint for real-time object detection with hardware detection"""
    try:
        await websocket.accept()
        detector = ObjectDetector()
        logger.info("Object detection WebSocket connection established")

        while True:
            try:
                data = await websocket.receive_text()
                data_json = json.loads(data)

                if "image" in data_json:
                    img = decode_base64_image(data_json["image"])
                    if img is not None:
                        # Get basic detection results
                        results = detector.detect_objects(img)
                        
                        # Enhance with hardware information if available
                        try:
                            from app.camera_object_detection.services.hardware_detection_service import HardwareDetectionService
                            
                            # Get known actuators from database
                            known_actuators = []
                            try:
                                from app.hydro_system.models.actuator import HydroActuator
                                from app.hydro_system.models.device import HydroDevice
                                
                                actuators = db.query(HydroActuator).join(HydroDevice).all()
                                known_actuators = [
                                    {
                                        "id": actuator.id,
                                        "type": actuator.type,
                                        "name": actuator.name,
                                        "device_name": actuator.device.name if actuator.device else None,
                                        "is_active": actuator.is_active
                                    }
                                    for actuator in actuators
                                ]
                            except Exception as db_error:
                                logger.warning(f"Could not fetch actuators: {db_error}")
                            
                            # Enhance detections with hardware info
                            enhanced_detections = HardwareDetectionService.enhance_detections_with_hardware_info(
                                results["detections"], known_actuators
                            )
                            results["detections"] = enhanced_detections
                            
                            # Add hardware statistics
                            hardware_stats = HardwareDetectionService.get_hardware_statistics(enhanced_detections)
                            results["hardware_stats"] = hardware_stats
                            
                            # Add known actuators info
                            results["known_actuators"] = known_actuators
                            
                        except Exception as enhance_error:
                            logger.warning(f"Could not enhance with hardware info: {enhance_error}")
                        
                        await websocket.send_json(results)
                    else:
                        await websocket.send_json({"error": "Invalid image data"})
                else:
                    await websocket.send_json({"error": "No image data provided"})
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON format"})
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")
                await websocket.send_json({"error": f"Processing error: {str(e)}"})
                
    except WebSocketDisconnect:
        logger.info("Object detection WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except Exception as close_error:
            logger.error(f"Error closing WebSocket: {close_error}")

@router.post("/train")
async def train_model(
    model_name: str = Form(...),
    epochs: int = Form(10),
    imgsz: int = Form(640),
    train_images: List[UploadFile] = File(...),
    train_labels: List[UploadFile] = File(...),
    val_images: Optional[List[UploadFile]] = File(None),
    val_labels: Optional[List[UploadFile]] = File(None)
):
    """
    Train a custom YOLOv8 model using uploaded training and validation data.
    """
    try:
        with TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            data_path = base_path / "data"
            train_img_dir = data_path / "images" / "train"
            train_lbl_dir = data_path / "labels" / "train"
            
            # Create directories for training data
            train_img_dir.mkdir(parents=True, exist_ok=True)
            train_lbl_dir.mkdir(parents=True, exist_ok=True)
            
            # Check if we have validation data
            has_validation = val_images and val_labels and len(val_images) > 0 and len(val_labels) > 0
            
            if has_validation:
                val_img_dir = data_path / "images" / "val"
                val_lbl_dir = data_path / "labels" / "val"
                val_img_dir.mkdir(parents=True, exist_ok=True)
                val_lbl_dir.mkdir(parents=True, exist_ok=True)

            # Save files
            def save_files(files, target_dir):
                if not files:
                    return
                    
                for file in files:
                    file_path = target_dir / file.filename
                    with open(file_path, "wb") as f:
                        shutil.copyfileobj(file.file, f)

            # Save training files
            save_files(train_images, train_img_dir)
            save_files(train_labels, train_lbl_dir)
            
            # Save validation files if provided
            if has_validation:
                save_files(val_images, val_img_dir)
                save_files(val_labels, val_lbl_dir)

            # Create data.yaml with or without validation
            yaml_path = base_path / "data.yaml"
            with open(yaml_path, "w") as f:
                if has_validation:
                    f.write(f"""\
path: {data_path}
train: images/train
val: images/val
nc: 1  # Modify as needed
names: ['object']  # Modify class names accordingly
""")
                else:
                    # No validation data, use only training data
                    f.write(f"""\
path: {data_path}
train: images/train
val: images/train  # Using training data for validation
nc: 1  # Modify as needed
names: ['object']  # Modify class names accordingly
""")

            # Train model
            model = YOLO("yolov8n.pt")  # Start with a base model
            
            # Configure training parameters
            train_args = {
                "data": str(yaml_path),
                "epochs": epochs,
                "imgsz": imgsz,
                "project": str(base_path),
                "name": "custom_model",
                "exist_ok": True,
                "patience": 50,  # Early stopping patience
                "batch": 16,     # Batch size
                "device": "cpu"  # Force CPU to avoid CUDA/GPU issues
            }
            
            # Start training
            logger.info(f"Starting training for model '{model_name}' with {epochs} epochs")
            results = model.train(**train_args)

            # Save final model
            trained_model_path = base_path / "custom_model" / "weights" / "best.pt"
            final_model_path = MODELS_DIR / f"{model_name}.pt"
            final_model_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(trained_model_path, final_model_path)
            
            # Save training data for later download
            model_data_dir = MODELS_DIR / model_name / "training_data"
            model_data_dir.mkdir(parents=True, exist_ok=True)
            
            # Save labels
            labels_dir = model_data_dir / "labels" / "train"
            labels_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy training labels
            for label_file in train_lbl_dir.glob("*.txt"):
                shutil.copy(label_file, labels_dir / label_file.name)
                
            # Save validation labels if available
            if has_validation:
                val_labels_dir = model_data_dir / "labels" / "val"
                val_labels_dir.mkdir(parents=True, exist_ok=True)
                
                for label_file in val_lbl_dir.glob("*.txt"):
                    shutil.copy(label_file, val_labels_dir / label_file.name)

            return {"message": f"Model '{model_name}' trained and saved successfully."}
    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
@router.get("/download-training-labels")
async def download_training_labels(model_name: str = "default"):
    """
    Download the YOLO format training labels for a specific model.
    
    Args:
        model_name: Name of the model to download labels for
    
    Returns:
        A zip file containing the YOLO format label files used for training
    """
    try:
        import zipfile
        from io import BytesIO
        import glob
        
        # Path to model's training data
        model_data_path = MODELS_DIR / model_name / "training_data"
        labels_path = model_data_path / "labels"
        
        # Check if the model and its training data exist
        if not model_data_path.exists() or not labels_path.exists():
            # If not, create sample labels instead
            logger.info(f"No training data found for model '{model_name}', generating samples")
            return await generate_sample_labels(model_name)
        
        # Create a BytesIO object to store the zip file
        zip_buffer = BytesIO()
        
        # Create a zip file
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add all label files to the zip
            for label_file in glob.glob(str(labels_path / "**" / "*.txt"), recursive=True):
                file_path = Path(label_file)
                # Get the relative path from the labels directory
                rel_path = file_path.relative_to(labels_path)
                # Add to zip with the relative path
                zip_file.write(label_file, str(rel_path))
            
            # Add a README file
            readme_content = f"""# YOLO Format Training Labels for Model: {model_name}

## Format
Each label file follows the YOLO format:
```
class_id x_center y_center width height
```

Where:
- class_id: Integer ID of the object class (0-based index)
- x_center, y_center: Normalized center coordinates of the object (0-1)
- width, height: Normalized width and height of the object (0-1)

## Usage
1. Each label file corresponds to an image file with the same name (but with .txt extension)
2. Place label files in the same directory structure as your images
3. For YOLOv8 training, organize your data as follows:
   - dataset/
     - images/
       - train/
         - image_0001.jpg
         - image_0002.jpg
         - ...
     - labels/
       - train/
         - image_0001.txt
         - image_0002.txt
         - ...
"""
            zip_file.writestr("README.md", readme_content)
        
        # Reset buffer position
        zip_buffer.seek(0)
        
        # Return the zip file
        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={model_name}_training_labels.zip"
            }
        )
    except Exception as e:
        logger.error(f"Error downloading training labels: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def generate_sample_labels(model_name: str):
    """Generate sample labels when actual training data is not available"""
    import zipfile
    from io import BytesIO
    import random
    
    # Default class names
    classes = ["person", "car", "dog", "bicycle", "motorcycle", "picture", "air-conditional", "flower", "computer", "chair", "table", "t-shirt", "pants", "shoes", "hat", "bag", "book", "phone", "clock", "tv", "lamp", "plant", "mirror", "window", "door"]
    class_ids = {name: i for i, name in enumerate(classes)}
    
    # Create a BytesIO object to store the zip file
    zip_buffer = BytesIO()
    
    # Create a zip file
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Generate sample label files
        for i in range(5):  # 5 sample files
            # Create a sample label file
            label_content = f"# YOLO format label file for image_{i:04d}.jpg\n"
            label_content += "# Format: class_id x_center y_center width height\n"
            label_content += "# All values are normalized (0-1)\n\n"
            
            # Generate random objects
            for _ in range(3):  # 3 objects per file
                # Random class
                class_name = random.choice(list(classes))
                class_id = class_ids[class_name]
                
                # Random position and size (normalized 0-1)
                x_center = round(random.uniform(0.2, 0.8), 6)
                y_center = round(random.uniform(0.2, 0.8), 6)
                width = round(random.uniform(0.05, 0.2), 6)
                height = round(random.uniform(0.05, 0.2), 6)
                
                # Add to label content
                label_content += f"{class_id} {x_center} {y_center} {width} {height} # {class_name}\n"
            
            # Add label file to zip
            zip_file.writestr(f"image_{i:04d}.txt", label_content)
        
        # Add a README file
        readme_content = f"""# Sample YOLO Format Labels for Model: {model_name}

## Format
Each label file follows the YOLO format:
```
class_id x_center y_center width height
```

Where:
- class_id: Integer ID of the object class (0-based index)
- x_center, y_center: Normalized center coordinates of the object (0-1)
- width, height: Normalized width and height of the object (0-1)

## Class Mapping
{chr(10).join([f"- Class {i}: {name}" for i, name in enumerate(classes)])}

## Note
These are sample labels generated because no actual training data was found for model '{model_name}'.
"""
        zip_file.writestr("README.md", readme_content)
    
    # Reset buffer position
    zip_buffer.seek(0)
    
    # Return the zip file
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={model_name}_sample_labels.zip"
        }
    )

@router.get("/models/list")
async def list_available_models():
    """
    List all available custom object detection models (.pt files) in the models directory.

    Returns:
        A list of model names (without the .pt extension)
    """
    try:
        model_files = MODELS_DIR.glob("*.pt")
        model_names = [file.stem for file in model_files]

        # Always include 'default' as an option if it's not already present
        if "default" not in model_names:
            model_names.insert(0, "default")

        return {"models": model_names}
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(status_code=500, detail="Unable to list models")
    
@router.delete("/models/{model_name}")
async def delete_model(model_name: str):
    """
    Delete a specific model file by name (excluding '.pt').

    Args:
        model_name: The name of the model file (without extension)

    Returns:
        Success message if deleted
    """
    model_path = MODELS_DIR / f"{model_name}.pt"

    if not model_path.exists():
        raise HTTPException(status_code=404, detail="Model not found")

    try:
        model_path.unlink()
        logger.info(f"Model '{model_name}' deleted successfully")
        return {"detail": f"Model '{model_name}' deleted successfully"}
    except Exception as e:
        logger.error(f"Failed to delete model '{model_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete model: {e}")    

# ==================== HISTORICAL DETECTION ENDPOINTS ====================

@router.get("/history", response_model=List[DetectionResultSchema])
async def get_detection_history(
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    class_name: Optional[str] = Query(None, description="Filter by detected class"),
    min_confidence: Optional[float] = Query(None, description="Minimum confidence threshold"),
    max_confidence: Optional[float] = Query(None, description="Maximum confidence threshold"),
    start_date: Optional[datetime] = Query(None, description="Start date filter (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date filter (ISO format)"),
    limit: int = Query(100, description="Maximum number of results", le=1000),
    offset: int = Query(0, description="Number of results to skip", ge=0),
    db: Session = Depends(get_db)
):
    """
    Get historical detection results with optional filters
    
    Example usage:
    - GET /history?limit=50&offset=0
    - GET /history?model_name=default&min_confidence=0.8
    - GET /history?class_name=person&start_date=2024-01-01T00:00:00
    """
    try:
        filters = DetectionFilterSchema(
            model_name=model_name,
            class_name=class_name,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset
        )
        
        results = DetectionService.get_detection_results(db, filters)
        return results
    except Exception as e:
        logger.error(f"Error retrieving detection history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{detection_id}", response_model=DetectionResultWithObjectsSchema)
async def get_detection_by_id(
    detection_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific detection result by ID with detailed object information"""
    try:
        detection_result = DetectionService.get_detection_by_id(db, detection_id)
        if not detection_result:
            raise HTTPException(status_code=404, detail="Detection result not found")
        
        # Get associated detection objects
        detection_objects = DetectionService.get_detection_objects(db, detection_id)
        
        # Convert to response schema
        result_dict = {
            "id": detection_result.id,
            "model_name": detection_result.model_name,
            "image_source": detection_result.image_source,
            "image_filename": detection_result.image_filename,
            "image_size": detection_result.image_size,
            "detections": detection_result.detections,
            "detection_count": detection_result.detection_count,
            "confidence_threshold": detection_result.confidence_threshold,
            "processing_time_ms": detection_result.processing_time_ms,
            "annotated_image": detection_result.annotated_image,
            "created_at": detection_result.created_at,
            "updated_at": detection_result.updated_at,
            "detection_objects": detection_objects
        }
        
        return result_dict
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving detection {detection_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=DetectionStatsSchema)
async def get_detection_stats(db: Session = Depends(get_db)):
    """Get detection statistics and analytics"""
    try:
        stats = DetectionService.get_detection_stats(db)
        return stats
    except Exception as e:
        logger.error(f"Error retrieving detection stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{detection_id}")
async def delete_detection_result(
    detection_id: int,
    db: Session = Depends(get_db)
):
    """Delete a specific detection result and its associated objects"""
    try:
        success = DetectionService.delete_detection_result(db, detection_id)
        if not success:
            raise HTTPException(status_code=404, detail="Detection result not found")
        
        return {"message": f"Detection result {detection_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting detection {detection_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup")
async def cleanup_old_detections(
    days_to_keep: int = Query(30, description="Number of days to keep", ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Clean up old detection results (admin function)"""
    try:
        deleted_count = DetectionService.cleanup_old_detections(db, days_to_keep)
        return {
            "message": f"Cleanup completed successfully",
            "deleted_count": deleted_count,
            "days_kept": days_to_keep
        }
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/usage")
async def get_model_usage_stats(db: Session = Depends(get_db)):
    """Get usage statistics for each model"""
    try:
        from sqlalchemy import func
        from app.camera_object_detection.models.detection import DetectionResult
        
        # Get model usage stats
        model_stats = db.query(
            DetectionResult.model_name,
            func.count(DetectionResult.id).label('total_detections'),
            func.avg(DetectionResult.detection_count).label('avg_objects_per_detection'),
            func.avg(DetectionResult.processing_time_ms).label('avg_processing_time'),
            func.max(DetectionResult.created_at).label('last_used')
        ).group_by(DetectionResult.model_name).all()
        
        results = []
        for stat in model_stats:
            results.append({
                "model_name": stat.model_name,
                "total_detections": stat.total_detections,
                "avg_objects_per_detection": round(float(stat.avg_objects_per_detection or 0), 2),
                "avg_processing_time_ms": round(float(stat.avg_processing_time or 0), 2),
                "last_used": stat.last_used
            })
        
        return {"model_usage": results}
    except Exception as e:
        logger.error(f"Error retrieving model usage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))