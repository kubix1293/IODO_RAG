"""Temporary end-to-end smoke test for model-assisted knowledge curation."""
from __future__ import annotations

import os
import uuid

import requests

from support.db import connect

BASE=os.getenv("SUPPORT_TEST_URL","http://127.0.0.1:8081")


def main():
    suffix=uuid.uuid4().hex[:10]
    ticket_id=uuid.uuid4(); report_id=uuid.uuid4()
    program_id=client_id=None
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM support.users WHERE username=%s",(os.environ["SUPPORT_BOOTSTRAP_USER"],))
        actor_id=cur.fetchone()["id"]
        cur.execute("INSERT INTO public.clients(name) VALUES(%s) RETURNING id",(f"Smoke curator client {suffix}",))
        client_id=cur.fetchone()["id"]
        cur.execute("INSERT INTO support.programs(name) VALUES(%s) RETURNING id",(f"Smoke curator program {suffix}",))
        program_id=cur.fetchone()["id"]
        cur.execute("INSERT INTO support.canonical_problems(program_id,title,normalized_description) VALUES(%s,'Brak startu usługi','Usługa nie uruchamia się') RETURNING id",(program_id,))
        problem_id=cur.fetchone()["id"]
        cur.execute("""INSERT INTO support.solutions(problem_id,title,summary,status,created_by,approved_by,approved_at)
          VALUES(%s,'Restart usługi','Ponownie uruchom usługę','approved',%s,%s,now()) RETURNING id""",(problem_id,actor_id,actor_id))
        solution_id=cur.fetchone()["id"]
        cur.execute("INSERT INTO support.solution_steps(solution_id,position,instruction) VALUES(%s,1,'Ponownie uruchom usługę')",(solution_id,))
        cur.execute("""INSERT INTO support.tickets(id,client_id,program_id,description,created_by,owner_id)
          VALUES(%s,%s,%s,'Usługa nie uruchamia się, kod ERR-4455, wersja 2.3.4',%s,%s)""",
          (ticket_id,client_id,program_id,actor_id,actor_id))
        cur.execute("""INSERT INTO support.ticket_resolution_reports(
          id,ticket_id,outcome,suggestion_rating,actual_resolution,created_by)
          VALUES(%s,%s,'helped',5,'Ponownie uruchomiono usługę i zweryfikowano jej stan',%s)""",
          (report_id,ticket_id,actor_id))
    try:
        session=requests.Session()
        login=session.post(BASE+"/api/v1/auth/login",json={
            "username":os.environ["SUPPORT_BOOTSTRAP_USER"],
            "password":os.environ["SUPPORT_BOOTSTRAP_PASSWORD"],
        },timeout=15)
        login.raise_for_status()
        response=session.post(
            f"{BASE}/api/v1/tickets/{ticket_id}/publish-resolution",
            json={"title":"Uruchomienie zatrzymanej usługi","scope":"client"},
            headers={"X-CSRF-Token":login.json()["csrf_token"]},
            timeout=120,
        )
        if response.status_code!=201:
            raise AssertionError(f"{response.status_code}: {response.text}")
        result=response.json()
        assert result["provider"]=="external_api",result
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT client_id,canonical_problem_id,solution_id FROM support.historical_cases WHERE program_id=%s",(program_id,))
            case=cur.fetchone()
            assert case and case["client_id"]==client_id
            cur.execute("SELECT scope,client_id,provider FROM support.knowledge_curation_runs WHERE ticket_id=%s",(ticket_id,))
            run=cur.fetchone()
            assert run and run["scope"]=="client" and run["client_id"]==client_id and run["provider"]=="external_api"
        print("Knowledge curation smoke: OK",result["curation_action"])
    finally:
        if program_id is not None:
            with connect() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM support.historical_cases WHERE program_id=%s",(program_id,))
                cur.execute("DELETE FROM support.tickets WHERE id=%s",(ticket_id,))
                cur.execute("DELETE FROM support.solutions WHERE problem_id IN (SELECT id FROM support.canonical_problems WHERE program_id=%s)",(program_id,))
                cur.execute("DELETE FROM support.canonical_problems WHERE program_id=%s",(program_id,))
                cur.execute("DELETE FROM support.programs WHERE id=%s",(program_id,))
                cur.execute("DELETE FROM public.clients WHERE id=%s",(client_id,))


if __name__=="__main__":
    main()
