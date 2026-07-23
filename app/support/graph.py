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
from .security import anonymize_with_report
from .workflow import interpret_locally


class SupportState(TypedDict, total=False):
    ticket_id: str
    client_id: int
    client_ref: str
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
    history_redactions: list[str]
    documentation_redactions: list[str]
    sources: list[dict]
    proposed_answer: str
    privacy_redactions: list[str]
    llm_provider: str
    external_llm_error: str


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
              WHERE program_id=%s AND status='approved' AND (client_id IS NULL OR client_id=%s)
              ORDER BY created_at DESC LIMIT %s""",
            (state["program_id"],state["client_id"],limit),
        )
        safe=[]; redactions=[]
        for raw in cur.fetchall():
            row=dict(raw); row["chunk_text"],found=anonymize_with_report(row["chunk_text"])
            row["title"],title_found=anonymize_with_report(row.get("title") or "")
            safe.append(row); redactions.extend(found+title_found)
        return {"history_candidates":safe,"history_redactions":redactions}


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
        safe=[]; redactions=[]
        for raw in cur.fetchall():
            row=dict(raw); row["chunk_text"],found=anonymize_with_report(row["chunk_text"])
            row["title"],title_found=anonymize_with_report(row.get("title") or "")
            safe.append(row); redactions.extend(found+title_found)
        return {"documentation_candidates":safe,"documentation_redactions":redactions}


def reranking_node(state: SupportState):
    candidates = (state.get("history_candidates") or []) + (state.get("documentation_candidates") or [])
    scores = rerank(state["effective_description"], [row["chunk_text"] for row in candidates])
    for row, score in zip(candidates, scores):
        row["rerank_score"] = score
    with connect() as conn, conn.cursor() as cur:
        top_sources = application_settings(cur)["retrieval_top_sources"]
    selected = sorted(candidates, key=lambda row: row["rerank_score"], reverse=True)[:top_sources]
    safe=[]; redactions=list(state.get("privacy_redactions") or [])
    redactions.extend(state.get("history_redactions") or [])
    redactions.extend(state.get("documentation_redactions") or [])
    for row in selected:
        chunk,found=anonymize_with_report(row["chunk_text"])
        title,title_found=anonymize_with_report(row.get("title") or "")
        redactions.extend(found+title_found)
        safe.append(json_safe({**row,"title":title,"chunk_text":chunk}))
    return {"sources":safe,"privacy_redactions":redactions,"step":"answer_generation"}


def external_llm_answer(prompt:str,runtime:dict)->str:
    if not settings.external_llm_url or not settings.external_llm_model or not settings.external_llm_api_key:
        raise RuntimeError("Zewnętrzne API LLM nie jest skonfigurowane")
    payload={"model":settings.external_llm_model,"messages":[{"role":"user","content":prompt}],
             "temperature":0.1,"max_tokens":runtime["llm_response_tokens"]}
    if settings.external_llm_reasoning_effort:
        payload["reasoning_effort"]=settings.external_llm_reasoning_effort
    response=requests.post(
        settings.external_llm_url,
        headers={"Authorization":f"Bearer {settings.external_llm_api_key}","Content-Type":"application/json"},
        json=payload,
        timeout=settings.external_llm_timeout_seconds,
    )
    response.raise_for_status()
    answer=(response.json()["choices"][0]["message"].get("content") or "").strip()
    if not answer: raise RuntimeError("Zewnętrzne API zwróciło pustą odpowiedź")
    return answer


def local_llm_answer(prompt:str,runtime:dict)->str:
    response=requests.post(
        f"{settings.llm_url}/api/generate",
        json={"model":settings.llm_model,"prompt":prompt,"stream":False,
              "options":{"temperature":0.1,"num_predict":runtime["llm_response_tokens"]}},
        timeout=runtime["llm_timeout_seconds"],
    )
    response.raise_for_status()
    return response.json().get("response","").strip()


def hybrid_llm_answer(prompt:str,runtime:dict)->tuple[str,str,str]:
    external_error=""
    if runtime["external_llm_enabled"]:
        try:
            return external_llm_answer(prompt,runtime),"external_api",""
        except Exception as exc:
            external_error=str(exc)[:300]
    answer=local_llm_answer(prompt,runtime)
    provider="ollama_fallback" if runtime["external_llm_enabled"] else "ollama_local"
    return answer,provider,external_error


def build_technical_support_prompt(state:SupportState)->str:
    sources = state.get("sources") or []
    context = "\n\n".join(
        f"MATERIAŁ {index + 1} ({row.get('kind')}):\n{row['chunk_text'][:1400]}"
        for index, row in enumerate(sources)
    )
    return f"""Jesteś starszym inżynierem wsparcia technicznego IT. Przygotuj praktyczną podpowiedź dla serwisanta rozwiązującego zgłoszenie dotyczące aplikacji lub infrastruktury.

Zasady analizy:
1. Najpierw wyodrębnij najważniejsze słowa kluczowe ze zgłoszenia: nazwy systemu, modułu, usługi, procesu, operacji, komunikaty i kody błędów, wersję oraz objaw.
2. Porównaj je z materiałami technicznymi. Najwyżej traktuj zgodność dokładnego kodu błędu, komponentu, wersji i wykonywanej operacji. Pomiń materiały dotyczące innego problemu, nawet jeśli zawierają podobne ogólne słowa.
3. Nie twórz stylu prawnego, formalnych cytowań, przypisów ani omówienia dokumentów. Nie wypisuj numerów materiałów w odpowiedzi.
4. Nie wymyślaj nazw opcji, ścieżek, poleceń ani wartości konfiguracji, których nie ma w zgłoszeniu lub materiałach.
5. Nie twierdź, że czynność została wykonana. To ma być instrukcja dla serwisanta.
6. Jeśli dopasowanie jest słabe, jasno napisz, jakich danych technicznych brakuje, zamiast zgadywać.

Wymagany format odpowiedzi:
SŁOWA KLUCZOWE
- krótka lista najważniejszych terminów

PRAWDOPODOBNA PRZYCZYNA
- konkretna diagnoza i poziom pewności: wysoki, średni albo niski

ZALECANA PROCEDURA
1. Konkretna czynność techniczna.
2. Kolejna czynność techniczna.
Przy każdym kroku podaj oczekiwany rezultat lub informację, co należy sprawdzić.

WERYFIKACJA
- jak potwierdzić usunięcie problemu

UWAGI I ESKALACJA
- ryzyko, warunek przerwania albo dane potrzebne do dalszej diagnozy

Odpowiadaj po polsku, technicznie, zwięźle i operacyjnie.

REFERENCJA KLIENTA: {state["client_ref"]}

ZGŁOSZENIE:
{state["effective_description"]}

MATERIAŁY TECHNICZNE:
{context or "Brak trafnych materiałów technicznych."}"""


def answer_node(state: SupportState):
    prompt=build_technical_support_prompt(state)
    with connect() as conn, conn.cursor() as cur:
        runtime = application_settings(cur)
    answer,provider,external_error=hybrid_llm_answer(prompt,runtime)
    return {
        "proposed_answer":answer,
        "llm_provider":provider,
        "external_llm_error":external_error,
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
