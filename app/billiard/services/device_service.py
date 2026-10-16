# app/billiard/services/device_service.py
# Read-side helpers for the central controller. Writes go through event_service.
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billiard.models import (
    BilliardDevice, BilliardTable, GameStatus, SessionStatus, TableGame, TableSession,
)
from app.billiard.schemas.device import ControllerState, TableStateOut
from app.billiard.utils.billing import as_utc
from app.user.models.user import User

import secrets
from datetime import timedelta
from fastapi import HTTPException
from app.billiard.services.device_auth import hash_api_key
from app.hydro_system.models.device import HydroDevice

OFFLINE_AFTER = timedelta(seconds=90)

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

    # ── NEW ──────────────────────────────────────────────────────────────
    @staticmethod
    def effective_status(d: BilliardDevice) -> DeviceStatus:
        """Stored status goes stale (nothing flips it to OFFLINE), so derive it from last_seen."""
        if d.last_seen is None or datetime.now(timezone.utc) - as_utc(d.last_seen) > OFFLINE_AFTER:
            return DeviceStatus.OFFLINE
        return d.status

    @staticmethod
    def _can_see_hydro(hd: HydroDevice, user: User) -> bool:
        return user.is_super_admin() or hd.user_id == user.id or (
            hd.client_id is not None and hd.client_id == user.client_id
        )

    @staticmethod
    def hydro_candidates(db: Session, user: User) -> list[dict]:
        taken = set(db.execute(select(BilliardDevice.device_id)).scalars())
        rows = db.query(HydroDevice).filter(HydroDevice.is_active.is_(True)).all()
        return [
            {"hydro_device_id": h.id, "device_id": h.device_id, "name": h.name, "location": h.location}
            for h in rows
            if DeviceService._can_see_hydro(h, user) and h.device_id not in taken
        ]

    @staticmethod
    def register(db: Session, data, user: User) -> tuple[BilliardDevice, str]:
        device_id, name = data.device_id, data.name
        if data.hydro_device_id is not None:
            hd = db.get(HydroDevice, data.hydro_device_id)
            if not hd or not DeviceService._can_see_hydro(hd, user):
                raise HTTPException(404, "Hydro device not found")
            device_id, name = device_id or hd.device_id, name or hd.name

        if db.execute(select(BilliardDevice.id).where(BilliardDevice.device_id == device_id)).first():
            raise HTTPException(409, f"Device '{device_id}' is already registered")

        key = secrets.token_urlsafe(32)          # returned once; only the hash is stored
        dev = BilliardDevice(
            client_id=user.client_id, device_id=device_id,
            name=name or device_id, api_key_hash=hash_api_key(key),
        )
        db.add(dev)
        db.flush()
        return dev, key

device_service = DeviceService()