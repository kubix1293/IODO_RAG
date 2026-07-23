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
    ("email", re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    ("pesel_or_id", re.compile(r"(?<!\d)(?:\d[ -]?){11}(?!\d)"), "[PESEL_LUB_ID]"),
    ("iban", re.compile(r"\bPL\s?(?:\d[ ]?){26}\b", re.I), "[RACHUNEK_BANKOWY]"),
    ("nip", re.compile(r"(?i)\bNIP\s*[:\-]?\s*(?:\d[ -]?){10}\b"), "[NIP]"),
    ("regon", re.compile(r"(?i)\bREGON\s*[:\-]?\s*(?:\d[ -]?){9,14}\b"), "[REGON]"),
    ("phone", re.compile(r"(?<!\d)(?:\+?48[ -]?)?(?:\d[ -]?){9}(?!\d)"), "[TELEFON]"),
    ("ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[ADRES_IP]"),
    ("credential", re.compile(r"(?i)\b(?:hasło|password|token|api[_ -]?key)\s*[:=]\s*\S+"), "[DANE_UWIERZYTELNIAJĄCE]"),
    ("person", re.compile(r"(?i)\b(?:pacjent|osoba|kontakt|imię i nazwisko)\s*[:\-]?\s+[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż-]+){1,2}"), "[OSOBA]"),
    ("address", re.compile(r"(?i)\b(?:adres|zamieszkał[ay]?)\s*[:\-]\s*[^,;\n]{5,100}"), "[ADRES]"),
    ("client", re.compile(r"(?i)\b(?:klient|firma|spółka)\s+[\w.-]+"), "[KLIENT]"),
]

def anonymize_with_report(text: str) -> tuple[str,list[str]]:
    found=[]
    for category,pattern,replacement in _SENSITIVE:
        text,count=pattern.subn(replacement,text)
        if count: found.extend([category]*count)
    return text,found

def anonymize(text: str) -> str:
    return anonymize_with_report(text)[0]

def client_reference(client_id: int, secret: str) -> str:
    digest=hmac.new(secret.encode(),f"support-client:{client_id}".encode(),hashlib.sha256).hexdigest()
    return f"K-{digest[:12]}"
