# Model danych

Migracja Alembic `0001_support` jest źródłem prawdy. Główne relacje:

```text
public.clients -> client_installations -> client_notes
programs -> tickets -> ticket_problem_links -> canonical_problems -> solutions -> solution_steps
tickets -> resolution_attempts -> step_results / feedback
programs -> knowledge_documents -> knowledge_chunks -> solution_evidence
tickets -> support_jobs / workflow_checkpoints / audit_events
```

Globalna wiedza ma `client_id IS NULL`; prywatna ma `scope=client` i klienta. Każde zapytanie wiedzy wymaga programu i dopuszcza tylko globalne rekordy oraz rekordy aktualnego klienta.
