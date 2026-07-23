# Testowanie

Testy jednostkowe uruchamia `pytest tests`. Krytyczne integracje: migracja na pustej bazie, izolacja dwóch klientów, TEI 384D, `/rerank`, restart workera oraz odszyfrowanie checkpointu.

Przed pilotem wymagany jest zanonimizowany zestaw minimum 30 przypadków: co najmniej 80% właściwych problemów w top 5 i rozwiązań w top 3. Warunkiem bezwzględnym jest brak wycieku między klientami. E2E obejmuje oba tryby procedury, odrzucenie powiązania, każdy feedback, draft i akceptację seniora.

Lokalny test `tests/integration_smoke.py` tworzy oznaczone dane testowe i sprawdza login, CSRF, kolejkę workera, workflow krokowy, feedback, zamknięcie, audyt, RBAC oraz izolację dwóch klientów. Uruchamiać wyłącznie na środowisku nieprodukcyjnym.

`tests/curation_smoke.py` tworzy tymczasowy problem, rozwiązanie, zgłoszenie i raport, wywołuje kuratora przez API, sprawdza użycie modelu zewnętrznego, prywatny zakres klienta i zapis decyzji, a następnie usuwa własne dane testowe.

Testy chunkingu sprawdzają rozpoznanie instrukcji, zachowanie nagłówka DOCX i brak połączenia dwóch procedur nawet wtedy, gdy overlap jest większy od ostatniego kroku.

Test promptu odpowiedzi sprawdza obecność technicznej struktury, nacisk na słowa kluczowe oraz zakaz stylu prawnego i numerowania materiałów. Po zmianie promptu należy dodatkowo wykonać neutralne wywołanie skonfigurowanego modelu i potwierdzić pięć wymaganych nagłówków odpowiedzi.
