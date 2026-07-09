# Kolejne kroki

Ostatnia aktualizacja: 2026-07-09

Cel pliku: lista nastepnych prac technicznych, ktore nie powinny byc traktowane jako gotowe funkcje przed implementacja i testami.

## 1. Uwierzytelnianie i ograniczenie dostepu

Web UI dziala na hostowych portach `80` i `8000` i nie ma jeszcze logowania. Przed szerszym udostepnieniem w sieci nalezy dodac przynajmniej proste uwierzytelnianie oraz ograniczyc dostep.

Minimalne wymagania:

- logowanie lub token dostepu do web UI,
- ograniczenie dostepu do zaufanej sieci albo reverse proxy,
- HTTPS przy ekspozycji poza hostem testowym,
- limity rozmiaru uploadu,
- status importu dla duzych plikow.

Usuwanie dokumentow z bazy jest juz dostepne w web UI, wiec brak uwierzytelniania jest teraz istotniejszym ryzykiem operacyjnym.

## 2. Decyzje przy instalacji na nowym serwerze

Runbook `docs/RUNBOOK_NEW_SERVER.md` opisuje techniczne odtworzenie systemu, ale przed produkcyjnym uruchomieniem trzeba nadal podjac decyzje operacyjne:

- czy przenoszona jest baza przez `pg_dump`/`psql`, czy dokumenty beda importowane ponownie,
- czy backupowane sa tylko `data/uploads`, czy rowniez wolumeny Docker,
- jakie wartosci chunkingu ustawic przed importem: wzorzec `.env.example` ma `CHUNK_TARGET_CHARS=3500` i `CHUNK_OVERLAP_CHARS=500`, a aktywny host uzywa `1100/150`,
- czy port `80` zostaje wystawiony bezposrednio, czy aplikacja ma dzialac za reverse proxy,
- jakie zasady firewalla ograniczaja dostep do web UI z LAN.

## 3. Stabilizacja `/ask` i jobow `/assessment/a5` na CPU

Podstawowa integracja z Ollama juz dziala, ale generacja jest wolna na CPU. Ostatni test `/ask` z `limit=1` trwal okolo 2-3 minuty. Pelny test `POST /assessment/a5` dla 5 pozycji przed guardrails trwal okolo 21 minut. Web UI uruchamia ankiete A.5 asynchronicznie przez `POST /assessment/a5/start`, ale sam job nadal wykonuje prace sekwencyjnie na CPU.

Obecne ustawienia po poprawce:

```text
max_chars=8500
num_ctx=8192
num_predict=384
temperature=0.2
LLM_TIMEOUT_SECONDS=1800
LLM_CONTEXT_MAX_CHARS=8500
LLM_NUM_CTX=8192
LLM_NUM_PREDICT=384
```

Kolejne kroki:

- mierzyc czasy odpowiedzi dla `limit=1`, `limit=3`, `limit=5`,
- dopracowac komunikaty statusu jobow i obsluge bledow,
- przeniesc statusy ankiet z pamieci procesu do trwalego storage,
- rozwazyc mniejszy model lub GPU, jesli odpowiedzi maja byc interaktywne,
- dodac jasne komunikaty, gdy kontekst jest pusty albo model przekracza timeout.

Po poprawce timeoutu `.env` ustawia `LLM_TIMEOUT_SECONDS=1800`, a pojedynczy timeout/blad LLM w ankiecie A.5 nie przerywa calego joba. Punkt dostaje `SPELNENIE: BLAD ANALIZY LLM`, a job przechodzi dalej. To poprawia odpornosc operacyjna, ale nie przyspiesza generacji na CPU.

Jesli czas CPU nadal bedzie zbyt dlugi, w pierwszej kolejnosci testowac mniejsze wartosci bez zmiany kodu:

- `LLM_CONTEXT_MAX_CHARS`,
- `LLM_NUM_CTX`,
- `LLM_NUM_PREDICT`.

