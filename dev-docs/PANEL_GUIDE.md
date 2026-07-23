# Instrukcja panelu serwisowego

## Dostęp i role

Panel działa na porcie `8081`. Otwórz `/login` i zaloguj się lokalnym kontem. Konto bootstrap ma nazwę z `SUPPORT_BOOTSTRAP_USER`, a początkowe hasło znajduje się wyłącznie w nieśledzonym `.env`.

Interfejs używa wspólnego układu **SERWISDESK**: ciemnego menu bocznego, jasnego obszaru roboczego, kart formularzy i spójnych oznaczeń statusu. Układ jest responsywny i na wąskim ekranie przenosi nawigację nad treść. Wzorzec wyglądu znajduje się w `docs/serwis-zgloszen.jsx`; produkcyjny panel zachowuje jednak serwerowe logowanie, RBAC, CSRF i istniejące API zamiast demonstracyjnych danych oraz bezpośredniego połączenia z zewnętrznym modelem z pliku wzorcowego.

- `technician`: zgłoszenia, analiza, raport realizacji i ocena;
- `senior_technician`: dodatkowo przypadki, dokumentacja i publikacja wiedzy;
- `admin`: wszystkie uprawnienia seniora i konfiguracja.

## Systemy i izolacja

Początkowe systemy to **ZZL** i **ASW**. Każde zgłoszenie, przypadek, dokument i problem należy do jednego systemu. Wyszukiwanie ZZL nie korzysta z ASW. Dokument globalny jest dostępny klientom tylko w swoim systemie, a prywatny dodatkowo wyłącznie wskazanemu klientowi.

## Nowe zgłoszenie

1. Wybierz **Nowe zgłoszenie serwisowe** (`/tickets/new`).
2. Wybierz klienta, system i opcjonalnie instalację.
3. Opisz objawy, kod błędu, wersję, środowisko i wykonane czynności.
4. Naciśnij **Utwórz i analizuj zgłoszenie**.

Panel automatycznie uruchomi analizę i otworzy stanowisko pracy.

## Stanowisko pracy

Lista spraw znajduje się pod `/tickets`, a szczegóły pod `/tickets/{id}/view`. Widok pokazuje opis, status workera, odpowiedź modelu, dokumentację i podobne przypadki użyte jako źródła, raport realizacji oraz stan publikacji wiedzy.

Przycisk **Uruchom / ponów analizę modelu** tworzy trwałe zadanie. Ekran odświeża się podczas pracy. Na obecnym CPU odpowiedź o limicie 500 tokenów może powstawać około dwóch minut.

Podczas `queued` i `running` panel pokazuje animowany komunikat o wyszukiwaniu źródeł i przygotowaniu odpowiedzi. Jeżeli workflow przejdzie do `needs_information`, ekran wyświetla brakujące pola. Wpisz wartości (albo jawnie „brak”/„nieznana”) i wybierz **Uzupełnij i wznów analizę**. Dane zostaną dołączone do opisu używanego przez retrieval i model.

## Konsultacja AI

Pozycja **Konsultacja AI** (`/assistant`) jest dostępna dla każdego zalogowanego serwisanta. Rozmowę można rozpocząć, podając pełny albo widoczny w panelu skrócony numer ticketu. System automatycznie dobierze klienta, system i opis zgłoszenia. Bez ticketu należy wybrać system oraz opcjonalnie klienta; ten tryb służy do pytań ogólnych i wykonywania czynności na podstawie instrukcji.

Każda kolejna wiadomość lub sprostowanie ponownie uruchamia wyszukiwanie przypadków historycznych, dokumentacji wektorowej i reranking. Model otrzymuje opis ticketu, osiem ostatnich wiadomości oraz aktualnie najlepiej dopasowane materiały. Rozmowy są trwałe i widoczne na liście **Moje konsultacje**.

Konsultacje zachowują izolację ZZL/ASW. Dla ticketu prywatne materiały są ograniczone do jego klienta; rozmowa ogólna bez klienta używa wyłącznie wiedzy globalnej. Przed przekazaniem do modelu ticket, wiadomości i historia są anonimizowane.

## Jak powstaje podpowiedź

Worker wykonuje:

1. rozpoznanie objawów, kodu błędu i wersji;
2. wyszukiwanie dokumentacji właściwego systemu i klienta;
3. dołączenie zatwierdzonych przypadków historycznych tego samego systemu;
4. reranking maksymalnie 20 kandydatów i wybór ośmiu źródeł;
5. rozszerzenie trafień z dokumentacji o poprzedni i następny fragment tej samej instrukcji;
6. wygenerowanie przez zewnętrzny model lub lokalną Ollamę technicznej diagnozy i instrukcji wyłącznie na podstawie trafnych materiałów.

Model wyodrębnia ze zgłoszenia system, moduł, usługę, operację, kod błędu, wersję i objaw. Odpowiedź zaczyna się naturalnym objaśnieniem problemu, a następnie prowadzi serwisanta przez kolejne numerowane czynności. Każdy krok mówi, co zrobić, dlaczego i jaki rezultat sprawdzić. Panel nie prezentuje odpowiedzi w stylu dokumentu prawnego, formalnych cytowań ani znaczników Markdown. Jeśli wiedza jest niewystarczająca, podpowiedź wskazuje dane potrzebne do dalszej diagnozy.

