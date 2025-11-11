import os
import shutil
from fastapi import HTTPException, status, UploadFile
from uuid import uuid4
from app.core import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class ImageService:
    @staticmethod
    def save_image(file: UploadFile, folder: str = "products") -> str:
        if not file or not file.filename:
            logger.warning("Missing upload file metadata")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file provided")
        upload_dir = os.path.join(config.MEDIA_DIR, folder)
        try:
            os.makedirs(upload_dir, exist_ok=True)
        except Exception:
            logger.exception("Failed to create media directory", extra={"path": upload_dir})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to prepare storage")
        ext = os.path.splitext(file.filename)[1] or ".bin"
        filename = f"{uuid4()}{ext}"
        file_path = os.path.join(upload_dir, filename)
        file.file.seek(0)
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception:
            logger.exception("Failed to save image", extra={"path": file_path})
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to save file")
        logger.info("Image saved", extra={"path": file_path})
        url_path = f"{config.MEDIA_URL.rstrip('/')}/{filename}"
        return url_path