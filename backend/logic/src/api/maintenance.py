from fastapi import APIRouter, Depends
from .auth import is_verified_api_call

from ..services import get_maintenance_service, MaintenanceService

router = APIRouter(tags=["maintenance"], dependencies=[Depends(is_verified_api_call)])

@router.post("/maintenance/vectorstore/clean_up", summary="Clean up vectorstore, remove orphan nodes.")
async def vectorstore_clean_up(maintenance_service : MaintenanceService = Depends(get_maintenance_service)):
    return await maintenance_service.vectorstore_clean_up()


