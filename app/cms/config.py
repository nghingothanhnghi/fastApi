# app/cms/config.py
# Configuration for the CMS module (media storage, pagination, limits).
import os
from pathlib import Path

CMS_MEDIA_DIR = os.getenv("CMS_MEDIA_DIR", "uploads/cms_media")
CMS_MEDIA_URL = os.getenv("CMS_MEDIA_URL", "/static/cms_media")

# NOTE: .svg is intentionally excluded (can embed scripts -> stored XSS on our origin).
ALLOWED_MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".mp4", ".webm"}
MAX_MEDIA_SIZE_MB = int(os.getenv("CMS_MAX_MEDIA_SIZE_MB", 20))

# Strip unsafe HTML from post content on write. Leave on unless content is rendered as plain text.
SANITIZE_HTML = os.getenv("CMS_SANITIZE_HTML", "true").lower() not in ("0", "false", "no")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_MEDIA_LIMIT = 50
MAX_MEDIA_LIMIT = 200

# Ensure the upload directory exists at import time (mirrors app/product/config style)
Path(CMS_MEDIA_DIR).mkdir(parents=True, exist_ok=True)
