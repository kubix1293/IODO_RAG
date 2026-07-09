from __future__ import annotations

import html
import threading
import time
import uuid
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from iodo_rag.audit import run_a5_assessment
from iodo_rag.config import get_settings
from iodo_rag.db import (
    connect,
    create_client,
    default_client_id,
    delete_document,
    ensure_schema,
    get_client,
    list_clients,
)
from iodo_rag.ingest import ingest_path
from iodo_rag.llm import answer_question
from iodo_rag.search import search as run_search

UPLOAD_ROOT = Path("/data/uploads")
SUPPORTED_SUFFIXES = {".pdf", ".docx"}

app = FastAPI(title="IODO Import Dokumentow")


@dataclass
class JobState:
    id: str
    client_id: int
    status: str = "running"
    messages: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] | None = None
    error: str | None = None
    current_step: str = "start"
    updated_at: float = field(default_factory=time.time)
    started_at: float = field(default_factory=time.time)


JOBS: dict[str, JobState] = {}
JOBS_LOCK = threading.Lock()


@app.on_event("startup")
def startup() -> None:
    settings = get_settings()
    with connect(settings.database_url) as conn:
        ensure_schema(conn)
        conn.commit()


def safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    stem = Path(name).stem or "document"
    suffix = Path(name).suffix.lower()
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "document"
    return f"{normalized[:120]}{suffix}"


def h(value: Any) -> str:
    return html.escape(str(value), quote=True)


def selected_client_id(request: Request | None = None, explicit: int | None = None) -> int:
    settings = get_settings()
    with connect(settings.database_url) as conn:
        ensure_schema(conn)
        if explicit:
            client = get_client(conn, client_id=explicit)
            if client:
                return explicit
        if request is not None:
            raw = request.query_params.get("client_id")
            if raw and raw.isdigit():
                client_id = int(raw)
                client = get_client(conn, client_id=client_id)
                if client:
                    return client_id
        client_id = default_client_id(conn)
        conn.commit()
        return client_id


