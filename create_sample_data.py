"""
Sample Data Creation Script

This script creates sample data for training a YOLOv8 model.
It generates synthetic images with simple shapes and corresponding YOLO format labels.
"""

import os
import random
import numpy as np
from PIL import Image, ImageDraw
from pathlib import Path

def create_sample_image(
    img_size: tuple = (640, 640),
    num_objects: int = 3,
    object_class: int = 0,
    bg_color: tuple = (240, 240, 240)
):
    """
    Create a sample image with random shapes and corresponding YOLO labels.
    
    Args:
        img_size: Image size (width, height)
        num_objects: Number of objects to draw
        object_class: Class ID for the objects
        bg_color: Background color
        
    Returns:
        image: PIL Image
        labels: List of YOLO format labels [class_id, x_center, y_center, width, height]
    """
    # Create a blank image
    image = Image.new('RGB', img_size, color=bg_color)
    draw = ImageDraw.Draw(image)
    
    # Available shapes
    shapes = ['rectangle', 'circle', 'triangle']
    
    # Generate random objects
    labels = []
    for _ in range(num_objects):
        # Random shape
        shape = random.choice(shapes)
        
        # Random size (10-20% of image size)
        obj_width = random.uniform(0.1, 0.2) * img_size[0]
        obj_height = random.uniform(0.1, 0.2) * img_size[1]
        
        # Random position
        x_center = random.uniform(0.2, 0.8) * img_size[0]
        y_center = random.uniform(0.2, 0.8) * img_size[1]
        
        # Calculate corners
        x1 = x_center - obj_width / 2
        y1 = y_center - obj_height / 2
        x2 = x_center + obj_width / 2
        y2 = y_center + obj_height / 2
        
        # Random color
        color = (
            random.randint(0, 200),
            random.randint(0, 200),
            random.randint(0, 200)
        )
        
        # Draw shape
        if shape == 'rectangle':
            draw.rectangle([x1, y1, x2, y2], fill=color)
        elif shape == 'circle':
            draw.ellipse([x1, y1, x2, y2], fill=color)
        elif shape == 'triangle':
            points = [
                (x_center, y1),
                (x1, y2),
                (x2, y2)
            ]
            draw.polygon(points, fill=color)
        
        # Create YOLO format label
        # [class_id, x_center, y_center, width, height] - normalized to 0-1
        label = [
            object_class,
            x_center / img_size[0],
            y_center / img_size[1],
            obj_width / img_size[0],
            obj_height / img_size[1]
        ]
        labels.append(label)
    
    return image, labels

def create_dataset(
    num_train: int = 50,
    num_val: int = 10,
    img_size: tuple = (640, 640),
    dataset_path: str = "dataset"
):
    """
    Create a sample dataset for YOLOv8 training.
    
    Args:
        num_train: Number of training images
        num_val: Number of validation images
        img_size: Image size (width, height)
        dataset_path: Path to the dataset directory
    """
    # Create directories
    dataset_dir = Path(dataset_path)
    train_img_dir = dataset_dir / "images" / "train"
    val_img_dir = dataset_dir / "images" / "val"
    train_lbl_dir = dataset_dir / "labels" / "train"
    val_lbl_dir = dataset_dir / "labels" / "val"
    
    # Ensure directories exist
    for dir_path in [train_img_dir, val_img_dir, train_lbl_dir, val_lbl_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)
    
    # Create training data
    print(f"Creating {num_train} training samples...")
    for i in range(num_train):
        # Create image and labels
        image, labels = create_sample_image(img_size=img_size)
        
        # Save image
        img_path = train_img_dir / f"train_{i:04d}.jpg"
        image.save(img_path)
        
        # Save labels
        lbl_path = train_lbl_dir / f"train_{i:04d}.txt"
        with open(lbl_path, 'w') as f:
            for label in labels:
                f.write(' '.join(map(str, label)) + '\n')
    
    # Create validation data
    print(f"Creating {num_val} validation samples...")
    for i in range(num_val):
        # Create image and labels
        image, labels = create_sample_image(img_size=img_size)
        
        # Save image
        img_path = val_img_dir / f"val_{i:04d}.jpg"
        image.save(img_path)
        
        # Save labels
        lbl_path = val_lbl_dir / f"val_{i:04d}.txt"
        with open(lbl_path, 'w') as f:
            for label in labels:
                f.write(' '.join(map(str, label)) + '\n')
    
    print(f"Dataset created at {dataset_dir.absolute()}")
    print(f"- Training images: {num_train}")
    print(f"- Validation images: {num_val}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Create sample data for YOLOv8 training")
    parser.add_argument("--train", type=int, default=50, help="Number of training images")
    parser.add_argument("--val", type=int, default=10, help="Number of validation images")
    parser.add_argument("--width", type=int, default=640, help="Image width")
    parser.add_argument("--height", type=int, default=640, help="Image height")
    parser.add_argument("--path", type=str, default="dataset", help="Path to dataset directory")
    
    args = parser.parse_args()
    
    create_dataset(
        num_train=args.train,
        num_val=args.val,
        img_size=(args.width, args.height),
        dataset_path=args.path
    )