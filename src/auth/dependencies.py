"""
FastAPI Authentication Dependencies.
Derives user identity from the independently verified session token.
Never trusts client-supplied user IDs.
"""
from __future__ import annotations

import logging
from typing import Optional
from fastapi import Cookie, Header, HTTPException, Request

from src.auth.appwrite_service import get_auth_service
from src.db.repositories import UserModel

logger = logging.getLogger(__name__)


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    appwrite_session: Optional[str] = Cookie(None),
) -> UserModel:
    """
    Enforces server-side authentication.
    Resolves session token from Authorization header or cookie.
    Raises HTTP 401 if missing, invalid, or expired.
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif authorization:
        token = authorization.strip()
    elif appwrite_session:
        token = appwrite_session.strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in to access this resource.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = get_auth_service()
    user = auth_service.verify_session(token)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Attach verified user to request state
    request.state.user = user
    return user


def get_optional_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    appwrite_session: Optional[str] = Cookie(None),
) -> Optional[UserModel]:
    """Allows anonymous or unauthenticated requests while resolving user when present."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif authorization:
        token = authorization.strip()
    elif appwrite_session:
        token = appwrite_session.strip()

    if not token:
        return None

    auth_service = get_auth_service()
    user = auth_service.verify_session(token)
    if user:
        request.state.user = user
    return user
