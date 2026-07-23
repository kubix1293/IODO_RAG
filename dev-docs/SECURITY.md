# Bezpieczeństwo

- Hasła: Argon2id; minimum 12 znaków przy tworzeniu.
- Sesje: losowe UUID po stronie serwera, 12 godzin, cookie HttpOnly/SameSite=Strict i Secure pod HTTPS.
- CSRF: osobny losowy token porównywany z sesją.
- RBAC: technician, senior_technician, admin; publikacja wiedzy wymaga roli senior lub admin.
- Dodawanie i przeglądanie przypadków historycznych wymaga roli senior lub admin; każdy odczyt wymaga wskazania jednego systemu.
- Import dokumentacji technicznej wymaga roli senior lub admin. Zakres klienta wymaga jawnego `client_id`; wyszukiwanie nadal filtruje system i klienta.
- Technik może zapisać raport realizacji i ocenę, lecz tylko senior/admin może opublikować metodę jako zatwierdzoną wiedzę systemu.
- Izolacja: program zawsze obowiązkowy; prywatna wiedza tylko dla klienta zgłoszenia.
- Anonimizacja: źródła przekazywane do UI są redagowane; test obejmuje e-mail, telefon i identyfikatory.
- Audyt: wszystkie modyfikujące operacje zapisują aktora, akcję, encję i metadane.
- Panel `/settings`, tworzenie kont i klientów oraz parametryzacja są dostępne wyłącznie administratorowi. Login jest ograniczony do bezpiecznego zestawu znaków, hasło ma minimum 12 znaków, a duplikaty loginów i klientów są odrzucane.
- Panel nie pozwala zmieniać sekretów, adresów usług ani danych połączenia z bazą. Edytowalne parametry mają walidowane zakresy po stronie API.
- Przed wejściem zgłoszenia do StateGraph oraz przed zapisaniem wyników agentów do checkpointów redagowane są: e-mail, PESEL/inne identyfikatory 11-cyfrowe, telefon, NIP, REGON, IBAN, IP, jawnie oznaczone dane logowania, osoba, adres i klient. Zewnętrzny prompt nie zawiera nazw plików źródłowych ani nazwy klienta.
- Zewnętrzne API otrzymuje pseudonim klienta HMAC `K-…`. Mapowanie pozostaje lokalne. Detekcja wzorcami nie daje gwarancji rozpoznania dowolnej informacji wrażliwej zapisanej nietypowo; przed użyciem produkcyjnym wymagane są testy DLP na reprezentatywnych zgłoszeniach oraz umowa z dostawcą dotycząca retencji i trenowania.
- Kurator wiedzy działa wyłącznie po akcji seniora/admina. Model nie zapisuje bezpośrednio do bazy: jego akcja i identyfikatory są walidowane, a prywatna metoda klienta nie może zmodyfikować rozwiązania globalnego ani innego klienta.

Przed pilotem należy ustawić losowe `SUPPORT_SESSION_SECRET`, zgodne `SUPPORT_CHECKPOINT_KEY` i `LANGGRAPH_AES_KEY`, zmienić hasło bootstrap i wystawić panel wyłącznie przez HTTPS/VPN.
