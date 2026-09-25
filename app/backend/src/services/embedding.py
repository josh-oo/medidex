import os
import httpx

import asyncio

import html
import unicodedata
from bs4 import BeautifulSoup

from dotenv import load_dotenv

from openai import AsyncOpenAI

load_dotenv()

BASE_URL = os.getenv("EMBEDDING_MODEL_BASE_URL")
API_KEY = os.getenv("EMBEDDING_MODEL_API_KEY")

class EmbeddingService:

    def __init__(self):
        #self.channel = CHANNEL
        self.sem = asyncio.Semaphore(4) #max number of concurrent requests

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
                model=None
            )
            vector = response.data[0].embedding
            return vector
        
    def readyz(self):
        try:
            resp = httpx.get("http://embedding:80/health", timeout=2.0)

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