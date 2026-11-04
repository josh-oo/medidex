import os
import re
import tempfile
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Path, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask

from pydantic import TypeAdapter, ValidationError

from src.background.wrapper import run_criteria_changed, run_import_database
from src.context import RequestContext
from src.services.database import DatabaseImportError, DatabaseNotFoundError
from src.utils.archive import DatabaseArchive, DatabaseArchiveError
from src.utils.dto import Database, DatabasePayload, DatabaseStage, DatabaseStorage, DatabaseUpdate, EligibilityCategory, EligibilitySchema
from src.utils.eligibility import ELIGIBILITY_CONFIG, EligibilityCriterion

from .auth import is_admin, is_verified_api_call
from .deps import get_context

router = APIRouter(tags=["databases"])


def _file_name(name: str) -> str:
    """The name of a database as a file name, e.g. "Oncology trials" -> "oncology-trials"."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "database"

database_id_path = Path(..., description="The id of the study database")


@router.get("/databases", dependencies=[Depends(is_verified_api_call)], summary="Get the study databases, each with its number of studies and reports.")
async def get_databases(ctx: RequestContext = Depends(get_context)) -> List[Database]:
    return await ctx.database_service.get_databases()


@router.get(
    "/eligibility-schema",
    dependencies=[Depends(is_verified_api_call)],
    summary="The categories of the eligibility criteria of the study databases, in their order, as configured in config/eligibility.yaml.",
)
async def get_eligibility_schema() -> EligibilitySchema:
    return EligibilitySchema(
        categories=[EligibilityCategory(key=key, **category.model_dump()) for key, category in ELIGIBILITY_CONFIG.categories.items()]
    )


@router.post("/databases", dependencies=[Depends(is_admin)], summary="Create a new, empty study database.", status_code=201)
async def create_database(payload: DatabasePayload, ctx: RequestContext = Depends(get_context)) -> Database:
    try:
        return await ctx.database_service.create_database(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/databases/{database_id}",
    dependencies=[Depends(is_admin)],
    summary="Rename a study database or change its description or eligibility criteria.",
    description="Changed criteria are checked again for the reports of its updates in the background (see ReportPostprocessor.criteria_changed).",
)
async def update_database(
    update: DatabaseUpdate,
    background_tasks: BackgroundTasks,
    database_id: int = database_id_path,
    ctx: RequestContext = Depends(get_context),
) -> Database:
    try:
        database = await ctx.database_service.update_database(database_id, update)
    except DatabaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if update.eligibilityCriteria is not None:
        background_tasks.add_task(run_criteria_changed, database_id, ctx.user_id)
    return database


@router.get(
    "/databases/{database_id}/storage",
    dependencies=[Depends(is_admin)],
    summary="What a study database takes in storage: its data, its search index and its PDFs (estimates).",
)
async def get_database_storage(database_id: int = database_id_path, ctx: RequestContext = Depends(get_context)) -> DatabaseStorage:
    try:
        return await ctx.database_service.get_storage(database_id)
    except DatabaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/databases/import",
    dependencies=[Depends(is_admin)],
    summary="Create a study database with the studies, reports and PDFs of an exported one (the archive of GET /databases/{database_id}/export, or its database.json alone, without PDFs).",
    description="Answers once the file is uploaded, with the database to be (`importing`); it is imported, and then its "
                "reports are added to the vectorstore, in the background, as GET /databases/{database_id}/status streams. "
                "Until they are, its studies are found by the study search but not suggested for new reports.",
    status_code=202,
)
async def import_database(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The exported database: a .medidex.zip archive (database.json and pdfs/), or a database.json without PDFs."),
    name: str = Form(..., min_length=1, max_length=200),
    description: Optional[str] = Form(None),
    eligibilityCriteria: str = Form(..., min_length=1, description="The criteria of the new database, a JSON list as in POST /databases."),
    ctx: RequestContext = Depends(get_context),
) -> Database:
    try:
        criteria = TypeAdapter(List[EligibilityCriterion]).validate_json(eligibilityCriteria)
        payload = DatabasePayload(name=name, description=description, eligibilityCriteria=criteria)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid eligibility criteria: {exc}") from exc
    # The upload is closed with the request, the import runs after it: it reads the same (temporary) file through a
    # handle of its own.
    source = os.fdopen(os.dup(file.file.fileno()), "rb")
    try:
        source.seek(0)
        archive = DatabaseArchive.open(source)
        database = await ctx.database_service.start_import(payload)
    except (DatabaseArchiveError, ValueError) as exc:
        source.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        source.close()
        raise
    background_tasks.add_task(run_import_database, database.databaseId, payload, archive, source, ctx.user_id)
    return database


@router.get(
    "/databases/{database_id}/status",
    dependencies=[Depends(is_verified_api_call)],
    summary="Stream where a study database is on its way to being usable: its import, then the indexing of its reports.",
    description="An SSE event per change, its data a DatabaseStatus; the first is where it is now. Ends once it is "
                "ready or its import failed.",
)
async def stream_database_status(request: Request, database_id: int = database_id_path, ctx: RequestContext = Depends(get_context)) -> StreamingResponse:
    status_service = ctx.database_status_service
    # Subscribed before the status is read: a change in between is not missed.
    pubsub = await status_service.subscribe(database_id)
    try:
        current = await ctx.database_service.get_status(database_id)
    except DatabaseNotFoundError as exc:
        await status_service.unsubscribe(database_id, pubsub)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # The session of the request is not needed while the stream waits.
    await ctx.db.close()

    async def events():
        status = current
        try:
            while True:
                yield f"data: {status.model_dump_json()}\n\n"
                if status.stage in (DatabaseStage.ready, DatabaseStage.failed) or await request.is_disconnected():
                    break
                status = await status_service.get_next_status(pubsub)
        finally:
            await status_service.unsubscribe(database_id, pubsub)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get(
    "/databases/{database_id}/export",
    dependencies=[Depends(is_admin)],
    summary="Export a study database as a zip archive: database.json (its studies with their fields, graphs, tags and reports) and the PDFs of its reports, which POST /databases/import reads.",
    response_class=FileResponse,
)
async def export_database(database_id: int = database_id_path, ctx: RequestContext = Depends(get_context)) -> FileResponse:
    # Written to a temporary file (PDFs make archives large) that is removed once it has been sent.
    handle, path = tempfile.mkstemp(suffix=".zip")
    try:
        with os.fdopen(handle, "wb") as target:
            name = await ctx.database_service.export_archive(database_id, target)
    except DatabaseNotFoundError as exc:
        os.remove(path)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        os.remove(path)
        raise
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{_file_name(name)}.medidex.zip",
        background=BackgroundTask(os.remove, path),
    )
