import asyncio
import hashlib
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from ..database.models import Project as DbProject, Report as DbReport
from ..database.repositories.project import ProjectRepository
from ..database.repositories.report import ReportRepository
from ..utils.dto import (
    FilterMode,
    Page,
    ReportIntake,
    Assignee,
    Project,
    ReportCuration,
    Task,
    filter_mode_to_bool,
    matches_filter,
    reports_to_dto,
    studies_to_preview_dto,
)
from ..utils.pagination import decode_cursor, encode_cursor
from ..utils.ris_parser import UploadedFile, parse_file
from ..utils.trial_registration_id import extract_trial_id
from .authorization import ProjectAccessDeniedError
from .pubsub import ProjectPubSubService
from .vectorstore import VectorstoreService


class ProjectNotFoundError(Exception):
    """No project exists with the given id."""


class ProjectAssigneeAlreadyExistsError(Exception):
    """The user is already assigned to this project."""


class ProjectAssigneeNotFoundError(Exception):
    """The user isn't assigned to this project."""


class ProjectResourceService:
    """Project overview/progress logic."""

    def __init__(
        self,
        project_repo: ProjectRepository,
        report_repo: ReportRepository,
        vectorstore_service: VectorstoreService,
        pubsub_service: ProjectPubSubService,
    ):
        self.project_repo = project_repo
        self.report_repo = report_repo
        self.vectorstore_service = vectorstore_service
        self.pubsub_service = pubsub_service

    async def get_vectorized_and_ready_report_ids(self, project_id: str) -> Tuple[Set[int], Set[int], Set[int]]:
        report_ids = await self.project_repo.get_project_associated_report_ids(project_id)
        if not report_ids:
            return set(), set(), set()

        # report.embedded/report.has_pdf are denormalized mirrors of Qdrant/filesystem
        # state (see models.py) kept in sync by the app itself, so this is now a plain SQL
        # read instead of a live Qdrant retrieve + a filesystem stat per report.
        embedded_reports, pdf_ready_reports = await self.report_repo.get_readiness_sets(report_ids)
        # Reports still being postprocessed (e.g. metadata extraction) aren't ready yet either.
        pending_postprocessing = await self.report_repo.get_postprocessing_pending(report_ids)
        ready_reports = (embedded_reports & pdf_ready_reports) - pending_postprocessing
        return embedded_reports, pdf_ready_reports, ready_reports

    async def get_project_stats(self, project: DbProject) -> Project:
        """For callers that already have the project row (e.g. get_all_project_stats,
        which just fetched every project).
        """
        report_ids = await self.project_repo.get_project_associated_report_ids(project.id)
        auto_searched_pdf_count = await self.project_repo.get_auto_searched_pdf_count_for_project(project.id)
        confirmed_report_count = await self.project_repo.get_confirmed_report_count_for_project(project.id)

        embedded_reports, reports_with_pdf, ready_reports = await self.get_vectorized_and_ready_report_ids(project.id)

        postprocessing_total, postprocessing_finished = await self.report_repo.get_postprocessing_progress(report_ids)

        assignees = await self.project_repo.get_project_assignees(project.id)
        assignee_ids = [user_id for user_id, _ in assignees if user_id]

        ready_for_review_count = 0
        if assignee_ids:
            completion_map = await self.project_repo.get_report_completion_by_users(project.id)
            assignee_set = set(assignee_ids)
            ready_for_review_count = sum(
                1 for report_id in report_ids
                if assignee_set.issubset(completion_map.get(report_id, set()))
            )

        assignee_payload = [
            Assignee(userId=user_id, numberReportsLinked=linked_count)
            for user_id, linked_count in assignees
        ]

        return Project(
            projectId=project.id,
            name=project.description,
            createdAt=project.date_created,
            numberReportsTotal=len(report_ids),
            numberReportsPreProcessed=len(embedded_reports),
            numberReportsReadyForProcessing=len(ready_reports),
            numberReportsWithPdf=len(reports_with_pdf),
            numberReportsReadyForReview=ready_for_review_count,
            numberReportsAutoSearchedPdf=auto_searched_pdf_count,
            numberReportsConfirmed=confirmed_report_count,
            numberReportsPostprocessing=postprocessing_total,
            numberReportsPostprocessed=postprocessing_finished,
            owner=project.uploaded_by,
            assignees=assignee_payload,
        )

    async def get_all_project_stats(self) -> List[Project]:
        projects = await self.project_repo.get_all_projects()
        return await asyncio.gather(*(self.get_project_stats(project) for project in projects))

    async def get_user_tasks(self) -> List[Task]:
        if not self.project_repo.user_id:
            return []

        projects = await self.project_repo.get_assigned_projects()
        if not projects:
            return []

        user_link_counts = await self.project_repo.get_user_link_counts_by_project()

        progress_results = await asyncio.gather(
            *(self.get_vectorized_and_ready_report_ids(project.id) for project in projects)
        )

        tasks: List[Task] = []
        for project, (_, _, ready_for_processing) in zip(projects, progress_results):
            tasks.append(
                Task(
                    projectId=project.id,
                    name=project.description,
                    owner=project.uploaded_by or "",
                    createdAt=project.date_created,
                    numberReportsReadyForProcessing=len(ready_for_processing),
                    numberReportsProcessed=user_link_counts.get(project.id, 0),
                )
            )

        return tasks

    @staticmethod
    def build_reports_from_entries(entries: List[dict]) -> Tuple[str, List[DbReport], List[Optional[str]]]:
        """Turn parsed bibliography entries (src/utils/ris_parser.py's parse_file()
        output) into unsaved Report rows plus the project id derived from their
        fingerprint - the same deterministic hash a re-upload of the same file
        must reproduce, so add_new_project() can detect it as a duplicate. Also returns
        a parallel list of best-effort trial ids (one per report, order-matched) for
        add_new_project() to seed each report's ReportAdded.trial_registration_id with -
        this is an unconfirmed guess, so it never lands on Report itself (see that
        field's comment in models.py).
        """
        reports: List[DbReport] = []
        trial_ids_by_report: List[Optional[str]] = []
        fingerprint_string = ""

        for entry in entries:
            title = entry.get('primary_title') or entry.get('title', "")
            authors = entry.get('authors', [])
            abstract = entry.get('abstract', None)
            report_number = int(entry.get('research_notes', -1))

            trial_ids = extract_trial_id(title=title, abstract=abstract, authors=authors)
            trial_id = trial_ids[0] if len(trial_ids) == 1 else None

            authors_str = "//".join(authors)
            safe_title = title.replace("\n", " ")

            try:
                safe_abstract = abstract.replace("\n", " ") if abstract is not None else ""
            except AttributeError:
                safe_abstract = str(abstract) if abstract is not None else ""

            reports.append(DbReport(
                title=safe_title,
                abstract=safe_abstract,
                authors=authors_str,
                report_number=report_number,
                journal=entry.get('secondary_title', None),
                year=int(entry.get('year', None)),
                volume=entry.get('volume', None),
                issue=entry.get('note', None),
                pages=entry.get('start_page', None),
                language=entry.get('language', None),
                publisher=entry.get('publisher', None),
                city=entry.get('place_published', None),
                doi=entry.get('doi', None),
            ))
            trial_ids_by_report.append(trial_id)

            fingerprint_string += "|".join([safe_title or "", safe_abstract or "", authors_str or ""])

        project_id = hashlib.sha256(fingerprint_string.encode()).hexdigest()
        return project_id, reports, trial_ids_by_report

    async def create_project(
        self,
        project_name: str,
        upload: UploadedFile,
    ) -> Optional[Tuple[Project, List[int]]]:
        """Parse a bibliography file (.ris/.cgi/.nbib, selected by `upload.filename`'s
        extension) into a new project, persist it, and notify subscribers. Who's
        allowed to call this at all (ADMIN role) is a coarse, data-independent
        permission.

        Scheduling the background PDF-search/embedding pass
        (src/background/wrapper.py's run_process_report_background) is left to the
        caller: how to fire it without blocking the response is framework-specific
        (e.g. FastAPI's BackgroundTasks) - this just hands back the report ids to schedule
        it with.

        Raises RisParseError if the file can't be parsed. Returns None if a project
        with this exact set of reports already exists (see
        build_reports_from_entries's deterministic project_id), otherwise the new
        project's full stats (via get_project_stats) plus its report ids.
        """
        entries = await parse_file(upload)
        project_id, reports, trial_ids = self.build_reports_from_entries(entries)
        saved_reports = await self.project_repo.add_new_project(project_id, project_name, reports, trial_ids)
        if saved_reports is None:
            return None

        await self.pubsub_service.publish_project_update(project_id)

        project = await self.project_repo.get_project_by_id(project_id)
        project_full = await self.get_project_stats(project)
        report_ids = [report.id for report in saved_reports]
        return project_full, report_ids

    async def delete_project(self, project_id: str) -> None:
        """Delete a project (cascading to its reports/assignments/annotations
        - see the DB schema) and clean up everything that isn't cascade-owned
        by Postgres: the reports' vectorstore embeddings, plus notifying
        subscribers. Raises ProjectNotFoundError if it doesn't exist. Who's
        allowed to call this (ADMIN role) is enforced at the API layer, same
        as create_project.
        """
        project = await self.project_repo.get_project_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        report_ids = await self.project_repo.get_project_associated_report_ids(project_id)
        await self.project_repo.delete_project(project_id)
        await self.vectorstore_service.delete_vectors_by_report_ids(report_ids)
        await self.pubsub_service.publish_project_update(project_id)

    async def assign_user_to_project(self, project_id: str, assignee_user_id: str) -> Assignee:
        """Assign a user to a project, giving them a review task. Raises
        ProjectNotFoundError if the project doesn't exist, or
        ProjectAssigneeAlreadyExistsError if they're already assigned.
        project_repo.add_project_assignee's own ValueError/PermissionError
        (no caller/ownership) propagate as-is - both heads already translate
        those generically, so there's nothing project-specific to add here.
        assignee_user_id is an opaque string - nothing here validates it
        against a real user list, which lets a downstream build assign
        synthetic, non-human "users" (e.g. an automation agent) without
        needing a hook from this service.
        """
        project = await self.project_repo.get_project_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        created = await self.project_repo.add_project_assignee(project_id, assignee_user_id)
        if not created:
            raise ProjectAssigneeAlreadyExistsError(
                f"{assignee_user_id} is already assigned to project {project_id}"
            )

        await self.pubsub_service.publish_project_update(project_id)
        return Assignee(userId=assignee_user_id, numberReportsLinked=0)

    async def remove_user_from_project(self, project_id: str, user_id: str) -> None:
        """Remove a user's assignment from a project. Raises
        ProjectNotFoundError if the project doesn't exist, or
        ProjectAssigneeNotFoundError if they weren't assigned to begin with.
        """
        project = await self.project_repo.get_project_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        removed = await self.project_repo.remove_project_assignee(project_id, user_id)
        if not removed:
            raise ProjectAssigneeNotFoundError(
                f"{user_id} is not assigned to project {project_id}"
            )

        await self.pubsub_service.publish_project_update(project_id)

    async def ensure_project_access(self, project_id: str) -> None:
        """Raise ProjectAccessDeniedError unless the caller uploaded this
        project or is assigned to it. Exposed for callers that don't have a
        more specific project_service operation to attach the check to (e.g.
        stream_project_updates below).
        """
        project = await self.project_repo.get_project_by_id(project_id)
        if project is not None and project.uploaded_by == self.project_repo.user_id:
            return
        if not await self.project_repo.is_project_assignee(project_id):
            raise ProjectAccessDeniedError(f"Not assigned to project {project_id}")

    async def stream_project_updates(
        self, project_id: str, is_disconnected: Callable[[], Awaitable[bool]]
    ) -> AsyncIterator[str]:
        """SSE frames ('data: ...\\n\\n') of a project's pubsub updates, until
        `is_disconnected` reports the caller has gone away. `is_disconnected`
        abstracts over the one framework-specific bit here (Starlette's
        Request.is_disconnected()), so the polling loop itself doesn't need
        to import FastAPI.

        Doesn't call ensure_project_access itself: this is a generator, so
        nothing in its body runs until the caller starts iterating it - too
        late to turn a denied access into an upfront 403/ResourceError
        instead of a failure mid-stream. Callers must call
        ensure_project_access(project_id) themselves first (see
        fastapi_app/projects.py's stream route).
        """
        pubsub = await self.pubsub_service.subscribe_to_project(project_id)
        try:
            while True:
                if await is_disconnected():
                    break
                data = await self.pubsub_service.get_next_project_update(pubsub)
                yield f"data: {data}\n\n"
        finally:
            await self.pubsub_service.unsubscribe_from_project(project_id, pubsub)

    async def get_project_annotations(
        self, project_id: str
    ) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:
        report_ids = await self.project_repo.get_project_associated_report_ids(project_id)
        if not report_ids:
            return {}

        assignees = await self.project_repo.get_project_assignees(project_id)
        assignee_ids = {user_id for user_id, _ in assignees if user_id}
        if not assignee_ids:
            return {}

        completion_map = await self.project_repo.get_report_completion_by_users(project_id)
        annotated_report_ids = [
            report_id
            for report_id in report_ids
            if assignee_ids.issubset(completion_map.get(report_id, set()))
        ]

        if not annotated_report_ids:
            return {}

        return await self.project_repo.get_project_annotations_by_assignees(
            project_id,
            assignee_ids,
            annotated_report_ids,
        )

    async def get_project_report_status(self, project_id: str) -> Dict[int, Dict[str, bool]]:
        report_ids = await self.project_repo.get_project_associated_report_ids(project_id)
        if not report_ids:
            return {}

        embedded_reports, pdf_ready_reports, _ = await self.get_vectorized_and_ready_report_ids(project_id)

        return {
            report_id: {
                "embedded": report_id in embedded_reports,
                "pdf": report_id in pdf_ready_reports,
            }
            for report_id in report_ids
        }

    async def review_candidate_report_ids(
        self,
        project_id: str,
        consensus: FilterMode,
        reviewed: FilterMode,
    ) -> Set[int]:
        """The review view's id-narrowing step: fully-annotated report ids (every project
        assignee has completed annotating), optionally further narrowed by consensus/reviewed.
        Bounded by the project's annotation rows (get_project_annotations already returns a
        compact per-report structure, no report bodies) - feeds into
        query_project_reports_page's restrict_to_ids rather than filtering an already-hydrated
        list.
        """
        annotations = await self.get_project_annotations(project_id)

        def _annotated_studies(report_id: int) -> List[Dict[str, Any]]:
            return annotations.get(report_id, {}).get("studies", [])

        candidate_ids = set(annotations.keys())

        if consensus is not FilterMode.any:
            # Fewer than two annotators can't disagree, so treat that as consensus too.
            candidate_ids = {
                report_id for report_id in candidate_ids
                if matches_filter(
                    len(_annotated_studies(report_id)) < 2
                    or len({s["studyId"] for s in _annotated_studies(report_id)}) == 1,
                    consensus,
                )
            }

        if reviewed is not FilterMode.any:
            candidate_ids = {
                report_id for report_id in candidate_ids
                if matches_filter(any(s["confirmed"] for s in _annotated_studies(report_id)), reviewed)
            }

        return candidate_ids

    async def hydrate_report_page(
        self, page_rows: List[DbReport], limit: int, *, include_report_detail: bool = False
    ) -> Page[ReportCuration] | Page[ReportIntake]:
        """Turns a page of plain Report rows - as ReportRepository.query_project_reports_page
        returns them, including its +1 lookahead row - into the DTO shape, fetching only
        what that shape needs for this page.

        `include_report_detail` switches the row (and page) shape from ReportCuration/
        Page[ReportCuration] to ReportIntake/Page[ReportIntake]: DOI + cached OpenAlex fulltext
        links (see get_fulltext_links_for_reports's docstring for why this is cache-only,
        unlike the single-report detail endpoint's live fallback) instead of flag/
        assignedStudies - intake reports haven't been curated yet, so those don't apply and
        this branch never queries for them. Only get_intake_reports_page sets this.
        """
        has_more = len(page_rows) > limit
        page_rows = page_rows[:limit]
        page_ids = [report.id for report in page_rows]

        _, reports_with_pdf = await self.report_repo.get_readiness_sets(page_ids)

        if include_report_detail:
            fulltext_links_by_report = await self.report_repo.get_fulltext_links_for_reports(page_ids)
            items = [
                ReportIntake(
                    **reports_to_dto([report])[0].model_dump(),
                    hasPdf=report.id in reports_with_pdf,
                    doi=report.doi,
                    fulltextLinks=fulltext_links_by_report.get(report.id, []),
                )
                for report in page_rows
            ]
            next_cursor = encode_cursor(page_ids[-1]) if has_more and page_ids else None
            return Page[ReportIntake](items=items, nextCursor=next_cursor)

        all_linked_studies = await self.report_repo.get_linked_studies_for_reports(page_ids)
        report_flags = await self.report_repo.get_report_flags_for_reports(page_ids)
        preliminary_trial_ids = await self.report_repo.get_preliminary_trial_ids_for_reports(page_ids)
        items = [
            ReportCuration(
                **reports_to_dto([report])[0].model_dump(),
                hasPdf=report.id in reports_with_pdf,
                flag=report_flags.get(report.id).message if report.id in report_flags else None,
                assignedStudies=studies_to_preview_dto(all_linked_studies.get(report.id, [])),
                preliminaryTrialId=preliminary_trial_ids.get(report.id),
            )
            for report in page_rows
        ]
        next_cursor = encode_cursor(page_ids[-1]) if has_more and page_ids else None
        return Page[ReportCuration](items=items, nextCursor=next_cursor)

    async def get_reports_page(
        self,
        project_id: str,
        *,
        search: Optional[str] = None,
        processed: FilterMode = FilterMode.any,
        flagged: FilterMode = FilterMode.any,
        new_study: FilterMode = FilterMode.any,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Page[ReportCuration]:
        """The normal curation view: never includes reports that are still being
        processed (not yet embedded/PDF-ready) - see get_intake_reports_page for that.
        Restricted to project assignees (or whoever uploaded it).
        """
        await self.ensure_project_access(project_id)
        cursor_id = decode_cursor(cursor) if cursor else None
        page_rows = await self.report_repo.query_project_reports_page(
            project_id,
            require_ready=True,
            search=search,
            processed=filter_mode_to_bool(processed),
            flagged=filter_mode_to_bool(flagged),
            new_study=filter_mode_to_bool(new_study),
            cursor_id=cursor_id,
            limit=limit,
        )
        return await self.hydrate_report_page(page_rows, limit)

    async def get_intake_reports_page(
        self,
        project_id: str,
        *,
        search: Optional[str] = None,
        with_pdf: FilterMode = FilterMode.any,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Page[ReportIntake]:
        """The admin intake view: unlike get_reports_page, always includes reports that
        have been auto-searched for a PDF but aren't fully processed yet, so an admin
        can watch reports as they arrive. Returns the richer ReportIntake
        shape (DOI + fulltext links included) so the pdf-upload UI can read a report's
        DOI/links straight off this list instead of a separate per-report fetch.
        """
        cursor_id = decode_cursor(cursor) if cursor else None
        page_rows = await self.report_repo.query_project_reports_page(
            project_id,
            require_ready=False,
            with_pdf=filter_mode_to_bool(with_pdf),
            search=search,
            cursor_id=cursor_id,
            limit=limit,
        )
        return await self.hydrate_report_page(page_rows, limit, include_report_detail=True)

    async def get_review_reports_page(
        self,
        project_id: str,
        *,
        search: Optional[str] = None,
        consensus: FilterMode = FilterMode.any,
        reviewed: FilterMode = FilterMode.any,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Page[ReportCuration]:
        """The admin annotator-review view: always restricted to reports every project
        assignee has completed annotating, regardless of search/filter.
        """
        cursor_id = decode_cursor(cursor) if cursor else None
        restrict_to_ids = await self.review_candidate_report_ids(project_id, consensus, reviewed)
        page_rows = await self.report_repo.query_project_reports_page(
            project_id,
            require_ready=True,
            search=search,
            restrict_to_ids=restrict_to_ids,
            cursor_id=cursor_id,
            limit=limit,
        )
        return await self.hydrate_report_page(page_rows, limit)
