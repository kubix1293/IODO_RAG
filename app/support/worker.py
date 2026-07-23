from __future__ import annotations
import json, math, os, socket, time, uuid
import requests
from .checkpoints import encrypt
from .config import settings
from .db import application_settings, connect
from .ranking import compatibility, effectiveness, total
from .security import anonymize
from .workflow import interpret_locally

WORKER=f"{socket.gethostname()}:{os.getpid()}"

def enrich_description(description:str,answers:dict)->str:
    context="\n".join(f"{key}: {value}" for key,value in answers.items() if str(value).strip())
    return description+(f"\nUzupełnienia serwisanta:\n{context}" if context else "")

def json_safe(value):
    if isinstance(value,float) and not math.isfinite(value): return None
    if isinstance(value,uuid.UUID): return str(value)
    if isinstance(value,dict): return {key:json_safe(item) for key,item in value.items()}
    if isinstance(value,list): return [json_safe(item) for item in value]
    return value

def claim():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT * FROM support.support_jobs WHERE status IN ('queued','failed_retryable') AND available_at<=now() ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"""); job=cur.fetchone()
        if job:
            cur.execute("UPDATE support.support_jobs SET status='running',locked_at=now(),locked_by=%s,attempts=attempts+1,last_error=NULL,updated_at=now() WHERE id=%s",(WORKER,job["id"]))
            cur.execute("UPDATE support.tickets SET status='in_progress',updated_at=now() WHERE id=%s",(job["ticket_id"],))
        return dict(job) if job else None

def embedding(text:str):
    response=requests.post(f"{settings.embedding_url}/embed",json={"inputs":[f"query: {text}"]},timeout=90); response.raise_for_status(); return response.json()[0]

def rerank(query:str, texts:list[str]):
    if not texts:return []
    response=requests.post(f"{settings.reranker_url}/rerank",json={"query":query,"texts":texts,"truncate":True},timeout=90); response.raise_for_status()
    scores={int(x["index"]):float(x["score"]) for x in response.json()}; return [scores.get(i,0.0) for i in range(len(texts))]

def retrieve(cur,ticket,vector,candidate_limit=20):
    documentation_limit=min(12,candidate_limit)
    cases_limit=max(0,candidate_limit-documentation_limit)
    cur.execute("""SELECT k.id::text id,'documentation' kind,k.chunk_text,d.title,d.client_id,1-(k.embedding<=>%s::vector) vector_score,
      ts_rank_cd(k.search_tsv,plainto_tsquery('simple',%s)) text_score
      FROM support.knowledge_chunks k JOIN support.knowledge_documents d ON d.id=k.document_id
      WHERE d.program_id=%s AND (d.scope='global' OR d.client_id=%s)
      ORDER BY GREATEST(1-(k.embedding<=>%s::vector),ts_rank_cd(k.search_tsv,plainto_tsquery('simple',%s))) DESC LIMIT %s""",
      (vector,ticket["description"],ticket["program_id"],ticket["client_id"],vector,ticket["description"],documentation_limit)); rows=[dict(x) for x in cur.fetchall()]
    cur.execute("""SELECT id::text id,'historical_case' kind,
      ticket_description||E'\nRozwiązanie: '||resolution chunk_text,title,NULL::bigint client_id,
      NULL::real vector_score,NULL::real text_score
      FROM support.historical_cases WHERE program_id=%s AND status='approved'
      ORDER BY created_at DESC LIMIT %s""",(ticket["program_id"],cases_limit))
    rows.extend(dict(x) for x in cur.fetchall()); return rows

def propose_answer(query:str,candidates:list[dict],runtime:dict):
    context="\n\n".join(f"[{index+1}] {row.get('kind')}: {row.get('title') or ''}\n{row['chunk_text'][:1400]}" for index,row in enumerate(candidates))
    prompt=f"""Jesteś asystentem serwisowym. Na podstawie wyłącznie źródeł zaproponuj bezpieczną diagnozę i czynności. Nie twierdź, że czynność wykonano. Jeśli źródła są niewystarczające, napisz czego brakuje. Odpowiedz po polsku, numerując kroki i wskazując numery źródeł.

ZGŁOSZENIE:\n{query}\n\nŹRÓDŁA:\n{context or 'Brak trafnych źródeł.'}"""
    response=requests.post(f"{settings.llm_url}/api/generate",json={"model":settings.llm_model,"prompt":prompt,"stream":False,"options":{"temperature":0.1,"num_predict":runtime["llm_response_tokens"]}},timeout=runtime["llm_timeout_seconds"])
    response.raise_for_status(); return response.json().get("response","").strip()

def process(job):
    with connect() as conn, conn.cursor() as cur:
        runtime=application_settings(cur)
        cur.execute("SELECT * FROM support.tickets WHERE id=%s FOR UPDATE",(job["ticket_id"],)); ticket=dict(cur.fetchone())
        state=dict(ticket["workflow_state"] or {}); answers=state.get("answers") or {}
        effective_description=enrich_description(ticket["description"],answers)
        recognized=interpret_locally(effective_description); state["recognized"]=recognized; state["effective_description"]=effective_description
        if recognized["missing"] and not state.get("answers"):
            status="needs_information"; state["step"]="clarification"; state["questions"]=[f"Uzupełnij: {x}" for x in recognized["missing"]]
        else:
            search_ticket={**ticket,"description":effective_description}
            vector=embedding(effective_description); candidates=retrieve(cur,search_ticket,vector,runtime["retrieval_candidates"]); scores=rerank(effective_description,[x["chunk_text"] for x in candidates])
            for row,score in zip(candidates,scores): row["rerank_score"]=score
            candidates=sorted(candidates,key=lambda x:x["rerank_score"],reverse=True)[:runtime["retrieval_top_sources"]]
            safe_candidates=json_safe([{**x,"chunk_text":anonymize(x["chunk_text"])} for x in candidates])
            answer=propose_answer(effective_description,safe_candidates,runtime)
            state.update(step="problem_decision",sources=safe_candidates,proposed_answer=answer); status="awaiting_problem_decision"
        cur.execute("UPDATE support.tickets SET status=%s,recognized=%s::jsonb,missing_fields=%s::jsonb,workflow_state=%s::jsonb,updated_at=now() WHERE id=%s",(status,json.dumps(recognized),json.dumps(recognized["missing"]),json.dumps(state),ticket["id"]))
        cur.execute("INSERT INTO support.workflow_checkpoints(ticket_id,encrypted_state,step) VALUES(%s,%s,%s) ON CONFLICT(ticket_id) DO UPDATE SET encrypted_state=excluded.encrypted_state,step=excluded.step,updated_at=now()",(ticket["id"],encrypt(state),state["step"]))
        cur.execute("UPDATE support.support_jobs SET status='done',updated_at=now(),last_error=NULL WHERE id=%s",(job["id"],))

def fail(job,error):
    with connect() as conn, conn.cursor() as cur:
        delay=min(300,2**min(job["attempts"],8)); cur.execute("UPDATE support.support_jobs SET status='failed_retryable',last_error=%s,available_at=now()+(%s||' seconds')::interval,updated_at=now() WHERE id=%s",(str(error)[:2000],delay,job["id"])); cur.execute("UPDATE support.tickets SET status='failed_retryable' WHERE id=%s",(job["ticket_id"],))

def run():
    while True:
        job=claim()
        if not job: time.sleep(2); continue
        try: process(job)
        except Exception as exc: fail(job,exc)

if __name__=="__main__": run()
