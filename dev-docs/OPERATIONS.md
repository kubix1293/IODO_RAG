# Operacje

1. Ustaw sekrety w `.env` (wartość Fernet dla checkpointów można utworzyć poleceniem administracyjnym poza repozytorium).
2. `docker compose build support-web support-worker`
3. `docker compose up -d postgres tei ollama reranker support-web support-worker`
4. Migracje ręczne: `docker compose run --rm --entrypoint alembic support-web upgrade head`.
5. Zdrowie: `GET http://localhost:8081/health`; stan: `docker compose ps`; logi: `docker compose logs support-web support-worker`.

Backup musi obejmować bazę PostgreSQL i `/data/support-uploads`. Odtworzenie należy ćwiczyć przed pilotem. Worker jest bezstanowy i może mieć wiele replik.
