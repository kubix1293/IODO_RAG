from __future__ import annotations

import json
import hashlib
import math
import uuid
from typing import TypedDict

import psycopg
import requests
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.graph import END, START, StateGraph
from psycopg.rows import dict_row

from .config import settings
from .db import application_settings, connect
from .security import anonymize
from .workflow import interpret_locally


class SupportState(TypedDict, total=False):
    ticket_id: str
    client_id: int
    program_id: int
    description: str
    answers: dict
    effective_description: str
    recognized: dict
    status: str
    step: str
    questions: list[str]
    history_candidates: list[dict]
    documentation_candidates: list[dict]
    sources: list[dict]
    proposed_answer: str


def enrich_description(description: str, answers: dict) -> str:
    context = "\n".join(f"{key}: {value}" for key, value in answers.items() if str(value).strip())
    return description + (f"\nUzupełnienia serwisanta:\n{context}" if context else "")


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def embedding(text: str):
    response = requests.post(f"{settings.embedding_url}/embed", json={"inputs": [f"query: {text}"]}, timeout=90)
    response.raise_for_status()
    return response.json()[0]


def rerank(query: str, texts: list[str]):
    if not texts:
        return []
    response = requests.post(
        f"{settings.reranker_url}/rerank",
        json={"query": query, "texts": texts, "truncate": True},
        timeout=90,
    )
    response.raise_for_status()
    scores = {int(item["index"]): float(item["score"]) for item in response.json()}
    return [scores.get(index, 0.0) for index in range(len(texts))]


def interpretation_node(state: SupportState):
    effective = enrich_description(state["description"], state.get("answers") or {})
    recognized = interpret_locally(effective)
    if recognized["missing"] and not state.get("answers"):
        return {
            "effective_description": effective,
            "recognized": recognized,
            "status": "needs_information",
            "step": "clarification",
            "questions": [f"Uzupełnij: {field}" for field in recognized["missing"]],
        }
    return {
        "effective_description": effective,
        "recognized": recognized,
        "status": "in_progress",
        "step": "db_agents",
    }


def after_interpretation(state: SupportState):
    return "stop_for_clarification" if state["status"] == "needs_information" else "dispatch_db_agents"


def dispatch_node(_: SupportState):
    return {"step": "db_agents"}


def history_agent_node(state: SupportState):
    """DB agent 1: approved historical service cases for exactly one program."""
    with connect() as conn, conn.cursor() as cur:
        runtime = application_settings(cur)
        documentation_limit = min(12, runtime["retrieval_candidates"])
        limit = max(0, runtime["retrieval_candidates"] - documentation_limit)
        cur.execute(
            """SELECT id::text id,'historical_case' kind,
              ticket_description||E'\nRozwiązanie: '||resolution chunk_text,title,
              NULL::bigint client_id,NULL::real vector_score,NULL::real text_score
              FROM support.historical_cases
              WHERE program_id=%s AND status='approved'
              ORDER BY created_at DESC LIMIT %s""",
            (state["program_id"], limit),
        )
        return {"history_candidates": [dict(row) for row in cur.fetchall()]}


def documentation_agent_node(state: SupportState):
    """DB agent 2: hybrid FTS/pgvector search with program and client visibility."""
    vector = embedding(state["effective_description"])
    with connect() as conn, conn.cursor() as cur:
        runtime = application_settings(cur)
        limit = min(12, runtime["retrieval_candidates"])
        cur.execute(
            """SELECT k.id::text id,'documentation' kind,k.chunk_text,d.title,d.client_id,
              1-(k.embedding<=>%s::vector) vector_score,
              ts_rank_cd(k.search_tsv,plainto_tsquery('simple',%s)) text_score
              FROM support.knowledge_chunks k
              JOIN support.knowledge_documents d ON d.id=k.document_id
              WHERE d.program_id=%s AND (d.scope='global' OR d.client_id=%s)
              ORDER BY GREATEST(1-(k.embedding<=>%s::vector),
                ts_rank_cd(k.search_tsv,plainto_tsquery('simple',%s))) DESC LIMIT %s""",
            (
                vector,
                state["effective_description"],
                state["program_id"],
                state["client_id"],
                vector,
                state["effective_description"],
                limit,
            ),
        )
        return {"documentation_candidates": [dict(row) for row in cur.fetchall()]}


