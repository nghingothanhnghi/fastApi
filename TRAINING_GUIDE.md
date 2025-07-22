# YOLOv8 Model Training Guide

This guide explains how to use the YOLOv8 model training interface in the application.

## Overview

The application provides a user-friendly interface for training custom YOLOv8 object detection models using your own labeled data.

## Training with Your Own Data

### Data Preparation

Before training, you need to prepare your dataset in the YOLO format:

1. **Images**: JPG or PNG files
2. **Labels**: Text files with the same name as the images, containing object annotations in YOLO format

#### YOLO Label Format

Each label file should contain one line per object in the format:
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

### Training Steps

1. Navigate to the "Train YOLOv8 Model" page
2. Enter a name for your model (e.g., "my_custom_model")
3. Set the number of training epochs (10-50 is a good starting point)
4. Select the image size (larger sizes are more accurate but slower)
5. Upload your training images and corresponding label files
6. Optionally, upload validation images and labels
7. Click "Train Model" to start the training process

## Using Trained Models

After training, your model will be saved and available for use in the object detection features:

1. Navigate to the "AR Object Detection" page
2. Enter your model name in the "Model Name" field
3. The system will use your trained model for detection

## Tips for Better Results

- Use at least 50 images per class for basic training
- Include images with varied backgrounds, lighting, and object orientations
- More epochs generally improve accuracy but may lead to overfitting
- Larger image sizes improve detection of small objects but require more processing power

## Troubleshooting

- If training fails, check that your label files are correctly formatted
- Ensure image and label filenames match exactly (except for the extension)
- For large datasets, consider training in smaller batches
- If the model is not detecting objects well, try increasing the number of epochs or using more training data