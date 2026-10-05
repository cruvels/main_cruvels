"""
Ingestion module exports for Task B.
"""
from .models import (
    ClaimModel,
    ConceptModel,
    DocumentHierarchy,
    DocumentMetadata,
    DocumentStatus,
    DocumentType,
    EntityModel,
    ParagraphModel,
    ParsedDocument,
    SectionModel,
    TableModel,
)
from .parsers import (
    DOCXParser,
    DocumentParser,
    ImageParser,
    PDFParser,
    TXTParser,
    get_parser,
)
from .pipeline import IngestionPipeline, get_ingestion_pipeline
from .repository import DocumentRepository, get_document_repository
from .semantic import classify_document, extract_semantics
from .storage import DocumentStorage, LocalDocumentStorage, get_document_storage

__all__ = [
    "DocumentStatus",
    "DocumentType",
    "ParagraphModel",
    "SectionModel",
    "TableModel",
    "EntityModel",
    "ConceptModel",
    "ClaimModel",
    "DocumentHierarchy",
    "DocumentMetadata",
    "ParsedDocument",
    "DocumentParser",
    "PDFParser",
    "DOCXParser",
    "TXTParser",
    "ImageParser",
    "get_parser",
    "DocumentStorage",
    "LocalDocumentStorage",
    "get_document_storage",
    "DocumentRepository",
    "get_document_repository",
    "classify_document",
    "extract_semantics",
    "IngestionPipeline",
    "get_ingestion_pipeline",
]
