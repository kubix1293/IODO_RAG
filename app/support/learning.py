from __future__ import annotations

import json
import re

from .db import application_settings
from .graph import hybrid_llm_answer
from .security import anonymize

ALLOWED_ACTIONS={"duplicate","supplement","new_solution","new_problem"}


def _json_object(text:str)->dict:
    cleaned=re.sub(r"^```(?:json)?\s*|\s*```$","",text.strip(),flags=re.I)
    try: return json.loads(cleaned)
    except json.JSONDecodeError:
        match=re.search(r"\{.*\}",cleaned,re.S)
        if not match: raise ValueError("Model nie zwrócił decyzji JSON")
        return json.loads(match.group(0))


def curate_knowledge(cur,description:str,resolution:str,title:str,candidates:list[dict],client_ref:str)->tuple[dict,str,str]:
    safe_candidates=[]
    allowed_problem_ids=set(); allowed_solution_ids=set()
    for row in candidates:
        problem_id=int(row["problem_id"]); allowed_problem_ids.add(problem_id)
        solution_id=int(row["solution_id"]) if row.get("solution_id") is not None else None
        if solution_id: allowed_solution_ids.add(solution_id)
        safe_candidates.append({
            "problem_id":problem_id,
            "problem_title":anonymize(row["problem_title"]),
            "problem_description":anonymize(row["problem_description"]),
            "solution_id":solution_id,
            "solution_title":anonymize(row.get("solution_title") or ""),
            "solution_summary":anonymize(row.get("solution_summary") or ""),
            "solution_client_id":row.get("solution_client_id"),
        })
    prompt=f"""Jesteś kuratorem bazy wiedzy serwisowej. Porównaj nowy przypadek z istniejącymi problemami i rozwiązaniami. Nie łącz wątków tylko dlatego, że mają podobne słowa: muszą dotyczyć tej samej przyczyny. Wybierz dokładnie jedną akcję:
- duplicate: ta sama metoda już istnieje i nic istotnego nie wnosi,
- supplement: ta sama metoda, ale nowy opis dodaje krok, ostrzeżenie lub warunek,
- new_solution: ten sam problem, lecz inna metoda rozwiązania,
- new_problem: inna przyczyna albo brak wiarygodnego dopasowania.

Zwróć wyłącznie JSON:
{{"action":"duplicate|supplement|new_solution|new_problem","problem_id":null,"solution_id":null,"confidence":0.0,"reason":"krótko","canonical_title":"...","canonical_description":"..."}}

REFERENCJA KLIENTA: {client_ref}
TYTUŁ: {anonymize(title)}
ZGŁOSZENIE: {anonymize(description)}
FAKTYCZNE ROZWIĄZANIE: {anonymize(resolution)}
KANDYDACI: {json.dumps(safe_candidates,ensure_ascii=False)}"""
    runtime=application_settings(cur)
    answer,provider,error=hybrid_llm_answer(prompt,runtime)
    decision=_json_object(answer)
    action=decision.get("action")
    if action not in ALLOWED_ACTIONS: raise ValueError("Model zwrócił nieobsługiwaną akcję")
    problem_id=decision.get("problem_id"); solution_id=decision.get("solution_id")
    if action!="new_problem" and (not isinstance(problem_id,int) or problem_id not in allowed_problem_ids):
        raise ValueError("Model wskazał problem spoza kandydatów")
    if action in {"duplicate","supplement"} and (not isinstance(solution_id,int) or solution_id not in allowed_solution_ids):
        raise ValueError("Model wskazał rozwiązanie spoza kandydatów")
    decision["confidence"]=max(0.0,min(1.0,float(decision.get("confidence") or 0)))
    decision["reason"]=str(decision.get("reason") or "")[:500]
    decision["canonical_title"]=str(decision.get("canonical_title") or title)[:240]
    decision["canonical_description"]=str(decision.get("canonical_description") or description)[:2000]
    return decision,provider,error
