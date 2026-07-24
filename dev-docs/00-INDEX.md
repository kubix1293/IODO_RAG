# Panel asystenta serwisowego — indeks

Status: działająca wersja pilotażowa na `:8081`. Zaimplementowano StateGraph z dwoma agentami DB, hybrydowy LLM z pierwszeństwem zewnętrznego API, import dokumentacji z akceptacją podziału, konsultacje AI, kurację wiedzy oraz obrazy zgłoszeń, rozwiązań i przypadków historycznych. Przed udostępnieniem klientom nadal wymagane są testy ewaluacyjne i potwierdzenie braku wycieków między klientami.

## Stan wdrożenia 2026-07-24

- migracje bazy są aktualne do `0013_historical_case_images`;
- screeny można przypisywać jako `problem` lub `solution` do zgłoszenia i przypadku historycznego;
- administrator jawnie potwierdza anonimizację przed użyciem obrazu przez zewnętrzny model;
- analiza wybiera maksymalnie cztery obrazy: najpierw bieżącego zgłoszenia, następnie z dopasowanych przypadków;
- panel prezentuje obrazy powiązane z odnalezionymi przypadkami i rozwiązaniami;
- zestaw jednostkowy obejmuje 32 testy i przechodzi w obrazie `support-web`.

- [Architektura](ARCHITECTURE.md)
- [Model danych](DATA_MODEL.md)
- [Procesy](WORKFLOWS.md)
- [Orkiestracja i agenci](AGENTS.md)
- [API](API.md)
- [Bezpieczeństwo](SECURITY.md)
- [Operacje](OPERATIONS.md)
- [Testowanie](TESTING.md)
- [Roadmapa](ROADMAP.md)
- [Plan kolejnych kroków](NEXT_STEPS.md)
- [Instrukcja panelu serwisowego](PANEL_GUIDE.md)
- [Punkt powrotu sesji](SESSION_HANDOFF.md)
- [ADR-001](adr/001-separate-support-panel.md)
