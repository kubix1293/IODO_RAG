# Procesy

Stany: `new → needs_information → awaiting_problem_decision → ready → in_progress → awaiting_feedback → closed`. Z każdego automatycznego etapu możliwe jest `failed_retryable` i wznowienie.

Worker wykonuje deterministycznie interpretację, uzupełnienie, retrieval hybrydowy (20), reranking (8) i zatrzymuje się przed decyzją serwisanta. Powiązanie problemu, tryb rozwiązania, wyniki kroków i feedback są osobnymi, audytowanymi komendami. Statystyka rozwiązania rośnie dopiero przy zamknięciu.

Retrieval łączy dokumentację techniczną i zatwierdzone przypadki historyczne wyłącznie tego samego systemu. Ollama tworzy proponowaną diagnozę i kroki na podstawie maksymalnie ośmiu źródeł. Po realizacji technik zapisuje ocenę i faktyczną metodę, a senior może opublikować ją jako zatwierdzone rozwiązanie dostępne następnym zgłoszeniom tego systemu.

Brak kodu błędu lub wersji zatrzymuje graf w `needs_information`. Panel renderuje pytania, a `/workflow/resume` zapisuje odpowiedzi. Worker buduje z opisu i uzupełnień wspólny tekst wejściowy dla embeddingu, rerankera i Ollamy.
