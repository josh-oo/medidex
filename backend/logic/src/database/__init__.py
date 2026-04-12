from fastapi import Depends

from .repositories.study import StudyRepository
from .repositories.project import ProjectRepository
from .repositories.report import ReportRepository
from .repositories.aspects import AspectRepository

from ..api.auth import get_user_id

from .sessions import AsyncSessionLocal, AsyncSession, test_db

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            # Ensure session is properly closed
            await session.close()
        
async def db_ready(db: AsyncSession = Depends(get_session)) -> str:
    return await test_db(db)
    
def get_study_repo(db: AsyncSession = Depends(get_session), user_id = Depends(get_user_id)) -> StudyRepository:
    return StudyRepository(db=db, user_id=user_id)

def get_project_repo(db: AsyncSession = Depends(get_session), user_id = Depends(get_user_id)) -> ProjectRepository:
    return ProjectRepository(db=db, user_id=user_id)

def get_report_repo(db: AsyncSession = Depends(get_session), user_id = Depends(get_user_id)) -> ReportRepository:
    return ReportRepository(db=db, user_id=user_id)

def get_aspect_repo(db: AsyncSession = Depends(get_session)) -> AspectRepository:
    return AspectRepository(db=db)