# Roadmapa

Po pilotażu: dashboard jakości i eskalacji, wersjonowanie/wycofanie rozwiązań, pełny importer asynchroniczny oraz klasyfikacja feedbacku przez LLM z kolejką weryfikacji. Trwałość grafu już opiera się na przygotowanej fabryce `AsyncPostgresSaver`; kolejne węzły będą przenoszone z kolejki deterministycznej bez zmiany API. Dopiero dane pilotażowe mogą uzasadnić pierwszą linię dla klientów. Narzędzia diagnostyczne pozostają domyślnie tylko do odczytu.
