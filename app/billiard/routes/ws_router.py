# app/billiard/routes/ws_router.py  (WebSocket only; see services/realtime.py for the messages)
# WS /ws/billiard?token=<JWT>[&client_id=<club>]
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from starlette.concurrency import run_in_threadpool
from starlette.status import WS_1008_POLICY_VIOLATION

from app.billiard import config
from app.billiard.services.realtime import get_realtime
from app.database import SessionLocal
from app.user import user as crud_user
from app.user.utils.token import ALGORITHM, SECRET_KEY

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Billiard Realtime"])


def _resolve_room(token: Optional[str], requested_club: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """(club, None) when the user may listen, else (None, reason). Same token rules as get_current_user."""
    if not token:
        return None, "Missing token"
    try:
        username = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get("sub")
    except JWTError:
        return None, "Invalid token"
    if not username:
        return None, "Invalid token"
    db = SessionLocal()                               # short-lived: a socket must not hold a connection
    try:
        user = crud_user.get_user_by_username(db, username)
        if not user or not user.is_active:
            return None, "Invalid token"
        if user.is_super_admin():                     # a super admin picks the club (or uses its own)
            club = requested_club or user.client_id
            return (club, None) if club else (None, "client_id is required for a super admin")
        if not user.client_id:
            return None, "User has no club"
        if requested_club and requested_club != user.client_id:
            return None, "Not allowed to listen to another club"
        return user.client_id, None
    finally:
        db.close()


@router.websocket("/ws/billiard")
async def billiard_updates(
    websocket: WebSocket, token: Optional[str] = Query(None), client_id: Optional[str] = Query(None),
):
    """Updates of the user's club: ids only, the POS refetches. Polling GET /tables/active keeps working."""
    await websocket.accept()                          # accept first so the browser can read the close reason
    club, reason = await run_in_threadpool(_resolve_room, token, client_id)
    if club is None:
        await websocket.close(code=WS_1008_POLICY_VIOLATION, reason=reason or "Not allowed")
        return

    realtime = get_realtime()
    connection = await realtime.connect(club, websocket)

    async def keep_alive() -> None:
        while True:
            await asyncio.sleep(config.WS_PING_SECONDS)
            await connection.send({"type": "ping"})

    pinger: Optional[asyncio.Task] = None
    try:
        await connection.send({"type": "ready", "client_id": club, "ping_seconds": config.WS_PING_SECONDS})
        pinger = asyncio.create_task(keep_alive())
        async for _ in websocket.iter_text():         # client messages (pong) are ignored
            pass
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("Billiard WebSocket ended", exc_info=True)
    finally:
        if pinger:
            pinger.cancel()
        realtime.disconnect(club, connection)
