import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://iodo:iodo@postgres:5432/iodo")
    embedding_url: str = os.getenv("EMBEDDING_URL", "http://tei:80").rstrip("/")
    reranker_url: str = os.getenv("RERANKER_URL", "http://reranker:80").rstrip("/")
    llm_url: str = os.getenv("LLM_URL", "http://ollama:11434").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "llama3.2:3b")
    session_secret: str = os.getenv("SUPPORT_SESSION_SECRET", "development-only-change-me")
    checkpoint_key: str = os.getenv("SUPPORT_CHECKPOINT_KEY", "")
    upload_root: str = os.getenv("SUPPORT_UPLOAD_ROOT", "/data/support-uploads")

settings = Settings()
