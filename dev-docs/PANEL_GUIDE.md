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

Do nowego lub istniejącego zgłoszenia można dodać JPEG, PNG albo WebP jako **objaw** lub **krok rozwiązania**. Obraz objawu jest widoczny lokalnie, ale model go nie otrzyma, dopóki administrator nie wybierze **Potwierdź anonimizację i dopuść do AI**, a serwisant nie uruchomi ponownie analizy. Obraz rozwiązania zostaje dołączony do metody podczas publikacji wiedzy i pojawia się przy kolejnych dopasowanych odpowiedziach.

Formularz **Zgłoś realizację i oceń podpowiedź** ma osobne pole do dodania wielu zdjęć kolejnych kroków lub rezultatu. Najpierw zapisywany jest raport tekstowy, następnie obrazy typu `solution`. Przed publikacją rozwiązania należy sprawdzić, czy wszystkie zdjęcia są widoczne w zgłoszeniu.

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

Jeśli opis nie zawiera błędu, awarii, niedziałania ani innego objawu problemu, system traktuje go jako zadanie. Wtedy podpowiedź jest krótka, wskazuje najważniejsze rzeczy do zapamiętania — w tym właściwe uwagi klienta — i odsyła do **Konsultacji AI** po szczegółowe kroki.

Do modelu nie jest wysyłany cały dokument. Kontekst zawiera tytuły i pełne, najlepiej dopasowane fragmenty wraz z sąsiednimi krokami procedury, maksymalnie do `24 000` znaków. Izolacja systemu i klienta jest sprawdzana także podczas dobierania sąsiednich fragmentów.

Model jedynie doradza i nie wykonuje czynności w systemach klienta.

## Realizacja i ocena

Po wykonaniu czynności technik wybiera wynik (`pomogła`, `częściowo pomogła`, `nie pomogła`), ocenia podpowiedź od 1 do 5, opisuje faktyczne rozwiązanie i opcjonalnie dodaje komentarz. Jeden raport przypada na zgłoszenie; ponowny zapis go aktualizuje.

## Publikacja przez seniora

Po raporcie senior/admin widzi w menu pozycję **Do zatwierdzenia** (`/knowledge/review`). Kolejka pokazuje niezatwierdzone raporty wraz z klientem, systemem, opisem zgłoszenia, faktycznym rozwiązaniem i oceną podpowiedzi. Akcja otwiera właściwe zgłoszenie bezpośrednio na formularzu zatwierdzania.

Senior nie musi podawać tytułu — wybiera zakres i zatwierdza skuteczność. Duplikat tylko aktualizuje statystyki istniejącego rozwiązania, a uzupełnienie dopisuje nową wiedzę bez tworzenia kolejnego przypadku. Osobny przypadek z tytułem wygenerowanym przez kuratora powstaje wyłącznie dla nowego problemu lub nowej metody. Zgłoszenie otrzymuje status `closed`, a raportu nie można zatwierdzić dwukrotnie.

Na stronie `/cases` znajduje się lista przypadków i formularz tworzenia wraz z osobnymi polami na screeny błędu oraz rozwiązania. Kliknięcie tytułu otwiera kartę `/cases/{id}`, gdzie senior może później dodawać i usuwać obrazy. Administrator używa przycisku „Potwierdź anonimizację i dopuść do AI”. Dopiero wtedy obraz może uczestniczyć w analizie następnego zgłoszenia.

Przed zapisem kurator Qwen porównuje metodę z obecną wiedzą. Może uznać ją za duplikat, dopisać nowy krok do tej samej metody, utworzyć alternatywne rozwiązanie istniejącego problemu albo nowy problem. Senior wybiera przy publikacji zakres globalny lub prywatny bieżącego klienta.

## Przypadki historyczne

Pod `/cases` senior/admin może podać system, zakres globalny albo prywatny klienta, tytuł, opis zgłoszenia, rozwiązanie oraz opcjonalnie kod błędu, wersję i środowisko. Przypadek jest używany tylko w analizie swojego systemu i — dla zakresu prywatnego — wskazanego klienta.

## Dokumentacja techniczna

Pod `/knowledge` senior/admin:

1. wybiera system;
2. wybiera zakres globalny albo prywatny klienta;
3. załącza PDF lub DOCX;
4. przesyła dokument w stanie roboczym;
5. otwiera dokument i uruchamia analizę podziału przez AI;
6. przegląda mapę, tytuły, moduły, operacje, strony i dokładną treść propozycji;
7. wybiera **Akceptuję podział i indeksuję**.

Embedding 384D powstaje dopiero po akceptacji. Do tego czasu propozycje nie uczestniczą w wyszukiwaniu. Model analizuje mapę całej instrukcji, a następnie grupuje małe, kolejne części i nadaje im tytuł techniczny, moduł, operację, typ oraz słowa kluczowe. Aplikacja zachowuje oryginalny tekst i wymusza maksymalnie `3600` znaków na zaakceptowany fragment.

Lista `/knowledge` pokazuje wszystkie dokumenty, ich system, zakres, stan i liczbę fragmentów. Dokument można usunąć wraz z plikiem i chunkami, chyba że jest powiązanym dowodem zatwierdzonego rozwiązania.

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
