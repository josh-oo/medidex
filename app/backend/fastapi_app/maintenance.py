from fastapi import APIRouter, Depends, HTTPException
from .auth import is_verified_api_call

from src.context import RequestContext
from .deps import get_context
from src.database.sessions import test_db
from src.services.maintenance import ReadinessService

from typing import Dict, Any

router = APIRouter(tags=["maintenance"])

@router.post("/maintenance/vectorstore/clean_up", dependencies=[Depends(is_verified_api_call)], summary="Clean up vectorstore, remove orphan nodes.")
async def vectorstore_clean_up(ctx: RequestContext = Depends(get_context)):
    return await ctx.maintenance_service.vectorstore_clean_up()

@router.get("/readyz", summary="Health check endpoint for readiness probe")
async def readyz(ctx: RequestContext = Depends(get_context)) -> Dict[str, Any]:
    db_status = await test_db(ctx.db)
    readiness_service = ReadinessService(
        db_ready=db_status,
        vectorstore=ctx.vectorstore_service,
        embedding_service=ctx.embedding_service,
    )
    result = await readiness_service.readyz()

    if result['status'] != "ready":
        raise HTTPException(status_code=503, detail=result)

    return result

