# Runbook instalacji IODO na nowym serwerze

Ostatnia aktualizacja: 2026-07-09

Cel pliku: kompletna instrukcja dla agenta Claude/Codex, ktory dostaje katalog projektu IODO i ma odtworzyc dzialajace srodowisko na nowym serwerze.

## Zakres

Runbook dotyczy projektu:

```bash
/opt/IODO
```

Zrodlem prawdy dla uruchomienia jest:

```bash
/opt/IODO/docker-compose.yml
/opt/IODO/.env.example
/opt/IODO/db/init.sql
/opt/IODO/app/Dockerfile
/opt/IODO/app/requirements.txt
```

Nie zmieniaj kodu aplikacji podczas instalacji. Dostosowania na nowym serwerze powinny dotyczyc glownie `.env`, mapowania portow w `docker-compose.yml` i reguly firewalla.

## Wymagania hosta

- Linux z Docker Engine i Docker Compose plugin.
- Dostep do internetu przy pierwszym starcie, zeby pobrac obrazy Docker, model TEI i model Ollama.
- Wolne porty hosta albo dostosowane mapowania w Compose:
  - `80` dla web UI,
  - `8000` dla web UI alternatywnie,
  - `5432` dla PostgreSQL,
  - `8080` dla TEI,
  - `11434` dla Ollamy.
- CPU wystarczy do uruchomienia, ale LLM na CPU jest wolny. GPU nie jest obecnie skonfigurowane.
- OCR nie jest czescia systemu. Import obsluguje PDF z warstwa tekstowa oraz DOCX.

## Uslugi Docker Compose

| Usluga | Obraz/build | Port hosta | Dane | Uwagi |
| --- | --- | --- | --- | --- |
| `postgres` | `pgvector/pgvector:pg16` | `5432:5432` | `postgres_data:/var/lib/postgresql/data` | Env: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`; init z `./db/init.sql`; healthcheck `pg_isready`. |
| `tei` | `ghcr.io/huggingface/text-embeddings-inference:cpu-latest` | `8080:80` | `hf_cache:/data` | Command: `--model-id intfloat/multilingual-e5-small`; `HF_HOME=/data`; pierwszy start moze dlugo pobierac model. |
| `ollama` | `ollama/ollama:latest` | `11434:11434` | `ollama_data:/root/.ollama` | Wymagany model `llama3.2:3b`; po swiezej instalacji wykonac `ollama pull`. |
| `app` | build `./app` | brak | `./data:/data` | Profil `tools`; CLI ingest/search; entrypoint `python -m iodo_rag.cli`. |
| `web` | build `./app` | `80:8000`, `8000:8000` | `./data:/data` | FastAPI/Uvicorn: `iodo_rag.web:app --host 0.0.0.0 --port 8000`. |

Oczekiwane nazwy kontenerow przy projekcie `iodo`:

```text
iodo-postgres-1
iodo-tei-1
iodo-ollama-1
iodo-web-1
```

## Modele i parametry

Embedding:

```text
EMBEDDING_URL=http://tei:80
EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DIM=384
EMBEDDING_BATCH_SIZE=8
```

LLM:

```text
LLM_URL=http://ollama:11434
LLM_MODEL=llama3.2:3b
LLM_TIMEOUT_SECONDS=1800
LLM_CONTEXT_MAX_CHARS=8500
LLM_NUM_CTX=8192
LLM_NUM_PREDICT=384
```

`tei` pobiera model embeddingowy do wolumenu `hf_cache`. `ollama` trzyma modele w `ollama_data`. Jesli kopiowany jest tylko katalog projektu, a nie wolumeny Docker, oba modele trzeba bedzie pobrac ponownie.

## Obraz Python aplikacji

`app/Dockerfile` buduje obraz dla `app` i `web`:

- baza: `python:3.12-slim`,
- katalog roboczy: `/app`,
- zaleznosc systemowa: `libmagic1`,
- instalacja Python: `pip install --no-cache-dir -r requirements.txt`,
- kod kopiowany z `app/iodo_rag` do `/app/iodo_rag`,
- domyslny entrypoint: `python -m iodo_rag.cli`,
- kontener `web` nadpisuje entrypoint na `uvicorn`.

`app/requirements.txt`:

```text
psycopg[binary]==3.2.3
python-docx==1.1.2
pypdf==5.1.0
python-magic==0.4.27
requests==2.32.3
rich==13.9.4
typer==0.15.1
click==8.1.8
fastapi==0.115.6
python-multipart==0.0.20
uvicorn[standard]==0.34.0
```

## Konfiguracja `.env`

Wzorzec `.env.example`:

```text
POSTGRES_DB=iodo
POSTGRES_USER=iodo
POSTGRES_PASSWORD=iodo
DATABASE_URL=postgresql://iodo:iodo@postgres:5432/iodo
EMBEDDING_URL=http://tei:80
EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DIM=384
EMBEDDING_BATCH_SIZE=8
CHUNK_TARGET_CHARS=3500
CHUNK_OVERLAP_CHARS=500
LLM_URL=http://ollama:11434
LLM_MODEL=llama3.2:3b
LLM_TIMEOUT_SECONDS=1800
LLM_CONTEXT_MAX_CHARS=8500
LLM_NUM_CTX=8192
LLM_NUM_PREDICT=384
```

Wazne: aktywny host w dniu 2026-07-09 ma inne wartosci chunkingu niz `.env.example`:

```text
CHUNK_TARGET_CHARS=1100
CHUNK_OVERLAP_CHARS=150
```

Interpretacja:

- `.env.example` jest wzorcem do startu nowej instalacji.
- `.env` jest konfiguracja aktywna konkretnego hosta i nie musi byc identyczny ze wzorcem.
- Dla obecnej pracy z wiekszymi kontekstami aktywny host uzywa `1100/150`.
- Na nowym serwerze agent powinien swiadomie ustalic docelowe wartosci chunkingu przed importem dokumentow, bo zmiana tych wartosci po imporcie nie przebuduje automatycznie juz zapisanych chunkow.
- Zmien hasla w `.env` przed uruchomieniem srodowiska poza hostem testowym. Nie wpisuj realnych hasel do dokumentacji.

## Schemat bazy

`db/init.sql` inicjuje PostgreSQL tylko przy tworzeniu pustego wolumenu `postgres_data`.

Tworzone elementy:

- rozszerzenie `vector`,
- tabela `clients(id, name unique, created_at)`,
- klient domyslny `Klient domyslny`,
- tabela `documents(id, client_id, source_file unique, title, sha256, mime_type, created_at, metadata)`,
- tabela `document_chunks(...)` z `embedding vector(384)` i generowanym `search_tsv`,
- indeks HNSW `document_chunks_embedding_hnsw` na `embedding vector_cosine_ops`,
- indeks GIN `document_chunks_search_idx` na `search_tsv`,
- indeks `document_chunks_document_idx`,
- indeks `documents_client_idx`.

## Dane i wolumeny

Katalog projektu:

```text
/opt/IODO
```

Dane plikowe aplikacji:

```text
/opt/IODO/data
/opt/IODO/data/uploads
```

Wolumeny Docker:

```text
postgres_data
hf_cache
ollama_data
```

Jesli przenosisz tylko katalog `/opt/IODO`, nie przenosisz automatycznie bazy ani modeli zapisanych w wolumenach Docker. W takim wariancie:

- PostgreSQL wystartuje z pustym wolumenem i wykona `db/init.sql`,
- TEI pobierze model embeddingowy ponownie,
- Ollama nie bedzie miala `llama3.2:3b`, dopoki nie wykonasz `ollama pull`,
- dokumenty trzeba zaimportowac ponownie albo odtworzyc z dumpa PostgreSQL.

## Instalacja Dockera

Na Debian/Ubuntu minimalna sciezka:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
```

