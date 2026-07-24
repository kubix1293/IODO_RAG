from __future__ import annotations

import json
import re
from typing import Any

from iodo_rag.chunking import split_into_chunks

from .graph import hybrid_llm_answer
from .security import anonymize

AI_BASE_CHARS = 1200
AI_BATCH_PARTS = 8
AI_MAX_CHUNK_CHARS = 3600
AI_OVERVIEW_CHARS = 18000


def _json_object(value: str) -> dict[str, Any]:
    value = value.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", value, re.I | re.S)
    if fenced:
        value = fenced.group(1)
    else:
        start, end = value.find("{"), value.rfind("}")
        if start >= 0 and end > start:
            value = value[start : end + 1]
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Model nie zwrócił obiektu JSON")
    return parsed


def _document_overview(text: str, details: list[dict[str, object]]) -> str:
    if len(text) <= AI_OVERVIEW_CHARS:
        return text
    samples: list[str] = []
    used = 0
    for page in details:
        page_text = str(page.get("text") or "").strip()
        if not page_text:
            continue
        sample = f"STRONA {page.get('page', '?')}:\n{page_text[:700]}"
        if used + len(sample) > AI_OVERVIEW_CHARS:
            break
        samples.append(sample)
        used += len(sample) + 2
    return "\n\n".join(samples) or text[:AI_OVERVIEW_CHARS]


def _map_document(
    text: str,
    details: list[dict[str, object]],
    program_name: str,
    runtime: dict,
) -> tuple[dict[str, Any], str, str]:
    prompt = f"""Przeanalizuj strukturę instrukcji technicznej systemu {program_name}.
Otrzymujesz pełny tekst, jeśli mieści się w kontekście, albo przekrojowe próbki kolejnych stron.
Nie rozwiązuj problemu użytkownika. Zbuduj mapę dokumentu potrzebną do późniejszego podziału.

Zwróć wyłącznie poprawny JSON:
{{
  "document_title": "tytuł",
  "document_type": "instruction|manual|configuration|reference",
  "modules": ["moduły i oznaczenia, np. ASW11"],
  "sections": ["główne obszary czynności"],
  "terminology": ["istotne nazwy ekranów, operacji i dokumentów"],
  "chunking_notes": "krótka wskazówka, gdzie nie rozdzielać procedur"
}}

Nie umieszczaj danych osobowych. Nie wymyślaj modułów, których nie ma w materiale.

MATERIAŁ:
{anonymize(_document_overview(text, details))}"""
    answer, provider, error = hybrid_llm_answer(
        prompt, {**runtime, "llm_response_tokens": min(2000, max(1200, runtime["llm_response_tokens"]))}
    )
    return _json_object(answer), provider, error


def _fallback_groups(parts: list[dict[str, object]]) -> list[dict[str, Any]]:
    return [
        {
            "part_numbers": [index + 1],
            "title": str(part.get("title") or f"Fragment {index + 1}")[:240],
            "module": None,
            "operation": None,
            "content_type": "reference",
            "keywords": [],
        }
        for index, part in enumerate(parts)
    ]


def _validate_groups(groups: object, parts: list[dict[str, object]]) -> list[dict[str, Any]]:
    if not isinstance(groups, list):
        raise ValueError("Brak listy groups")
    expected = list(range(1, len(parts) + 1))
    seen: list[int] = []
    valid: list[dict[str, Any]] = []
    for raw in groups:
        if not isinstance(raw, dict):
            raise ValueError("Nieprawidłowa grupa")
        numbers = raw.get("part_numbers")
        if not isinstance(numbers, list) or not numbers:
            raise ValueError("Brak part_numbers")
        numbers = [int(number) for number in numbers]
        if numbers != list(range(numbers[0], numbers[-1] + 1)):
            raise ValueError("Grupa nie jest ciągła")
        if min(numbers) < 1 or max(numbers) > len(parts):
            raise ValueError("Numer fragmentu poza zakresem")
        text = "\n\n".join(str(parts[number - 1]["text"]) for number in numbers)
        if len(text) > AI_MAX_CHUNK_CHARS:
            raise ValueError("Proponowany fragment jest za duży")
        seen.extend(numbers)
        valid.append(
            {
                "part_numbers": numbers,
                "title": str(raw.get("title") or parts[numbers[0] - 1].get("title") or "Fragment")[:240],
                "module": str(raw["module"])[:120] if raw.get("module") else None,
                "operation": str(raw["operation"])[:240] if raw.get("operation") else None,
                "content_type": str(raw.get("content_type") or "reference")[:80],
                "keywords": [str(item)[:100] for item in (raw.get("keywords") or [])[:20]],
            }
        )
    if seen != expected:
        raise ValueError("Model pominął, powtórzył albo zmienił kolejność fragmentów")
    return valid


