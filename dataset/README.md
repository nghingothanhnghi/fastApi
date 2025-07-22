# YOLOv8 Training Dataset

This folder contains the dataset structure for training YOLOv8 object detection models.

## Folder Structure

```
dataset/
├── images/
│   ├── train/  # Training images (.jpg, .png, etc.)
│   └── val/    # Validation images (.jpg, .png, etc.)
├── labels/
│   ├── train/  # Training labels (.txt files in YOLO format)
│   └── val/    # Validation labels (.txt files in YOLO format)
└── data.yaml   # Dataset configuration file
```

## Label Format

YOLO label format is one text file per image with the same name (e.g., image.jpg → image.txt). Each line in the text file represents one object and follows this format:

```
class_id x_center y_center width height
```

Where:
- `class_id`: Integer representing the class (0-based index)
- `x_center, y_center`: Normalized center coordinates (0.0-1.0)
- `width, height`: Normalized width and height (0.0-1.0)

Example:
```
0 0.5 0.5 0.2 0.3
```

## Training

To train a model using this dataset, you can use the `/train` endpoint in the API or run the training directly with YOLOv8:

```python
from ultralytics import YOLO

# Load a model
model = YOLO("yolov8n.pt")  # load a pretrained model

# Train the model
results = model.train(
    data="path/to/dataset/data.yaml",
    epochs=100,
    imgsz=640,
    batch=16
)
```

## Adding Your Own Data

1. Place your training images in `images/train/`
2. Place your validation images in `images/val/`
3. Add corresponding label files in `labels/train/` and `labels/val/`
4. Update the `data.yaml` file with your class names