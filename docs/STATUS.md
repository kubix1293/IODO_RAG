# Status wdrozenia IODO RAG

Ostatnia aktualizacja: 2026-07-09

Cel pliku: aktualny stan wdrozenia lokalnego pipeline RAG, zweryfikowane komponenty, ograniczenia i komendy testowe.

Data stanu: 2026-07-09

## Cel

Zbudowano lokalny, self-hosted pipeline RAG dla polskich dokumentow prawnych i dokumentow bezpieczenstwa. System obsluguje dokumenty PDF z warstwa tekstowa oraz DOCX, zapisuje chunki w PostgreSQL z pgvector, korzysta z lokalnego serwera embeddingow TEI i ma podstawowa interpretacje wynikow przez lokalny model Ollama.

## Lokalizacja

Projekt znajduje sie w:

```bash
/opt/IODO
```

Wczesniejszy katalog roboczy `/home/maverick/IODO` zostal przeniesiony do `/opt/IODO`.

## Odtworzenie na nowym serwerze

Dedykowany runbook instalacji i migracji znajduje sie w:

```text
docs/RUNBOOK_NEW_SERVER.md
```

Dokument opisuje wymagania hosta, Docker Compose, porty, wolumeny, `.env`, modele, budowanie obrazow, start uslug, healthchecki, backup/restore PostgreSQL i checklist koncowy. Jest przeznaczony dla agenta, ktory dostaje katalog projektu na nowym serwerze i ma uruchomic system bez dodatkowego kontekstu.

Wazne fakty migracyjne:

- zrodlem projektu jest `/opt/IODO`,
- sam katalog projektu nie zawiera wolumenow Docker `postgres_data`, `hf_cache` i `ollama_data`,
- uploady sa w `/opt/IODO/data/uploads`,
- bez dumpa PostgreSQL albo backupu wolumenu `postgres_data` baze trzeba odtworzyc ponownym importem dokumentow,
- TEI i Ollama moga pobrac modele ponownie na nowym hoscie,
- po swiezej instalacji Ollamy wymagany jest `docker exec iodo-ollama-1 ollama pull llama3.2:3b`, jesli model nie jest juz w `ollama_data`.

## Uruchomione komponenty

Stack Docker Compose sklada sie z:

- `postgres`: PostgreSQL 16 z rozszerzeniem `pgvector`
- `tei`: Hugging Face Text Embeddings Inference na CPU
- `ollama`: lokalny serwer LLM
- `app`: kontener narzedziowy Python do ingestii i wyszukiwania
- `web`: interfejs web FastAPI/Uvicorn do importu, wyszukiwania i pytan do modelu

Sprawdzone uslugi:

- `iodo-postgres-1`: PostgreSQL/pgvector
- `iodo-tei-1`: TEI na `http://tei:80`, port hosta `8080`
- `iodo-ollama-1`: Ollama na `http://ollama:11434`, port hosta `11434`
- `iodo-web-1`: FastAPI/Uvicorn, porty hosta `80` i `8000`
- `app`: obraz narzedziowy CLI

Aktualny web UI zawiera:

- import PDF/DOCX,
- dashboard stanu bazy,
- tabela `Ostatnie dokumenty` z kolumna `Akcje` i przyciskiem `Usun`,
- sekcja `Klient` z wyborem aktywnego klienta i formularzem dodania klienta,
- liczniki dokumentow i chunkow liczone dla aktywnego klienta,
- formularz `Zapytaj dokumenty`,
- przycisk `Szukaj w dokumentach` dla `GET /search`,
- przycisk `Zapytaj model` dla `GET /ask`,
- sekcje `Ankieta A.5` z przyciskiem `Wykonaj ankiete A.5`; web UI uruchamia ankiete asynchronicznie przez `POST /assessment/a5/start`.

Aktualny adres hosta w sieci LAN podczas testow:

```text
192.168.1.14
```

Interfejs web byl lokalnie zweryfikowany pod:

```text
http://192.168.1.14/health
http://192.168.1.14:8000/health
http://127.0.0.1/health
http://127.0.0.1:8000/health
```

Endpoint `/health` zwrocil:

```json
{"status":"ok"}
```

## Model embeddingowy

Aktualny model:

```text
intfloat/multilingual-e5-small
```

Wymiar embeddingu:

```text
384
```

TEI:

```text
wewnatrz Compose: http://tei:80
host: http://127.0.0.1:8080
```

Uzasadnienie:

- model jest wielojezyczny i nadaje sie do dokumentow po polsku,
- jest znacznie lzejszy do self-hostingu na CPU niz `BAAI/bge-m3`,
- pasuje do obecnych zasobow hosta bez zawieszania startu TEI na rozgrzewaniu modelu.

Kod embeddingow w `app/iodo_rag/embeddings.py` dodaje prefiksy wymagane przez modele E5:

- `passage: ` dla chunkow dokumentow podczas ingestii,
- `query: ` dla zapytan wyszukiwania.

