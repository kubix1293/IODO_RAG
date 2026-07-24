# API v1

OpenAPI jest pod `/docs`. Endpointy obejmują logowanie/wylogowanie, CRUD przebiegu zgłoszenia, start/wznowienie workflow, decyzję problemu, pełny/interaktywny tryb rozwiązania, wynik kroku, feedback, zamknięcie, import wiedzy oraz akceptację/odrzucenie rozwiązania.

Przypadki historyczne:

- `POST /api/v1/cases` — dodanie opisu zgłoszenia i rozwiązania przez seniora/admina; opcjonalny `client_id` ustawia zakres prywatny;
- `GET /api/v1/cases?program_id={id}` — lista wyłącznie jednego wskazanego systemu;
- `GET /cases` — formularz panelu dla seniora/admina.

Interfejs panelu udostępnia `GET /login`, `GET /tickets/new` dla ręcznego wprowadzania zgłoszeń oraz `GET /knowledge` dla importu PDF/DOCX przez seniora/admina. Dokument jest zawsze przypisany do jednego systemu oraz zakresu globalnego albo prywatnego klienta.

Dokumentacja techniczna:

- `POST /api/v1/knowledge/documents` — zapisuje plik jako `pending_analysis`; nie tworzy jeszcze embeddingów;
- `GET /knowledge/documents/{id}` — mapa dokumentu, dokładny podgląd propozycji i metadanych;
- `POST /api/v1/knowledge/documents/{id}/analyze` — przekrojowa interpretacja dokumentu i propozycja logicznych chunków przez hybrydowy LLM;
- `POST /api/v1/knowledge/documents/{id}/approve` — akceptacja seniora/admina, embedding 384D i publikacja chunków;
- `DELETE /api/v1/knowledge/documents/{id}` — usuwa plik, propozycje i chunki, o ile dokument nie jest dowodem zatwierdzonego rozwiązania.

Analiza może zakończyć się ostrzeżeniem i deterministycznym podziałem awaryjnym. Taki podział nadal wymaga przeglądu i akceptacji. Endpointy modyfikujące wymagają CSRF.

Stanowisko pracy zgłoszenia:

- `GET /tickets` i `GET /tickets/{id}/view` — lista oraz podgląd opisu, odpowiedzi modelu i źródeł;
- `POST /api/v1/tickets/{id}/resolution-report` — wynik realizacji, ocena 1–5 i faktyczna metoda;
- `POST /api/v1/tickets/{id}/publish-resolution` — zatwierdzenie skuteczności i modelowa kuracja przez seniora/admina; wymaga `scope=global|client`, a `title` jest opcjonalny. Zwraca `curation_action`, `provider` i opcjonalny `historical_case_id`.

Obrazy zgłoszeń:

- `POST /api/v1/tickets/{id}/images` — multipart `purpose=problem|solution` oraz JPEG/PNG/WebP do 10 MB;
- `GET /api/v1/ticket-images/{id}` — uwierzytelniony podgląd obrazu;
- `POST /api/v1/ticket-images/{id}/approve-for-ai` — wyłącznie administrator potwierdza wcześniejszą anonimizację i dopuszcza obraz problemu do zewnętrznego modelu;
- `DELETE /api/v1/ticket-images/{id}` — autor albo senior/admin usuwa obraz.

Obrazy niezatwierdzone nie są wysyłane do modelu. Publikacja rozwiązania wiąże obrazy typu `solution` z zatwierdzoną metodą.

Obrazy w bazie przypadków:

- `POST /api/v1/cases/{id}/images` — senior/admin dodaje JPEG, PNG albo WebP jako `problem` lub `solution`;
- `GET /api/v1/case-images/{id}` — uwierzytelniony podgląd;
- `POST /api/v1/case-images/{id}/approve-for-ai` — administrator potwierdza anonimizację;
- `DELETE /api/v1/case-images/{id}` — autor albo senior/admin usuwa obraz.

Kurator może wskazać istniejące `problem_id` i `solution_id`, ale serwer akceptuje wyłącznie ID wcześniej przekazane modelowi jako kandydaci tego systemu i zakresu. `duplicate` aktualizuje tylko skuteczność, `supplement` dodatkowo uzupełnia istniejące rozwiązanie, a przypadek historyczny powstaje tylko dla `new_solution` lub `new_problem`.

Konsultacje:

- `GET /assistant` — panel trwałych rozmów serwisanta;
- `POST /api/v1/consultations` — tworzy rozmowę dla pełnego/skróconego numeru ticketu albo wskazanego `program_id` i opcjonalnego `client_id`;
- `POST /api/v1/consultations/{id}/messages` — zapisuje pytanie, ponownie wykonuje retrieval i reranking, wywołuje hybrydowy LLM oraz zapisuje odpowiedź wraz ze źródłami.

Serwisant ma dostęp wyłącznie do utworzonych przez siebie rozmów. Kontekst ticketu ustala system i klienta po stronie serwera, więc nie można ich podmienić w żądaniu wiadomości.

Po logowaniu klient otrzymuje cookie HttpOnly i `csrf_token`. Każde modyfikujące żądanie poza loginem wymaga nagłówka `X-CSRF-Token`. Błędy walidacji to 422, brak sesji 401, brak roli 403, konflikt stanu 409.

Administracja (wyłącznie `admin`):

- `GET /settings` — panel użytkowników, klientów i parametrów;
- `POST /api/v1/admin/users` — utworzenie konta i przypisanie roli;
- `POST /api/v1/admin/clients` — dodanie klienta do wspólnego katalogu;
- `POST /api/v1/admin/settings` — zapis kontrolowanych parametrów analizy i importu.

Pole `external_llm_enabled` przełącza strategię generowania: `true` oznacza zewnętrzne API jako pierwszy wybór z automatycznym fallbackiem do Ollamy, `false` wymusza wyłącznie Ollamę. Endpoint nie przyjmuje kluczy API.