Aktualne ograniczenie jobow: `JOBS` jest slownikiem w pamieci procesu web. Restart kontenera usuwa historie i status zadania. Docelowo uzyc tabeli `jobs` w PostgreSQL albo Redis/Celery/RQ.

## 4. Cytowania i kontrola jakosci odpowiedzi

`/ask` odpowiada na podstawie znalezionych fragmentow. Prompt zostal przestawiony na tryb audytowy i dla pytan kontrolnych powinien zaczynac odpowiedz od `Tak`, `Nie`, `Czesciowo` albo `Brak danych`, z krotkim uzasadnieniem i wskazaniem podstawy w kontekscie, np. `[1]`.

To poprawia znany przypadek, w ktorym `/search` znajdowal fragment o Polityce Bezpieczenstwa Informacji i politykach tematycznych SZBI, ale stary prompt/model odpowiadal `brak danych`. Nadal nie jest to produkcyjna kontrola jakosci odpowiedzi.

Do dopracowania:

- testy regresji sprawdzajace prefiks odpowiedzi (`Tak`/`Nie`/`Czesciowo`/`Brak danych`) i podstawe `[1]`, `[2]`,
- pokazywanie metadanych zrodel przy odpowiedzi modelu,
- blokada odpowiedzi, gdy retrieval nie zwroci wystarczajacego kontekstu,
- testy regresji na pytaniach, dla ktorych znane sa poprawne fragmenty.

## 5. Rozbudowa ankiety A.5 i trybu punktu audytowego

Pierwsza wersja ankiety A.5 jest juz wdrozona w web UI przez `POST /assessment/a5`. Obecnie wykonuje synchronicznie 5 pierwszych pozycji:

```text
A.5.1.1
A.5.2.1
A.5.3.1
A.5.4.1
A.5.5.1
```

Kazda pozycja uzywa `search_for_audit_item(item, settings)`, przekazuje finalny kontekst do Ollamy i renderuje wynik HTML. Prompty sa ladowane z `app/iodo_rag/audit_prompts_A5.jsonl`, a logika znajduje sie w `app/iodo_rag/audit.py`.

Web UI uruchamia ankiete przez `POST /assessment/a5/start` i odpytuje `GET /jobs/{job_id}` co 5 sekund. Stary `POST /assessment/a5` nadal istnieje jako synchroniczna sciezka kompatybilna.

Pierwsza poprawka retrievalu jest juz wdrozona:

- `build_retrieval_queries(item)` tworzy warianty z pol `query`, `question`, `requirement`, `evidence` oraz kombinacji `control`/`control_name`/`question`/`evidence`/`requirement`,
- `search_for_audit_item(item, settings)` uruchamia obecny hybrid search przez `run_search` dla kazdego wariantu,
- `AUDIT_QUERY_LIMIT = 12` okresla limit kandydatow na wariant zapytania,
- `AUDIT_CONTEXT_LIMIT = 10` okresla pule kandydatow po deduplikacji i scoringu,
- `AUDIT_PRIMARY_CONTEXT_LIMIT = 5` okresla liczbe trafien glownych, dla ktorych pobierane jest sasiedztwo,
- `AUDIT_EXPANDED_CONTEXT_LIMIT = 14` okresla maksymalny finalny kontekst do LLM po rozszerzeniu,
- deduplikacja dziala po `chunk id`,
- prosty scoring audytowy uzywa najlepszego `hybrid_score`, liczby wariantow zapytan, ktore znalazly chunk, oraz trafien slow dowodowych/waznych terminow,
- pola diagnostyczne `audit_score`, `audit_query_count`, `audit_keyword_hits`, `audit_queries` sa dodawane do wynikow i moga pomoc w debugowaniu.

Rozszerzenie o sasiednie chunki jest wdrozone:

- `hybrid_search` zwraca `document_id`, `chunk_index` i `client_name`,
- `adjacent_chunks` pobiera poprzedni, aktualny i nastepny chunk z tego samego dokumentu dla seed chunkow,
- `audit.py` zwraca role `trafienie glowne`, `poprzedni chunk`, `nastepny chunk`,
- celem jest pokazanie LLM krotkiego kontekstu przed i po punktowym trafieniu.

