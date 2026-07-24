# Operacje

1. Ustaw sekrety w `.env` (wartość Fernet dla checkpointów można utworzyć poleceniem administracyjnym poza repozytorium).
2. `docker compose build support-web support-worker`
3. `docker compose up -d postgres tei ollama reranker support-web support-worker`
4. Migracje ręczne: `docker compose run --rm --entrypoint alembic support-web upgrade head`.
5. Zdrowie: `GET http://localhost:8081/health`; stan: `docker compose ps`; logi: `docker compose logs support-web support-worker`.

Reranker ma ograniczony budżet batcha (`2048` tokenów, 32 równoległe żądania), aby model GTE mieścił się na hoście z 8 GiB RAM. Zmianę limitów należy poprzedzić pomiarem pamięci i czasu odpowiedzi.

Odpowiedź asystenta ma domyślny limit 1200 tokenów. Na obecnym CPU lokalne generowanie może trwać kilka minut; ekran zgłoszenia automatycznie odświeża status zadania.

Timeout połączenia workera z Ollamą jest sterowany przez `LLM_TIMEOUT_SECONDS` (wdrożenie: 1800 s). Nie należy ustawiać go poniżej czasu generowania 500 tokenów na docelowym CPU. Ponowienie czyści poprzedni komunikat błędu i ustawia zgłoszenie na `in_progress`.

Zewnętrzny generator konfiguruje się wyłącznie przez sekrety środowiskowe `EXTERNAL_LLM_URL`, `EXTERNAL_LLM_MODEL`, `EXTERNAL_LLM_API_KEY` i `EXTERNAL_LLM_TIMEOUT_SECONDS`. URL ma wskazywać endpoint zgodny z OpenAI Chat Completions. Bez kompletu tych wartości albo po błędzie API worker automatycznie użyje Ollamy. Przełącznik biznesowy znajduje się w `/settings`.

Aktualne wdrożenie używa OVH AI Endpoint `Qwen3.5-9B` przez `/v1/chat/completions`. `EXTERNAL_LLM_REASONING_EFFORT=none` jest wymagane, ponieważ domyślne rozumowanie modelu może zużyć cały limit na niewidoczne pole `reasoning`. Klucz pozostaje wyłącznie w nieśledzonym `.env`. Neutralny test połączenia trwał 0,56 s, a pełny StateGraph z ośmioma źródłami 19,99 s.

Backup musi obejmować bazę PostgreSQL i `/data/support-uploads`. Odtworzenie należy ćwiczyć przed pilotem. Worker jest bezstanowy i może mieć wiele replik.

Obrazy zgłoszeń są przechowywane w `/data/support-uploads/ticket-images`, a obrazy przypadków historycznych w `/data/support-uploads/case-images`. Nie wolno odtwarzać samej bazy bez odpowiadającej jej kopii tego katalogu. Po migracji `0013_historical_case_images` należy sprawdzić obecność tabeli `support.historical_case_images`.

Minimalna weryfikacja wydania:

1. `docker compose build support-web support-worker`;
2. uruchomienie testów jednostkowych z katalogu `tests`;
3. `docker compose up -d support-web support-worker`;
4. potwierdzenie `GET /health` i zdrowia obu kontenerów;
5. sprawdzenie logu Alembic oraz utworzenia najnowszej migracji;
6. test dodania obrazu przypadku, podglądu i zatwierdzenia go do AI przez administratora.

Analiza podziału dokumentu jest uruchamiana jawnie z jego widoku. Długi dokument może wymagać wielu wywołań LLM; nie należy zamykać strony przed odpowiedzią endpointu. Stan `analysis_failed` pozwala ponowić analizę. Stan `pending_review` oznacza, że propozycje istnieją, ale nie są jeszcze widoczne dla retrieval. Po wdrożeniu migracji `0011_document_chunk_review` istniejące dokumenty pozostają `indexed`.
