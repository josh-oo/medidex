from fastapi import APIRouter, Depends, HTTPException
from .auth import is_verified_api_call

from ..services import get_maintenance_service, MaintenanceService
from ..services import get_readiness_service, ReadinessService

from typing import Dict, Any

router = APIRouter(tags=["maintenance"])

@router.post("/maintenance/vectorstore/clean_up", dependencies=[Depends(is_verified_api_call)], summary="Clean up vectorstore, remove orphan nodes.")
async def vectorstore_clean_up(maintenance_service : MaintenanceService = Depends(get_maintenance_service)):
    return await maintenance_service.vectorstore_clean_up()

@router.get("/readyz", summary="Health check endpoint for readiness probe")
async def readyz(readiness_service : ReadinessService = Depends(get_readiness_service)) -> Dict[str, Any]:
    result = await readiness_service.readyz()

    if result['status'] != "ready":
        raise HTTPException(status_code=503, detail=result)
    
    return result


