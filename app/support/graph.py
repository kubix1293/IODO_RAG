from __future__ import annotations

import base64
import json
import hashlib
import math
import re
import uuid
from pathlib import Path
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


LLM_CONTEXT_MAX_CHARS = 24_000


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


def lexical_rerank(query:str,texts:list[str])->list[float]:
    query_tokens=set(re.findall(r"[\w.-]{2,}",query.lower()))
    if not query_tokens:
        return [0.0 for _ in texts]
    codes={token for token in query_tokens if any(char.isdigit() for char in token)}
    scores=[]
    for text in texts:
        text_tokens=set(re.findall(r"[\w.-]{2,}",text.lower()))
        overlap=len(query_tokens & text_tokens)/len(query_tokens)
        code_matches=len(codes & text_tokens)
        scores.append(min(1.0,overlap+(0.25*code_matches)))
    return scores


def rerank(query: str, texts: list[str]):
    if not texts:
        return []
    try:
        response = requests.post(
            f"{settings.reranker_url}/rerank",
            json={"query": query, "texts": texts, "truncate": True},
            timeout=30,
        )
        response.raise_for_status()
        scores = {int(item["index"]): float(item["score"]) for item in response.json()}
        return [scores.get(index, 0.0) for index in range(len(texts))]
    except requests.RequestException:
        return lexical_rerank(query,texts)


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
            """SELECT id,kind,solution_id,chunk_text,title,client_id,
              NULL::real vector_score,NULL::real text_score FROM (
                SELECT id::text id,'historical_case' kind,solution_id,
                  ticket_description||E'\nRozwiązanie: '||resolution chunk_text,title,
                  client_id,created_at
                FROM support.historical_cases
                WHERE program_id=%s AND status='approved' AND (client_id IS NULL OR client_id=%s)
                UNION ALL
                SELECT 'solution-'||s.id::text id,'approved_solution' kind,s.id solution_id,
                  p.normalized_description||E'\nRozwiązanie: '||s.summary||
                  COALESCE(E'\nKroki:\n'||string_agg(ss.position||'. '||ss.instruction,E'\n' ORDER BY ss.position),'') chunk_text,
                  s.title,s.client_id,s.created_at
                FROM support.solutions s
                JOIN support.canonical_problems p ON p.id=s.problem_id
                LEFT JOIN support.solution_steps ss ON ss.solution_id=s.id
                WHERE p.program_id=%s AND s.status='approved'
                  AND (s.client_id IS NULL OR s.client_id=%s)
                GROUP BY s.id,p.normalized_description
              ) knowledge ORDER BY created_at DESC LIMIT %s""",
            (state["program_id"],state["client_id"],state["program_id"],state["client_id"],limit),
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
            """SELECT k.id::text id,'documentation' kind,k.document_id,k.chunk_index,
              k.chunk_text,COALESCE(k.metadata->>'title',d.title) title,d.client_id,
              1-(k.embedding<=>%s::vector) vector_score,
              ts_rank_cd(k.search_tsv,plainto_tsquery('simple',%s)) text_score
              FROM support.knowledge_chunks k
              JOIN support.knowledge_documents d ON d.id=k.document_id
              WHERE d.status='indexed' AND d.program_id=%s AND (d.scope='global' OR d.client_id=%s)
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


def expand_documentation_neighbors(selected:list[dict],state:SupportState,cur)->list[dict]:
    """Add the preceding and following chunks without crossing visibility boundaries."""
    expanded=[]; included=set()
    for row in selected:
        if row.get("kind") != "documentation" or row.get("document_id") is None:
            key=(row.get("kind"),str(row.get("id")))
            if key not in included:
                expanded.append(row); included.add(key)
            continue
        cur.execute(
            """SELECT k.id::text id,'documentation' kind,k.document_id,k.chunk_index,
              k.chunk_text,COALESCE(k.metadata->>'title',d.title) title,d.client_id,NULL::real vector_score,NULL::real text_score
              FROM support.knowledge_chunks k
              JOIN support.knowledge_documents d ON d.id=k.document_id
              WHERE k.document_id=%s AND k.chunk_index BETWEEN %s AND %s
                AND d.status='indexed' AND d.program_id=%s AND (d.scope='global' OR d.client_id=%s)
              ORDER BY k.chunk_index""",
            (
                row["document_id"],
                max(0,int(row["chunk_index"])-1),
                int(row["chunk_index"])+1,
                state["program_id"],
                state["client_id"],
            ),
        )
        neighbors={int(item["chunk_index"]):dict(item) for item in cur.fetchall()}
        neighbors[int(row["chunk_index"])]=row
        for chunk_index in sorted(neighbors):
            item=neighbors[chunk_index]
            key=("documentation",str(item["id"]))
            if key in included:
                continue
            item["context_role"]="match" if chunk_index==int(row["chunk_index"]) else "neighbor"
            item["rerank_score"]=row.get("rerank_score")
            expanded.append(item); included.add(key)
    return expanded


def reranking_node(state: SupportState):
    candidates = (state.get("history_candidates") or []) + (state.get("documentation_candidates") or [])
    scores = rerank(state["effective_description"], [row["chunk_text"] for row in candidates])
    for row, score in zip(candidates, scores):
        row["rerank_score"] = score
    with connect() as conn, conn.cursor() as cur:
        top_sources = application_settings(cur)["retrieval_top_sources"]
        selected = sorted(candidates, key=lambda row: row["rerank_score"], reverse=True)[:top_sources]
        selected = expand_documentation_neighbors(selected,state,cur)
    safe=[]; redactions=list(state.get("privacy_redactions") or [])
    redactions.extend(state.get("history_redactions") or [])
    redactions.extend(state.get("documentation_redactions") or [])
    for row in selected:
        chunk,found=anonymize_with_report(row["chunk_text"])
        title,title_found=anonymize_with_report(row.get("title") or "")
        redactions.extend(found+title_found)
        safe.append(json_safe({**row,"title":title,"chunk_text":chunk}))
    return {"sources":safe,"privacy_redactions":redactions,"step":"answer_generation"}


def external_llm_answer(prompt:str,runtime:dict,images:list[dict]|None=None)->str:
    if not settings.external_llm_url or not settings.external_llm_model or not settings.external_llm_api_key:
        raise RuntimeError("Zewnętrzne API LLM nie jest skonfigurowane")
    content: str|list[dict] = prompt
    if images:
        content=[{"type":"text","text":prompt}]
        content.extend({"type":"image_url","image_url":{"url":image["data_url"]}} for image in images)
    payload={"model":settings.external_llm_model,"messages":[{"role":"user","content":content}],
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


def plain_text_response(answer:str)->str:
    answer=answer.replace("**","").replace("__","")
    answer=re.sub(r"(?m)^\s*#{1,6}\s*","",answer)
    answer=re.sub(r"(?m)^(\s*)\*\s+",r"\1- ",answer)
    return answer.replace("*","").strip()


def hybrid_llm_answer(prompt:str,runtime:dict,images:list[dict]|None=None)->tuple[str,str,str]:
    external_error=""
    if runtime["external_llm_enabled"]:
        try:
            answer=external_llm_answer(prompt,runtime,images) if images else external_llm_answer(prompt,runtime)
            return plain_text_response(answer),"external_api",""
        except Exception as exc:
            external_error=str(exc)[:300]
    answer=plain_text_response(local_llm_answer(prompt,runtime))
    provider="ollama_fallback" if runtime["external_llm_enabled"] else "ollama_local"
    return answer,provider,external_error


def approved_ticket_images(ticket_id:str|uuid.UUID)->list[dict]:
    """Load only screenshots explicitly approved by an administrator for AI."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id,storage_path,mime_type,original_name FROM support.ticket_images
          WHERE ticket_id=%s AND purpose='problem' AND ai_approved_at IS NOT NULL
          ORDER BY uploaded_at LIMIT 4""",(ticket_id,))
        rows=cur.fetchall()
    root=(Path(settings.upload_root)/"ticket-images").resolve()
    result=[]
    for row in rows:
        path=Path(row["storage_path"]).resolve()
        if root not in path.parents or not path.is_file():
            continue
        encoded=base64.b64encode(path.read_bytes()).decode("ascii")
        result.append({"id":str(row["id"]),"name":row["original_name"],
                       "origin":"current_ticket","purpose":"problem",
                       "data_url":f"data:{row['mime_type']};base64,{encoded}"})
    return result


def historical_case_ids_from_sources(sources:list[dict])->list[str]:
    """Keep matched historical cases in reranked order without duplicates."""
    result=[]
    for source in sources or []:
        if source.get("kind")!="historical_case":
            continue
        try:
            case_id=str(uuid.UUID(str(source.get("id"))))
        except (TypeError,ValueError,AttributeError):
            continue
        if case_id not in result:
            result.append(case_id)
    return result


def approved_analysis_images(state:SupportState,limit:int=4)->list[dict]:
    """Current ticket screenshots first, then approved images of matched cases."""
    result=approved_ticket_images(state["ticket_id"])[:limit]
    case_ids=historical_case_ids_from_sources(state.get("sources") or [])
    if len(result)>=limit or not case_ids:
        return result
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id,case_id,purpose,storage_path,mime_type,original_name
          FROM support.historical_case_images
          WHERE case_id=ANY(%s::uuid[]) AND ai_approved_at IS NOT NULL
          ORDER BY array_position(%s::uuid[],case_id),uploaded_at""",(case_ids,case_ids))
        rows=cur.fetchall()
    root=(Path(settings.upload_root)/"case-images").resolve()
    for row in rows:
        if len(result)>=limit:
            break
        path=Path(row["storage_path"]).resolve()
        if root not in path.parents or not path.is_file():
            continue
        encoded=base64.b64encode(path.read_bytes()).decode("ascii")
        result.append({
            "id":str(row["id"]),"name":row["original_name"],
            "origin":"historical_case","purpose":row["purpose"],
            "case_id":str(row["case_id"]),
            "data_url":f"data:{row['mime_type']};base64,{encoded}",
        })
    return result


