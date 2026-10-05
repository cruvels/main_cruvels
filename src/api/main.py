"""
FastAPI Backend Server for Cruvels AI Legal Knowledge Assistant.
Enforces Individual Authentication, User-Scoped Memory, and Strict Authorization.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

from src.config import get_settings, get_path, setup_logging
from src.context.permissions import AuthorizedScope
from src.agent.graph import run_agent
from src.ingestion.loader import load_document
from src.ingestion.preprocess import chunk_document
from src.ingestion.pipeline import get_ingestion_pipeline
from src.ingestion.repository import get_document_repository
from src.ingestion.storage import get_document_storage
from src.context.pkb import get_pkb_indexer
from src.retrieval.hybrid import get_hybrid_retriever
from src.agent.drafting import get_drafting_agent, DraftingRequest, StyleEngine
from src.llm.model import get_llm
from src.retrieval.vectorstore import build_vectorstore, reset_vectorstore_cache, delete_document_vectors

# Auth & Database & Memory imports
from src.db.connection import init_database
from src.db.repositories import (
    UserModel,
    ConversationRepository,
    AuditRepository,
    UserRepository,
    UserSettingsRepository,
)
from src.auth.dependencies import get_current_user, get_optional_user
from src.auth.appwrite_service import get_auth_service
from src.memory.service import get_memory_service
from src.api.routers import auth, users, conversations, memory

logger = logging.getLogger(__name__)

SUGGESTIONS_CACHE = {
    "key": None,
    "suggestions": None,
}

DEFAULT_SUGGESTIONS = [
    {
        "label": "Parties in the agreement",
        "question": "Who are the parties involved in this agreement?",
        "icon": "fa-solid fa-users",
    },
    {
        "label": "Key terms & obligations",
        "question": "What are the primary terms, duties, and obligations specified in this document?",
        "icon": "fa-solid fa-file-contract",
    },
    {
        "label": "Confidentiality & restrictions",
        "question": "What confidentiality terms, restrictive covenants, or non-disclosure obligations are stated?",
        "icon": "fa-solid fa-shield-halved",
    },
    {
        "label": "Governing law & jurisdiction",
        "question": "What is the governing law, dispute resolution process, and jurisdiction?",
        "icon": "fa-solid fa-gavel",
    },
]

app = FastAPI(
    title="Cruvels AI Legal Assistant API",
    description="Agentic Legal Knowledge RAG System with Cruvels & Kimi LLM - Individual Auth & Memory",
    version="2.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include specialized routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(conversations.router)
app.include_router(memory.router)


@app.on_event("startup")
def on_startup():
    """Initializes authoritative database schema and setup logging."""
    setup_logging()
    init_database()
    logger.info("Cruvels AI Application & Database initialized.")


class AskRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    case_id: Optional[str] = None
    visibility: Optional[str] = "private"


class AskResponse(BaseModel):
    answer: str
    sources: List[dict]
    is_fallback: bool
    conversation_id: Optional[str] = None


@app.get("/api/health")
def health_check():
    settings = get_settings()
    auth_service = get_auth_service()
    return {
        "status": "healthy",
        "llm_provider": settings["llm"]["provider"],
        "llm_model": settings["llm"]["model"],
        "embedding_model": settings["embeddings"]["model"],
        "appwrite_configured": auth_service.is_configured(),
    }


@app.post("/api/ask", response_model=AskResponse)
def ask_question(
    req: AskRequest,
    current_user: UserModel = Depends(get_current_user),
):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    logger.info("Received query from user %s: %s", current_user.id, req.question)
    scope = AuthorizedScope(
        user_id=current_user.id,
        case_id=req.case_id or "",
        allowed_visibilities=("shared", "client", "firm", "private"),
    )

    # 1. Fetch relevant long-term user memories
    memory_service = get_memory_service()
    user_memories = memory_service.retrieve_relevant_memories(current_user.id, req.question)

    # 2. Guarantee active conversation exists for this user so history is ALWAYS preserved
    conv_repo = ConversationRepository()
    active_conv_id = req.conversation_id

    if active_conv_id:
        conv = conv_repo.get_conversation(active_conv_id, current_user.id)
        if not conv:
            title = req.question.strip()[:36] + ("..." if len(req.question.strip()) > 36 else "")
            new_conv = conv_repo.create_conversation(current_user.id, title=title or "Legal Inquiry")
            active_conv_id = new_conv.id
    else:
        title = req.question.strip()[:36] + ("..." if len(req.question.strip()) > 36 else "")
        new_conv = conv_repo.create_conversation(current_user.id, title=title or "Legal Inquiry")
        active_conv_id = new_conv.id

    # Retrieve prior conversation message context for the LLM
    msgs = conv_repo.list_messages(active_conv_id, current_user.id, limit=8)
    conversation_context = [{"role": m.role, "content": m.content} for m in msgs]

    # Persist the user message with guaranteed user ownership
    conv_repo.add_message(active_conv_id, current_user.id, role="user", content=req.question)

    try:
        outcome = run_agent(
            question=req.question,
            scope=scope,
            conversation_context=conversation_context,
            user_memories=user_memories,
        )
        answer = outcome.get("answer", "")

        # 3. Always save assistant response to conversation history with metadata
        conv_repo.add_message(
            active_conv_id,
            current_user.id,
            role="assistant",
            content=answer,
            message_metadata={"sources": outcome.get("sources", []), "is_fallback": outcome.get("is_fallback", False)},
        )

        # 4. Extract new stable memories if auto-memory is enabled
        try:
            memory_service.extract_memories_from_conversation(
                user_id=current_user.id,
                user_message=req.question,
                assistant_response=answer,
                conversation_id=active_conv_id,
            )
        except Exception as mem_err:
            logger.warning("Memory extraction error: %s", mem_err)

        AuditRepository().log(
            user_id=current_user.id,
            operation="RAG_ASK",
            resource_type="query",
            resource_id=active_conv_id,
            result="success",
        )

        return AskResponse(
            answer=answer,
            sources=outcome.get("sources", []),
            is_fallback=outcome.get("is_fallback", False),
            conversation_id=active_conv_id,
        )
    except Exception as e:
        logger.exception("Error during RAG execution")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/suggestions")
def get_document_suggestions(current_user: Optional[UserModel] = Depends(get_optional_user)):
    """Dynamically generate tailored suggested questions by analyzing ingested documents."""
    global SUGGESTIONS_CACHE
    raw_dir = get_path("raw_data_dir")
    if not raw_dir.exists():
        return {"suggestions": DEFAULT_SUGGESTIONS, "is_dynamic": False}

    supported = get_settings()["ingestion"]["supported_extensions"]
    files = [p for p in raw_dir.iterdir() if p.is_file() and p.suffix.lower() in supported]
    if not files:
        return {"suggestions": DEFAULT_SUGGESTIONS, "is_dynamic": False}

    cache_key = "-".join(f"{f.name}:{f.stat().st_mtime}" for f in sorted(files, key=lambda x: x.name))
    if SUGGESTIONS_CACHE["key"] == cache_key and SUGGESTIONS_CACHE["suggestions"]:
        return {"suggestions": SUGGESTIONS_CACHE["suggestions"], "is_dynamic": True}

    doc_text_snippets = []
    for f in files[:2]:
        try:
            doc = load_document(f)
            snippet = doc.full_text[:3000].strip()
            if snippet:
                doc_text_snippets.append(f"--- Document: {f.name} ---\n{snippet}")
        except Exception as e:
            logger.warning("Could not extract sample text from %s: %s", f.name, e)

    if not doc_text_snippets:
        return {"suggestions": DEFAULT_SUGGESTIONS, "is_dynamic": False}

    combined_text = "\n\n".join(doc_text_snippets)

    system_prompt = (
        "You are an expert legal document analyst. "
        "Based on the provided excerpt of the uploaded legal document(s), generate exactly 4 distinct, highly relevant, and specific questions a legal counsel or client would ask to understand this document. "
        "Return ONLY a valid JSON array of 4 objects with this exact structure:\n"
        "[\n"
        '  {"label": "Short label (3-6 words)", "question": "Full actionable legal question", "icon": "fa-solid fa-users"},\n'
        '  {"label": "Short label (3-6 words)", "question": "Full actionable legal question", "icon": "fa-solid fa-calendar-check"},\n'
        '  {"label": "Short label (3-6 words)", "question": "Full actionable legal question", "icon": "fa-solid fa-shield-halved"},\n'
        '  {"label": "Short label (3-6 words)", "question": "Full actionable legal question", "icon": "fa-solid fa-gavel"}\n'
        "]\n"
        "Valid icons include: fa-solid fa-users, fa-solid fa-calendar, fa-solid fa-clock, fa-solid fa-shield-halved, fa-solid fa-gavel, fa-solid fa-file-contract, fa-solid fa-handshake, fa-solid fa-money-bill-wave, fa-solid fa-building-shield, fa-solid fa-scale-balanced."
    )

    try:
        llm = get_llm()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Document excerpt:\n{combined_text[:3500]}\n\nGenerate 4 tailored question suggestions in JSON format."),
        ]
        response = llm.invoke(messages)
        content = response.content.strip()

        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        parsed = json.loads(content)
        if isinstance(parsed, list) and len(parsed) >= 2:
            suggestions = []
            for item in parsed[:4]:
                if isinstance(item, dict) and "question" in item:
                    label = item.get("label") or item["question"][:35] + "..."
                    icon = item.get("icon") or "fa-solid fa-file-lines"
                    suggestions.append({
                        "label": label,
                        "question": item["question"],
                        "icon": icon,
                    })
            if suggestions:
                SUGGESTIONS_CACHE["key"] = cache_key
                SUGGESTIONS_CACHE["suggestions"] = suggestions
                return {"suggestions": suggestions, "is_dynamic": True}
    except Exception as e:
        logger.warning("Failed to dynamically generate document suggestions: %s", e)

    return {"suggestions": DEFAULT_SUGGESTIONS, "is_dynamic": False}


@app.get("/api/documents")
def list_documents(
    case_id: Optional[str] = None,
    current_user: UserModel = Depends(get_current_user),
):
    repo = get_document_repository()
    docs = repo.list_documents(user_id=current_user.id, case_id=case_id)
    return {
        "documents": [
            {
                "document_id": d.document_id,
                "user_id": d.user_id,
                "tenant_id": d.tenant_id,
                "filename": d.filename,
                "file_type": d.file_type,
                "file_size": d.file_size,
                "checksum": d.checksum,
                "document_type": d.document_type.value if hasattr(d.document_type, "value") else str(d.document_type),
                "classification_confidence": d.classification_confidence,
                "case_id": d.case_id,
                "access_scope": d.access_scope,
                "status": d.status.value if hasattr(d.status, "value") else str(d.status),
                "created_at": d.created_at.isoformat(),
                "updated_at": d.updated_at.isoformat(),
            }
            for d in docs
        ]
    }


@app.post("/api/documents/upload")
async def upload_document_phase1(
    file: UploadFile = File(...),
    case_id: Optional[str] = None,
    access_scope: str = "private",
    current_user: UserModel = Depends(get_current_user),
):
    global SUGGESTIONS_CACHE
    SUGGESTIONS_CACHE["key"] = None
    SUGGESTIONS_CACHE["suggestions"] = None

    supported = [".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"]
    ext = Path(file.filename).suffix.lower()
    if ext not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported types: {supported}",
        )

    pipeline = get_ingestion_pipeline()
    try:
        # Strictly user-scoped
        meta = pipeline.process_document(
            file_obj=file.file,
            filename=file.filename,
            user_id=current_user.id,
            tenant_id="default_tenant",
            case_id=case_id,
            access_scope=access_scope,
        )

        # Auto-index into Personal Knowledge Base (Phase 2)
        knowledge_units_count = 0
        try:
            indexer = get_pkb_indexer()
            kus = indexer.index_document(document_id=meta.document_id, user_id=current_user.id)
            knowledge_units_count = len(kus)
            logger.info("Auto-indexed %d knowledge units for %s (user: %s)", knowledge_units_count, file.filename, current_user.id)
        except Exception as idx_err:
            logger.warning("PKB auto-indexing warning (non-fatal): %s", idx_err)

        # Vectorstore sync with user_id metadata
        try:
            doc = load_document(meta.original_file_location)
            chunks = chunk_document(doc)
            if chunks:
                build_vectorstore(chunks, visibility=access_scope, user_id=current_user.id, case_id=case_id)
        except Exception as bridge_err:
            logger.warning("Vectorstore sync warning: %s", bridge_err)

        AuditRepository().log(
            user_id=current_user.id,
            operation="DOCUMENT_UPLOAD",
            resource_type="document",
            resource_id=meta.document_id,
            result="success",
        )

        doc_info = {
            "document_id": meta.document_id,
            "filename": meta.filename,
            "file_type": meta.file_type,
            "file_size": meta.file_size,
            "checksum": meta.checksum,
            "document_type": meta.document_type.value if hasattr(meta.document_type, "value") else str(meta.document_type),
            "classification_confidence": meta.classification_confidence,
            "status": meta.status.value if hasattr(meta.status, "value") else str(meta.status),
        }
        return {
            "status": "success",
            "document_id": meta.document_id,
            "document": doc_info,
            "filename": meta.filename,
            "file_type": meta.file_type,
            "file_size": meta.file_size,
            "checksum": meta.checksum,
            "document_type": doc_info["document_type"],
            "classification_confidence": meta.classification_confidence,
            "ingestion_status": doc_info["status"],
            "knowledge_units": knowledge_units_count,
        }
    except Exception as e:
        logger.exception("Document ingestion failed for %s", file.filename)
        raise HTTPException(status_code=500, detail=f"Document ingestion failed: {str(e)}")


@app.get("/api/documents/{document_id}")
def get_document_details(
    document_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    repo = get_document_repository()
    doc = repo.get_document(document_id, user_id=current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    knowledge = repo.get_extracted_knowledge(document_id)
    return {
        "document": {
            "document_id": doc.document_id,
            "user_id": doc.user_id,
            "tenant_id": doc.tenant_id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "checksum": doc.checksum,
            "document_type": doc.document_type.value if hasattr(doc.document_type, "value") else str(doc.document_type),
            "classification_confidence": doc.classification_confidence,
            "case_id": doc.case_id,
            "access_scope": doc.access_scope,
            "status": doc.status.value if hasattr(doc.status, "value") else str(doc.status),
            "created_at": doc.created_at.isoformat(),
            "updated_at": doc.updated_at.isoformat(),
        },
        "knowledge": knowledge,
    }


@app.get("/api/documents/{document_id}/status")
def get_document_status(
    document_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    repo = get_document_repository()
    doc = repo.get_document(document_id, user_id=current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied")
    return {
        "document_id": doc.document_id,
        "status": doc.status.value if hasattr(doc.status, "value") else str(doc.status),
        "document_type": doc.document_type.value if hasattr(doc.document_type, "value") else str(doc.document_type),
        "classification_confidence": doc.classification_confidence,
        "error_message": doc.error_message,
        "updated_at": doc.updated_at.isoformat(),
    }


@app.delete("/api/documents/{document_id}")
def delete_document(
    document_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    repo = get_document_repository()
    doc = repo.get_document(document_id, user_id=current_user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    # 1. Delete physical file
    storage = get_document_storage()
    if doc.original_file_location:
        storage.delete_file(doc.original_file_location)

    # 2. Delete vectors from Chroma
    delete_document_vectors(document_id, current_user.id)

    # 3. Delete relational records
    deleted = repo.delete_document(document_id, user_id=current_user.id)

    AuditRepository().log(
        user_id=current_user.id,
        operation="DOCUMENT_DELETE",
        resource_type="document",
        resource_id=document_id,
        result="success",
    )

    return {"status": "deleted" if deleted else "failed", "document_id": document_id}


@app.delete("/api/knowledge-base")
def clear_knowledge_base(current_user: UserModel = Depends(get_current_user)):
    """Wipe user's ingested documents and associated vector embeddings."""
    global SUGGESTIONS_CACHE
    SUGGESTIONS_CACHE["key"] = None
    SUGGESTIONS_CACHE["suggestions"] = None

    repo = get_document_repository()
    storage = get_document_storage()
    user_docs = repo.list_documents(user_id=current_user.id)

    for d in user_docs:
        try:
            delete_document_vectors(d.document_id, current_user.id)
            if d.original_file_location:
                storage.delete_file(d.original_file_location)
            repo.delete_document(d.document_id, user_id=current_user.id)
        except Exception as e:
            logger.warning("Error deleting doc %s: %s", d.document_id, e)

    AuditRepository().log(
        user_id=current_user.id,
        operation="KB_CLEAR",
        resource_type="knowledge_base",
        resource_id=None,
        result="success",
    )
    return {"status": "cleared"}


