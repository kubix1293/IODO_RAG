from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from iodo_rag.config import Settings


SYSTEM_PROMPT = """Jestes asystentem audytowym do analizy polskich dokumentow prawnych i bezpieczenstwa.
Odpowiadaj po polsku, zwiezle i rzeczowo.
Korzystaj wylacznie z przekazanego kontekstu.

Zasady interpretacji:
- Traktuj slowo "organizacja" jako podmiot, ktorego dotycza znalezione dokumenty, np. ICZMP, urzad, administrator lub inna nazwa wystepujaca w kontekscie.
- Nie wymagaj doslownego powtorzenia tresci pytania. Jesli kontekst zawiera rownowazne dowody, wyciagnij wniosek.
- Dla pytan kontrolnych/audytowych odpowiedz najpierw jednym z: "Tak", "Nie", "Czesciowo" albo "Brak danych".
- "Brak danych" wybierz tylko wtedy, gdy w kontekscie rzeczywiscie nie ma przeslanek pozwalajacych odpowiedziec.
- Uzasadnij odpowiedz 1-3 krotkimi zdaniami i wskaz, ktory fragment kontekstu jest podstawa, np. [1].
- Gdy wskazujesz dowod, podaj nazwe dokumentu, strone oraz sekcje/artykul/paragraf/punkt, jesli sa podane w metadanych fragmentu.
- Nie tworz porad prawnych poza trescia dokumentow."""


def build_context(rows: list[dict[str, Any]], *, max_chars: int = 8500) -> str:
    parts: list[str] = []
    used = 0
    for index, row in enumerate(rows, start=1):
        source = str(row.get("source_file") or "nieznane zrodlo")
        source_name = Path(source).name
        document_title = str(row.get("document_title") or row.get("title") or source_name)
        client_name = str(row.get("client_name") or row.get("client_id") or "brak klienta")
        ref_parts = [
            ("sekcja", row.get("section")),
            ("artykul", row.get("article")),
            ("paragraf", row.get("paragraph")),
            ("punkt", row.get("point")),
        ]
        ref = "; ".join(f"{label}: {value}" for label, value in ref_parts if value) or "brak referencji"
        pages = _format_pages(row)
        chunk_index = row.get("chunk_index")
        context_role = str(row.get("context_role") or "trafienie")
        audit_score = row.get("audit_score")
        score = f"; audit_score: {float(audit_score):.4f}" if audit_score is not None else ""
        text = str(row.get("chunk_text") or "").strip()
        block = (
            f"[{index}] Klient: {client_name}; dokument: {document_title}; plik: {source_name}; "
            f"{pages}; {ref}; chunk_index: {chunk_index}; rola_kontekstu: {context_role}{score}\n"
            f"{text}"
        )
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def _format_pages(row: dict[str, Any]) -> str:
    page_from = row.get("page_from")
    page_to = row.get("page_to")
    if page_from and page_to:
        return f"strony: {page_from}-{page_to}"
    if page_from:
        return f"strona: {page_from}"
    if page_to:
        return f"strona: {page_to}"
    return "strona: brak"


def answer_question(question: str, rows: list[dict[str, Any]], settings: Settings) -> str:
    context = build_context(rows, max_chars=settings.llm_context_max_chars)
    if not context:
        return "Nie znaleziono wystarczajacego kontekstu w zaimportowanych dokumentach."

    prompt = f"""{SYSTEM_PROMPT}

Kontekst:
{context}

Pytanie:
{question}

Odpowiedz:"""

    response = requests.post(
        f"{settings.llm_url}/api/generate",
        json={
            "model": settings.llm_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": settings.llm_num_ctx,
                "num_predict": settings.llm_num_predict,
            },
        },
        timeout=settings.llm_timeout_seconds,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise requests.HTTPError(
            f"{exc}; LLM response: {response.text[:1000]}",
            response=response,
        ) from exc

    payload = response.json()
    answer = payload.get("response")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError(f"Unexpected LLM response: {payload!r}")
    return answer.strip()


def answer_with_prompt(
    *,
    system_prompt: str,
    user_prompt: str,
    rows: list[dict[str, Any]],
    settings: Settings,
) -> str:
    context = build_context(rows, max_chars=settings.llm_context_max_chars)
    if not context:
        return "SPELNENIE: BRAK DANYCH W DOKUMENTACH\nDOWOD: brak\nUZASADNIENIE: Nie znaleziono wystarczajacego kontekstu w zaimportowanych dokumentach."

    prompt = f"""{system_prompt}

Kontekst RAG:
{context}

Zadanie:
{user_prompt}

Odpowiedz:"""

    response = requests.post(
        f"{settings.llm_url}/api/generate",
        json={
            "model": settings.llm_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": settings.llm_num_ctx,
                "num_predict": settings.llm_num_predict,
            },
        },
        timeout=settings.llm_timeout_seconds,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise requests.HTTPError(
            f"{exc}; LLM response: {response.text[:1000]}",
            response=response,
        ) from exc

    payload = response.json()
    answer = payload.get("response")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError(f"Unexpected LLM response: {payload!r}")
    return answer.strip()
