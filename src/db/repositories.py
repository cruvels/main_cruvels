"""
Database repository implementations for Users, Settings, Conversations, Messages, Memories, and Audit logs.
Strictly enforces ownership filtering on every read/write operation.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.db.connection import get_db_connection

logger = logging.getLogger(__name__)


# Pydantic domain models
class UserModel(BaseModel):
    id: str
    auth_provider: str = "appwrite"
    auth_user_id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_image: Optional[str] = None
    account_status: str = "active"
    created_at: str
    updated_at: str


class UserSettingsModel(BaseModel):
    user_id: str
    auto_memory_enabled: bool = True
    preferred_style: str = "Formal / Precise"
    created_at: str
    updated_at: str


class ConversationModel(BaseModel):
    id: str
    user_id: str
    title: str
    status: str = "active"
    created_at: str
    updated_at: str


class MessageModel(BaseModel):
    id: str
    conversation_id: str
    user_id: str
    role: str
    content: str
    message_metadata: Optional[Dict[str, Any]] = None
    created_at: str


class UserMemoryModel(BaseModel):
    id: str
    user_id: str
    memory_type: str  # PROFILE, PREFERENCE, WRITING_STYLE, WORKFLOW, CONTEXT
    memory_content: str
    source_type: str = "conversation"
    source_id: Optional[str] = None
    confidence: float = 1.0
    importance: float = 0.5
    status: str = "active"
    created_at: str
    updated_at: str


class AuditLogModel(BaseModel):
    id: str
    user_id: str
    operation: str
    resource_type: str
    resource_id: Optional[str] = None
    result: str = "success"
    details: Optional[str] = None
    timestamp: str


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


class UserRepository:
    """Manages user identities mapped to Appwrite auth identity."""

    def get_by_id(self, user_id: str) -> Optional[UserModel]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_model(row)

    def get_by_auth_user_id(self, auth_user_id: str) -> Optional[UserModel]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE auth_user_id = ?", (auth_user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_model(row)

    def get_by_email(self, email: str) -> Optional[UserModel]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_model(row)

    def get_password_hash(self, email: str) -> Optional[str]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),))
            row = cursor.fetchone()
            if not row:
                return None
            return row["password_hash"] if isinstance(row, dict) or hasattr(row, "__getitem__") else None

    def create_user(
        self,
        auth_user_id: str,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        auth_provider: str = "appwrite",
        profile_image: Optional[str] = None,
        password_hash: Optional[str] = None,
    ) -> UserModel:
        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (
                    id, auth_provider, auth_user_id, email,
                    first_name, last_name, profile_image,
                    account_status, password_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    auth_provider,
                    auth_user_id,
                    email.strip().lower(),
                    first_name,
                    last_name,
                    profile_image,
                    "active",
                    password_hash,
                    now,
                    now,
                ),
            )
            # Create default settings
            cursor.execute(
                """
                INSERT INTO user_settings (user_id, auto_memory_enabled, preferred_style, created_at, updated_at)
                VALUES (?, 1, 'Formal / Precise', ?, ?)
                """,
                (user_id, now, now),
            )
            conn.commit()

        AuditRepository().log(
            user_id=user_id,
            operation="USER_REGISTER",
            resource_type="user",
            resource_id=user_id,
            result="success",
        )
        return self.get_by_id(user_id)

    def get_or_create_user(
        self,
        auth_user_id: str,
        email: str,
        name: Optional[str] = None,
        auth_provider: str = "appwrite",
    ) -> UserModel:
        """Idempotent user resolution."""
        existing = self.get_by_auth_user_id(auth_user_id)
        if existing:
            return existing

        by_email = self.get_by_email(email)
        if by_email:
            # Update auth_user_id if mapped
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET auth_user_id = ?, updated_at = ? WHERE id = ?",
                    (auth_user_id, _now_iso(), by_email.id),
                )
                conn.commit()
            return self.get_by_id(by_email.id)

        first_name, last_name = None, None
        if name:
            parts = name.strip().split(" ", 1)
            first_name = parts[0]
            if len(parts) > 1:
                last_name = parts[1]

        return self.create_user(
            auth_user_id=auth_user_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            auth_provider=auth_provider,
        )

    def update_profile(
        self,
        user_id: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        profile_image: Optional[str] = None,
    ) -> Optional[UserModel]:
        now = _now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE users
                SET first_name = COALESCE(?, first_name),
                    last_name = COALESCE(?, last_name),
                    profile_image = COALESCE(?, profile_image),
                    updated_at = ?
                WHERE id = ?
                """,
                (first_name, last_name, profile_image, now, user_id),
            )
            conn.commit()

        AuditRepository().log(
            user_id=user_id,
            operation="PROFILE_UPDATE",
            resource_type="user",
            resource_id=user_id,
            result="success",
        )
        return self.get_by_id(user_id)

    def update_password_hash(self, user_id: str, password_hash: str) -> None:
        now = _now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?", (password_hash, now, user_id))
            conn.commit()

    def delete_user(self, user_id: str) -> bool:
        """Deletes user and cascades to settings, conversations, memories, documents."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()

        AuditRepository().log(
            user_id=user_id,
            operation="ACCOUNT_DELETE",
            resource_type="user",
            resource_id=user_id,
            result="success",
        )
        return True

    def _row_to_model(self, row: Any) -> UserModel:
        return UserModel(
            id=str(row["id"]),
            auth_provider=str(row["auth_provider"]),
            auth_user_id=str(row["auth_user_id"]),
            email=str(row["email"]),
            first_name=row["first_name"],
            last_name=row["last_name"],
            profile_image=row["profile_image"],
            account_status=str(row["account_status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )


class UserSettingsRepository:
    """Manages user-specific preferences and AI memory configuration."""

    def get_settings(self, user_id: str) -> UserSettingsModel:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                now = _now_iso()
                cursor.execute(
                    """
                    INSERT INTO user_settings (user_id, auto_memory_enabled, preferred_style, created_at, updated_at)
                    VALUES (?, 1, 'Formal / Precise', ?, ?)
                    """,
                    (user_id, now, now),
                )
                conn.commit()
                return UserSettingsModel(
                    user_id=user_id,
                    auto_memory_enabled=True,
                    preferred_style="Formal / Precise",
                    created_at=now,
                    updated_at=now,
                )
            return UserSettingsModel(
                user_id=str(row["user_id"]),
                auto_memory_enabled=bool(row["auto_memory_enabled"]),
                preferred_style=str(row["preferred_style"] or "Formal / Precise"),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )

    def update_settings(
        self,
        user_id: str,
        auto_memory_enabled: Optional[bool] = None,
        preferred_style: Optional[str] = None,
    ) -> UserSettingsModel:
        curr = self.get_settings(user_id)
        new_auto = curr.auto_memory_enabled if auto_memory_enabled is None else auto_memory_enabled
        new_style = curr.preferred_style if preferred_style is None else preferred_style
        now = _now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE user_settings
                SET auto_memory_enabled = ?, preferred_style = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (1 if new_auto else 0, new_style, now, user_id),
            )
            conn.commit()

        AuditRepository().log(
            user_id=user_id,
            operation="MEMORY_SETTINGS_UPDATE",
            resource_type="settings",
            resource_id=user_id,
            result="success",
        )
        return self.get_settings(user_id)


class ConversationRepository:
    """Manages individual conversation history with strict user isolation."""

    def create_conversation(self, user_id: str, title: str = "New Conversation") -> ConversationModel:
        conv_id = f"cnv_{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversations (id, user_id, title, status, created_at, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?)
                """,
                (conv_id, user_id, title.strip() or "New Conversation", now, now),
            )
            conn.commit()

        AuditRepository().log(
            user_id=user_id,
            operation="CONVERSATION_CREATE",
            resource_type="conversation",
            resource_id=conv_id,
            result="success",
        )
        return ConversationModel(
            id=conv_id,
            user_id=user_id,
            title=title.strip() or "New Conversation",
            status="active",
            created_at=now,
            updated_at=now,
        )

    def list_conversations(self, user_id: str, limit: int = 50) -> List[ConversationModel]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM conversations
                WHERE user_id = ? AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = cursor.fetchall()
            return [
                ConversationModel(
                    id=str(r["id"]),
                    user_id=str(r["user_id"]),
                    title=str(r["title"]),
                    status=str(r["status"]),
                    created_at=str(r["created_at"]),
                    updated_at=str(r["updated_at"]),
                )
                for r in rows
            ]

    def get_conversation(self, conversation_id: str, user_id: str) -> Optional[ConversationModel]:
        """Strictly verifies ownership: User A cannot read User B's conversation."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            r = cursor.fetchone()
            if not r:
                return None
            return ConversationModel(
                id=str(r["id"]),
                user_id=str(r["user_id"]),
                title=str(r["title"]),
                status=str(r["status"]),
                created_at=str(r["created_at"]),
                updated_at=str(r["updated_at"]),
            )

    def update_conversation(
        self,
        conversation_id: str,
        user_id: str,
        title: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[ConversationModel]:
        conv = self.get_conversation(conversation_id, user_id)
        if not conv:
            return None
        now = _now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE conversations
                SET title = COALESCE(?, title),
                    status = COALESCE(?, status),
                    updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (title, status, now, conversation_id, user_id),
            )
            conn.commit()
        return self.get_conversation(conversation_id, user_id)

    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        conv = self.get_conversation(conversation_id, user_id)
        if not conv:
            return False
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversation_messages WHERE conversation_id = ?", (conversation_id,))
            cursor.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id))
            conn.commit()

        AuditRepository().log(
            user_id=user_id,
            operation="CONVERSATION_DELETE",
            resource_type="conversation",
            resource_id=conversation_id,
            result="success",
        )
        return True

    def add_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        message_metadata: Optional[Dict[str, Any]] = None,
    ) -> MessageModel:
        # Verify conversation ownership
        conv = self.get_conversation(conversation_id, user_id)
        if not conv:
            raise PermissionError("Access denied: conversation does not belong to user")

        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        meta_str = json.dumps(message_metadata) if message_metadata else None

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversation_messages (id, conversation_id, user_id, role, content, message_metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (msg_id, conversation_id, user_id, role, content, meta_str, now),
            )
            # Bump conversation updated_at
            cursor.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
            conn.commit()

        return MessageModel(
            id=msg_id,
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            message_metadata=message_metadata,
            created_at=now,
        )

    def list_messages(self, conversation_id: str, user_id: str, limit: int = 100) -> List[MessageModel]:
        # Verify ownership first!
        conv = self.get_conversation(conversation_id, user_id)
        if not conv:
            return []

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM conversation_messages
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (conversation_id, user_id, limit),
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                meta = None
                if r["message_metadata"]:
                    try:
                        meta = json.loads(r["message_metadata"])
                    except Exception:
                        pass
                results.append(
                    MessageModel(
                        id=str(r["id"]),
                        conversation_id=str(r["conversation_id"]),
                        user_id=str(r["user_id"]),
                        role=str(r["role"]),
                        content=str(r["content"]),
                        message_metadata=meta,
                        created_at=str(r["created_at"]),
                    )
                )
            return results


class UserMemoryRepository:
    """Manages individual long-term user memories with strict ownership and deduplication."""

    def create_memory(
        self,
        user_id: str,
        memory_type: str,
        memory_content: str,
        source_type: str = "conversation",
        source_id: Optional[str] = None,
        confidence: float = 1.0,
        importance: float = 0.5,
    ) -> UserMemoryModel:
        mem_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        valid_types = {"PROFILE", "PREFERENCE", "WRITING_STYLE", "WORKFLOW", "CONTEXT"}
        clean_type = memory_type.upper() if memory_type.upper() in valid_types else "CONTEXT"

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_memories (
                    id, user_id, memory_type, memory_content, source_type,
                    source_id, confidence, importance, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    mem_id,
                    user_id,
                    clean_type,
                    memory_content.strip(),
                    source_type,
                    source_id,
                    confidence,
                    importance,
                    now,
                    now,
                ),
            )
            conn.commit()

        AuditRepository().log(
            user_id=user_id,
            operation="MEMORY_CREATE",
            resource_type="memory",
            resource_id=mem_id,
            result="success",
        )
        return self.get_memory(mem_id, user_id)

    def list_memories(
        self,
        user_id: str,
        memory_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[UserMemoryModel]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if memory_type:
                cursor.execute(
                    """
                    SELECT * FROM user_memories
                    WHERE user_id = ? AND memory_type = ? AND status = 'active'
                    ORDER BY importance DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (user_id, memory_type.upper(), limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM user_memories
                    WHERE user_id = ? AND status = 'active'
                    ORDER BY importance DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                )
            rows = cursor.fetchall()
            return [self._row_to_model(r) for r in rows]

    def get_memory(self, memory_id: str, user_id: str) -> Optional[UserMemoryModel]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            )
            r = cursor.fetchone()
            if not r:
                return None
            return self._row_to_model(r)

    def update_memory(
        self,
        memory_id: str,
        user_id: str,
        memory_content: Optional[str] = None,
        importance: Optional[float] = None,
        status: Optional[str] = None,
    ) -> Optional[UserMemoryModel]:
        mem = self.get_memory(memory_id, user_id)
        if not mem:
            return None
        now = _now_iso()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE user_memories
                SET memory_content = COALESCE(?, memory_content),
                    importance = COALESCE(?, importance),
                    status = COALESCE(?, status),
                    updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (memory_content, importance, status, now, memory_id, user_id),
            )
            conn.commit()

        AuditRepository().log(
            user_id=user_id,
            operation="MEMORY_UPDATE",
            resource_type="memory",
            resource_id=memory_id,
            result="success",
        )
        return self.get_memory(memory_id, user_id)

    def delete_memory(self, memory_id: str, user_id: str) -> bool:
        mem = self.get_memory(memory_id, user_id)
        if not mem:
            return False
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
            conn.commit()

        AuditRepository().log(
            user_id=user_id,
            operation="MEMORY_DELETE",
            resource_type="memory",
            resource_id=memory_id,
            result="success",
        )
        return True

    def clear_all_memories(self, user_id: str) -> int:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_memories WHERE user_id = ?", (user_id,))
            count = cursor.rowcount
            conn.commit()

        AuditRepository().log(
            user_id=user_id,
            operation="MEMORY_CLEAR_ALL",
            resource_type="memory",
            resource_id=None,
            result="success",
            details=f"Cleared {count} memories",
        )
        return count

    def find_equivalent_memory(self, user_id: str, memory_type: str, content: str) -> Optional[UserMemoryModel]:
        """Finds existing memory with identical or near-identical content for controlled updates."""
        all_mems = self.list_memories(user_id, memory_type=memory_type)
        clean = content.strip().lower()
        for m in all_mems:
            if m.memory_content.strip().lower() == clean:
                return m
            # Check high substring containment
            if clean in m.memory_content.strip().lower() or m.memory_content.strip().lower() in clean:
                return m
        return None

    def _row_to_model(self, r: Any) -> UserMemoryModel:
        return UserMemoryModel(
            id=str(r["id"]),
            user_id=str(r["user_id"]),
            memory_type=str(r["memory_type"]),
            memory_content=str(r["memory_content"]),
            source_type=str(r["source_type"] or "conversation"),
            source_id=r["source_id"],
            confidence=float(r["confidence"] or 1.0),
            importance=float(r["importance"] or 0.5),
            status=str(r["status"] or "active"),
            created_at=str(r["created_at"]),
            updated_at=str(r["updated_at"]),
        )


class AuditRepository:
    """Records audit logs for compliance, security, and traceability without logging secrets."""

    def log(
        self,
        user_id: str,
        operation: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        result: str = "success",
        details: Optional[str] = None,
    ) -> None:
        log_id = f"aud_{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO audit_logs (id, user_id, operation, resource_type, resource_id, result, details, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (log_id, user_id, operation, resource_type, resource_id, result, details, now),
                )
                conn.commit()
        except Exception as e:
            logger.warning("Failed to record audit log: %s", e)
