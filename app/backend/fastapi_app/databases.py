import os
import re
import tempfile
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Path, Request, Response
from fastapi.responses import FileResponse
from sse_starlette import EventSourceResponse
from starlette.background import BackgroundTask

from src.background.wrapper import run_criteria_changed, run_import_database
from src.context import RequestContext
from src.services.database import DatabaseImportError, DatabaseNotFoundError, DatabaseOwnerError
from src.services.upload import UploadLengthError, UploadNotFoundError, UploadOffsetError
from src.utils.archive import DatabaseArchive, DatabaseArchiveError
from src.utils.dto import Database, DatabaseImport, DatabasePayload, OwnerTransfer, DatabaseStage, DatabaseStorage, DatabaseUpdate, EligibilityCategory, EligibilitySchema
from src.utils.eligibility import ELIGIBILITY_CONFIG, EligibilityCriterion

from .admin import require_owner_candidate
from .auth import is_admin, is_verified_api_call, is_verified_user
from .deps import get_context

router = APIRouter(tags=["databases"])


def _file_name(name: str) -> str:
    """The name of a database as a file name, e.g. "Oncology trials" -> "oncology-trials"."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "database"

database_id_path = Path(..., description="The id of the study database")


async def check_database_owner(database_id: int = database_id_path, ctx: RequestContext = Depends(get_context)) -> None:
    """404/403 unless the caller owns the study database: only its owner changes, exports and hands it over."""
    try:
        await ctx.database_service.ensure_owner(database_id)
    except DatabaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DatabaseOwnerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
upload_id_path = Path(..., description="The id of the upload: the last segment of its URL (POST /databases/uploads)")


@router.get("/databases", dependencies=[Depends(is_verified_api_call)], summary="Get the study databases, each with its number of studies and reports.")
async def get_databases(ctx: RequestContext = Depends(get_context)) -> List[Database]:
    return await ctx.database_service.get_databases()


@router.get(
    "/eligibility-schema",
    dependencies=[Depends(is_verified_api_call)],
    summary="The categories of the eligibility criteria of the study databases, in their order: the elements of PICO and the study, each followed by the relations of the study ontology in it (config/medidex-study.yaml).",
)
async def get_eligibility_schema() -> EligibilitySchema:
    return EligibilitySchema(
        categories=[EligibilityCategory(key=key, **category.model_dump(include={"path", "description", "color"})) for key, category in ELIGIBILITY_CONFIG.categories.items()]
    )


@router.post("/databases", dependencies=[Depends(is_admin)], summary="Create a new, empty study database.", status_code=201)
async def create_database(payload: DatabasePayload, ctx: RequestContext = Depends(get_context)) -> Database:
    try:
        return await ctx.database_service.create_database(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/databases/{database_id}",
    dependencies=[Depends(check_database_owner)],
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


@router.put(
    "/databases/{database_id}/owner",
    dependencies=[Depends(check_database_owner)],
    summary="Hand a study database, with its updates, over to another user.",
    description="Only its owner can, to any approved user. From then on the new owner changes and exports it and uploads, assigns, merges and deletes its updates.",
)
async def transfer_database(
    body: OwnerTransfer, database_id: int = database_id_path, ctx: RequestContext = Depends(get_context)
) -> Database:
    await require_owner_candidate(body.ownerId)
    try:
        return await ctx.database_service.transfer_database(database_id, body.ownerId)
    except DatabaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/databases/{database_id}/storage",
    dependencies=[Depends(check_database_owner)],
    summary="What a study database takes in storage: its data, its search index and its PDFs (estimates).",
)
async def get_database_storage(database_id: int = database_id_path, ctx: RequestContext = Depends(get_context)) -> DatabaseStorage:
    try:
        return await ctx.database_service.get_storage(database_id)
    except DatabaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# The uploads of exported databases follow the tus protocol (https://tus.io, version 1.0.0 with its creation and
# termination extensions), so that a tus client (tus-js-client in the frontend) sends them: in parts, since a proxy in
# front of the backend may limit the size of a request (a Cloudflare tunnel to 100 MB) while an archive can be many GB,
# and going on after a part failed or the page was loaded again. A finished upload is imported by its id
# (POST /databases/import); one that is not is removed after a day.
TUS_VERSION = "1.0.0"
TUS_HEADERS = {"Tus-Resumable": TUS_VERSION}


def tus_resumable(tus_resumable: Optional[str] = Header(None)) -> None:
    """Every tus request but OPTIONS names the version of the protocol it speaks."""
    if tus_resumable != TUS_VERSION:
        raise HTTPException(status_code=412, detail=f"Only tus {TUS_VERSION} is supported.", headers={"Tus-Version": TUS_VERSION})


def _upload_error(exc: Exception) -> HTTPException:
    status = {UploadNotFoundError: 404, UploadOffsetError: 409, UploadLengthError: 413}[type(exc)]
    return HTTPException(status_code=status, detail=str(exc), headers=TUS_HEADERS)


@router.options("/databases/uploads", summary="What the tus server of the uploads supports.", status_code=204)
async def describe_uploads() -> Response:
    return Response(status_code=204, headers={**TUS_HEADERS, "Tus-Version": TUS_VERSION, "Tus-Extension": "creation,termination"})


@router.post(
    "/databases/uploads",
    dependencies=[Depends(is_verified_user), Depends(tus_resumable)],
    summary="Start the upload of an exported database (tus creation); its URL is the Location of the answer.",
    status_code=201,
)
async def start_upload(
    request: Request,
    upload_length: int = Header(..., ge=0, description="The size of the file in bytes."),
    ctx: RequestContext = Depends(get_context),
) -> Response:
    upload_id = ctx.upload_service.start(upload_length)
    # A path, not a URL: behind a TLS-terminating proxy the backend does not know the scheme the client used.
    return Response(status_code=201, headers={**TUS_HEADERS, "Location": f"{request.url.path.rstrip('/')}/{upload_id}"})


@router.head(
    "/databases/uploads/{upload_id}",
    dependencies=[Depends(is_verified_user), Depends(tus_resumable)],
    summary="How much of an upload has arrived (Upload-Offset): where its next part starts.",
)
async def get_upload(upload_id: str = upload_id_path, ctx: RequestContext = Depends(get_context)) -> Response:
    try:
        received, length = ctx.upload_service.status(upload_id)
    except UploadNotFoundError as exc:
        raise _upload_error(exc) from exc
    return Response(
        status_code=200,
        headers={**TUS_HEADERS, "Upload-Offset": str(received), "Upload-Length": str(length), "Cache-Control": "no-store"},
    )


@router.patch(
    "/databases/uploads/{upload_id}",
    dependencies=[Depends(is_verified_user), Depends(tus_resumable)],
    summary="Append the next part of an upload, the raw bytes as the body (application/offset+octet-stream).",
    description="Upload-Offset is where the part starts: what has arrived so far, or the request is rejected (409) and "
                "nothing appended. A part that broke off is kept as far as it came; HEAD says where to go on from.",
    status_code=204,
)
async def append_upload(
    request: Request,
    upload_id: str = upload_id_path,
    upload_offset: int = Header(..., ge=0),
    content_type: Optional[str] = Header(None),
    ctx: RequestContext = Depends(get_context),
) -> Response:
    if content_type != "application/offset+octet-stream":
        raise HTTPException(status_code=415, detail="A part is sent as application/offset+octet-stream.", headers=TUS_HEADERS)
    try:
        received = await ctx.upload_service.append(upload_id, upload_offset, request.stream())
    except (UploadNotFoundError, UploadOffsetError, UploadLengthError) as exc:
        raise _upload_error(exc) from exc
    return Response(status_code=204, headers={**TUS_HEADERS, "Upload-Offset": str(received)})


@router.delete(
    "/databases/uploads/{upload_id}",
    dependencies=[Depends(is_verified_user), Depends(tus_resumable)],
    summary="Discard an upload that is not to be imported (tus termination).",
    status_code=204,
)
async def discard_upload(upload_id: str = upload_id_path, ctx: RequestContext = Depends(get_context)) -> Response:
    try:
        ctx.upload_service.discard(upload_id)
    except UploadNotFoundError as exc:
        raise _upload_error(exc) from exc
    return Response(status_code=204, headers=TUS_HEADERS)


@router.post(
    "/databases/import",
    dependencies=[Depends(is_admin)],
    summary="Create a study database with the studies, reports and PDFs of an exported one (the archive of GET /databases/{database_id}/export, or its database.json alone, without PDFs), uploaded with tus to POST /databases/uploads.",
    description="Answers at once, with the database to be (`importing`); it is imported, and then its reports are "
                "added to the vectorstore, in the background, as GET /databases/{database_id}/status streams. Until "
                "they are, its studies are found by the study search but not suggested for new reports. The upload is "
                "used up, also when the file is rejected.",
    status_code=202,
)
async def import_database(
    body: DatabaseImport,
    background_tasks: BackgroundTasks,
    ctx: RequestContext = Depends(get_context),
) -> Database:
    payload = DatabasePayload(name=body.name, description=body.description, eligibilityCriteria=body.eligibilityCriteria)
    try:
        source = ctx.upload_service.take(body.uploadId)
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UploadLengthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
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
async def stream_database_status(request: Request, database_id: int = database_id_path, ctx: RequestContext = Depends(get_context)) -> EventSourceResponse:
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
                yield status.model_dump_json()
                if status.stage in (DatabaseStage.ready, DatabaseStage.failed) or await request.is_disconnected():
                    break
                status = await status_service.get_next_status(pubsub)
        finally:
            await status_service.unsubscribe(database_id, pubsub)

    return EventSourceResponse(events())


@router.get(
    "/databases/{database_id}/export",
    dependencies=[Depends(check_database_owner)],
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
