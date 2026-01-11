import os
from fastapi import Depends

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from dotenv import load_dotenv

from ..api.auth import get_user_id

from .repositories.study import StudyRepository
from .repositories.batch import BatchRepository
from .repositories.report import ReportRepository
from .repositories.aspects import AspectRepository

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB_RESOURCES = os.getenv("POSTGRES_DB_RESOURCES")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB_RESOURCES}"
PDF_PATH = os.path.join(DATABASE_VOLUME,"resources", "pdfs")

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False  # keep objects available after commit
)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

async def db_ready(db: AsyncSession = Depends(get_session)):
    try:
        await db.execute(select(1))
        return "ready"
    except Exception as e:
        return str(e)
        
def get_study_repo(db: AsyncSession = Depends(get_session), user_id = Depends(get_user_id)):
    return StudyRepository(db=db, user_id=user_id)

def get_batch_repo(db: AsyncSession = Depends(get_session), user_id = Depends(get_user_id)):
    return BatchRepository(db=db, user_id=user_id)

def get_report_repo(db: AsyncSession = Depends(get_session), user_id = Depends(get_user_id)):
    return ReportRepository(db=db, user_id=user_id)

def get_aspect_repo(db: AsyncSession = Depends(get_session)):
    return AspectRepository(db=db)