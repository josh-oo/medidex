"""MCP tools for searching/retrieving Medidex studies and reports.

Thin wrappers around the same repository layer the REST API (src/api/resources.py)
and the LangChain agent tools (src/services/agent.py) already query - kept here
instead of duplicating query logic. Authorization mirrors the REST API: a
per-call user_id (from the verified token's subject) is threaded into the
repositories exactly like the REST routers' `Depends(get_user_id)` does, and
get_report additionally replicates the REST API's project-membership check
(check_report_access) so an MCP caller can't see reports outside their
assigned projects.
"""

from typing import List

from fastapi import HTTPException

from mcp.server import MCPServer

from src.database.repositories.study import StudyRepository
from src.database.repositories.report import ReportRepository
from src.database.repositories.project import ProjectRepository
from src.api.core import check_report_access
from src.utils.dto import Study, Report, studies_to_dto

from .context import current_user_id, session_scope


def _report_row_to_dto(row: dict) -> Report:
    return Report(
        reportId=row["id"],
        year=row["year"],
        title=row["title"],
        abstract=row["abstract"],
        trialId=row["trial_registration_id"],
        authors=row["authors"].split("//") if row["authors"] else [],
        createdAt=row["date_entered"],
        updatedAt=row["date_edited"],
    )


def _db_report_to_dto(db_report) -> Report:
    return Report(
        reportId=db_report.id,
        year=db_report.year,
        title=db_report.title,
        abstract=db_report.abstract,
        trialId=db_report.trial_registration_id,
        authors=db_report.authors.split("//") if db_report.authors else [],
        createdAt=db_report.date_entered,
        updatedAt=db_report.date_edited,
    )


def register(server: MCPServer) -> None:
    @server.tool()
    async def search_study_by_short_name(short_name: str) -> Study:
        """Search for a clinical study by its short name (acronym, trial registration id, or "first author + year" label). Returns the single best match."""
        user_id = current_user_id()
        async with session_scope() as db:
            study_repo = StudyRepository(db=db, user_id=user_id)
            study = await study_repo.search_study_by_shortname(short_name)
            if study is None:
                raise ValueError(f"No study found with shortname '{short_name}'")
            return studies_to_dto([study])[0]

    @server.tool()
    async def get_study(study_id: int) -> Study:
        """Get full details for a study by its numeric id."""
        user_id = current_user_id()
        async with session_scope() as db:
            study_repo = StudyRepository(db=db, user_id=user_id)
            study = await study_repo.get_study_by_id(study_id)
            if study is None:
                raise ValueError(f"Study {study_id} not found")
            return studies_to_dto([study])[0]

    @server.tool()
    async def get_study_reports(study_id: int) -> List[Report]:
        """List all reports already linked to a study (the "studification" result for that study)."""
        user_id = current_user_id()
        async with session_scope() as db:
            study_repo = StudyRepository(db=db, user_id=user_id)
            rows = await study_repo.get_study_reports_by_study_id(study_id)
            return [_report_row_to_dto(row) for row in rows]

    @server.tool()
    async def get_report(report_id: int) -> Report:
        """Get full details (including abstract) for a single report by its numeric id."""
        user_id = current_user_id()
        async with session_scope() as db:
            report_repo = ReportRepository(db=db, user_id=user_id)
            project_repo = ProjectRepository(db=db, user_id=user_id)
            try:
                await check_report_access(report_id, report_repo=report_repo, project_repo=project_repo, user_id=user_id)
            except HTTPException as exc:
                raise ValueError(exc.detail) from exc
            db_report = await report_repo.get_report_by_id(report_id)
            if db_report is None:
                raise ValueError(f"Report {report_id} not found")
            return _db_report_to_dto(db_report)
