# Plan kolejnych kroków

Aktualizowano: 2026-07-22

## Zasady realizacji

Etapy wykonujemy kolejno. Etap uznajemy za ukończony dopiero po spełnieniu kryteriów odbioru i zapisaniu wyniku poniżej. Zmiana zachowania i odpowiadająca jej dokumentacja trafiają do tego samego commitu.

## 1. Konfiguracja produkcyjna

Status: **ukończony**

- wygenerować unikalny sekret sesji i klucz szyfrowania checkpointów;
- ustawić konto bootstrap bez wartości przykładowych;
- sprawdzić, że `.env` nie jest śledzony przez Git;
- zweryfikować konfigurację Compose bez ujawniania sekretów.

Kryterium odbioru: wszystkie wymagane zmienne są obecne, nie są wartościami przykładowymi i nie trafiają do repozytorium.

## 2. Uruchomienie pełnego stosu

Status: **ukończony**

- uruchomić PostgreSQL, TEI, Ollamę, reranker, `support-web` i `support-worker`;
- pobrać wymagane modele;
- sprawdzić healthchecki, port `8081` i logi startowe.

Kryterium odbioru: wszystkie usługi są zdrowe, panel odpowiada na `/health`, a worker nie ma błędów startowych.

## 3. Testy integracyjne

Status: **ukończony**

- przetestować logowanie, CSRF i RBAC;
- przetestować embedding 384D, reranking i Ollamę;
- przejść pełny workflow zgłoszenia;
- przerwać worker i potwierdzić wznowienie z checkpointu;
- potwierdzić izolację wiedzy dwóch klientów.

Kryterium odbioru: scenariusze integracyjne przechodzą, a brak wycieku między klientami jest udokumentowany.

## 4. Zestaw ewaluacyjny

Status: **w toku — oczekuje na dane historyczne**

- przygotować minimum 30 zanonimizowanych przypadków historycznych;
- opisać oczekiwany problem i rozwiązanie;
- uruchomić pomiar top 5/top 3.

Panel przyjmowania przypadków jest dostępny pod `/cases` dla seniora/admina. Systemy ZZL i ASW są rozdzielone obowiązkowym `program_id`. Oczekujemy na wskazanie pliku źródłowego z przykładami.

Kryterium odbioru: minimum 80% właściwych problemów w top 5 i 80% właściwych rozwiązań w top 3.

## 5. Funkcje pilotażowe

Status: **oczekuje**

- dodać dashboard spraw, czasu rozwiązania, skuteczności i eskalacji;
- dodać kolejkę weryfikacji feedbacku i wersjonowanie rozwiązań;
- przygotować procedurę backupu, odtworzenia i rollbacku.

Kryterium odbioru: senior może obsłużyć kolejkę wiedzy, administrator widzi metryki, a odtworzenie danych jest sprawdzone.

## 6. Kontrolowany pilotaż

Status: **oczekuje**

- dopuścić wyłącznie wskazanych serwisantów;
- monitorować jakość, błędy, eskalacje i incydenty prywatności;
- zebrać dane do decyzji o dalszej automatyzacji.

Kryterium odbioru: zakończony przegląd pilotażu i udokumentowana decyzja dotycząca następnej wersji.

## Dziennik wykonania

- 2026-07-22: utworzono plan; rozpoczęto etap 1.
- 2026-07-22: etap 1 ukończony; sekrety wygenerowane, `.env` ma tryb 0600 i pozostaje poza Git. Rozpoczęto etap 2.
- 2026-07-22: etap 2 ukończony; pełny stos uruchomiony. Reranker otrzymał limit batcha 2048/32 z powodu hosta 8 GiB. Rozpoczęto etap 3.
- 2026-07-22: etap 3 ukończony; modele, API, CSRF, RBAC, audyt, izolacja klientów i wznowienie kolejki po restarcie przeszły testy. Naprawiono zapis niefinitywnych wyników rankingu w checkpointach. Rozpoczęto etap 4; potrzebne są rzeczywiste zanonimizowane przypadki.
- 2026-07-22: dodano systemy ZZL i ASW oraz formularz `/cases` dla seniora/admina. Test potwierdził, że lista ZZL nie zwraca przypadku ASW, a technik otrzymuje 403.
- 2026-07-22: dodano formularz `/tickets/new` dla ręcznych zgłoszeń i `/knowledge` dla systemowego importu PDF/DOCX. Dokumentacja jest indeksowana i dostępna retrievalowi wyłącznie w swoim systemie oraz zakresie klienta.
- 2026-07-22: dodano stanowisko `/tickets/{id}/view`: odpowiedź Ollamy ze źródłami, raport realizacji, ocenę podpowiedzi oraz publikację faktycznej metody przez seniora do wiedzy systemu.
- 2026-07-22: uzupełniono UX analizy o animację `queued/running`, widoczne pytania `needs_information`, formularz uzupełnień i wznowienie z przekazaniem odpowiedzi do modelu.
