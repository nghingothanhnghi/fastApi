# app/cms/routes/__init__.py
# Aggregates every CMS sub-router into one, so main.py only needs one include_router() call.
from fastapi import APIRouter

from app.cms.routes.category_router import router as category_router
from app.cms.routes.tag_router import router as tag_router
from app.cms.routes.media_router import router as media_router
from app.cms.routes.post_router import router as post_router

cms_router = APIRouter()
cms_router.include_router(category_router)
cms_router.include_router(tag_router)
cms_router.include_router(media_router)
cms_router.include_router(post_router)
