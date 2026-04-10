from fastapi import Depends

from .repositories.study import StudyRepository
from .repositories.project import ProjectRepository
from .repositories.report import ReportRepository
from .repositories.aspects import AspectRepository

from ..api.auth import get_user_id

from .sessions import AsyncSessionLocal, AsyncSession, test_db

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
        
async def db_ready(db: AsyncSession = Depends(get_session)):
    return await test_db(db)
    
def get_study_repo(db: AsyncSession = Depends(get_session), user_id = Depends(get_user_id)):
    return StudyRepository(db=db, user_id=user_id)

def get_project_repo(db: AsyncSession = Depends(get_session), user_id = Depends(get_user_id)):
    return ProjectRepository(db=db, user_id=user_id)

def get_report_repo(db: AsyncSession = Depends(get_session), user_id = Depends(get_user_id)):
    return ReportRepository(db=db, user_id=user_id)

def get_aspect_repo(db: AsyncSession = Depends(get_session)):
    return AspectRepository(db=db)