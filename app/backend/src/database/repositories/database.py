"""The study databases (see StudyDatabase in models.py) and the reports an imported database brings."""

from typing import Dict, List, Optional, Tuple

from sqlalchemy import Table, exists, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, func, select

from ..models import UPDATE_DATA_KEY, Project, Report, Study, StudyAdded, StudyDatabase, StudyReport, StudyReportAdded


class DatabaseRepository:
    # The core of a database (`:database_id`): its studies but those created in an update that is not merged yet
    # (they have a study_added record until then), and the links of no scope (no study_report_added record: imported,
    # of the seed, or merged from an update, see UpdateMergeService). The links of the scopes belong to the updates.
    CORE_STUDIES = "SELECT id FROM study WHERE database_id = :database_id AND id NOT IN (SELECT study_id FROM study_added)"
    UPDATE_STUDIES = "SELECT id FROM study WHERE database_id = :database_id AND id IN (SELECT study_id FROM study_added)"
    CORE_LINKS = (
        "SELECT sr.id FROM study_report sr JOIN study s ON s.id = sr.study_id WHERE s.database_id = :database_id"
        " AND NOT EXISTS (SELECT 1 FROM study_report_added sra WHERE sra.study_report_id = sr.id)"
    )
    UPDATE_LINKS = (
        "SELECT sr.id FROM study_report sr JOIN study s ON s.id = sr.study_id WHERE s.database_id = :database_id"
        " AND EXISTS (SELECT 1 FROM study_report_added sra WHERE sra.study_report_id = sr.id)"
    )
    # The reports of a database: those of its core links, which stay, and those its projects (its updates) brought
    # in, which go with the project unless they get merged.
    LINKED_REPORTS = f"SELECT report_id FROM study_report WHERE id IN ({CORE_LINKS})"
    UPDATE_REPORTS = "SELECT ra.report_id FROM report_added ra JOIN project p ON p.id = ra.project_id WHERE p.database_id = :database_id"
    # The rows a database owns, by table: the ids that belong to the database itself and those that belong to its
    # updates (None: none). Every other table of the schema (extensions included) belongs to a database through a
    # foreign key to one of these, the first of this order it has; tables without one (the tag vocabulary,
    # settings, ...) are shared. A table marked as UPDATE_DATA belongs to the updates only.
    OWNED_IDS: Dict[str, Tuple[Optional[str], Optional[str]]] = {
        "study_database": ("SELECT CAST(:database_id AS integer)", None),
        "study": (CORE_STUDIES, UPDATE_STUDIES),
        "project": (None, "SELECT id FROM project WHERE database_id = :database_id"),
        "study_report": (CORE_LINKS, UPDATE_LINKS),
        "report": (LINKED_REPORTS, f"{UPDATE_REPORTS} EXCEPT {LINKED_REPORTS}"),
    }

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
        """The number of studies and of their reports per database: its core (see CORE_STUDIES and CORE_LINKS), without
        what open updates add until it is merged."""
        studies = dict((await self.db.execute(
            select(Study.database_id, func.count(Study.id)).where(self._core_study()).group_by(Study.database_id)
        )).all())
        reports = dict((await self.db.execute(
            select(Study.database_id, func.count(func.distinct(StudyReport.report_id)))
            .join(StudyReport, StudyReport.study_id == Study.id)
            .where(self._core_link())
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

    @staticmethod
    def _core_study():
        return ~exists().where(StudyAdded.study_id == Study.id)

    @staticmethod
    def _core_link():
        return ~exists().where(StudyReportAdded.study_report_id == StudyReport.id)

    async def get_report_ids_by_database(self, database_id: Optional[int] = None) -> Dict[int, List[int]]:
        """The reports of the core links of each database (or of one)."""
        stmt = (
            select(Study.database_id, StudyReport.report_id)
            .join(StudyReport, StudyReport.study_id == Study.id)
            .where(self._core_link())
            .distinct()
        )
        if database_id is not None:
            stmt = stmt.where(Study.database_id == database_id)
        result: Dict[int, List[int]] = {}
        for database, report_id in (await self.db.execute(stmt)).all():
            result.setdefault(database, []).append(report_id)
        return result

    async def get_report_ids(self, database_id: int) -> Tuple[List[int], List[int]]:
        """The reports of the core links of the database, and those its open updates hold (linked or not)."""
        params = {"database_id": database_id}
        linked = (await self.db.execute(text(self.LINKED_REPORTS), params)).scalars().all()
        in_updates = (await self.db.execute(text(self.UPDATE_REPORTS), params)).scalars().all()
        return sorted(set(linked)), sorted(set(in_updates))

    async def count_projects(self, database_id: int) -> int:
        return (await self.db.execute(select(func.count(Project.id)).where(Project.database_id == database_id))).scalar_one()

    async def get_table_storage(self, database_id: int) -> Tuple[int, int]:
        """The bytes the rows of the database take in the tables of the schema, as (database, updates): of every table
        the share on disk (indexes and TOAST included) its rows take, by the size of the rows."""
        quote = self.db.get_bind().dialect.identifier_preparer.quote
        database_bytes = updates_bytes = 0
        for table in SQLModel.metadata.sorted_tables:
            owner = self._owner(table)
            if owner is None:
                continue
            column, (database_ids, update_ids) = owner
            own = [
                f"coalesce(sum(pg_column_size(t.*)) FILTER (WHERE t.{quote(column)} IN ({ids})), 0)" if ids else "0"
                for ids in (database_ids, update_ids)
            ]
            database_size, updates_size, all_size, on_disk = (await self.db.execute(
                text(
                    f"SELECT {own[0]}, {own[1]}, coalesce(sum(pg_column_size(t.*)), 0),"
                    " pg_total_relation_size(CAST(:table AS regclass))"
                    f" FROM {quote(table.name)} AS t"
                ),
                {"database_id": database_id, "table": quote(table.name)},
            )).one()
            if all_size:
                database_bytes += round(on_disk * database_size / all_size)
                updates_bytes += round(on_disk * updates_size / all_size)
        return database_bytes, updates_bytes

    @classmethod
    def _owner(cls, table: Table) -> Optional[Tuple[str, Tuple[Optional[str], Optional[str]]]]:
        """Which rows of `table` belong to a database, as (column, its ids of the database and of its updates, see
        OWNED_IDS): its id for a table of OWNED_IDS, else its foreign key to the first of them it references; None for a
        shared table."""
        if table.name in cls.OWNED_IDS:
            return "id", cls.OWNED_IDS[table.name]
        keys = {key.column.table.name: key.parent.name for key in table.foreign_keys}
        owner = next((owner for owner in cls.OWNED_IDS if owner in keys), None)
        if owner is None:
            return None
        database_ids, update_ids = cls.OWNED_IDS[owner]
        if table.info.get(UPDATE_DATA_KEY):
            return keys[owner], (None, cls.UPDATE_REPORTS if owner == "report" else database_ids or update_ids)
        return keys[owner], (database_ids, update_ids)

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
