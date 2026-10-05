"""
Retrieval: fetch the most relevant chunks for a user question, filtered to
only what the current authenticated user and session is authorized to see.
Enforces strict user isolation: User A cannot retrieve User B's documents.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.config import get_settings
from src.context.permissions import AuthorizedScope
from .vectorstore import load_vectorstore

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    doc_id: str
    file_name: str
    page_number: int
    score: float
    source_type: str
    user_id: str = ""


def retrieve_chunks(query: str, scope: AuthorizedScope) -> list[RetrievedChunk]:
    settings = get_settings()
    top_k = settings["retrieval"]["top_k"]
    threshold = settings["retrieval"]["score_threshold"]

    store = load_vectorstore()

    try:
        # Chroma similarity_search_with_relevance_scores returns (Document, score)
        results = store.similarity_search_with_relevance_scores(
            query,
            k=min(top_k * 3, 20),
        )
    except Exception as e:
        logger.warning("Error during similarity search: %s", e)
        return []

    filtered: list[RetrievedChunk] = []
    for doc, score in results:
        meta = doc.metadata
        chunk_user_id = meta.get("user_id")
        visibility = meta.get("visibility", "private")

        # 1. Enforce strict user isolation: private chunks must match scope.user_id
        if chunk_user_id and scope.user_id:
            if chunk_user_id != scope.user_id and visibility != "shared":
                continue

        # 2. Case scope isolation
        if scope.case_id and meta.get("case_id"):
            if meta.get("case_id") != scope.case_id:
                continue

        # 3. Visibility permission check
        if not scope.can_access(visibility, meta.get("doc_id")):
            continue

        # 4. Score threshold
        if score < threshold:
            continue

        filtered.append(
            RetrievedChunk(
                text=doc.page_content,
                doc_id=meta.get("doc_id") or meta.get("document_id", ""),
                file_name=meta.get("file_name", "Document"),
                page_number=int(meta.get("page_number", 1)),
                score=score,
                source_type=meta.get("source_type", "document"),
                user_id=chunk_user_id or "",
            )
        )
        if len(filtered) >= top_k:
            break

    logger.info("Retrieved %d user-scoped chunks above threshold %.2f for user %s", len(filtered), threshold, scope.user_id)
    return filtered
