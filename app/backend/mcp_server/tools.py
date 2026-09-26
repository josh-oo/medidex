"""MCP tools for searching Medidex studies, and for project management.

Search tools are thin wrappers around the same repository layer the REST API
(fastapi_app/resources.py) and the LangChain agent tools (src/services/agent.py)
already query - kept here instead of duplicating query logic. Kept as tools
rather than moved into resources.py (unlike this package's other study/report
lookups): each resolves a caller-supplied search key to a result, which is a
search action, not a fetch of a record at a known, addressable URI.

Project management tools mirror the REST API's project/assignee write
endpoints (fastapi_app/projects.py: POST /projects, POST and DELETE
/projects/{project_id}/assignees, DELETE /projects/{project_id}), reusing the
same ProjectResourceService (src/services/project.py) the REST API also
calls for the parts that aren't framework glue. Every one of them is admin
only (require_admin(), the MCP-side equivalent of the REST API's
Depends(is_admin) - see mcp_server/context.py).

The two delete-shaped ones confirm before touching anything, via the SDK's
resolver-based elicitation (Annotated[ElicitationResult[T], Resolve(fn)] -
see https://py.sdk.modelcontextprotocol.io/handlers/elicitation/) rather
than calling ctx.elicit() by hand in the tool body: the resolver form works
across both the batched (>= 2026-07-28) and standalone-request (older)
elicitation transports, and lets require_admin() run - and reject a
non-admin - before the confirmation prompt is even sent. But elicitation
itself is a capability the *connecting client* has to declare (most don't
yet - form-mode support is still new), and a resolver that elicits without
checking first gets the whole call killed with an opaque
MISSING_REQUIRED_CLIENT_CAPABILITY MCPError, not a usable fallback. So each
resolver checks ctx.client_capabilities first (_client_supports_elicitation()
below) and only elicits when the connected client actually declared form
support; otherwise it requires the tool's own `confirm=True` argument
instead (skipping the prompt entirely if the caller already passed it) -
the same "ask only when necessary" resolver shape the SDK docs use for a
non-empty-folder check, just keyed on client capability rather than data.

create_project kicks off the same background PDF-search/embedding pipeline
POST /projects does (src/background/wrapper.py's process_report(), which
both heads now share - it used to live inline in fastapi_app/projects.py).
FastAPI schedules it via BackgroundTasks; there's no equivalent here, so it's
fired with a bare asyncio.create_task() instead (see _fire_and_forget()) -
process_report() opens its own DB session(s) independently of the tool
call's own request_context(), so it keeps running after this tool returns.

list_projects, list_tasks, and the whole "Study/report/project lookup tools"
section further down duplicate resources.py's resources as tools, because
MCP resource support is inconsistent across clients in practice: several
clients only ever surface `tools/*`, never calling `resources/list` at all,
and even ones that do generally can't fill in a *template* resource's URI
parameters (medidex://studies/{study_id} and friends) - Claude included, as
of writing. Without a tool form, a client like that has no way to ever reach
these lookups, whether by discovery (list_projects/list_tasks - "what
projects exist" has no id to fetch by in the first place) or by id (the
lookup tools further down). The underlying reads are cheap and
side-effect-free, so the duplication costs little; resources.py keeps its
own definitions too, for clients that do support resources/templates, and
for the `project` resource's subscribability (see resources.py's own
docstring), which the tool form doesn't replicate.
"""

import asyncio
from typing import Annotated, Any, Dict, List, Set

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from typing import Annotated

from pydantic import BaseModel, Field

from mcp.server.mcpserver import (
    AcceptedElicitation,
    Context,
    Elicit,
    ElicitationResult,
    Resolve,
)
from mcp.server.mcpserver.exceptions import ToolError

