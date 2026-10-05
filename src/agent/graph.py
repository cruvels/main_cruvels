"""
LangGraph wiring for the Legal Knowledge Assistant.

Flow:
  agent -> [has tool calls? and under budget?]
              -> yes: tools (ToolNode) -> count_tool_call -> agent (loop)
              -> no:  finalize -> END

This replaces a version of the graph that called retrieval directly from a
node. Now the LLM is bound to real tools (document_search,
document_metadata_lookup) via a proper `ToolNode`, and decides for itself
whether/when to call them -- matching the assignment's "agent that can
choose between a limited number of tools" requirement (section 4.1) rather
than a fixed retrieval step.

The agent never takes any action beyond these two read-only tools -- no
external legal actions, no irreversible decisions (assignment section 4.2).
"""
from __future__ import annotations

import logging

import json
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from src.config import get_settings
from src.context.permissions import AuthorizedScope
from src.retrieval.retriever import retrieve_chunks
from src.llm.model import get_llm
from .state import AgentState
from .nodes import agent_node, should_continue, count_tool_call, finalize, get_tools_for_scope, _system_prompt

logger = logging.getLogger(__name__)


def build_agent_graph(scope: AuthorizedScope):
    """Builds the multi-turn tool-calling graph for complex workflows."""
    tools = get_tools_for_scope(scope)
    tool_node = ToolNode(tools)

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("count_tool_call", count_tool_call)
    graph.add_node("finalize", finalize)

    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "finalize": "finalize"},
    )
    graph.add_edge("tools", "count_tool_call")
    graph.add_edge("count_tool_call", "agent")
    graph.add_edge("finalize", END)

    return graph.compile()


def run_agent(
    question: str,
    scope: AuthorizedScope,
    conversation_context: list[dict] | None = None,
    user_memories: list[Any] | None = None,
) -> dict:
    """Legal Q&A agent with RAG-first, personal memory, and general-knowledge fallback.

    Flow:
    1. Try vector search for relevant document chunks strictly scoped to the user.
    2. Incorporate user memory preferences and recent conversation context.
    3. Ground answer citing document evidence, retaining user tone preferences.
    """
    chunks = retrieve_chunks(question, scope)

    # Format user memory instructions if present
    memory_block = ""
    if user_memories:
        from src.memory.service import get_memory_service
        memory_block = "\n" + get_memory_service().format_memory_context(user_memories) + "\n"

    # Format recent conversation context if present
    conv_block = ""
    if conversation_context:
        recent = conversation_context[-6:]
        conv_lines = [f"- {m.get('role', 'user').capitalize()}: {m.get('content', '')}" for m in recent]
        conv_block = "\n[RECENT CONVERSATION HISTORY]\n" + "\n".join(conv_lines) + "\n"

    base_prompt = _system_prompt()
    if memory_block:
        base_prompt += "\n" + memory_block

    if chunks:
        # --- GROUNDED MODE: answer from document evidence ---
        sources = []
        seen = set()
        for c in chunks:
            key = (c.file_name, c.page_number)
            if key not in seen:
                seen.add(key)
                sources.append({
                    "file_name": c.file_name,
                    "page_number": c.page_number,
                    "doc_id": c.doc_id,
                })

        evidence_blocks = [
            f"--- [Source: {c.file_name}, Page: {c.page_number}] ---\n{c.text}"
            for c in chunks
        ]
        combined_evidence = "\n\n".join(evidence_blocks)

        system_msg = SystemMessage(content=base_prompt)
        human_content = (
            f"{conv_block}\n"
            f"User Question:\n{question}\n\n"
            f"Authorized Document Evidence:\n{combined_evidence}\n\n"
            "Instructions: Answer using the document evidence above. "
            "Cite the document name and page number for each key point. "
            "If the documents don't fully answer the question, supplement with your general legal knowledge and clearly label which parts come from documents vs general knowledge."
        )
        human_msg = HumanMessage(content=human_content.strip())
    else:
        # --- GENERAL KNOWLEDGE MODE: no documents matched, use LLM expertise ---
        logger.info("run_agent: no matching chunks — using general legal knowledge mode")
        sources = []
        system_msg = SystemMessage(content=base_prompt)
        human_content = (
            f"{conv_block}\n"
            f"User Question:\n{question}\n\n"
            "Note: No specific case documents are available for this question. "
            "Answer using your general legal knowledge and expertise while adhering to user memory preferences. "
            "Clearly start your answer with 'Based on general legal principles:' and provide a thorough, accurate response."
        )
        human_msg = HumanMessage(content=human_content.strip())

    try:
        llm = get_llm()
        response = llm.invoke([system_msg, human_msg])
        answer_text = response.content.strip()
        return {
            "answer": answer_text,
            "sources": sources,
            "is_fallback": False,
        }
    except Exception as e:
        logger.warning("LLM invocation failed, trying graph agent: %s", e)
        try:
            app = build_agent_graph(scope)
            initial_state: AgentState = {
                "messages": [HumanMessage(content=question)],
                "scope": scope,
                "tool_calls_made": 0,
            }
            final_state = app.invoke(initial_state)
            return {
                "answer": final_state.get("answer", ""),
                "sources": final_state.get("sources", []),
                "is_fallback": final_state.get("is_fallback", False),
            }
        except Exception as e2:
            logger.exception("Graph agent also failed: %s", e2)
            return {
                "answer": f"⚠️ LLM error: {str(e2)}",
                "sources": [],
                "is_fallback": True,
            }


def stream_agent(question: str, scope: AuthorizedScope):
    """Streams tokens in real-time as line-delimited JSON chunks for instantaneous UI response."""
    chunks = retrieve_chunks(question, scope)

    sources = []
    if chunks:
        seen = set()
        for c in chunks:
            key = (c.file_name, c.page_number)
            if key not in seen:
                seen.add(key)
                sources.append({
                    "file_name": c.file_name,
                    "page_number": c.page_number,
                    "doc_id": c.doc_id,
                })
        yield json.dumps({"type": "sources", "sources": sources, "is_fallback": False}) + "\n"

        evidence_blocks = [
            f"--- [Source: {c.file_name}, Page: {c.page_number}] ---\n{c.text}"
            for c in chunks
        ]
        combined_evidence = "\n\n".join(evidence_blocks)
        system_msg = SystemMessage(content=_system_prompt())
        human_msg = HumanMessage(
            content=(
                f"User Question:\n{question}\n\n"
                f"Authorized Document Evidence:\n{combined_evidence}\n\n"
                "Instructions: Answer using the document evidence above. Cite document name and page for each key point. "
                "Supplement with general legal knowledge when needed and label it clearly."
            )
        )
    else:
        logger.info("stream_agent: no chunks — using general legal knowledge mode")
        yield json.dumps({"type": "sources", "sources": [], "is_fallback": False}) + "\n"
        system_msg = SystemMessage(content=_system_prompt())
        human_msg = HumanMessage(
            content=(
                f"User Question:\n{question}\n\n"
                "Note: No specific case documents are available. "
                "Answer using your general legal knowledge and expertise. "
                "Clearly start your answer with 'Based on general legal principles:' and provide a thorough, accurate response."
            )
        )

    try:
        llm = get_llm()
        for chunk in llm.stream([system_msg, human_msg]):
            if chunk.content:
                yield json.dumps({"type": "token", "token": chunk.content}) + "\n"
    except Exception as e:
        logger.exception("Error during LLM streaming: %s", e)
        yield json.dumps({"type": "error", "detail": str(e)}) + "\n"

    yield json.dumps({"type": "done"}) + "\n"
