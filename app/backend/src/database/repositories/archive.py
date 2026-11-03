"""The archive of the reports of the updates (ReportArchive in models.py) and what merging a report into the core
database changes in the tables (see UpdateMergeService)."""

import datetime
from typing import Any, Dict, List, Optional, Sequence

from pydantic_core import to_jsonable_python
from sqlalchemy import Table, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, delete, select

from ..models import (
    ARCHIVE_KEY,
    UPDATE_DATA_KEY,
    Report,
    ReportArchive,
    ReportFields,
    Study,
    Link,
    UpdateLink,
    UpdateReport,
    UpdateStudy,
)

# What became of an archived report (ReportArchive.outcome).
MERGED = "merged"
DELETED = "deleted"


class ArchiveRepository:
    def __init__(self, db: AsyncSession, user_id: Optional[str]):
        self.db = db
        self.user_id = user_id

    async def commit(self):
        await self.db.commit()

    async def rollback(self):
        await self.db.rollback()

    async def get_outcome_counts(self, project_id: str) -> Dict[str, int]:
        """How many reports of the project were merged and deleted, by outcome."""
        result = await self.db.execute(
            select(ReportArchive.outcome, func.count(ReportArchive.report_id))
            .where(ReportArchive.project_id == project_id)
            .group_by(ReportArchive.outcome)
        )
        return dict(result.all())

    async def get_last_archived_at(self, project_id: str) -> Optional[datetime.datetime]:
        """When the last report of the project was merged or deleted."""
        return (await self.db.execute(
            select(func.max(ReportArchive.archived_at)).where(ReportArchive.project_id == project_id)
        )).scalar_one_or_none()

    async def collect(self, report_id: int) -> Dict[str, Any]:
        """What the update knows of the report, as JSON: the report (with what the update keeps of it, see
        UpdateReport), its links in every scope and its rows of the tables of the updates that are archived (see
        UPDATE_DATA and UPDATE_CACHE)."""
        report = await self.db.get(UpdateReport, report_id)
        links = (await self.db.execute(
            select(
                func.coalesce(UpdateLink.study_id, UpdateLink.update_study_id).label("study_id"),
                func.coalesce(Study.short_name, UpdateStudy.short_name).label("short_name"),
                UpdateLink.created_by,
                UpdateLink.created_at,
                UpdateStudy.created_by.label("study_created_by"),
            )
            .outerjoin(Study, Study.id == UpdateLink.study_id)
            .outerjoin(UpdateStudy, UpdateStudy.id == UpdateLink.update_study_id)
            .where(UpdateLink.report_id == report_id)
        )).mappings().all()

        tables = {}
        for table in self._update_tables():
            if table.info.get(ARCHIVE_KEY, True) and table is not UpdateLink.__table__:
                rows = (await self.db.execute(select(table).where(table.c.report_id == report_id))).mappings().all()
                if rows:
                    tables[table.name] = [dict(row) for row in rows]

        return to_jsonable_python({
            "report": report.model_dump(exclude={"project_id"}) if report else None,
            "links": [dict(link) for link in links],
            "tables": tables,
        })

    async def promote_report(self, report_id: int) -> None:
        """Adds the report of an update to the core database under its id (see Report); its row of the update stays
        until remove_update_report."""
        report = await self.db.get(UpdateReport, report_id)
        self.db.add(Report(id=report.id, **{name: getattr(report, name) for name in ReportFields.model_fields}))
        await self.db.flush()

    async def add_core_links(self, report_id: int, study_ids: Sequence[int]) -> None:
        """Links the report of the core database to the studies of the core database `study_ids`."""
        self.db.add_all(Link(study_id=study_id, report_id=report_id) for study_id in study_ids)
        await self.db.flush()

    async def get_linked_study_ids(self, report_id: int) -> List[int]:
        """The studies (of the core database or of the update) any scope linked the report of an update to."""
        return list((await self.db.execute(
            select(func.coalesce(UpdateLink.study_id, UpdateLink.update_study_id))
            .where(UpdateLink.report_id == report_id)
            .distinct()
        )).scalars().all())

    async def remove_update_report(self, report_id: int) -> None:
        """Removes the report from its update: its row of update_report, and with it (the foreign keys of the tables of
        the updates, see UPDATE_DATA) its links, flags, commits, scores and the rows of the extensions."""
        await self.db.execute(delete(UpdateReport).where(UpdateReport.id == report_id))
        await self.db.flush()

    def add(self, archive: ReportArchive) -> None:
        self.db.add(archive)

    @staticmethod
    def _update_tables() -> List[Table]:
        """The tables of update data (see UPDATE_DATA) whose rows belong to a report (a report_id column)."""
        return [
            table for table in SQLModel.metadata.sorted_tables
            if table.info.get(UPDATE_DATA_KEY) and "report_id" in table.c
        ]
