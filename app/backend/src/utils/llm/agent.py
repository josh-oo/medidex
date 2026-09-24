import os
from typing import Any, AsyncGenerator

from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

load_dotenv()

POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_DB_LANGGRAPH = os.getenv("POSTGRES_DB_LANGGRAPH")

DB_URI = os.getenv("DB_URI") or (
	f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB_LANGGRAPH}"
)


async def get_checkpointer() -> AsyncGenerator[Any, None]:
	if not DB_URI:
		raise RuntimeError("DB_URI is not configured")

	async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
		yield checkpointer
