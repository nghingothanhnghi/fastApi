# app/middleware/error_handler.py
# Middleware to handle exceptions and log them

from fastapi import Request
from fastapi.responses import JSONResponse
import logging
import traceback

logger = logging.getLogger(__name__)

async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Exception occurred: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"detail": str(e)},
        )