Docelowy uklad wyszukiwania dla ankiet A.5 i kolejnych:

```text
query expansion -> hybrid search -> deduplikacja -> reranking -> LLM ocenia spelnienie
```

Plan techniczny:

1. Query expansion: pierwszy wariant jest wdrozony przez `build_retrieval_queries`; dalej warto poprawiac slowniki, synonimy i warianty specyficzne dla obszarow kontroli.
2. Hybrid search: pierwszy wariant jest wdrozony przez wielokrotne wywolanie obecnego `run_search`.
3. Deduplikacja: pierwszy wariant jest wdrozony po `chunk id`; dalej mozna dodac deduplikacje po podobienstwie tekstu i sasiedztwie stron.
4. Reranking: dodac lokalny reranker, ktory ulozy kandydatow wzgledem konkretnego wymagania i oczekiwanych dowodow.
5. Ocena LLM: przekazywac do modelu tylko najlepsze, opisane fragmenty i wymagac statusu `TAK`/`CZESCIOWO`/`NIE`/`BRAK DANYCH`, dowodow, brakow i krotkiego uzasadnienia.

Obecne ograniczenia:

```text
build_context max_chars=8500
num_ctx=8192
num_predict=384
```

Endpoint jest synchroniczny i wolny na CPU. Po guardrails sprawdzono healthcheck, ladowanie 5 pytan i render sekcji UI. Po pierwszej poprawce retrievalu przetestowano etap retrieval dla wszystkich 5 punktow; pelnego przebiegu z LLM nie powtarzano ze wzgledu na czas.

Dla kolejnych etapow trzeba rozbudowac tryb punktu ankietowego/audytowego, ktory przyjmuje strukture:

- pytania kontrolne,
- wymagane dowody,
- opcjonalne metadane punktu, np. numer wymagania, obszar, standard lub audyt.

Proponowany przeplyw:

- uruchomic osobne zapytania retrievalowe dla kazdego pytania kontrolnego i wariantu query expansion,
- uruchomic osobne zapytania retrievalowe dla kazdego wymaganego dowodu,
- scalic i zdeduplikowac znalezione chunki,
- wykonac reranking kandydatow przed budowa kontekstu,
- rozwijac obecny mechanizm pobierania sasiednich chunkow, np. sterowac szerokoscia okna i limitami per dokument,
- zbudowac wiekszy lub hierarchiczny kontekst dla modelu,
- wygenerowac odpowiedz dla calego punktu, a nie tylko dla jednego pytania.

Oczekiwany format odpowiedzi:

- status dla kazdego pytania: `Tak`, `Nie`, `Czesciowo` albo `Brak danych`,
- znalezione dowody,
- zrodla i strony dokumentow, jesli metadane strony sa dostepne,
- luki dowodowe, czyli czego nie znaleziono w zaimportowanych plikach,
- krotkie podsumowanie statusu calego punktu.

Ryzyka i ograniczenia:

- wiekszy kontekst spowolni Ollame na CPU,
- dluzszy prompt moze wymagac mniejszego modelu, rerankera, streszczania posredniego albo mocniejszego hardware/GPU,
- proste zwiekszenie `max_chars` i `num_ctx` moze pogorszyc latencje bez poprawy jakosci, jesli retrieval nie bedzie dobrze rozbity na pytania i dowody,
- potrzebne beda testy regresji na realnych punktach ankietowych, gdzie znane sa oczekiwane dokumenty i luki dowodowe.

Wyniki testow pierwszej poprawki retrievalu z 2026-07-09:

