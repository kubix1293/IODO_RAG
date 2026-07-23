from __future__ import annotations

from .db import application_settings
from .graph import (
    LLM_CONTEXT_MAX_CHARS,
    documentation_agent_node,
    history_agent_node,
    hybrid_llm_answer,
    reranking_node,
)
from .security import anonymize


def answer_consultation(
    *,
    question:str,
    conversation:list[dict],
    ticket_description:str|None,
    program_id:int,
    client_id:int|None,
    client_ref:str,
) -> tuple[str,str,str,list[dict]]:
    safe_question=anonymize(question)
    safe_ticket=anonymize(ticket_description or "")
    retrieval_query="\n".join(part for part in (safe_ticket,safe_question) if part)
    state={
        "program_id":program_id,
        "client_id":client_id,
        "effective_description":retrieval_query,
        "privacy_redactions":[],
    }
    history=history_agent_node(state)
    documentation=documentation_agent_node(state)
    ranked=reranking_node({**state,**history,**documentation})
    sources=ranked.get("sources") or []

    blocks=[]; used=0
    for index,row in enumerate(sources):
        title=(row.get("title") or "bez tytułu").strip()
        role="fragment sąsiedni" if row.get("context_role")=="neighbor" else "trafienie"
        header=f"MATERIAŁ {index+1} ({row.get('kind')}, {role})\nTYTUŁ: {title}\n"
        remaining=LLM_CONTEXT_MAX_CHARS-used-len(header)
        if remaining<=0: break
        block=header+(row.get("chunk_text") or "")[:remaining]
        blocks.append(block); used+=len(block)+2

    history_text="\n".join(
        f"{'SERWISANT' if item['role']=='user' else 'ASYSTENT'}: {anonymize(item['content'])}"
        for item in conversation[-8:]
    )
    prompt=f"""Jesteś konsultantem technicznym IT w panelu serwisowym. Prowadzisz rozmowę z serwisantem.

Zasady:
1. Odpowiedz bezpośrednio na ostatnie pytanie lub sprostowanie.
2. Uwzględnij historię rozmowy i opis ticketu, jeśli został wskazany.
3. Materiały zostały wyszukane ponownie dla ostatniej wiadomości. Preferuj dokładne kody błędów, nazwy modułów, wersje i operacje.
4. Gdy użytkownik prosi o wykonanie czynności na podstawie instrukcji, podaj techniczną procedurę krok po kroku wraz z oczekiwanym wynikiem.
5. Nie wymyślaj opcji, poleceń ani konfiguracji, których nie potwierdzają materiały. Przy braku danych zadaj konkretne pytania diagnostyczne.
6. Nie używaj stylu prawnego. Nie twierdź, że wykonałeś czynności w systemie klienta.
7. Najpierw odpowiedz naturalnym wyjaśnieniem, a potem — jeśli potrzebne są czynności — przedstaw je kolejno jako 1., 2., 3. Przy każdym kroku wyjaśnij co zrobić, dlaczego i jaki wynik sprawdzić.
8. Nie używaj składni Markdown: gwiazdek, podwójnych gwiazdek, znaków #, tabel ani sztucznych formalnych nagłówków. Pisz jak doświadczony serwisant rozmawiający z drugim serwisantem.

REFERENCJA KLIENTA: {client_ref}
OPIS TICKETU:
{safe_ticket or "Rozmowa ogólna, bez ticketu."}

HISTORIA ROZMOWY:
{history_text or "Brak wcześniejszych wiadomości."}

OSTATNIA WIADOMOŚĆ SERWISANTA:
{safe_question}

MATERIAŁY TECHNICZNE:
{chr(10).join(blocks) or "Brak trafnych materiałów."}"""
    runtime=application_settings()
    answer,provider,error=hybrid_llm_answer(prompt,runtime)
    return answer,provider,error,sources