def load_dashboard(client_id: int) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    with connect(settings.database_url) as conn:
        ensure_schema(conn)
        clients = list_clients(conn)
        current_client = get_client(conn, client_id=client_id)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  d.id,
                  d.client_id,
                  d.title,
                  d.source_file,
                  d.mime_type,
                  d.created_at,
                  count(c.id) AS chunks
                FROM documents d
                LEFT JOIN document_chunks c ON c.document_id = d.id
                WHERE d.client_id = %s
                GROUP BY d.id
                ORDER BY d.created_at DESC, d.id DESC
                LIMIT 25
                """,
                (client_id,),
            )
            documents = list(cur.fetchall())

            cur.execute("SELECT count(*) AS count FROM documents WHERE client_id = %s", (client_id,))
            document_count = int(cur.fetchone()["count"])

            cur.execute(
                """
                SELECT count(*) AS count
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.client_id = %s
                """,
                (client_id,),
            )
            chunk_count = int(cur.fetchone()["count"])

    return documents, {"documents": document_count, "chunks": chunk_count}, clients, current_client


def client_options(clients: list[dict[str, Any]], current_client_id: int) -> str:
    options = []
    for client in clients:
        selected = " selected" if int(client["id"]) == current_client_id else ""
        label = f"{client['name']} ({client.get('documents') or 0} dok., {client.get('chunks') or 0} chunk.)"
        options.append(f'<option value="{h(client["id"])}"{selected}>{h(label)}</option>')
    return "\n".join(options)


def add_job_message(job: JobState, message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    with JOBS_LOCK:
        job.messages.append(f"{timestamp} - {message}")
        job.current_step = message
        job.updated_at = time.time()


def job_snapshot(job: JobState) -> dict[str, Any]:
    with JOBS_LOCK:
        payload: dict[str, Any] = {
            "id": job.id,
            "status": job.status,
            "messages": list(job.messages),
            "error": job.error,
            "current_step": job.current_step,
            "client_id": job.client_id,
        }
        if job.status == "done":
            payload["result_html"] = render_assessment(job.results or [])
        return payload


def render_answer(answer: str | None) -> str:
    if not answer:
        return ""
    return f"""
    <section class="answer">
      <h2>Odpowiedz modelu</h2>
      <p>{h(answer)}</p>
    </section>
    """


def render_assessment(results: list[dict[str, Any]] | None) -> str:
    if results is None:
        return ""

    if not results:
        return """
        <section class="assessment">
          <h2>Wynik ankiety A.5</h2>
          <div class="empty">Brak wynikow ankiety.</div>
        </section>
        """

    cards = []
    for result in results:
        item = result["item"]
        rows = result.get("rows") or []
        sources = []
        for row in rows[:3]:
            source = Path(str(row.get("source_file") or "nieznane zrodlo")).name
            pages = ""
            if row.get("page_from") or row.get("page_to"):
                pages = f", str. {h(row.get('page_from') or '-')}-{h(row.get('page_to') or '-')}"
            ref_parts = [
                row.get("section"),
                row.get("article"),
                row.get("paragraph"),
                row.get("point"),
            ]
            ref = " ".join(str(value) for value in ref_parts if value) or "brak referencji"
            role = row.get("context_role") or "trafienie"
            chunk_index = row.get("chunk_index")
            score = row.get("audit_score", row.get("hybrid_score", 0))
            sources.append(
                f"<li>{h(source)}{pages}, {h(ref)}, chunk {h(chunk_index)}, {h(role)}, score {float(score):.4f}</li>"
            )
        source_html = "\n".join(sources) or "<li>Brak zrodel z wyszukiwania.</li>"
        cards.append(
            '<article class="assessment-card">'
            f"<h3>{h(item['control'])} - {h(item['control_name'])}</h3>"
            f"<p><strong>Pytanie:</strong> {h(item['question'])}</p>"
            f"<pre>{h(result['answer'])}</pre>"
            "<details><summary>Najlepsze trafienia RAG</summary>"
            f"<ol>{source_html}</ol>"
            "</details>"
            "</article>"
        )

    return f"""
    <section class="assessment">
      <h2>Wynik ankiety A.5</h2>
      <p class="hint">Wykonano sekwencyjnie pierwsze pytanie dla kontroli A.5.1-A.5.5 na podstawie zaimportowanych dokumentow.</p>
      {"".join(cards)}
    </section>
    """


def render_result_cards(query: str | None, rows: list[dict[str, Any]] | None) -> str:
    if query is None:
        return ""

    if rows is None:
        rows = []

    if not rows:
        body = '<div class="empty result-empty">Brak wynikow dla podanego pytania.</div>'
    else:
        cards = []
        for row in rows:
            source = Path(str(row["source_file"])).name
            ref_parts = [
                row.get("section"),
                row.get("article"),
                row.get("paragraph"),
                row.get("point"),
            ]
            ref = " ".join(str(value) for value in ref_parts if value) or "brak referencji"
            pages = ""
            if row.get("page_from") or row.get("page_to"):
                pages = f"str. {h(row.get('page_from') or '-')}-{h(row.get('page_to') or '-')}"
            excerpt = str(row["chunk_text"]).strip()
            if len(excerpt) > 1400:
                excerpt = f"{excerpt[:1400].rstrip()}..."
            cards.append(
                '<article class="result-card">'
                '<div class="result-meta">'
                f"<strong>{h(row.get('document_title') or source)}</strong>"
                f"<span>{h(source)}</span>"
                f"<span>{h(ref)}</span>"
                f"<span>{pages}</span>"
                f"<span>score {float(row['hybrid_score']):.4f}</span>"
                "</div>"
                f"<p>{h(excerpt)}</p>"
                "</article>"
            )
        body = "\n".join(cards)

    return f"""
    <section class="search-results">
      <h2>Wyniki wyszukiwania</h2>
      <p class="query">Pytanie: <strong>{h(query)}</strong></p>
      {body}
    </section>
    """


def render_page(
    *,
    client_id: int | None = None,
    message: str | None = None,
    error: str | None = None,
    search_query: str | None = None,
    search_rows: list[dict[str, Any]] | None = None,
    answer: str | None = None,
    assessment_results: list[dict[str, Any]] | None = None,
) -> HTMLResponse:
    try:
        current_client_id = client_id or selected_client_id()
        documents, stats, clients, current_client = load_dashboard(current_client_id)
        db_error = None
    except Exception as exc:  # pragma: no cover - surfaced in the UI for operations
        documents = []
        clients = []
        current_client = None
        current_client_id = client_id or 0
        stats = {"documents": 0, "chunks": 0}
        db_error = str(exc)

    options_html = client_options(clients, current_client_id)
    current_client_name = current_client.get("name") if current_client else "brak klienta"

    rows = []
    for doc in documents:
        source = Path(str(doc["source_file"])).name
        document_label = doc.get("title") or source
        rows.append(
            "<tr>"
            f"<td>{h(doc['id'])}</td>"
            f"<td>{h(document_label)}</td>"
            f"<td>{h(source)}</td>"
            f"<td>{h(doc.get('mime_type') or '-')}</td>"
            f"<td>{h(doc.get('chunks') or 0)}</td>"
            f"<td>{h(doc.get('created_at') or '-')}</td>"
            "<td>"
            f'<form class="inline-form" action="/documents/{h(doc["id"])}/delete" method="post" '
            'onsubmit="return confirm(\'Usunac ten dokument z bazy?\')">'
            f'<input type="hidden" name="client_id" value="{h(current_client_id)}">'
            '<button class="danger-button" type="submit">Usun</button>'
            "</form>"
            "</td>"
            "</tr>"
        )

    table_body = "\n".join(rows) or (
        '<tr><td colspan="7" class="empty">Brak zaimportowanych dokumentow dla wybranego klienta.</td></tr>'
    )
    results = render_result_cards(search_query, search_rows)
    answer_html = render_answer(answer)
    assessment_html = render_assessment(assessment_results)

    notice = ""
    if message:
        notice = f'<div class="notice success">{h(message)}</div>'
    if error:
        notice = f'<div class="notice error">{h(error)}</div>'
    if db_error:
        notice += f'<div class="notice error">Blad polaczenia z baza: {h(db_error)}</div>'

    html_body = f"""<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>IODO - import dokumentow</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #18202a;
      --muted: #5b6470;
      --line: #dce2ea;
      --primary: #0f766e;
      --primary-dark: #115e59;
      --danger: #b42318;
      --success-bg: #e7f6ef;
      --error-bg: #fdecec;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    main {{
      width: min(1120px, calc(100% - 32px));
      margin: 32px auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-end;
      margin-bottom: 22px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 30px;
      line-height: 1.15;
    }}
    p {{ color: var(--muted); margin: 0; }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 320px;
      gap: 18px;
      align-items: start;
    }}
    section, aside {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
    }}
    h2 {{
      margin: 0 0 16px;
      font-size: 18px;
    }}
    label {{
      display: block;
      margin-bottom: 8px;
      font-weight: 650;
    }}
    input[type="file"] {{
      display: block;
      width: 100%;
      padding: 18px;
      border: 1px dashed #9aa6b2;
      border-radius: 8px;
      background: #fbfcfd;
    }}
    input[type="search"], input[type="number"], input[type="text"], select {{
      display: block;
      width: 100%;
      padding: 11px 12px;
      border: 1px solid #9aa6b2;
      border-radius: 6px;
      background: #fbfcfd;
      color: var(--text);
      font: inherit;
    }}
    .search-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 120px;
      gap: 12px;
      align-items: end;
    }}
    .client-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: end;
    }}
    .job-panel {{
      margin-top: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: #fbfcfd;
    }}
    .job-panel[hidden] {{
      display: none;
    }}
    .job-log {{
      margin: 10px 0 0;
      padding-left: 18px;
      color: var(--muted);
      line-height: 1.5;
      font-size: 14px;
    }}
    button {{
      margin-top: 16px;
      border: 0;
      border-radius: 6px;
      padding: 11px 16px;
      background: var(--primary);
      color: white;
      font-weight: 700;
      cursor: pointer;
    }}
    button:hover {{ background: var(--primary-dark); }}
    .inline-form {{
      margin: 0;
    }}
    .inline-form button {{
      margin: 0;
    }}
    .danger-button {{
      background: var(--danger);
      padding: 8px 10px;
      font-size: 13px;
    }}
    .danger-button:hover {{
      background: #8f1d14;
    }}
    .hint {{
      margin-top: 10px;
      font-size: 14px;
      color: var(--muted);
    }}
    .stats {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: #fbfcfd;
    }}
    .stat strong {{
      display: block;
      font-size: 28px;
      margin-bottom: 2px;
    }}
    .stat span {{ color: var(--muted); font-size: 14px; }}
    .notice {{
      margin-bottom: 18px;
      border-radius: 8px;
      padding: 12px 14px;
      border: 1px solid var(--line);
    }}
    .success {{ background: var(--success-bg); }}
    .error {{ background: var(--error-bg); color: var(--danger); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      padding: 11px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #eef2f6;
      font-size: 13px;
      color: #344054;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    .list {{ margin-top: 18px; }}
    .empty {{ color: var(--muted); text-align: center; padding: 28px; }}
    .import-search {{
      display: grid;
      gap: 18px;
    }}
    .search-results {{
      margin-top: 18px;
    }}
    .answer {{
      margin-top: 18px;
      border-left: 4px solid var(--primary);
    }}
    .answer p {{
      white-space: pre-wrap;
      color: var(--text);
      line-height: 1.55;
    }}
    .query {{
      margin-bottom: 14px;
    }}
    .assessment {{
      margin-top: 18px;
    }}
    .assessment-card {{
      border-top: 1px solid var(--line);
      padding: 16px 0;
    }}
    .assessment-card h3 {{
      margin: 0 0 10px;
      font-size: 16px;
    }}
    .assessment-card pre {{
      white-space: pre-wrap;
      background: #fbfcfd;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      color: var(--text);
      font-family: inherit;
      line-height: 1.5;
    }}
    .assessment-card details {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 14px;
    }}
    .result-card {{
      border-top: 1px solid var(--line);
      padding: 16px 0;
    }}
    .result-card:last-child {{ padding-bottom: 0; }}
    .result-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 12px;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 13px;
    }}
    .result-meta strong {{
      color: var(--text);
    }}
    .result-card p {{
      white-space: pre-wrap;
      color: var(--text);
      line-height: 1.5;
    }}
    .result-empty {{
      border-top: 1px solid var(--line);
    }}
    @media (max-width: 820px) {{
      header {{ display: block; }}
      .grid {{ grid-template-columns: 1fr; }}
      .search-row {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>IODO - import dokumentow</h1>
        <p>Upload PDF/DOCX, embedding w TEI i zapis chunkow w PostgreSQL/pgvector.</p>
      </div>
      <p>Klient: {h(current_client_name)}<br>Model: intfloat/multilingual-e5-small</p>
    </header>
    {notice}
    <div class="grid">
      <div class="import-search">
        <section>
          <h2>Klient</h2>
          <form action="/" method="get">
            <label for="client_id">Aktywny klient</label>
            <div class="client-row">
              <select id="client_id" name="client_id" onchange="this.form.submit()">
                {options_html}
              </select>
              <button type="submit">Wybierz</button>
            </div>
            <div class="hint">Import, wyszukiwanie, pytania i ankieta dzialaja tylko dla wybranego klienta.</div>
          </form>
          <form action="/clients" method="post">
            <label for="client_name">Nowy klient</label>
            <input id="client_name" name="name" type="text" placeholder="np. Firma ABC" required>
            <button type="submit">Dodaj klienta</button>
          </form>
        </section>
        <section>
          <h2>Import pliku</h2>
          <form action="/upload" method="post" enctype="multipart/form-data">
            <input type="hidden" name="client_id" value="{h(current_client_id)}">
            <label for="files">Dokumenty cyfrowe</label>
            <input id="files" name="files" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" multiple required>
            <button type="submit">Importuj i utworz embeddingi</button>
            <div class="hint">Obslugiwane sa PDF z warstwa tekstowa oraz DOCX. Skanowane PDF wymagaja OCR przed importem.</div>
          </form>
        </section>
        <section>
          <h2>Zapytaj dokumenty</h2>
          <form action="/search" method="get">
            <input type="hidden" name="client_id" value="{h(current_client_id)}">
            <div class="search-row">
              <div>
                <label for="q">Pytanie lub fraza</label>
                <input id="q" name="q" type="search" value="{h(search_query or '')}" placeholder="np. jakie sa obowiazki administratora danych?" required>
              </div>
              <div>
                <label for="limit">Wyniki</label>
                <input id="limit" name="limit" type="number" min="1" max="20" value="5">
              </div>
            </div>
            <button type="submit">Szukaj w dokumentach</button>
            <button type="submit" formaction="/ask">Zapytaj model</button>
            <div class="hint">Wyszukiwanie zwraca trafienia z pgvector. Model odpowiada tylko na podstawie znalezionych fragmentow.</div>
          </form>
        </section>
        <section>
          <h2>Ankieta A.5</h2>
          <form id="assessment-form" action="/assessment/a5/start" method="post">
            <input type="hidden" name="client_id" value="{h(current_client_id)}">
            <button type="submit">Wykonaj ankiete A.5</button>
            <div class="hint">Na razie wykonuje 5 pierwszych pytan: A.5.1.1-A.5.5.1, jedno po drugim. Operacja moze potrwac kilka minut na CPU.</div>
          </form>
          <div id="job-panel" class="job-panel" hidden>
            <strong id="job-status">Przygotowuje zadanie...</strong>
            <ol id="job-log" class="job-log"></ol>
          </div>
        </section>
      </div>
      <aside>
        <h2>Stan bazy</h2>
        <div class="stats">
          <div class="stat"><strong>{h(stats["documents"])}</strong><span>dokumenty</span></div>
          <div class="stat"><strong>{h(stats["chunks"])}</strong><span>chunki</span></div>
        </div>
      </aside>
    </div>
    {assessment_html}
    {answer_html}
    {results}
    <section class="list">
      <h2>Ostatnie dokumenty</h2>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Tytul</th>
            <th>Plik</th>
            <th>MIME</th>
            <th>Chunki</th>
            <th>Utworzono</th>
            <th>Akcje</th>
          </tr>
        </thead>
        <tbody>{table_body}</tbody>
      </table>
    </section>
  </main>
  <script>
    const assessmentForm = document.getElementById('assessment-form');
    const jobPanel = document.getElementById('job-panel');
    const jobStatus = document.getElementById('job-status');
    const jobLog = document.getElementById('job-log');

    function renderJob(data) {{
      jobPanel.hidden = false;
      jobStatus.textContent = data.current_step || data.status;
      jobLog.innerHTML = '';
      for (const message of data.messages || []) {{
        const item = document.createElement('li');
        item.textContent = message;
        jobLog.appendChild(item);
      }}
      if (data.status === 'done') {{
        const wrapper = document.createElement('div');
        wrapper.innerHTML = data.result_html || '';
        const oldResult = document.querySelector('.assessment');
        if (oldResult) {{
          oldResult.remove();
        }}
        document.querySelector('.grid').insertAdjacentElement('afterend', wrapper);
        jobStatus.textContent = 'Ankieta A.5 zakonczona.';
      }}
      if (data.status === 'error') {{
        jobStatus.textContent = data.error || 'Blad wykonania zadania.';
      }}
    }}

    async function pollJob(jobId) {{
      const response = await fetch(`/jobs/${{jobId}}`);
      const data = await response.json();
      renderJob(data);
      if (data.status === 'running') {{
        window.setTimeout(() => pollJob(jobId), 5000);
      }}
    }}

    if (assessmentForm) {{
      assessmentForm.addEventListener('submit', async (event) => {{
        event.preventDefault();
        jobPanel.hidden = false;
        jobStatus.textContent = 'Startuje ankiete A.5...';
        jobLog.innerHTML = '';
        const button = assessmentForm.querySelector('button[type="submit"]');
        if (button) {{
          button.disabled = true;
        }}
        try {{
          const response = await fetch(assessmentForm.action, {{
            method: 'POST',
            body: new FormData(assessmentForm)
          }});
          const data = await response.json();
          renderJob(data);
          pollJob(data.id);
        }} catch (error) {{
          jobStatus.textContent = `Blad startu zadania: ${{error}}`;
        }} finally {{
          if (button) {{
            button.disabled = false;
          }}
        }}
      }});
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(html_body)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return render_page(
        client_id=selected_client_id(request),
        message=request.query_params.get("message"),
        error=request.query_params.get("error"),
    )


@app.get("/search", response_class=HTMLResponse)
def search_documents(request: Request, q: str = "", limit: int = 5, client_id: int | None = None) -> HTMLResponse:
    query = q.strip()
    current_client_id = selected_client_id(request, client_id)
    if not query:
        return render_page(client_id=current_client_id, error="Podaj pytanie lub fraze do wyszukania.")

    safe_limit = max(1, min(limit, 20))
    try:
        rows = run_search(query, get_settings(), limit=safe_limit, client_id=current_client_id)
    except Exception as exc:  # pragma: no cover - surfaced in the UI for operations
        return render_page(
            client_id=current_client_id,
            error=f"Blad wyszukiwania: {exc}",
            search_query=query,
            search_rows=[],
        )

    return render_page(
        client_id=current_client_id,
        message=f"Znaleziono {len(rows)} wynikow.",
        search_query=query,
        search_rows=rows,
    )


@app.get("/ask", response_class=HTMLResponse)
def ask_documents(request: Request, q: str = "", limit: int = 5, client_id: int | None = None) -> HTMLResponse:
    query = q.strip()
    current_client_id = selected_client_id(request, client_id)
    if not query:
        return render_page(client_id=current_client_id, error="Podaj pytanie dla modelu.")

    safe_limit = max(1, min(limit, 10))
    settings = get_settings()
    rows: list[dict[str, Any]] = []
    try:
        rows = run_search(query, settings, limit=safe_limit, client_id=current_client_id)
        answer = answer_question(query, rows, settings)
    except Exception as exc:  # pragma: no cover - surfaced in the UI for operations
        return render_page(
            client_id=current_client_id,
            error=f"Blad odpowiedzi modelu: {exc}",
            search_query=query,
            search_rows=rows,
        )

    return render_page(
        client_id=current_client_id,
        message=f"Odpowiedz wygenerowana na podstawie {len(rows)} fragmentow.",
        search_query=query,
        search_rows=rows,
        answer=answer,
    )


@app.post("/assessment/a5", response_class=HTMLResponse)
def assessment_a5(request: Request, client_id: int | None = Form(default=None)) -> HTMLResponse:
    current_client_id = selected_client_id(request, client_id)
    settings = get_settings()
    try:
        results = run_a5_assessment(settings, client_id=current_client_id)
    except Exception as exc:  # pragma: no cover - surfaced in the UI for operations
        return render_page(client_id=current_client_id, error=f"Blad wykonania ankiety A.5: {exc}")

    return render_page(
        client_id=current_client_id,
        message=f"Ankieta A.5 wykonana dla {len(results)} pytan.",
        assessment_results=results,
    )


def run_assessment_job(job: JobState) -> None:
    heartbeat_stop = threading.Event()

    def heartbeat() -> None:
        while not heartbeat_stop.wait(120):
            add_job_message(job, f"Prace trwaja; jestem na etapie: {job.current_step}")

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        settings = get_settings()
        results = run_a5_assessment(
            settings,
            client_id=job.client_id,
            progress=lambda message: add_job_message(job, message),
        )
        with JOBS_LOCK:
            job.results = results
            job.status = "done"
            job.current_step = "Ankieta A.5 zakonczona."
            job.updated_at = time.time()
    except Exception as exc:  # pragma: no cover - surfaced in the UI
        with JOBS_LOCK:
            job.status = "error"
            job.error = str(exc)
            job.current_step = f"Blad wykonania ankiety A.5: {exc}"
            job.updated_at = time.time()
    finally:
        heartbeat_stop.set()


@app.post("/assessment/a5/start")
def assessment_a5_start(request: Request, client_id: int = Form(...)) -> JSONResponse:
    current_client_id = selected_client_id(request, client_id)
    job = JobState(id=uuid.uuid4().hex, client_id=current_client_id)
    add_job_message(job, "Zadanie przyjete. Rozpoczynam prace nad dokumentacja.")
    with JOBS_LOCK:
        JOBS[job.id] = job
    thread = threading.Thread(target=run_assessment_job, args=(job,), daemon=True)
    thread.start()
    return JSONResponse(job_snapshot(job))


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> JSONResponse:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return JSONResponse({"status": "error", "error": "Nie znaleziono zadania."}, status_code=404)
    return JSONResponse(job_snapshot(job))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/clients")
def create_client_route(name: str = Form(...)) -> RedirectResponse:
    clean_name = " ".join(name.strip().split())
    if not clean_name:
        return RedirectResponse(
            f"/?error={quote('Podaj nazwe klienta.')}",
            status_code=303,
        )
    settings = get_settings()
    try:
        with connect(settings.database_url) as conn:
            ensure_schema(conn)
            client_id = create_client(conn, name=clean_name)
            conn.commit()
    except Exception as exc:  # pragma: no cover - surfaced in the UI for operations
        return RedirectResponse(
            f"/?error={quote(f'Blad dodawania klienta: {exc}')}",
            status_code=303,
        )

    return RedirectResponse(
        f"/?client_id={client_id}&message={quote(f'Dodano klienta: {clean_name}')}",
        status_code=303,
    )


@app.post("/documents/{document_id}/delete")
def delete_document_route(document_id: int, client_id: int | None = Form(default=None)) -> RedirectResponse:
    settings = get_settings()
    suffix = f"?client_id={client_id}" if client_id else ""
    try:
        with connect(settings.database_url) as conn:
            deleted = delete_document(conn, document_id=document_id)
            conn.commit()
    except Exception as exc:  # pragma: no cover - surfaced in the UI for operations
        return RedirectResponse(
            f"/{suffix}&error={quote(f'Blad usuwania dokumentu {document_id}: {exc}')}" if suffix else f"/?error={quote(f'Blad usuwania dokumentu {document_id}: {exc}')}",
            status_code=303,
        )

    if not deleted:
        return RedirectResponse(
            f"/{suffix}&error={quote(f'Dokument {document_id} nie istnieje.')}" if suffix else f"/?error={quote(f'Dokument {document_id} nie istnieje.')}",
            status_code=303,
        )

    label = deleted.get("title") or Path(str(deleted.get("source_file") or document_id)).name
    target_client_id = client_id or deleted.get("client_id")
    return RedirectResponse(
        f"/?client_id={target_client_id}&message={quote(f'Usunieto dokument z bazy: {label}')}",
        status_code=303,
    )


@app.post("/upload")
def upload(client_id: int = Form(...), files: list[UploadFile] = File(...)) -> RedirectResponse:
    if not files:
        raise HTTPException(status_code=400, detail="Nie wybrano plikow")

    unsupported = [
        file.filename or "bez_nazwy"
        for file in files
        if Path(file.filename or "").suffix.lower() not in SUPPORTED_SUFFIXES
    ]
    if unsupported:
        return RedirectResponse(
            f"/?client_id={client_id}&error={quote('Dozwolone sa tylko pliki .pdf i .docx: ' + ', '.join(unsupported))}",
            status_code=303,
        )

    settings = get_settings()
    current_client_id = client_id
    with connect(settings.database_url) as conn:
        ensure_schema(conn)
        if not get_client(conn, client_id=current_client_id):
            return RedirectResponse(
                f"/?error={quote('Wybrany klient nie istnieje.')}",
                status_code=303,
            )
        conn.commit()
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    imported = []

    for file in files:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = UPLOAD_ROOT / f"{timestamp}_{safe_filename(file.filename or 'document')}"

        with target.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)

        try:
            document_id, chunk_count = ingest_path(target, settings, client_id=current_client_id)
        except Exception as exc:
            target.unlink(missing_ok=True)
            error = f"Blad importu {file.filename}: {exc}"
            return RedirectResponse(f"/?client_id={current_client_id}&error={quote(error)}", status_code=303)

        imported.append((document_id, chunk_count))

    total_chunks = sum(chunk_count for _, chunk_count in imported)
    message = f"Zaimportowano {len(imported)} plikow; utworzono {total_chunks} chunkow."
    return RedirectResponse(f"/?client_id={current_client_id}&message={quote(message)}", status_code=303)
