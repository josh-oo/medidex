import json
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Tuple

from pydantic import ValidationError

from ..database.models import Report as DbReport, Study as DbStudy, StudyDatabase
from ..database.repositories.database import DatabaseRepository
from ..database.repositories.study import DuplicateShortNameError, StudyRepository
from ..database.tagstorage import TAG_TABLES
from ..utils.dto import (
    Database,
    DatabaseExport,
    DatabasePayload,
    DatabaseReport,
    DatabaseStudy,
    DatabaseUpdate,
    StudyGraph,
    StudyPayload,
)
from ..utils.archive import DatabaseArchive
from ..utils.studyconfig import GRAPH_FIELD, INLINE_SEPARATOR, STUDY_CONFIG
from .report import DocumentService
from .vectorstore import VectorstoreService


class DatabaseNotFoundError(Exception):
    """No study database exists with the given id."""


class DatabaseIndexingError(Exception):
    """The reports of the database are still being added to the vectorstore (StudyDatabase.indexing)."""


class DatabaseImportError(ValueError):
    """The file is no database of the exchange format (see DatabaseExport in utils/dto.py)."""


class StudyDatabaseService:
    """The study databases: listing and creating them, and moving whole databases in and out as JSON
    (DatabaseExport)."""

    # How many problems of an import file are reported at once.
    MAX_IMPORT_ERRORS = 5
    # Reports per request when asking the vectorstore which of them it has.
    VECTORSTORE_CHUNK = 1000

    def __init__(self, database_repo: DatabaseRepository, study_repo: StudyRepository, vectorstore: VectorstoreService):
        self.database_repo = database_repo
        self.study_repo = study_repo
        self.vectorstore = vectorstore

    async def get_databases(self) -> List[Database]:
        """The databases with their numbers of studies and reports, and how many of the reports the vectorstore has
        (a database is still `indexing` while it lacks some)."""
        databases = await self.database_repo.get_databases()
        counts = await self.database_repo.get_counts()
        indexed = await self._indexed(await self.database_repo.get_report_ids_by_database())
        return [
            self._to_dto(database, *counts.get(database.id, (0, 0)), indexed.get(database.id, 0))
            for database in databases
        ]

    async def create_database(self, payload: DatabasePayload) -> Database:
        """A new, empty database."""
        try:
            database = await self.database_repo.add_database(payload.name, payload.description, payload.eligibilityCriteria)
            await self.database_repo.commit()
        except Exception:
            await self.database_repo.rollback()
            raise
        return self._to_dto(database)

    async def update_database(self, database_id: int, update: DatabaseUpdate) -> Database:
        """Renames the database or changes its description or eligibility criteria. Raises DatabaseNotFoundError."""
        database = await self.database_repo.get_database(database_id)
        if database is None:
            raise DatabaseNotFoundError(f"Database {database_id} not found")
        given = update.model_dump(exclude_unset=True)
        columns = {"name": "name", "description": "description", "eligibilityCriteria": "eligibility_criteria"}
        values = {
            columns[key]: (value or "").strip() or None
            for key, value in given.items()
            # Name and criteria are required: null leaves them as they are.
            if value is not None or key == "description"
        }
        if any(values.get(column) is None for column in ("name", "eligibility_criteria") if column in values):
            raise ValueError("Name and eligibility criteria cannot be empty")
        try:
            database = await self.database_repo.update_database(database, values)
            await self.database_repo.commit()
        except Exception:
            await self.database_repo.rollback()
            raise
        return await self._with_numbers(database)

    async def import_database(self, payload: DatabasePayload, archive: DatabaseArchive) -> Tuple[Database, List[int]]:
        """A new database with the studies, reports and PDFs of an exported one (`archive`, see utils/archive.py);
        `payload` names and describes it. All or nothing: raises DatabaseImportError, and imports nothing, if the file
        is no such database or misses a PDF it names. The PDFs are stored under the ids the reports get. Returns the database and
        the ids of its reports, which still have to be added to the vectorstore (index_reports; left to the caller,
        which knows how to run it in the background)."""
        document = self.parse(archive.document)
        studies = [self._payload(index, study) for index, study in enumerate(document.studies)]
        reports: Dict[Tuple[Any, ...], Tuple[DatabaseReport, List[int]]] = {}
        for study in document.studies:
            for report in study.reports:
                reports.setdefault(self._report_key(report), (report, []))
        pdfs = self._pdfs(archive, [report for report, _ in reports.values()])
        try:
            database = await self.database_repo.add_database(payload.name, payload.description, payload.eligibilityCriteria)
            for study, values in zip(document.studies, studies):
                new_study = await self.study_repo.import_study(values, database.id, study.createdAt)
                for category, names in study.tags.items():
                    await self.study_repo.add_study_tags(new_study.id, category, names)
                for report in study.reports:
                    reports[self._report_key(report)][1].append(new_study.id)
            saved: List[Tuple[DbReport, Optional[bytes]]] = []
            for report, study_ids in reports.values():
                saved.append((await self.database_repo.add_report(self._to_db_report(report), study_ids), pdfs.get(report.pdf or "")))
            await self.database_repo.commit()
        except DuplicateShortNameError as exc:
            await self.database_repo.rollback()
            raise DatabaseImportError(f"Two studies share a short name: {exc}") from exc
        except Exception:
            await self.database_repo.rollback()
            raise
        for report, pdf in saved:
            if pdf is not None:
                DocumentService.write_pdf(report.id, pdf)
        return self._to_dto(database, len(studies), len(saved)), [report.id for report, _ in saved]

    async def export_archive(self, database_id: int, target: BinaryIO) -> str:
        """Writes the archive of the database (its document and the PDFs of its reports, see utils/archive.py) to
        `target`; returns the name of the database. Raises DatabaseNotFoundError."""
        document, files = await self._export(database_id)
        DatabaseArchive.write(target, document.model_dump_json(indent=2).encode(), files.items())
        return document.name

    async def export_database(self, database_id: int) -> DatabaseExport:
        """The database as one JSON document (`database.json` of its archive, which names the PDFs without holding
        them). Raises DatabaseNotFoundError."""
        document, _ = await self._export(database_id)
        return document

    async def _export(self, database_id: int) -> Tuple[DatabaseExport, Dict[str, Path]]:
        """The document of the database and the PDF files it names, by their names in the archive."""
        database = await self.database_repo.get_database(database_id)
        if database is None:
            raise DatabaseNotFoundError(f"Database {database_id} not found")
        studies = await self.study_repo.get_database_studies(database_id)
        study_ids = [study.id for study in studies]
        graphs = await self.study_repo.get_graphs(studies)
        tags = {category: await self.study_repo.get_study_tags(category, study_ids) for category in TAG_TABLES}
        reports = await self.study_repo.get_study_reports_by_study_ids(study_ids) if study_ids else {}
        files: Dict[str, Path] = {}
        for found in reports.values():
            for report in found:
                path = Path(DocumentService.pdf_file_path(report.id))
                if path.is_file():
                    files[self._pdf_name(report)] = path
        document = DatabaseExport(
            name=database.name,
            description=database.description,
            eligibilityCriteria=database.eligibility_criteria,
            studies=[
                DatabaseStudy(
                    **self._fields(study),
                    graph=self._to_export_graph(graphs[study.id]),
                    tags={category: [tag.keyword for tag in by_study[study.id]] for category, by_study in tags.items() if by_study.get(study.id)},
                    reports=[
                        self._to_export_report(report, self._pdf_name(report) in files)
                        for report in sorted(reports.get(study.id, []), key=lambda report: report.id)
                    ],
                    createdAt=study.date_entered,
                )
                for study in studies
            ],
        )
        return document, files

    async def index_reports(self, report_ids: List[int]) -> None:
        """Adds the reports of an imported database to the vectorstore, so its studies are found for new reports. If
        this is interrupted, the sync on the next start (MaintenanceService.sync_vectorstore) adds the rest."""
        study_ids = await self.database_repo.get_report_study_ids(report_ids)
        study_databases = await self.database_repo.get_study_database_ids()
        for report in await self.database_repo.get_reports(report_ids):
            await self.vectorstore.add_study_report_to_vectorstore(report, study_ids[report.id], study_databases)

    async def get_database(self, database_id: int) -> Database:
        """One database with its numbers and whether it is still being indexed. Raises DatabaseNotFoundError."""
        database = await self.database_repo.get_database(database_id)
        if database is None:
            raise DatabaseNotFoundError(f"Database {database_id} not found")
        return await self._with_numbers(database)

    async def _indexed(self, report_ids: Dict[int, List[int]]) -> Dict[int, int]:
        """How many of the reports of each database have a point in the vectorstore, asked in chunks."""
        every = sorted({report_id for ids in report_ids.values() for report_id in ids})
        existing: set = set()
        for start in range(0, len(every), self.VECTORSTORE_CHUNK):
            existing.update(await self.vectorstore.reports_exist(every[start:start + self.VECTORSTORE_CHUNK]))
        return {database_id: sum(1 for report_id in ids if report_id in existing) for database_id, ids in report_ids.items()}

    async def _with_numbers(self, database: StudyDatabase) -> Database:
        counts = await self.database_repo.get_counts()
        report_ids = await self.database_repo.get_report_ids_by_database(database.id)
        indexed = await self._indexed(report_ids)
        studies, reports = counts.get(database.id, (0, 0))
        return self._to_dto(database, studies, reports, indexed.get(database.id, 0))

    @classmethod
    def parse(cls, content: bytes) -> DatabaseExport:
        try:
            data = json.loads(content)
        except (UnicodeDecodeError, ValueError) as exc:
            raise DatabaseImportError(f"The file is no JSON: {exc}") from exc
        if not isinstance(data, dict) or data.get("format") != "medidex-database":
            raise DatabaseImportError('The file is no Medidex database (a JSON object with "format": "medidex-database").')
        if data.get("version", 1) != 1:
            raise DatabaseImportError(f"Version {data.get('version')} of the database format is not supported (only 1).")
        try:
            document = DatabaseExport.model_validate(data)
        except ValidationError as exc:
            raise DatabaseImportError(cls._describe(exc)) from exc
        problems = []
        names = [study.shortName for study in document.studies]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            problems.append(f"Short names used by more than one study: {', '.join(duplicates[:cls.MAX_IMPORT_ERRORS])}")
        for index, study in enumerate(document.studies):
            unknown = set(study.tags) - set(TAG_TABLES)
            if unknown:
                problems.append(f"studies[{index}] ({study.shortName}): unknown tag categories {sorted(unknown)} (known: {', '.join(TAG_TABLES)})")
        if problems:
            raise DatabaseImportError("; ".join(problems[:cls.MAX_IMPORT_ERRORS]))
        return document

    @classmethod
    def _payload(cls, index: int, study: DatabaseStudy) -> Dict[str, Any]:
        """The values of a new study (as add_study takes them), checked like a study created by hand."""
        fields = study.model_dump(exclude={"graph", "tags", "reports", "createdAt"})
        graph = json.dumps(study.graph) if study.graph else None
        try:
            return StudyPayload(**fields, **{GRAPH_FIELD: graph}).model_dump()
        except ValidationError as exc:
            raise DatabaseImportError(f"studies[{index}] ({study.shortName}): {cls._describe(exc)}") from exc

    @classmethod
    def _describe(cls, exc: ValidationError) -> str:
        errors = exc.errors()
        described = [
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" if error["loc"] else error["msg"]
            for error in errors[:cls.MAX_IMPORT_ERRORS]
        ]
        more = f" (and {len(errors) - cls.MAX_IMPORT_ERRORS} more)" if len(errors) > cls.MAX_IMPORT_ERRORS else ""
        return "; ".join(described) + more

    @staticmethod
    def _fields(study: DbStudy) -> Dict[str, Any]:
        """The fields as the study holds them: not the values utils/derive.py would calculate from its graph, which an
        import would turn into values of its own."""
        values: Dict[str, Any] = {key: getattr(study, field.column) for key, field in STUDY_CONFIG.fields.items()}
        for key in STUDY_CONFIG.inline_categories:
            column = getattr(study, key)
            values[key] = [part.strip() for part in column.split(INLINE_SEPARATOR) if part.strip()] if column else []
        return values

    @staticmethod
    def _to_export_graph(graph: StudyGraph) -> Optional[Dict[str, Any]]:
        """The graph as a study takes it (utils/graph.py), with its tags by name."""
        if not graph.nodes:
            return None
        return {
            "nodes": [{"id": node.id, "kind": node.kind, "value": node.value} for node in graph.nodes],
            "edges": [edge.model_dump() for edge in graph.edges],
        }

    @staticmethod
    def _report_key(report: DatabaseReport) -> Tuple[Any, ...]:
        """A report listed under several studies is one report."""
        if report.doi:
            return ("doi", report.doi.strip().lower())
        return ("title", report.title.strip().lower(), report.year)

    @staticmethod
    def _pdf_name(report: DbReport) -> str:
        return f"{DatabaseArchive.PDF_FOLDER}/{report.id}.pdf"

    @classmethod
    def _pdfs(cls, archive: DatabaseArchive, reports: List[DatabaseReport]) -> Dict[str, bytes]:
        """The PDFs the reports name, by name; raises DatabaseImportError if the archive misses one."""
        pdfs: Dict[str, bytes] = {}
        missing = []
        for report in reports:
            if report.pdf and report.pdf not in pdfs:
                content = archive.pdf(report.pdf)
                if content is None:
                    missing.append(report.pdf)
                else:
                    pdfs[report.pdf] = content
        if missing:
            more = f" (and {len(missing) - cls.MAX_IMPORT_ERRORS} more)" if len(missing) > cls.MAX_IMPORT_ERRORS else ""
            raise DatabaseImportError(f"The archive misses the PDFs {', '.join(missing[:cls.MAX_IMPORT_ERRORS])}{more}")
        return pdfs

    @staticmethod
    def _to_db_report(report: DatabaseReport) -> DbReport:
        db_report = DbReport(
            title=report.title.replace("\n", " "),
            authors="//".join(author.strip() for author in report.authors if author.strip()),
            year=report.year,
            abstract=(report.abstract or "").replace("\n", " "),
            journal=report.journal,
            volume=report.volume,
            issue=report.issue,
            pages=report.pages,
            language=report.language,
            publisher=report.publisher,
            city=report.city,
            doi=report.doi,
            trial_registration_id=report.trialId,
        )
        if report.createdAt:
            db_report.date_entered = report.createdAt
        return db_report

    @classmethod
    def _to_export_report(cls, report: DbReport, has_pdf: bool) -> DatabaseReport:
        return DatabaseReport(
            title=report.title,
            year=report.year,
            authors=[author.strip() for author in (report.authors or "").split("//") if author.strip()],
            abstract=report.abstract or None,
            journal=report.journal,
            volume=report.volume,
            issue=report.issue,
            pages=report.pages,
            language=report.language,
            publisher=report.publisher,
            city=report.city,
            doi=report.doi,
            trialId=report.trial_registration_id,
            createdAt=report.date_entered,
            pdf=cls._pdf_name(report) if has_pdf else None,
        )

    @staticmethod
    def _to_dto(database: StudyDatabase, studies: int = 0, reports: int = 0, indexed: int = 0) -> Database:
        return Database(
            databaseId=database.id,
            name=database.name,
            description=database.description,
            eligibilityCriteria=database.eligibility_criteria,
            createdAt=database.date_created,
            numberStudies=studies,
            numberReports=reports,
            numberReportsIndexed=indexed,
            indexing=indexed < reports,
        )
