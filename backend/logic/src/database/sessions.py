import os

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel import select

from dotenv import load_dotenv

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB_RESOURCES = os.getenv("POSTGRES_DB_RESOURCES")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB_RESOURCES}"
PDF_PATH = os.path.join(DATABASE_VOLUME,"resources", "pdfs")

engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    pool_size=20,  # Number of connections to maintain in pool
    max_overflow=10,  # Additional connections beyond pool_size
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_pre_ping=True,  # Verify connections are alive before using them
)

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False  # keep objects available after commit
)

async def test_db(db : AsyncSession) -> str:
    try:
        await db.execute(select(1))
        return "ready"
    except Exception as e:
        return str(e)