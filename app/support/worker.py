from __future__ import annotations
import json, os, socket, time
from .checkpoints import encrypt
from .db import connect
from .graph import enrich_description, invoke_support_graph, json_safe

WORKER=f"{socket.gethostname()}:{os.getpid()}"

def claim():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT * FROM support.support_jobs WHERE status IN ('queued','failed_retryable') AND available_at<=now() ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"""); job=cur.fetchone()
        if job:
            cur.execute("UPDATE support.support_jobs SET status='running',locked_at=now(),locked_by=%s,attempts=attempts+1,last_error=NULL,updated_at=now() WHERE id=%s",(WORKER,job["id"]))
            cur.execute("UPDATE support.tickets SET status='in_progress',updated_at=now() WHERE id=%s",(job["ticket_id"],))
        return dict(job) if job else None

def process(job):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM support.tickets WHERE id=%s FOR UPDATE",(job["ticket_id"],)); ticket=dict(cur.fetchone())
        state=dict(ticket["workflow_state"] or {}); answers=state.get("answers") or {}
    result=invoke_support_graph({
        "ticket_id":str(ticket["id"]),"client_id":ticket["client_id"],"program_id":ticket["program_id"],
        "description":ticket["description"],"answers":answers,"history_candidates":[],"documentation_candidates":[],
    })
    state=json_safe(dict(result)); recognized=state["recognized"]; status=state["status"]
    with connect() as conn, conn.cursor() as cur:
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
