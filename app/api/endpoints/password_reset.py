# app/api/endpoints/password_reset.py

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.user import user as crud_user
from app.utils.email import send_reset_code_email
from app.user.schemas.password_reset import PasswordResetRequest, PasswordResetVerify, PasswordResetConfirm
from app.utils.security import hash_password
import random

router = APIRouter(prefix="/password", tags=["Password Reset"])

@router.post("/forgot")
async def request_reset_code(
    data: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    user = crud_user.get_user_by_email(db, data.email)
    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    code = f"{random.randint(100000, 999999)}"
    crud_user.save_reset_code(db, data.email, code)

    print(f"[DEBUG] Password reset code for {data.email}: {code}") 

    background_tasks.add_task(send_reset_code_email, data.email, code)
    return {"msg": "Reset code sent"}


@router.post("/verify-code")
def verify_code(data: PasswordResetVerify, db: Session = Depends(get_db)):
    if not crud_user.verify_reset_code(db, data.email, data.code):
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    return {"msg": "Code verified"}


@router.post("/reset")
def reset_password(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    user = crud_user.get_user_by_email(db, data.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(data.new_password)
    crud_user.delete_reset_codes(db, data.email)
    db.commit()
    return {"msg": "Password reset successful"}

