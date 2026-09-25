"""MCP resources for Medidex studies, reports, and report PDFs.

Unlike tools.py's tools (fuzzy/keyed searches returning a single best match or
result set, not a fetch of a record at a known URI), resources are addressed
by URI and read their content on demand - the right fit here since every
lookup below resolves a specific, already-known id to a record. Mirrors the
GET endpoints under /studies and /reports/{report_id} in the REST API
(fastapi_app/resources.py); reuses the same repository layer rather than
duplicating query logic. A few of that router's endpoints aren't mirrored
here:
- `GET /studies/reports`, `GET /studies/persons`: `include_in_schema=False`
  bulk/legacy variants of the per-study resources below, not part of the
  public API surface.
- `GET /studies/{study_id}/date_entered`: already covered by the `study`
  resource's `createdAt` field (see `studies_to_dto`), so no separate
  resource for it.
- `GET /studies/{trial_id}/study_id`: a search keyed on caller-supplied text
  rather than a fetch by a known id, so it's a tool
  (`search_study_ids_by_trial_id` in tools.py), not a resource here.

Report-scoped resources additionally enforce the same project-membership
check as the REST API's check_report_access (fastapi_app/core.py) - via the
shared domain function in context.py, not that FastAPI dependency itself -
so an MCP caller can't see reports outside their assigned projects. Study
resources don't: studies aren't project-scoped, matching the REST API's
/studies endpoints (which don't depend on check_report_access either).

Project management resources mirror GET /projects, /projects/{project_id}
and /tasks (fastapi_app/projects.py), reusing the same ProjectResourceService
(src/services/project.py) the REST API now also calls. The two /projects
endpoints are admin-gated (require_admin(), the MCP-side equivalent of the
REST API's Depends(is_admin)); /tasks isn't - it's scoped to the caller's own
assignments either way. There's no separate resource for GET
/projects/{project_id}/stream: the `project` resource below is itself
subscribable (see mcp_server/live_updates.py), so a client that lists to it
via `subscriptions/listen` gets the same underlying update signal the REST
endpoint streams over SSE.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from mcp.server import MCPServer

from src.utils.dto import ProjectDetails, ProjectTask, Report, Study, Tag, reports_to_dto, studies_to_dto, tags_to_dto

from .context import current_user_id, request_context, require_admin, require_report_access


def register(server: MCPServer) -> None:
    """
    Study resources
    """

    @server.resource(
        "medidex://studies/{study_id}",
        name="study",
        title="Study",
        description="Full details for a study by its numeric id.",
        mime_type="application/json",
    )
    async def get_study(study_id: int) -> Study:
        async with request_context(current_user_id()) as ctx:
            study = await ctx.study_repo.get_study_by_id(study_id)
            if study is None:
                raise ValueError(f"Study {study_id} not found")
            return studies_to_dto([study])[0]

    @server.resource(
        "medidex://studies/{study_id}/reports",
        name="study-reports",
        title="Study reports",
        description='All reports already linked to a study (the "studification" result for that study).',
        mime_type="application/json",
    )
    async def get_study_reports(study_id: int) -> List[Report]:
        async with request_context(current_user_id()) as ctx:
            reports = await ctx.study_repo.get_linked_reports(study_id)
            return reports_to_dto(reports)

    @server.resource(
        "medidex://studies/{study_id}/interventions",
        name="study-interventions",
        title="Study interventions",
        description="Interventions for a specific study (e.g. 'Placebo', 'Group Therapy', ...).",
        mime_type="application/json",
    )
    async def get_study_interventions(study_id: int) -> List[Tag]:
        async with request_context(current_user_id()) as ctx:
            result = await ctx.study_repo.get_study_interventions_single(study_id)
            return tags_to_dto(result)

    @server.resource(
        "medidex://studies/{study_id}/conditions",
        name="study-conditions",
        title="Study conditions",
        description="The health conditions of participants in a specific study (e.g. 'COVID-19', 'Diabetes', ...).",
        mime_type="application/json",
    )
    async def get_study_conditions(study_id: int) -> List[Tag]:
        async with request_context(current_user_id()) as ctx:
            result = await ctx.study_repo.get_study_conditions_single(study_id)
            return tags_to_dto(result)

    @server.resource(
        "medidex://studies/{study_id}/outcomes",
        name="study-outcomes",
        title="Study outcomes",
        description="Outcomes for a specific study (e.g. 'Mortality', 'Hospitalization', ...).",
        mime_type="application/json",
    )
    async def get_study_outcomes(study_id: int) -> List[Tag]:
        async with request_context(current_user_id()) as ctx:
            result = await ctx.study_repo.get_study_outcomes_single(study_id)
            return tags_to_dto(result)

    @server.resource(
        "medidex://studies/{study_id}/participants",
        name="study-participants",
        title="Study participants",
        description="Participant description for a specific study (e.g. Male, Female, Adult, Child, ...).",
        mime_type="application/json",
    )
    async def get_study_participants(study_id: int) -> List[Dict[str, Any]]:
        async with request_context(current_user_id()) as ctx:
            return await ctx.study_repo.get_study_participants_single(study_id)

    @server.resource(
        "medidex://studies/{study_id}/design",
        name="study-design",
        title="Study design",
        description="The study design of the corresponding study ('Randomized Controlled Trial', 'Controlled Clinical Trial').",
        mime_type="application/json",
    )
    async def get_study_design(study_id: int) -> List[Dict[str, Any]]:
        async with request_context(current_user_id()) as ctx:
            return await ctx.study_repo.get_study_design_single(study_id)

    @server.resource(
        "medidex://studies/{study_id}/persons",
        name="study-persons",
        title="Study persons",
        description="All persons (usually only authors) associated with a specific study.",
        mime_type="application/json",
    )
    async def get_study_persons(study_id: int) -> List[str]:
        async with request_context(current_user_id()) as ctx:
            # Matches the REST endpoint's own default (Query(False)), not
            # the repository method's own default of True.
            return await ctx.study_repo.get_study_persons_single(study_id=study_id, normalize_names=False)

    """
    Report resources
    """

    @server.resource(
        "medidex://reports/{report_id}",
        name="report",
        title="Report",
        description="Full details (including abstract) for a single report by its numeric id.",
        mime_type="application/json",
    )
    async def get_report(report_id: int) -> Report:
        async with request_context(current_user_id()) as ctx:
            await require_report_access(report_id, ctx)
            db_report = await ctx.report_repo.get_report_by_id(report_id)
            if db_report is None:
                raise ValueError(f"Report {report_id} not found")
            return reports_to_dto([db_report])[0]

    @server.resource(
        "medidex://reports/{report_id}/studies",
        name="report-studies",
        title="Report studies",
        description="The studies linked to a specific report.",
        mime_type="application/json",
    )
    async def get_report_studies(report_id: int) -> List[Study]:
        async with request_context(current_user_id()) as ctx:
            await require_report_access(report_id, ctx)
            result = await ctx.report_repo.get_linked_studies(report_id)
            return studies_to_dto(result)

    @server.resource(
        "medidex://reports/{report_id}/pdf",
        name="report-pdf",
        title="Report PDF",
        description="The full-text PDF for a report.",
        mime_type="application/pdf",
    )
    async def get_report_pdf(report_id: int) -> bytes:
        async with request_context(current_user_id()) as ctx:
            await require_report_access(report_id, ctx)

            try:
                pdf_path = await ctx.document_service.get_path(report_id)
            except Exception as exc:
                raise ValueError(f"PDF not found for report {report_id}") from exc

            return await asyncio.to_thread(Path(pdf_path).read_bytes)

    """
    Project management resources
    """

    @server.resource(
        "medidex://projects",
        name="projects",
        title="Projects",
        description="An overview of all current projects, with embedding/assignment progress for each. Admin only.",
        mime_type="application/json",
    )
    async def get_projects() -> List[ProjectDetails]:
        require_admin()
        async with request_context(current_user_id()) as ctx:
            return await ctx.project_service.get_all_project_stats()

    @server.resource(
        "medidex://projects/{project_id}",
        name="project",
        title="Project",
        description=(
            "Details and progress for a single project. Admin only. Subscribable: "
            "a client that lists to this resource via subscriptions/listen gets a "
            "ResourceUpdated event whenever the project changes."
        ),
        mime_type="application/json",
    )
    async def get_project(project_id: str) -> ProjectDetails:
        require_admin()
        async with request_context(current_user_id()) as ctx:
            project = await ctx.project_repo.get_project_by_id(project_id)
            if project is None:
                raise ValueError(f"Project {project_id} not found")
            return await ctx.project_service.get_project_stats(project)

    @server.resource(
        "medidex://tasks",
        name="tasks",
        title="Tasks",
        description="Pending review tasks for the authenticated user: every project they're assigned to, with their personal study-link counts.",
        mime_type="application/json",
    )
    async def get_tasks() -> List[ProjectTask]:
        async with request_context(current_user_id()) as ctx:
            return await ctx.project_service.get_user_tasks()
