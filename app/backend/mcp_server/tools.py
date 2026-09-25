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

list_projects and list_tasks duplicate the `projects` and `tasks` resources
(mcp_server/resources.py) as tools. Not the general policy (a plain fetch by
a known id stays resource-only, see resources.py's own docstring) - but
these two are the only *discovery* entry points ("what projects exist" has
no id to fetch by), and MCP resource support is inconsistent across clients
in practice (several only surface `tools/*`, never calling `resources/list`
at all), so without a tool form a client like that has no way to ever learn
a project id exists to act on. The underlying reads are cheap and
side-effect-free, so the duplication costs little.
"""

import asyncio
from typing import Annotated, List, Set

from mcp.server import MCPServer
from mcp.server.mcpserver import AcceptedElicitation, Context, Elicit, ElicitationResult, Resolve
from pydantic import BaseModel, Field

from src.background.wrapper import run_process_report_background
from src.services.project import ProjectResourceService
from src.utils.dto import Project, ProjectAssignee, ProjectDetails, ProjectTask, Study, studies_to_dto
from src.utils.ris_parser import parse_file

from .context import current_user_id, request_context, require_admin

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
    confirm: bool = Field(description="Set to true to confirm this action. Anything else cancels it.")


def _client_supports_elicitation(mcp_ctx: Context) -> bool:
    """Mirrors the capability check the SDK's own resolver machinery runs
    before honoring an Elicit marker (mcp.server.mcpserver.resolve._require_capability,
    form-mode branch): True unless the client declared elicitation support
    but only in url mode, or didn't declare it at all.
    """
    capabilities = mcp_ctx.client_capabilities
    elicitation = capabilities.elicitation if capabilities is not None else None
    return elicitation is not None and (elicitation.form is not None or elicitation.url is None)


async def _confirm_delete_project(project_id: str, confirm: bool, mcp_ctx: Context) -> ConfirmAction | Elicit[ConfirmAction]:
    """Resolver for delete_project's `confirmation` parameter - runs before the
    tool body. require_admin() here means a non-admin is rejected without ever
    being asked to confirm.
    """
    require_admin()
    if confirm:
        return ConfirmAction(confirm=True)
    if not _client_supports_elicitation(mcp_ctx):
        raise ValueError(
            "This client doesn't support confirmation prompts. Confirm with the user yourself, "
            "then call this tool again with confirm=True."
        )
    return Elicit(
        f"Delete project '{project_id}' and all its reports and embeddings? This cannot be undone.",
        ConfirmAction,
    )


async def _confirm_remove_project_task(
    project_id: str, assignee_user_id: str, confirm: bool, mcp_ctx: Context
) -> ConfirmAction | Elicit[ConfirmAction]:
    """Resolver for remove_project_task's `confirmation` parameter - see
    _confirm_delete_project.
    """
    require_admin()
    if confirm:
        return ConfirmAction(confirm=True)
    if not _client_supports_elicitation(mcp_ctx):
        raise ValueError(
            "This client doesn't support confirmation prompts. Confirm with the user yourself, "
            "then call this tool again with confirm=True."
        )
    return Elicit(
        f"Remove {assignee_user_id}'s assignment from project '{project_id}'?",
        ConfirmAction,
    )


def _confirmed(confirmation: ElicitationResult[ConfirmAction]) -> bool:
    return isinstance(confirmation, AcceptedElicitation) and confirmation.data.confirm


def register(server: MCPServer) -> None:
    """
    Search tools
    """

    @server.tool()
    async def search_study_by_short_name(short_name: str) -> Study:
        """Search for a clinical study by its short name (acronym, trial registration id, or "first author + year" label). Returns the single best match."""
        async with request_context(current_user_id()) as ctx:
            study = await ctx.study_repo.search_study_by_shortname(short_name)
            if study is None:
                raise ValueError(f"No study found with shortname '{short_name}'")
            return studies_to_dto([study])[0]

    @server.tool()
    async def search_study_ids_by_trial_id(trial_id: str) -> List[int]:
        """Search for study ids by trial registration id (e.g. NCT00034892, ACTRN12605000202662)."""
        async with request_context(current_user_id()) as ctx:
            result = await ctx.study_repo.get_study_id_by_trial_id(trial_id)
            if result is None:
                raise ValueError(f"Trial {trial_id} not found")
            return result

    """
    Project management tools
    """

    @server.tool()
    async def create_project(project_name: str, file_content: str, filename: str = "reports.ris") -> Project:
        """Create a new project (a batch of new reports awaiting study assignment) from a bibliography file's contents (.ris, .cgi, or .nbib format - selected by `filename`'s extension). Admin only. Kicks off background PDF search and embedding for the new reports, same as the web app; poll the `project` resource (or subscribe to it) to track progress."""
        require_admin()
        async with request_context(current_user_id()) as ctx:
            upload = _InMemoryUpload(file_content.encode("utf-8"), filename)
            # RisParseError (src/utils/ris_parser.py) is already a ValueError,
            # this module's own error convention - no translation needed.
            entries = await parse_file(upload)

            project_id, reports = ProjectResourceService.build_reports_from_entries(entries)

            saved_reports = await ctx.project_repo.add_new_project(project_id, project_name, reports)
            if saved_reports is None:
                raise ValueError("Project already exists")

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

    @server.tool()
    async def list_projects() -> List[ProjectDetails]:
        """List all current projects, with embedding/assignment progress for each. Admin only. Tool form of the `projects` resource, for clients that don't support MCP resources."""
        require_admin()
        async with request_context(current_user_id()) as ctx:
            return await ctx.project_service.get_all_project_stats()

    @server.tool()
    async def list_tasks() -> List[ProjectTask]:
        """List the authenticated user's pending review tasks: every project they're assigned to, with their personal study-link counts. Tool form of the `tasks` resource, for clients that don't support MCP resources."""
        async with request_context(current_user_id()) as ctx:
            return await ctx.project_service.get_user_tasks()

    @server.tool()
    async def assign_project_task(project_id: str, assignee_user_id: str) -> ProjectAssignee:
        """Assign a user to a project, giving them a review task: they can link that project's reports to studies, and the project shows up in their `tasks` resource. Admin only."""
        require_admin()
        async with request_context(current_user_id()) as ctx:
            project = await ctx.project_repo.get_project_by_id(project_id)
            if project is None:
                raise ValueError(f"Project {project_id} not found")

            try:
                created = await ctx.project_repo.add_project_assignee(project_id, assignee_user_id)
            except (ValueError, PermissionError) as exc:
                raise ValueError(str(exc)) from exc

            if not created:
                raise ValueError(f"{assignee_user_id} is already assigned to project {project_id}")

            await ctx.pubsub_service.publish_project_update(project_id)
            return ProjectAssignee(userId=assignee_user_id, numberReportsLinked=0)

    @server.tool()
    async def delete_project(
        project_id: str,
        confirmation: Annotated[ElicitationResult[ConfirmAction], Resolve(_confirm_delete_project)],
        confirm: bool = False,
    ) -> None:
        """Delete a project and all its associated reports, including their calculated embedding vectors. Admin only. Irreversible - asks the caller to confirm before deleting anything, or (if the client doesn't support confirmation prompts) requires confirm=True after you've confirmed with the user yourself."""
        if not _confirmed(confirmation):
            raise ValueError("Not confirmed - no changes were made.")

        async with request_context(current_user_id()) as ctx:
            project = await ctx.project_repo.get_project_by_id(project_id)
            if project is None:
                raise ValueError(f"Project {project_id} not found")

            report_ids = await ctx.project_repo.get_project_associated_report_ids(project_id)
            await ctx.project_repo.delete_project(project_id)
            await ctx.vectorstore_service.delete_vectors_by_report_ids(report_ids)
            await ctx.pubsub_service.publish_project_update(project_id)

    @server.tool()
    async def remove_project_task(
        project_id: str,
        assignee_user_id: str,
        confirmation: Annotated[ElicitationResult[ConfirmAction], Resolve(_confirm_remove_project_task)],
        confirm: bool = False,
    ) -> None:
        """Remove a user's assignment from a project. Admin only. Asks the caller to confirm before removing it, or (if the client doesn't support confirmation prompts) requires confirm=True after you've confirmed with the user yourself."""
        if not _confirmed(confirmation):
            raise ValueError("Not confirmed - no changes were made.")

        async with request_context(current_user_id()) as ctx:
            project = await ctx.project_repo.get_project_by_id(project_id)
            if project is None:
                raise ValueError(f"Project {project_id} not found")

            try:
                removed = await ctx.project_repo.remove_project_assignee(project_id, assignee_user_id)
            except (ValueError, PermissionError) as exc:
                raise ValueError(str(exc)) from exc

            if not removed:
                raise ValueError(f"{assignee_user_id} is not assigned to project {project_id}")

            await ctx.pubsub_service.publish_project_update(project_id)
