# Testowanie

Testy jednostkowe uruchamia `pytest tests`. Krytyczne integracje: migracja na pustej bazie, izolacja dwóch klientów, TEI 384D, `/rerank`, restart workera oraz odszyfrowanie checkpointu.

Przed pilotem wymagany jest zanonimizowany zestaw minimum 30 przypadków: co najmniej 80% właściwych problemów w top 5 i rozwiązań w top 3. Warunkiem bezwzględnym jest brak wycieku między klientami. E2E obejmuje oba tryby procedury, odrzucenie powiązania, każdy feedback, draft i akceptację seniora.

Lokalny test `tests/integration_smoke.py` tworzy oznaczone dane testowe i sprawdza login, CSRF, kolejkę workera, workflow krokowy, feedback, zamknięcie, audyt, RBAC oraz izolację dwóch klientów. Uruchamiać wyłącznie na środowisku nieprodukcyjnym.
