# Runbook operacyjny IODO RAG

Ostatnia aktualizacja: 2026-07-09

Cel pliku: operacyjne komendy utrzymania, importu, wyszukiwania, pytan do modelu i diagnostyki stacka `/opt/IODO`.

## Katalog projektu

```bash
cd /opt/IODO
```

## Nowy serwer albo migracja

Pelna procedura instalacji i odtworzenia systemu na nowym serwerze jest w:

```text
docs/RUNBOOK_NEW_SERVER.md
```

Uzyj jej, gdy agent dostaje skopiowany katalog projektu i ma odtworzyc srodowisko od zera. Dokument zawiera wymagania hosta, zaleznosci, uslugi Compose, porty, wolumeny, `.env`, start, healthchecki, backup/restore PostgreSQL oraz checklist koncowy.

Kluczowa roznica wzgledem codziennej operacji: skopiowanie samego katalogu `/opt/IODO` nie przenosi wolumenow Docker `postgres_data`, `hf_cache` i `ollama_data`. Bez backupu/restore PostgreSQL baza bedzie pusta, a modele TEI/Ollama zostana pobrane ponownie.

## Start uslug

```bash
sudo docker compose up -d postgres tei ollama web
```

Pierwszy start TEI moze trwac dluzej, poniewaz model embeddingowy musi zostac pobrany do wolumenu cache. Pierwsze pytanie do Ollamy tez moze byc wolne, jesli model dopiero sie laduje.

## Status kontenerow

```bash
sudo docker compose ps
```

Oczekiwany stan:

- `postgres`: `healthy`
- `tei`: `healthy`, hostowo port `8080`
- `ollama`: `Up`, hostowo port `11434`
- `web`: `Up`, porty `80->8000` i `8000->8000`

## Logi

PostgreSQL:

```bash
sudo docker logs --tail 100 iodo-postgres-1
```

TEI:

```bash
sudo docker logs --tail 100 iodo-tei-1
```

Ollama:

```bash
sudo docker logs --tail 100 iodo-ollama-1
```

Web UI:

```bash
sudo docker logs --tail 100 iodo-web-1
```

## Budowanie i odtwarzanie web

Po zmianach w kodzie aplikacji web:

```bash
sudo docker compose build web
sudo docker compose up -d web
```

Dla obrazu narzedziowego CLI:

```bash
sudo docker compose --profile tools build app
```

## Interfejs web

Uruchomienie interfejsu:

```bash
sudo docker compose up -d postgres tei ollama web
```

Adres:

```text
http://192.168.1.14
http://192.168.1.14:8000
http://localhost
http://localhost:8000
```

`192.168.1.14` to adres LAN hosta odczytany podczas testow. Jesli adres zmieni sie przez DHCP, nalezy sprawdzic aktualny adres hosta, np. przez `ip -4 -br addr`.

Interfejs pozwala:

- wybrac aktywnego klienta i dodac nowego klienta,
- importowac jeden lub wiele plikow `.pdf`/`.docx`,
- sprawdzac liczbe dokumentow i chunkow dla aktywnego klienta,
- przegladac ostatnie dokumenty aktywnego klienta,
- usuwac dokumenty z PostgreSQL/pgvector przyciskiem `Usun`,
- wyszukiwac fragmenty aktywnego klienta przez `GET /search`,
- zadawac pytania lokalnemu modelowi przez `GET /ask`,
- uruchamiac ankiete A.5 asynchronicznie przez `POST /assessment/a5/start`.

Pliki uploadowane przez web sa zapisywane w `/opt/IODO/data/uploads`, a nastepnie przechodza przez ten sam pipeline ingestii co CLI: parsowanie tekstu, chunking, embedding w TEI i zapis do PostgreSQL/pgvector. Web UI wymaga wybranego klienta; dokument jest zapisywany z `documents.client_id`.

Kontener `web` startuje przez Uvicorn:

```text
iodo_rag.web:app --host 0.0.0.0 --port 8000
```

Healthcheck aplikacji web:

```bash
curl http://localhost/health
curl http://localhost:8000/health
curl http://192.168.1.14/health
curl http://192.168.1.14:8000/health
```

Oczekiwany wynik:

```json
{"status":"ok"}
```

Aktualne mapowanie portow:

```text
80 -> 8000/tcp w kontenerze web
8000 -> 8000/tcp w kontenerze web
8080 -> 80/tcp w kontenerze tei
11434 -> 11434/tcp w kontenerze ollama
```

Sprawdzenie mapowania:

```bash
sudo docker port iodo-web-1
sudo docker port iodo-tei-1
sudo docker port iodo-ollama-1
sudo ss -ltnp
```

## Pomoc CLI

