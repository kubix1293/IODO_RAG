# Procesy

Stany: `new → needs_information → awaiting_problem_decision → ready → in_progress → awaiting_feedback → closed`. Z każdego automatycznego etapu możliwe jest `failed_retryable` i wznowienie.

Worker wykonuje deterministycznie interpretację, uzupełnienie, retrieval hybrydowy (20), reranking (8) i zatrzymuje się przed decyzją serwisanta. Powiązanie problemu, tryb rozwiązania, wyniki kroków i feedback są osobnymi, audytowanymi komendami. Statystyka rozwiązania rośnie dopiero przy zamknięciu.
