from fastapi import APIRouter
from app.utils.adb_client import adb_manager

router = APIRouter()

@router.get("")
def health_check():
    """Health check endpoint to verify the server is running."""
    adb_status = "connected" if adb_manager is not None else "not connected"
    return {"status": "ok", "message": f"Server is running, ADB is {adb_status}"}
