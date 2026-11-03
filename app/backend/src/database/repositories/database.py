"""The study databases (see StudyDatabase in models.py) and the reports an imported database brings."""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, func, select

from ..models import UPDATE_DATA_KEY, Project, Report, Study, StudyDatabase, Link


class DatabaseRepository:
    # The reports of a database: those linked to its studies, which stay, and those its projects (its updates) brought
    # in, which go with the project unless they get merged.
    LINKED_REPORTS = "SELECT l.report_id FROM link l JOIN study s ON s.id = l.study_id WHERE s.database_id = :database_id"
    UPDATE_REPORTS = "SELECT ur.id FROM update_report ur JOIN project p ON p.id = ur.project_id WHERE p.database_id = :database_id"
    # The rows a database owns in the tables whose ids identify it, by table: the ids of its rows (`:database_id`).
    # Every other table of the schema (extensions included) belongs to a database through a foreign key to one of
    # these, the first of this order it has; tables without one (the tag vocabulary, settings, ...) are shared. The
    # rows of a table marked as UPDATE_DATA belong to its updates, those of every other table to the database itself.
    OWNED_IDS: Dict[str, str] = {
        "update_report": UPDATE_REPORTS,
        "update_study": "SELECT id FROM update_study WHERE database_id = :database_id",
        "project": "SELECT id FROM project WHERE database_id = :database_id",
        "study": "SELECT id FROM study WHERE database_id = :database_id",
        "report": LINKED_REPORTS,
        "study_database": "SELECT CAST(:database_id AS integer)",
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
        stmt = select(StudyDatabase).order_by(StudyDatabase.created_at, StudyDatabase.id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_database(self, database_id: int) -> Optional[StudyDatabase]:
        return await self.db.get(StudyDatabase, database_id)

    async def get_counts(self) -> Dict[int, Tuple[int, int]]:
        """The number of studies and of their reports per database, of the core database: what open updates add only
        counts once it is merged."""
        studies = dict((await self.db.execute(
            select(Study.database_id, func.count(Study.id)).group_by(Study.database_id)
        )).all())
        reports = dict((await self.db.execute(
            select(Study.database_id, func.count(func.distinct(Link.report_id)))
            .join(Link, Link.study_id == Study.id)
            .group_by(Study.database_id)
        )).all())
        return {database_id: (count, reports.get(database_id, 0)) for database_id, count in studies.items()}

    async def reserve_database_id(self) -> int:
        """An id no database has or gets (from the sequence of their ids), for a database added later (add_database)."""
        return (await self.db.execute(text("SELECT nextval(pg_get_serial_sequence('study_database', 'id'))"))).scalar_one()

    async def add_database(
        self, name: str, description: Optional[str], eligibility_criteria: List[Dict[str, Any]], database_id: Optional[int] = None
    ) -> StudyDatabase:
        """A new database; the database numbers it, unless it gets an id reserved for it (reserve_database_id)."""
        database = StudyDatabase(
            id=database_id,
            name=name.strip(),
            description=(description or "").strip() or None,
            eligibility_criteria=eligibility_criteria,
            created_by=self.user_id,
        )
        self.db.add(database)
        await self.db.flush()
        return database

    async def update_database(self, database: StudyDatabase, values: Dict[str, Any]) -> StudyDatabase:
        """Changes the given columns of the database (name, description, eligibility_criteria)."""
        for column, value in values.items():
            setattr(database, column, value)
        self.db.add(database)
        await self.db.flush()
        return database

    async def get_report_ids_by_database(self, database_id: Optional[int] = None) -> Dict[int, List[int]]:
        """The reports linked to the studies of each database (or of one)."""
        stmt = (
            select(Study.database_id, Link.report_id)
            .join(Link, Link.study_id == Study.id)
            .distinct()
        )
        if database_id is not None:
            stmt = stmt.where(Study.database_id == database_id)
        result: Dict[int, List[int]] = {}
        for database, report_id in (await self.db.execute(stmt)).all():
            result.setdefault(database, []).append(report_id)
        return result

    async def get_report_ids(self, database_id: int) -> Tuple[List[int], List[int]]:
        """The reports linked to the studies of the database, and those its open updates hold (linked or not)."""
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
            column, ids = owner
            own_size, all_size, on_disk = (await self.db.execute(
                text(
                    f"SELECT coalesce(sum(pg_column_size(t.*)) FILTER (WHERE t.{quote(column)} IN ({ids})), 0),"
                    " coalesce(sum(pg_column_size(t.*)), 0), pg_total_relation_size(CAST(:table AS regclass))"
                    f" FROM {quote(table.name)} AS t"
                ),
                {"database_id": database_id, "table": quote(table.name)},
            )).one()
            if all_size:
                share = round(on_disk * own_size / all_size)
                if table.info.get(UPDATE_DATA_KEY):
                    updates_bytes += share
                else:
                    database_bytes += share
        return database_bytes, updates_bytes

    @classmethod
    def _owner(cls, table: Table) -> Optional[Tuple[str, str]]:
        """Which rows of `table` belong to a database, as (column, its ids of the database, see OWNED_IDS): its id for a
        table of OWNED_IDS, else its foreign key to the first of them it references; None for a shared table."""
        if table.name in cls.OWNED_IDS:
            return "id", cls.OWNED_IDS[table.name]
        keys = {key.column.table.name: key.parent.name for key in table.foreign_keys}
        owner = next((owner for owner in cls.OWNED_IDS if owner in keys), None)
        return (keys[owner], cls.OWNED_IDS[owner]) if owner is not None else None

    async def add_report(self, report: Report, study_ids: List[int]) -> Report:
        """Adds a report of an imported database to the core database, linked to its studies."""
        self.db.add(report)
        await self.db.flush()
        self.db.add_all(Link(study_id=study_id, report_id=report.id) for study_id in study_ids)
        await self.db.flush()
        return report

    async def get_reports(self, report_ids: List[int]) -> List[Report]:
        return list((await self.db.execute(select(Report).where(Report.id.in_(report_ids)))).scalars().all())

    async def get_study_database_ids(self) -> Dict[int, int]:
        """The database of every study, for the vectorstore (VectorstoreService.database_payload)."""
        return dict((await self.db.execute(select(Study.id, Study.database_id))).all())

    async def get_all_report_study_ids(self) -> Dict[int, List[int]]:
        """The studies of every report of the core database linked to one."""
        result: Dict[int, List[int]] = {}
        for report_id, study_id in (await self.db.execute(select(Link.report_id, Link.study_id))).all():
            result.setdefault(report_id, []).append(study_id)
        return result

    async def get_report_study_ids(self, report_ids: List[int]) -> Dict[int, List[int]]:
        """The studies of each report, for the vectorstore."""
        rows = (await self.db.execute(
            select(Link.report_id, Link.study_id).where(Link.report_id.in_(report_ids))
        )).all()
        result: Dict[int, List[int]] = {report_id: [] for report_id in report_ids}
        for report_id, study_id in rows:
            result[report_id].append(study_id)
        return result
