"""Factory for durable LangGraph checkpoints keyed by ticket_id/thread_id."""
import hashlib
from contextlib import asynccontextmanager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from .config import settings

@asynccontextmanager
async def checkpoint_saver():
    # EncryptedSerializer reads LANGGRAPH_AES_KEY. Keep that key outside the DB.
    if not settings.checkpoint_key:
        raise RuntimeError("SUPPORT_CHECKPOINT_KEY/LANGGRAPH_AES_KEY is required")
    serde = EncryptedSerializer.from_pycryptodome_aes(key=hashlib.sha256(settings.checkpoint_key.encode()).digest())
    async with AsyncPostgresSaver.from_conn_string(settings.database_url, serde=serde) as saver:
        await saver.setup()
        yield saver

def graph_config(ticket_id: str) -> dict:
    return {"configurable": {"thread_id": ticket_id}}
