# Testowanie

Testy jednostkowe uruchamia `pytest tests`. Krytyczne integracje: migracja na pustej bazie, izolacja dwóch klientów, TEI 384D, `/rerank`, restart workera oraz odszyfrowanie checkpointu.

Przed pilotem wymagany jest zanonimizowany zestaw minimum 30 przypadków: co najmniej 80% właściwych problemów w top 5 i rozwiązań w top 3. Warunkiem bezwzględnym jest brak wycieku między klientami. E2E obejmuje oba tryby procedury, odrzucenie powiązania, każdy feedback, draft i akceptację seniora.

Lokalny test `tests/integration_smoke.py` tworzy oznaczone dane testowe i sprawdza login, CSRF, kolejkę workera, workflow krokowy, feedback, zamknięcie, audyt, RBAC oraz izolację dwóch klientów. Uruchamiać wyłącznie na środowisku nieprodukcyjnym.

`tests/curation_smoke.py` tworzy tymczasowy problem, rozwiązanie, zgłoszenie i raport, wywołuje kuratora przez API, sprawdza użycie modelu zewnętrznego, prywatny zakres klienta i zapis decyzji, a następnie usuwa własne dane testowe.

Testy chunkingu sprawdzają rozpoznanie instrukcji, zachowanie nagłówka DOCX, brak połączenia dwóch procedur nawet wtedy, gdy overlap jest większy od ostatniego kroku, oraz twardy limit dla jednego bardzo dużego bloku.

Testy propozycji AI sprawdzają ciągłość i kompletność numerów części, limit wielkości grupy oraz zachowanie dokładnego tekstu źródłowego. Integracyjnie należy sprawdzić stany dokumentu, blokadę retrieval przed akceptacją, utworzenie embeddingów dopiero po akceptacji, RBAC, CSRF i usunięcie dokumentu.

Test promptu odpowiedzi sprawdza dialogowe wyjaśnienie, numerowane kroki, nacisk na słowa kluczowe oraz zakaz stylu prawnego i składni Markdown. Osobny test sprawdza usunięcie gwiazdek i znaczników nagłówków z odpowiedzi modelu.

Testy kontekstu LLM sprawdzają przekazanie tytułu i pełnego fragmentu, dobieranie fragmentu poprzedniego oraz następnego, oznaczenie ich roli i nieprzekroczenie globalnego budżetu `24 000` znaków.

Testy obrazów muszą sprawdzać walidację MIME i rozmiaru, RBAC zatwierdzenia do AI, brak wysyłki niezatwierdzonego obrazu, multimodalny format `image_url`, tekstowy fallback Ollamy, powiązanie obrazu rozwiązania podczas publikacji oraz uwierzytelniony podgląd.

Dla obrazów przypadków testujemy także filtrowanie identyfikatorów wyłącznie do zrerankowanych `historical_case`, zachowanie kolejności trafień, deduplikację oraz pierwszeństwo obrazów bieżącego zgłoszenia w limicie czterech.

Testy kuracji sprawdzają, że `duplicate` i `supplement` nie tworzą przypadku historycznego, wszystkie akcje aktualizują właściwy licznik skuteczności, a `new_solution` i `new_problem` tworzą osobny przypadek z tytułem kuratora.
