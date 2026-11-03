from sqlalchemy import exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..models import Study, StudyTag, Tag
from typing import List, Optional

class AspectRepository:
    def __init__(self, db : AsyncSession):
        self.db = db

    async def get_all_tags(self, category: str, ids: List[int], databases: Optional[List[int]] = None) -> List[Tag]:
        """All tags of a category (a key of config/medidex-study.yaml), or only those with the given ids; with
        `databases`, only the tags of studies of those study databases."""
        stmt = select(Tag).where(Tag.category == category)
        if ids:
            stmt = stmt.where(Tag.id.in_(ids))
        if databases:
            stmt = stmt.where(exists().where(
                StudyTag.tag_id == Tag.id, StudyTag.study_id == Study.id, Study.database_id.in_(databases)
            ))
        return list((await self.db.execute(stmt.order_by(Tag.id))).scalars().all())
