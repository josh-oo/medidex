"""The archive of the reports of the updates (ReportArchive in models.py) and what merging a report into the core
database changes in the tables (see UpdateMergeService)."""

import datetime
from typing import Any, Dict, List, Optional, Sequence

from pydantic_core import to_jsonable_python
from sqlalchemy import Table, exists, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, delete, select

from ..models import (
    ARCHIVE_KEY,
    UPDATE_DATA_KEY,
    Report,
    ReportAdded,
    ReportArchive,
    ReportFlag,
    Study,
    StudyAdded,
    StudyReport,
    StudyReportAdded,
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
        """What the update knows of the report, as JSON: the report, its row of the update, its links in every scope,
        its flags and its rows of the update tables that are archived (see UPDATE_DATA and UPDATE_CACHE)."""
        report = await self.db.get(Report, report_id)
        added = (await self.db.execute(select(ReportAdded).where(ReportAdded.report_id == report_id))).scalar_one_or_none()
        links = (await self.db.execute(
            select(
                StudyReport.study_id,
                Study.short_name,
                StudyReportAdded.created_by,
                StudyReportAdded.date_created,
                StudyReportAdded.confirmed,
                StudyAdded.created_by.label("study_created_by"),
            )
            .join(Study, Study.id == StudyReport.study_id)
            .outerjoin(StudyReportAdded, StudyReportAdded.study_report_id == StudyReport.id)
            .outerjoin(StudyAdded, StudyAdded.study_id == StudyReport.study_id)
            .where(StudyReport.report_id == report_id)
        )).mappings().all()
        flags = (await self.db.execute(select(ReportFlag).where(ReportFlag.report_id == report_id))).scalars().all()

        tables = {}
        for table in self._update_tables():
            if table.info.get(ARCHIVE_KEY, True):
                rows = (await self.db.execute(select(table).where(table.c.report_id == report_id))).mappings().all()
                if rows:
                    tables[table.name] = [dict(row) for row in rows]

        return to_jsonable_python({
            "report": report.model_dump() if report else None,
            "update": added.model_dump(exclude={"report_id", "project_id"}) if added else None,
            "links": [dict(link) for link in links],
            "flags": [flag.model_dump(exclude={"report_id"}) for flag in flags],
            "tables": tables,
        })

    async def merge_links(self, report_id: int, study_ids: Sequence[int]) -> None:
        """Makes the links of the report to `study_ids` the links of the core database, which every scope sees (no
        study_report_added), along with the studies created in the update among them (no study_added), and removes
        its other links; studies created in the update that have no report left go as well."""
        dropped = list((await self.db.execute(
            select(StudyReport.study_id)
            .where(StudyReport.report_id == report_id)
            .where(StudyReport.study_id.not_in(study_ids))
        )).scalars().all())
        await self.db.execute(
            delete(StudyReport).where(StudyReport.report_id == report_id).where(StudyReport.study_id.not_in(study_ids))
        )
        await self.db.execute(
            delete(StudyReportAdded).where(
                StudyReportAdded.study_report_id.in_(
                    select(StudyReport.id).where(StudyReport.report_id == report_id)
                )
            )
        )
        await self.db.execute(delete(StudyAdded).where(StudyAdded.study_id.in_(study_ids)))
        await self.delete_orphaned_studies(dropped)

    async def delete_orphaned_studies(self, study_ids: Sequence[int]) -> None:
        """The studies created in an update among `study_ids` that have no report any more (see delete_project)."""
        if not study_ids:
            return
        has_report = exists().where(StudyReport.study_id == Study.id)
        created_here = exists().where(StudyAdded.study_id == Study.id)
        await self.db.execute(delete(Study).where(Study.id.in_(study_ids)).where(created_here).where(~has_report))

    async def get_selected_study_ids(self, report_id: int) -> List[int]:
        """The studies the reviewer selected for the report (a confirmed link of a scope)."""
        return list((await self.db.execute(
            select(StudyReport.study_id)
            .join(StudyReportAdded, StudyReportAdded.study_report_id == StudyReport.id)
            .where(StudyReport.report_id == report_id)
            .where(StudyReportAdded.confirmed.is_(True))
            .distinct()
        )).scalars().all())

    async def get_linked_study_ids(self, report_id: int) -> List[int]:
        return list((await self.db.execute(
            select(StudyReport.study_id).where(StudyReport.report_id == report_id).distinct()
        )).scalars().all())

    async def purge_update_data(self, report_id: int) -> None:
        """Removes the report from its update: its rows of the update tables, its flags and its row of the update
        (report_added), so that it is a report of the core database."""
        for table in self._update_tables():
            await self.db.execute(delete(table).where(table.c.report_id == report_id))
        await self.db.execute(delete(ReportFlag).where(ReportFlag.report_id == report_id))
        await self.db.execute(delete(ReportAdded).where(ReportAdded.report_id == report_id))

    def add(self, archive: ReportArchive) -> None:
        self.db.add(archive)

    @staticmethod
    def _update_tables() -> List[Table]:
        """The tables of update data (see UPDATE_DATA) whose rows belong to a report (a report_id column)."""
        return [
            table for table in SQLModel.metadata.sorted_tables
            if table.info.get(UPDATE_DATA_KEY) and "report_id" in table.c
        ]
