"""MCP tools for searching/retrieving Medidex studies and reports.

Thin wrappers around the same repository layer the REST API (fastapi_app/resources.py)
and the LangChain agent tools (src/services/agent.py) already query - kept here
instead of duplicating query logic. Authorization mirrors the REST API: a
per-call user_id (from the verified token's subject) drives the same
RequestContext the REST API builds via Depends(get_context), and get_report
additionally enforces the same project-membership check as the REST API's
check_report_access (fastapi_app/core.py) - via the shared domain function in
context.py, not that FastAPI dependency itself - so an MCP caller can't see
reports outside their assigned projects.
"""

from typing import List

from mcp.server import MCPServer

from src.utils.dto import Study, Report, studies_to_dto

from .context import current_user_id, request_context, require_report_access


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
        async with request_context(current_user_id()) as ctx:
            study = await ctx.study_repo.search_study_by_shortname(short_name)
            if study is None:
                raise ValueError(f"No study found with shortname '{short_name}'")
            return studies_to_dto([study])[0]

    @server.tool()
    async def get_study(study_id: int) -> Study:
        """Get full details for a study by its numeric id."""
        async with request_context(current_user_id()) as ctx:
            study = await ctx.study_repo.get_study_by_id(study_id)
            if study is None:
                raise ValueError(f"Study {study_id} not found")
            return studies_to_dto([study])[0]

    @server.tool()
    async def get_study_reports(study_id: int) -> List[Report]:
        """List all reports already linked to a study (the "studification" result for that study)."""
        async with request_context(current_user_id()) as ctx:
            rows = await ctx.study_repo.get_study_reports_by_study_id(study_id)
            return [_report_row_to_dto(row) for row in rows]

    @server.tool()
    async def get_report(report_id: int) -> Report:
        """Get full details (including abstract) for a single report by its numeric id."""
        async with request_context(current_user_id()) as ctx:
            await require_report_access(report_id, ctx)
            db_report = await ctx.report_repo.get_report_by_id(report_id)
            if db_report is None:
                raise ValueError(f"Report {report_id} not found")
            return _db_report_to_dto(db_report)
