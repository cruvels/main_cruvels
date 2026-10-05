"""
Conversations API Router: Short-term conversation memory with strict user isolation.
User A can never view or manipulate User B's conversations or messages.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.auth.dependencies import get_current_user
from src.db.repositories import ConversationRepository, UserModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Conversation"


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None


class AddMessageRequest(BaseModel):
    role: str  # user, assistant, system
    content: str
    metadata: Optional[Dict[str, Any]] = None


@router.get("")
def list_conversations(
    limit: int = 50,
    current_user: UserModel = Depends(get_current_user),
):
    repo = ConversationRepository()
    convs = repo.list_conversations(user_id=current_user.id, limit=limit)
    return {"conversations": [c.model_dump() for c in convs]}


@router.post("", status_code=201)
def create_conversation(
    req: CreateConversationRequest,
    current_user: UserModel = Depends(get_current_user),
):
    repo = ConversationRepository()
    conv = repo.create_conversation(user_id=current_user.id, title=req.title or "New Conversation")
    return {"conversation": conv.model_dump()}


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    repo = ConversationRepository()
    conv = repo.get_conversation(conversation_id, user_id=current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")
    return {"conversation": conv.model_dump()}


@router.patch("/{conversation_id}")
def update_conversation(
    conversation_id: str,
    req: UpdateConversationRequest,
    current_user: UserModel = Depends(get_current_user),
):
    repo = ConversationRepository()
    updated = repo.update_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
        title=req.title,
        status=req.status,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")
    return {"conversation": updated.model_dump()}


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    repo = ConversationRepository()
    deleted = repo.delete_conversation(conversation_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")
    return {"status": "deleted", "conversation_id": conversation_id}


@router.get("/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: str,
    limit: int = 100,
    current_user: UserModel = Depends(get_current_user),
):
    repo = ConversationRepository()
    # Check conversation ownership first
    conv = repo.get_conversation(conversation_id, user_id=current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")

    messages = repo.list_messages(conversation_id=conversation_id, user_id=current_user.id, limit=limit)
    return {"messages": [m.model_dump() for m in messages]}


@router.post("/{conversation_id}/messages", status_code=201)
def add_conversation_message(
    conversation_id: str,
    req: AddMessageRequest,
    current_user: UserModel = Depends(get_current_user),
):
    repo = ConversationRepository()
    try:
        msg = repo.add_message(
            conversation_id=conversation_id,
            user_id=current_user.id,
            role=req.role,
            content=req.content,
            message_metadata=req.metadata,
        )
        return {"message": msg.model_dump()}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied: conversation does not belong to user")
