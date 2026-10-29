"""The study databases (see StudyDatabase in models.py) and the reports an imported database brings."""

from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from ..models import Report, Study, StudyDatabase, StudyReport


class DatabaseRepository:
    def __init__(self, db: AsyncSession, user_id: Optional[str]):
        self.db = db
        self.user_id = user_id

    async def commit(self):
        await self.db.commit()

    async def rollback(self):
        await self.db.rollback()

    async def get_databases(self) -> List[StudyDatabase]:
        """All study databases, the oldest (the default one) first."""
        stmt = select(StudyDatabase).order_by(StudyDatabase.date_created, StudyDatabase.id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_database(self, database_id: int) -> Optional[StudyDatabase]:
        return await self.db.get(StudyDatabase, database_id)

    async def get_counts(self) -> Dict[int, Tuple[int, int]]:
        """The number of studies and of their reports per database (every scope's, for the overview of the admin)."""
        studies = dict((await self.db.execute(select(Study.database_id, func.count(Study.id)).group_by(Study.database_id))).all())
        reports = dict((await self.db.execute(
            select(Study.database_id, func.count(func.distinct(StudyReport.report_id)))
            .join(StudyReport, StudyReport.study_id == Study.id)
            .group_by(Study.database_id)
        )).all())
        return {database_id: (count, reports.get(database_id, 0)) for database_id, count in studies.items()}

    async def add_database(self, name: str, description: Optional[str], eligibility_criteria: Optional[str]) -> StudyDatabase:
        """A new database; the database numbers it."""
        database = StudyDatabase(
            name=name.strip(),
            description=(description or "").strip() or None,
            eligibility_criteria=(eligibility_criteria or "").strip() or None,
            created_by=self.user_id,
        )
        self.db.add(database)
        await self.db.flush()
        return database

    async def update_database(self, database: StudyDatabase, values: Dict[str, Optional[str]]) -> StudyDatabase:
        """Changes the given columns of the database (name, description, eligibility_criteria)."""
        for column, value in values.items():
            setattr(database, column, value)
        self.db.add(database)
        await self.db.flush()
        return database

    async def get_report_ids_by_database(self, database_id: Optional[int] = None) -> Dict[int, List[int]]:
        """The reports of the studies of each database (or of one)."""
        stmt = (
            select(Study.database_id, StudyReport.report_id)
            .join(StudyReport, StudyReport.study_id == Study.id)
            .distinct()
        )
        if database_id is not None:
            stmt = stmt.where(Study.database_id == database_id)
        result: Dict[int, List[int]] = {}
        for database, report_id in (await self.db.execute(stmt)).all():
            result.setdefault(database, []).append(report_id)
        return result

    async def add_report(self, report: Report, study_ids: List[int]) -> Report:
        """Adds a report of an imported database linked to its studies, as the seed data is: no project, no record of
        who linked it (so the links count for every scope)."""
        self.db.add(report)
        await self.db.flush()
        self.db.add_all(StudyReport(study_id=study_id, report_id=report.id) for study_id in study_ids)
        await self.db.flush()
        return report

    async def get_reports(self, report_ids: List[int]) -> List[Report]:
        return list((await self.db.execute(select(Report).where(Report.id.in_(report_ids)))).scalars().all())

    async def get_study_database_ids(self) -> Dict[int, int]:
        """The database of every study, for the vectorstore (VectorstoreService.database_payload)."""
        return dict((await self.db.execute(select(Study.id, Study.database_id))).all())

    async def get_all_report_study_ids(self) -> Dict[int, List[int]]:
        """The studies of every report linked to one."""
        result: Dict[int, List[int]] = {}
        for report_id, study_id in (await self.db.execute(select(StudyReport.report_id, StudyReport.study_id))).all():
            result.setdefault(report_id, []).append(study_id)
        return result

    async def get_report_study_ids(self, report_ids: List[int]) -> Dict[int, List[int]]:
        """The studies of each report, for the vectorstore."""
        rows = (await self.db.execute(
            select(StudyReport.report_id, StudyReport.study_id).where(StudyReport.report_id.in_(report_ids))
        )).all()
        result: Dict[int, List[int]] = {report_id: [] for report_id in report_ids}
        for report_id, study_id in rows:
            result[report_id].append(study_id)
        return result
