from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from ..services import get_agent_service, AgentService


from .auth import is_verified_api_call

router = APIRouter(tags=["agents"], dependencies=[Depends(is_verified_api_call)])

@router.get("/reports/{report_id}/prediction", summary="Find a matching existing study or suggest a new study based on AI.")
async def predict(agent_service : AgentService = Depends(get_agent_service)):
    return await agent_service.ainvoke()


@router.get("/reports/{report_id}/prediction/stream", summary="Stream agent execution for finding a matching study.")
async def predict_stream(agent_service: AgentService = Depends(get_agent_service)):
    return StreamingResponse(agent_service.astream(), media_type="text/event-stream")