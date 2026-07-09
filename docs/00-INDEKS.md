# Indeks dokumentacji IODO RAG

Ostatnia aktualizacja: 2026-07-09

Cel pliku: mapa aktualnej dokumentacji technicznej projektu `/opt/IODO`, statusu wdrozenia i najwazniejszych zmian.

## Status projektu

Projekt jest lokalnym, self-hosted pipeline RAG dla polskich dokumentow prawnych i dokumentow bezpieczenstwa.

Gotowe i zweryfikowane:

- import PDF z warstwa tekstowa oraz DOCX przez web UI,
- web UI FastAPI do uploadu jednego lub wielu plikow,
- dashboard web pokazujacy liczbe dokumentow, chunkow i ostatnie importy,
- obsluga klientow w web UI i filtrowanie dokumentow/retrievalu po `client_id`,
- usuwanie dokumentow z bazy przez web UI,
- zapis dokumentow i chunkow w PostgreSQL 16 z pgvector,
- embeddingi przez Hugging Face TEI na modelu `intfloat/multilingual-e5-small`,
- wyszukiwanie hybrydowe w web UI przez `GET /search`,
- podstawowe odpowiedzi modelu w web UI przez `GET /ask` i lokalna Ollame,
- ankieta A.5 w web UI przez `POST /assessment/a5` dla pierwszych 5 pozycji kontrolnych,
- asynchroniczne uruchamianie ankiety A.5 przez `POST /assessment/a5/start` i status `GET /jobs/{job_id}`,
- multi-query retrieval ankiety A.5 z deduplikacja i prostym scoringiem audytowym,
- rozszerzone metadane RAG i sasiednie chunki w kontekscie ankiety A.5,
- CLI do ingestii i wyszukiwania.

Obecny stan danych po testach klientow:

- klienci: tylko `Klient domyslny`,
- dokumenty klienta domyslnego: `1`.

Nie jest jeszcze gotowe:

- OCR dla skanowanych PDF,
- uwierzytelnianie,
- reranker,
- ewaluacja jakosci na wiekszym zbiorze pytan,
- docelowy pipeline ankietowy: query expansion, deduplikacja, reranking i ocena spelnienia przez LLM,
- trwale przechowywanie jobow ankietowych poza pamiecia procesu web,
- produkcyjny tryb czata z cytowaniami i kontrola halucynacji.

## Stack

- Docker Compose
- PostgreSQL 16 + `pgvector`
- Hugging Face Text Embeddings Inference `cpu-latest`
- Ollama `llama3.2:3b`
- Python, Typer, FastAPI, Uvicorn
- `pypdf`, `python-docx`, `psycopg`, `requests`

## Pliki dokumentacji

- `README.md` - szybki opis projektu, start stacka, import, wyszukiwanie i web UI.
- `docs/STATUS.md` - aktualny stan wdrozenia, komponenty, zweryfikowane komendy i ograniczenia.
- `docs/OPERATIONS.md` - runbook operacyjny: start, logi, import, wyszukiwanie, pytania do modelu, diagnostyka.
- `docs/RUNBOOK_NEW_SERVER.md` - kompletna instalacja i odtworzenie IODO na nowym serwerze z katalogu projektu, dumpa PostgreSQL albo ponownego importu.
- `docs/NEXT_STEPS.md` - kolejne kroki techniczne i ograniczenia, ktore nie sa jeszcze gotowymi funkcjami.
- `docs/WORKFLOW.md` - zasady aktualizowania dokumentacji po zmianach.

## Co sie ostatnio zmienilo

- 2026-07-09: Dodano `docs/RUNBOOK_NEW_SERVER.md`: wymagania hosta, uslugi Compose, modele, `.env`, wolumeny, instalacje Dockera, start, healthchecki, backup/restore i checklist koncowy dla odtworzenia IODO na nowym serwerze.
- 2026-07-09: Udokumentowano poprawke timeoutu Ollamy i odpornosci ankiety A.5 na bledy per punkt: `LLM_TIMEOUT_SECONDS=1800`, konfigurowalne `LLM_CONTEXT_MAX_CHARS`, `LLM_NUM_CTX`, `LLM_NUM_PREDICT` oraz `SPELNENIE: BLAD ANALIZY LLM` zamiast przerwania calej ankiety.
- 2026-07-09: Udokumentowano rozszerzone metadane RAG i sasiednie chunki dla ankiety: `document_id`, `chunk_index`, `client_name`, `adjacent_chunks`, role kontekstu, limit 5 trafien glownych / 14 fragmentow po rozszerzeniu, `build_context max_chars=8500` i `num_ctx=8192`.
- 2026-07-09: Udokumentowano obsluge klientow: tabela `clients`, `documents.client_id`, domyslny klient, dashboard per klient, import/search/ask/assessment filtrowane po `client_id` oraz asynchroniczne joby ankiety A.5 przez `POST /assessment/a5/start` i `GET /jobs/{job_id}`.
- 2026-07-09: Udokumentowano pierwsza poprawke retrievalu ankiety A.5: multi-query z pol `query`, `question`, `requirement`, `evidence`, deduplikacja po chunk id, scoring audytowy, finalny kontekst 10 unikalnych chunkow i pola diagnostyczne `audit_score`, `audit_query_count`, `audit_keyword_hits`, `audit_queries`.
- 2026-07-09: Dopisano docelowy plan wyszukiwania dla ankiet A.5 i kolejnych: query expansion -> hybrid search -> deduplikacja -> reranking -> LLM ocenia spelnienie; oceniono obecny chunking jako sensowna baze wymagajaca wzbogacenia metadanych, tabel, fragmentow dowodowych i pobierania sasiednich chunkow.
- 2026-07-08: Udokumentowano ankiete A.5 w web UI: `POST /assessment/a5`, plik `audit_prompts_A5.jsonl`, 5 pierwszych pozycji A.5.1.1-A.5.5.1, guardrails i ograniczenie wolnego synchronicznego wykonania na CPU.
- 2026-07-01: Dopisano zadanie przyszle dla trybu punktu ankietowego/audytowego: wiele pytan kontrolnych, wymagane dowody, osobne retrievale, scalanie kontekstu, cytowania i luki dowodowe.
- 2026-07-01: Udokumentowano poprawke promptu `/ask`: tryb audytowy dla polskich dokumentow prawnych i bezpieczenstwa, lepsza interpretacja slowa "organizacja" oraz test pytania o Polityke Bezpieczenstwa Informacji i polityki tematyczne SZBI.
- 2026-07-01: Udokumentowano usuwanie dokumentow z bazy przez `POST /documents/{document_id}/delete`; operacja usuwa rekord dokumentu oraz chunki/embeddingi, ale nie usuwa pliku uploadu.