Embeddingi sa batchowane przez `EMBEDDING_BATCH_SIZE`, domyslnie `8`.

## Model LLM

Odpowiedzi z dokumentow obsluguje lokalna Ollama:

```text
LLM_URL=http://ollama:11434
LLM_MODEL=llama3.2:3b
LLM_TIMEOUT_SECONDS=1800
LLM_CONTEXT_MAX_CHARS=8500
LLM_NUM_CTX=8192
LLM_NUM_PREDICT=384
```

Model `llama3.2:3b` zostal pobrany lokalnie w kontenerze Ollama. `ollama list` pokazywal model `llama3.2:3b` o rozmiarze ok. `2.0 GB`.

Implementacja:

- `app/iodo_rag/llm.py`
- `GET /ask` w `app/iodo_rag/web.py`
- `answer_with_prompt(system_prompt, user_prompt, rows, settings)` dla ankiet uzywajacych promptow z JSONL

Prompt systemowy w `app/iodo_rag/llm.py` dziala teraz w trybie audytowym dla polskich dokumentow prawnych i bezpieczenstwa. Najwazniejsze zasady:

- slowo "organizacja" nalezy interpretowac jako podmiot wynikajacy z kontekstu, np. ICZMP, urzad, administrator albo inna nazwa z dokumentow,
- model nie ma wymagac doslownego powtorzenia tresci pytania, jesli kontekst zawiera rownowazne dowody,
- dla pytan kontrolnych/audytowych odpowiedz ma zaczynac sie od `Tak`, `Nie`, `Czesciowo` albo `Brak danych`,
- `Brak danych` ma byc wybierane tylko wtedy, gdy w kontekscie faktycznie nie ma przeslanek,
- odpowiedz ma zawierac 1-3 zdania uzasadnienia i wskazanie podstawy w kontekcie, np. `[1]`,
- przy wskazywaniu dowodu model ma podac dokument/plik, strone oraz sekcje/artykul/paragraf/punkt, jesli sa w metadanych,
- nadal obowiazuje zakaz porad prawnych poza trescia dokumentow.

Aktualne parametry wydajnosciowe:

- `build_context(..., max_chars=8500)`,
- `num_ctx=8192`,
- `num_predict=384`,
- `temperature=0.2`,
- timeout HTTP do Ollamy: `1800` sekund z `.env`.

Parametry kontekstu i generacji sa teraz konfigurowalne przez `Settings`:

- `llm_context_max_chars`,
- `llm_num_ctx`,
- `llm_num_predict`.

`llm.py` uzywa tych wartosci w `build_context(...)` i opcjach Ollamy zamiast wartosci hardcoded.

Wazne ograniczenie: na CPU endpoint `/ask` jest wolny. Test z `limit=1` trwal okolo 2-3 minuty po poprawce. Wiekszy limit albo dluzszy kontekst moze nadal byc zauwazalnie wolny.

Wazne ograniczenie jakosciowe: `llama3.2:3b` to maly model lokalny. Prompt audytowy poprawia zachowanie `/ask` na pytaniach kontrolnych, ale nie zastepuje ewaluacji jakosci odpowiedzi na wiekszym zestawie pytan regresyjnych.

## Ankieta A.5

Web UI ma osobna sekcje `Ankieta A.5` z przyciskiem `Wykonaj ankiete A.5`.

Endpointy:

```text
POST /assessment/a5/start
GET /jobs/{job_id}
POST /assessment/a5
```

`POST /assessment/a5/start` jest aktualna sciezka uzywana przez web UI. Tworzy job w pamieci procesu web i zwraca JSON ze statusem. `GET /jobs/{job_id}` zwraca aktualny status, log komunikatow, blad albo `result_html` po zakonczeniu. Stary `POST /assessment/a5` nadal istnieje jako synchroniczna sciezka kompatybilna.

Implementacja:

- `app/iodo_rag/audit.py`
- `app/iodo_rag/audit_prompts_A5.jsonl`
- `run_a5_assessment(settings)` w `audit.py`
- `load_a5_questions()` w `audit.py`
- `answer_with_prompt(...)` w `app/iodo_rag/llm.py`

Zakres obecnie wykonywany:

- `A.5.1.1`
- `A.5.2.1`
- `A.5.3.1`
- `A.5.4.1`
- `A.5.5.1`

`audit_prompts_A5.jsonl` zostal skopiowany do pakietu aplikacji z roboczego pliku `/home/maverick/prompty_RAG_A5.jsonl`. Wczesniejsza nazwa wspomniana przez uzytkownika, `prompt_RAG_A5.jason`, nie byla faktyczna nazwa pliku zrodlowego.

Przeplyw dla kazdej pozycji:

