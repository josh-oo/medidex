"""What the backend does when it starts, before and after it serves its first request: the schema of the resources
database and the vectorstore sync. app-init only prepares Qdrant, the data volume and Keycloak, and never touches
postgres. No data is loaded: admins create or import the study databases (e.g. the demo database,
deploy/data/seed/synthetic_database.zip) on the Database management page.
"""

import asyncio
import logging
from typing import Optional

from ..context import RequestContext
from ..database.schema import ResourceSchema
from ..database.sessions import AsyncSessionLocal, engine

logger = logging.getLogger(__name__)


class Startup:
    def __init__(self, schema: ResourceSchema):
        self.schema = schema
        self._sync: Optional[asyncio.Task] = None

    @classmethod
    def from_env(cls) -> "Startup":
        return cls(ResourceSchema(engine))

    async def start(self) -> None:
        """The schema, before the first request; the vectorstore sync then runs in the background (it embeds, which
        takes long), until it is done or the backend stops."""
        await self.schema.ensure()
        self._sync = asyncio.create_task(self._sync_vectorstore())

    async def stop(self) -> None:
        if self._sync is not None and not self._sync.done():
            self._sync.cancel()

    async def _sync_vectorstore(self) -> None:
        try:
            async with AsyncSessionLocal() as session:
                result = await RequestContext(db=session, user_id=None).maintenance_service.sync_vectorstore()
            logger.info("vectorstore sync done: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("vectorstore sync failed; it runs again on the next start")