```bash
sudo docker compose --profile tools run --rm app --help
```

## Klienci

Web UI ma sekcje `Klient`:

- `Aktywny klient` - lista klientow z liczba dokumentow i chunkow,
- `Nowy klient` - formularz dodania klienta,
- dashboard i lista dokumentow ograniczone do aktywnego klienta.

Endpoint:

```text
POST /clients
```

Zachowanie:

- normalizuje nazwe klienta,
- tworzy klienta albo zwraca istniejacego po tej samej nazwie,
- po sukcesie zwraca redirect `303` na `/?client_id=...`.

Migracja schematu uruchamia sie na starcie web przez `ensure_schema()`:

- tworzy `clients`,
- tworzy `Klient domyslny`,
- dodaje `documents.client_id`,
- przypisuje stare dokumenty bez klienta do klienta domyslnego,
- tworzy `documents_client_idx`.

Finalny stan po testach 2026-07-09:

```text
Klient domyslny: 1 dokument
```

Klienci testowi uzyci do testow zostali usunieci.

## Import dokumentow

Import przez web UI:

```text
http://192.168.1.14
http://192.168.1.14:8000
```

Przed importem wybrac aktywnego klienta. Formularz uploadu wysyla `client_id`, a `ingest_path(..., client_id=...)` zapisuje dokument w tym kliencie.

Import przez CLI: umiesc dokumenty w:

```bash
/opt/IODO/data/inbox
```

Import calego katalogu:

```bash
sudo docker compose --profile tools run --rm app ingest /data/inbox
```

Import pojedynczego pliku:

```bash
sudo docker compose --profile tools run --rm app ingest /data/inbox/nazwa_pliku.pdf
```

## Stan bazy

Aktualny stan po ostatnich testach klientow:

```text
Klient domyslny: 1 dokument
```

Dashboard na stronie glownej pokazuje wartosci per aktywny klient. W razie potrzeby mozna sprawdzic baze z kontenera PostgreSQL:

```bash
sudo docker exec iodo-postgres-1 psql -U iodo -d iodo -c "select cl.id, cl.name, count(distinct d.id) as documents, count(c.id) as chunks from clients cl left join documents d on d.client_id = cl.id left join document_chunks c on c.document_id = d.id group by cl.id order by cl.id;"
```

## Usuwanie dokumentow z bazy

Web UI:

- w tabeli `Ostatnie dokumenty` kazdy dokument ma kolumne `Akcje`,
- przycisk `Usun` wysyla `POST /documents/{document_id}/delete`,
- przegladarka pokazuje potwierdzenie JS `Usunac ten dokument z bazy?`.

Endpoint:

```text
POST /documents/{document_id}/delete
```

Zachowanie:

- helper `iodo_rag.db.delete_document` wykonuje `DELETE FROM documents WHERE id = %s RETURNING id, source_file, title`,
- chunki i embeddingi sa usuwane z PostgreSQL/pgvector przez `ON DELETE CASCADE` na `document_chunks.document_id`,
- po sukcesie aplikacja zwraca redirect `303` na `/?message=Usunieto dokument z bazy: ...`,
- gdy dokument nie istnieje, aplikacja zwraca redirect `303` na `/?error=Dokument ... nie istnieje.`

Wazne: ta operacja nie usuwa pliku zrodlowego z `/data/uploads`. Usuwa tylko rekord dokumentu oraz powiazane chunki/embeddingi z bazy.

Formularz usuwania przekazuje `client_id`, a redirect zachowuje kontekst aktywnego klienta.

Testy wykonane po wdrozeniu:

```bash
python3 -m py_compile /home/maverick/db.py.work /home/maverick/web.py.work
curl http://127.0.0.1/health
curl -i -X POST http://127.0.0.1/documents/999999/delete
curl -i -X POST http://127.0.0.1/documents/3/delete
```

Wyniki testow:

- `/health` zwrocil `{"status":"ok"}`,
- strona `/` renderowala kolumne `Akcje` i przyciski `Usun`,
- nieistniejacy dokument zwrocil redirect `303` z bledem `Dokument 999999 nie istnieje.`,
- tymczasowy rekord `__delete_test__.pdf` zostal usuniety z bazy,
- po tescie liczniki wrocily do `2` dokumentow i `96` chunkow,
- `/search?q=administrator%20danych&limit=1` nadal zwracal 1 wynik.

## Wyszukiwanie

Web:

```bash
curl "http://127.0.0.1/search?q=administrator%20danych&limit=1"
```

Endpoint:

```text
GET /search?q=<pytanie>&limit=<1..20>&client_id=<id>
```

