# app/ai_vision/integrations/storage_client.py
import os
import hashlib
from abc import ABC, abstractmethod
from uuid import uuid4
import cv2
from fastapi import UploadFile, HTTPException, status
from app.ai_vision import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ImageStorageService(ABC):
    @abstractmethod
    def save(self, file: UploadFile) -> dict:
        """Returns {"storage_path", "public_url", "file_size_bytes", "image_hash"}"""
        raise NotImplementedError


class LocalImageStorage(ImageStorageService):
    """Same shape as app/product/services/image_service.py's approach -
    kept here rather than reused directly because the target directory,
    URL prefix, and validation rules are AI-vision-specific."""

    def save(self, file: UploadFile) -> dict:
        if not file or not file.filename:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No file provided")
        if file.content_type not in config.ALLOWED_IMAGE_MIME_TYPES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported content type '{file.content_type}'")

        # The content type is the contract accepted by this endpoint.  Do
        # not carry a user-controlled extension into the storage path.
        extensions = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }
        ext = extensions[file.content_type]
        filename = f"{uuid4().hex}{ext}"
        file_path = os.path.join(config.AI_VISION_IMAGE_DIR, filename)

        file.file.seek(0, os.SEEK_END)
        size_bytes = file.file.tell()
        file.file.seek(0)
        if size_bytes > config.IMAGE_MAX_SIZE_MB * 1024 * 1024:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Image exceeds {config.IMAGE_MAX_SIZE_MB}MB limit")

        hasher = hashlib.sha256()
        try:
            with open(file_path, "wb") as buffer:
                for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
                    hasher.update(chunk)
                    buffer.write(chunk)
        except Exception:
            logger.exception("Failed to save AI vision image", extra={"path": file_path})
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Unable to save image")

        # UploadFile.content_type is client supplied. Validate the actual
        # bytes before persisting a record/queueing inference so malformed
        # files fail at upload time rather than becoming failed jobs later.
        image = cv2.imread(file_path, cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            try:
                os.remove(file_path)
            except OSError:
                logger.warning("Could not remove invalid AI vision upload", extra={"path": file_path})
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is not a valid image")

        height, width = image.shape[:2]

        return {
            "storage_path": file_path,
            "public_url": f"{config.AI_VISION_IMAGE_URL.rstrip('/')}/{filename}",
            "file_size_bytes": size_bytes,
            "image_hash": hasher.hexdigest(),
            "width": width,
            "height": height,
        }


def get_image_storage_service() -> ImageStorageService:
    # Swap on config.AI_VISION_STORAGE_BACKEND when S3/MinIO backends are added.
    return LocalImageStorage()


image_storage_service = get_image_storage_service()
