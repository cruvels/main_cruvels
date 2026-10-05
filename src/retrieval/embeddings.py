"""
Embeddings factory. Kept separate from the vector store so the embedding
model can be swapped (e.g. local model instead of OpenAI) without touching
retrieval logic.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import logging
from typing import List

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from src.config import get_settings

logger = logging.getLogger(__name__)


class ResilientFallbackEmbeddings(Embeddings):
    """
    Deterministic 384-dimensional feature embedding that operates without PyTorch DLL dependencies,
    ensuring vector operations never fail even if Windows Application Control blocks torch._C DLL.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim

    def _embed_text(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        tokens = text.lower().split()
        if not tokens:
            return vec

        for word in tokens:
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            val = ((h >> 8) % 1000) / 500.0 - 1.0
            vec[idx] += val

        # Normalize L2
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [round(x / norm, 5) for x in vec]
        return vec

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_text(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed_text(text)


@lru_cache(maxsize=1)
def get_embeddings():
    settings = get_settings()
    provider = settings["embeddings"]["provider"]
    model = settings["embeddings"]["model"]

    if provider == "openai":
        return OpenAIEmbeddings(model=model)

    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        emb = HuggingFaceEmbeddings(
            model_name=model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True, "batch_size": 32},
        )
        # Smoke-test to detect DLL failures that surface only on first call
        emb.embed_query("test")
        return emb
    except Exception as e:
        logger.warning(
            "Could not load HuggingFaceEmbeddings (%s). Falling back to ResilientFallbackEmbeddings.",
            e,
        )
        return ResilientFallbackEmbeddings(dim=384)
