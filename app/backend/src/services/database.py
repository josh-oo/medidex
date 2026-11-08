import asyncio
import datetime
import json
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Tuple

from pydantic import ValidationError

from ..database.models import Report as DbReport, Study as DbStudy, StudyDatabase
from ..database.repositories.database import DatabaseRepository
from ..database.repositories.study import DuplicateShortNameError, StudyRepository
from ..utils.dto import (
    Database,
    DatabaseExport,
    DatabasePayload,
    DatabaseReport,
    DatabaseStorage,
    StorageExtra,
    StorageUsage,
    DatabaseStudy,
    DatabaseStage,
    DatabaseStatus,
    DatabaseUpdate,
    StudyGraph,
    StudyPayload,
    study_values,
)
from ..utils.archive import DatabaseArchive
from ..utils.eligibility import EligibilityCriteria, EligibilityCriterion
from ..utils.pdfs import PdfFiles
from ..utils.storage import update_storage_registry
from ..utils.studyconfig import GRAPH_FIELD
from ..utils.tagconfig import TAG_CATEGORIES
from .embedding import EmbeddingService
from .pubsub import DatabaseStatusService
from .report import DocumentService
from .vectorstore import VectorstoreService


class DatabaseNotFoundError(Exception):
    """No study database exists with the given id."""


class DatabaseIndexingError(Exception):
    """The database is still being imported, or its reports are still being added to the vectorstore (Database.importing
    and indexing)."""


class DatabaseImportError(ValueError):
    """The file is no database of the exchange format (see DatabaseExport in utils/dto.py)."""


