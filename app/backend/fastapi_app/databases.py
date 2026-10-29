import os
import re
import tempfile
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Path, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from src.background.wrapper import run_index_database_reports
from src.context import RequestContext
from src.services.database import DatabaseImportError, DatabaseNotFoundError
from src.utils.archive import DatabaseArchive, DatabaseArchiveError
from src.utils.dto import Database, DatabasePayload, DatabaseUpdate

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


@router.post("/databases", dependencies=[Depends(is_admin)], summary="Create a new, empty study database.", status_code=201)
async def create_database(payload: DatabasePayload, ctx: RequestContext = Depends(get_context)) -> Database:
    return await ctx.database_service.create_database(payload)


@router.patch("/databases/{database_id}", dependencies=[Depends(is_admin)], summary="Rename a study database or change its description or eligibility criteria.")
async def update_database(update: DatabaseUpdate, database_id: int = database_id_path, ctx: RequestContext = Depends(get_context)) -> Database:
    try:
        return await ctx.database_service.update_database(database_id, update)
    except DatabaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/databases/import",
    dependencies=[Depends(is_admin)],
    summary="Create a study database with the studies, reports and PDFs of an exported one (the archive of GET /databases/{database_id}/export, or its database.json alone, without PDFs).",
    description="Its reports are added to the vectorstore in the background; until then its studies are found by the study search but not suggested for new reports.",
    status_code=201,
)
async def import_database(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The exported database: a .medidex.zip archive (database.json and pdfs/), or a database.json without PDFs."),
    name: str = Form(..., min_length=1, max_length=200),
    description: Optional[str] = Form(None),
    eligibilityCriteria: str = Form(..., min_length=1),
    ctx: RequestContext = Depends(get_context),
) -> Database:
    payload = DatabasePayload(name=name, description=description, eligibilityCriteria=eligibilityCriteria)
    try:
        database, report_ids = await ctx.database_service.import_database(payload, DatabaseArchive.open(file.file))
    except (DatabaseImportError, DatabaseArchiveError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if report_ids:
        background_tasks.add_task(run_index_database_reports, report_ids, ctx.user_id)
    return database


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
