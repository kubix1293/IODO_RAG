# Punkt powrotu sesji

Identyfikator: **IODO-SUPPORT-20260722-524DCC8**

Data: 2026-07-22

## Stan

Panel serwisowy działa prawidłowo na porcie `8081`. Ostatnia zweryfikowana baza kodu przed tym dokumentem to commit `524dcc8`.

Aktywne i sprawdzone funkcje:

- logowanie, sesje, CSRF i role;
- systemy ZZL oraz ASW z izolacją wyszukiwania;
- ręczne tworzenie i lista zgłoszeń;
- stanowisko pracy zgłoszenia;
- animowany status analizy `queued/running`;
- widoczne pytania dla `needs_information`;
- uzupełnienie braków i wznowienie workflow;
- retrieval dokumentacji i przypadków tego samego systemu;
- reranking i odpowiedź Ollamy z limitem 500 tokenów;
- raport realizacji i ocena podpowiedzi 1–5;
- publikacja rozwiązania przez seniora do bazy wiedzy;
- ręczne przypadki historyczne;
- import PDF/DOCX w zakresie globalnym lub klienta;
- trwała kolejka, retry i szyfrowane checkpointy.

## Ostatnia diagnoza

Zgłoszenie `19da1a0d-022b-4b1c-ac28-5ed137bda99d` poprawnie przeszło do `needs_information`, ponieważ brakowało kodu błędu i wersji. Panel pokazuje teraz formularz uzupełnienia oraz po wznowieniu przekazuje odpowiedzi do embeddingu, rerankera i Ollamy.

## Weryfikacja

- test formularza uzupełnień na wskazanym zgłoszeniu: zaliczony;
- testy jednostkowe: `7 passed`;
- Compose: poprawna konfiguracja;
- `support-web`, `support-worker`, PostgreSQL, TEI, reranker i Ollama: uruchomione podczas odbioru;
- dokumentacja użytkownika: `PANEL_GUIDE.md`.

## Następny krok

Etap 4 pozostaje otwarty: import minimum 30 rzeczywistych, zanonimizowanych przypadków historycznych i pomiar jakości top 5/top 3. Użytkownik ma wskazać plik źródłowy z przykładami.

## Jak wznowić

W nowej rozmowie podaj identyfikator `IODO-SUPPORT-20260722-524DCC8` i poproś o przeczytanie tego pliku oraz `NEXT_STEPS.md` przed rozpoczęciem zmian.
