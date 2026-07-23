# API v1

OpenAPI jest pod `/docs`. Endpointy obejmują logowanie/wylogowanie, CRUD przebiegu zgłoszenia, start/wznowienie workflow, decyzję problemu, pełny/interaktywny tryb rozwiązania, wynik kroku, feedback, zamknięcie, import wiedzy oraz akceptację/odrzucenie rozwiązania.

Przypadki historyczne:

- `POST /api/v1/cases` — dodanie opisu zgłoszenia i rozwiązania przez seniora/admina;
- `GET /api/v1/cases?program_id={id}` — lista wyłącznie jednego wskazanego systemu;
- `GET /cases` — formularz panelu dla seniora/admina.

Interfejs panelu udostępnia `GET /login`, `GET /tickets/new` dla ręcznego wprowadzania zgłoszeń oraz `GET /knowledge` dla importu PDF/DOCX przez seniora/admina. Dokument jest zawsze przypisany do jednego systemu oraz zakresu globalnego albo prywatnego klienta.

Stanowisko pracy zgłoszenia:

- `GET /tickets` i `GET /tickets/{id}/view` — lista oraz podgląd opisu, odpowiedzi modelu i źródeł;
- `POST /api/v1/tickets/{id}/resolution-report` — wynik realizacji, ocena 1–5 i faktyczna metoda;
- `POST /api/v1/tickets/{id}/publish-resolution` — publikacja metody przez seniora/admina jako zatwierdzone rozwiązanie i przypadek historyczny.

Po logowaniu klient otrzymuje cookie HttpOnly i `csrf_token`. Każde modyfikujące żądanie poza loginem wymaga nagłówka `X-CSRF-Token`. Błędy walidacji to 422, brak sesji 401, brak roli 403, konflikt stanu 409.

Administracja (wyłącznie `admin`):

- `GET /settings` — panel użytkowników, klientów i parametrów;
- `POST /api/v1/admin/users` — utworzenie konta i przypisanie roli;
- `POST /api/v1/admin/clients` — dodanie klienta do wspólnego katalogu;
- `POST /api/v1/admin/settings` — zapis kontrolowanych parametrów analizy i importu.