1. `load_a5_questions()` wybiera pierwsze pytanie (`question_no=1`) dla kontroli `A.5.1`-`A.5.5`.
2. `run_a5_assessment()` wykonuje `search_for_audit_item(item, settings, client_id=...)`.
3. `search_for_audit_item()` buduje kilka wariantow zapytan i uruchamia obecny `run_search`/`hybrid_search` dla kazdego wariantu.
4. Wyniki sa deduplikowane po `chunk id`, oceniane prostym scoringiem audytowym i ograniczane do puli kandydatow.
5. Dla najlepszych trafien glownych pobierane sa sasiednie chunki z tego samego dokumentu.
6. Rozszerzony kontekst RAG jest przekazywany do Ollamy przez `answer_with_prompt(...)`.
7. Wyniki sa renderowane jako HTML na stronie glownej.

Ankieta wykonuje pozycje sekwencyjnie, jedna po drugiej. Dla web UI dlugie wykonanie zostalo odsuniete z requestu HTTP do watku joba w procesie web. Frontend uzywa `fetch` i pollingu co 5 sekund, pokazujac status w panelu `job-panel`.

Komunikaty joba obejmuja:

- start zadania,
- rozpoczecie retrieval dla punktu,
- liczbe znalezionych fragmentow i przejscie do analizy,
- zakonczenie analizy punktu,
- wynik koncowy.

Job ma heartbeat co 120 sekund:

```text
Prace trwaja; jestem na etapie: ...
```

Ograniczenie: joby sa trzymane w pamieci procesu web (`JOBS`). Restart kontenera web kasuje historie i status jobow. Docelowo statusy powinny trafic do tabeli `jobs` albo do kolejki/pamieci zewnetrznej, np. Redis + Celery/RQ.

Po rozszerzeniu kontekstu RAG o metadane i sasiednie chunki pojedynczy request do Ollamy na CPU moze przekroczyc dawny timeout `600` sekund. Problem zgloszony 2026-07-09 mial postac:

```text
HTTPConnectionPool(host='ollama', port=11434): Read timed out. (read timeout=600)
```

Timeout Ollamy zwiekszono do `LLM_TIMEOUT_SECONDS=1800`. Dodatkowo `audit.py` lapie `requests.Timeout` oraz inne wyjatki podczas `answer_with_prompt(...)` dla pojedynczego punktu ankiety. Timeout albo blad jednego punktu nie przerywa calej ankiety: wynik punktu ma `SPELNENIE: BLAD ANALIZY LLM` z technicznym uzasadnieniem, a job przechodzi do kolejnego punktu. Asynchroniczny job nadal raportuje progres i heartbeat; przy timeoutie punktu dopisuje komunikat i kontynuuje nastepny punkt.

Pierwsza poprawka retrievalu ankiety A.5 jest wdrozona w `app/iodo_rag/audit.py`. Endpoint `/assessment/a5` i UX pozostaly bez zmian, ale wewnetrzny retrieval nie jest juz pojedynczym `run_search(..., limit=5)`.

Aktualny retrieval ankiety:

- `build_retrieval_queries(item)` tworzy warianty z pol `query`, `question`, `requirement`, `evidence` oraz kombinacji `control`/`control_name`/`question`/`evidence`/`requirement`,
- `search_for_audit_item(item, settings)` uruchamia obecny `run_search` dla kazdego wariantu,
- `AUDIT_QUERY_LIMIT = 12` okresla limit kandydatow na jeden wariant zapytania,
- `AUDIT_CONTEXT_LIMIT = 10` okresla pule kandydatow po multi-query, deduplikacji i scoringu,
- `AUDIT_PRIMARY_CONTEXT_LIMIT = 5` okresla liczbe glownych trafien uzytych jako seed do pobrania sasiedztwa,
- `AUDIT_EXPANDED_CONTEXT_LIMIT = 14` okresla maksymalna liczbe fragmentow po rozszerzeniu o sasiednie chunki,
- wyniki sa deduplikowane po `chunk id`,
- scoring audytowy laczy najlepszy `hybrid_score`, bonus za liczbe wariantow zapytan, ktore znalazly chunk, oraz bonus za slowa dowodowe i wazne terminy,
- do wierszy wynikowych dodawane sa pola diagnostyczne `audit_score`, `audit_query_count`, `audit_keyword_hits`, `audit_queries`.

Retrieval ankiety rozszerza teraz kontekst dla LLM o sasiednie chunki:

- `hybrid_search` zwraca dodatkowo `document_id`, `chunk_index` i `client_name`,
- `db.adjacent_chunks(conn, chunk_ids, client_id=None)` pobiera poprzedni, aktualny i nastepny chunk z tego samego dokumentu dla seed chunkow, z zachowaniem filtra `client_id`,
- `search.fetch_adjacent_chunks(...)` jest wrapperem uzywanym przez `audit.py`,
- po multi-query i scoringu `audit.py` bierze 5 najlepszych trafien glownych, dociaga ich sasiedztwo i zwraca maksymalnie 14 fragmentow do LLM,
- fragmenty maja pola `context_role`, `seed_chunk_id`, `neighbor_offset`, `audit_score`, `audit_query_count`, `audit_keyword_hits`, `audit_queries`,
- role kontekstu to `trafienie glowne`, `poprzedni chunk`, `nastepny chunk`.

