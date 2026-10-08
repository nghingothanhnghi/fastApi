# app/billiard/routes/game_router.py  (HTTP only; rules live in game_service)
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.user.models.user import User
from app.user.utils.token import get_current_user
from app.billiard.schemas.game import GameResponse, NewGameResponse, ScoreChangeRequest
from app.billiard.services.game_service import game_service

router = APIRouter(tags=["Billiard Games"])


@router.get("/sessions/{session_id}/games", response_model=list[GameResponse])
def list_games(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return game_service.list_games(db, session_id, current_user)


@router.post("/sessions/{session_id}/games", response_model=GameResponse, status_code=201)
def start_game(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    game = game_service.start_game(db, session_id, current_user)
    db.commit()
    db.refresh(game)
    return game


@router.post("/games/{game_id}/score", response_model=GameResponse)
def change_score(
    game_id: int, request: ScoreChangeRequest,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    game = game_service.change_score(db, game_id, request.player, request.delta, current_user)
    db.commit()
    db.refresh(game)
    return game


@router.post("/games/{game_id}/reset", response_model=GameResponse)
def reset_score(game_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    game = game_service.reset_score(db, game_id, current_user)
    db.commit()
    db.refresh(game)
    return game


@router.post("/games/{game_id}/new", response_model=NewGameResponse)
def new_game(game_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    finished, started = game_service.new_game(db, game_id, current_user)
    db.commit()
    db.refresh(finished)
    db.refresh(started)
    return NewGameResponse(finished=finished, started=started)


@router.post("/games/{game_id}/finish", response_model=GameResponse)
def finish_game(game_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    game = game_service.finish_game(db, game_id, current_user)
    db.commit()
    db.refresh(game)
    return game

