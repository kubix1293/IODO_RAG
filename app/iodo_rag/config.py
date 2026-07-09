from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    embedding_url: str
    embedding_model: str
    embedding_dim: int
    chunk_target_chars: int
    chunk_overlap_chars: int
    llm_url: str
    llm_model: str
    llm_timeout_seconds: int
    llm_context_max_chars: int
    llm_num_ctx: int
    llm_num_predict: int


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql://iodo:iodo@localhost:5432/iodo"),
        embedding_url=os.getenv("EMBEDDING_URL", "http://localhost:8080").rstrip("/"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small"),
        embedding_dim=int(os.getenv("EMBEDDING_DIM", "384")),
        chunk_target_chars=int(os.getenv("CHUNK_TARGET_CHARS", "3500")),
        chunk_overlap_chars=int(os.getenv("CHUNK_OVERLAP_CHARS", "500")),
        llm_url=os.getenv("LLM_URL", "http://localhost:11434").rstrip("/"),
        llm_model=os.getenv("LLM_MODEL", "llama3.2:3b"),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "180")),
        llm_context_max_chars=int(os.getenv("LLM_CONTEXT_MAX_CHARS", "8500")),
        llm_num_ctx=int(os.getenv("LLM_NUM_CTX", "8192")),
        llm_num_predict=int(os.getenv("LLM_NUM_PREDICT", "384")),
    )