def build_technical_support_prompt(state:SupportState)->str:
    sources = state.get("sources") or []
    blocks=[]; used_chars=0
    for index,row in enumerate(sources):
        title=(row.get("title") or "bez tytułu").strip()
        role="fragment sąsiedni procedury" if row.get("context_role")=="neighbor" else "trafienie"
        header=f"MATERIAŁ {index + 1} ({row.get('kind')}, {role})\nTYTUŁ: {title}\n"
        remaining=LLM_CONTEXT_MAX_CHARS-used_chars-len(header)
        if remaining <= 0:
            break
        text=(row.get("chunk_text") or "").strip()
        block=header+text[:remaining]
        blocks.append(block)
        used_chars+=len(block)+2
    context="\n\n".join(blocks)
    return f"""Jesteś starszym inżynierem wsparcia technicznego IT. Przygotuj praktyczną podpowiedź dla serwisanta rozwiązującego zgłoszenie dotyczące aplikacji lub infrastruktury.

Najpierw rozróżnij rodzaj zgłoszenia:
- PROBLEM: treść jasno opisuje błąd, awarię, niedziałanie, blokadę, niepoprawny rezultat, komunikat błędu albo brak możliwości wykonania czynności.
- ZADANIE: treść nazywa czynność do wykonania, np. aktualizację, konfigurację, instalację, import lub przygotowanie danych, ale nie opisuje niedziałania.
- Nie wymyślaj problemu ani awarii, jeśli zgłoszenie ich nie zawiera. Klasyfikacja wstępna aplikacji: {(state.get("recognized") or {}).get("issue_kind","nieustalona")}.

Zasady analizy:
1. Najpierw wyodrębnij najważniejsze słowa kluczowe ze zgłoszenia: nazwy systemu, modułu, usługi, procesu, operacji, komunikaty i kody błędów, wersję oraz objaw.
2. Porównaj je z materiałami technicznymi. Najwyżej traktuj zgodność dokładnego kodu błędu, komponentu, wersji i wykonywanej operacji. Pomiń materiały dotyczące innego problemu, nawet jeśli zawierają podobne ogólne słowa.
3. Nie twórz stylu prawnego, formalnych cytowań, przypisów ani omówienia dokumentów. Nie wypisuj numerów materiałów w odpowiedzi.
4. Nie wymyślaj nazw opcji, ścieżek, poleceń ani wartości konfiguracji, których nie ma w zgłoszeniu lub materiałach.
5. Nie twierdź, że czynność została wykonana. To ma być instrukcja dla serwisanta.
6. Jeśli dopasowanie jest słabe, jasno napisz, jakich danych technicznych brakuje, zamiast zgadywać.

Sposób odpowiedzi dla PROBLEMU:
Najpierw wyjaśnij serwisantowi w kilku naturalnych zdaniach, jak rozumiesz problem i jaka jest najbardziej prawdopodobna przyczyna. Następnie przeprowadź go przez rozwiązanie, używając kolejnych numerowanych kroków: 1., 2., 3. Każdy krok wyjaśnij prostym językiem technicznym: co zrobić, dlaczego oraz jaki wynik powinien się pojawić. Na końcu opisz, jak zweryfikować rezultat i kiedy przerwać działania lub eskalować problem.

Sposób odpowiedzi dla ZADANIA:
Nie diagnozuj przyczyny i nie nazywaj czynności problemem. Odpowiedz krótko, zaczynając od „W ramach tego zadania pamiętaj o:”, a następnie wymień tylko najważniejsze praktyczne punkty wynikające z odnalezionej wiedzy. Jeśli materiał mówi, że podobna czynność była wcześniej wykonywana u tego klienta, zaznacz krótko „U tego klienta wcześniej zwrócono uwagę na:”, ale nie ujawniaj danych innych klientów. Nie twórz rozbudowanej procedury. Ostatnie zdanie musi brzmieć dokładnie: „W celu uzyskania szczegółowych informacji przejdź do zakładki Konsultacja AI.”

Nie używaj składni Markdown. Nie stosuj gwiazdek, podwójnych gwiazdek, znaków #, tabel ani sztucznych formalnych nagłówków. Odpowiedź ma brzmieć jak rzeczowa rozmowa doświadczonego serwisanta z drugim serwisantem.

REFERENCJA KLIENTA: {state["client_ref"]}

ZGŁOSZENIE:
{state["effective_description"]}

MATERIAŁY TECHNICZNE:
{context or "Brak trafnych materiałów technicznych."}"""