- kompilacja `audit.py` i przebudowa/odtworzenie web przeszly OK,
- backend laduje 5 pytan `A.5.1.1`-`A.5.5.1`,
- pierwszy punkt generuje 9 wariantow zapytan,
- retrieval `A.5.1.1` zwraca 10 unikalnych chunkow; top trafienia mialy `audit_query_count` 6-8 i `audit_keyword_hits` 9-11,
- retrieval dla wszystkich pieciu punktow zwraca po 10 kandydatow,
- pelnego `/assessment/a5` z LLM nie uruchomiono ponownie ze wzgledu na czas CPU; do kolejnego etapu potrzebny jest test end-to-end z ocena jakosci odpowiedzi.

Wyniki testow rozszerzonych metadanych i sasiednich chunkow z 2026-07-09:

- retrieval `A.5.1.1` dla `client_id=1` zwrocil 13 fragmentow z rolami `poprzedni chunk`, `trafienie glowne`, `nastepny chunk`,
- retrieval dla wszystkich pieciu punktow A.5 zwrocil 13-14 fragmentow,
- `build_context` zawiera klienta, dokument, plik, strone, referencje, `chunk_index`, role kontekstu i `audit_score`,
- pelnej analizy LLM nie powtorzono ze wzgledu na czas CPU.

## 6. Utrwalenie klientow i jobow

Obsluga klientow jest wdrozona w pierwszej wersji:

- tabela `clients`,
- `documents.client_id`,
- klient `Klient domyslny`,
- dashboard i lista dokumentow per klient,
- import, search, ask i assessment filtrowane po `client_id`.

Do dalszego dopracowania:

- rozstrzygnac, czy `source_file` ma pozostac globalnie unikalny, czy powinien byc unikalny per klient,
- dodac administracyjne usuwanie/archiwizacje klientow zamiast recznego sprzatania testow,
- dodac testy regresji izolacji danych miedzy klientami,
- utrwalic joby ankietowe w PostgreSQL albo Redis/Celery/RQ,
- dodac historie wynikow ankiet per klient,
- dopisac status anulowania/przerwania joba.

## 7. Rozbudowa chunkingu pod dowody ankietowe

Obecny `app/iodo_rag/chunking.py` jest sensowna baza:

- wykrywa typ dokumentu `legal`, `markdown` albo `prose`,
- dla dokumentow prawnych dzieli po sekcjach, artykulach, ustepach i punktach,
- dla Markdown zapisuje `heading_path`,
- dla prozy ma fallback po akapitach, liniach, zdaniach i slowach,
- dla PDF korzysta ze znacznikow `[PAGE n]` i zapisuje `page_from`/`page_to`,
- domyslnie uzywa `CHUNK_TARGET_CHARS=3500` i `CHUNK_OVERLAP_CHARS=500`.

Wniosek: nie trzeba wyrzucac obecnego chunkingu. Trzeba go rozbudowac pod retrieval dowodow ankietowych, bo obecnie embedding jest liczony z samego tekstu chunku, a czesc semantyki dokumentu zostaje w osobnych polach lub metadanych.

Priorytety:

- budowac tekst do embeddingu z tresci oraz kontekstu dokumentu: tytul dokumentu, nazwa pliku, `heading_path`, sekcja, artykul, ustep, punkt, strony, typ dokumentu i ewentualne metadane parsera,
- poprawic obsluge tabel i metadanych zatwierdzenia, np. wlasciciel, zatwierdzil, data obowiazywania, wersja, historia zmian, podpisy i lista polityk/procedur,
- rozbic wybrane dokumenty na mniejsze albo logiczniejsze fragmenty dowodowe, gdy jeden chunk zawiera kilka niezaleznych wymagan,
- dodac mozliwosc pobrania sasiednich chunkow tego samego dokumentu przy budowie kontekstu dla LLM,
- dopracowac obecne pobieranie sasiednich chunkow pod przypadki tabel, bardzo krotkich chunkow i kilku trafien z tego samego dokumentu,
- zachowac obecne `page_from`/`page_to`, bo sa potrzebne do audytowych wskazan zrodel.

## 8. OCR dla skanowanych PDF

Obecny parser obsluguje PDF-y z warstwa tekstowa. Dla skanow trzeba dodac etap OCR przed ingestia.