class StudyDatabaseService:
    """The study databases: listing and creating them, and moving whole databases in and out as JSON
    (DatabaseExport)."""

    # How many problems of an import file are reported at once.
    MAX_IMPORT_ERRORS = 5
    # Reports per request when asking the vectorstore which of them it has.
    VECTORSTORE_CHUNK = 1000

    def __init__(
        self,
        database_repo: DatabaseRepository,
        study_repo: StudyRepository,
        vectorstore: VectorstoreService,
        status_service: DatabaseStatusService,
    ):
        self.database_repo = database_repo
        self.study_repo = study_repo
        self.vectorstore = vectorstore
        self.status_service = status_service

    async def get_databases(self) -> List[Database]:
        """The databases with their numbers of studies and reports, and how many of the reports the vectorstore has
        (a database is still `indexing` while it lacks some, with why if that stopped), and then those being imported
        (`importing`)."""
        databases = await self.database_repo.get_databases()
        counts = await self.database_repo.get_counts()
        indexed = await self._indexed(await self.database_repo.get_report_ids_by_database())
        imports = {database.databaseId: database for database in await self.status_service.imports()}
        return [
            imports.pop(database.id, None) or await self._with_indexing_error(
                self._to_dto(database, *counts.get(database.id, (0, 0)), indexed.get(database.id, 0))
            )
            for database in databases
        ] + sorted(imports.values(), key=lambda database: database.databaseId)

    async def create_database(self, payload: DatabasePayload) -> Database:
        """A new, empty database."""
        try:
            database = await self.database_repo.add_database(payload.name, payload.description, self._criteria(payload.eligibilityCriteria))
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
        columns = {"name": "name", "description": "description"}
        values: Dict[str, Any] = {
            columns[key]: (value or "").strip() or None
            for key, value in given.items()
            # The name is required: null leaves it as it is.
            if key in columns and (value is not None or key == "description")
        }
        if "name" in values and values["name"] is None:
            raise ValueError("The name cannot be empty")
        if update.eligibilityCriteria is not None:
            values["eligibility_criteria"] = self._criteria(update.eligibilityCriteria)
        try:
            database = await self.database_repo.update_database(database, values)
            await self.database_repo.commit()
        except Exception:
            await self.database_repo.rollback()
            raise
        return await self._with_numbers(database)

    async def start_import(self, payload: DatabasePayload) -> Database:
        """The database an import (import_database) will make, under an id reserved for it, listed as `importing`
        until the import ends (end_import)."""
        database = Database(
            databaseId=await self.database_repo.reserve_database_id(),
            importing=True,
            name=payload.name.strip(),
            description=(payload.description or "").strip() or None,
            eligibilityCriteria=EligibilityCriteria.validate(payload.eligibilityCriteria),
            createdAt=datetime.datetime.now(datetime.timezone.utc),
        )
        await self.status_service.start_import(database)
        return database

    async def import_database(self, database_id: int, payload: DatabasePayload, archive: DatabaseArchive) -> List[int]:
        """The database of start_import with the studies, reports and PDFs of an exported one (`archive`, see
        utils/archive.py); `payload` names and describes it. All or nothing: raises DatabaseImportError, and imports
        nothing, if the file is no such database or misses a PDF it names. The PDFs are stored under the ids the
        reports get. Its progress is published (DatabaseStatusService). Returns the ids of its reports, which still
        have to be added to the vectorstore (index_reports)."""
        document = self.parse(archive.document)
        studies = [self._payload(index, study) for index, study in enumerate(document.studies)]
        reports: Dict[Tuple[Any, ...], Tuple[DatabaseReport, List[int]]] = {}
        for study in document.studies:
            for report in study.reports:
                reports.setdefault(self._report_key(report), (report, []))
        self._check_pdfs(archive, [report for report, _ in reports.values()])
        try:
            await self.database_repo.add_database(payload.name, payload.description, self._criteria(payload.eligibilityCriteria), database_id)
            await self.study_repo.import_tags(document.tags)
            progress = await self.status_service.progress(database_id, DatabaseStage.importing, "studies", len(studies)).start()
            for study, values in zip(document.studies, studies):
                new_study = await self.study_repo.import_study(values, study.tags, database_id, self._utc(study.createdAt))
                for report in study.reports:
                    study_ids = reports[self._report_key(report)][1]
                    # A study lists a report once, however many of its entries are that report.
                    if new_study.id not in study_ids:
                        study_ids.append(new_study.id)
                await progress.advance()
            await self._check_vocabulary(database_id, document)
            progress = await self.status_service.progress(database_id, DatabaseStage.importing, "reports", len(reports)).start()
            saved: List[Tuple[DbReport, Optional[str]]] = []
            for report, study_ids in reports.values():
                saved.append((await self.database_repo.add_report(self._to_db_report(report), study_ids), report.pdf))
                await progress.advance()
            await self.database_repo.commit()
        except DuplicateShortNameError as exc:
            await self.database_repo.rollback()
            raise DatabaseImportError(f"Two studies share a short name: {exc}") from exc
        except Exception:
            await self.database_repo.rollback()
            raise
        # One PDF at a time, read from the archive as it is stored: an archive of a large database does not fit into
        # memory.
        pdfs = [(report, name) for report, name in saved if name]
        progress = await self.status_service.progress(database_id, DatabaseStage.importing, "pdfs", len(pdfs)).start()
        for report, name in pdfs:
            await asyncio.to_thread(self._store_pdf, archive, name, report.id)
            await progress.advance()
        return [report.id for report, _ in saved]

    async def _check_vocabulary(self, database_id: int, document: DatabaseExport) -> None:
        """Raises DatabaseImportError if the imported studies have a tag the vocabulary of the file does not list (by
        their tags, their graphs or a field written into them, such as their countries)."""
        listed = {(tag.category, tag.name.lower()) for tag in document.tags}
        study_ids = [study.id for study in await self.study_repo.get_database_studies(database_id)]
        unlisted = sorted({
            f"{tag.category}: {tag.name}" for tag in await self.study_repo.get_tag_vocabulary(study_ids)
            if (tag.category, tag.name.lower()) not in listed
        })
        if unlisted:
            raise DatabaseImportError(f"Tags the studies name are not listed in `tags`: {', '.join(unlisted[:self.MAX_IMPORT_ERRORS])}")

    async def end_import(self, database_id: int, error: Optional[str] = None) -> None:
        """Ends the import of the database: it is listed as it is from now on, or, if the import failed with `error`,
        not at all."""
        await self.status_service.end_import(database_id)
        if error is not None:
            await self.status_service.publish(DatabaseStatus(databaseId=database_id, stage=DatabaseStage.failed, message=error))

    async def get_status(self, database_id: int) -> DatabaseStatus:
        """Where the database is now: imported (the last status published for it), indexed, ready, failed while it was
        indexed (lately, and not started again), or not there because its import failed (lately). Raises
        DatabaseNotFoundError."""
        status = await self.status_service.current(database_id)
        if status is not None and status.stage == DatabaseStage.importing:
            return status
        try:
            database = await self.get_database(database_id)
        except DatabaseNotFoundError:
            if status is not None and status.stage == DatabaseStage.failed:
                return status
            raise
        if database.indexing and database.indexingError is not None:
            return DatabaseStatus(databaseId=database_id, stage=DatabaseStage.failed, message=database.indexingError)
        if database.indexing:
            return DatabaseStatus(databaseId=database_id, stage=DatabaseStage.indexing, done=database.numberReportsIndexed, total=database.numberReports)
        return DatabaseStatus(databaseId=database_id, stage=DatabaseStage.ready)

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
        tags = {category: await self.study_repo.get_study_tags(category, study_ids) for category in TAG_CATEGORIES}
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
            eligibilityCriteria=EligibilityCriteria.read(database.eligibility_criteria),
            tags=await self.study_repo.get_tag_vocabulary(study_ids),
            studies=[
                DatabaseStudy(
                    **self._fields(study),
                    graph=self._to_export_graph(graphs[study.id]),
                    tags={category: [tag.keyword for tag in by_study[study.id]] for category, by_study in tags.items() if by_study.get(study.id)},
                    reports=[
                        self._to_export_report(report, self._pdf_name(report) in files)
                        for report in sorted(reports.get(study.id, []), key=lambda report: report.id)
                    ],
                    createdAt=study.created_at,
                )
                for study in studies
            ],
        )
        return document, files

    async def index_reports(self, database_id: int, report_ids: List[int]) -> None:
        """Adds the reports of an imported database to the vectorstore, so its studies are found for new reports, and
        publishes how far it is (DatabaseStatusService). If this is interrupted, the sync on the next start
        (MaintenanceService.sync_vectorstore) adds the rest. If it fails (e.g. the embedding API is not reachable), that
        is published with why and the error raised."""
        try:
            study_ids = await self.database_repo.get_report_study_ids(report_ids)
            study_databases = await self.database_repo.get_study_database_ids()
            progress = await self.status_service.progress(database_id, DatabaseStage.indexing, None, len(report_ids)).start()
            reports = await self.database_repo.get_reports(report_ids)

            async def index(report):
                await self.vectorstore.add_study_report_to_vectorstore(report, study_ids, study_databases)
                await progress.advance()

            await EmbeddingService.for_each(reports, index)
        except Exception as exc:
            await self.status_service.fail_indexing(database_id, exc)
            raise
        await self.status_service.publish(DatabaseStatus(databaseId=database_id, stage=DatabaseStage.ready))

    async def get_database(self, database_id: int) -> Database:
        """One database with its numbers and whether it is still being imported or indexed. Raises
        DatabaseNotFoundError."""
        for database in await self.status_service.imports():
            if database.databaseId == database_id:
                return database
        database = await self.database_repo.get_database(database_id)
        if database is None:
            raise DatabaseNotFoundError(f"Database {database_id} not found")
        return await self._with_numbers(database)

    async def get_storage(self, database_id: int) -> DatabaseStorage:
        """What the database takes in storage, split into what stays (`database`) and what only serves its updates
        (`updates`, see DatabaseStorage). Raises DatabaseNotFoundError."""
        if await self.database_repo.get_database(database_id) is None:
            raise DatabaseNotFoundError(f"Database {database_id} not found")
        linked, in_updates = await self.database_repo.get_report_ids(database_id)
        unlinked = sorted(set(in_updates) - set(linked))
        database_bytes, updates_bytes = await self.database_repo.get_table_storage(database_id)
        extras = [
            StorageExtra(label=storage.label, bytes=await storage.measure(in_updates))
            for storage in update_storage_registry.all()
        ]
        return DatabaseStorage(
            databaseId=database_id,
            numberReports=len(linked),
            numberUpdates=await self.database_repo.count_projects(database_id),
            numberReportsInUpdates=len(in_updates),
            database=await self._usage(database_bytes, linked),
            updates=await self._usage(updates_bytes, unlinked, [extra for extra in extras if extra.bytes]),
        )

    async def _usage(self, data_bytes: int, report_ids: List[int], extras: Optional[List[StorageExtra]] = None) -> StorageUsage:
        """The storage of a part of a database: its rows (`data_bytes`) and the search index and PDFs of its reports."""
        _, search_bytes = await self.vectorstore.usage(report_ids)
        files, pdf_bytes = await asyncio.to_thread(PdfFiles.usage, report_ids)
        return StorageUsage(
            dataBytes=data_bytes,
            searchIndexBytes=search_bytes,
            pdfBytes=pdf_bytes,
            pdfFiles=files,
            extras=extras or [],
        )

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
        return await self._with_indexing_error(self._to_dto(database, studies, reports, indexed.get(database.id, 0)))

    async def _with_indexing_error(self, database: Database) -> Database:
        """The database with why its indexing stopped, if it is still `indexing` (its status is only asked then)."""
        if database.indexing:
            database.indexingError = await self.status_service.indexing_error(database.databaseId)
        return database

    @classmethod
    def parse(cls, content: bytes) -> DatabaseExport:
        try:
            data = json.loads(content)
        except (UnicodeDecodeError, ValueError) as exc:
            raise DatabaseImportError(f"The file is no JSON: {exc}") from exc
        if not isinstance(data, dict) or data.get("format") != "medidex-database":
            raise DatabaseImportError('The file is no Medidex database (a JSON object with "format": "medidex-database").')
        if data.get("version") != 2:
            raise DatabaseImportError(f"Version {data.get('version')} of the database format is not supported (only 2).")
        try:
            document = DatabaseExport.model_validate(data)
        except ValidationError as exc:
            raise DatabaseImportError(cls.describe(exc)) from exc
        problems = []
        names = [study.shortName for study in document.studies]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            problems.append(f"Short names used by more than one study: {', '.join(duplicates[:cls.MAX_IMPORT_ERRORS])}")
        for index, tag in enumerate(document.tags):
            if tag.category not in TAG_CATEGORIES:
                problems.append(f"tags[{index}] ({tag.name}): unknown tag category {tag.category} (known: {', '.join(TAG_CATEGORIES)})")
        for index, study in enumerate(document.studies):
            unknown = set(study.tags) - set(TAG_CATEGORIES)
            if unknown:
                problems.append(f"studies[{index}] ({study.shortName}): unknown tag categories {sorted(unknown)} (known: {', '.join(TAG_CATEGORIES)})")
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
            raise DatabaseImportError(f"studies[{index}] ({study.shortName}): {cls.describe(exc)}") from exc

    @classmethod
    def describe(cls, exc: ValidationError) -> str:
        """What is wrong with a file that is not as its format says, the first few problems."""
        errors = exc.errors()
        described = [
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" if error["loc"] else error["msg"]
            for error in errors[:cls.MAX_IMPORT_ERRORS]
        ]
        more = f" (and {len(errors) - cls.MAX_IMPORT_ERRORS} more)" if len(errors) > cls.MAX_IMPORT_ERRORS else ""
        return "; ".join(described) + more

    @staticmethod
    def _fields(study: DbStudy) -> Dict[str, Any]:
        """The fields of the study; those derived from its graph are views of it, which an import writes back unchanged."""
        return study_values(study)

    @staticmethod
    def _utc(value: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        """A time of the exchange format, which is UTC if it names no time zone."""
        return value.replace(tzinfo=datetime.timezone.utc) if value is not None and value.tzinfo is None else value

    @staticmethod
    def _to_export_graph(graph: StudyGraph) -> Optional[Dict[str, Any]]:
        """The graph as a study takes it (utils/graph.py), with its tags by name."""
        if not graph.nodes:
            return None
        return {
            "nodes": [
                {"id": node.id, "kind": node.kind, "value": node.value, **({"text": node.text} if node.text else {}), **({"match": node.match} if node.match else {})}
                for node in graph.nodes
            ],
            "edges": [edge.model_dump() for edge in graph.edges],
        }

    @staticmethod
    def _report_key(report: DatabaseReport) -> Tuple[Any, ...]:
        """A report listed under several studies is one report: the reports of an id, else of a DOI, else of a title
        and year."""
        if report.id:
            return ("id", report.id.strip())
        if report.doi:
            return ("doi", report.doi.strip().lower())
        return ("title", report.title.strip().lower(), report.year)

    @staticmethod
    def _pdf_name(report: DbReport) -> str:
        return f"{DatabaseArchive.PDF_FOLDER}/{report.id}.pdf"

    @classmethod
    def _check_pdfs(cls, archive: DatabaseArchive, reports: List[DatabaseReport]) -> None:
        """Raises DatabaseImportError if the archive misses a PDF the reports name."""
        missing = sorted({report.pdf for report in reports if report.pdf and not archive.has_pdf(report.pdf)})
        if missing:
            more = f" (and {len(missing) - cls.MAX_IMPORT_ERRORS} more)" if len(missing) > cls.MAX_IMPORT_ERRORS else ""
            raise DatabaseImportError(f"The archive misses the PDFs {', '.join(missing[:cls.MAX_IMPORT_ERRORS])}{more}")

    @staticmethod
    def _store_pdf(archive: DatabaseArchive, name: str, report_id: int) -> None:
        content = archive.pdf(name)
        if content is not None:
            DocumentService.write_pdf(report_id, content)

    @staticmethod
    def _to_db_report(report: DatabaseReport) -> DbReport:
        db_report = DbReport(
            title=report.title.replace("\n", " "),
            authors=[author.strip() for author in report.authors if author.strip()],
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
            db_report.created_at = StudyDatabaseService._utc(report.createdAt)
        return db_report

    @classmethod
    def _to_export_report(cls, report: DbReport, has_pdf: bool) -> DatabaseReport:
        return DatabaseReport(
            id=str(report.id),
            title=report.title,
            year=report.year,
            authors=report.authors,
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
            createdAt=report.created_at,
            pdf=cls._pdf_name(report) if has_pdf else None,
        )

    @staticmethod
    def _criteria(criteria: List[EligibilityCriterion]) -> List[Dict[str, Any]]:
        """The criteria as they are stored; raises ValueError for none or a repeated id."""
        return [criterion.model_dump() for criterion in EligibilityCriteria.validate(criteria)]

    @staticmethod
    def _to_dto(database: StudyDatabase, studies: int = 0, reports: int = 0, indexed: int = 0) -> Database:
        return Database(
            databaseId=database.id,
            name=database.name,
            description=database.description,
            eligibilityCriteria=EligibilityCriteria.read(database.eligibility_criteria),
            createdAt=database.created_at,
            numberStudies=studies,
            numberReports=reports,
            numberReportsIndexed=indexed,
            indexing=indexed < reports,
        )