from src.background.wrapper import run_process_report_background
from src.services.project import ProjectResourceService
from src.utils.dto import (
    Project,
    ProjectAssignee,
    ProjectDetails,
    ProjectTask,
    Report,
    Study,
    Tag,
    reports_to_dto,
    studies_to_dto,
    tags_to_dto,
)
from src.utils.ris_parser import RisParseError, parse_file

from .context import current_user_id, request_context, require_admin, require_report_access

# Fire-and-forget background jobs (see _fire_and_forget()) need a strong
# reference kept somewhere until they finish, or asyncio may garbage-collect
# a task mid-run.
_background_tasks: Set[asyncio.Task] = set()


def _fire_and_forget(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class _InMemoryUpload:
    """Satisfies parse_file()'s UploadedFile protocol (src/utils/ris_parser.py:
    a `.filename` attribute and an async `.read()`) so a tool can feed it a
    bibliography file's raw text without a real HTTP multipart upload.
    """

    def __init__(self, content: bytes, filename: str):
        self._content = content
        self.filename = filename

    async def read(self) -> bytes:
        return self._content


class ConfirmAction(BaseModel):
    confirm: bool = Field(
        description="Confirm this destructive action."
    )


async def _confirm_delete_project(
    project_id: str,
    ctx: Context,
) -> ConfirmAction | Elicit[ConfirmAction]:
    require_admin()

    capabilities = ctx.client_capabilities
    if capabilities is None or capabilities.elicitation is None:
        raise ToolError(
            "This client did not declare the MCP 'elicitation' capability, so "
            "delete_project cannot ask for confirmation before deleting. "
            f"(client capabilities: {capabilities!r})"
        )

    return Elicit(
        f"Delete project '{project_id}' and all its reports and embeddings? "
        "This cannot be undone.",
        ConfirmAction,
    )


def register(server: MCPServer) -> None:
    """
    Search tools
    """

    @server.tool(
        annotations=ToolAnnotations(
            title="Search Study by Short Name",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def search_study_by_short_name(short_name: str) -> Study:
        """Search for a clinical study by its short name (acronym, trial registration id, or "first author + year" label). Returns the single best match."""
        async with request_context(current_user_id()) as ctx:
            study = await ctx.study_repo.search_study_by_shortname(short_name)
            if study is None:
                raise ToolError(f"No study found with shortname '{short_name}'")
            return studies_to_dto([study])[0]

    @server.tool(
        annotations=ToolAnnotations(
            title="Search Study IDs by Trial ID",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def search_study_ids_by_trial_id(trial_id: str) -> List[int]:
        """Search for study ids by trial registration id (e.g. NCT00034892, ACTRN12605000202662)."""
        async with request_context(current_user_id()) as ctx:
            result = await ctx.study_repo.get_study_id_by_trial_id(trial_id)
            if result is None:
                raise ToolError(f"Trial {trial_id} not found")
            return result

    """
    Study/report/project lookup tools

    Tool-form duplicates of resources.py's per-id study/report/project resources
    (medidex://studies/{study_id}, medidex://reports/{report_id}, .../projects/{project_id},
    ...). Beyond list_projects/list_tasks's own rationale (parameterless discovery
    entry points), these hit a harder gap: they're *template* resources, and most
    MCP clients - Claude included - can't fill in a template's URI parameters at
    all, so a client like that can't reach these resources no matter how it's
    asked (see resources.py's own module docstring). The resources stay defined
    there too, for clients that do support templates.

    report-pdf is deliberately not duplicated here: a whole PDF as inline tool
    output floods the model's context with a binary blob it can't read as text,
    which isn't a good fit for a tool result either way.
    """

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study(study_id: int) -> Study:
        """Full details for a study by its numeric id. Tool form of the `study` resource, for clients that don't support MCP resource templates."""
        async with request_context(current_user_id()) as ctx:
            study = await ctx.study_repo.get_study_by_id(study_id)
            if study is None:
                raise ToolError(f"Study {study_id} not found")
            return studies_to_dto([study])[0]

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Reports",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_reports(study_id: int) -> List[Report]:
        """All reports already linked to a study (the "studification" result for that study). Tool form of the `study-reports` resource."""
        async with request_context(current_user_id()) as ctx:
            reports = await ctx.study_repo.get_linked_reports(study_id)
            return reports_to_dto(reports)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Interventions",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_interventions(study_id: int) -> List[Tag]:
        """Interventions for a specific study (e.g. 'Placebo', 'Group Therapy', ...). Tool form of the `study-interventions` resource."""
        async with request_context(current_user_id()) as ctx:
            result = await ctx.study_repo.get_study_interventions_single(study_id)
            return tags_to_dto(result)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Conditions",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_conditions(study_id: int) -> List[Tag]:
        """The health conditions of participants in a specific study (e.g. 'COVID-19', 'Diabetes', ...). Tool form of the `study-conditions` resource."""
        async with request_context(current_user_id()) as ctx:
            result = await ctx.study_repo.get_study_conditions_single(study_id)
            return tags_to_dto(result)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Outcomes",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_outcomes(study_id: int) -> List[Tag]:
        """Outcomes for a specific study (e.g. 'Mortality', 'Hospitalization', ...). Tool form of the `study-outcomes` resource."""
        async with request_context(current_user_id()) as ctx:
            result = await ctx.study_repo.get_study_outcomes_single(study_id)
            return tags_to_dto(result)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Participants",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_participants(study_id: int) -> List[Dict[str, Any]]:
        """Participant description for a specific study (e.g. Male, Female, Adult, Child, ...). Tool form of the `study-participants` resource."""
        async with request_context(current_user_id()) as ctx:
            return await ctx.study_repo.get_study_participants_single(study_id)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Design",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_design(study_id: int) -> List[Dict[str, Any]]:
        """The study design of the corresponding study ('Randomized Controlled Trial', 'Controlled Clinical Trial'). Tool form of the `study-design` resource."""
        async with request_context(current_user_id()) as ctx:
            return await ctx.study_repo.get_study_design_single(study_id)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Persons",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_persons(study_id: int) -> List[str]:
        """All persons (usually only authors) associated with a specific study. Tool form of the `study-persons` resource."""
        async with request_context(current_user_id()) as ctx:
            # Matches the REST endpoint's own default (Query(False)), not
            # the repository method's own default of True.
            return await ctx.study_repo.get_study_persons_single(study_id=study_id, normalize_names=False)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Report",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_report(report_id: int) -> Report:
        """Full details (including abstract) for a single report by its numeric id. Tool form of the `report` resource."""
        async with request_context(current_user_id()) as ctx:
            await require_report_access(report_id, ctx)
            db_report = await ctx.report_repo.get_report_by_id(report_id)
            if db_report is None:
                raise ToolError(f"Report {report_id} not found")
            return reports_to_dto([db_report])[0]

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Report Studies",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_report_studies(report_id: int) -> List[Study]:
        """The studies linked to a specific report. Tool form of the `report-studies` resource."""
        async with request_context(current_user_id()) as ctx:
            await require_report_access(report_id, ctx)
            result = await ctx.report_repo.get_linked_studies(report_id)
            return studies_to_dto(result)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Project",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_project(project_id: str) -> ProjectDetails:
        """Details and progress for a single project. Admin only. Tool form of the `project` resource - unlike the resource, this snapshot isn't subscribable; poll it or use the resource form for live updates."""
        require_admin()
        async with request_context(current_user_id()) as ctx:
            project = await ctx.project_repo.get_project_by_id(project_id)
            if project is None:
                raise ToolError(f"Project {project_id} not found")
            return await ctx.project_service.get_project_stats(project)

    """
    Project management tools
    """

    @server.tool(
        annotations=ToolAnnotations(
            title="Create Project",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def create_project(project_name: str, file_content: str, filename: str = "reports.ris") -> Project:
        """Create a new project (a batch of new reports awaiting study assignment) from a bibliography file's contents (.ris, .cgi, or .nbib format - selected by `filename`'s extension). Admin only. Kicks off background PDF search and embedding for the new reports, same as the web app; poll the `project` resource (or subscribe to it) to track progress."""
        require_admin()
        async with request_context(current_user_id()) as ctx:
            upload = _InMemoryUpload(file_content.encode("utf-8"), filename)
            try:
                entries = await parse_file(upload)
            except RisParseError as exc:
                raise ToolError(str(exc)) from exc

            project_id, reports = ProjectResourceService.build_reports_from_entries(entries)

            saved_reports = await ctx.project_repo.add_new_project(project_id, project_name, reports)
            if saved_reports is None:
                raise ToolError("Project already exists")

            report_ids = [report.id for report in saved_reports]
            _fire_and_forget(run_process_report_background(project_id, report_ids, ctx.user_id))

            await ctx.pubsub_service.publish_project_update(project_id)

            project = await ctx.project_repo.get_project_by_id(project_id)
            return Project(
                projectId=project.id,
                name=project.description,
                owner=project.uploaded_by or "",
                createdAt=project.date_created,
                numberReportsReadyForProcessing=0,
            )

    @server.tool(
        annotations=ToolAnnotations(
            title="List Projects",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def list_projects() -> List[ProjectDetails]:
        """List all current projects, with embedding/assignment progress for each. Admin only. Tool form of the `projects` resource, for clients that don't support MCP resources."""
        require_admin()
        async with request_context(current_user_id()) as ctx:
            return await ctx.project_service.get_all_project_stats()

    @server.tool(
        annotations=ToolAnnotations(
            title="List My Tasks",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def list_tasks() -> List[ProjectTask]:
        """List the authenticated user's pending review tasks: every project they're assigned to, with their personal study-link counts. Tool form of the `tasks` resource, for clients that don't support MCP resources."""
        async with request_context(current_user_id()) as ctx:
            return await ctx.project_service.get_user_tasks()

    @server.tool(
        annotations=ToolAnnotations(
            title="Assign Project Task",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def assign_project_task(project_id: str, assignee_user_id: str) -> ProjectAssignee:
        """Assign a user to a project, giving them a review task: they can link that project's reports to studies, and the project shows up in their `tasks` resource. Admin only."""
        require_admin()
        async with request_context(current_user_id()) as ctx:
            project = await ctx.project_repo.get_project_by_id(project_id)
            if project is None:
                raise ToolError(f"Project {project_id} not found")

            try:
                created = await ctx.project_repo.add_project_assignee(project_id, assignee_user_id)
            except (ValueError, PermissionError) as exc:
                raise ToolError(str(exc)) from exc

            if not created:
                raise ToolError(f"{assignee_user_id} is already assigned to project {project_id}")

            await ctx.pubsub_service.publish_project_update(project_id)
            return ProjectAssignee(userId=assignee_user_id, numberReportsLinked=0)

    @server.tool(
        annotations=ToolAnnotations(
            title="Delete Project",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def delete_project(project_id: str, confirmation: Annotated[ElicitationResult[ConfirmAction],Resolve(_confirm_delete_project),],) -> None:
        match confirmation:
            case AcceptedElicitation(data=ConfirmAction(confirm=True)):
                pass
            case AcceptedElicitation():
                raise ToolError("Not confirmed - no changes were made.")
            case _:
                raise ToolError("Not confirmed - no changes were made.")

        async with request_context(current_user_id()) as ctx:
            project = await ctx.project_repo.get_project_by_id(project_id)
            if project is None:
                raise ToolError(f"Project {project_id} not found")

            report_ids = await ctx.project_repo.get_project_associated_report_ids(
                project_id
            )
            await ctx.project_repo.delete_project(project_id)
            await ctx.vectorstore_service.delete_vectors_by_report_ids(report_ids)
            await ctx.pubsub_service.publish_project_update(project_id)
