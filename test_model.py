"""
YOLOv8 Model Testing Script

This script tests a trained YOLOv8 model on a single image or a directory of images.
"""

import os
import argparse
import cv2
import numpy as np
from pathlib import Path
from ultralytics import YOLO

def test_model(
    model_path: str,
    image_path: str,
    conf_threshold: float = 0.25,
    save_results: bool = True,
    output_dir: str = "results"
):
    """
    Test a YOLOv8 model on an image or directory of images.
    
    Args:
        model_path: Path to the trained model
        image_path: Path to an image or directory of images
        conf_threshold: Confidence threshold for detections
        save_results: Whether to save the results
        output_dir: Directory to save the results
    """
    # Check if model exists
    if not Path(model_path).exists():
        print(f"Error: Model not found at {model_path}")
        return
    
    # Check if image path exists
    image_path = Path(image_path)
    if not image_path.exists():
        print(f"Error: Image path not found at {image_path}")
        return
    
    # Create output directory if saving results
    if save_results:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
    
    # Load the model
    print(f"Loading model from {model_path}...")
    model = YOLO(model_path)
    
    # Get list of images
    if image_path.is_dir():
        image_files = [f for f in image_path.glob("*") if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp']]
        print(f"Found {len(image_files)} images in {image_path}")
    else:
        image_files = [image_path]
        print(f"Testing on single image: {image_path}")
    
    # Process each image
    for img_file in image_files:
        print(f"Processing {img_file.name}...")
        
        # Run inference
        results = model(str(img_file), conf=conf_threshold)
        
        # Get results
        result = results[0]
        
        # Print detections
        print(f"Found {len(result.boxes)} objects:")
        for i, box in enumerate(result.boxes):
            cls_id = int(box.cls[0].item())
            cls_name = result.names[cls_id]
            conf = box.conf[0].item()
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            print(f"  {i+1}. {cls_name}: {conf:.2f} at [{int(x1)}, {int(y1)}, {int(x2)}, {int(y2)}]")
        
        # Save results
        if save_results:
            # Get annotated image
            annotated_img = result.plot()
            
            # Save to output directory
            output_file = output_path / f"{img_file.stem}_result{img_file.suffix}"
            cv2.imwrite(str(output_file), annotated_img)
            print(f"  Saved result to {output_file}")
    
    print("Testing completed!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test a YOLOv8 model")
    parser.add_argument("--model", type=str, required=True, help="Path to the trained model")
    parser.add_argument("--image", type=str, required=True, help="Path to an image or directory of images")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--save", action="store_true", help="Save the results")
    parser.add_argument("--output", type=str, default="results", help="Directory to save the results")
    
    args = parser.parse_args()
    
    test_model(
        model_path=args.model,
        image_path=args.image,
        conf_threshold=args.conf,
        save_results=args.save,
        output_dir=args.output
    )