# app/auth_provider/routes/oauth_router.py
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth_provider.providers.registry import oauth_provider_registry
from app.auth_provider.utils.oauth_state import create_state_token, verify_state_token
from app.auth_provider.services.oauth_service import oauth_service
from app.core.config import BACKEND_URL, FRONTEND_URL

router = APIRouter(prefix="/auth", tags=["OAuth"])


def _redirect_uri(provider: str) -> str:
    return f"{BACKEND_URL}/auth/{provider}/callback"


@router.get("/{provider}/login")
def oauth_login(provider: str, redirect_after: str | None = Query(None)):
    try:
        oauth = oauth_provider_registry.get_provider(provider)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    state = create_state_token(redirect_after)
    url = oauth.get_authorization_url(state=state, redirect_uri=_redirect_uri(provider))
    return RedirectResponse(url)


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        oauth = oauth_provider_registry.get_provider(provider)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        state_payload = verify_state_token(state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    token_data = await oauth.exchange_code_for_token(code, redirect_uri=_redirect_uri(provider))
    user_info = await oauth.fetch_user_info(token_data)

    result = oauth_service.login_or_register(db, user_info, token_data)

    redirect_after = state_payload.get("redirect_after") or FRONTEND_URL
    # Hand the JWT to the frontend via a fragment so it never hits server logs
    return RedirectResponse(f"{redirect_after}#access_token={result['access_token']}&token_type=bearer")