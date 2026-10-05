"""
User Profile API Router: Profile inspection, update, and complete account deletion with cascade.
"""
from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.auth.dependencies import get_current_user
from src.db.repositories import UserModel, UserRepository, UserSettingsRepository
from src.memory.service import get_memory_service
from src.retrieval.vectorstore import delete_document_vectors

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["Users"])


class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_image: Optional[str] = None


@router.get("/me")
def get_user_profile(current_user: UserModel = Depends(get_current_user)):
    settings_repo = UserSettingsRepository()
    settings = settings_repo.get_settings(current_user.id)
    return {
        "user": current_user.model_dump(),
        "settings": settings.model_dump(),
    }


@router.patch("/me")
def update_user_profile(
    req: ProfileUpdateRequest,
    current_user: UserModel = Depends(get_current_user),
):
    repo = UserRepository()
    updated = repo.update_profile(
        user_id=current_user.id,
        first_name=req.first_name,
        last_name=req.last_name,
        profile_image=req.profile_image,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": updated.model_dump()}


@router.delete("/me")
def delete_user_account(current_user: UserModel = Depends(get_current_user)):
    """
    Deletes user account, cascading to:
    - User profile and settings
    - All conversations & messages
    - All long-term memories
    - All personal documents and knowledge units
    - All vectorstore embeddings (Chroma)
    """
    # 1. Clean up user memories from Chroma
    memory_service = get_memory_service()
    memory_service.clear_all_memories(current_user.id)

    # 2. Clean up documents and vectors
    from src.ingestion.repository import get_document_repository
    from src.ingestion.storage import get_document_storage

    doc_repo = get_document_repository()
    storage = get_document_storage()
    user_docs = doc_repo.list_documents(user_id=current_user.id)
    for d in user_docs:
        try:
            delete_document_vectors(d.document_id, current_user.id)
            if d.original_file_location:
                storage.delete_file(d.original_file_location)
        except Exception as e:
            logger.warning("Error deleting doc files/vectors during account purge: %s", e)

    # 3. Delete from database (cascades to all relational tables)
    repo = UserRepository()
    repo.delete_user(current_user.id)

    return {"status": "deleted", "message": "Account and all associated personal data have been completely purged."}
