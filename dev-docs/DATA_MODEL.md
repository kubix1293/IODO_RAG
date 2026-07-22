# Model danych

Migracja Alembic `0001_support` jest źródłem prawdy. Główne relacje:

```text
public.clients -> client_installations -> client_notes
programs -> tickets -> ticket_problem_links -> canonical_problems -> solutions -> solution_steps
programs -> historical_cases
tickets -> resolution_attempts -> step_results / feedback
tickets -> ticket_resolution_reports -> published solution
programs -> knowledge_documents -> knowledge_chunks -> solution_evidence
tickets -> support_jobs / workflow_checkpoints / audit_events
```

Globalna wiedza ma `client_id IS NULL`; prywatna ma `scope=client` i klienta. Każde zapytanie wiedzy wymaga programu i dopuszcza tylko globalne rekordy oraz rekordy aktualnego klienta.

`historical_cases` przechowuje opis zgłoszenia i rozwiązanie oraz zawsze wymaga jednego `program_id`. Początkowe systemy to ZZL i ASW. Odczyt przypadków nie ma trybu „wszystkie systemy”; wymagany filtr programu zapobiega mieszaniu baz problemów.

`ticket_resolution_reports` przechowuje wynik realizacji, ocenę podpowiedzi 1–5 oraz faktycznie zastosowaną metodę. Jeden raport przypada na zgłoszenie. Po publikacji przez seniora wskazuje utworzone zatwierdzone rozwiązanie.