def answer_node(state: SupportState):
    prompt=build_technical_support_prompt(state)
    with connect() as conn, conn.cursor() as cur:
        runtime = application_settings(cur)
    images=approved_analysis_images(state)
    if images:
        current_count=sum(image.get("origin")=="current_ticket" for image in images)
        historical_count=sum(image.get("origin")=="historical_case" for image in images)
        prompt+=f"""\n\nZATWIERDZONE ZRZUTY EKRANU:
Administrator potwierdził anonimizację wszystkich przekazanych obrazów.
Pierwsze obrazy bieżącego zgłoszenia: {current_count}. Obrazy odnalezionych przypadków historycznych: {historical_count}.
Obrazy bieżącego zgłoszenia pokazują obecny stan. Obrazy historyczne są wyłącznie przykładami objawu albo wykonania rozwiązania z odnalezionego przypadku; nie twierdź, że pokazują bieżące zgłoszenie.
Odczytaj komunikaty, moduł, pola i stan interfejsu. Nie próbuj identyfikować osób. Jeśli obraz jest nieczytelny, zaznacz to zamiast zgadywać."""
    answer,provider,external_error=hybrid_llm_answer(prompt,runtime,images=images)
    return {
        "proposed_answer":answer,
        "llm_provider":provider,
        "external_llm_error":external_error,
        "analyzed_image_ids":[image["id"] for image in images] if provider=="external_api" else [],
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