Celem jest, aby LLM widzial nie tylko punktowe trafienie, ale tez krotki kontekst przed i po fragmencie.

Docelowy pipeline dla ankiet A.5 i kolejnych pozostaje:

```text
query expansion -> hybrid search -> deduplikacja -> reranking -> LLM ocenia spelnienie
```

Znaczenie etapow:

- query expansion: generowanie kilku wariantow zapytan dla wymagania, dowodow, nazw procedur, synonimow i typowych nazw dokumentow,
- hybrid search: obecne wyszukiwanie wektorowe + full-text jako pierwszy etap kandydatow,
- deduplikacja: laczenie wynikow z wielu wariantow zapytan i usuwanie powtorzonych lub prawie identycznych chunkow,
- reranking: lokalny reranker porzadkuje kandydatow pod konkretne wymaganie i dowody; jeszcze nie zostal wdrozony,
- LLM: ocenia spelnienie na podstawie wybranych fragmentow, opisuje dowody, braki i status `TAK`/`CZESCIOWO`/`NIE`/`BRAK DANYCH`.

Dodatkowe guardrails w `audit.py` dla odpowiedzi ankietowych:

- `referencja: brak referencji` oznacza brak wyodrebnionej referencji/metadanych, a nie brak dowodu,
- tresc fragmentu, nazwa dokumentu i strona moga byc dowodem,
- przy czesciowym potwierdzeniu model ma wybierac `CZESCIOWO` zamiast `NIE`,
- `NIE` ma byc uzywane tylko przy jawnym zaprzeczeniu w dokumentach,
- odpowiedz ma opisywac zarowno potwierdzone elementy, jak i braki.
- odpowiedz/dowod ma wskazywac najbardziej konkretna lokalizacje: dokument/plik, strone, sekcje, artykul, paragraf albo punkt, jesli sa w metadanych,
- fragmenty `poprzedni chunk` i `nastepny chunk` sa kontekstem pomocniczym dla `trafienie glowne`, a nie osobnym trafieniem.

`llm.build_context()` buduje teraz bogatsze naglowki kontekstu. Kazdy blok zawiera:

- klienta,
- dokument i nazwe pliku,
- strone albo zakres stron,
- sekcje/artykul/paragraf/punkt,
- `chunk_index`,
- role kontekstu,
- `audit_score`, jesli jest dostepny.

Limit kontekstu zostal zwiekszony do `max_chars=8500`, a `num_ctx` dla Ollamy do `8192`.

Wazne ograniczenie: pelny test 5 pozycji przed dodaniem guardrails zwrocil HTML z wynikami, ale trwal okolo 21 minut na CPU. Po dodaniu guardrails wykonano szybkie testy ladowania pytan, healthchecka i renderowania sekcji UI. Po pierwszej poprawce retrievalu przetestowano etap retrieval dla wszystkich 5 punktow, bez ponownego pelnego przebiegu ankiety z LLM.

## Klienci

Dodano model klienta w bazie:

```text
clients(id, name unique, created_at)
documents.client_id
documents_client_idx
```

Startup aplikacji web wykonuje `ensure_schema()`:

- tworzy tabele `clients`, jesli jej nie ma,
- tworzy klienta `Klient domyslny`, jesli go nie ma,
- dodaje `documents.client_id`, jesli kolumny nie ma,
- przypisuje istniejace dokumenty bez `client_id` do klienta domyslnego,
- tworzy indeks `documents_client_idx` na `(client_id, created_at DESC, id DESC)`.

`/opt/IODO/db/init.sql` zostal zaktualizowany dla swiezych instalacji: tworzy `clients`, dodaje `client_id` w `documents` i indeks `documents_client_idx`.

Web UI ma sekcje `Klient`:

- wybor aktywnego klienta,
- formularz dodania nowego klienta przez `POST /clients`,
- licznik dokumentow i chunkow per klient,
- dashboard i lista dokumentow filtrowane do aktywnego klienta.

Import dokumentow w web UI wymaga wybranego klienta. `ingest_path(..., client_id=...)` zapisuje dokument z tym klientem. Usuwanie dokumentu zachowuje `client_id` w redirect, zeby operator pozostawal w kontekscie aktywnego klienta.

Search, ask i assessment sa filtrowane po `client_id`. `hybrid_search(..., client_id=...)` filtruje kandydatow przez `documents.client_id`.

Finalny stan klientow po testach 2026-07-09:

- `Klient domyslny`: 1 dokument,
- klienci testowi utworzeni podczas testow zostali usunieci.

## Baza danych

Schemat inicjalizacyjny znajduje sie w:

```bash
/opt/IODO/db/init.sql
```

Najwazniejsze tabele:

- `clients`: klienci/tenanci dokumentow, `name` jest unikalne
- `documents`: metadane plikow zrodlowych
- `document_chunks`: tekst chunkow, metadane, `embedding vector(384)` oraz kolumna `tsvector`

Relacja `document_chunks.document_id REFERENCES documents(id) ON DELETE CASCADE` usuwa chunki i embeddingi z bazy przy usunieciu rekordu dokumentu.

Stan po ostatnich testach klientow:

- tylko `Klient domyslny`,
- dokumenty klienta domyslnego: `1`.

Wyszukiwanie jest hybrydowe:

- podobienstwo wektorowe przez pgvector,
- full-text search PostgreSQL po tresci chunkow,
- ranking laczony w `iodo_rag.db.hybrid_search`.

`hybrid_search` zwraca teraz metadane potrzebne do budowy audytowego kontekstu: `document_id`, `chunk_index`, `client_id`, `client_name`, `source_file`, `document_title`, `page_from`, `page_to`, `section`, `article`, `paragraph`, `point`.

Chunking w `app/iodo_rag/chunking.py` rozpoznaje podstawowe typy dokumentow:

- akty/dokumenty prawne: sekcje, artykuly, ustepy i punkty,
- Markdown: naglowki jako sciezka `heading_path`,
- proza: akapity z rekurencyjnym podzialem po akapitach, liniach, zdaniach i slowach.

Dla PDF parser dodaje znaczniki stron `[PAGE n]`, a chunking zapisuje zakres stron jako `page_from` i `page_to`, jesli da sie go wyliczyc.

Obecne parametry chunkingu:

```text
CHUNK_TARGET_CHARS=3500
CHUNK_OVERLAP_CHARS=500
```

Ocena obecnego chunkingu: jest sensowna baza dla dokumentow prawnych, Markdown i prozy. Zachowuje podstawowa strukture dokumentu, zakres stron i overlap pelnymi blokami. Dla ankiet i dowodow audytowych trzeba go jednak rozbudowac, bo aktualny embedding powstaje z samego `chunk["text"]`, a czesc kontekstu dokumentu jest tylko w osobnych kolumnach/metadanych.

Kierunki rozbudowy chunkingu dla ankiet:

- dodawac do tekstu embeddingu kontekst dokumentu i metadane, np. tytul dokumentu, sciezke naglowkow, sekcje, artykul, ustep, punkt, strony i typ dokumentu,
- lepiej zachowywac tabele oraz metadane zatwierdzenia, takie jak wlasciciel dokumentu, data zatwierdzenia, wersja, historia zmian i podpisy,
- tworzyc mniejsze lub bardziej logiczne fragmenty dowodowe tam, gdzie jeden chunk 3500 znakow miesza kilka wymagan,
- zachowac mozliwosc pobrania sasiednich chunkow tego samego dokumentu przy budowie kontekstu dla LLM.

## Obslugiwane pliki

Obecnie obslugiwane sa:

- `.pdf` z tekstem mozliwym do ekstrakcji,
- `.docx`.

Skanowane PDF-y wymagaja osobnego OCR przed ingestia. OCR nie zostal jeszcze wdrozony.

## Endpointy web

- `GET /` - dashboard, import, formularz wyszukiwania i pytan do modelu.
- `POST /clients` - dodanie albo wybranie klienta po nazwie; po sukcesie redirect `303` z `client_id`.
- `POST /upload` - upload jednego lub wielu plikow `.pdf`/`.docx` do `/data/uploads` i ingestia dla wybranego `client_id`.
- `POST /documents/{document_id}/delete` - usuniecie dokumentu z PostgreSQL/pgvector; usuwa tez chunki przez `ON DELETE CASCADE`, ale nie usuwa pliku z `/data/uploads`.
- `GET /search?q=...&limit=...&client_id=...` - wyszukiwanie hybrydowe w aktywnym kliencie; limit jest ograniczany do zakresu `1..20`.
- `GET /ask?q=...&limit=...&client_id=...` - wyszukiwanie w aktywnym kliencie + odpowiedz Ollamy na podstawie znalezionych fragmentow; limit jest ograniczany do zakresu `1..10`.
- `POST /assessment/a5/start` - asynchroniczne uruchomienie ankiety A.5 dla aktywnego klienta; zwraca JSON joba.
- `GET /jobs/{job_id}` - status joba ankiety A.5, komunikaty, blad albo `result_html` po zakonczeniu.
- `POST /assessment/a5` - synchroniczne wykonanie ankiety A.5; sciezka kompatybilna, nadal filtrowana po `client_id`.
- `GET /health` - healthcheck aplikacji.

`/ask` w przypadku bledu modelu zachowuje znalezione `search_rows`, zeby operator widzial wyniki retrievalu zamiast pustej listy.

