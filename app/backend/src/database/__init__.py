from .repositories.study import StudyRepository
from .repositories.project import ProjectRepository
from .repositories.report import ReportRepository
from .repositories.aspects import AspectRepository

from .sessions import AsyncSessionLocal, AsyncSession

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            # Ensure session is properly closed
            await session.close()
