"""
MemoryService: Autonomous & Explicit Long-Term Memory Extraction, Validation, and Retrieval.
Separates User Memory from Legal Knowledge.
Ensures user-scoping, deduplication, and synchronization with Chroma vector store.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage

from src.db.repositories import UserMemoryRepository, UserSettingsRepository, UserMemoryModel
from src.llm.model import get_llm
from src.retrieval.vectorstore import add_memory_vector, delete_memory_vectors

logger = logging.getLogger(__name__)


class MemoryService:
    """Manages the lifecycle of user long-term memories."""

    def __init__(self):
        self.memory_repo = UserMemoryRepository()
        self.settings_repo = UserSettingsRepository()

    def get_settings(self, user_id: str):
        return self.settings_repo.get_settings(user_id)

    def update_settings(self, user_id: str, auto_memory_enabled: Optional[bool] = None, preferred_style: Optional[str] = None):
        return self.settings_repo.update_settings(user_id, auto_memory_enabled, preferred_style)

    def list_memories(self, user_id: str, memory_type: Optional[str] = None, limit: int = 100) -> List[UserMemoryModel]:
        return self.memory_repo.list_memories(user_id, memory_type=memory_type, limit=limit)

    def get_memory(self, memory_id: str, user_id: str) -> Optional[UserMemoryModel]:
        return self.memory_repo.get_memory(memory_id, user_id)

    def create_memory(
        self,
        user_id: str,
        memory_type: str,
        memory_content: str,
        source_type: str = "explicit",
        source_id: Optional[str] = None,
        confidence: float = 1.0,
        importance: float = 0.5,
    ) -> UserMemoryModel:
        """Explicitly adds a user memory and syncs with Chroma vector memory."""
        # Deduplication check
        existing = self.memory_repo.find_equivalent_memory(user_id, memory_type, memory_content)
        if existing:
            updated = self.memory_repo.update_memory(
                memory_id=existing.id,
                user_id=user_id,
                importance=max(existing.importance, importance),
            )
            return updated or existing

        mem = self.memory_repo.create_memory(
            user_id=user_id,
            memory_type=memory_type,
            memory_content=memory_content,
            source_type=source_type,
            source_id=source_id,
            confidence=confidence,
            importance=importance,
        )

        # Sync to Chroma vector memory
        try:
            add_memory_vector(
                user_id=user_id,
                memory_id=mem.id,
                memory_content=mem.memory_content,
                memory_type=mem.memory_type,
                importance=mem.importance,
            )
        except Exception as e:
            logger.warning("Failed to sync memory vector: %s", e)

        return mem

    def update_memory(
        self,
        memory_id: str,
        user_id: str,
        memory_content: Optional[str] = None,
        importance: Optional[float] = None,
        status: Optional[str] = None,
    ) -> Optional[UserMemoryModel]:
        updated = self.memory_repo.update_memory(
            memory_id=memory_id,
            user_id=user_id,
            memory_content=memory_content,
            importance=importance,
            status=status,
        )
        if updated and memory_content:
            try:
                add_memory_vector(
                    user_id=user_id,
                    memory_id=updated.id,
                    memory_content=updated.memory_content,
                    memory_type=updated.memory_type,
                    importance=updated.importance,
                )
            except Exception as e:
                logger.warning("Failed to update memory vector: %s", e)
        return updated

    def delete_memory(self, memory_id: str, user_id: str) -> bool:
        """Deletes memory from database and Chroma vector store."""
        deleted = self.memory_repo.delete_memory(memory_id, user_id)
        if deleted:
            try:
                delete_memory_vectors(memory_id, user_id)
            except Exception as e:
                logger.warning("Failed to delete memory vector: %s", e)
        return deleted

    def clear_all_memories(self, user_id: str) -> int:
        memories = self.memory_repo.list_memories(user_id, limit=500)
        for m in memories:
            try:
                delete_memory_vectors(m.id, user_id)
            except Exception:
                pass
        return self.memory_repo.clear_all_memories(user_id)

    # ---------------------------------------------------------
    # Intelligent Memory Extraction from Conversation
    # ---------------------------------------------------------
    def extract_memories_from_conversation(
        self,
        user_id: str,
        user_message: str,
        assistant_response: str,
        conversation_id: Optional[str] = None,
    ) -> List[UserMemoryModel]:
        """
        Analyzes a conversation turn to extract useful, stable user preferences or profile facts.
        Respects user settings (auto_memory_enabled).
        Never treats document-derived legal facts as user memories.
        """
        settings = self.get_settings(user_id)
        if not settings.auto_memory_enabled:
            logger.info("Auto-memory is disabled for user %s. Skipping extraction.", user_id)
            return []

        # Heuristic pre-filter: user statement must contain indicator of preference/profile
        indicators = [
            "i prefer", "i like", "always", "never", "my role", "i am a", "we operate",
            "my jurisdiction", "my company", "my client", "draft in", "format as", "style",
            "i practice", "keep answers", "concise", "formal"
        ]
        text_lower = user_message.lower()
        if not any(ind in text_lower for ind in indicators):
            return []

        prompt = (
            "You are an AI memory analyzer for a Legal AI platform.\n"
            "Analyze the user's message and determine if they stated a stable preference, professional role, writing style, or workflow preference that should be remembered for future interactions.\n"
            "CRITICAL RULES:\n"
            "1. User Memory is NOT Legal Knowledge. Do NOT extract contract clauses, statutory terms, or case facts as user memories.\n"
            "2. Only extract clear, user-centric preferences (e.g. 'Prefers brief bullet-point summaries', 'Practices corporate law in California').\n"
            "3. If nothing stable or useful is mentioned, return an empty array [].\n"
            "4. Return ONLY a valid JSON array of objects with structure:\n"
            "[\n"
            '  {"memory_type": "PREFERENCE|WRITING_STYLE|PROFILE|WORKFLOW|CONTEXT", "memory_content": "Concise statement", "importance": 0.1-1.0, "confidence": 0.8-1.0}\n'
            "]"
        )

        extracted_models = []
        try:
            llm = get_llm()
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=f"User message: {user_message}\nAssistant response: {assistant_response[:300]}"),
            ]
            res = llm.invoke(messages)
            content = res.content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)

            data = json.loads(content)
            if isinstance(data, list):
                for item in data:
                    m_type = item.get("memory_type", "PREFERENCE").upper()
                    m_content = item.get("memory_content", "").strip()
                    imp = float(item.get("importance", 0.5))
                    conf = float(item.get("confidence", 0.9))

                    if m_content and len(m_content) >= 5 and conf >= 0.7:
                        mem = self.create_memory(
                            user_id=user_id,
                            memory_type=m_type,
                            memory_content=m_content,
                            source_type="conversation",
                            source_id=conversation_id,
                            confidence=conf,
                            importance=imp,
                        )
                        extracted_models.append(mem)
        except Exception as e:
            logger.warning("Memory extraction parsing notice: %s", e)

        return extracted_models

    # ---------------------------------------------------------
    # Memory Retrieval & AI Context Assembly
    # ---------------------------------------------------------
    def retrieve_relevant_memories(self, user_id: str, query: str, limit: int = 5) -> List[UserMemoryModel]:
        """
        Retrieves top relevant memories for the authenticated user based on importance and recency.
        Strictly user-scoped.
        """
        all_mems = self.memory_repo.list_memories(user_id=user_id, limit=50)
        if not all_mems:
            return []

        q_lower = query.lower()
        # Score memories by keyword match + importance
        scored = []
        for m in all_mems:
            words = [w for w in re.findall(r"\b\w{3,}\b", m.memory_content.lower())]
            overlap = sum(1 for w in words if w in q_lower)
            relevance = (overlap / max(len(words), 1)) * 0.4
            score = relevance + (m.importance * 0.4) + (m.confidence * 0.2)
            scored.append((score, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def format_memory_context(self, memories: List[UserMemoryModel]) -> str:
        """Formats retrieved memories for safe injection into LLM system prompt."""
        if not memories:
            return ""

        lines = ["\n[USER PREFERENCES & STABLE AI MEMORY]"]
        lines.append("(Note: User preferences guide tone, drafting style, and focus, but do NOT override verifiable document evidence or system security rules.)")
        for m in memories:
            lines.append(f"• [{m.memory_type}]: {m.memory_content}")
        return "\n".join(lines)


_MEMORY_SERVICE = MemoryService()


def get_memory_service() -> MemoryService:
    global _MEMORY_SERVICE
    return _MEMORY_SERVICE
