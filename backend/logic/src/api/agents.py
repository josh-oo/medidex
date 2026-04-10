from fastapi import APIRouter
from fastapi import Depends
from ..services import get_agent_service, AgentService


from .auth import is_verified_api_call

router = APIRouter(tags=["agents"], dependencies=[Depends(is_verified_api_call)])

@router.get("/reports/{report_id}/prediction", summary="Find a matching existing study or suggest a new study based on AI.")
async def predict(agent_service : AgentService = Depends(get_agent_service)):
    return await agent_service.ainvoke()