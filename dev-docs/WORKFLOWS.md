# Procesy

Stany: `new → needs_information → awaiting_problem_decision → ready → in_progress → awaiting_feedback → closed`. Z każdego automatycznego etapu możliwe jest `failed_retryable` i wznowienie.

Worker uruchamia deterministyczny LangGraph `StateGraph`: interpretację, uzupełnienie, równoległą grupę dwóch agentów DB, reranking (domyślnie 8 źródeł) i generowanie odpowiedzi. Graf zatrzymuje się przed decyzją serwisanta. Powiązanie problemu, tryb rozwiązania, wyniki kroków i feedback są osobnymi, audytowanymi komendami. Statystyka rozwiązania rośnie dopiero przy zamknięciu.

`history_agent` pobiera zatwierdzone przypadki historyczne, a `documentation_agent` wykonuje wyszukiwanie full-text/pgvector. Oba zawsze filtrują ten sam system, a agent dokumentacji dodatkowo widoczność klienta. Ollama tworzy proponowaną diagnozę i kroki na podstawie zrerankowanych źródeł. Po realizacji technik zapisuje ocenę i faktyczną metodę, a senior może opublikować ją jako zatwierdzone rozwiązanie dostępne następnym zgłoszeniom tego systemu.

Brak kodu błędu lub wersji zatrzymuje graf w `needs_information`. Panel renderuje pytania, a `/workflow/resume` zapisuje odpowiedzi. Worker buduje z opisu i uzupełnień wspólny tekst wejściowy dla embeddingu, rerankera i Ollamy.
