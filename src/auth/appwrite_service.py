"""
Appwrite Authentication Service.
Handles Appwrite session verification, user registration, login, logout, and token validation.
Includes deterministic local cryptographic session verification when external Appwrite credentials
are pending or for local testing environments.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional
import httpx

import src.config  # Guarantees .env is loaded
from src.db.repositories import UserRepository, UserModel

logger = logging.getLogger(__name__)


def get_auth_secret() -> str:
    return os.getenv("AUTH_SECRET_KEY", "cruvels-legal-ai-secure-jwt-key-2026-production")


class AppwriteAuthService:
    """Central identity and session verification manager."""

    def __init__(self):
        self.user_repo = UserRepository()

    @property
    def endpoint(self) -> str:
        return os.getenv("APPWRITE_ENDPOINT", "").rstrip("/")

    @property
    def project_id(self) -> str:
        return os.getenv("APPWRITE_PROJECT_ID", "").strip()

    @property
    def api_key(self) -> str:
        return os.getenv("APPWRITE_API_KEY", "").strip()

    def is_configured(self) -> bool:
        return bool(self.endpoint and self.project_id)

    # ---------------------------------------------------------
    # Appwrite Remote Session Verification
    # ---------------------------------------------------------
    def _verify_appwrite_remote_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """Verifies session directly with Appwrite REST API."""
        if not self.is_configured():
            return None

        headers = {
            "X-Appwrite-Project": self.project_id,
        }
        # Support both JWT and session tokens
        if session_token.startswith("jwt:"):
            headers["X-Appwrite-JWT"] = session_token[4:]
        else:
            headers["X-Appwrite-Session"] = session_token

        try:
            with httpx.Client(timeout=5.0) as client:
                res = client.get(f"{self.endpoint}/account", headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return {
                        "auth_user_id": data.get("$id"),
                        "email": data.get("email"),
                        "name": data.get("name", ""),
                        "provider": "appwrite",
                    }
                else:
                    logger.debug("Appwrite session check returned HTTP %d: %s", res.status_code, res.text)
        except Exception as e:
            logger.warning("Appwrite remote connection failed: %s", e)
        return None

    # ---------------------------------------------------------
    # Cryptographic Local Session Generation & Verification
    # ---------------------------------------------------------
    def create_local_session_token(self, user: UserModel, expires_in_sec: int = 86400 * 7) -> str:
        """Issues an HMAC-SHA256 authenticated session token."""
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": user.id,
            "auth_user_id": user.auth_user_id,
            "email": user.email,
            "exp": int(time.time()) + expires_in_sec,
            "iat": int(time.time()),
        }
        h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        sig = hmac.new(get_auth_secret().encode(), f"{h_b64}.{p_b64}".encode(), hashlib.sha256).digest()
        s_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
        return f"{h_b64}.{p_b64}.{s_b64}"

    def verify_local_session_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verifies cryptographic signature and expiration of local session token."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            h_b64, p_b64, s_b64 = parts
            expected_sig = hmac.new(get_auth_secret().encode(), f"{h_b64}.{p_b64}".encode(), hashlib.sha256).digest()
            actual_sig = base64.urlsafe_b64decode(s_b64 + "==")
            if not hmac.compare_digest(expected_sig, actual_sig):
                return None

            payload_bytes = base64.urlsafe_b64decode(p_b64 + "==")
            payload = json.loads(payload_bytes)
            if payload.get("exp", 0) < int(time.time()):
                logger.debug("Session token expired.")
                return None
            return payload
        except Exception as e:
            logger.debug("Token verification error: %s", e)
            return None

    # ---------------------------------------------------------
    # Core Public Interface
    # ---------------------------------------------------------
    def verify_session(self, token: str) -> Optional[UserModel]:
        """
        Independently verifies session token (Appwrite or Local).
        Returns the resolved, authenticated UserModel from database.
        Never trusts client-supplied user ID!
        """
        if not token:
            return None

        clean_token = token.replace("Bearer ", "").strip()

        # 1. Try Appwrite remote verification if configured
        if self.is_configured():
            remote_info = self._verify_appwrite_remote_session(clean_token)
            if remote_info:
                return self.user_repo.get_or_create_user(
                    auth_user_id=remote_info["auth_user_id"],
                    email=remote_info["email"],
                    name=remote_info.get("name"),
                    auth_provider="appwrite",
                )

        # 2. Try Cryptographic local token verification
        payload = self.verify_local_session_token(clean_token)
        if payload:
            user = self.user_repo.get_by_id(payload["sub"])
            if user and user.account_status == "active":
                return user

        return None

    def register_user(
        self,
        email: str,
        password: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Registers a new user and returns user model + session token."""
        clean_email = email.strip().lower()
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters long")

        existing = self.user_repo.get_by_email(clean_email)
        if existing:
            raise ValueError("An account with this email already exists")

        auth_user_id = f"appwrite_{secrets.token_hex(12)}"

        # If Appwrite server API is configured, create in Appwrite as well
        if self.is_configured() and self.api_key:
            try:
                with httpx.Client(timeout=5.0) as client:
                    res = client.post(
                        f"{self.endpoint}/users",
                        headers={
                            "X-Appwrite-Project": self.project_id,
                            "X-Appwrite-Key": self.api_key,
                            "Content-Type": "application/json",
                        },
                        json={
                            "userId": "unique()",
                            "email": clean_email,
                            "password": password,
                            "name": f"{first_name or ''} {last_name or ''}".strip() or clean_email,
                        },
                    )
                    if res.status_code in (200, 201):
                        auth_user_id = res.json().get("$id", auth_user_id)
            except Exception as e:
                logger.warning("Remote Appwrite user registration notice: %s", e)

        salt = secrets.token_hex(16)
        pw_hash = f"pbkdf2_sha256${salt}${hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()}"

        user = self.user_repo.create_user(
            auth_user_id=auth_user_id,
            email=clean_email,
            first_name=first_name,
            last_name=last_name,
            auth_provider="appwrite",
            password_hash=pw_hash,
        )

        session_token = self.create_local_session_token(user)
        return {
            "user": user.model_dump(),
            "session_token": session_token,
        }

    def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticates user and returns session token."""
        clean_email = email.strip().lower()
        user = self.user_repo.get_by_email(clean_email)
        if not user:
            raise ValueError("Invalid email or password")

        pw_hash = self.user_repo.get_password_hash(clean_email)
        if not pw_hash or not self._verify_password(password, pw_hash):
            raise ValueError("Invalid email or password")

        session_token = self.create_local_session_token(user)
        return {
            "user": user.model_dump(),
            "session_token": session_token,
        }

    def reset_password(self, email: str, new_password: str) -> bool:
        clean_email = email.strip().lower()
        user = self.user_repo.get_by_email(clean_email)
        if not user:
            return False
        if len(new_password) < 6:
            raise ValueError("Password must be at least 6 characters long")

        salt = secrets.token_hex(16)
        pw_hash = f"pbkdf2_sha256${salt}${hashlib.pbkdf2_hmac('sha256', new_password.encode(), salt.encode(), 100000).hex()}"
        self.user_repo.update_password_hash(user.id, pw_hash)
        return True

    def _verify_password(self, password: str, stored_hash: str) -> bool:
        try:
            parts = stored_hash.split("$")
            if len(parts) != 3 or parts[0] != "pbkdf2_sha256":
                return False
            salt = parts[1]
            target_hex = parts[2]
            computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
            return hmac.compare_digest(computed, target_hex)
        except Exception:
            return False


_AUTH_SERVICE = AppwriteAuthService()


def get_auth_service() -> AppwriteAuthService:
    global _AUTH_SERVICE
    return _AUTH_SERVICE