`/search` uzywa `iodo_rag.search.search`, ktore tworzy embedding zapytania przez TEI i uruchamia `hybrid_search` w PostgreSQL/pgvector. Jesli podano `client_id`, kandydaci sa filtrowani przez `documents.client_id`.

Test koncowy:

- `http://127.0.0.1/search?q=administrator%20danych&limit=1` zwrocil 1 wynik,
- wczesniejszy test z `limit=3` zwrocil 3 wyniki,
- historycznie, przed wprowadzeniem klientow, dashboard pokazywal 2 dokumenty i 96 chunkow; aktualnie dashboard pokazuje liczniki per aktywny klient.

CLI:

```bash
sudo docker compose --profile tools run --rm app search "kontrola dostepu do systemow teleinformatycznych" --limit 10
```

Komenda tworzy embedding zapytania z prefiksem `query: ` i uruchamia wyszukiwanie hybrydowe:

- top kandydaci wektorowi przez `embedding <=> query_embedding`,
- top kandydaci tekstowi przez `plainto_tsquery('simple', query)`,
- ranking laczony przez sume odwrotnosci rang.

Wyniki zawieraja score, plik zrodlowy, referencje strukturalne jesli sa dostepne oraz fragment chunku.

## Pytania do modelu

Web:

```bash
curl "http://127.0.0.1/ask?q=administrator%20danych&limit=1"
```

Endpoint:

```text
GET /ask?q=<pytanie>&limit=<1..10>&client_id=<id>
```

`/ask` wykonuje:

1. wyszukiwanie przez `iodo_rag.search.search` w aktywnym `client_id`,
2. budowe kontekstu w `iodo_rag.llm.build_context`,
3. wywolanie Ollamy `POST /api/generate`,
4. render odpowiedzi w sekcji `Odpowiedz modelu`.

Aktualne ustawienia LLM:

```env
LLM_URL=http://ollama:11434
LLM_MODEL=llama3.2:3b
LLM_TIMEOUT_SECONDS=1800
LLM_CONTEXT_MAX_CHARS=8500
LLM_NUM_CTX=8192
LLM_NUM_PREDICT=384
```

Parametry generacji w `app/iodo_rag/llm.py`:

```text
max_chars=8500
num_ctx=8192
num_predict=384
temperature=0.2
```

Te wartosci sa konfigurowalne przez `.env`:

- `LLM_CONTEXT_MAX_CHARS`,
- `LLM_NUM_CTX`,
- `LLM_NUM_PREDICT`.

Prompt systemowy w `app/iodo_rag/llm.py` jest ustawiony na tryb audytowy dla polskich dokumentow prawnych i bezpieczenstwa. Dla pytan kontrolnych `/ask` powinien zaczynac odpowiedz od jednego z: `Tak`, `Nie`, `Czesciowo`, `Brak danych`, a nastepnie podac krotkie uzasadnienie z podstawa w kontekcie, np. `[1]`. Slowo "organizacja" jest interpretowane jako podmiot wynikajacy ze znalezionych dokumentow, a `Brak danych` powinno byc uzywane tylko wtedy, gdy kontekst nie zawiera przeslanek. Gdy model wskazuje dowod, ma podac konkretna lokalizacje: dokument/plik, strone oraz sekcje/artykul/paragraf/punkt, jesli te metadane sa dostepne.

Test koncowy `/ask`:

- `limit=1` zwrocil strone z `Odpowiedz modelu`,
- komunikat UI: `Odpowiedz wygenerowana na podstawie 1 fragmentow.`,
- przykladowa odpowiedz dotyczyla art. 158 i przejscia administratora bezpieczenstwa informacji w inspektora ochrony danych.

Test regresyjny dla trybu audytowego:

```bash
python3 -m py_compile /home/maverick/llm.py.work
sudo docker compose build web
sudo docker compose up -d web
curl http://127.0.0.1/health
curl "http://127.0.0.1/ask?q=Czy%20organizacja%20posiada%20formalnie%20zdefiniowan%C4%85%20polityk%C4%99%20bezpiecze%C5%84stwa%20informacji%20oraz%20polityki%20tematyczne&limit=5"
```

Oczekiwane zachowanie po poprawce: `/ask` odpowiada od `Tak` i wskazuje fragmenty kontekstu dotyczace Polityki Bezpieczenstwa Informacji oraz dedykowanych polityk tematycznych w SZBI. W opisanym tescie `/search` znajdowal wlasciwy fragment jako pierwszy wynik, a `/ask` mial `rows=5` i `context_chars=3661`; poprawka dotyczyla promptu LLM, nie retrievalu.

Uwaga operacyjna: na CPU `/ask` jest wolny. Test z `limit=1` trwal okolo 2-3 minuty po poprawce. Dla wiekszego limitu czas odpowiedzi moze istotnie wzrosnac.