def reranking_node(state: SupportState):
    candidates = (state.get("history_candidates") or []) + (state.get("documentation_candidates") or [])
    scores = rerank(state["effective_description"], [row["chunk_text"] for row in candidates])
    for row, score in zip(candidates, scores):
        row["rerank_score"] = score
    with connect() as conn, conn.cursor() as cur:
        top_sources = application_settings(cur)["retrieval_top_sources"]
    selected = sorted(candidates, key=lambda row: row["rerank_score"], reverse=True)[:top_sources]
    safe = json_safe([{**row, "chunk_text": anonymize(row["chunk_text"])} for row in selected])
    return {"sources": safe, "step": "answer_generation"}


def answer_node(state: SupportState):
    sources = state.get("sources") or []
    context = "\n\n".join(
        f"[{index + 1}] {row.get('kind')}: {row.get('title') or ''}\n{row['chunk_text'][:1400]}"
        for index, row in enumerate(sources)
    )
    prompt = f"""Jesteś asystentem serwisowym. Na podstawie wyłącznie źródeł zaproponuj bezpieczną diagnozę i czynności. Nie twierdź, że czynność wykonano. Jeśli źródła są niewystarczające, napisz czego brakuje. Odpowiedz po polsku, numerując kroki i wskazując numery źródeł.

ZGŁOSZENIE:
{state["effective_description"]}

ŹRÓDŁA:
{context or "Brak trafnych źródeł."}"""
    with connect() as conn, conn.cursor() as cur:
        runtime = application_settings(cur)
    response = requests.post(
        f"{settings.llm_url}/api/generate",
        json={
            "model": settings.llm_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": runtime["llm_response_tokens"]},
        },
        timeout=runtime["llm_timeout_seconds"],
    )
    response.raise_for_status()
    return {
        "proposed_answer": response.json().get("response", "").strip(),
        "status": "awaiting_problem_decision",
        "step": "problem_decision",
    }


def build_graph(checkpointer):
    graph = StateGraph(SupportState)
    graph.add_node("interpretation", interpretation_node)
    graph.add_node("dispatch_db_agents", dispatch_node)
    graph.add_node("history_agent", history_agent_node)
    graph.add_node("documentation_agent", documentation_agent_node)
    graph.add_node("reranking", reranking_node)
    graph.add_node("answer_generation", answer_node)
    graph.add_edge(START, "interpretation")
    graph.add_conditional_edges(
        "interpretation",
        after_interpretation,
        {"stop_for_clarification": END, "dispatch_db_agents": "dispatch_db_agents"},
    )
    graph.add_edge("dispatch_db_agents", "history_agent")
    graph.add_edge("dispatch_db_agents", "documentation_agent")
    graph.add_edge(["history_agent", "documentation_agent"], "reranking")
    graph.add_edge("reranking", "answer_generation")
    graph.add_edge("answer_generation", END)
    return graph.compile(checkpointer=checkpointer, name="support_db_orchestrator")


def invoke_support_graph(initial_state: SupportState):
    if not settings.checkpoint_key:
        raise RuntimeError("SUPPORT_CHECKPOINT_KEY/LANGGRAPH_AES_KEY is required")
    # Accept the existing Fernet/base64 deployment secret while always giving
    # LangGraph a valid, separate 32-byte AES key.
    aes_key = hashlib.sha256(settings.checkpoint_key.encode()).digest()
    serde = EncryptedSerializer.from_pycryptodome_aes(key=aes_key)
    with psycopg.connect(
        settings.database_url, autocommit=True, prepare_threshold=0, row_factory=dict_row
    ) as checkpoint_connection:
        saver = PostgresSaver(checkpoint_connection, serde=serde)
        saver.setup()
        graph = build_graph(saver)
        return graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": initial_state["ticket_id"]}},
        )
