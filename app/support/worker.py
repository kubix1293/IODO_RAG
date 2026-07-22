from __future__ import annotations
import json, os, socket, time, uuid
import requests
from .checkpoints import encrypt
from .config import settings
from .db import connect
from .ranking import compatibility, effectiveness, total
from .security import anonymize
from .workflow import interpret_locally

WORKER=f"{socket.gethostname()}:{os.getpid()}"

def claim():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT * FROM support.support_jobs WHERE status IN ('queued','failed_retryable') AND available_at<=now() ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"""); job=cur.fetchone()
        if job: cur.execute("UPDATE support.support_jobs SET status='running',locked_at=now(),locked_by=%s,attempts=attempts+1,updated_at=now() WHERE id=%s",(WORKER,job["id"]))
        return dict(job) if job else None

def embedding(text:str):
    response=requests.post(f"{settings.embedding_url}/embed",json={"inputs":[f"query: {text}"]},timeout=90); response.raise_for_status(); return response.json()[0]

def rerank(query:str, texts:list[str]):
    if not texts:return []
    response=requests.post(f"{settings.reranker_url}/rerank",json={"query":query,"texts":texts,"truncate":True},timeout=90); response.raise_for_status()
    scores={int(x["index"]):float(x["score"]) for x in response.json()}; return [scores.get(i,0.0) for i in range(len(texts))]

def retrieve(cur,ticket,vector):
    cur.execute("""SELECT k.id,k.chunk_text,d.title,d.client_id,1-(k.embedding<=>%s::vector) vector_score,
      ts_rank_cd(k.search_tsv,plainto_tsquery('simple',%s)) text_score
      FROM support.knowledge_chunks k JOIN support.knowledge_documents d ON d.id=k.document_id
      WHERE d.program_id=%s AND (d.scope='global' OR d.client_id=%s)
      ORDER BY GREATEST(1-(k.embedding<=>%s::vector),ts_rank_cd(k.search_tsv,plainto_tsquery('simple',%s))) DESC LIMIT 20""",
      (vector,ticket["description"],ticket["program_id"],ticket["client_id"],vector,ticket["description"])); return [dict(x) for x in cur.fetchall()]

def process(job):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM support.tickets WHERE id=%s FOR UPDATE",(job["ticket_id"],)); ticket=dict(cur.fetchone())
        state=dict(ticket["workflow_state"] or {}); recognized=interpret_locally(ticket["description"]); state["recognized"]=recognized
        if recognized["missing"] and not state.get("answers"):
            status="needs_information"; state["step"]="clarification"; state["questions"]=[f"Uzupełnij: {x}" for x in recognized["missing"]]
        else:
            vector=embedding(ticket["description"]); candidates=retrieve(cur,ticket,vector); scores=rerank(ticket["description"],[x["chunk_text"] for x in candidates])
            for row,score in zip(candidates,scores): row["rerank_score"]=score
            candidates=sorted(candidates,key=lambda x:x["rerank_score"],reverse=True)[:8]
            state.update(step="problem_decision",sources=[{**x,"chunk_text":anonymize(x["chunk_text"])} for x in candidates]); status="awaiting_problem_decision"
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
