# Orkiestracja i agenci

Aktywny workflow jest deterministycznym `StateGraph` o nazwie `support_db_orchestrator`. Model nie wybiera dowolnych narzędzi i nie wykonuje operacji w systemach klientów.

## Grupa agentów DB

Po interpretacji orkiestrator równolegle uruchamia dwa wyspecjalizowane węzły:

1. `history_agent` — przeszukuje zatwierdzone przypadki historyczne wyłącznie dla `program_id` zgłoszenia. Nie miesza ZZL z ASW.
2. `documentation_agent` — wykonuje hybrydowe wyszukiwanie full-text i pgvector w dokumentacji tego samego programu. Dopuszcza wiedzę globalną oraz prywatną wyłącznie dla `client_id` zgłoszenia.

Agenci są kontrolowanymi komponentami retrieval, a nie autonomicznymi agentami LLM. Nie posiadają terminala, dostępu do sieci klienta ani narzędzi zapisujących dane.

## Graf

```text
START
  -> interpretation
     -> [braki] END / needs_information
     -> dispatch_db_agents
          |-> history_agent ---------|
          |-> documentation_agent ---|-> reranking
                                         -> answer_generation
                                         -> END / awaiting_problem_decision
```

Wyniki obu agentów są przechowywane w osobnych polach stanu, następnie scalane i rerankowane. Zapobiega to konfliktom przy równoległym zapisie oraz kumulowaniu kandydatów po ponownej analizie.

## Trwałość

Graf używa synchronicznego `PostgresSaver` zgodnego z workerem. `thread_id` jest równy `ticket_id`. Checkpointy LangGraph są szyfrowane AES kluczem wyprowadzonym przez SHA-256 z `SUPPORT_CHECKPOINT_KEY`. Dotychczasowy zaszyfrowany rekord `support.workflow_checkpoints` pozostaje kompatybilnym podglądem stanu dla aplikacji.

Kolejka `support.support_jobs` nadal odpowiada za przejęcie zadania przez worker, retry i status `failed_retryable`. Awaria TEI, rerankera lub Ollamy nie usuwa checkpointów.

## Hybrydowy generator LLM

Węzeł `answer_generation` najpierw wywołuje skonfigurowane API zgodne z OpenAI Chat Completions. Timeout, błąd HTTP, brak konfiguracji albo pusta odpowiedź automatycznie kierują prompt do lokalnej Ollamy. Administrator może wyłączyć API w `/settings`; wtedy Ollama jest używana bez próby zewnętrznej.

Do grafu trafia już zanonimizowany opis. Prompt zawiera pseudonim klienta `K-…` wyprowadzony przez HMAC z wewnętrznego ID, ale nie nazwę klienta. Stan zapisuje `llm_provider`, błąd fallbacku oraz kategorie wykonanych redakcji.
