import os
import shutil
from fastapi import UploadFile
from sqlalchemy.orm import Session
from app.product.models.product import ProductVariant
from uuid import uuid4
from app.core import config

class ImageService:
    @staticmethod
    def save_image(file: UploadFile, folder: str = "products") -> str:

        # Create subfolder under MEDIA_DIR
        upload_dir = os.path.join(config.MEDIA_DIR, folder)
        os.makedirs(upload_dir, exist_ok=True)

        ext = os.path.splitext(file.filename)[1]
        filename = f"{uuid4()}{ext}"
        file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Return accessible URL path
        return f"{config.MEDIA_URL}/{folder}/{filename}"