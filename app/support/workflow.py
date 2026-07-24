from __future__ import annotations
import json, re

STEPS = ["interpretation","clarification","retrieval","reranking","problem_decision","solution_ranking","resolution","feedback","validation","close"]

def interpret_locally(description: str) -> dict:
    code = re.search(r"\b(?:ERR(?:OR)?[-_: ]?)?[A-Z]*\d{3,6}\b", description, re.I)
    version = re.search(r"\b(?:v(?:ersja)?\s*)?(\d+\.\d+(?:\.\d+)?)\b", description, re.I)
    problem = re.search(
        r"(?i)\b(?:błąd|problem|awaria|usterka|nie\s+działa|nie\s+mogę|nie\s+można|"
        r"brak\s+możliwości|zawiesza\w*|blokuje\w*|timeout|wyjątek|niepoprawn\w*|"
        r"odrzuca\w*|komunikat\s+błędu)\b",
        description,
    )
    issue_kind="problem" if problem or code else "task"
    missing=[]
    if issue_kind=="problem":
        if not code: missing.append("error_code")
        if not version: missing.append("version")
    return {"symptoms": description[:1000],"error_code":code.group(0) if code else None,
            "version":version.group(1) if version else None,"issue_kind":issue_kind,"missing":missing}

def validate_feedback(outcome: str, comment: str | None) -> tuple[str,str|None]:
    if outcome not in {"helped","partially_helped","not_helped"}: return "suspicious","Nieznany wynik"
    if outcome != "helped" and len((comment or "").strip()) < 8: return "incomplete","Wymagany opis rezultatu"
    contradictory = outcome == "helped" and any(x in (comment or "").lower() for x in ("nie pomog", "nadal", "bez zmian"))
    return ("suspicious","Komentarz przeczy wynikowi") if contradictory else ("consistent",None)
