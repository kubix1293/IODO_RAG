# Architektura

`support-web:8081` obsługuje wyłącznie HTTP, sesje i decyzje człowieka. `support-worker` pobiera trwałe zadania z PostgreSQL przez `FOR UPDATE SKIP LOCKED`. Oba używają schematu `support`; katalog `public.clients` jest współdzielony. TEI generuje embeddingi 384D, osobny TEI wykonuje `/rerank`, a Ollama jest usługą LLM. V1 nie wykonuje akcji na systemach klientów.

```text
browser -> support-web -> PostgreSQL <- support-worker
                                      -> TEI / reranker / Ollama
```

Awaria modelu zmienia zadanie i zgłoszenie na `failed_retryable`. StateGraph używa szyfrowanego `PostgresSaver`, a `ticket_id` jest identyfikatorem wątku. Tabela `workflow_checkpoints` przechowuje dodatkowy kompatybilny podgląd końcowego stanu.

Worker łączy fragmenty dokumentacji technicznej i zatwierdzone przypadki historyczne. Kandydaci są ograniczani przez system i klienta, rerankowani, a osiem najlepszych trafień stanowi kontekst odpowiedzi Ollamy. Raport realizacji może zostać opublikowany przez seniora jako rozwiązanie dostępne następnym zgłoszeniom.

Import wiedzy stosuje chunking strukturalny. Dla instrukcji granicą jest procedura/nagłówek, następnie kroki i akapity; domyślny rozmiar to 1600 znaków z overlapem 220 znaków bez przenoszenia treści pomiędzy procedurami.

Retrieval jest rozdzielony na równoległą grupę agentów DB: `history_agent` oraz `documentation_agent`. Szczegółową topologię opisuje [AGENTS.md](AGENTS.md).
