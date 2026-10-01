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
import base64
import binascii
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Set, Union

from mcp.server import MCPServer
from mcp.types import BlobResourceContents, EmbeddedResource, ToolAnnotations
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
from src.database.repositories.study import DuplicateShortNameError
from src.services.authorization import (
    AuthenticationRequiredError,
    ProjectAccessDeniedError,
    ReportAccessDeniedError,
    ReportNotFoundError,
)
from src.services.core import ReportNotInSourceProjectError, ReportNotReadyError
from src.services.project import (
    ProjectAssigneeAlreadyExistsError,
    ProjectNotFoundError,
)
from src.utils.dto import (
    Assignee,
    FilterMode,
    Page,
    Project,
    Report,
    ReportCuration,
    ReportIntake,
    ReportPreview,
    Study,
    StudyCandidate,
    StudyFull,
    StudyPayload,
    Tag,
    Task,
    reports_to_base_dto,
    reports_to_dto,
    studies_to_dto,
)
from src.utils.pagination import decode_cursor, encode_cursor, InvalidCursorError
from src.utils.query_parser import QueryNode
from src.utils.ris_parser import RisParseError

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
            title="Search Studies",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def search_studies(
        query: Union[str, QueryNode],
        limit: int = 10,
        cursor: Optional[str] = None,
    ) -> Page[Study]:
        """Search across all studies to find candidates for "studification" (linking a
        report to its parent study).

        Pass a plain string for free-text search, matched against study name, trial ID,
        author and intervention - e.g. query="NCT04267848" or query="Smith diabetes".

        Pass a structured filter object to instead AND/OR-combine field==value
        conditions (each a case-insensitive substring match) - e.g. to find studies
        about Metformin for Diabetes:
          {"type": "and", "operands": [
            {"type": "comparison", "field": "intervention", "value": "Metformin"},
            {"type": "comparison", "field": "condition", "value": "Diabetes"}
          ]}
        "and"/"or" operands can themselves be "and"/"or" groups, nested as deep as
        needed - there's no operator-precedence ambiguity to worry about, unlike a
        string query language, since the nesting itself says exactly what groups with
        what. Valid `field` values: name (the study's short name), trialId, author,
        status, country, intervention, condition, outcome, participant, design.

        Returns at most `limit` studies per page (default 10, max 50). Pass the
        previous response's `nextCursor` back as `cursor` to fetch the next page;
        omit `cursor` for the first page.
        """
        limit = max(1, min(limit, 50))
        try:
            offset = decode_cursor(cursor) if cursor else 0
        except InvalidCursorError as exc:
            raise ToolError(str(exc)) from exc

        async with request_context(current_user_id()) as ctx:
            if isinstance(query, str):
                studies, has_more = await ctx.study_service.search_studies(query, limit, offset)
            else:
                studies, has_more = await ctx.study_service.search_studies_advanced(query, limit, offset)

        next_cursor = encode_cursor(offset + limit) if has_more else None
        return Page[Study](items=studies, nextCursor=next_cursor)

    @server.tool(
        annotations=ToolAnnotations(
            title="Search Candidate Studies",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def search_candidate_studies(
        report_id: int,
        limit: int = 10,
        cursor: Optional[str] = None,
        negative_studies: Optional[List[int]] = None,
        negative_reports: Optional[List[int]] = None,
        return_details: bool = False,
    ) -> Page[StudyCandidate]:
        """Find candidate parent studies for a specific report's "studification",
        ranked by relevance instead of matched by query - the AI-assisted counterpart
        to search_studies. Scores every study by embedding similarity to the report's
        own content (plus any study already linked to a report in the same project
        that scores well too), rather than matching a query string/filter against
        study fields; trial-id/author matches aren't mixed into this ranking, so pair
        this with search_studies when a specific trial id or author is known. Each
        result carries its `relevance` score (0-1), highest first.

        The report must have finished PDF/embedding processing first (see
        get_intake_reports's `hasPdf` and upload_report_pdf) or this raises an error
        saying so.

        Pass `negative_studies` to exclude specific studies from the ranking, or
        `negative_reports` to downrank studies matched mainly through those reports
        (e.g. ones the researcher already rejected as false positives). Pass
        return_details=True to include each candidate's underlying match sources -
        for debugging relevance, not normally needed.

        Returns at most `limit` candidates per page (default 10, max 50). Pass the
        previous response's nextCursor back as `cursor` to fetch the next page.
        """
        limit = max(1, min(limit, 50))
        async with request_context(current_user_id()) as ctx:
            try:
                return await ctx.study_similarity_service.get_similar_studies_page(
                    report_id,
                    None,
                    limit,
                    cursor,
                    None,
                    negative_studies,
                    negative_reports,
                    return_details,
                    ctx.user_id,
                )
            except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
                raise ToolError(str(exc)) from exc
            except (ReportNotReadyError, ReportNotInSourceProjectError) as exc:
                raise ToolError(str(exc)) from exc
            except InvalidCursorError as exc:
                raise ToolError(str(exc)) from exc

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

    get_report_pdf is the one deliberate exception to "cheap and side-effect-free
    lookups only": a whole PDF as inline tool output (base64, via EmbeddedResource/
    BlobResourceContents - see below) floods the model's context with a binary
    blob it can't read as text. It's still exposed, as an explicit, individually
    invoked tool a client only calls when it actually needs the bytes (e.g. to
    hand off to a PDF-reading tool downstream) - never returned as part of a list
    response like get_intake_reports, which only ever surfaces `hasPdf`.
    """

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Details",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study(study_id: int) -> StudyFull:
        """Full details for a study by its numeric id, including its linked reports and
        tag-like aspects (interventions, conditions, outcomes, participants, design) -
        each as a first page of up to 10 items. If a list's `nextCursor` is set, there
        are more than 10: page through that specific list with its own dedicated tool
        (get_study_reports, get_study_interventions, get_study_conditions,
        get_study_outcomes, get_study_participants, or get_study_design), passing that
        `nextCursor` as `cursor`."""
        limit = 10
        async with request_context(current_user_id()) as ctx:
            study = await ctx.study_repo.get_study_by_id(study_id)
            if study is None:
                raise ToolError(f"Study {study_id} not found")

            reports, reports_more = await ctx.study_repo.get_study_reports_by_study_id_page(study_id, limit=limit, offset=0)
            interventions, interventions_more = await ctx.study_repo.get_study_interventions_single_page(study_id, limit=limit, offset=0)
            conditions, conditions_more = await ctx.study_repo.get_study_conditions_single_page(study_id, limit=limit, offset=0)
            outcomes, outcomes_more = await ctx.study_repo.get_study_outcomes_single_page(study_id, limit=limit, offset=0)
            participants, participants_more = await ctx.study_repo.get_study_participants_single_page(study_id, limit=limit, offset=0)
            design, design_more = await ctx.study_repo.get_study_design_single_page(study_id, limit=limit, offset=0)

        next_cursor = encode_cursor(limit)
        study_dto = studies_to_dto([study])[0]
        return StudyFull(
            **study_dto.model_dump(),
            reports=Page[ReportPreview](items=reports_to_base_dto(reports), nextCursor=next_cursor if reports_more else None),
            interventions=Page[Tag](items=interventions, nextCursor=next_cursor if interventions_more else None),
            conditions=Page[Tag](items=conditions, nextCursor=next_cursor if conditions_more else None),
            outcomes=Page[Tag](items=outcomes, nextCursor=next_cursor if outcomes_more else None),
            participants=Page[Tag](items=participants, nextCursor=next_cursor if participants_more else None),
            design=Page[Tag](items=design, nextCursor=next_cursor if design_more else None),
        )

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Reports",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_reports(study_id: int, limit: int = 10, cursor: Optional[str] = None) -> Page[Report]:
        """Reports already linked to a study (the "studification" result for that study), paginated."""
        limit = max(1, min(limit, 100))
        try:
            offset = decode_cursor(cursor) if cursor else 0
        except InvalidCursorError as exc:
            raise ToolError(str(exc)) from exc

        async with request_context(current_user_id()) as ctx:
            reports, has_more = await ctx.study_repo.get_study_reports_by_study_id_page(
                study_id, limit=limit, offset=offset
            )

        next_cursor = encode_cursor(offset + limit) if has_more else None
        return Page[Report](items=reports_to_dto(reports), nextCursor=next_cursor)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Interventions",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_interventions(study_id: int, limit: int = 10, cursor: Optional[str] = None) -> Page[Tag]:
        """Interventions for a specific study (e.g. 'Placebo', 'Group Therapy', ...), paginated."""
        limit = max(1, min(limit, 100))
        try:
            offset = decode_cursor(cursor) if cursor else 0
        except InvalidCursorError as exc:
            raise ToolError(str(exc)) from exc

        async with request_context(current_user_id()) as ctx:
            result, has_more = await ctx.study_repo.get_study_interventions_single_page(
                study_id, limit=limit, offset=offset
            )

        next_cursor = encode_cursor(offset + limit) if has_more else None
        return Page[Tag](items=result, nextCursor=next_cursor)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Conditions",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_conditions(study_id: int, limit: int = 10, cursor: Optional[str] = None) -> Page[Tag]:
        """The health conditions of participants in a specific study (e.g. 'COVID-19', 'Diabetes', ...), paginated."""
        limit = max(1, min(limit, 100))
        try:
            offset = decode_cursor(cursor) if cursor else 0
        except InvalidCursorError as exc:
            raise ToolError(str(exc)) from exc

        async with request_context(current_user_id()) as ctx:
            result, has_more = await ctx.study_repo.get_study_conditions_single_page(
                study_id, limit=limit, offset=offset
            )

        next_cursor = encode_cursor(offset + limit) if has_more else None
        return Page[Tag](items=result, nextCursor=next_cursor)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Outcomes",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_outcomes(study_id: int, limit: int = 10, cursor: Optional[str] = None) -> Page[Tag]:
        """Outcomes for a specific study (e.g. 'Mortality', 'Hospitalization', ...), paginated."""
        limit = max(1, min(limit, 100))
        try:
            offset = decode_cursor(cursor) if cursor else 0
        except InvalidCursorError as exc:
            raise ToolError(str(exc)) from exc

        async with request_context(current_user_id()) as ctx:
            result, has_more = await ctx.study_repo.get_study_outcomes_single_page(
                study_id, limit=limit, offset=offset
            )

        next_cursor = encode_cursor(offset + limit) if has_more else None
        return Page[Tag](items=result, nextCursor=next_cursor)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Participants",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_participants(study_id: int, limit: int = 10, cursor: Optional[str] = None) -> Page[Tag]:
        """Participant description for a specific study (e.g. Male, Female, Adult, Child, ...), paginated"""
        limit = max(1, min(limit, 100))
        try:
            offset = decode_cursor(cursor) if cursor else 0
        except InvalidCursorError as exc:
            raise ToolError(str(exc)) from exc

        async with request_context(current_user_id()) as ctx:
            result, has_more = await ctx.study_repo.get_study_participants_single_page(
                study_id, limit=limit, offset=offset
            )

        next_cursor = encode_cursor(offset + limit) if has_more else None
        return Page[Tag](items=result, nextCursor=next_cursor)

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Study Design",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_study_design(study_id: int, limit: int = 10, cursor: Optional[str] = None) -> Page[Tag]:
        """The study design of the corresponding study ('Randomized Controlled Trial', 'Controlled Clinical Trial'), paginated"""
        limit = max(1, min(limit, 100))
        try:
            offset = decode_cursor(cursor) if cursor else 0
        except InvalidCursorError as exc:
            raise ToolError(str(exc)) from exc

        async with request_context(current_user_id()) as ctx:
            result, has_more = await ctx.study_repo.get_study_design_single_page(
                study_id, limit=limit, offset=offset
            )

        next_cursor = encode_cursor(offset + limit) if has_more else None
        return Page[Tag](items=result, nextCursor=next_cursor)

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
        """All persons (usually only authors) associated with a specific study."""
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
        """Full details (including abstract) for a single report by its numeric id."""
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
        """The studies linked to a specific report."""
        async with request_context(current_user_id()) as ctx:
            await require_report_access(report_id, ctx)
            result = await ctx.report_repo.get_linked_studies(report_id)
            return studies_to_dto(result)

    @server.tool(
        annotations=ToolAnnotations(
            title="Link Report to Study",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def link_report_to_study(report_id: int, study_id: int) -> None:
        """Link a report to an existing parent study - the "studification" action.
        Pick `study_id` from search_studies or search_candidate_studies. Linking a
        report that's already linked to this study is a no-op."""
        async with request_context(current_user_id()) as ctx:
            try:
                await ctx.linkage_service.link_existing_study_to_report(report_id, study_id, ctx.user_id)
            except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
                raise ToolError(str(exc)) from exc

    @server.tool(
        annotations=ToolAnnotations(
            title="Link Report to New Study",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def link_report_to_new_study(
        report_id: int,
        short_name: str,
        status: str,
        countries: List[str],
        number_participants: Optional[str] = None,
        duration: Optional[str] = None,
        comparison: Optional[str] = None,
        trial_id: Optional[str] = None,
    ) -> Study:
        """Create a brand-new parent study and link this report to it in one step -
        use this instead of link_report_to_study when search_studies and
        search_candidate_studies found no existing match. `short_name` must be
        unique across all studies."""
        payload = StudyPayload(
            shortName=short_name,
            status=status,
            countries=countries,
            numberParticipants=number_participants,
            duration=duration,
            comparison=comparison,
            trialId=trial_id,
        )
        async with request_context(current_user_id()) as ctx:
            try:
                new_study = await ctx.linkage_service.create_study_and_link_to_report(report_id, payload, ctx.user_id)
            except (ReportNotFoundError, AuthenticationRequiredError, ReportAccessDeniedError) as exc:
                raise ToolError(str(exc)) from exc
            except DuplicateShortNameError as exc:
                raise ToolError(f"Study shortName '{short_name}' already exists") from exc
            return studies_to_dto([new_study])[0]

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Project Reports",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_project_reports(
        project_id: str,
        search: Optional[str] = None,
        processed: FilterMode = FilterMode.any,
        flagged: FilterMode = FilterMode.any,
        new_study: FilterMode = FilterMode.any,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Page[ReportCuration]:
        """The normal curation view for a project's reports - the "ready" reports, as
        opposed to get_intake_reports's admin-only queue: never includes reports still
        being processed (not yet embedded/PDF-ready), so every result here is ready to
        review and studify. Each result carries its already-linked studies
        (`assignedStudies`) and flag state.

        Pass processed/flagged/new_study="only" or "exclude" to filter down (default
        "any" returns both): `processed` filters by whether the report already has at
        least one linked study (use "exclude" to find reports still needing
        studification), `new_study` by whether a linked study was created after the
        report itself. Restricted to the project's assignees (or whoever uploaded it).

        Returns at most `limit` reports per page (default 50, max 200); pass the
        previous response's nextCursor back as `cursor` to fetch the next page."""
        limit = max(1, min(limit, 200))
        async with request_context(current_user_id()) as ctx:
            try:
                return await ctx.project_service.get_reports_page(
                    project_id,
                    search=search,
                    processed=processed,
                    flagged=flagged,
                    new_study=new_study,
                    cursor=cursor,
                    limit=limit,
                )
            except InvalidCursorError as exc:
                raise ToolError(str(exc)) from exc
            except ProjectAccessDeniedError as exc:
                raise ToolError(str(exc)) from exc

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Intake Reports",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_intake_reports(
        project_id: str,
        search: Optional[str] = None,
        with_pdf: FilterMode = FilterMode.any,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Page[ReportIntake]:
        """The admin intake view for a project's newly-entered reports - the
        "studification" queue: unlike get_study_reports (which lists reports
        already linked to a *study*), this lists a *project's* reports, and unlike
        get_project's own `reports` page, it always includes reports still being
        processed (not yet embedded, or without a PDF yet), so an admin can watch
        reports arrive and see which ones still need a PDF before linking them to
        a study.

        Pass with_pdf="only" or "exclude" to filter down to reports that do/don't
        have a PDF yet (default "any" returns both) - check each result's `hasPdf`
        field, then use get_report_pdf or upload_report_pdf accordingly. Admin only.

        Returns at most `limit` reports per page (default 50, max 200); pass the
        previous response's nextCursor back as `cursor` to fetch the next page."""
        require_admin()
        limit = max(1, min(limit, 200))
        async with request_context(current_user_id()) as ctx:
            try:
                return await ctx.project_service.get_intake_reports_page(
                    project_id, search=search, with_pdf=with_pdf, cursor=cursor, limit=limit
                )
            except InvalidCursorError as exc:
                raise ToolError(str(exc)) from exc

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Report PDF",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_report_pdf(report_id: int) -> EmbeddedResource:
        """The fulltext PDF for a report, if one has been uploaded or auto-found for
        it already - check `hasPdf` on get_intake_reports first, or just call this
        and handle the "not found" error, since a fresh project's PDF search runs
        in the background and can still be in progress. If there's no PDF yet, use
        upload_report_pdf to supply one instead.

        Returns the PDF as a base64-encoded blob resource (application/pdf)."""
        async with request_context(current_user_id()) as ctx:
            await require_report_access(report_id, ctx)
            try:
                pdf_path = await ctx.document_service.get_path(report_id)
            except Exception as exc:
                raise ToolError(f"PDF file not found for report {report_id}.") from exc
            content = await asyncio.to_thread(Path(pdf_path).read_bytes)

        return EmbeddedResource(
            resource=BlobResourceContents(
                uri=f"medidex://reports/{report_id}/pdf",
                mime_type="application/pdf",
                blob=base64.b64encode(content).decode("ascii"),
            )
        )

    @server.tool(
        annotations=ToolAnnotations(
            title="Upload Report PDF",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def upload_report_pdf(
        report_id: int,
        file_content_base64: str,
        filename: str = "report.pdf",
    ) -> Dict[str, Any]:
        """Upload the fulltext PDF for a report that doesn't have one yet (see
        get_intake_reports's `hasPdf` field to find which ones). `file_content_base64`
        is the raw PDF file's bytes, base64-encoded. Replaces any existing PDF for
        this report. Admin only."""
        require_admin()
        if not filename.lower().endswith(".pdf"):
            raise ToolError("File must have a .pdf extension.")
        try:
            content = base64.b64decode(file_content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ToolError(f"file_content_base64 is not valid base64: {exc}") from exc
        if not content.startswith(b"%PDF-"):
            raise ToolError("File does not look like a PDF (missing %PDF- header).")

        async with request_context(current_user_id()) as ctx:
            upload = _InMemoryUpload(content, filename)
            try:
                result = await ctx.document_service.upload_pdf(report_id, upload)
                await ctx.report_repo.db.commit()
                await ctx.pubsub_service.publish_report_update(report_id)
                return result
            except Exception as exc:
                await ctx.report_repo.db.rollback()
                raise ToolError(f"Failed to save PDF: {exc}") from exc

    @server.tool(
        annotations=ToolAnnotations(
            title="Get Project",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_project(project_id: str) -> Project:
        """Details and progress for a single project. Admin only."""
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
                result = await ctx.project_service.create_project(project_name, upload)
            except RisParseError as exc:
                raise ToolError(str(exc)) from exc
            if result is None:
                raise ToolError("Project already exists")
            project, report_ids = result

            _fire_and_forget(run_process_report_background(project.projectId, report_ids, ctx.user_id))

            return project

    @server.tool(
        annotations=ToolAnnotations(
            title="List Projects",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def list_projects() -> List[Project]:
        """List all current projects, with embedding/assignment progress for each. Admin only."""
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
    async def list_tasks() -> List[Task]:
        """List the authenticated user's pending review tasks: every project they're assigned to, with their personal study-link counts. """
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
    async def assign_project_task(project_id: str, assignee_user_id: str) -> Assignee:
        """Assign a user to a project, giving them a review task: they can link that project's reports to studies, and the project shows up in their `tasks` resource. Admin only."""
        require_admin()
        async with request_context(current_user_id()) as ctx:
            try:
                return await ctx.project_service.assign_user_to_project(project_id, assignee_user_id)
            except ProjectNotFoundError as exc:
                raise ToolError(str(exc)) from exc
            except ProjectAssigneeAlreadyExistsError as exc:
                raise ToolError(str(exc)) from exc
            except (ValueError, PermissionError) as exc:
                raise ToolError(str(exc)) from exc

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
            try:
                await ctx.project_service.delete_project(project_id)
            except ProjectNotFoundError as exc:
                raise ToolError(str(exc)) from exc