Uwaga jakosciowa: prompt audytowy poprawia odpowiedzi malego modelu `llama3.2:3b`, ale nie jest gwarancja poprawnosci. Dla zastosowan kontrolnych nadal trzeba prowadzic ewaluacje na zestawie pytan i oczekiwanych podstaw w dokumentach.

## Ankieta A.5

Web UI ma sekcje `Ankieta A.5` i przycisk:

```text
Wykonaj ankiete A.5
```

Endpoint:

```text
POST /assessment/a5/start
GET /jobs/{job_id}
POST /assessment/a5
```

`POST /assessment/a5/start` jest sciezka uzywana przez web UI. Tworzy job w pamieci procesu web i od razu zwraca JSON ze statusem. Frontend odpytuje `GET /jobs/{job_id}` co 5 sekund i pokazuje log w `job-panel`. `POST /assessment/a5` nadal istnieje jako synchroniczna sciezka kompatybilna.

Test synchroniczny z terminala:

```bash
curl -X POST http://127.0.0.1/assessment/a5
```

Uwaga: endpoint renderuje HTML i wykonuje cala ankiete synchronicznie w procesie requestu. Na CPU pelny przebieg 5 pozycji przed dodaniem guardrails trwal okolo 21 minut.

Aktualny zakres:

```text
A.5.1.1
A.5.2.1
A.5.3.1
A.5.4.1
A.5.5.1
```

Pliki implementacji:

- `/opt/IODO/app/iodo_rag/audit.py`
- `/opt/IODO/app/iodo_rag/audit_prompts_A5.jsonl`
- `/opt/IODO/app/iodo_rag/llm.py`
- `/opt/IODO/app/iodo_rag/web.py`

Przeplyw:

1. `load_a5_questions()` laduje pierwsze pytanie dla kontroli `A.5.1`-`A.5.5` z `audit_prompts_A5.jsonl`.
2. `run_a5_assessment()` wywoluje `search_for_audit_item(item, settings, client_id=...)` dla kazdej pozycji.
3. `build_retrieval_queries(item)` tworzy warianty zapytan z pol `query`, `question`, `requirement`, `evidence` oraz kombinacji danych punktu.
4. `search_for_audit_item()` uruchamia obecny `hybrid_search` przez `run_search` dla kazdego wariantu.
5. Wyniki sa deduplikowane po `chunk id`, oceniane scoringiem audytowym i ograniczane do puli kandydatow.
6. Dla najlepszych trafien glownych pobierane sa sasiednie chunki z tego samego dokumentu.
7. `answer_with_prompt(...)` wysyla prompt z JSONL oraz rozszerzony kontekst do Ollamy `llama3.2:3b`.
8. Wyniki sa renderowane w sekcji ankiety razem z odpowiedzia modelu i uzytym kontekstem.

Aktualne stale retrievalu ankiety:

```text
AUDIT_QUERY_LIMIT=12
AUDIT_CONTEXT_LIMIT=10
AUDIT_PRIMARY_CONTEXT_LIMIT=5
AUDIT_EXPANDED_CONTEXT_LIMIT=14
```

`AUDIT_QUERY_LIMIT` oznacza limit kandydatow na wariant zapytania. `AUDIT_CONTEXT_LIMIT` oznacza pule kandydatow po deduplikacji i scoringu. `AUDIT_PRIMARY_CONTEXT_LIMIT` oznacza liczbe najlepszych trafien glownych, dla ktorych pobierane jest sasiedztwo. `AUDIT_EXPANDED_CONTEXT_LIMIT` oznacza maksymalna liczbe fragmentow przekazywanych do LLM po rozszerzeniu o sasiednie chunki.

Scoring audytowy sortuje kandydatow wedlug:

- najlepszego `hybrid_score` znalezionego dla danego chunku,
- bonusu za liczbe wariantow zapytan, ktore znalazly chunk,
- bonusu za slowa dowodowe i wazne terminy z punktu ankiety.

Do wynikow dodawane sa pola diagnostyczne:

- `audit_score`,
- `audit_query_count`,
- `audit_keyword_hits`,
- `audit_queries`.

Te pola moga pomoc w debugowaniu retrievalu i ocenie, dlaczego dany fragment trafil do kontekstu LLM.

Rozszerzone metadane RAG i sasiednie chunki:

- `hybrid_search` zwraca `document_id`, `chunk_index`, `client_name` oraz dotychczasowe `client_id`, `source_file`, `document_title`, `page_from`, `page_to`, `section`, `article`, `paragraph`, `point`,
- `db.adjacent_chunks(conn, chunk_ids, client_id=None)` pobiera poprzedni, aktualny i nastepny chunk z tego samego dokumentu dla seed chunkow, z zachowaniem filtra `client_id`,
- `search.fetch_adjacent_chunks(...)` jest wrapperem dla ankiety,
- `audit.py` bierze 5 najlepszych trafien glownych, dociaga sasiednie chunki i zwraca maksymalnie 14 fragmentow,
- kazdy fragment moze miec `context_role`, `seed_chunk_id`, `neighbor_offset`, `audit_score`, `audit_query_count`, `audit_keyword_hits`, `audit_queries`.

Role kontekstu:

- `trafienie glowne`,
- `poprzedni chunk`,
- `nastepny chunk`.

`llm.build_context()` dodaje do kazdego bloku klienta, dokument, plik, strone/zakres stron, referencje strukturalna, `chunk_index`, `rola_kontekstu` i `audit_score`. Web UI w szczegolach najlepszych trafien ankiety pokazuje dokument, strone, referencje, chunk index, role kontekstu i score.

Statusy asynchronicznego joba:

- `running` - job trwa,
- `done` - wynik jest gotowy, `GET /jobs/{job_id}` zwraca `result_html`,
- `error` - wystapil blad, odpowiedz zawiera `error`.

Komunikaty w panelu obejmuja start zadania, rozpoczecie retrieval dla punktu, liczbe znalezionych fragmentow, przejscie do analizy, zakonczenie punktu i wynik koncowy. Co 120 sekund job dopisuje heartbeat:

```text
Prace trwaja; jestem na etapie: ...
```

Wazne ograniczenie: joby sa przechowywane w pamieci procesu web. Restart kontenera usuwa statusy i historie jobow.

Od poprawki timeoutu jeden blad LLM nie przerywa calej ankiety. Jesli `answer_with_prompt(...)` dla punktu zwroci timeout albo inny wyjatek, `audit.py` zapisuje wynik punktu jako:

```text
SPELNENIE: BLAD ANALIZY LLM
```

W uzasadnieniu trafia techniczny opis bledu oraz informacja, ile fragmentow znalazl retrieval. Job dopisuje komunikat, np. timeout/blada analizy punktu, i przechodzi do nastepnego punktu.

Docelowy uklad wyszukiwania dla ankiet A.5 i kolejnych:

```text
query expansion -> hybrid search -> deduplikacja -> reranking -> LLM ocenia spelnienie
```

Na dzisiaj dziala pierwszy etap tego ukladu: multi-query retrieval, hybrid search, deduplikacja i prosty scoring audytowy. Nie ma jeszcze osobnego rerankera. Operator powinien traktowac wyniki jako pomoc audytowa wymagajaca przegladu, nie jako zamknieta automatyczna ocene.

Docelowo operacyjny przebieg powinien wygladac tak:

1. Dla kazdego wymagania system generuje warianty zapytan: pytanie kontrolne, wymagane dowody, typowe nazwy polityk/procedur, synonimy i hasla z obszaru kontroli.
2. Kazdy wariant uruchamia hybrid search: pgvector + PostgreSQL full-text.
3. Wyniki z wielu zapytan sa deduplikowane po `chunk_id`, dokumencie, stronie i podobienstwie tekstu.
4. Reranker wybiera najlepsze fragmenty dowodowe dla konkretnego wymagania.
5. LLM dostaje tylko wybrane, opisane fragmenty i ocenia spelnienie: `TAK`, `CZESCIOWO`, `NIE` albo `BRAK DANYCH`, z dowodami i brakami.

Szybkie testy po zmianach:

```bash
curl http://127.0.0.1/health
sudo docker exec iodo-web-1 python -c "from iodo_rag.audit import load_a5_questions; print([f\"{q['control']}.{q['question_no']}\" for q in load_a5_questions()])"
curl http://127.0.0.1/
```

Oczekiwane wyniki:

- `/health` zwraca `{"status":"ok"}`,
- lista pytan to `['A.5.1.1', 'A.5.2.1', 'A.5.3.1', 'A.5.4.1', 'A.5.5.1']`,
- strona glowna zawiera sekcje `Ankieta A.5` i przycisk `Wykonaj ankiete A.5`.

Testy retrievalu po pierwszej poprawce, wykonane 2026-07-09:

- `python3 -m py_compile /home/maverick/audit.py.work` OK,
- `docker compose build web` OK,
- `docker compose up -d web` OK,
- `/health` OK,
- backend laduje 5 pytan `A.5.1.1`-`A.5.5.1`,
- pierwszy punkt generuje 9 wariantow zapytan,
- retrieval `A.5.1.1` zwraca 10 unikalnych chunkow; top trafienia mialy `audit_query_count` 6-8 i `audit_keyword_hits` 9-11,
- retrieval dla wszystkich pieciu punktow zwraca po 10 kandydatow,
- web UI nadal renderuje sekcje `Ankieta A.5` i przycisk `Wykonaj ankiete A.5`.

