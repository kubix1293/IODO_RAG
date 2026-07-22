# Instrukcja panelu serwisowego

## Dostęp i role

Panel działa na porcie `8081`. Otwórz `/login` i zaloguj się lokalnym kontem. Konto bootstrap ma nazwę z `SUPPORT_BOOTSTRAP_USER`, a początkowe hasło znajduje się wyłącznie w nieśledzonym `.env`.

- `technician`: zgłoszenia, analiza, raport realizacji i ocena;
- `senior_technician`: dodatkowo przypadki, dokumentacja i publikacja wiedzy;
- `admin`: wszystkie uprawnienia seniora i konfiguracja.

## Systemy i izolacja

Początkowe systemy to **ZZL** i **ASW**. Każde zgłoszenie, przypadek, dokument i problem należy do jednego systemu. Wyszukiwanie ZZL nie korzysta z ASW. Dokument globalny jest dostępny klientom tylko w swoim systemie, a prywatny dodatkowo wyłącznie wskazanemu klientowi.

## Nowe zgłoszenie

1. Wybierz **Nowe zgłoszenie serwisowe** (`/tickets/new`).
2. Wybierz klienta, system i opcjonalnie instalację.
3. Opisz objawy, kod błędu, wersję, środowisko i wykonane czynności.
4. Naciśnij **Utwórz zgłoszenie**.

Panel automatycznie uruchomi analizę i otworzy stanowisko pracy.

## Stanowisko pracy

Lista spraw znajduje się pod `/tickets`, a szczegóły pod `/tickets/{id}/view`. Widok pokazuje opis, status workera, odpowiedź modelu, dokumentację i podobne przypadki użyte jako źródła, raport realizacji oraz stan publikacji wiedzy.

Przycisk **Uruchom / ponów analizę modelu** tworzy trwałe zadanie. Ekran odświeża się podczas pracy. Na obecnym CPU odpowiedź o limicie 500 tokenów może powstawać około dwóch minut.

Podczas `queued` i `running` panel pokazuje animowany komunikat o wyszukiwaniu źródeł i przygotowaniu odpowiedzi. Jeżeli workflow przejdzie do `needs_information`, ekran wyświetla brakujące pola. Wpisz wartości (albo jawnie „brak”/„nieznana”) i wybierz **Uzupełnij i wznów analizę**. Dane zostaną dołączone do opisu używanego przez retrieval i model.

## Jak powstaje podpowiedź

Worker wykonuje:

1. rozpoznanie objawów, kodu błędu i wersji;
2. wyszukiwanie dokumentacji właściwego systemu i klienta;
3. dołączenie zatwierdzonych przypadków historycznych tego samego systemu;
4. reranking maksymalnie 20 kandydatów i wybór ośmiu źródeł;
5. wygenerowanie przez Ollamę diagnozy i numerowanych kroków wyłącznie na podstawie źródeł.

Model jedynie doradza i nie wykonuje czynności w systemach klienta.

## Realizacja i ocena

Po wykonaniu czynności technik wybiera wynik (`pomogła`, `częściowo pomogła`, `nie pomogła`), ocenia podpowiedź od 1 do 5, opisuje faktyczne rozwiązanie i opcjonalnie dodaje komentarz. Jeden raport przypada na zgłoszenie; ponowny zapis go aktualizuje.

## Publikacja przez seniora

Po raporcie senior/admin widzi sekcję **Publikacja do bazy wiedzy**. Nadaje tytuł i publikuje metodę. Panel wiąże lub tworzy problem kanoniczny, tworzy zatwierdzone rozwiązanie i krok procedury oraz przypadek historyczny. Wiedza jest od razu dostępna kolejnym zgłoszeniom tego systemu. Raportu nie można opublikować dwukrotnie.

## Przypadki historyczne

Pod `/cases` senior/admin może podać system, tytuł, opis zgłoszenia, rozwiązanie oraz opcjonalnie kod błędu, wersję i środowisko. Przypadek jest używany tylko w analizie swojego systemu.

## Dokumentacja techniczna

Pod `/knowledge` senior/admin:

1. wybiera system;
2. wybiera zakres globalny albo prywatny klienta;
3. załącza PDF lub DOCX;
4. uruchamia import i indeksowanie.

Dokument jest parsowany, dzielony na fragmenty `1100/150`, embedowany do 384 wymiarów i zapisywany w PostgreSQL/pgvector. Fragmenty stają się źródłami odpowiedzi modelu.

## Statusy i wznowienie

- `needs_information`: brakuje danych krytycznych;
- `failed_retryable`: usługa modelowa czasowo nie odpowiedziała;
- `awaiting_problem_decision`: podpowiedź jest gotowa;
- `awaiting_feedback`: zapisano realizację lub oczekiwany jest feedback;
- `closed`: sprawa zakończona.

Zadania pozostają w PostgreSQL. Restart workera nie usuwa kolejki ani szyfrowanego checkpointu. Analizę można ponowić z ekranu sprawy.
