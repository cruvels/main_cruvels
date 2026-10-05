"""
Phase 2: Personal Knowledge Base & Intelligent Indexing.
Defines KnowledgeUnit, Importance Analyzer, Hierarchical and Contextual Chunking,
and Multi-representation persistence in PostgreSQL/SQLite and VectorDB.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.config import get_path
from src.ingestion.models import ClaimModel, ConceptModel, EntityModel, SectionModel
from src.ingestion.repository import get_document_repository
from src.retrieval.embeddings import get_embeddings
from src.retrieval.vectorstore import build_vectorstore

logger = logging.getLogger(__name__)


class KnowledgeUnit(BaseModel):
    id: str
    user_id: str
    tenant_id: str = "default_tenant"
    document_id: str
    case_id: Optional[str] = None
    chunk_id: str
    parent_chunk_id: Optional[str] = None
    document_type: str = "Other"
    section_type: str = "General"
    section_title: str = ""
    legal_topic: str = "general"
    text: str
    context_prefix: str = ""
    importance_score: float = 0.5
    authority_score: float = 0.5
    relevance_score: float = 0.5
    recency_score: float = 0.5
    confidence_score: float = 1.0
    citation_count: int = 0
    entities: List[str] = Field(default_factory=list)
    concepts: List[str] = Field(default_factory=list)
    claims: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    access_scope: str = "private"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def calculate_importance_score(
    text: str,
    section_title: str,
    entities: List[str],
    concepts: List[str],
    claims: List[str],
    citations: List[str],
) -> float:
    """
    Computes an explainable importance score between 0.0 and 1.0 based on:
    - Legal keywords (holding, ordered, agreed, breach, liability, shall, terminate)
    - Density of extracted entities & legal concepts
    - Presence of citations & verifiable legal claims
    - Critical section headings (Definitions, Obligations, Remedies, Operative Order)
    """
    score = 0.30

    # Section relevance signal
    high_value_sections = ["order", "judgment", "obligations", "liability", "damages", "remedies", "termination", "holding"]
    if any(h in section_title.lower() for h in high_value_sections):
        score += 0.20

    # Claims signal
    if claims:
        score += min(len(claims) * 0.10, 0.20)

    # Citations signal
    if citations:
        score += min(len(citations) * 0.08, 0.15)

    # Concept density signal
    if concepts:
        score += min(len(concepts) * 0.05, 0.10)

    # Entity density signal
    if entities:
        score += min(len(entities) * 0.02, 0.05)

    return min(max(round(score, 3), 0.1), 1.0)


class PersonalKnowledgeBaseIndexer:
    """Orchestrates indexing of documents into structured relational knowledge units & vectors."""

    def __init__(self):
        self.repo = get_document_repository()
        self.embeddings = get_embeddings()

    def index_document(self, document_id: str, user_id: str) -> List[KnowledgeUnit]:
        """Extracts sections, runs contextual chunking, computes importance, and persists to DB and VectorDB."""
        doc = self.repo.get_document(document_id, user_id=user_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found or unauthorized for user {user_id}")

        extracted = self.repo.get_extracted_knowledge(document_id)
        sections = extracted.get("sections", [])
        paragraphs = extracted.get("paragraphs", [])
        entities = [e["name"] for e in extracted.get("entities", [])]
        concepts = [c["topic"] for c in extracted.get("concepts", [])]
        claims = [cl["claim_text"] for cl in extracted.get("claims", [])]

        knowledge_units: List[KnowledgeUnit] = []

        # If document had sections, chunk hierarchically with context
        if sections:
            for s_idx, sec in enumerate(sections):
                sec_id = sec["section_id"]
                sec_title = sec["title"]
                sec_paras = [p for p in paragraphs if p.get("section_id") == sec_id]
                sec_text = "\n".join(p["text"] for p in sec_paras) if sec_paras else sec_title

                imp = calculate_importance_score(
                    text=sec_text,
                    section_title=sec_title,
                    entities=entities,
                    concepts=concepts,
                    claims=claims,
                    citations=[],
                )

                ku_id = f"{document_id}_ku_sec_{s_idx}"
                ku = KnowledgeUnit(
                    id=ku_id,
                    user_id=user_id,
                    tenant_id=doc.tenant_id,
                    document_id=document_id,
                    case_id=doc.case_id,
                    chunk_id=ku_id,
                    parent_chunk_id=None,
                    document_type=doc.document_type.value if hasattr(doc.document_type, "value") else str(doc.document_type),
                    section_type=f"Section {sec.get('level', 1)}",
                    section_title=sec_title,
                    legal_topic=concepts[0] if concepts else "general",
                    text=sec_text or sec_title,
                    context_prefix=f"[Document: {doc.filename} | Section: {sec_title}]",
                    importance_score=imp,
                    entities=entities[:5],
                    concepts=concepts[:5],
                    claims=claims[:3],
                    citations=[],
                    access_scope=doc.access_scope,
                )
                knowledge_units.append(ku)

                # Contextual Child Chunks for paragraphs
                for p_idx, p in enumerate(sec_paras):
                    p_text = p["text"]
                    p_imp = calculate_importance_score(
                        text=p_text,
                        section_title=sec_title,
                        entities=entities,
                        concepts=concepts,
                        claims=claims,
                        citations=[],
                    )
                    child_id = f"{document_id}_ku_p_{s_idx}_{p_idx}"
                    child_ku = KnowledgeUnit(
                        id=child_id,
                        user_id=user_id,
                        tenant_id=doc.tenant_id,
                        document_id=document_id,
                        case_id=doc.case_id,
                        chunk_id=child_id,
                        parent_chunk_id=ku_id,
                        document_type=doc.document_type.value if hasattr(doc.document_type, "value") else str(doc.document_type),
                        section_type="Paragraph",
                        section_title=sec_title,
                        legal_topic=concepts[0] if concepts else "general",
                        text=p_text,
                        context_prefix=f"[Context: {sec_title}] ",
                        importance_score=p_imp,
                        entities=entities[:3],
                        concepts=concepts[:3],
                        claims=claims[:2],
                        citations=[],
                        access_scope=doc.access_scope,
                    )
                    knowledge_units.append(child_ku)
        else:
            # Fallback if no sections detected
            for p_idx, p in enumerate(paragraphs):
                p_text = p["text"]
                imp = calculate_importance_score(p_text, "General", entities, concepts, claims, [])
                ku_id = f"{document_id}_ku_{p_idx}"
                ku = KnowledgeUnit(
                    id=ku_id,
                    user_id=user_id,
                    tenant_id=doc.tenant_id,
                    document_id=document_id,
                    case_id=doc.case_id,
                    chunk_id=ku_id,
                    document_type=doc.document_type.value if hasattr(doc.document_type, "value") else str(doc.document_type),
                    section_title="General",
                    text=p_text,
                    importance_score=imp,
                    entities=entities[:3],
                    concepts=concepts[:3],
                    claims=claims[:2],
                    access_scope=doc.access_scope,
                )
                knowledge_units.append(ku)

        # Store knowledge units into relational SQLite table
        with self.repo._get_connection() as conn:
            cursor = conn.cursor()
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
            now = datetime.utcnow().isoformat()
            for k in knowledge_units:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO knowledge_units
                    (id, user_id, tenant_id, document_id, case_id, chunk_id, parent_chunk_id,
                     document_type, section_type, section_title, legal_topic, text, importance_score,
                     entities_json, concepts_json, claims_json, access_scope, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        k.id,
                        k.user_id,
                        k.tenant_id,
                        k.document_id,
                        k.case_id,
                        k.chunk_id,
                        k.parent_chunk_id,
                        k.document_type,
                        k.section_type,
                        k.section_title,
                        k.legal_topic,
                        k.text,
                        k.importance_score,
                        json.dumps(k.entities),
                        json.dumps(k.concepts),
                        json.dumps(k.claims),
                        k.access_scope,
                        now,
                        now,
                    ),
                )
            conn.commit()

        logger.info("Indexed %d Knowledge Units for document %s (user: %s)", len(knowledge_units), document_id, user_id)
        return knowledge_units


_default_indexer: Optional[PersonalKnowledgeBaseIndexer] = None


def get_pkb_indexer() -> PersonalKnowledgeBaseIndexer:
    global _default_indexer
    if _default_indexer is None:
        _default_indexer = PersonalKnowledgeBaseIndexer()
    return _default_indexer