Testy klientow i asynchronicznych statusow ankiety, wykonane 2026-07-09:

- `py_compile` dla `db.py`, `ingest.py`, `search.py`, `audit.py`, `web.py` OK,
- `docker compose build web` OK,
- `docker compose up -d web` OK,
- `/health` OK,
- migracja utworzyla klienta domyslnego i przypisala istniejacy dokument: `Klient domyslny` ma 1 dokument,
- importy modulow w kontenerze OK,
- strona glowna renderuje `Aktywny klient`, `Nowy klient`, `Ankieta A.5`, `/assessment/a5/start` i `job-panel`,
- `/search?client_id=1&q=polityka&limit=2` zwrocil 2 wyniki dla `Klient domyslny`,
- `POST /clients` sprawdzono przez utworzenie klienta testowego; endpoint zwrocil `303` z `client_id`, klient testowy zostal usuniety,
- asynchroniczny job ankiety przetestowano na tymczasowym kliencie bez dokumentow: job przeszedl `running -> done`, zwrocil komunikaty dla `A.5.1.1`-`A.5.5.1` i `result_html`; klient testowy zostal usuniety.

Testy rozszerzonych metadanych RAG i sasiednich chunkow, wykonane 2026-07-09:

- zmienione pliki aplikacji: `db.py`, `search.py`, `audit.py`, `llm.py`, `web.py`,
- `py_compile` dla `db.py`, `search.py`, `audit.py`, `llm.py`, `web.py` OK,
- `docker compose build web` OK,
- `docker compose up -d web` OK,
- `/health` OK,
- importy w kontenerze OK,
- retrieval `A.5.1.1` dla `client_id=1` zwrocil 13 fragmentow: `poprzedni chunk`, `trafienie glowne`, `nastepny chunk`; wyniki zawieraly `document_title`, `page_from`/`page_to` i `chunk_index`,
- `build_context` pokazal naglowki z klientem, dokumentem, plikiem, strona, referencja, `chunk_index`, `rola_kontekstu` i `audit_score`,
- retrieval dla wszystkich pieciu punktow A.5 zwrocil 13-14 fragmentow: 5 trafien glownych oraz poprzednie/nastepne chunki tam, gdzie istnieja,
- pelnej analizy LLM `/assessment/a5` nie uruchomiono ponownie ze wzgledu na znany dlugi czas CPU; testowany byl zmieniony etap retrieval/kontekstu.

Testy poprawki timeoutu Ollamy i odpornosci ankiety na bledy LLM per punkt:

- `py_compile` dla `config.py`, `llm.py`, `audit.py` OK,
- `docker compose build web` OK,
- `docker compose up -d web` OK,
- `/health` OK,
- w kontenerze web `get_settings()` zwrocil `1800 8500 8192 384`,
- import `iodo_rag.web` OK,
- logi web bez bledow startu.

Guardrails w `audit.py` doprecyzowuja, ze `referencja: brak referencji` nie oznacza braku dowodu, tresc fragmentu moze byc dowodem, przy czesciowym potwierdzeniu nalezy wybrac `CZESCIOWO`, a `NIE` tylko przy jawnym zaprzeczeniu w dokumentach.

Pelnego `/assessment/a5` z LLM po tej poprawce nie uruchomiono ponownie ze wzgledu na znany czas dzialania na CPU, rzedu kilkunastu-kilkudziesieciu minut. Przetestowany zostal zmieniony etap retrieval. Jesli operator uruchamia pelny test endpointu, nalezy zalozyc dlugi czas odpowiedzi. Dla rozbudowy ankiety poza 5 pozycji potrzebny bedzie tryb zadania w tle, status postepu i prawdopodobnie lepsza strategia kontekstu.

## Chunking i dowody ankietowe

Aktualny chunking w `/opt/IODO/app/iodo_rag/chunking.py`:

- rozpoznaje typ dokumentu: `legal`, `markdown` albo `prose`,
- dla dokumentow prawnych dzieli po sekcjach, artykulach, ustepach i punktach,
- dla Markdown zapisuje `heading_path`,
- dla prozy uzywa fallbacku po akapitach, liniach, zdaniach i slowach,
- dla PDF korzysta ze znacznikow `[PAGE n]` i wylicza `page_from`/`page_to`,
- domyslnie pracuje na `CHUNK_TARGET_CHARS=3500` i `CHUNK_OVERLAP_CHARS=500`.