`POST /documents/{document_id}/delete` po sukcesie zwraca redirect `303` na strone glowna z komunikatem `Usunieto dokument z bazy: ...`. Jesli dokument nie istnieje, zwraca redirect `303` z bledem `Dokument ... nie istnieje.`

## Wykonane poprawki

- Zainstalowano Docker/Compose oraz narzedzia wymagane do pracy z projektem.
- Przeniesiono projekt do `/opt/IODO`.
- Uruchomiono PostgreSQL z pgvector.
- Uruchomiono TEI na CPU.
- Zmieniono model embeddingowy z `BAAI/bge-m3` na `intfloat/multilingual-e5-small`.
- Dopasowano wymiar wektora w bazie i konfiguracji do `384`.
- Dodano webowy interfejs importu dokumentow w `app/iodo_rag/web.py`.
- Dodano dashboard web pokazujacy liczbe dokumentow, chunkow i ostatnie 25 dokumentow.
- Dodano upload wielu plikow PDF/DOCX do `/opt/IODO/data/uploads`.
- Dodano helper `delete_document(conn, *, document_id: int)` w `app/iodo_rag/db.py`.
- Dodano usuwanie dokumentow z bazy przez web UI: kolumne `Akcje`, formularz POST i endpoint `POST /documents/{document_id}/delete`.
- Dodano formularz `Zapytaj dokumenty`, endpoint `GET /search` i przycisk `Szukaj w dokumentach`.
- Dodano podstawowa integracje z Ollama: `app/iodo_rag/llm.py`, endpoint `GET /ask`, przycisk `Zapytaj model`.
- Dodano ankiete A.5 w web UI: sekcje `Ankieta A.5`, przycisk `Wykonaj ankiete A.5` i endpoint `POST /assessment/a5`.
- Dodano obsluge klientow: `clients`, `documents.client_id`, `POST /clients`, wybor aktywnego klienta w web UI oraz dashboard per klient.
- Dodano `ensure_schema()` w `db.py` i uruchamianie migracji schematu na starcie web.
- Zaktualizowano `db/init.sql` dla swiezych instalacji z klientami.
- Zmieniono `ingest_path` tak, aby przyjmowal `client_id` i zapisywal dokument z klientem.
- Przefiltrowano `search`, `/ask` i ankiete A.5 po `client_id`.
- Dodano asynchroniczne joby ankiety A.5: `POST /assessment/a5/start`, `GET /jobs/{job_id}`, polling JS co 5 sekund i heartbeat co 120 sekund.
- Dodano `app/iodo_rag/audit.py` z `load_a5_questions()` i `run_a5_assessment()`.
- Dodano `app/iodo_rag/audit_prompts_A5.jsonl` z promptami ankiety A.5.
- Dodano `answer_with_prompt(system_prompt, user_prompt, rows, settings)` w `app/iodo_rag/llm.py`.
- Dodano guardrails ankietowe w `audit.py` dla interpretacji fragmentow bez referencji, czesciowego potwierdzenia i luk dowodowych.
- Rozszerzono retrieval ankiety A.5 w `audit.py`: `build_retrieval_queries()`, `search_for_audit_item()`, deduplikacja po chunk id, scoring audytowy i pola diagnostyczne `audit_score`, `audit_query_count`, `audit_keyword_hits`, `audit_queries`.
- Rozszerzono metadane RAG i kontekst ankiety: `hybrid_search` zwraca `document_id`, `chunk_index`, `client_name`, dodano `adjacent_chunks()` i `fetch_adjacent_chunks()`, a `audit.py` dociaga poprzedni/nastepny chunk dla 5 najlepszych trafien.
- Zwiekszono `build_context` do `max_chars=8500` i `num_ctx` Ollamy do `8192`; naglowki kontekstu zawieraja klienta, dokument, plik, strone, referencje, `chunk_index`, role kontekstu i `audit_score`.
- Dodano konfigurowalne parametry LLM w `config.py`: `llm_context_max_chars`, `llm_num_ctx`, `llm_num_predict`.
- Zmieniono `.env` i `.env.example`: `LLM_TIMEOUT_SECONDS=1800`, `LLM_CONTEXT_MAX_CHARS=8500`, `LLM_NUM_CTX=8192`, `LLM_NUM_PREDICT=384`.
- Uodporniono ankiete A.5 na timeouty i bledy LLM per punkt: blad jednego punktu zapisuje `SPELNENIE: BLAD ANALIZY LLM` i nie przerywa calej ankiety.
- Przestawiono `SYSTEM_PROMPT` w `app/iodo_rag/llm.py` na tryb audytowy dla polskich dokumentow prawnych i bezpieczenstwa.
- Dodano usluge `ollama` w `docker-compose.yml` z portem `11434` i wolumenem `ollama_data`.
- Dodano zmienne `LLM_URL`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS` do `.env` i `.env.example`.
- Naprawiono pierwsze timeouty `/ask` przez zmniejszenie kontekstu i zwiekszenie timeoutu.
- W `/ask` przy bledzie modelu zachowywane sa znalezione wyniki wyszukiwania.
- Dodano zaleznosci `fastapi`, `python-multipart` i `uvicorn[standard]`.
- Wystawiono usluge `web` w Docker Compose na portach `80` i `8000`.
- Naprawiono blad importu `422 Unprocessable Entity` z TEI przez batchowanie embeddingow po maksymalnie 8 tekstow.
- Dodano pin `click==8.1.8`, poniewaz Typer mial problem zgodnosci z Click 8.2.
- Dodano `docs/WORKFLOW.md` z zasada uzywania `agent_to_docs` po zakonczonych pracach i testach.
- Uporzadkowano embeddingi E5 przez prefiksy `passage:` dla dokumentow i `query:` dla zapytan.
- Rozszerzono chunking o strukture dokumentow prawnych, naglowki Markdown, zakresy stron i fallback dla prozy.

## Zweryfikowane testy koncowe

Healthcheck:

```bash
curl http://127.0.0.1/health
```

Wynik:

```json
{"status":"ok"}
```

Wyszukiwanie web:

```bash
curl "http://127.0.0.1/search?q=administrator%20danych&limit=1"
```

Wynik: strona HTML z 1 wynikiem oraz dashboardem pokazujacym `2` dokumenty i `96` chunkow. Wczesniejszy test z `limit=3` zwracal 3 wyniki.

Pytanie do modelu:

```bash
curl "http://127.0.0.1/ask?q=administrator%20danych&limit=1"
```

Wynik: strona HTML z sekcja `Odpowiedz modelu` i komunikatem:

```text
Odpowiedz wygenerowana na podstawie 1 fragmentow.
```

Ankieta A.5:

- pelny test `POST /assessment/a5` przed guardrails zwrocil HTML z 5 wynikami, ale trwal okolo 21 minut na CPU,
- po guardrails `/health` zwrocil `{"status":"ok"}`,
- backend zaladowal 5 pytan: `['A.5.1.1', 'A.5.2.1', 'A.5.3.1', 'A.5.4.1', 'A.5.5.1']`,
- strona glowna renderowala sekcje `Ankieta A.5` i przycisk `Wykonaj ankiete A.5`.

Testy retrievalu ankiety A.5 po pierwszej poprawce, wykonane 2026-07-09:

- `python3 -m py_compile /home/maverick/audit.py.work` zakonczyl sie OK,
- `docker compose build web` zakonczyl sie OK,
- `docker compose up -d web` zakonczyl sie OK,
- `/health` zwrocil OK,
- backend zaladowal 5 pytan `A.5.1.1`-`A.5.5.1`,
- pierwszy punkt wygenerowal 9 wariantow zapytan,
- retrieval `A.5.1.1` zwrocil 10 unikalnych chunkow; top trafienia mialy `audit_query_count` 6-8 i `audit_keyword_hits` 9-11,
- retrieval dla wszystkich pieciu punktow zwrocil po 10 kandydatow,
- web UI nadal renderowal sekcje `Ankieta A.5` i przycisk `Wykonaj ankiete A.5`,
- pelnego `/assessment/a5` z LLM nie uruchomiono ponownie ze wzgledu na znany czas dzialania na CPU; przetestowany zostal zmieniony etap retrieval.

Testy klientow i asynchronicznych statusow ankiety, wykonane 2026-07-09:

- `py_compile` dla `db.py`, `ingest.py`, `search.py`, `audit.py`, `web.py` zakonczyl sie OK,
- `docker compose build web` zakonczyl sie OK,
- `docker compose up -d web` zakonczyl sie OK,
- `/health` zwrocil OK,
- migracja utworzyla klienta domyslnego i przypisala istniejacy dokument: `Klient domyslny` ma 1 dokument,
- importy modulow w kontenerze przeszly OK,
- strona glowna renderowala `Aktywny klient`, `Nowy klient`, `Ankieta A.5`, `/assessment/a5/start` i `job-panel`,
- `/search?client_id=1&q=polityka&limit=2` zwrocil 2 wyniki dla `Klient domyslny`,
- `POST /clients` sprawdzono przez utworzenie klienta testowego; endpoint zwrocil `303` z `client_id`, a klient testowy zostal usuniety,
- asynchroniczny job ankiety przetestowano na tymczasowym kliencie bez dokumentow: job przeszedl `running -> done`, zwrocil komunikaty dla `A.5.1.1`-`A.5.5.1` i `result_html`; klient testowy zostal usuniety,
- finalny stan klientow po testach: tylko `Klient domyslny` z 1 dokumentem.

Testy rozszerzonych metadanych RAG i sasiednich chunkow, wykonane 2026-07-09:

- zmienione pliki aplikacji: `db.py`, `search.py`, `audit.py`, `llm.py`, `web.py`,
- `py_compile` dla `db.py`, `search.py`, `audit.py`, `llm.py`, `web.py` zakonczyl sie OK,
- `docker compose build web` zakonczyl sie OK,
- `docker compose up -d web` zakonczyl sie OK,
- `/health` zwrocil OK,
- importy w kontenerze przeszly OK,
- retrieval `A.5.1.1` dla `client_id=1` zwrocil 13 fragmentow: `poprzedni chunk`, `trafienie glowne`, `nastepny chunk`; wyniki zawieraly `document_title`, `page_from`/`page_to` i `chunk_index`,
- `build_context` pokazal naglowki z klientem, dokumentem, plikiem, strona, referencja, `chunk_index`, `rola_kontekstu` i `audit_score`,
- retrieval dla wszystkich pieciu punktow A.5 zwrocil 13-14 fragmentow: 5 trafien glownych oraz poprzednie/nastepne chunki tam, gdzie istnieja,
- pelnej analizy LLM `/assessment/a5` nie uruchomiono ponownie ze wzgledu na znany dlugi czas CPU; testowany byl zmieniony etap retrieval/kontekstu.

Testy poprawki timeoutu Ollamy i odpornosci ankiety na bledy LLM per punkt:

- `py_compile` dla `config.py`, `llm.py`, `audit.py` zakonczyl sie OK,
- `docker compose build web` zakonczyl sie OK,
- `docker compose up -d web` zakonczyl sie OK,
- `/health` zwrocil OK,
- w kontenerze web `get_settings()` zwrocil `1800 8500 8192 384`,
- import `iodo_rag.web` zakonczyl sie OK,
- logi web nie pokazaly bledow startu.

Przykladowa odpowiedz modelu dotyczyla art. 158 i przejscia administratora bezpieczenstwa informacji w inspektora ochrony danych.

Po zmianach przebudowano i odtworzono web:

```bash
cd /opt/IODO
sudo docker compose build web
sudo docker compose up -d web
```

Test regresyjny po zmianie promptu `/ask`:

```bash
python3 -m py_compile /home/maverick/llm.py.work
curl http://127.0.0.1/health
curl "http://127.0.0.1/ask?q=Czy%20organizacja%20posiada%20formalnie%20zdefiniowan%C4%85%20polityk%C4%99%20bezpiecze%C5%84stwa%20informacji%20oraz%20polityki%20tematyczne&limit=5"
```

Wyniki:

- kompilacja `llm.py.work` zakonczyla sie poprawnie,
- po przebudowie i odtworzeniu `web` endpoint `/health` zwrocil `{"status":"ok"}`,
- `/ask` dla pytania o formalnie zdefiniowana Polityke Bezpieczenstwa Informacji i polityki tematyczne odpowiedzial poprawnie od `Tak`,
- odpowiedz wskazala, ze w dokumentach jest opis Polityki Bezpieczenstwa Informacji oraz dedykowanych polityk tematycznych w ramach II poziomu SZBI,
- mechanika RAG zostala pozniej rozszerzona o metadane, sasiednie chunki, `max_chars=8500` i `num_ctx=8192`; `num_predict=384` pozostaje bez zmian.

Usuwanie dokumentow:

- `python3 -m py_compile /home/maverick/db.py.work /home/maverick/web.py.work` zakonczyl sie poprawnie.
- Strona `/` renderowala kolumne `Akcje` i przyciski `Usun` dla dokumentow ID 1 i 2.
- `POST /documents/999999/delete` zwrocil `303` z komunikatem bledu `Dokument 999999 nie istnieje.`
- Tymczasowy rekord testowy `__delete_test__.pdf` dostal ID 3.
- `POST /documents/3/delete` zwrocil `303` z komunikatem `Usunieto dokument z bazy: delete-test`.
- Po usunieciu `SELECT count(*) FROM documents WHERE source_file='__delete_test__.pdf'` zwrocil `0`.
- Liczniki po tescie wrocily do `2` dokumentow i `96` chunkow.
- `/search?q=administrator%20danych&limit=1` nadal zwracal 1 wynik.

## Znane ograniczenia

- Brak OCR dla skanowanych PDF.
- Usuwanie dokumentu kasuje rekord i chunki/embeddingi z bazy, ale nie usuwa pliku z `/data/uploads`.
- `/ask` na CPU jest wolny; test `limit=1` trwal okolo 2-3 minuty.
- Podstawowy LLM nie ma jeszcze twardego cytowania zrodel ani ewaluacji jakosci.
- Brak rerankera wynikow.
- Brak uwierzytelniania w interfejsie web.
- Brak osobnego API integracyjnego z autoryzacja dla aplikacji zewnetrznych.
- Brak ewaluacji jakosci na rzeczywistym zbiorze pytan.
- Aktualny model embeddingowy jest kompromisem pod CPU; dla wyzszej jakosci mozna wrocic do mocniejszego modelu po zapewnieniu lepszych zasobow.