Do modelu nie jest wysyłany cały dokument. Kontekst zawiera tytuły i pełne, najlepiej dopasowane fragmenty wraz z sąsiednimi krokami procedury, maksymalnie do `24 000` znaków. Izolacja systemu i klienta jest sprawdzana także podczas dobierania sąsiednich fragmentów.

Model jedynie doradza i nie wykonuje czynności w systemach klienta.

## Realizacja i ocena

Po wykonaniu czynności technik wybiera wynik (`pomogła`, `częściowo pomogła`, `nie pomogła`), ocenia podpowiedź od 1 do 5, opisuje faktyczne rozwiązanie i opcjonalnie dodaje komentarz. Jeden raport przypada na zgłoszenie; ponowny zapis go aktualizuje.

## Publikacja przez seniora

Po raporcie senior/admin widzi w menu pozycję **Do zatwierdzenia** (`/knowledge/review`). Kolejka pokazuje nieopublikowane rozwiązania wraz z klientem, systemem, opisem zgłoszenia, faktycznym rozwiązaniem i oceną podpowiedzi. Akcja **Oceń i opublikuj** otwiera właściwe zgłoszenie bezpośrednio na formularzu zatwierdzania.

Senior nadaje tytuł, wybiera zakres i publikuje metodę. Panel wiąże lub tworzy problem kanoniczny, tworzy zatwierdzone rozwiązanie i krok procedury oraz przypadek historyczny. Wiedza jest od razu dostępna kolejnym zgłoszeniom tego systemu, a zgłoszenie otrzymuje status `closed`. Raportu nie można opublikować dwukrotnie.

Przed zapisem kurator Qwen porównuje metodę z obecną wiedzą. Może uznać ją za duplikat, dopisać nowy krok do tej samej metody, utworzyć alternatywne rozwiązanie istniejącego problemu albo nowy problem. Senior wybiera przy publikacji zakres globalny lub prywatny bieżącego klienta.

## Przypadki historyczne

Pod `/cases` senior/admin może podać system, zakres globalny albo prywatny klienta, tytuł, opis zgłoszenia, rozwiązanie oraz opcjonalnie kod błędu, wersję i środowisko. Przypadek jest używany tylko w analizie swojego systemu i — dla zakresu prywatnego — wskazanego klienta.

## Dokumentacja techniczna

Pod `/knowledge` senior/admin:

1. wybiera system;
2. wybiera zakres globalny albo prywatny klienta;
3. załącza PDF lub DOCX;
4. uruchamia import i indeksowanie.

Dokument jest parsowany, dzielony domyślnie na fragmenty `1600/220`, embedowany do 384 wymiarów i zapisywany w PostgreSQL/pgvector. Fragmenty stają się źródłami odpowiedzi modelu.

Instrukcje techniczne mają osobną strategię: chunker rozpoznaje procedury i listy kroków, zachowuje nagłówki DOCX, nie łączy różnych procedur oraz powtarza nazwę procedury w długich fragmentach. Overlap działa tylko wewnątrz tej samej procedury.

Dla zakresu globalnego pole klienta nie jest wysyłane. Backend toleruje również pustą wartość starszego formularza i traktuje ją jako brak klienta.

## Ustawienia administratora

Administrator ma w menu pozycję **Ustawienia** (`/settings`). Może tam:

- utworzyć konto serwisanta, starszego serwisanta albo administratora;
- dodać klienta do katalogu używanego przy nowych zgłoszeniach;
- ustawić czas oczekiwania na Ollamę, limit tokenów odpowiedzi, liczbę kandydatów i źródeł oraz rozmiar i nakładanie fragmentów dokumentacji;
- włączyć zewnętrzny model jako pierwszy wybór albo natychmiast przełączyć system na samą lokalną Ollamę.

Parametry obowiązują przy kolejnej analizie lub imporcie i nie wymagają restartu kontenerów. Zmiany zapisują się w audycie. Sekrety i adresy infrastruktury nadal konfiguruje się wyłącznie przez środowisko uruchomieniowe.

Domyślny limit generowanej odpowiedzi wynosi `1200` tokenów. Administrator może ustawić wartość od `100` do `2000` tokenów.

Po analizie stanowisko zgłoszenia pokazuje użyty generator: `zewnętrzne API`, `lokalna Ollama (fallback)` albo `lokalna Ollama`, a także liczbę wykonanych redakcji danych.

## Statusy i wznowienie

- `needs_information`: brakuje danych krytycznych;
- `failed_retryable`: usługa modelowa czasowo nie odpowiedziała;
- `awaiting_problem_decision`: podpowiedź jest gotowa;
- `awaiting_feedback`: zapisano realizację lub oczekiwany jest feedback;
- `closed`: sprawa zakończona.

Zadania pozostają w PostgreSQL. Restart workera nie usuwa kolejki ani szyfrowanego checkpointu. Analizę można ponowić z ekranu sprawy.
