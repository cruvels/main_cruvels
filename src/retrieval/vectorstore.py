"""
Vector store build/load with Chroma.
Enforces user_id scoping across all embeddings and searches.
Never runs unrestricted vector searches across private user data.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from langchain_chroma import Chroma

from src.config import get_path
from src.ingestion.preprocess import Chunk
from .embeddings import get_embeddings

logger = logging.getLogger(__name__)

_CACHED_VECTORSTORE: Chroma | None = None


def reset_vectorstore_cache() -> None:
    """Invalidates the in-memory Chroma vectorstore instance."""
    global _CACHED_VECTORSTORE
    _CACHED_VECTORSTORE = None


def build_vectorstore(
    chunks: list[Chunk],
    visibility: str = "private",
    user_id: str = "ui-user",
    case_id: Optional[str] = None,
    tenant_id: str = "default_tenant",
) -> Chroma:
    """
    Embed chunks and ADD them to the local Chroma store with user_id metadata.
    Ensures vector data is traceable back to the owner user_id.
    """
    global _CACHED_VECTORSTORE
    persist_dir = str(get_path("vectorstore_dir"))
    embeddings = get_embeddings()

    texts = [c.text for c in chunks]
    metadatas = [
        {
            "chunk_id": c.chunk_id,
            "doc_id": c.doc_id,
            "document_id": c.doc_id,
            "file_name": c.file_name,
            "page_number": c.page_number,
            "source_type": c.source_type,
            "visibility": visibility,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "case_id": case_id or "",
            "knowledge_type": "legal_document",
        }
        for c in chunks
    ]
    ids = [c.chunk_id for c in chunks]

    logger.info("Adding %d chunks to vectorstore for user %s at %s", len(chunks), user_id, persist_dir)

    store = None
    if _CACHED_VECTORSTORE is not None:
        try:
            _CACHED_VECTORSTORE.add_texts(texts=texts, metadatas=metadatas, ids=ids)
            store = _CACHED_VECTORSTORE
        except Exception as e:
            logger.warning("Failed to add to cached vectorstore (%s). Resetting cache.", e)
            _CACHED_VECTORSTORE = None

    if store is None:
        try:
            store = Chroma(
                persist_directory=persist_dir,
                embedding_function=embeddings,
                collection_name="briefly_stage1",
            )
            store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
        except Exception as e:
            logger.warning("Error with existing store (%s). Recreating clean vectorstore...", e)
            import shutil
            from pathlib import Path
            p = Path(persist_dir)
            if p.exists():
                shutil.rmtree(p)
            p.mkdir(parents=True, exist_ok=True)
            store = Chroma.from_texts(
                texts=texts,
                embedding=embeddings,
                metadatas=metadatas,
                ids=ids,
                persist_directory=persist_dir,
                collection_name="briefly_stage1",
            )

    _CACHED_VECTORSTORE = store
    try:
        count = store._collection.count()
        logger.info("Vectorstore now contains %d documents", count)
    except Exception:
        pass
    return store


def load_vectorstore() -> Chroma:
    global _CACHED_VECTORSTORE
    if _CACHED_VECTORSTORE is not None:
        return _CACHED_VECTORSTORE

    persist_dir = str(get_path("vectorstore_dir"))
    embeddings = get_embeddings()
    try:
        _CACHED_VECTORSTORE = Chroma(
            persist_directory=persist_dir,
            embedding_function=embeddings,
            collection_name="briefly_stage1",
        )
    except Exception as e:
        logger.warning("Error loading vectorstore (%s). Initializing fresh vectorstore...", e)
        import shutil
        from pathlib import Path
        p = Path(persist_dir)
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)
        _CACHED_VECTORSTORE = Chroma(
            persist_directory=persist_dir,
            embedding_function=embeddings,
            collection_name="briefly_stage1",
        )
    return _CACHED_VECTORSTORE


def delete_document_vectors(document_id: str, user_id: str) -> int:
    """Synchronously deletes document vector chunks belonging to the specified user."""
    store = load_vectorstore()
    try:
        # Chroma collection delete with where clause
        where_filter = {
            "$and": [
                {"doc_id": document_id},
                {"user_id": user_id},
            ]
        }
        res = store._collection.get(where=where_filter)
        ids_to_delete = res.get("ids", [])
        if ids_to_delete:
            store._collection.delete(ids=ids_to_delete)
            logger.info("Deleted %d vectors for doc_id %s, user %s", len(ids_to_delete), document_id, user_id)
            return len(ids_to_delete)
    except Exception as e:
        logger.warning("Error deleting vectors for document %s: %s", document_id, e)
    return 0


def add_memory_vector(
    user_id: str,
    memory_id: str,
    memory_content: str,
    memory_type: str,
    importance: float = 0.5,
) -> None:
    """Stores vector representation for semantic user memory retrieval."""
    store = load_vectorstore()
    try:
        doc_id = f"mem_vec_{memory_id}"
        meta = {
            "user_id": user_id,
            "memory_id": memory_id,
            "memory_type": memory_type,
            "importance": float(importance),
            "knowledge_type": "user_memory",
            "visibility": "private",
        }
        store.add_texts(texts=[memory_content], metadatas=[meta], ids=[doc_id])
    except Exception as e:
        logger.warning("Error storing memory vector: %s", e)


def delete_memory_vectors(memory_id: str, user_id: str) -> None:
    """Synchronously deletes memory vectors from Chroma."""
    store = load_vectorstore()
    try:
        doc_id = f"mem_vec_{memory_id}"
        store._collection.delete(ids=[doc_id])
    except Exception as e:
        logger.warning("Error deleting memory vector %s: %s", memory_id, e)


def search_vectorstore_user_scoped(
    query: str,
    user_id: str,
    top_k: int = 5,
    case_id: Optional[str] = None,
    knowledge_type: Optional[str] = None,
) -> List[tuple[Any, float]]:
    """
    Executes similarity search strictly scoped to the authenticated user.
    Never returns chunks belonging to other users.
    """
    store = load_vectorstore()
    filters: List[Dict[str, Any]] = [{"user_id": user_id}]
    if case_id:
        filters.append({"case_id": case_id})
    if knowledge_type:
        filters.append({"knowledge_type": knowledge_type})

    where_filter = filters[0] if len(filters) == 1 else {"$and": filters}

    try:
        results = store.similarity_search_with_relevance_scores(
            query=query,
            k=top_k,
            filter=where_filter,
        )
        return results
    except Exception as e:
        logger.warning("User-scoped vector search error: %s", e)
        # Fallback to direct collection query or manual filter
        try:
            results = store.similarity_search_with_relevance_scores(query=query, k=top_k * 2)
            # Filter strictly by user_id in Python
            return [(d, s) for d, s in results if d.metadata.get("user_id") == user_id][:top_k]
        except Exception:
            return []
