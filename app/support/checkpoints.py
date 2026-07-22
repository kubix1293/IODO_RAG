import base64, hashlib, json
from cryptography.fernet import Fernet
from .config import settings

def _fernet() -> Fernet:
    raw = settings.checkpoint_key.encode()
    try: return Fernet(raw)
    except Exception: return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw or settings.session_secret.encode()).digest()))

def encrypt(state: dict) -> bytes: return _fernet().encrypt(json.dumps(state, ensure_ascii=False).encode())
def decrypt(value: bytes) -> dict: return json.loads(_fernet().decrypt(value).decode())