To jest sensowna baza operacyjna. Przy interpretacji wynikow ankiet trzeba jednak pamietac, ze embedding jest liczony z tekstu chunku, a nie z pelnego opisu dokumentu i metadanych. Oznacza to, ze wazne informacje z tytulu dokumentu, sciezki naglowkow, wersji, tabel zatwierdzen albo sasiedniego fragmentu moga nie trafiac do podobienstwa wektorowego.

Dla kolejnej wersji ankiet warto zaplanowac:

- tekst embeddingu zlozony z metadanych i tresci, np. `dokument`, `tytul`, `sekcja`, `heading_path`, `strony`, `typ dokumentu`, `tresc`,
- parser lub preprocesor zachowujacy tabele zatwierdzen, historie zmian i pola metadanych jako tekst przeszukiwalny,
- mniejsze albo logiczniejsze fragmenty dla dowodow, jesli jeden chunk zawiera kilka niezaleznych wymagan,
- mechanizm pobrania sasiednich chunkow przed wyslaniem kontekstu do LLM, np. poprzedni i nastepny chunk z tego samego dokumentu.

## Konfiguracja

Glowne pliki:

- `/opt/IODO/.env`
- `/opt/IODO/.env.example`
- `/opt/IODO/docker-compose.yml`
- `/opt/IODO/db/init.sql`
- `/opt/IODO/app/iodo_rag/config.py`
- `/opt/IODO/app/iodo_rag/web.py`
- `/opt/IODO/app/iodo_rag/llm.py`
- `/opt/IODO/app/iodo_rag/audit.py`
- `/opt/IODO/app/iodo_rag/audit_prompts_A5.jsonl`
- `/opt/IODO/app/iodo_rag/db.py`
- `/opt/IODO/app/iodo_rag/ingest.py`
- `/opt/IODO/app/iodo_rag/search.py`

Kluczowe wartosci:

```env
EMBEDDING_URL=http://tei:80
EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DIM=384
EMBEDDING_BATCH_SIZE=8
CHUNK_TARGET_CHARS=3500
CHUNK_OVERLAP_CHARS=500
LLM_URL=http://ollama:11434
LLM_MODEL=llama3.2:3b
LLM_TIMEOUT_SECONDS=1800
LLM_CONTEXT_MAX_CHARS=8500
LLM_NUM_CTX=8192
LLM_NUM_PREDICT=384
```

W bazie kolumna embeddingu musi miec ten sam wymiar:

```sql
embedding vector(384)
```

Modele E5 wymagaja prefiksow tekstu. Aplikacja robi to automatycznie w `app/iodo_rag/embeddings.py`:

- `passage: ` dla tekstow indeksowanych podczas ingestii,
- `query: ` dla zapytan wyszukiwania.

Nie nalezy dopisywac tych prefiksow recznie w zapytaniu CLI ani w formularzu web.

## Ollama

Sprawdzenie modeli:

```bash
sudo docker exec iodo-ollama-1 ollama list
```

Oczekiwany model:

```text
llama3.2:3b
```

Pobranie modelu, jesli brakuje:

```bash
sudo docker exec iodo-ollama-1 ollama pull llama3.2:3b
```

## Reset danych

Nie wykonywac resetu wolumenow bez potwierdzenia, bo usuwa to baze, cache modeli albo modele Ollamy. Przed kasowaniem danych nalezy sprawdzic:

```bash
sudo docker volume ls
sudo docker system df
```

Wolumeny uzywane przez stack:

- `postgres_data`
- `hf_cache`
- `ollama_data`

Do usuwania pojedynczego dokumentu z bazy uzywac przycisku `Usun` w web UI zamiast resetu wolumenu PostgreSQL. Trzeba pamietac, ze plik uploadu zostaje w `/data/uploads`.

## Typowe problemy

### TEI dlugo startuje

Sprawdz logi:

```bash
sudo docker logs --tail 120 iodo-tei-1
```

Pierwszy start moze pobierac model. Jesli proces zatrzymuje sie na rozgrzewaniu duzego modelu, upewnic sie, ze konfiguracja nadal wskazuje `intfloat/multilingual-e5-small`.

### `/ask` konczy sie timeoutem

Sprawdz:

```bash
sudo docker logs --tail 120 iodo-web-1
sudo docker logs --tail 120 iodo-ollama-1
```

Aktualne ograniczenia wydajnosciowe sa celowo obnizone:

- kontekst do 8500 znakow,
- `num_ctx=8192`,
- `num_predict=384`,
- `LLM_TIMEOUT_SECONDS=1800`.

Jesli timeout wroci, testowac najpierw `limit=1`. Wiekszy limit moze byc zbyt wolny na CPU. Dla ankiety A.5 timeout pojedynczego punktu nie powinien zatrzymac calego joba, ale wynik punktu bedzie oznaczony jako `SPELNENIE: BLAD ANALIZY LLM`.