Alternatywnie mozna uzyc oficjalnej instalacji Docker Engine z repozytorium Dockera, jesli host wymaga nowszej wersji.

Sprawdzenie:

```bash
docker --version
docker compose version
```

## Instalacja projektu od zera

1. Przygotuj katalog:

```bash
sudo mkdir -p /opt/IODO
```

2. Skopiuj katalog projektu do `/opt/IODO`.

3. Przejdz do projektu:

```bash
cd /opt/IODO
```

4. Utworz konfiguracje:

```bash
cp .env.example .env
```

5. Edytuj `.env`:

```bash
nano .env
```

Minimalnie sprawdz:

- `POSTGRES_PASSWORD`,
- `DATABASE_URL` musi zawierac te same dane co `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
- `CHUNK_TARGET_CHARS` i `CHUNK_OVERLAP_CHARS`,
- parametry `LLM_*`.

6. Zbuduj obrazy aplikacji:

```bash
sudo docker compose --profile tools build app web
```

7. Uruchom uslugi:

```bash
sudo docker compose up -d postgres tei ollama web
```

8. Obserwuj status:

```bash
sudo docker compose ps
sudo docker logs --tail 100 iodo-tei-1
sudo docker logs --tail 100 iodo-ollama-1
sudo docker logs --tail 100 iodo-web-1
```

Pierwszy start `tei` moze dlugo byc `unhealthy`, bo pobiera model `intfloat/multilingual-e5-small`.

9. Pobierz model Ollama, jesli nie ma go w wolumenie:

```bash
sudo docker exec iodo-ollama-1 ollama pull llama3.2:3b
sudo docker exec iodo-ollama-1 ollama list
```

10. Sprawdz healthchecki:

```bash
curl http://localhost/health
curl http://localhost:8000/health
curl http://localhost:8080/health
sudo docker exec iodo-postgres-1 psql -U iodo -d iodo -c "select count(*) from clients;"
sudo docker compose ps
```

Oczekiwane:

- web zwraca `{"status":"ok"}`,
- TEI health zwraca OK,
- tabela `clients` istnieje,
- `docker compose ps` pokazuje `postgres`, `tei`, `ollama` jako healthy/running oraz `web` jako running.

11. Otworz web UI:

```text
http://SERVER_IP/
http://SERVER_IP:8000/
```

Firewall hosta musi przepuszczac przynajmniej port `80` albo `8000` z LAN.

## Import i test funkcjonalny

CLI jest dostepne przez profil `tools`:

```bash
sudo docker compose --profile tools run --rm app --help
```

Import katalogu:

```bash
sudo docker compose --profile tools run --rm app ingest /data/inbox
```

Web UI zapisuje uploady w:

```text
/opt/IODO/data/uploads
```

Po instalacji wykonaj test uploadu malego PDF z warstwa tekstowa albo DOCX. Jesli przeniesiono baze i dane, wykonaj test wyszukiwania w web UI.

## Backup starego serwera

Dump PostgreSQL:

```bash
cd /opt/IODO
sudo docker exec iodo-postgres-1 pg_dump -U iodo -d iodo > iodo-postgres.dump.sql
```

Backup uploadow:

```bash
cd /opt/IODO
tar -czf iodo-uploads.tgz data/uploads
```

Opcjonalnie mozna backupowac wolumeny Docker `postgres_data`, `ollama_data`, `hf_cache`, ale przy prostszej migracji zwykle wystarczy:

- dump PostgreSQL,
- katalog `data/uploads`,
- ponowne pobranie modeli TEI/Ollama na nowym serwerze.

## Restore na nowym serwerze

1. Uruchom pusty stack, aby powstaly kontenery i schemat.

```bash
cd /opt/IODO
sudo docker compose up -d postgres tei ollama web
```

2. Odtworz baze z dumpa. Jesli baza jest pusta, wystarczy:

```bash
sudo docker exec -i iodo-postgres-1 psql -U iodo -d iodo < iodo-postgres.dump.sql
```

Jesli baza zawiera dane testowe, najpierw zdecyduj, czy je usunac. Nie wykonuj destrukcyjnego czyszczenia bez swiadomej decyzji.

3. Odtworz uploady:

```bash
cd /opt/IODO
tar -xzf iodo-uploads.tgz
```

4. Pobierz model Ollama, jesli nie zostal przeniesiony z wolumenem:

```bash
sudo docker exec iodo-ollama-1 ollama pull llama3.2:3b
```

5. Wykonaj testy zdrowia z sekcji instalacyjnej.

## Typowe problemy

### TEI dlugo `unhealthy`

Przy pierwszym starcie TEI pobiera model do `hf_cache`. Sprawdz logi:

```bash
sudo docker logs --tail 200 iodo-tei-1
```

Jesli host nie ma internetu, pobranie modelu sie nie uda.

### Ollama nie ma modelu

Objawy: `/ask` albo ankieta nie dziala, a `ollama list` nie zawiera `llama3.2:3b`.

Naprawa:

```bash
sudo docker exec iodo-ollama-1 ollama pull llama3.2:3b
sudo docker exec iodo-ollama-1 ollama list
```

### Port 80 jest zajety

Sprawdz:

```bash
sudo ss -ltnp
```

Rozwiazania:

- zatrzymac inna usluge na porcie `80`,
- zmienic mapowanie `web` w `docker-compose.yml`, np. zostawic tylko `8000:8000`,
- wystawic aplikacje przez reverse proxy.

### PDF jest skanem bez OCR

System nie ma OCR. Taki PDF moze zaimportowac sie bez uzytecznego tekstu. Trzeba dostarczyc PDF z warstwa tekstowa, DOCX albo dodac osobny etap OCR.

### LLM timeout albo bardzo wolne odpowiedzi na CPU

CPU jest wspierany, ale wolny. Parametry do regulacji bez zmiany kodu:

```text
LLM_TIMEOUT_SECONDS
LLM_CONTEXT_MAX_CHARS
LLM_NUM_CTX
LLM_NUM_PREDICT
```

Zmniejszenie kontekstu i liczby generowanych tokenow zwykle skraca czas odpowiedzi, ale moze pogorszyc jakosc.

### Brak dostepu z LAN

Sprawdz:

```bash
curl http://localhost/health
curl http://localhost:8000/health
ip -4 -br addr
sudo ss -ltnp
```

Jesli lokalnie dziala, a z LAN nie, sprawdz firewall/ufw/iptables i otworz port `80` albo `8000`.

## Checklist koncowy dla agenta

- `sudo docker compose ps` pokazuje uslugi `postgres`, `tei`, `ollama`, `web` jako healthy/running.
- `curl http://localhost/health` zwraca `{"status":"ok"}`.
- `curl http://localhost:8000/health` zwraca `{"status":"ok"}`.
- `curl http://localhost:8080/health` potwierdza TEI.
- `sudo docker exec iodo-ollama-1 ollama list` zawiera `llama3.2:3b`.
- `sudo docker exec iodo-postgres-1 psql -U iodo -d iodo -c "select count(*) from clients;"` dziala.
- Tabela `clients` zawiera `Klient domyslny`.
- Web UI dziala z LAN pod `http://SERVER_IP/` albo `http://SERVER_IP:8000/`.
- Upload malego PDF z warstwa tekstowa albo DOCX dziala.
- Jesli przeniesiono dane, test wyszukiwania zwraca oczekiwane fragmenty.
