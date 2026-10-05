"""
LLM interface layer. Keeps model choice/provider isolated from agent and
retrieval logic so swapping models or providers never touches those layers.

Provider "moonshot" targets Kimi K2.5 -- the finalized reasoning/agent
candidate from Model_Verification_and_Evaluation_Final_Report (HIGH
PRIORITY: verified spec sheet, native multimodal + agentic reasoning,
fits legal RAG/drafting/document-understanding workloads). Moonshot's API
is OpenAI-compatible, so this reuses ChatOpenAI with a custom base_url
instead of a separate client.
"""
from __future__ import annotations

import os
from functools import lru_cache

from langchain_openai import ChatOpenAI

from src.config import get_settings

MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@lru_cache(maxsize=1)
def get_llm():
    settings = get_settings()
    provider = settings["llm"]["provider"]

    if provider == "openai":
        return ChatOpenAI(
            model=settings["llm"]["model"],
            temperature=settings["llm"]["temperature"],
            max_tokens=settings["llm"]["max_tokens"],
        )

    if provider == "moonshot":
        api_key = os.getenv("MOONSHOT_API_KEY")
        if not api_key:
            raise RuntimeError(
                "MOONSHOT_API_KEY is not set. Get a key from platform.moonshot.ai "
                "and add it to .env before using provider: moonshot."
            )
        return ChatOpenAI(
            model=settings["llm"]["model"],
            temperature=settings["llm"]["temperature"],
            max_tokens=settings["llm"]["max_tokens"],
            base_url=MOONSHOT_BASE_URL,
            api_key=api_key,
        )

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("MOONSHOT_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Add OPENROUTER_API_KEY to .env."
            )
        # Cap max_tokens safely to 512 or configured setting to fit account credit allocation
        tokens = min(int(settings["llm"].get("max_tokens", 512)), 512)
        return ChatOpenAI(
            model=settings["llm"]["model"],
            temperature=settings["llm"]["temperature"],
            max_tokens=tokens,
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
            timeout=12.0,
            max_retries=1,
            default_headers={
                "HTTP-Referer": "http://localhost:8080",
                "X-Title": "Cruvels AI Legal Assistant",
            },
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")
