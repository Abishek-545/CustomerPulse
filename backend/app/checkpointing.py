"""Durable LangGraph checkpoint selection."""
from langgraph.checkpoint.memory import MemorySaver

from .config import settings
from .db import database_url


_connection = None


def build_checkpointer():
    global _connection
    use_postgres = settings.checkpoint_backend == "postgres" or (settings.checkpoint_backend == "auto" and database_url.startswith("postgresql"))
    if not use_postgres:
        return MemorySaver(), "memory"
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg import Connection
    connection_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    _connection = Connection.connect(connection_url, autocommit=True, prepare_threshold=0)
    saver = PostgresSaver(_connection)
    saver.setup()
    return saver, "postgres"
