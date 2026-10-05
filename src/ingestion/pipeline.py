"""
Phase 1 Ingestion Pipeline Orchestrator.
Coordinates:
1. File validation & storage (SHA256, original preservation)
2. Format-specific Parsing & OCR
3. Structure Detection (Headings, Sections, Paragraphs, Tables, Citations)
4. Document Type Classification
5. Semantic Understanding (Entities, Concepts, Claims)
6. Relational Knowledge Storage (Postgres/SQLite)
7. Status & Job updates
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import BinaryIO, Optional
import uuid

from .models import (
    DocumentMetadata,
    DocumentStatus,
    DocumentType,
    ParsedDocument,
)
from .parsers import get_parser
from .repository import DocumentRepository, get_document_repository
from .semantic import classify_document, extract_semantics
from .storage import DocumentStorage, get_document_storage

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """End-to-end Phase 1 document ingestion and understanding pipeline."""

    def __init__(
        self,
        storage: Optional[DocumentStorage] = None,
        repository: Optional[DocumentRepository] = None,
    ):
        self.storage = storage or get_document_storage()
        self.repo = repository or get_document_repository()

    def process_document(
        self,
        file_obj: BinaryIO,
        filename: str,
        user_id: str,
        tenant_id: str = "default_tenant",
        case_id: Optional[str] = None,
        access_scope: str = "private",
    ) -> DocumentMetadata:
        """
        Executes full Phase 1 pipeline:
        Storage -> Validation -> Parsing & OCR -> Structure -> Classification -> Semantics -> DB
        """
        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        ext = Path(filename).suffix.lower()

        logger.info("Starting Phase 1 ingestion for file: %s (doc_id: %s, user_id: %s)", filename, doc_id, user_id)

        # 1. Save original file
        storage_path, checksum, file_size = self.storage.save_file(file_obj, filename, user_id, doc_id)

        # 2. Initial Document Metadata
        meta = DocumentMetadata(
            document_id=doc_id,
            user_id=user_id,
            tenant_id=tenant_id,
            filename=filename,
            file_type=ext,
            file_size=file_size,
            checksum=checksum,
            document_type=DocumentType.OTHER,
            classification_confidence=0.0,
            case_id=case_id,
            access_scope=access_scope,
            status=DocumentStatus.PROCESSING,
            original_file_location=storage_path,
        )
        self.repo.create_document(meta)

        try:
            # 3. Parse Document & Run OCR where necessary
            self.repo.update_document_status(doc_id, DocumentStatus.OCR)
            parser = get_parser(ext)
            parse_result = parser.parse(Path(storage_path), doc_id)

            full_text = parse_result["text"]
            structure = parse_result["structure"]

            # 4. Classification & Semantic Understanding
            self.repo.update_document_status(doc_id, DocumentStatus.ANALYZING)
            doc_type, class_conf = classify_document(full_text)
            entities, concepts, claims = extract_semantics(full_text, doc_id)

            # 5. Persist Extracted Knowledge Structures
            self.repo.save_knowledge_extraction(
                document_id=doc_id,
                sections=structure.sections,
                entities=entities,
                concepts=concepts,
                claims=claims,
            )

            # 6. Finalize Status
            self.repo.update_document_status(
                document_id=doc_id,
                status=DocumentStatus.COMPLETED,
                doc_type=doc_type,
                confidence=class_conf,
            )

            updated_meta = self.repo.get_document(doc_id, user_id)
            logger.info("Successfully completed Phase 1 ingestion for %s (Type: %s)", filename, doc_type.value)
            return updated_meta or meta

        except Exception as e:
            logger.exception("Ingestion failed for %s: %s", filename, e)
            self.repo.update_document_status(
                document_id=doc_id,
                status=DocumentStatus.FAILED,
                error_msg=str(e),
            )
            failed_meta = self.repo.get_document(doc_id, user_id)
            return failed_meta or meta


_default_pipeline: Optional[IngestionPipeline] = None


def get_ingestion_pipeline() -> IngestionPipeline:
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = IngestionPipeline()
    return _default_pipeline
