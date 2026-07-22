import json, uuid
from datetime import datetime, timedelta, timezone
import psycopg
from psycopg.rows import dict_row
from .config import settings

def connect(): return psycopg.connect(settings.database_url, row_factory=dict_row)
def audit(cur, user_id, action, entity_type, entity_id, details=None):
    cur.execute("INSERT INTO support.audit_events(actor_id,action,entity_type,entity_id,details) VALUES(%s,%s,%s,%s,%s::jsonb)",(user_id,action,entity_type,str(entity_id),json.dumps(details or {})))

def session_user(session_id: str | None):
    if not session_id: return None
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT u.id,u.username,u.role,s.csrf_token FROM support.sessions s JOIN support.users u ON u.id=s.user_id WHERE s.id=%s AND s.expires_at>now() AND u.active",(session_id,))
        return cur.fetchone()

def create_session(cur, user_id, csrf, ip_hash, user_agent):
    sid=uuid.uuid4(); expires=datetime.now(timezone.utc)+timedelta(hours=12)
    cur.execute("INSERT INTO support.sessions(id,user_id,csrf_token,expires_at,ip_hash,user_agent) VALUES(%s,%s,%s,%s,%s,%s)",(sid,user_id,csrf,expires,ip_hash,user_agent[:500]))
    return sid, expires
