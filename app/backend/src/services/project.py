import asyncio
import hashlib
from typing import Any, List, Set, Tuple

from ..database.models import Project as DbProject, Report as DbReport
from ..database.repositories.project import ProjectRepository
from ..database.repositories.report import ReportRepository
from ..utils.dto import Project, ProjectAssignee, ProjectDetails, ProjectTask
from ..utils.trial_registration_id import extract_trial_id
from .vectorstore import VectorstoreService


class ProjectResourceService:
    """Project overview/progress logic shared by the REST API (fastapi_app/projects.py)
    and the MCP server (mcp_server/resources.py, mcp_server/tools.py) - a project's
    stats/task view is assembled from several repos plus the vectorstore, and project
    creation parses an uploaded bibliography file into report rows, so both live here
    instead of being duplicated per presentation head.
    """

    def __init__(self, project_repo: ProjectRepository, report_repo: ReportRepository, vectorstore_service: VectorstoreService):
        self.project_repo = project_repo
        self.report_repo = report_repo
        self.vectorstore_service = vectorstore_service

    async def get_vectorized_and_ready_report_ids(self, project_id: str) -> Tuple[Set[int], Set[int], Set[int]]:
        report_ids = await self.project_repo.get_project_associated_report_ids(project_id)
        if not report_ids:
            return set(), set(), set()

        # Run database query first, then vectorstore query to avoid concurrent session usage
        reports_with_pdf = await self.report_repo.get_pdf_availabilities(report_ids)
        reports_with_embedding = await self.vectorstore_service.reports_exist(report_ids)

        embedded_reports = set(reports_with_embedding)
        pdf_ready_reports = set(reports_with_pdf)
        ready_reports = embedded_reports & pdf_ready_reports
        return embedded_reports, pdf_ready_reports, ready_reports

    async def get_project_stats(self, project: DbProject) -> ProjectDetails:
        report_ids = await self.project_repo.get_project_associated_report_ids(project.id)
        auto_searched_pdf_count = await self.project_repo.get_auto_searched_pdf_count_for_project(project.id)
        confirmed_report_count = await self.project_repo.get_confirmed_report_count_for_project(project.id)

        embedded_reports, reports_with_pdf, ready_reports = await self.get_vectorized_and_ready_report_ids(project.id)

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
            ProjectAssignee(userId=user_id, numberReportsLinked=linked_count)
            for user_id, linked_count in assignees
        ]

        return ProjectDetails(
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
            owner=project.uploaded_by,
            assignees=assignee_payload,
        )

    async def get_all_project_stats(self) -> List[ProjectDetails]:
        projects = await self.project_repo.get_all_projects()
        return await asyncio.gather(*(self.get_project_stats(project) for project in projects))

    async def get_user_tasks(self) -> List[ProjectTask]:
        if not self.project_repo.user_id:
            return []

        projects = await self.project_repo.get_assigned_projects()
        if not projects:
            return []

        user_link_counts = await self.project_repo.get_user_link_counts_by_project()

        progress_results = await asyncio.gather(
            *(self.get_vectorized_and_ready_report_ids(project.id) for project in projects)
        )

        tasks: List[ProjectTask] = []
        for project, (_, _, ready_for_processing) in zip(projects, progress_results):
            project_payload = Project(
                projectId=project.id,
                name=project.description,
                owner=project.uploaded_by or "",
                createdAt=project.date_created,
                numberReportsReadyForProcessing=len(ready_for_processing),
            )
            tasks.append(
                ProjectTask(
                    project=project_payload,
                    numberReportsProcessed=user_link_counts.get(project.id, 0),
                )
            )

        return tasks

    @staticmethod
    def build_reports_from_entries(entries: List[dict]) -> Tuple[str, List[DbReport]]:
        """Turn parsed bibliography entries (src/utils/ris_parser.py's parse_file()
        output) into unsaved Report rows plus the project id derived from their
        fingerprint - the same deterministic hash a re-upload of the same file
        must reproduce, so add_new_project() can detect it as a duplicate.
        """
        reports: List[DbReport] = []
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
                trial_registration_id=trial_id,
            ))

            fingerprint_string += "|".join([safe_title or "", safe_abstract or "", authors_str or ""])

        project_id = hashlib.sha256(fingerprint_string.encode()).hexdigest()
        return project_id, reports
