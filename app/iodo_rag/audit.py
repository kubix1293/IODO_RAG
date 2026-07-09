from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import requests

from iodo_rag.config import Settings
from iodo_rag.llm import answer_with_prompt
from iodo_rag.search import fetch_adjacent_chunks
from iodo_rag.search import search as run_search

PROMPTS_PATH = Path(__file__).with_name("audit_prompts_A5.jsonl")
DEFAULT_CONTROLS = ("A.5.1", "A.5.2", "A.5.3", "A.5.4", "A.5.5")
AUDIT_QUERY_LIMIT = 12
AUDIT_CONTEXT_LIMIT = 10
AUDIT_PRIMARY_CONTEXT_LIMIT = 5
AUDIT_EXPANDED_CONTEXT_LIMIT = 14
AUDIT_KEYWORDS = (
    "polityka",
    "zatwierdz",
    "kierownict",
    "zarząd",
    "zarzad",
    "prezes",
    "właściciel",
    "wlasciciel",
    "odpowiedzial",
    "rola",
    "obowiązk",
    "obowiazk",
    "przegląd",
    "przeglad",
    "aktualiz",
    "wersj",
    "historia zmian",
    "potwierdzen",
    "komunikac",
    "rejestr",
    "procedur",
    "wykaz",
    "kontakt",
    "organ",
    "władzy",
    "wladzy",
)
AUDIT_RAG_GUARDRAILS = """Dodatkowe zasady dla tej aplikacji RAG:
- Pole "referencja: brak referencji" oznacza tylko brak wyodrebnionego numeru punktu/metadanych. Nie oznacza, ze fragment nie jest dowodem.
- Jezeli tresc fragmentu potwierdza wymaganie, uznaj dowod na podstawie tresci, nazwy dokumentu i strony.
- Jezeli fragment potwierdza tylko czesc wymagania, wybierz CZESCIOWO zamiast NIE.
- Odpowiedz NIE tylko wtedy, gdy dokument wprost zaprzecza spelnieniu wymagania.
- Gdy brakuje dowodow na czesc wymagan, opisz potwierdzone elementy oraz braki.
- W polu DOWOD podaj najbardziej konkretna lokalizacje: nazwe dokumentu/pliku, strone oraz sekcje, artykul, paragraf albo punkt, jezeli sa w metadanych kontekstu.
- Fragmenty oznaczone jako poprzedni/nastepny chunk traktuj jako kontekst pomocniczy dla trafienia glownego, a nie jako osobne trafienie."""
WORD_RE = re.compile(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", re.UNICODE)


def load_a5_questions(
    *,
    controls: tuple[str, ...] = DEFAULT_CONTROLS,
    question_no: int = 1,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    wanted = set(controls)

    with PROMPTS_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("control") in wanted and int(row.get("question_no", 0)) == question_no:
                selected.append(row)

    selected.sort(key=lambda row: controls.index(str(row["control"])))
    return selected


def build_retrieval_queries(item: dict[str, Any]) -> list[str]:
    queries: list[str] = []

    def add(value: object) -> None:
        if value is None:
            return
        if isinstance(value, list):
            for entry in value:
                add(entry)
            return
        text = str(value).strip()
        if text and text not in queries:
            queries.append(text)

    add(item.get("query"))
    add(item.get("question"))
    add(item.get("requirement"))
    add(item.get("evidence"))

    control = str(item.get("control") or "").strip()
    control_name = str(item.get("control_name") or "").strip()
    question = str(item.get("question") or "").strip()
    requirement = str(item.get("requirement") or "").strip()
    evidence = " ".join(str(entry) for entry in item.get("evidence") or [])

    add(f"{control} {control_name} {question}")
    add(f"{control_name} dowody dokumenty {evidence}")
    add(f"{control_name} {requirement}")

    return queries


ProgressCallback = Callable[[str], None]


def search_for_audit_item(
    item: dict[str, Any],
    settings: Settings,
    *,
    client_id: int | None = None,
) -> list[dict[str, Any]]:
    candidates: dict[int, dict[str, Any]] = {}

    for query in build_retrieval_queries(item):
        for row in run_search(query, settings, limit=AUDIT_QUERY_LIMIT, client_id=client_id):
            chunk_id = int(row["id"])
            current = candidates.get(chunk_id)
            hybrid_score = float(row.get("hybrid_score") or 0)
            if current is None:
                current = dict(row)
                current["_matched_queries"] = []
                current["_best_hybrid_score"] = hybrid_score
                candidates[chunk_id] = current
            elif hybrid_score > float(current.get("_best_hybrid_score") or 0):
                current.update(row)
                current["_best_hybrid_score"] = hybrid_score

            matched_queries = current.setdefault("_matched_queries", [])
            if query not in matched_queries:
                matched_queries.append(query)

    scored = [_score_audit_candidate(row, item) for row in candidates.values()]
    scored.sort(key=lambda row: float(row.get("audit_score") or 0), reverse=True)
    return _expand_with_neighbors(scored[:AUDIT_CONTEXT_LIMIT], settings, client_id=client_id)


def _expand_with_neighbors(
    rows: list[dict[str, Any]],
    settings: Settings,
    *,
    client_id: int | None,
) -> list[dict[str, Any]]:
    primary_rows = rows[:AUDIT_PRIMARY_CONTEXT_LIMIT]
    seed_ids = [int(row["id"]) for row in primary_rows]
    if not seed_ids:
        return []

    primary_by_id = {int(row["id"]): row for row in primary_rows}
    neighbors = fetch_adjacent_chunks(seed_ids, settings, client_id=client_id)
    expanded: dict[int, dict[str, Any]] = {}

    for neighbor in neighbors:
        chunk_id = int(neighbor["id"])
        seed_id = int(neighbor["seed_id"])
        offset = int(neighbor["neighbor_offset"])
        row = dict(neighbor)
        seed = primary_by_id.get(seed_id, {})
        row["seed_chunk_id"] = seed_id
        row["neighbor_offset"] = offset
        row["context_role"] = _context_role(offset)
        row["audit_score"] = float(seed.get("audit_score") or 0)
        row["audit_query_count"] = seed.get("audit_query_count", 0)
        row["audit_keyword_hits"] = seed.get("audit_keyword_hits", 0)
        row["audit_queries"] = seed.get("audit_queries", [])
        row["hybrid_score"] = float(seed.get("hybrid_score") or 0) if offset else float(seed.get("hybrid_score") or 0)

        current = expanded.get(chunk_id)
        if current is None or _role_priority(row["context_role"]) > _role_priority(str(current.get("context_role"))):
            expanded[chunk_id] = row

    ordered = sorted(
        expanded.values(),
        key=lambda row: (
            -float(row.get("audit_score") or 0),
            int(row.get("document_id") or 0),
            int(row.get("chunk_index") or 0),
        ),
    )
    return ordered[:AUDIT_EXPANDED_CONTEXT_LIMIT]


def _context_role(offset: int) -> str:
    if offset < 0:
        return "poprzedni chunk"
    if offset > 0:
        return "nastepny chunk"
    return "trafienie glowne"


def _role_priority(role: str) -> int:
    if role == "trafienie glowne":
        return 3
    if role in {"poprzedni chunk", "nastepny chunk"}:
        return 2
    return 1


def _score_audit_candidate(row: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    matched_queries = row.get("_matched_queries") or []
    query_bonus = min(len(matched_queries), 6) * 0.01
    keyword_hits = _count_keyword_hits(row, item)
    keyword_bonus = min(keyword_hits, 10) * 0.003
    best_hybrid_score = float(row.get("_best_hybrid_score") or row.get("hybrid_score") or 0)

    row["audit_score"] = best_hybrid_score + query_bonus + keyword_bonus
    row["audit_query_count"] = len(matched_queries)
    row["audit_keyword_hits"] = keyword_hits
    row["audit_queries"] = matched_queries
    row["hybrid_score"] = best_hybrid_score
    return row


def _count_keyword_hits(row: dict[str, Any], item: dict[str, Any]) -> int:
    text_parts = [
        row.get("chunk_text"),
        row.get("source_file"),
        row.get("document_title"),
        row.get("title"),
        item.get("control_name"),
    ]
    haystack = " ".join(str(part or "") for part in text_parts).lower()

    hits = 0
    for keyword in AUDIT_KEYWORDS:
        if keyword.lower() in haystack:
            hits += 1

    for term in _important_terms(item):
        if term in haystack:
            hits += 1

    return hits


def _important_terms(item: dict[str, Any]) -> set[str]:
    source_parts: list[str] = []
    for key in ("control_name", "question", "requirement", "query"):
        value = item.get(key)
        if value:
            source_parts.append(str(value))
    for evidence in item.get("evidence") or []:
        source_parts.append(str(evidence))

    stop_words = {
        "oraz",
        "przez",
        "ktore",
        "które",
        "jest",
        "jako",
        "czy",
        "dla",
        "pod",
        "nad",
        "sie",
        "się",
        "ich",
        "lub",
        "or",
        "and",
        "the",
        "should",
    }
    terms: set[str] = set()
    for match in WORD_RE.finditer(" ".join(source_parts).lower()):
        word = match.group(0)
        if len(word) >= 7 and word not in stop_words:
            terms.add(word)
    return terms


def run_a5_assessment(
    settings: Settings,
    *,
    client_id: int | None = None,
    progress: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    questions = load_a5_questions()
    if progress:
        progress("Rozpoczynam prace nad ankieta A.5.")
    for index, item in enumerate(questions, start=1):
        label = f"{item['id']} ({index}/{len(questions)})"
        if progress:
            progress(f"Rozpoczynam retrieval dla punktu {label}.")
        rows = search_for_audit_item(item, settings, client_id=client_id)
        if progress:
            progress(
                f"Znalazlem {len(rows)} odpowiadajacych fragmentow dla punktu {label}; przechodze do analizy."
            )
        try:
            answer = answer_with_prompt(
                system_prompt=f"{item['system']}\n\n{AUDIT_RAG_GUARDRAILS}",
                user_prompt=str(item["prompt"]),
                rows=rows,
                settings=settings,
            )
        except requests.Timeout as exc:
            answer = (
                "SPELNENIE: BLAD ANALIZY LLM\n"
                "DOWOD: analiza przerwana przez timeout modelu\n"
                f"UZASADNIENIE: Ollama nie zwrocila odpowiedzi dla punktu {label} "
                f"w limicie {settings.llm_timeout_seconds} sekund. Retrieval znalazl {len(rows)} fragmentow, "
                "ale generacja odpowiedzi przekroczyla limit czasu. "
                f"Szczegoly techniczne: {exc}"
            )
            if progress:
                progress(f"Timeout analizy punktu {label}; zapisuje blad punktu i przechodze dalej.")
        except Exception as exc:
            answer = (
                "SPELNENIE: BLAD ANALIZY LLM\n"
                "DOWOD: blad podczas generowania odpowiedzi\n"
                f"UZASADNIENIE: Nie udalo sie wygenerowac odpowiedzi dla punktu {label}. "
                f"Retrieval znalazl {len(rows)} fragmentow. Szczegoly techniczne: {exc}"
            )
            if progress:
                progress(f"Blad analizy punktu {label}; zapisuje blad punktu i przechodze dalej.")
        if progress:
            progress(f"Zakonczylem analize punktu {label}.")
        results.append(
            {
                "item": item,
                "answer": answer,
                "rows": rows,
            }
        )
    if progress:
        progress("Zakonczylem ankiete A.5 i przygotowuje wynik.")
    return results
