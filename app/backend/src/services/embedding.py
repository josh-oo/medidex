import os
from typing import Awaitable, Callable, Optional, Sequence, TypeVar
import httpx

import asyncio

import html
import unicodedata
from bs4 import BeautifulSoup

from dotenv import load_dotenv

from openai import APIStatusError, AsyncOpenAI

load_dotenv()

BASE_URL = os.getenv("EMBEDDING_MODEL_BASE_URL")
API_KEY = os.getenv("EMBEDDING_MODEL_API_KEY")
# The model asked for in every request: required by hosted APIs (e.g. "openai/text-embedding-3-small" on OpenRouter),
# ignored by the local text-embeddings-inference container, which serves the one model it was started with.
MODEL = os.getenv("EMBEDDING_MODEL_ID")
# Probed by readyz; empty for a hosted API, which has no health endpoint of its own.
HEALTH_URL = os.getenv("EMBEDDING_MODEL_HEALTH_URL")
T = TypeVar("T")
# Requests to the embedding backend at once, process-wide: the local model takes few, a hosted API many more.
MAX_CONCURRENCY = int(os.getenv("EMBEDDING_MAX_CONCURRENCY") or "4")

class EmbeddingService:
    def __init__(self):
        #self.channel = CHANNEL
        self.sem = asyncio.Semaphore(MAX_CONCURRENCY)

        #IMPORTANT: do not use langchain since it applies tokenization before sending it to TEI
        #MORE INFORMATION: https://github.com/huggingface/text-embeddings-inference/issues/273    
        self.model = AsyncOpenAI(
            base_url=BASE_URL,
            api_key=API_KEY, 
        )
    
    async def preprocess(self, text):
        def _preprocess(text):
            utf8_string = html.unescape(text)
            utf8_string = utf8_string.replace('\r', '\n')
            utf8_string = utf8_string.replace('\n', ' ')

            soup = BeautifulSoup(utf8_string, "lxml")
            utf8_string = soup.get_text(separator='')

            utf8_string = ' '.join(utf8_string.split())
            normalized_text = unicodedata.normalize("NFKC", utf8_string)
            return normalized_text
        return await asyncio.to_thread(_preprocess, text)
    
    async def embed(self, text: str):
        async with self.sem:
            text = await self.preprocess(text)
            response = await self.model.embeddings.create(
                input=[text],
                model=MODEL
            )
            vector = response.data[0].embedding
            return vector

    @staticmethod
    async def for_each(items: Sequence[T], handle: Callable[[T], Awaitable[None]]) -> None:
        """Awaits `handle` for every item, all at once: as many embed at the same time (one request per text) as the
        semaphore lets (MAX_CONCURRENCY). The first error is raised, once the others are cancelled."""
        error: Optional[BaseException] = None
        try:
            async with asyncio.TaskGroup() as group:
                for item in items:
                    group.create_task(handle(item))
        except ExceptionGroup as errors:
            error = errors.exceptions[0]
        # Raised outside the except block, so that it does not seem to come from the group.
        if error is not None:
            raise error

    @staticmethod
    def is_transient(exc: BaseException) -> bool:
        """Whether a request may succeed if tried again: the service is not reachable or overloaded (e.g. the local
        model still starting), not a request it refuses (a missing API key, an unknown model)."""
        if isinstance(exc, APIStatusError):
            return exc.status_code in (408, 409, 429) or exc.status_code >= 500
        return True

    def readyz(self):
        if not HEALTH_URL:
            return {"status": "healthy", "message": "hosted service, not probed"}
        try:
            resp = httpx.get(HEALTH_URL, timeout=2.0)

            if resp.status_code == 200:
                return {"status": "healthy", "message": "subservice reachable"}
            else:
                return {
                    "status": "degraded",
                    "message": f"subservice returned {resp.status_code}"
                }

        except httpx.RequestError as e:
            return {
                "status": "unhealthy",
                "message": f"subservice unreachable: {str(e)}"
            }

# Singleton: the semaphore inside EmbeddingService is meant to cap concurrent
# requests to the embedding backend process-wide. Constructing a new instance
# per request (as the old FastAPI Depends(get_embedding_service) factory did)
# gives each request its own semaphore instead, so the cap never actually
# applies across concurrent requests.
embedding_service = EmbeddingService()