Rozsadne opcje self-hosted:

- Tesseract jako najprostszy start,
- PaddleOCR dla lepszej jakosci,
- osobny wewnetrzny serwis OCR, jesli dokumentow bedzie duzo.

## 9. Reranker

Po pierwszym etapie retrievalu warto dodac lokalny reranker, szczegolnie dla ustaw, dokumentow bezpieczenstwa i ankiet A.5, gdzie wazne sa dokladne fragmenty dowodowe.

Kandydat:

```text
BAAI/bge-reranker-v2-m3
```

Reranker powinien byc dokumentowany jako gotowa funkcja dopiero po wdrozeniu i testach na realnych pytaniach. W docelowym pipeline ankietowym jest etapem miedzy deduplikacja wynikow a ocena LLM.

## 10. Ewaluacja jakosci

Przygotowac 30-50 rzeczywistych pytan po polsku z oczekiwanymi fragmentami odpowiedzi. Dla kazdego pytania sprawdzac, czy poprawny fragment znajduje sie w top 5 lub top 10 wynikow.

Ewaluacja powinna osobno sprawdzac retrieval i generacje `/ask`. Obecna mechanika RAG ma juz multi-query, rozszerzone metadane, sasiednie chunki, `max_chars=8500`, `num_ctx=8192` i `num_predict=384`, ale `llama3.2:3b` pozostaje malym modelem lokalnym: prompt i metadane pomagaja w interpretacji pytan audytowych, ale nie zastepuja testow jakosci.

Zakres minimalny:

- pytania faktograficzne,
- pytania o konkretne artykuly/paragrafy,
- pytania przekrojowe wymagajace kilku fragmentow,
- pytania bez odpowiedzi w dokumentach.

## 11. Metadane prawne i bezpieczenstwa

Warto dalej rozszerzyc ingestie o strukture dokumentu:

- tytul aktu lub dokumentu,
- rozdzial,
- artykul,
- paragraf,
- punkt,
- strona,
- wersja dokumentu,
- data obowiazywania,
- klauzula lub poziom poufnosci, jesli dotyczy.

Czesc tych danych jest juz wyciagana przez chunking strukturalny, ale wymaga weryfikacji na wiekszym zbiorze dokumentow.

## 12. API aplikacyjne

Obecnie FastAPI wystawia glownie endpointy webowe renderujace HTML:

- `GET /`,
- `POST /upload`,
- `POST /clients`,
- `GET /search`,
- `GET /ask`,
- `POST /assessment/a5/start`,
- `GET /jobs/{job_id}`,
- `POST /assessment/a5`,
- `GET /health`.

Docelowe API integracyjne powinno wystawic osobne kontrakty JSON:

- import dokumentu,
- status ingestii,
- wyszukiwanie,
- pytanie do modelu,
- pobranie fragmentu z metadanymi,
- healthcheck.

Takie API powinno miec autoryzacje i limity.

## 13. Kopie zapasowe

Ustalic backup PostgreSQL i katalogu z dokumentami zrodlowymi. Minimalnie:

- `pg_dump` bazy `iodo`,
- backup `/opt/IODO/data`,
- backup tabel `clients` i przyszlych tabel jobow/wynikow ankiet,
- backup plikow konfiguracyjnych `.env`, `docker-compose.yml` i `db/init.sql`,
- backup wolumenu `ollama_data`, jesli modele maja nie byc pobierane ponownie.

## 14. Polityka retencji plikow uploadu

Usuwanie dokumentu z web UI kasuje dokument oraz chunki/embeddingi z PostgreSQL/pgvector, ale zostawia plik zrodlowy w `/data/uploads`.

Do ustalenia:

- czy pliki uploadu maja byc usuwane recznie,
- czy dodac opcjonalne usuwanie pliku razem z rekordem bazy,
- czy trzymac audyt usunietych dokumentow,
- jak backup ma traktowac dokumenty usuniete z indeksu, ale pozostawione na dysku.
