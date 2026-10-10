"""
YOLOv8 Training Script

This script trains a YOLOv8 model using the dataset in the dataset/ folder.
"""

import os
import argparse
from ultralytics import YOLO
from pathlib import Path

def train_model(
    model_name: str = "yolov8n.pt",
    epochs: int = 50,
    imgsz: int = 640,
    batch: int = 16,
    save_dir: str = "app/models/custom_objects"
):
    """
    Train a YOLOv8 model using the dataset in the dataset/ folder.
    
    Args:
        model_name: Base model to start from (yolov8n.pt, yolov8s.pt, etc.)
        epochs: Number of training epochs
        imgsz: Image size for training
        batch: Batch size
        save_dir: Directory to save the trained model
    """
    # Get the absolute path to the dataset
    dataset_path = Path("dataset/data.yaml").absolute()
    
    # Check if dataset exists
    if not dataset_path.exists():
        print(f"Error: Dataset configuration file not found at {dataset_path}")
        return
    
    # Check if there are images in the dataset
    train_images_path = Path("dataset/images/train")
    if not train_images_path.exists() or not any(train_images_path.iterdir()):
        print(f"Error: No training images found in {train_images_path}")
        return
    
    # Create save directory if it doesn't exist
    save_dir_path = Path(save_dir)
    save_dir_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Starting training with {model_name} for {epochs} epochs...")
    print(f"Dataset: {dataset_path}")
    
    # Load the model
    model = YOLO(model_name)
    
    # Train the model
    results = model.train(
        data=str(dataset_path),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        name="custom_model"
    )
    
    # Save the trained model
    final_model_path = save_dir_path / f"{Path(model_name).stem}_custom.pt"
    model.export(format="pt")
    
    # Copy the best model to the custom_objects directory
    best_model_path = Path("runs/detect/custom_model/weights/best.pt")
    if best_model_path.exists():
        import shutil
        shutil.copy(best_model_path, final_model_path)
        print(f"Model saved to {final_model_path}")
    else:
        print(f"Warning: Best model not found at {best_model_path}")
    
    print("Training completed!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train a YOLOv8 model")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Base model to start from")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size for training")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--save-dir", type=str, default="app/models/custom_objects", help="Directory to save the trained model")
    
    args = parser.parse_args()
    
    train_model(
        model_name=args.model,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        save_dir=args.save_dir
    )