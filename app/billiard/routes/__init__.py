# app/billiard/routes/__init__.py
from fastapi import APIRouter

from app.billiard.routes.table_router import router as table_router
from app.billiard.routes.game_router import router as game_router
from app.billiard.routes.session_router import router as session_router
from app.billiard.routes.report_router import router as report_router

billiard_router = APIRouter()
billiard_router.include_router(table_router)
billiard_router.include_router(game_router)
billiard_router.include_router(session_router)
billiard_router.include_router(report_router)