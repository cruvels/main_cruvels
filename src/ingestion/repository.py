"""
Database repositories and metadata manager for Phase 1 structured knowledge.
Stores Document Metadata, Sections, Paragraphs, Entities, Concepts, Claims, and Processing Jobs in SQLite/PostgreSQL.
Ensures tenant/user isolation at storage and retrieval time.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.config import get_path
from .models import (
    ClaimModel,
    ConceptModel,
    DocumentMetadata,
    DocumentStatus,
    DocumentType,
    EntityModel,
    ParagraphModel,
    SectionModel,
)


class DocumentRepository:
    """Manages relational metadata persistence for documents and extracted knowledge units."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            self.db_path = get_path("processed_data_dir") / "legal_kb.sqlite3"
        else:
            self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Documents table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    classification_confidence REAL DEFAULT 0.0,
                    case_id TEXT,
                    access_scope TEXT DEFAULT 'private',
                    status TEXT NOT NULL,
                    original_file_location TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Sections table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS document_sections (
                    section_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    parent_section_id TEXT,
                    title TEXT NOT NULL,
                    level INTEGER DEFAULT 1,
                    page_number INTEGER DEFAULT 1,
                    order_index INTEGER DEFAULT 0,
                    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
                )
            """)

            # Paragraphs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS document_paragraphs (
                    paragraph_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    section_id TEXT,
                    page_number INTEGER DEFAULT 1,
                    text TEXT NOT NULL,
                    order_index INTEGER DEFAULT 0,
                    is_clause INTEGER DEFAULT 0,
                    clause_number TEXT,
                    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
                )
            """)

            # Entities table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    context TEXT,
                    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
                )
            """)

            # Concepts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS concepts (
                    concept_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    description TEXT,
                    relevance_score REAL DEFAULT 1.0,
                    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
                )
            """)

            # Claims table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS claims (
                    claim_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    section_id TEXT,
                    claim_text TEXT NOT NULL,
                    claim_type TEXT DEFAULT 'factual',
                    confidence REAL DEFAULT 1.0,
                    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
                )
            """)

            # Processing jobs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processing_jobs (
                    job_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress REAL DEFAULT 0.0,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Knowledge Units table (Phase 2 & Phase 3)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_units (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    case_id TEXT,
                    chunk_id TEXT NOT NULL,
                    parent_chunk_id TEXT,
                    document_type TEXT,
                    section_type TEXT,
                    section_title TEXT,
                    legal_topic TEXT,
                    text TEXT NOT NULL,
                    importance_score REAL DEFAULT 0.5,
                    entities_json TEXT,
                    concepts_json TEXT,
                    claims_json TEXT,
                    access_scope TEXT DEFAULT 'private',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def create_document(self, meta: DocumentMetadata) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO documents (
                    document_id, user_id, tenant_id, filename, file_type,
                    file_size, checksum, document_type, classification_confidence,
                    case_id, access_scope, status, original_file_location,
                    error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meta.document_id,
                    meta.user_id,
                    meta.tenant_id,
                    meta.filename,
                    meta.file_type,
                    meta.file_size,
                    meta.checksum,
                    meta.document_type.value if hasattr(meta.document_type, "value") else str(meta.document_type),
                    meta.classification_confidence,
                    meta.case_id,
                    meta.access_scope,
                    meta.status.value if hasattr(meta.status, "value") else str(meta.status),
                    meta.original_file_location,
                    meta.error_message,
                    meta.created_at.isoformat(),
                    meta.updated_at.isoformat(),
                ),
            )
            conn.commit()

    def update_document_status(
        self,
        document_id: str,
        status: DocumentStatus,
        doc_type: Optional[DocumentType] = None,
        confidence: Optional[float] = None,
        error_msg: Optional[str] = None,
    ) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            if doc_type is not None and confidence is not None:
                cursor.execute(
                    """
                    UPDATE documents
                    SET status = ?, document_type = ?, classification_confidence = ?, error_message = ?, updated_at = ?
                    WHERE document_id = ?
                    """,
                    (
                        status.value,
                        doc_type.value if hasattr(doc_type, "value") else str(doc_type),
                        confidence,
                        error_msg,
                        now,
                        document_id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    UPDATE documents
                    SET status = ?, error_message = ?, updated_at = ?
                    WHERE document_id = ?
                    """,
                    (status.value, error_msg, now, document_id),
                )
            conn.commit()

    def get_document(self, document_id: str, user_id: Optional[str] = None) -> Optional[DocumentMetadata]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute(
                    "SELECT * FROM documents WHERE document_id = ? AND user_id = ?",
                    (document_id, user_id),
                )
            else:
                cursor.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return DocumentMetadata(
                document_id=row["document_id"],
                user_id=row["user_id"],
                tenant_id=row["tenant_id"],
                filename=row["filename"],
                file_type=row["file_type"],
                file_size=row["file_size"],
                checksum=row["checksum"],
                document_type=DocumentType(row["document_type"]) if row["document_type"] in DocumentType.__members__.values() else DocumentType.OTHER,
                classification_confidence=row["classification_confidence"],
                case_id=row["case_id"],
                access_scope=row["access_scope"],
                status=DocumentStatus(row["status"]),
                original_file_location=row["original_file_location"],
                error_message=row["error_message"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    def list_documents(self, user_id: str, case_id: Optional[str] = None) -> List[DocumentMetadata]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if case_id:
                cursor.execute(
                    "SELECT * FROM documents WHERE user_id = ? AND case_id = ? ORDER BY created_at DESC",
                    (user_id, case_id),
                )
            else:
                cursor.execute(
                    "SELECT * FROM documents WHERE user_id = ? ORDER BY created_at DESC",
                    (user_id,),
                )
            rows = cursor.fetchall()
            docs = []
            for row in rows:
                doc_type_val = row["document_type"]
                try:
                    dt = DocumentType(doc_type_val)
                except ValueError:
                    dt = DocumentType.OTHER
                docs.append(
                    DocumentMetadata(
                        document_id=row["document_id"],
                        user_id=row["user_id"],
                        tenant_id=row["tenant_id"],
                        filename=row["filename"],
                        file_type=row["file_type"],
                        file_size=row["file_size"],
                        checksum=row["checksum"],
                        document_type=dt,
                        classification_confidence=row["classification_confidence"],
                        case_id=row["case_id"],
                        access_scope=row["access_scope"],
                        status=DocumentStatus(row["status"]),
                        original_file_location=row["original_file_location"],
                        error_message=row["error_message"],
                        created_at=datetime.fromisoformat(row["created_at"]),
                        updated_at=datetime.fromisoformat(row["updated_at"]),
                    )
                )
            return docs

    def delete_document(self, document_id: str, user_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM documents WHERE document_id = ? AND user_id = ?",
                (document_id, user_id),
            )
            deleted = cursor.rowcount > 0
            if deleted:
                cursor.execute("DELETE FROM document_sections WHERE document_id = ?", (document_id,))
                cursor.execute("DELETE FROM document_paragraphs WHERE document_id = ?", (document_id,))
                cursor.execute("DELETE FROM entities WHERE document_id = ?", (document_id,))
                cursor.execute("DELETE FROM concepts WHERE document_id = ?", (document_id,))
                cursor.execute("DELETE FROM claims WHERE document_id = ?", (document_id,))
                cursor.execute("DELETE FROM processing_jobs WHERE document_id = ?", (document_id,))
            conn.commit()
            return deleted

    def save_knowledge_extraction(
        self,
        document_id: str,
        sections: List[SectionModel],
        entities: List[EntityModel],
        concepts: List[ConceptModel],
        claims: List[ClaimModel],
    ) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for sec in sections:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO document_sections
                    (section_id, document_id, parent_section_id, title, level, page_number, order_index)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sec.section_id, document_id, sec.parent_section_id, sec.title, sec.level, sec.page_number, sec.order_index),
                )
                for p in sec.paragraphs:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO document_paragraphs
                        (paragraph_id, document_id, section_id, page_number, text, order_index, is_clause, clause_number)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (p.paragraph_id, document_id, sec.section_id, p.page_number, p.text, p.order_index, 1 if p.is_clause else 0, p.clause_number),
                    )

            for ent in entities:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO entities
                    (entity_id, document_id, entity_type, name, confidence, context)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (ent.entity_id, document_id, ent.entity_type, ent.name, ent.confidence, ent.context),
                )

            for conc in concepts:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO concepts
                    (concept_id, document_id, topic, description, relevance_score)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (conc.concept_id, document_id, conc.topic, conc.description, conc.relevance_score),
                )

            for clm in claims:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO claims
                    (claim_id, document_id, section_id, claim_text, claim_type, confidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (clm.claim_id, document_id, clm.section_id, clm.claim_text, clm.claim_type, clm.confidence),
                )
            conn.commit()

    def get_extracted_knowledge(self, document_id: str) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM document_sections WHERE document_id = ? ORDER BY order_index", (document_id,))
            sections = [dict(row) for row in cursor.fetchall()]

            cursor.execute("SELECT * FROM document_paragraphs WHERE document_id = ? ORDER BY order_index", (document_id,))
            paragraphs = [dict(row) for row in cursor.fetchall()]

            cursor.execute("SELECT * FROM entities WHERE document_id = ?", (document_id,))
            entities = [dict(row) for row in cursor.fetchall()]

            cursor.execute("SELECT * FROM concepts WHERE document_id = ?", (document_id,))
            concepts = [dict(row) for row in cursor.fetchall()]

            cursor.execute("SELECT * FROM claims WHERE document_id = ?", (document_id,))
            claims = [dict(row) for row in cursor.fetchall()]

            return {
                "sections": sections,
                "paragraphs": paragraphs,
                "entities": entities,
                "concepts": concepts,
                "claims": claims,
            }


_default_repo: Optional[DocumentRepository] = None


def get_document_repository() -> DocumentRepository:
    global _default_repo
    if _default_repo is None:
        _default_repo = DocumentRepository()
    return _default_repo
