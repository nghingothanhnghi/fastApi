import base64
import cv2
import numpy as np
from typing import Optional, Tuple, Dict, Any
import io
from PIL import Image

def decode_base64_image(base64_string: str) -> Optional[np.ndarray]:
    """
    Decode a base64 string into an OpenCV image.
    
    Args:
        base64_string: Base64 encoded image string
        
    Returns:
        numpy.ndarray: OpenCV image or None if decoding fails
    """
    try:
        # Remove data URL prefix if present
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        
        # Decode base64 string
        img_data = base64.b64decode(base64_string)
        
        # Convert to numpy array
        nparr = np.frombuffer(img_data, np.uint8)
        
        # Decode image
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        return img
    except Exception as e:
        print(f"Error decoding base64 image: {e}")
        return None

def encode_image_to_base64(image: np.ndarray) -> str:
    """
    Encode an OpenCV image to base64 string.
    
    Args:
        image: OpenCV image (numpy.ndarray)
        
    Returns:
        str: Base64 encoded image string
    """
    try:
        # Encode image to jpg format
        success, buffer = cv2.imencode('.jpg', image)
        if not success:
            return ""
        
        # Convert to base64
        encoded_image = base64.b64encode(buffer).decode('utf-8')
        
        return encoded_image
    except Exception as e:
        print(f"Error encoding image to base64: {e}")
        return ""

def resize_image(image: np.ndarray, target_size: Tuple[int, int]) -> np.ndarray:
    """
    Resize an image to the target size.
    
    Args:
        image: OpenCV image
        target_size: Target size as (width, height)
        
    Returns:
        numpy.ndarray: Resized image
    """
    return cv2.resize(image, target_size, interpolation=cv2.INTER_AREA)

def preprocess_image_for_model(image: np.ndarray, target_size: Tuple[int, int] = (640, 640)) -> np.ndarray:
    """
    Preprocess an image for model input.
    
    Args:
        image: OpenCV image
        target_size: Target size for the model input
        
    Returns:
        numpy.ndarray: Preprocessed image
    """
    # Resize image
    resized = resize_image(image, target_size)
    
    # Convert BGR to RGB (if using PyTorch models)
    rgb_image = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    
    return rgb_image

def draw_bounding_boxes(
    image: np.ndarray, 
    detections: Dict[str, Any],
    color: Tuple[int, int, int] = (0, 255, 0),
    thickness: int = 2
) -> np.ndarray:
    """
    Draw bounding boxes on an image based on detection results.
    
    Args:
        image: OpenCV image
        detections: Dictionary containing detection results
        color: BGR color tuple for the bounding box
        thickness: Line thickness
        
    Returns:
        numpy.ndarray: Image with bounding boxes
    """
    result_image = image.copy()
    
    for detection in detections:
        # Get bounding box coordinates
        x1, y1, x2, y2 = detection["bbox"]
        
        # Convert to integers
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        
        # Draw rectangle
        cv2.rectangle(result_image, (x1, y1), (x2, y2), color, thickness)
        
        # Add label
        label = f"{detection['class']}: {detection['confidence']:.2f}"
        cv2.putText(
            result_image, 
            label, 
            (x1, y1 - 10), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.5, 
            color, 
            thickness
        )
    
    return result_image