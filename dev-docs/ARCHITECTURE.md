# Architektura

`support-web:8081` obsługuje wyłącznie HTTP, sesje i decyzje człowieka. `support-worker` pobiera trwałe zadania z PostgreSQL przez `FOR UPDATE SKIP LOCKED`. Oba używają schematu `support`; katalog `public.clients` jest współdzielony. TEI generuje embeddingi 384D, osobny TEI wykonuje `/rerank`, a Ollama jest usługą LLM. V1 nie wykonuje akcji na systemach klientów.

```text
browser -> support-web -> PostgreSQL <- support-worker
                                      -> TEI / reranker / Ollama
```

Awaria modelu zmienia zadanie i zgłoszenie na `failed_retryable`. Stan etapów jest szyfrowany w `workflow_checkpoints`; `ticket_id` jest identyfikatorem wątku.

Worker łączy fragmenty dokumentacji technicznej i zatwierdzone przypadki historyczne. Kandydaci są ograniczani przez system i klienta, rerankowani, a osiem najlepszych trafień stanowi kontekst odpowiedzi Ollamy. Raport realizacji może zostać opublikowany przez seniora jako rozwiązanie dostępne następnym zgłoszeniom.
