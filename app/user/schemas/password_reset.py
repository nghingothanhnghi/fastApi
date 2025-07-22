# app/user/schemas/password_reset.py
# This module defines the schemas for password reset operations.
from pydantic import BaseModel, EmailStr, constr
from typing import Annotated

CodeStr = Annotated[str, constr(min_length=6, max_length=6)]
class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetVerify(BaseModel):
    email: EmailStr
    code: CodeStr

class PasswordResetConfirm(BaseModel):
    email: EmailStr
    new_password: str
