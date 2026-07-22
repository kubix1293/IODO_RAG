"""Destructive smoke test for a local, non-production support stack."""
from __future__ import annotations

import os
import time
import uuid
from io import BytesIO

import requests
from docx import Document

from support.db import connect
from support.security import hash_password


BASE = os.getenv("SUPPORT_TEST_URL", "http://127.0.0.1:8081")


def require(response: requests.Response, status: int) -> dict:
    if response.status_code != status:
        raise AssertionError(f"{response.request.method} {response.url}: {response.status_code} {response.text}")
    return response.json() if response.content else {}


def main() -> None:
    suffix = uuid.uuid4().hex[:10]
    with connect() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO public.clients(name) VALUES(%s) RETURNING id", (f"Smoke klient {suffix}",))
        client_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO support.programs(name) VALUES(%s) RETURNING id", (f"Smoke program {suffix}",))
        program_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO support.client_installations(client_id,program_id,version,environment) VALUES(%s,%s,'2.4.1','test') RETURNING id",
            (client_id, program_id),
        )
        installation_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO support.canonical_problems(program_id,title,normalized_description,error_codes) VALUES(%s,%s,%s,ARRAY['ERR-1234']) RETURNING id",
            (program_id, "Błąd zapisu", "Nie można zapisać rekordu"),
        )
        problem_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO support.solutions(problem_id,title,summary,status) VALUES(%s,'Naprawa zapisu','Procedura testowa','approved') RETURNING id",
            (problem_id,),
        )
        solution_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO support.solution_steps(solution_id,position,instruction,expected_result) VALUES(%s,1,'Sprawdź uprawnienia','Zapis działa') RETURNING id",
            (solution_id,),
        )
        step_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO public.clients(name) VALUES(%s) RETURNING id", (f"Smoke obcy klient {suffix}",))
        other_client_id = cur.fetchone()["id"]
        technician_username = f"smoke-tech-{suffix}"
        technician_password = f"Smoke-{suffix}-password"
        cur.execute(
            "INSERT INTO support.users(username,password_hash,role) VALUES(%s,%s,'technician')",
            (technician_username, hash_password(technician_password)),
        )
        zero_vector = "[" + ",".join(["0"] * 384) + "]"
        cur.execute(
            "INSERT INTO support.knowledge_documents(program_id,client_id,scope,source_file,title,sha256) VALUES(%s,%s,'client',%s,'Własny dokument',%s) RETURNING id",
            (program_id, client_id, f"smoke-own-{suffix}.txt", f"own-{suffix}"),
        )
        own_document_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO support.knowledge_documents(program_id,client_id,scope,source_file,title,sha256) VALUES(%s,%s,'client',%s,'Obcy dokument',%s) RETURNING id",
            (program_id, other_client_id, f"smoke-other-{suffix}.txt", f"other-{suffix}"),
        )
        other_document_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO support.knowledge_chunks(document_id,chunk_index,chunk_text,embedding) VALUES(%s,0,'własna prywatna wiedza',%s::vector),(%s,0,'obca prywatna wiedza',%s::vector)",
            (own_document_id, zero_vector, other_document_id, zero_vector),
        )
        cur.execute(
            "SELECT d.id FROM support.knowledge_documents d WHERE d.program_id=%s AND (d.scope='global' OR d.client_id=%s)",
            (program_id, client_id),
        )
        visible_ids = {row["id"] for row in cur.fetchall()}
        assert own_document_id in visible_ids and other_document_id not in visible_ids

    session = requests.Session()
    assert session.get(BASE + "/login", timeout=10).status_code == 200
    login = require(
        session.post(BASE + "/api/v1/auth/login", json={"username": os.environ["SUPPORT_BOOTSTRAP_USER"], "password": os.environ["SUPPORT_BOOTSTRAP_PASSWORD"]}),
        200,
    )
    headers = {"X-CSRF-Token": login["csrf_token"]}
    assert session.get(BASE + "/", timeout=10).status_code == 200
    assert session.get(BASE + "/cases", timeout=10).status_code == 200
    assert session.get(BASE + "/tickets/new", timeout=10).status_code == 200
    assert session.get(BASE + "/knowledge", timeout=10).status_code == 200
    assert session.post(BASE + "/api/v1/tickets", json={}, timeout=10).status_code == 403
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id,name FROM support.programs WHERE name IN ('ZZL','ASW')")
        system_ids = {row["name"]: row["id"] for row in cur.fetchall()}
    document=Document(); document.add_paragraph(f"Instrukcja ZZL {suffix}: aby odblokować zapis, sprawdź uprawnienia operatora.")
    document_bytes=BytesIO(); document.save(document_bytes); document_bytes.seek(0)
    indexed=require(
        session.post(
            BASE + "/api/v1/knowledge/documents",
            headers=headers,
            data={"program_id":system_ids["ZZL"],"scope":"global"},
            files={"file":(f"instrukcja-zzl-{suffix}.docx",document_bytes,"application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            timeout=120,
        ),
        202,
    )
    assert indexed["status"]=="indexed" and indexed["chunks"]>=1
    created_cases = {}
    for system_name in ("ZZL", "ASW"):
        created_cases[system_name] = require(
            session.post(
                BASE + "/api/v1/cases",
                headers=headers,
                json={"program_id": system_ids[system_name], "title": f"Przypadek {system_name} {suffix}", "ticket_description": f"Opis zgłoszenia wyłącznie dla {system_name}", "resolution": f"Rozwiązanie wyłącznie dla {system_name}"},
            ),
            201,
        )
    zzl_cases = require(session.get(BASE + "/api/v1/cases", params={"program_id": system_ids["ZZL"]}), 200)["cases"]
    zzl_case_ids = {row["id"] for row in zzl_cases}
    assert created_cases["ZZL"]["id"] in zzl_case_ids
    assert created_cases["ASW"]["id"] not in zzl_case_ids
    ticket = require(
        session.post(
            BASE + "/api/v1/tickets",
            headers=headers,
            json={"client_id": client_id, "program_id": program_id, "installation_id": installation_id, "description": "ERR-1234: błąd zapisu w wersji 2.4.1 w środowisku testowym"},
            timeout=10,
        ),
        201,
    )
    ticket_id = ticket["id"]
    require(session.post(f"{BASE}/api/v1/tickets/{ticket_id}/analysis/start", headers=headers, timeout=10), 202)

    workflow = {}
    for _ in range(90):
        workflow = require(session.get(f"{BASE}/api/v1/tickets/{ticket_id}/workflow", timeout=10), 200)
        if workflow["status"] in {"awaiting_problem_decision", "failed_retryable"}:
            break
        time.sleep(1)
    assert workflow["status"] == "awaiting_problem_decision", workflow
    assert workflow["job"]["status"] == "done"

    require(
        session.post(f"{BASE}/api/v1/tickets/{ticket_id}/problem-link", headers=headers, json={"problem_id": problem_id, "decision": "confirmed"}),
        200,
    )
    attempt_id = uuid.uuid4()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO support.resolution_attempts(id,ticket_id,solution_id,position,rerank_score,compatibility_score,effectiveness_score,total_score) VALUES(%s,%s,%s,1,.9,1,.5,.82)",
            (attempt_id, ticket_id, solution_id),
        )
    require(
        session.post(f"{BASE}/api/v1/tickets/{ticket_id}/resolution-mode", headers=headers, json={"attempt_id": str(attempt_id), "mode": "interactive"}),
        200,
    )
    require(
        session.post(f"{BASE}/api/v1/tickets/{ticket_id}/steps/{step_id}/result", headers=headers, json={"attempt_id": str(attempt_id), "result": "Uprawnienia poprawione", "successful": True}),
        200,
    )
    result = require(
        session.post(f"{BASE}/api/v1/tickets/{ticket_id}/feedback", headers=headers, json={"attempt_id": str(attempt_id), "outcome": "helped", "comment": "Po wykonaniu kroku zapis działa poprawnie"}),
        200,
    )
    assert result["validation"] == "consistent"
    require(
        session.post(f"{BASE}/api/v1/tickets/{ticket_id}/close", headers=headers, json={"final_attempt_id": str(attempt_id)}),
        200,
    )
    closed = require(session.get(f"{BASE}/api/v1/tickets/{ticket_id}"), 200)
    assert closed["status"] == "closed"
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) count FROM support.audit_events WHERE entity_id=%s", (ticket_id,))
        assert cur.fetchone()["count"] >= 7
        cur.execute("SELECT step FROM support.workflow_checkpoints WHERE ticket_id=%s", (ticket_id,))
        assert cur.fetchone()["step"] == "problem_decision"
    require(session.post(BASE + "/api/v1/auth/logout", headers=headers), 204)
    technician = requests.Session()
    tech_login = require(technician.post(BASE + "/api/v1/auth/login", json={"username": technician_username, "password": technician_password}), 200)
    forbidden = technician.post(
        f"{BASE}/api/v1/solutions/{solution_id}/approve",
        headers={"X-CSRF-Token": tech_login["csrf_token"]},
    )
    assert forbidden.status_code == 403, forbidden.text
    forbidden_case = technician.post(
        BASE + "/api/v1/cases",
        headers={"X-CSRF-Token": tech_login["csrf_token"]},
        json={"program_id": system_ids["ZZL"], "title": "Niedozwolony przypadek", "ticket_description": "Technik nie może dodać tego przypadku", "resolution": "Ta operacja musi zostać odrzucona"},
    )
    assert forbidden_case.status_code == 403, forbidden_case.text
    assert technician.get(BASE + "/cases", timeout=10).status_code == 403
    assert technician.get(BASE + "/tickets/new", timeout=10).status_code == 200
    assert technician.get(BASE + "/knowledge", timeout=10).status_code == 403
    print(f"integration smoke passed: ticket={ticket_id}")


if __name__ == "__main__":
    main()
