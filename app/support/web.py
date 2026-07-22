from __future__ import annotations
import hashlib, html, json, os, shutil, uuid
from pathlib import Path
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from iodo_rag.chunking import split_into_chunks
from iodo_rag.embeddings import EmbeddingClient
from iodo_rag.parsers import parse_document
from iodo_rag.vector import to_pgvector
from .config import settings
from .db import audit, connect, create_session, session_user
from .security import anonymize, hash_password, ip_hash, require_role, token, verify_password
from .workflow import validate_feedback

app=FastAPI(title="IODO Support",version="1.0.0")

class Login(BaseModel): username:str; password:str
class TicketCreate(BaseModel): client_id:int; program_id:int; installation_id:int|None=None; description:str=Field(min_length=10)
class Resume(BaseModel): answers:dict={}
class ProblemLink(BaseModel): problem_id:int; decision:str=Field(pattern="^(confirmed|rejected)$")
class ResolutionMode(BaseModel): attempt_id:uuid.UUID; mode:str=Field(pattern="^(full|interactive)$")
class StepResult(BaseModel): attempt_id:uuid.UUID; result:str; successful:bool|None=None
class FeedbackIn(BaseModel): attempt_id:uuid.UUID; outcome:str; comment:str|None=None
class CloseIn(BaseModel): final_attempt_id:uuid.UUID|None=None
class HistoricalCaseIn(BaseModel):
    program_id:int
    title:str=Field(min_length=3,max_length=240)
    ticket_description:str=Field(min_length=10)
    resolution:str=Field(min_length=10)
    error_code:str|None=None
    version:str|None=None
    environment:str|None=None
class ResolutionReportIn(BaseModel):
    outcome:str=Field(pattern="^(helped|partially_helped|not_helped)$")
    suggestion_rating:int=Field(ge=1,le=5)
    actual_resolution:str=Field(min_length=10)
    comment:str|None=None
class PublishResolutionIn(BaseModel):
    title:str=Field(min_length=3,max_length=240)

def user(request:Request):
    found=session_user(request.cookies.get("support_session"))
    if not found: raise HTTPException(401,"Wymagane logowanie")
    return dict(found)

def csrf(request:Request, current=Depends(user), x_csrf_token:str|None=Header(None)):
    if not x_csrf_token or x_csrf_token != current["csrf_token"]: raise HTTPException(403,"Nieprawidłowy CSRF token")
    return current

@app.on_event("startup")
def bootstrap():
    username=os.getenv("SUPPORT_BOOTSTRAP_USER"); password=os.getenv("SUPPORT_BOOTSTRAP_PASSWORD")
    if not username or not password: return
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM support.users LIMIT 1")
        if not cur.fetchone():
            cur.execute("INSERT INTO support.users(username,password_hash,role) VALUES(%s,%s,'admin')",(username,hash_password(password)))

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/",response_class=HTMLResponse)
def index(request:Request):
    current=session_user(request.cookies.get("support_session"))
    if not current: return "<h1>IODO Support</h1><p><a href='/login'>Zaloguj się do panelu</a></p>"
    senior_links = "<p><a href='/cases'>Baza przypadków serwisowych</a></p><p><a href='/knowledge'>Import dokumentacji technicznej</a></p>" if current["role"] in {"senior_technician","admin"} else ""
    csrf_value=html.escape(current["csrf_token"],quote=True)
    return f"<h1>IODO Support</h1><p>Zalogowany: {html.escape(current['username'])} ({current['role']})</p><p><a href='/tickets'>Zgłoszenia serwisowe</a></p><p><a href='/tickets/new'>Nowe zgłoszenie serwisowe</a></p>{senior_links}<p>API: <a href='/docs'>/docs</a></p><button id='logout'>Wyloguj</button><script>document.getElementById('logout').onclick=async()=>{{await fetch('/api/v1/auth/logout',{{method:'POST',headers:{{'X-CSRF-Token':'{csrf_value}'}}}});location='/login';}}</script>"

@app.get("/login",response_class=HTMLResponse)
def login_page(request:Request):
    if session_user(request.cookies.get("support_session")): return "<p>Jesteś już zalogowany. <a href='/'>Przejdź do panelu</a>.</p>"
    return """<!doctype html><html lang='pl'><meta charset='utf-8'><title>Logowanie — IODO Support</title>
    <style>body{font:16px system-ui;max-width:420px;margin:4rem auto;padding:0 1rem}label{display:block;margin-top:1rem}input{width:100%;padding:.7rem;box-sizing:border-box}button{margin-top:1rem;padding:.7rem 1.2rem}#message{margin-top:1rem;color:#a00}</style>
    <h1>IODO Support</h1><form id='login-form'><label>Użytkownik<input name='username' autocomplete='username' required></label><label>Hasło<input type='password' name='password' autocomplete='current-password' required></label><button type='submit'>Zaloguj</button></form><div id='message'></div>
    <script>document.getElementById('login-form').addEventListener('submit',async(e)=>{e.preventDefault();const f=new FormData(e.target);const r=await fetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(f.entries()))});if(r.ok)location='/';else document.getElementById('message').textContent='Nieprawidłowy użytkownik lub hasło.';});</script></html>"""

