"""
Authentication API Router: Registration, Login, Logout, Session Verification, and Password Management.
"""
from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from src.auth.appwrite_service import get_auth_service
from src.auth.dependencies import get_current_user
from src.db.repositories import UserModel, UserSettingsRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    new_password: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest):
    auth_service = get_auth_service()
    try:
        result = auth_service.register_user(
            email=str(req.email),
            password=req.password,
            first_name=req.first_name,
            last_name=req.last_name,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Registration error: %s", e)
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")


@router.post("/login")
def login(req: LoginRequest):
    auth_service = get_auth_service()
    try:
        result = auth_service.login_user(
            email=str(req.email),
            password=req.password,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("Login error: %s", e)
        raise HTTPException(status_code=500, detail="Authentication failed. Please try again.")


@router.post("/logout")
def logout(current_user: UserModel = Depends(get_current_user)):
    return {"status": "logged_out", "user_id": current_user.id}


@router.get("/me")
def get_me(current_user: UserModel = Depends(get_current_user)):
    settings_repo = UserSettingsRepository()
    settings = settings_repo.get_settings(current_user.id)
    return {
        "user": current_user.model_dump(),
        "settings": settings.model_dump(),
    }


@router.post("/password/forgot")
def forgot_password(req: ForgotPasswordRequest):
    # Security best practice: don't reveal if user exists
    return {
        "status": "sent",
        "message": f"Password reset instructions have been dispatched to {req.email} if an account exists.",
    }


@router.post("/password/reset")
def reset_password(req: ResetPasswordRequest):
    auth_service = get_auth_service()
    try:
        success = auth_service.reset_password(str(req.email), req.new_password)
        if not success:
            raise HTTPException(status_code=404, detail="Account not found.")
        return {"status": "success", "message": "Password reset successfully. You can now log in."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Password reset error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to reset password.")