@app.post("/api/documents/{document_id}/index")
def index_document_endpoint(
    document_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    indexer = get_pkb_indexer()
    try:
        kus = indexer.index_document(document_id=document_id, user_id=current_user.id)
        return {
            "status": "indexed",
            "document_id": document_id,
            "knowledge_units_created": len(kus),
        }
    except Exception as e:
        logger.exception("Indexing failed for %s: %s", document_id, e)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


# Phase 3: Hybrid Retrieval & RAG Query
class RAGQueryRequest(BaseModel):
    query: str
    tenant_id: str = "default_tenant"
    case_id: Optional[str] = None
    top_k: int = 5


@app.post("/api/rag/query")
def rag_hybrid_query(
    req: RAGQueryRequest,
    current_user: UserModel = Depends(get_current_user),
):
    retriever = get_hybrid_retriever()
    packages = retriever.retrieve(
        query=req.query,
        user_id=current_user.id,
        tenant_id=req.tenant_id,
        case_id=req.case_id,
        top_k=req.top_k,
    )

    # Format answer through grounded agent
    scope = AuthorizedScope(user_id=current_user.id, case_id=req.case_id or "")
    agent_res = run_agent(req.query, scope)

    return {
        "answer": agent_res.get("answer", ""),
        "sources": [
            {
                "document_id": p.document_id,
                "filename": p.filename,
                "section_title": p.section_title,
                "importance_score": p.importance_score,
                "hybrid_score": p.hybrid_score,
                "provenance": p.provenance,
            }
            for p in packages
        ],
        "is_fallback": agent_res.get("is_fallback", False),
    }


# Phase 4: Style Analysis & Drafting Engine
@app.post("/api/style/analyze")
def analyze_style_endpoint(current_user: UserModel = Depends(get_current_user)):
    engine = StyleEngine()
    prof = engine.analyze_user_style(user_id=current_user.id)
    return {"status": "analyzed", "profile": prof.model_dump()}


@app.get("/api/style/profile")
def get_style_profile_endpoint(current_user: UserModel = Depends(get_current_user)):
    engine = StyleEngine()
    prof = engine.get_style_profile(user_id=current_user.id)
    return {"profile": prof.model_dump()}


@app.post("/api/drafting/generate")
def generate_draft_endpoint(
    req: DraftingRequest,
    current_user: UserModel = Depends(get_current_user),
):
    agent = get_drafting_agent()
    draft = agent.generate_draft(req)
    return draft.model_dump()


# Serve static web frontend
static_dir = Path(__file__).resolve().parent.parent.parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
