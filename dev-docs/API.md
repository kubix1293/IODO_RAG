# API v1

OpenAPI jest pod `/docs`. Endpointy obejmują logowanie/wylogowanie, CRUD przebiegu zgłoszenia, start/wznowienie workflow, decyzję problemu, pełny/interaktywny tryb rozwiązania, wynik kroku, feedback, zamknięcie, import wiedzy oraz akceptację/odrzucenie rozwiązania.

Po logowaniu klient otrzymuje cookie HttpOnly i `csrf_token`. Każde modyfikujące żądanie poza loginem wymaga nagłówka `X-CSRF-Token`. Błędy walidacji to 422, brak sesji 401, brak roli 403, konflikt stanu 409.
