"""
Memory API Router: Individual Long-term memory management, settings, and vector synchronization.
"""
from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.auth.dependencies import get_current_user
from src.db.repositories import UserModel
from src.memory.service import get_memory_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["Memory"])


class CreateMemoryRequest(BaseModel):
    memory_type: str  # PROFILE, PREFERENCE, WRITING_STYLE, WORKFLOW, CONTEXT
    memory_content: str
    importance: Optional[float] = 0.5
    confidence: Optional[float] = 1.0


class UpdateMemoryRequest(BaseModel):
    memory_content: Optional[str] = None
    importance: Optional[float] = None
    status: Optional[str] = None


class UpdateMemorySettingsRequest(BaseModel):
    auto_memory_enabled: Optional[bool] = None
    preferred_style: Optional[str] = None


@router.get("")
def list_memories(
    memory_type: Optional[str] = Query(None),
    limit: int = 100,
    current_user: UserModel = Depends(get_current_user),
):
    service = get_memory_service()
    memories = service.list_memories(user_id=current_user.id, memory_type=memory_type, limit=limit)
    return {"memories": [m.model_dump() for m in memories]}


@router.post("", status_code=201)
def create_memory(
    req: CreateMemoryRequest,
    current_user: UserModel = Depends(get_current_user),
):
    service = get_memory_service()
    mem = service.create_memory(
        user_id=current_user.id,
        memory_type=req.memory_type,
        memory_content=req.memory_content,
        source_type="explicit",
        confidence=req.confidence or 1.0,
        importance=req.importance or 0.5,
    )
    return {"memory": mem.model_dump()}


@router.get("/settings")
def get_memory_settings(current_user: UserModel = Depends(get_current_user)):
    service = get_memory_service()
    settings = service.get_settings(current_user.id)
    return {"settings": settings.model_dump()}


@router.patch("/settings")
def update_memory_settings(
    req: UpdateMemorySettingsRequest,
    current_user: UserModel = Depends(get_current_user),
):
    service = get_memory_service()
    updated = service.update_settings(
        user_id=current_user.id,
        auto_memory_enabled=req.auto_memory_enabled,
        preferred_style=req.preferred_style,
    )
    return {"settings": updated.model_dump()}


@router.get("/{memory_id}")
def get_memory(
    memory_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    service = get_memory_service()
    mem = service.get_memory(memory_id, user_id=current_user.id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found or access denied")
    return {"memory": mem.model_dump()}


@router.patch("/{memory_id}")
def update_memory(
    memory_id: str,
    req: UpdateMemoryRequest,
    current_user: UserModel = Depends(get_current_user),
):
    service = get_memory_service()
    updated = service.update_memory(
        memory_id=memory_id,
        user_id=current_user.id,
        memory_content=req.memory_content,
        importance=req.importance,
        status=req.status,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found or access denied")
    return {"memory": updated.model_dump()}


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    service = get_memory_service()
    deleted = service.delete_memory(memory_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found or access denied")
    return {"status": "deleted", "memory_id": memory_id}


@router.delete("")
def clear_all_memories(current_user: UserModel = Depends(get_current_user)):
    service = get_memory_service()
    count = service.clear_all_memories(user_id=current_user.id)
    return {"status": "cleared", "count": count}
