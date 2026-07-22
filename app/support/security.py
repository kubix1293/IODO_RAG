import hashlib, hmac, re, secrets
from argon2 import PasswordHasher
from fastapi import HTTPException

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
ROLE_LEVEL = {"technician": 1, "senior_technician": 2, "admin": 3}

def hash_password(value: str) -> str:
    if len(value) < 12: raise ValueError("Hasło musi mieć co najmniej 12 znaków")
    return ph.hash(value)

def verify_password(encoded: str, value: str) -> bool:
    try: return ph.verify(encoded, value)
    except Exception: return False

def require_role(user: dict, role: str) -> None:
    if ROLE_LEVEL.get(str(user.get("role")), 0) < ROLE_LEVEL[role]:
        raise HTTPException(403, "Brak wymaganej roli")

def token() -> str: return secrets.token_urlsafe(32)
def ip_hash(ip: str, secret: str) -> str: return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()

_SENSITIVE = [
    (re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"\b(?:\+?48\s*)?(?:\d[ -]?){9}\b"), "[TELEFON]"),
    (re.compile(r"\b\d{11}\b"), "[IDENTYFIKATOR]"),
    (re.compile(r"(?i)\b(?:klient|firma|spółka)\s+[\w.-]+"), "[KLIENT]"),
]
def anonymize(text: str) -> str:
    for pattern, replacement in _SENSITIVE: text = pattern.sub(replacement, text)
    return text