@app.get("/tickets",response_class=HTMLResponse)
def tickets_page(current=Depends(user)):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT t.id,t.status,t.description,t.created_at,c.name client_name,p.name program_name
          FROM support.tickets t JOIN public.clients c ON c.id=t.client_id JOIN support.programs p ON p.id=t.program_id
          WHERE c.name NOT LIKE 'Smoke %' ORDER BY t.created_at DESC LIMIT 100""")
        tickets=cur.fetchall()
    rows="".join(f"<tr><td><a href='/tickets/{row['id']}/view'>{str(row['id'])[:8]}</a></td><td>{html.escape(row['client_name'])}</td><td>{html.escape(row['program_name'])}</td><td>{html.escape(str(row['status']))}</td><td>{html.escape(row['description'][:120])}</td><td>{row['created_at'].strftime('%Y-%m-%d %H:%M')}</td></tr>" for row in tickets)
    return f"""<!doctype html><html lang='pl'><meta charset='utf-8'><title>Zgłoszenia</title><style>body{{font:16px system-ui;max-width:1200px;margin:2rem auto;padding:0 1rem}}table{{border-collapse:collapse;width:100%}}th,td{{padding:.6rem;border-bottom:1px solid #ddd;text-align:left}}</style><h1>Zgłoszenia serwisowe</h1><p><a href='/tickets/new'>+ Nowe zgłoszenie</a> · <a href='/'>Panel</a></p><table><thead><tr><th>ID</th><th>Klient</th><th>System</th><th>Status</th><th>Opis</th><th>Utworzono</th></tr></thead><tbody>{rows}</tbody></table></html>"""

@app.get("/tickets/{ticket_id}/view",response_class=HTMLResponse)
def ticket_workbench(ticket_id:uuid.UUID,current=Depends(user)):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT t.*,c.name client_name,p.name program_name FROM support.tickets t
          JOIN public.clients c ON c.id=t.client_id JOIN support.programs p ON p.id=t.program_id WHERE t.id=%s""",(ticket_id,)); ticket=cur.fetchone()
        if not ticket: raise HTTPException(404,"Nie znaleziono zgłoszenia")
        cur.execute("SELECT * FROM support.ticket_resolution_reports WHERE ticket_id=%s",(ticket_id,)); report=cur.fetchone()
        cur.execute("SELECT status,last_error,updated_at FROM support.support_jobs WHERE ticket_id=%s ORDER BY created_at DESC LIMIT 1",(ticket_id,)); job=cur.fetchone()
    state=dict(ticket["workflow_state"] or {}); answer_text=state.get("proposed_answer") or ("Analiza czeka na uzupełnienie danych." if ticket["status"]=="needs_information" else "Analiza nie została jeszcze wykonana."); answer=html.escape(answer_text)
    sources=[]
    for index,source in enumerate(state.get("sources") or [],1):
        label="Przypadek historyczny" if source.get("kind")=="historical_case" else "Dokumentacja"
        score=source.get("rerank_score"); score_text=f" · trafność {float(score):.3f}" if isinstance(score,(int,float)) else ""
        sources.append(f"<details><summary>{index}. {label}: {html.escape(source.get('title') or 'bez tytułu')}{score_text}</summary><pre>{html.escape(source.get('chunk_text') or '')}</pre></details>")
    source_html="".join(sources) or "<p>Brak trafnych źródeł.</p>"
    csrf_value=html.escape(current["csrf_token"],quote=True); report_html=""
    if report:
        published=f"<p><strong>Opublikowane rozwiązanie ID:</strong> {report['published_solution_id']}</p>" if report["published_solution_id"] else ""
        report_html=f"<section><h2>Raport realizacji</h2><p>Wynik: {html.escape(report['outcome'])}; ocena podpowiedzi: {report['suggestion_rating']}/5</p><pre>{html.escape(report['actual_resolution'])}</pre>{published}</section>"
    senior_publish=""
    if current["role"] in {"senior_technician","admin"} and report and not report["published_solution_id"]:
        senior_publish="""<section><h2>Publikacja do bazy wiedzy</h2><form id='publish-form'><label>Tytuł rozwiązania<input name='title' minlength='3' required></label><button>Opublikuj zatwierdzone rozwiązanie</button></form><div id='publish-message'></div></section>"""
    running=bool(job and job["status"] in {"queued","running"}); auto_refresh="setTimeout(()=>location.reload(),3000);" if running else ""
    progress_html="<div id='work-status' class='progress'><span class='spinner'></span><span>Model analizuje zgłoszenie, wyszukuje źródła i przygotowuje odpowiedź…</span></div>" if running else "<div id='work-status'></div>"
    clarification_html=""
    if ticket["status"]=="needs_information":
        labels={"error_code":"Kod błędu (wpisz „brak”, jeśli nie występuje)","version":"Wersja systemu (wpisz „nieznana”, jeśli brak danych)"}; fields=[]
        for missing in ticket["missing_fields"] or []:
            fields.append(f"<label>{html.escape(labels.get(missing,missing))}<input name='{html.escape(missing,quote=True)}' required></label>")
        clarification_html=f"<section class='warning'><h2>Potrzebne uzupełnienie</h2><p>Analiza została zatrzymana, ponieważ brakuje danych. Uzupełnij pola i wznów — odpowiedzi zostaną dołączone do opisu dla modelu.</p><form id='resume-form'>{''.join(fields)}<button>Uzupełnij i wznów analizę</button></form><div id='resume-message'></div></section>"
    job_text=f"{job['status']}: {job.get('last_error') or ''}" if job else "brak"
    return f"""<!doctype html><html lang='pl'><meta charset='utf-8'><title>Zgłoszenie {ticket_id}</title>
    <style>body{{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem}}section{{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}}pre{{white-space:pre-wrap}}label{{display:block;margin-top:1rem}}input,select,textarea{{width:100%;padding:.6rem;box-sizing:border-box}}textarea{{min-height:9rem}}button{{margin-top:1rem;padding:.7rem 1.2rem}}.progress{{display:flex;gap:.8rem;align-items:center;padding:1rem;background:#eef6ff;border:1px solid #8abcec;border-radius:8px}}.warning{{background:#fff8df;border-color:#d5a72f}}.spinner{{width:20px;height:20px;border:3px solid #b9d7f2;border-top-color:#1769aa;border-radius:50%;animation:spin .8s linear infinite}}@keyframes spin{{to{{transform:rotate(360deg)}}}}</style>
    <p><a href='/tickets'>← Zgłoszenia</a></p><h1>{html.escape(ticket['program_name'])} · {html.escape(ticket['client_name'])}</h1><p>Status: <strong>{html.escape(str(ticket['status']))}</strong> · zadanie: {html.escape(job_text)}</p>{progress_html}{clarification_html}
    <section><h2>Opis zgłoszenia</h2><pre>{html.escape(ticket['description'])}</pre><button id='analyse'>Uruchom / ponów analizę modelu</button></section>
    <section><h2>Proponowana odpowiedź</h2><pre>{answer}</pre><h3>Źródła</h3>{source_html}</section>
    <section><h2>Zgłoś realizację i oceń podpowiedź</h2><form id='report-form'><label>Wynik<select name='outcome'><option value='helped'>Pomogła</option><option value='partially_helped'>Częściowo pomogła</option><option value='not_helped'>Nie pomogła</option></select></label><label>Ocena podpowiedzi 1–5<input name='suggestion_rating' type='number' min='1' max='5' value='3' required></label><label>Faktycznie zastosowane rozwiązanie<textarea name='actual_resolution' minlength='10' required></textarea></label><label>Komentarz<textarea name='comment'></textarea></label><button>Zapisz raport realizacji</button></form><div id='report-message'></div></section>{report_html}{senior_publish}
    <script>const csrf='{csrf_value}';const showProgress=()=>{{document.getElementById('work-status').className='progress';document.getElementById('work-status').innerHTML='<span class="spinner"></span><span>Model analizuje zgłoszenie, wyszukuje źródła i przygotowuje odpowiedź…</span>';}};document.getElementById('analyse').onclick=async(e)=>{{e.target.disabled=true;showProgress();const r=await fetch('/api/v1/tickets/{ticket_id}/analysis/start',{{method:'POST',headers:{{'X-CSRF-Token':csrf}}}});if(r.ok)setTimeout(()=>location.reload(),800);else{{e.target.disabled=false;alert(await r.text());}}}};const rf=document.getElementById('resume-form');if(rf)rf.onsubmit=async(e)=>{{e.preventDefault();const answers=Object.fromEntries(new FormData(e.target).entries());showProgress();const r=await fetch('/api/v1/tickets/{ticket_id}/workflow/resume',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':csrf}},body:JSON.stringify({{answers}})}});document.getElementById('resume-message').textContent=r.ok?'Dane zapisane. Wznawiam analizę…':'Błąd: '+await r.text();if(r.ok)setTimeout(()=>location.reload(),800);}};document.getElementById('report-form').onsubmit=async(e)=>{{e.preventDefault();const b=Object.fromEntries(new FormData(e.target).entries());b.suggestion_rating=Number(b.suggestion_rating);const r=await fetch('/api/v1/tickets/{ticket_id}/resolution-report',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':csrf}},body:JSON.stringify(b)}});document.getElementById('report-message').textContent=r.ok?'Raport zapisany. Odświeżam...':'Błąd: '+await r.text();if(r.ok)setTimeout(()=>location.reload(),700);}};const pf=document.getElementById('publish-form');if(pf)pf.onsubmit=async(e)=>{{e.preventDefault();const r=await fetch('/api/v1/tickets/{ticket_id}/publish-resolution',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':csrf}},body:JSON.stringify(Object.fromEntries(new FormData(e.target).entries()))}});document.getElementById('publish-message').textContent=r.ok?'Rozwiązanie opublikowane. Odświeżam...':'Błąd: '+await r.text();if(r.ok)setTimeout(()=>location.reload(),700);}};{auto_refresh}</script></html>"""

@app.get("/tickets/new",response_class=HTMLResponse)
def new_ticket_page(current=Depends(user)):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id,name FROM public.clients WHERE name NOT LIKE 'Smoke %' ORDER BY name")
        clients=cur.fetchall()
        cur.execute("SELECT id,name FROM support.programs WHERE active AND name NOT LIKE 'Smoke %' ORDER BY name")
        programs=cur.fetchall()
        cur.execute("SELECT id,client_id,program_id,version,environment FROM support.client_installations WHERE active ORDER BY id")
        installations=cur.fetchall()
    client_options="".join(f"<option value='{row['id']}'>{html.escape(row['name'])}</option>" for row in clients)
    program_options="".join(f"<option value='{row['id']}'>{html.escape(row['name'])}</option>" for row in programs)
    installation_json=html.escape(json.dumps(installations,ensure_ascii=False),quote=False)
    csrf_value=html.escape(current["csrf_token"],quote=True)
    return f"""<!doctype html><html lang='pl'><meta charset='utf-8'><title>Nowe zgłoszenie</title>
    <style>body{{font:16px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem}}label{{display:block;margin-top:1rem}}select,textarea{{width:100%;padding:.6rem;box-sizing:border-box}}textarea{{min-height:12rem}}button{{margin-top:1rem;padding:.7rem 1.2rem}}#message{{margin-top:1rem}}</style>
    <h1>Nowe zgłoszenie serwisowe</h1><form id='ticket-form'>
    <label>Klient<select name='client_id' required>{client_options}</select></label>
    <label>System<select name='program_id' required>{program_options}</select></label>
    <label>Instalacja<select name='installation_id'><option value=''>Brak / nie dotyczy</option></select></label>
    <label>Opis zgłoszenia<textarea name='description' minlength='10' required placeholder='Objawy, kod błędu, wersja, wykonane czynności...'></textarea></label>
    <button type='submit'>Utwórz zgłoszenie</button></form><div id='message'></div><p><a href='/'>Powrót</a></p>
    <script>const installations={installation_json};const form=document.getElementById('ticket-form');const install=form.installation_id;function refresh(){{install.innerHTML='<option value="">Brak / nie dotyczy</option>';for(const row of installations)if(row.client_id==form.client_id.value&&row.program_id==form.program_id.value){{const o=document.createElement('option');o.value=row.id;o.textContent=[row.version,row.environment].filter(Boolean).join(' / ')||('Instalacja '+row.id);install.appendChild(o);}}}}form.client_id.onchange=refresh;form.program_id.onchange=refresh;refresh();form.addEventListener('submit',async(e)=>{{e.preventDefault();const f=new FormData(form);const body=Object.fromEntries(f.entries());body.client_id=Number(body.client_id);body.program_id=Number(body.program_id);body.installation_id=body.installation_id?Number(body.installation_id):null;const r=await fetch('/api/v1/tickets',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':'{csrf_value}'}},body:JSON.stringify(body)}});const m=document.getElementById('message');if(r.ok){{const data=await r.json();await fetch('/api/v1/tickets/'+data.id+'/analysis/start',{{method:'POST',headers:{{'X-CSRF-Token':'{csrf_value}'}}}});location='/tickets/'+data.id+'/view';}}else m.textContent='Błąd: '+await r.text();}});</script></html>"""

@app.get("/knowledge",response_class=HTMLResponse)
def knowledge_page(current=Depends(user)):
    require_role(current,"senior_technician")
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id,name FROM support.programs WHERE active AND name NOT LIKE 'Smoke %' ORDER BY name")
        programs=cur.fetchall()
        cur.execute("SELECT id,name FROM public.clients WHERE name NOT LIKE 'Smoke %' ORDER BY name")
        clients=cur.fetchall()
    program_options="".join(f"<option value='{row['id']}'>{html.escape(row['name'])}</option>" for row in programs)
    client_options="".join(f"<option value='{row['id']}'>{html.escape(row['name'])}</option>" for row in clients)
    csrf_value=html.escape(current["csrf_token"],quote=True)
    return f"""<!doctype html><html lang='pl'><meta charset='utf-8'><title>Import dokumentacji</title>
    <style>body{{font:16px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem}}label{{display:block;margin-top:1rem}}select,input{{width:100%;padding:.6rem;box-sizing:border-box}}button{{margin-top:1rem;padding:.7rem 1.2rem}}#message{{margin-top:1rem}}</style>
    <h1>Import dokumentacji technicznej</h1><p>PDF lub DOCX zostanie przypisany do jednego systemu. Zakres globalny jest dostępny wszystkim klientom tego systemu; zakres klienta tylko wybranemu klientowi.</p>
    <form id='knowledge-form'><label>System<select name='program_id' required>{program_options}</select></label>
    <label>Zakres<select name='scope'><option value='global'>Globalny dla systemu</option><option value='client'>Prywatny dla klienta</option></select></label>
    <label id='client-label' hidden>Klient<select name='client_id'><option value=''>Wybierz klienta</option>{client_options}</select></label>
    <label>Dokument PDF/DOCX<input type='file' name='file' accept='.pdf,.docx' required></label><button type='submit'>Importuj i indeksuj</button></form><div id='message'></div><p><a href='/'>Powrót</a></p>
    <script>const form=document.getElementById('knowledge-form');const clientLabel=document.getElementById('client-label');form.scope.onchange=()=>clientLabel.hidden=form.scope.value!=='client';form.addEventListener('submit',async(e)=>{{e.preventDefault();if(form.scope.value==='client'&&!form.client_id.value){{document.getElementById('message').textContent='Wybierz klienta.';return;}}const m=document.getElementById('message');m.textContent='Trwa parsowanie i indeksowanie dokumentu...';const r=await fetch('/api/v1/knowledge/documents',{{method:'POST',headers:{{'X-CSRF-Token':'{csrf_value}'}},body:new FormData(form)}});m.textContent=r.ok?'Dokument zaindeksowany: '+JSON.stringify(await r.json()):'Błąd: '+await r.text();}});</script></html>"""

@app.get("/cases",response_class=HTMLResponse)
def cases_page(current=Depends(user)):
    require_role(current,"senior_technician")
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id,name FROM support.programs WHERE active ORDER BY name")
        programs=cur.fetchall()
    options="".join(f"<option value='{row['id']}'>{html.escape(row['name'])}</option>" for row in programs)
    csrf_value=html.escape(current["csrf_token"],quote=True)
    return f"""<!doctype html><html lang='pl'><meta charset='utf-8'><title>Przypadki serwisowe</title>
    <style>body{{font:16px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem}}label{{display:block;margin-top:1rem}}input,select,textarea{{width:100%;padding:.6rem;box-sizing:border-box}}textarea{{min-height:8rem}}button{{margin-top:1rem;padding:.7rem 1.2rem}}#message{{margin-top:1rem}}</style>
    <h1>Dodaj przypadek serwisowy</h1><p>Każdy przypadek należy dokładnie do jednego systemu. Dane ZZL i ASW są wyszukiwane oddzielnie.</p>
    <form id='case-form'><label>System<select name='program_id' required>{options}</select></label>
    <label>Tytuł<input name='title' minlength='3' required></label>
    <label>Opis zgłoszenia<textarea name='ticket_description' minlength='10' required></textarea></label>
    <label>Rozwiązanie<textarea name='resolution' minlength='10' required></textarea></label>
    <label>Kod błędu<input name='error_code'></label><label>Wersja<input name='version'></label><label>Środowisko<input name='environment'></label>
    <button type='submit'>Zapisz przypadek</button></form><div id='message'></div><p><a href='/'>Powrót</a></p>
    <script>document.getElementById('case-form').addEventListener('submit',async(e)=>{{e.preventDefault();const f=new FormData(e.target);const body=Object.fromEntries(f.entries());body.program_id=Number(body.program_id);for(const k of ['error_code','version','environment'])if(!body[k])body[k]=null;const r=await fetch('/api/v1/cases',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':'{csrf_value}'}},body:JSON.stringify(body)}});document.getElementById('message').textContent=r.ok?'Przypadek zapisany.':'Błąd: '+await r.text();if(r.ok)e.target.reset();}});</script></html>"""

@app.post("/api/v1/auth/login")
def login(body:Login,request:Request,response:Response):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id,username,password_hash,role,active FROM support.users WHERE username=%s",(body.username,)); found=cur.fetchone()
        if not found or not found["active"] or not verify_password(found["password_hash"],body.password): raise HTTPException(401,"Błędne dane logowania")
        csrf_value=token(); sid,expires=create_session(cur,found["id"],csrf_value,ip_hash(request.client.host if request.client else "",settings.session_secret),request.headers.get("user-agent",""))
        cur.execute("UPDATE support.users SET last_login_at=now() WHERE id=%s",(found["id"],)); audit(cur,found["id"],"login","session",sid)
    response.set_cookie("support_session",str(sid),httponly=True,samesite="strict",secure=request.url.scheme=="https",expires=expires)
    return {"user":{"id":found["id"],"username":found["username"],"role":found["role"]},"csrf_token":csrf_value}

@app.post("/api/v1/auth/logout",status_code=204)
def logout(request:Request,response:Response,current=Depends(csrf)):
    with connect() as conn, conn.cursor() as cur:
        sid=request.cookies.get("support_session"); audit(cur,current["id"],"logout","session",sid); cur.execute("DELETE FROM support.sessions WHERE id=%s",(sid,))
    response.delete_cookie("support_session")

@app.post("/api/v1/tickets",status_code=201)
def create_ticket(body:TicketCreate,current=Depends(csrf)):
    ticket_id=uuid.uuid4()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO support.tickets(id,client_id,program_id,installation_id,description,owner_id,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",(ticket_id,body.client_id,body.program_id,body.installation_id,body.description,current["id"],current["id"])); row=cur.fetchone(); audit(cur,current["id"],"create","ticket",ticket_id)
    return row

@app.get("/api/v1/tickets/{ticket_id}")
def get_ticket(ticket_id:uuid.UUID,current=Depends(user)):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT t.*,c.name client_name,p.name program_name FROM support.tickets t JOIN public.clients c ON c.id=t.client_id JOIN support.programs p ON p.id=t.program_id WHERE t.id=%s",(ticket_id,)); row=cur.fetchone()
        if not row: raise HTTPException(404,"Nie znaleziono zgłoszenia")
        cur.execute("SELECT severity,body FROM support.client_notes n JOIN support.client_installations i ON i.id=n.installation_id WHERE i.id=%s AND n.retired_at IS NULL",(row["installation_id"],)); row["client_notes"]=cur.fetchall()
        return row

@app.post("/api/v1/tickets/{ticket_id}/analysis/start",status_code=202)
def start(ticket_id:uuid.UUID,current=Depends(csrf)):
    job=uuid.uuid4()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM support.tickets WHERE id=%s FOR UPDATE",(ticket_id,))
        if not cur.fetchone(): raise HTTPException(404,"Nie znaleziono zgłoszenia")
        cur.execute("INSERT INTO support.support_jobs(id,ticket_id,kind) VALUES(%s,%s,'analysis')",(job,ticket_id)); audit(cur,current["id"],"analysis_start","ticket",ticket_id,{"job_id":str(job)})
    return {"job_id":job,"status":"queued"}

@app.get("/api/v1/tickets/{ticket_id}/workflow")
def workflow(ticket_id:uuid.UUID,current=Depends(user)):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT status,recognized,missing_fields,workflow_state FROM support.tickets WHERE id=%s",(ticket_id,)); ticket=cur.fetchone()
        if not ticket: raise HTTPException(404)
        cur.execute("SELECT id,kind,status,attempts,last_error,updated_at FROM support.support_jobs WHERE ticket_id=%s ORDER BY created_at DESC LIMIT 1",(ticket_id,)); ticket["job"]=cur.fetchone()
        return ticket

@app.post("/api/v1/tickets/{ticket_id}/workflow/resume",status_code=202)
def resume(ticket_id:uuid.UUID,body:Resume,current=Depends(csrf)):
    job=uuid.uuid4()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE support.tickets SET workflow_state=workflow_state||%s::jsonb,status='new',updated_at=now() WHERE id=%s",(json.dumps({"answers":body.answers}),ticket_id))
        if not cur.rowcount: raise HTTPException(404)
        cur.execute("INSERT INTO support.support_jobs(id,ticket_id,kind,payload) VALUES(%s,%s,'resume',%s::jsonb)",(job,ticket_id,json.dumps(body.answers))); audit(cur,current["id"],"workflow_resume","ticket",ticket_id)
    return {"job_id":job,"status":"queued"}

@app.post("/api/v1/tickets/{ticket_id}/problem-link")
def link_problem(ticket_id:uuid.UUID,body:ProblemLink,current=Depends(csrf)):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO support.ticket_problem_links(ticket_id,problem_id,status,decided_by,decided_at) VALUES(%s,%s,%s,%s,now()) ON CONFLICT(ticket_id,problem_id) DO UPDATE SET status=excluded.status,decided_by=excluded.decided_by,decided_at=now()",(ticket_id,body.problem_id,body.decision,current["id"])); cur.execute("UPDATE support.tickets SET status=CASE WHEN %s='confirmed' THEN 'ready'::support.ticket_status ELSE 'awaiting_problem_decision'::support.ticket_status END WHERE id=%s",(body.decision,ticket_id)); audit(cur,current["id"],"problem_link","ticket",ticket_id,body.model_dump())
    return {"status":body.decision}

@app.post("/api/v1/tickets/{ticket_id}/resolution-mode")
def mode(ticket_id:uuid.UUID,body:ResolutionMode,current=Depends(csrf)):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE support.resolution_attempts SET mode=%s WHERE id=%s AND ticket_id=%s",(body.mode,body.attempt_id,ticket_id));
        if not cur.rowcount: raise HTTPException(404)
        cur.execute("UPDATE support.tickets SET status='in_progress' WHERE id=%s",(ticket_id,)); audit(cur,current["id"],"resolution_mode","ticket",ticket_id,{"mode":body.mode})
    return {"mode":body.mode}

@app.post("/api/v1/tickets/{ticket_id}/steps/{step_id}/result")
def step_result(ticket_id:uuid.UUID,step_id:int,body:StepResult,current=Depends(csrf)):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO support.step_results(attempt_id,step_id,result,successful,created_by) SELECT %s,%s,%s,%s,%s WHERE EXISTS(SELECT 1 FROM support.resolution_attempts WHERE id=%s AND ticket_id=%s) ON CONFLICT(attempt_id,step_id) DO UPDATE SET result=excluded.result,successful=excluded.successful",(body.attempt_id,step_id,body.result,body.successful,current["id"],body.attempt_id,ticket_id));
        if not cur.rowcount: raise HTTPException(404)
        audit(cur,current["id"],"step_result","ticket",ticket_id,{"step_id":step_id})
    return {"saved":True}

@app.post("/api/v1/tickets/{ticket_id}/feedback")
def feedback(ticket_id:uuid.UUID,body:FeedbackIn,current=Depends(csrf)):
    validation,reason=validate_feedback(body.outcome,body.comment)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO support.feedback(attempt_id,outcome,comment,validation,validation_reason,created_by) SELECT %s,%s,%s,%s,%s,%s WHERE EXISTS(SELECT 1 FROM support.resolution_attempts WHERE id=%s AND ticket_id=%s) ON CONFLICT(attempt_id) DO UPDATE SET outcome=excluded.outcome,comment=excluded.comment,validation=excluded.validation,validation_reason=excluded.validation_reason",(body.attempt_id,body.outcome,body.comment,validation,reason,current["id"],body.attempt_id,ticket_id));
        if not cur.rowcount: raise HTTPException(404)
        cur.execute("UPDATE support.tickets SET status='awaiting_feedback' WHERE id=%s",(ticket_id,)); audit(cur,current["id"],"feedback","ticket",ticket_id,{"validation":validation})
    return {"validation":validation,"reason":reason}

@app.post("/api/v1/tickets/{ticket_id}/close")
def close(ticket_id:uuid.UUID,body:CloseIn,current=Depends(csrf)):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT f.outcome,f.validation,a.solution_id FROM support.feedback f JOIN support.resolution_attempts a ON a.id=f.attempt_id WHERE a.ticket_id=%s AND (%s::uuid IS NULL OR a.id=%s)",(ticket_id,body.final_attempt_id,body.final_attempt_id)); feedback_row=cur.fetchone()
        if not feedback_row or feedback_row["validation"] != "consistent": raise HTTPException(409,"Feedback musi być kompletny i spójny")
        cur.execute("UPDATE support.resolution_attempts SET final_outcome=%s,finalized_at=now() WHERE id=%s",(feedback_row["outcome"],body.final_attempt_id)); column={"helped":"success_count","partially_helped":"partial_count","not_helped":"failure_count"}[feedback_row["outcome"]]; cur.execute(f"UPDATE support.solutions SET {column}={column}+1 WHERE id=%s AND status='approved'",(feedback_row["solution_id"],)); cur.execute("UPDATE support.tickets SET status='closed',closed_at=now(),updated_at=now() WHERE id=%s",(ticket_id,)); audit(cur,current["id"],"close","ticket",ticket_id)
    return {"status":"closed"}

@app.post("/api/v1/tickets/{ticket_id}/resolution-report")
def resolution_report(ticket_id:uuid.UUID,body:ResolutionReportIn,current=Depends(csrf)):
    report_id=uuid.uuid4()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM support.tickets WHERE id=%s",(ticket_id,))
        if not cur.fetchone(): raise HTTPException(404,"Nie znaleziono zgłoszenia")
        cur.execute("""INSERT INTO support.ticket_resolution_reports(id,ticket_id,outcome,suggestion_rating,actual_resolution,comment,created_by)
          VALUES(%s,%s,%s,%s,%s,%s,%s)
          ON CONFLICT(ticket_id) DO UPDATE SET outcome=excluded.outcome,suggestion_rating=excluded.suggestion_rating,
          actual_resolution=excluded.actual_resolution,comment=excluded.comment,created_by=excluded.created_by,updated_at=now()
          RETURNING *""",(report_id,ticket_id,body.outcome,body.suggestion_rating,body.actual_resolution,body.comment,current["id"])); row=cur.fetchone()
        cur.execute("UPDATE support.tickets SET status='awaiting_feedback',updated_at=now() WHERE id=%s",(ticket_id,)); audit(cur,current["id"],"resolution_report","ticket",ticket_id,{"outcome":body.outcome,"rating":body.suggestion_rating})
    return row

@app.post("/api/v1/tickets/{ticket_id}/publish-resolution",status_code=201)
def publish_resolution(ticket_id:uuid.UUID,body:PublishResolutionIn,current=Depends(csrf)):
    require_role(current,"senior_technician")
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT t.*,r.id report_id,r.actual_resolution,r.published_solution_id
          FROM support.tickets t JOIN support.ticket_resolution_reports r ON r.ticket_id=t.id WHERE t.id=%s FOR UPDATE""",(ticket_id,)); row=cur.fetchone()
        if not row: raise HTTPException(409,"Najpierw zapisz raport realizacji")
        if row["published_solution_id"]: raise HTTPException(409,"Rozwiązanie zostało już opublikowane")
        cur.execute("SELECT problem_id FROM support.ticket_problem_links WHERE ticket_id=%s AND status='confirmed' ORDER BY decided_at DESC NULLS LAST LIMIT 1",(ticket_id,)); linked=cur.fetchone()
        if linked: problem_id=linked["problem_id"]
        else:
            cur.execute("INSERT INTO support.canonical_problems(program_id,title,normalized_description) VALUES(%s,%s,%s) RETURNING id",(row["program_id"],body.title,row["description"])); problem_id=cur.fetchone()["id"]
            cur.execute("INSERT INTO support.ticket_problem_links(ticket_id,problem_id,status,decided_by,decided_at) VALUES(%s,%s,'confirmed',%s,now())",(ticket_id,problem_id,current["id"]))
        cur.execute("""INSERT INTO support.solutions(problem_id,title,summary,status,created_by,approved_by,approved_at)
          VALUES(%s,%s,%s,'approved',%s,%s,now()) RETURNING id""",(problem_id,body.title,row["actual_resolution"],current["id"],current["id"])); solution_id=cur.fetchone()["id"]
        cur.execute("INSERT INTO support.solution_steps(solution_id,position,instruction,expected_result) VALUES(%s,1,%s,'Problem rozwiązany')",(solution_id,row["actual_resolution"]))
        case_id=uuid.uuid4(); cur.execute("""INSERT INTO support.historical_cases(id,program_id,title,ticket_description,resolution,status,created_by)
          VALUES(%s,%s,%s,%s,%s,'approved',%s)""",(case_id,row["program_id"],body.title,row["description"],row["actual_resolution"],current["id"]))
        cur.execute("UPDATE support.ticket_resolution_reports SET published_solution_id=%s,published_at=now() WHERE id=%s",(solution_id,row["report_id"])); audit(cur,current["id"],"publish_resolution","ticket",ticket_id,{"solution_id":solution_id,"historical_case_id":str(case_id)})
    return {"solution_id":solution_id,"historical_case_id":case_id,"status":"approved"}

@app.post("/api/v1/knowledge/documents",status_code=202)
def upload_document(program_id:int=Form(...),scope:str=Form(...),client_id:int|None=Form(None),file:UploadFile=File(...),current=Depends(csrf)):
    require_role(current,"senior_technician")
    if scope not in {"global","client"} or (scope=="client" and not client_id): raise HTTPException(422,"Nieprawidłowy zakres")
    suffix=Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf",".docx"}: raise HTTPException(415,"Obsługiwane są PDF i DOCX")
    root=Path(settings.upload_root); root.mkdir(parents=True,exist_ok=True); target=root/f"{uuid.uuid4()}{suffix}"
    with target.open("wb") as out: shutil.copyfileobj(file.file,out)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    text,_,_=parse_document(target)
    chunks=split_into_chunks(text,target_chars=1100,overlap_chars=150)
    vectors=EmbeddingClient(settings.embedding_url,384).embed([str(x["text"]) for x in chunks])
    with connect() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO support.knowledge_documents(program_id,client_id,scope,source_file,title,sha256,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id",(program_id,client_id if scope=="client" else None,scope,str(target),file.filename,digest,current["id"])); doc=cur.fetchone()["id"]; audit(cur,current["id"],"knowledge_upload","knowledge_document",doc)
        for index,(chunk,vector) in enumerate(zip(chunks,vectors)):
            cur.execute("INSERT INTO support.knowledge_chunks(document_id,chunk_index,chunk_text,metadata,embedding) VALUES(%s,%s,%s,%s::jsonb,%s::vector)",(doc,index,chunk["text"],json.dumps(chunk.get("metadata",{})),to_pgvector(vector)))
    return {"document_id":doc,"status":"indexed","chunks":len(chunks)}

@app.post("/api/v1/cases",status_code=201)
def create_historical_case(body:HistoricalCaseIn,current=Depends(csrf)):
    require_role(current,"senior_technician")
    case_id=uuid.uuid4()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM support.programs WHERE id=%s AND active",(body.program_id,))
        program=cur.fetchone()
        if not program: raise HTTPException(404,"Nie znaleziono aktywnego systemu")
        cur.execute("""INSERT INTO support.historical_cases(id,program_id,title,ticket_description,resolution,error_code,version,environment,created_by)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
          (case_id,body.program_id,body.title,body.ticket_description,body.resolution,body.error_code,body.version,body.environment,current["id"]))
        row=cur.fetchone(); audit(cur,current["id"],"create","historical_case",case_id,{"program_id":body.program_id,"program":program["name"]})
    return row

@app.get("/api/v1/cases")
def list_historical_cases(program_id:int,current=Depends(user)):
    require_role(current,"senior_technician")
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT c.id,c.program_id,p.name program,c.title,c.ticket_description,c.resolution,c.error_code,c.version,c.environment,c.status,c.created_at
          FROM support.historical_cases c JOIN support.programs p ON p.id=c.program_id
          WHERE c.program_id=%s AND c.status<>'retired' ORDER BY c.created_at DESC""",(program_id,))
        return {"program_id":program_id,"cases":cur.fetchall()}

@app.post("/api/v1/solutions/{solution_id}/approve")
def approve(solution_id:int,current=Depends(csrf)):
    require_role(current,"senior_technician")
    with connect() as conn, conn.cursor() as cur: cur.execute("UPDATE support.solutions SET status='approved',approved_by=%s,approved_at=now() WHERE id=%s AND status='draft'",(current["id"],solution_id)); audit(cur,current["id"],"approve","solution",solution_id)
    return {"status":"approved"}

@app.post("/api/v1/solutions/{solution_id}/reject")
def reject(solution_id:int,current=Depends(csrf)):
    require_role(current,"senior_technician")
    with connect() as conn, conn.cursor() as cur: cur.execute("UPDATE support.solutions SET status='rejected' WHERE id=%s AND status='draft'",(solution_id,)); audit(cur,current["id"],"reject","solution",solution_id)
    return {"status":"rejected"}