Jesli czas CPU nadal jest zbyt dlugi, mozna zmniejszyc bez zmiany kodu:

- `LLM_CONTEXT_MAX_CHARS`,
- `LLM_NUM_CTX`,
- `LLM_NUM_PREDICT`.

Zwiekszenie timeoutu pozwala jobowi czekac dluzej, ale nie przyspiesza generacji.

### `/assessment/a5` trwa bardzo dlugo

To nadal oczekiwane na CPU. Web UI uruchamia ankiete przez job asynchroniczny, wiec request HTTP nie powinien wisiec do konca pracy. Sam job nadal wykonuje 5 pozycji sekwencyjnie, a kazda pozycja robi retrieval i osobne wywolanie Ollamy.

Sprawdzic logi:

```bash
sudo docker logs --tail 120 iodo-web-1
sudo docker logs --tail 120 iodo-ollama-1
```

Do szybkiej diagnostyki nie uruchamiac od razu calego endpointu, tylko sprawdzic healthcheck, ladowanie promptow i render strony glownej:

```bash
curl http://127.0.0.1/health
sudo docker exec iodo-web-1 python -c "from iodo_rag.audit import load_a5_questions; print([f\"{q['control']}.{q['question_no']}\" for q in load_a5_questions()])"
curl http://127.0.0.1/
```

Jesli web pokazuje pusty albo utracony status joba, sprawdzic, czy kontener `web` nie zostal zrestartowany. Statusy jobow sa w pamieci procesu.

### `/ask` zwraca `Brak danych`, mimo ze `/search` znajduje fragment

Najpierw porownac wyniki `/search` i kontekst `/ask` dla tego samego pytania oraz limitu. Aktualny prompt powinien uznawac rownowazne dowody w kontekscie i nie wymagac doslownego powtorzenia pytania w dokumencie.

Sprawdzic test regresyjny:

```bash
curl "http://127.0.0.1/search?q=Czy%20organizacja%20posiada%20formalnie%20zdefiniowan%C4%85%20polityk%C4%99%20bezpiecze%C5%84stwa%20informacji%20oraz%20polityki%20tematyczne&limit=5"
curl "http://127.0.0.1/ask?q=Czy%20organizacja%20posiada%20formalnie%20zdefiniowan%C4%85%20polityk%C4%99%20bezpiecze%C5%84stwa%20informacji%20oraz%20polityki%20tematyczne&limit=5"
```

Jesli `/search` nadal zwraca poprawny fragment, a `/ask` odpowiada blednie, traktowac to jako problem jakosci generacji malego modelu i dopisac przypadek do zestawu ewaluacyjnego.

### Wyniki wyszukiwania sa puste

Najpierw sprawdzic, czy dokumenty zostaly zaimportowane. Puste wyniki sa normalne w swiezej bazie bez danych.

```bash
sudo docker exec iodo-postgres-1 psql -U iodo -d iodo -c "select count(*) from documents;"
sudo docker exec iodo-postgres-1 psql -U iodo -d iodo -c "select count(*) from document_chunks;"
```

### Dokument usuniety z bazy nadal ma plik w uploads

To oczekiwane zachowanie. `POST /documents/{document_id}/delete` usuwa dane z PostgreSQL/pgvector, ale nie usuwa pliku zrodlowego z `/data/uploads`. Jesli trzeba usunac takze plik z dysku, nalezy zrobic to osobna, swiadoma operacja administracyjna po sprawdzeniu sciezki.

### Blad TEI `422 Unprocessable Entity` przy imporcie

TEI ma limit rozmiaru batcha. Aplikacja batchuje embeddingi przez `EMBEDDING_BATCH_SIZE`, domyslnie:

```env
EMBEDDING_BATCH_SIZE=8
```

Test batchowania:

```bash
sudo docker exec iodo-web-1 python -c "from iodo_rag.embeddings import EmbeddingClient; vectors = EmbeddingClient('http://tei:80', 384).embed([f'test dokumentu {i}' for i in range(50)]); print(len(vectors), len(vectors[0]))"
```

Oczekiwany wynik:

```text
50 384
```

Jesli blad wroci, sprawdzic logi:

```bash
sudo docker logs --tail 120 iodo-tei-1
sudo docker logs --tail 120 iodo-web-1
```

### Interfejs web nie otwiera sie z innego hosta

Sprawdzic po kolei:

```bash
sudo docker compose ps
sudo docker port iodo-web-1
sudo ss -ltnp
```

Jesli proces slucha poprawnie, sprawdzic firewall hosta i aktualny adres IP hosta.
