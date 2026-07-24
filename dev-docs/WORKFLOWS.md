# Procesy

Stany: `new → needs_information → awaiting_problem_decision → ready → in_progress → awaiting_feedback → closed`. Z każdego automatycznego etapu możliwe jest `failed_retryable` i wznowienie.

Worker uruchamia deterministyczny LangGraph `StateGraph`: interpretację, uzupełnienie, równoległą grupę dwóch agentów DB, reranking (domyślnie 8 źródeł) i generowanie odpowiedzi. Graf zatrzymuje się przed decyzją serwisanta. Powiązanie problemu, tryb rozwiązania, wyniki kroków i feedback są osobnymi, audytowanymi komendami. Statystyka rozwiązania rośnie dopiero przy zamknięciu.

`history_agent` pobiera zatwierdzone przypadki historyczne, a `documentation_agent` wykonuje wyszukiwanie full-text/pgvector. Oba zawsze filtrują ten sam system, a agent dokumentacji dodatkowo widoczność klienta. Ollama tworzy proponowaną diagnozę i kroki na podstawie zrerankowanych źródeł. Po realizacji technik zapisuje ocenę i faktyczną metodę, a senior może opublikować ją jako zatwierdzone rozwiązanie dostępne następnym zgłoszeniom tego systemu.

W zgłoszeniu sklasyfikowanym jako problem brak kodu błędu lub wersji zatrzymuje graf w `needs_information`. Panel renderuje pytania, a `/workflow/resume` zapisuje odpowiedzi. Worker buduje z opisu i uzupełnień wspólny tekst wejściowy dla embeddingu, rerankera i Ollamy.

Interpretacja rozróżnia `problem` i `task`. Brak kodu błędu lub wersji zatrzymuje graf tylko dla zgłoszenia opisującego awarię, niedziałanie, blokadę albo komunikat błędu. Zwykła czynność — np. aktualizacja, konfiguracja lub instalacja bez objawu awarii — przechodzi bez pytań o błąd i wersję.

Dla `task` odpowiedź jest krótką listą „W ramach tego zadania pamiętaj o”, uwzględnia dostępną wiedzę klienta i kończy się odesłaniem do zakładki **Konsultacja AI** po szczegółową procedurę. Model nie może dopowiadać awarii ani diagnozy, której nie ma w treści.

Po zapisaniu realizacji senior wybiera zakres globalny albo prywatny klienta i uruchamia kuratora wiedzy. Model porównuje przypadek z problemami i rozwiązaniami tego samego systemu oraz dopuszczalnego zakresu. Zwraca `duplicate`, `supplement`, `new_solution` albo `new_problem`. Kod waliduje wszystkie ID. Prywatna wiedza nie może uzupełnić globalnego rozwiązania — powstaje wtedy prywatny wariant pod istniejącym problemem.

Zatwierdzenie raportu nie wymaga ręcznego tytułu. Dla `duplicate` system wyłącznie zwiększa licznik `success_count`, `partial_count` albo `failure_count` wskazanego rozwiązania. Dla `supplement` aktualizuje licznik i dopisuje niepowtarzający się krok. Nowy `historical_case` jest tworzony wyłącznie dla `new_solution` lub `new_problem`; tytuł generuje kurator. Zatwierdzone rozwiązania i ich kroki są niezależnymi kandydatami retrievalu, więc uzupełnienie jest wyszukiwalne bez sztucznego duplikowania przypadku.

## Import instrukcji z akceptacją

```text
przesłanie PDF/DOCX
→ pending_analysis
→ mapa całego dokumentu (pełny tekst małego dokumentu lub próbki kolejnych stron)
→ techniczny podział bazowy ≤ 1200 znaków
→ LLM grupuje wyłącznie kolejne części i nadaje metadane
→ walidacja kompletności, kolejności i limitu ≤ 3600 znaków
→ pending_review
→ podgląd seniora/admina
→ akceptacja
→ embedding TEI 384D
→ indexed / dostępny w retrieval
```

Model nie zapisuje własnej parafrazy instrukcji. Wskazuje numery kolejnych części do połączenia i metadane. Serwer składa `chunk_text` wyłącznie z oryginalnego tekstu źródłowego, odrzuca pominięcia, powtórzenia, zmianę kolejności, nieciągłe grupy oraz zbyt duże fragmenty. Błąd odpowiedzi JSON uruchamia bezpieczny podział awaryjny, który również czeka na człowieka.

## Obrazy zgłoszeń

```text
upload obrazu problemu
→ lokalny podgląd / brak dostępu AI
→ administrator potwierdza anonimizację
→ ponowienie analizy
→ zewnętrzny Qwen otrzymuje tekst i maks. 4 zatwierdzone obrazy
```

Lokalna Ollama pozostaje fallbackiem tekstowym. Obraz typu `solution` nie służy do diagnozy. Przy publikacji raportu zostaje powiązany z rozwiązaniem, a później jest prezentowany serwisantowi, gdy retrieval odnajdzie przypadek tego rozwiązania.

Zdjęcia rozwiązania można przesłać bezpośrednio w formularzu raportu realizacji. Frontend zapisuje raport, potem każdy obraz jako `purpose=solution`; publikacja wiedzy tworzy relacje `solution_image_links`.

Senior może też dołączyć screeny błędu i rozwiązania bezpośrednio do istniejącego przypadku historycznego. W kolejnej analizie najpierw wybierane są zatwierdzone obrazy bieżącego ticketu, a potem zatwierdzone obrazy przypadków obecnych w zrerankowanych źródłach, łącznie maksymalnie cztery. Prompt rozróżnia stan bieżący od historycznego przykładu.