def _group_batch(
    parts: list[dict[str, object]],
    document_map: dict[str, Any],
    program_name: str,
    runtime: dict,
) -> tuple[list[dict[str, Any]], str, str]:
    material = "\n\n".join(
        f"CZĘŚĆ {index + 1}:\n{anonymize(str(part['text']))}"
        for index, part in enumerate(parts)
    )
    prompt = f"""Jesteś architektem bazy wiedzy technicznej systemu {program_name}.
Połącz kolejne małe części w logiczne fragmenty do wyszukiwania wektorowego.

Zasady bezwzględne:
1. Każda część od 1 do {len(parts)} musi wystąpić dokładnie raz.
2. Łącz tylko części bezpośrednio sąsiadujące i nie zmieniaj ich kolejności.
3. Nie przepisuj treści. Zwracasz wyłącznie numery części i metadane.
4. Nie rozdzielaj nagłówka od procedury ani kroków tej samej krótkiej procedury.
5. Nie łącz różnych modułów, ekranów, operacji lub niezależnych tematów.
6. Jedna grupa może obejmować najwyżej 3 części.
7. Tytuł ma opisywać konkretną czynność lub problem, a nie nazwę całego dokumentu.
8. Słowa kluczowe powinny obejmować moduł, ekran, operację, kod błędu i synonimy używane przez serwisantów.

MAPA DOKUMENTU:
{json.dumps(document_map, ensure_ascii=False)}

Zwróć wyłącznie JSON:
{{
  "groups": [
    {{
      "part_numbers": [1, 2],
      "title": "konkretny tytuł techniczny",
      "module": "np. ASW11 albo null",
      "operation": "wykonywana czynność albo null",
      "content_type": "procedure|configuration|troubleshooting|reference|warning",
      "keywords": ["słowo", "synonim"]
    }}
  ]
}}

CZĘŚCI:
{material}"""
    answer, provider, error = hybrid_llm_answer(
        prompt, {**runtime, "llm_response_tokens": min(2000, max(1200, runtime["llm_response_tokens"]))}
    )
    parsed = _json_object(answer)
    return _validate_groups(parsed.get("groups"), parts), provider, error


def propose_chunks(
    text: str,
    details: list[dict[str, object]],
    program_name: str,
    runtime: dict,
) -> tuple[list[dict[str, object]], dict[str, Any], str, str]:
    """Create reviewable chunks; the LLM only selects boundaries and metadata."""
    base_parts = split_into_chunks(text, target_chars=AI_BASE_CHARS, overlap_chars=0)
    if not base_parts:
        raise ValueError("Dokument nie zawiera tekstu możliwego do zaindeksowania")

    errors: list[str] = []
    providers: list[str] = []
    try:
        document_map, provider, error = _map_document(text, details, program_name, runtime)
        providers.append(provider)
        if error:
            errors.append(error)
    except Exception as exc:
        document_map = {
            "document_title": "",
            "document_type": "instruction",
            "modules": [],
            "sections": [],
            "terminology": [],
            "chunking_notes": "Automatyczna mapa dokumentu była niedostępna.",
        }
        errors.append(f"mapa dokumentu: {exc}")

    proposals: list[dict[str, object]] = []
    proposal_index = 0
    for offset in range(0, len(base_parts), AI_BATCH_PARTS):
        batch = base_parts[offset : offset + AI_BATCH_PARTS]
        try:
            groups, provider, error = _group_batch(batch, document_map, program_name, runtime)
            providers.append(provider)
            if error:
                errors.append(error)
        except Exception as exc:
            groups = _fallback_groups(batch)
            errors.append(f"partia {offset // AI_BATCH_PARTS + 1}: {exc}")
        for group in groups:
            numbers = group.pop("part_numbers")
            selected = [batch[number - 1] for number in numbers]
            chunk_text = "\n\n".join(str(part["text"]) for part in selected)
            metadata = {
                **group,
                "source_part_from": offset + numbers[0],
                "source_part_to": offset + numbers[-1],
                "page_from": min(
                    (int(part["page_from"]) for part in selected if part.get("page_from") is not None),
                    default=None,
                ),
                "page_to": max(
                    (int(part["page_to"]) for part in selected if part.get("page_to") is not None),
                    default=None,
                ),
                "document_map": document_map,
            }
            proposals.append(
                {
                    "proposed_index": proposal_index,
                    "chunk_text": chunk_text,
                    "metadata": metadata,
                }
            )
            proposal_index += 1
    provider_summary = ",".join(dict.fromkeys(providers)) or "deterministic_fallback"
    return proposals, document_map, provider_summary, " | ".join(dict.fromkeys(errors))[:2000]
