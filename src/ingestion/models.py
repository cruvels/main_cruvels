"""
Data models and schemas for Phase 1 (Document Ingestion & Understanding).
Represents Document Metadata, Normalized Document, Sections, Paragraphs,
Entities, Concepts, Claims, and Processing Statuses.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class DocumentStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    PROCESSING = "PROCESSING"
    OCR = "OCR"
    ANALYZING = "ANALYZING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DocumentType(str, enum.Enum):
    JUDGMENT = "Judgment"
    CONTRACT = "Contract"
    AGREEMENT = "Agreement"
    LEGAL_NOTICE = "Legal Notice"
    PETITION = "Petition"
    WRITTEN_STATEMENT = "Written Statement"
    RESEARCH_DOCUMENT = "Research Document"
    CASE_FILE = "Case File"
    DRAFT = "Draft"
    TEMPLATE = "Template"
    CORRESPONDENCE = "Correspondence"
    OTHER = "Other"


class ParagraphModel(BaseModel):
    paragraph_id: str
    section_id: Optional[str] = None
    page_number: int
    text: str
    order_index: int = 0
    is_clause: bool = False
    clause_number: Optional[str] = None


class SectionModel(BaseModel):
    section_id: str
    parent_section_id: Optional[str] = None
    title: str
    level: int = 1
    page_number: int = 1
    order_index: int = 0
    paragraphs: List[ParagraphModel] = Field(default_factory=list)


class TableModel(BaseModel):
    table_id: str
    page_number: int
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)


class EntityModel(BaseModel):
    entity_id: str
    document_id: str
    entity_type: str  # person, organization, court, judge, company, date, amount, location, statute, section, case, party
    name: str
    confidence: float = 1.0
    context: Optional[str] = None


class ConceptModel(BaseModel):
    concept_id: str
    document_id: str
    topic: str  # breach, limitation, arbitration, jurisdiction, damages, indemnity, termination, obligations, etc.
    description: Optional[str] = None
    relevance_score: float = 1.0


class ClaimModel(BaseModel):
    claim_id: str
    document_id: str
    section_id: Optional[str] = None
    claim_text: str
    claim_type: str = "factual"  # factual, legal, procedural
    confidence: float = 1.0


class DocumentHierarchy(BaseModel):
    title: str = ""
    sections: List[SectionModel] = Field(default_factory=list)
    tables: List[TableModel] = Field(default_factory=list)
    footnotes: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    signature_block_detected: bool = False


class DocumentMetadata(BaseModel):
    document_id: str
    user_id: str
    tenant_id: str = "default_tenant"
    filename: str
    file_type: str
    file_size: int
    checksum: str
    document_type: DocumentType = DocumentType.OTHER
    classification_confidence: float = 0.0
    case_id: Optional[str] = None
    access_scope: str = "private"
    status: DocumentStatus = DocumentStatus.UPLOADED
    original_file_location: str = ""
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ParsedDocument(BaseModel):
    document_id: str
    text: str
    pages: List[dict] = Field(default_factory=list)
    structure: DocumentHierarchy = Field(default_factory=DocumentHierarchy)
    entities: List[EntityModel] = Field(default_factory=list)
    concepts: List[ConceptModel] = Field(default_factory=list)
    claims: List[ClaimModel] = Field(default_factory=list)
    metadata: DocumentMetadata
