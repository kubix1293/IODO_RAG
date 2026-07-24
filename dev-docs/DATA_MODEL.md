# Model danych

Migracja Alembic `0001_support` jest źródłem prawdy. Główne relacje:

```text
public.clients -> client_installations -> client_notes
programs -> tickets -> ticket_problem_links -> canonical_problems -> solutions -> solution_steps
programs -> historical_cases
tickets -> resolution_attempts -> step_results / feedback
tickets -> ticket_resolution_reports -> published solution
tickets -> ticket_images -> solution_image_links -> solutions
programs -> knowledge_documents -> knowledge_chunk_proposals
                             \-> knowledge_chunks -> solution_evidence
tickets -> support_jobs / workflow_checkpoints / audit_events
users -> application_settings
```

Globalna wiedza ma `client_id IS NULL`; prywatna ma `scope=client` i klienta. Każde zapytanie wiedzy wymaga programu i dopuszcza tylko globalne rekordy oraz rekordy aktualnego klienta.

`historical_cases` przechowuje opis zgłoszenia i rozwiązanie oraz zawsze wymaga jednego `program_id`. Początkowe systemy to ZZL i ASW. Odczyt przypadków nie ma trybu „wszystkie systemy”; wymagany filtr programu zapobiega mieszaniu baz problemów.

Migracja `0006_knowledge_curation` dodaje do przypadku opcjonalny `client_id` oraz powiązania z problemem kanonicznym i rozwiązaniem. `client_id IS NULL` oznacza przypadek globalny; przypadek prywatny jest zwracany tylko dla zgłoszeń tego klienta. `knowledge_curation_runs` przechowuje decyzję modelu, zakres, dostawcę i aktora publikacji.

`ticket_resolution_reports` przechowuje wynik realizacji, ocenę podpowiedzi 1–5 oraz faktycznie zastosowaną metodę. Jeden raport przypada na zgłoszenie. Po publikacji przez seniora wskazuje utworzone zatwierdzone rozwiązanie.

Migracja `0004_application_settings` dodaje ustawienia typu klucz–wartość wraz z administratorem i czasem ostatniej zmiany. Do bazy trafiają wyłącznie kontrolowane wartości liczbowe; sekrety pozostają w środowisku uruchomieniowym.

Migracja `0005_external_llm` dodaje przełącznik `external_llm_enabled`. Domyślna wartość włącza strategię external-first, ale brak kompletnej konfiguracji dostawcy powoduje bezpieczny fallback do Ollamy.

Migracja `0011_document_chunk_review` dodaje kontrolowany cykl życia dokumentu:
`pending_analysis → analyzing → pending_review → indexed` albo `analysis_failed`.
`knowledge_chunk_proposals` przechowuje dokładną, jeszcze nieprzeszukiwalną treść propozycji, kolejność oraz metadane: tytuł techniczny, moduł, operację, typ treści, słowa kluczowe, strony i mapę dokumentu. Dopiero akceptacja kopiuje propozycje do `knowledge_chunks` i wylicza embeddingi. Istniejące dokumenty otrzymują stan `indexed`.

Migracja `0012_ticket_images` dodaje `ticket_images` z przeznaczeniem `problem` albo `solution`, ścieżką kontrolowanego pliku, MIME, rozmiarem, autorem oraz osobnym zatwierdzeniem administratora do AI. `solution_image_links` wiąże obrazy wykonanych czynności z opublikowanym rozwiązaniem.

Migracja `0013_historical_case_images` dodaje analogiczne obrazy bezpośrednio do `historical_cases`. `purpose=problem` opisuje objaw lub komunikat błędu, a `purpose=solution` krok albo rezultat naprawy. Każdy obraz ma niezależny stan dopuszczenia do AI.
