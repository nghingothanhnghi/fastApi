# app/billiard/services/device_service.py
# Read-side helpers for the central controller. Writes go through event_service.
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billiard.models import (
    BilliardDevice, BilliardTable, GameStatus, SessionStatus, TableGame, TableSession,
)
from app.billiard.schemas.device import ControllerState, TableStateOut
from app.billiard.utils.billing import as_utc
from app.user.models.user import User


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    return as_utc(dt) if dt else None   # SQLite returns naive datetimes


class DeviceService:

    @staticmethod
    def build_state(db: Session, device: BilliardDevice) -> ControllerState:
        """Server view of every table of the device's tenant. The ESP32 calls this
        after a reboot or reconnect and reconciles (scores: device wins)."""
        tables = db.execute(
            select(BilliardTable)
            .where(BilliardTable.client_id == device.client_id, BilliardTable.is_active.is_(True))
            .order_by(BilliardTable.name)
        ).scalars().all()
        ids = [t.id for t in tables]

        sessions = {}
        games = {}
        if ids:
            sessions = {
                s.table_id: s for s in db.execute(
                    select(TableSession).where(
                        TableSession.table_id.in_(ids), TableSession.status == SessionStatus.ACTIVE
                    )
                ).scalars()
            }
            games = {
                g.session_id: g for g in db.execute(
                    select(TableGame).where(
                        TableGame.session_id.in_([s.id for s in sessions.values()] or [0]),
                        TableGame.status == GameStatus.ACTIVE,
                    )
                ).scalars()
            }

        out = []
        for t in tables:
            s = sessions.get(t.id)
            g = games.get(s.id) if s else None
            out.append(TableStateOut(
                table_id=t.id, name=t.name, status=t.status,
                session_id=s.id if s else None,
                session_start_time=_utc(s.start_time) if s else None,
                session_ends_at=_utc(s.ends_at) if s else None,
                game_id=g.id if g else None,
                game_number=g.game_number if g else None,
                player_a_score=g.player_a_score if g else None,
                player_b_score=g.player_b_score if g else None,
            ))

        return ControllerState(
            device_id=device.device_id,
            server_time=datetime.now(timezone.utc),
            server_state_version=device.last_applied_seq,
            tables=out,
        )

    @staticmethod
    def list_devices(db: Session, user: User) -> list[BilliardDevice]:
        stmt = select(BilliardDevice).order_by(BilliardDevice.device_id)
        if not user.is_super_admin():
            stmt = stmt.where(BilliardDevice.client_id == user.client_id)
        return list(db.execute(stmt).scalars().all())


device_service = DeviceService()