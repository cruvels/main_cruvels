"""
Database connection and session manager.
Supports PostgreSQL (via psycopg2 / SQLAlchemy) and SQLite fallback for local development.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Any

from src.config import get_path

logger = logging.getLogger(__name__)

_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def get_database_url() -> str:
    global _DATABASE_URL
    return os.getenv("DATABASE_URL", _DATABASE_URL).strip()


def is_postgres() -> bool:
    url = get_database_url()
    return url.startswith("postgres://") or url.startswith("postgresql://")


def get_sqlite_path() -> Path:
    db_path = get_path("processed_data_dir") / "legal_kb.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


class DBConnectionWrapper:
    """Wrapper that provides a uniform cursor interface across SQLite and PostgreSQL."""

    def __init__(self, raw_conn: Any, is_pg: bool = False):
        self.raw_conn = raw_conn
        self.is_pg = is_pg

    def cursor(self):
        return self.raw_conn.cursor()

    def commit(self):
        self.raw_conn.commit()

    def rollback(self):
        self.raw_conn.rollback()

    def close(self):
        self.raw_conn.close()


@contextmanager
def get_db_connection() -> Generator[DBConnectionWrapper, None, None]:
    """Context manager for obtaining a database connection."""
    if is_postgres():
        import psycopg2
        from psycopg2.extras import RealDictCursor

        url = get_database_url()
        # Normalise postgres:// to postgresql:// if needed
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
        wrapper = DBConnectionWrapper(conn, is_pg=True)
        try:
            yield wrapper
            wrapper.commit()
        except Exception:
            wrapper.rollback()
            raise
        finally:
            wrapper.close()
    else:
        db_path = get_sqlite_path()
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        wrapper = DBConnectionWrapper(conn, is_pg=False)
        try:
            yield wrapper
            wrapper.commit()
        except Exception:
            wrapper.rollback()
            raise
        finally:
            wrapper.close()


def init_database() -> None:
    """Creates all required tables if they do not exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        is_pg = conn.is_pg

        # 1. Users Table
        id_type = "VARCHAR(64)" if is_pg else "TEXT"
        text_type = "TEXT"
        bool_type = "BOOLEAN" if is_pg else "INTEGER"
        ts_type = "TIMESTAMPTZ" if is_pg else "TEXT"
        now_val = "CURRENT_TIMESTAMP"

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                id {id_type} PRIMARY KEY,
                auth_provider VARCHAR(32) NOT NULL DEFAULT 'appwrite',
                auth_user_id VARCHAR(128) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                first_name VARCHAR(128),
                last_name VARCHAR(128),
                profile_image {text_type},
                account_status VARCHAR(32) NOT NULL DEFAULT 'active',
                password_hash VARCHAR(255),
                created_at {ts_type} NOT NULL DEFAULT {now_val},
                updated_at {ts_type} NOT NULL DEFAULT {now_val}
            )
        """)

        # 2. User Settings Table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id {id_type} PRIMARY KEY,
                auto_memory_enabled {bool_type} NOT NULL DEFAULT {'TRUE' if is_pg else '1'},
                preferred_style VARCHAR(64) DEFAULT 'Formal / Precise',
                created_at {ts_type} NOT NULL DEFAULT {now_val},
                updated_at {ts_type} NOT NULL DEFAULT {now_val},
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 3. Conversations Table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS conversations (
                id {id_type} PRIMARY KEY,
                user_id {id_type} NOT NULL,
                title VARCHAR(255) NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                created_at {ts_type} NOT NULL DEFAULT {now_val},
                updated_at {ts_type} NOT NULL DEFAULT {now_val},
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 4. Conversation Messages Table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id {id_type} PRIMARY KEY,
                conversation_id {id_type} NOT NULL,
                user_id {id_type} NOT NULL,
                role VARCHAR(32) NOT NULL,
                content {text_type} NOT NULL,
                message_metadata {text_type},
                created_at {ts_type} NOT NULL DEFAULT {now_val},
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 5. User Memories Table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS user_memories (
                id {id_type} PRIMARY KEY,
                user_id {id_type} NOT NULL,
                memory_type VARCHAR(64) NOT NULL,
                memory_content {text_type} NOT NULL,
                source_type VARCHAR(64) NOT NULL DEFAULT 'conversation',
                source_id VARCHAR(128),
                confidence REAL NOT NULL DEFAULT 1.0,
                importance REAL NOT NULL DEFAULT 0.5,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                created_at {ts_type} NOT NULL DEFAULT {now_val},
                updated_at {ts_type} NOT NULL DEFAULT {now_val},
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 6. Audit Logs Table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id {id_type} PRIMARY KEY,
                user_id {id_type} NOT NULL,
                operation VARCHAR(64) NOT NULL,
                resource_type VARCHAR(64) NOT NULL,
                resource_id VARCHAR(128),
                result VARCHAR(32) NOT NULL,
                details {text_type},
                timestamp {ts_type} NOT NULL DEFAULT {now_val}
            )
        """)

        # Existing knowledge & document tables: documents, sections, paragraphs, entities, concepts, claims, processing_jobs, knowledge_units
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS documents (
                document_id {id_type} PRIMARY KEY,
                user_id {id_type} NOT NULL,
                tenant_id VARCHAR(64) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                file_type VARCHAR(32) NOT NULL,
                file_size INTEGER NOT NULL,
                checksum VARCHAR(128) NOT NULL,
                document_type VARCHAR(64) NOT NULL,
                classification_confidence REAL DEFAULT 0.0,
                case_id VARCHAR(64),
                access_scope VARCHAR(32) DEFAULT 'private',
                status VARCHAR(32) NOT NULL,
                original_file_location {text_type} NOT NULL,
                error_message {text_type},
                created_at {ts_type} NOT NULL DEFAULT {now_val},
                updated_at {ts_type} NOT NULL DEFAULT {now_val}
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS document_sections (
                section_id {id_type} PRIMARY KEY,
                document_id {id_type} NOT NULL,
                parent_section_id VARCHAR(64),
                title VARCHAR(255) NOT NULL,
                level INTEGER DEFAULT 1,
                page_number INTEGER DEFAULT 1,
                order_index INTEGER DEFAULT 0,
                FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS document_paragraphs (
                paragraph_id {id_type} PRIMARY KEY,
                document_id {id_type} NOT NULL,
                section_id VARCHAR(64),
                page_number INTEGER DEFAULT 1,
                text {text_type} NOT NULL,
                order_index INTEGER DEFAULT 0,
                is_clause INTEGER DEFAULT 0,
                clause_number VARCHAR(64),
                FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS entities (
                entity_id {id_type} PRIMARY KEY,
                document_id {id_type} NOT NULL,
                entity_type VARCHAR(64) NOT NULL,
                name VARCHAR(255) NOT NULL,
                confidence REAL DEFAULT 1.0,
                context {text_type},
                FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS concepts (
                concept_id {id_type} PRIMARY KEY,
                document_id {id_type} NOT NULL,
                topic VARCHAR(128) NOT NULL,
                description {text_type},
                relevance_score REAL DEFAULT 1.0,
                FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS claims (
                claim_id {id_type} PRIMARY KEY,
                document_id {id_type} NOT NULL,
                section_id VARCHAR(64),
                claim_text {text_type} NOT NULL,
                claim_type VARCHAR(64) DEFAULT 'factual',
                confidence REAL DEFAULT 1.0,
                FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS processing_jobs (
                job_id {id_type} PRIMARY KEY,
                document_id {id_type} NOT NULL,
                user_id {id_type} NOT NULL,
                status VARCHAR(32) NOT NULL,
                stage VARCHAR(64) NOT NULL,
                progress REAL DEFAULT 0.0,
                error_message {text_type},
                created_at {ts_type} NOT NULL DEFAULT {now_val},
                updated_at {ts_type} NOT NULL DEFAULT {now_val}
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS knowledge_units (
                id {id_type} PRIMARY KEY,
                user_id {id_type} NOT NULL,
                tenant_id VARCHAR(64) NOT NULL,
                document_id {id_type} NOT NULL,
                case_id VARCHAR(64),
                chunk_id VARCHAR(128) NOT NULL,
                parent_chunk_id VARCHAR(128),
                document_type VARCHAR(64),
                section_type VARCHAR(64),
                section_title VARCHAR(255),
                legal_topic VARCHAR(128),
                text {text_type} NOT NULL,
                importance_score REAL DEFAULT 0.5,
                entities_json {text_type},
                concepts_json {text_type},
                claims_json {text_type},
                access_scope VARCHAR(32) DEFAULT 'private',
                created_at {ts_type} NOT NULL DEFAULT {now_val},
                updated_at {ts_type} NOT NULL DEFAULT {now_val},
                FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
            )
        """)

        # Create Indexes for user_id, conversation_id, document_id, case_id
        index_queries = [
            "CREATE INDEX IF NOT EXISTS idx_users_auth_id ON users(auth_user_id)",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_conv_messages_conv ON conversation_messages(conversation_id)",
            "CREATE INDEX IF NOT EXISTS idx_conv_messages_user ON conversation_messages(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_memories_user ON user_memories(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_memories_type ON user_memories(user_id, memory_type)",
            "CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_documents_case ON documents(user_id, case_id)",
            "CREATE INDEX IF NOT EXISTS idx_ku_user ON knowledge_units(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_ku_doc ON knowledge_units(document_id)",
            "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id)",
        ]
        for q in index_queries:
            try:
                cursor.execute(q)
            except Exception as e:
                logger.debug("Index creation notice: %s", e)

        conn.commit()
    logger.info("Database initialized successfully.")
