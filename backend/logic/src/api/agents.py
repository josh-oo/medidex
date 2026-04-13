from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse
from ..services import get_agent_service, get_question_answering_service, AutomationService, QuestionAnsweringService


from .auth import is_verified_api_call

router = APIRouter(tags=["agents"], dependencies=[Depends(is_verified_api_call)])

@router.get("/reports/{report_id}/chat", summary="Get the current chat history.")
async def chat_history(report_id : int, agent_service: QuestionAnsweringService = Depends(get_question_answering_service)):
    return await agent_service.get_history(report_id)

@router.post("/reports/{report_id}/chat", summary="Get the current chat history.")
async def chat_question(report_id: int, question: str = Body(..., embed=False, description="Question to ask about the prediction"),agent_service: QuestionAnsweringService = Depends(get_question_answering_service)):
    return await agent_service.ask_me(report_id, question)

@router.delete("/reports/{report_id}/chat", summary="Delete the current chat history.")
async def chat_delete(report_id: int, agent_service: QuestionAnsweringService = Depends(get_question_answering_service)):
    await agent_service.delete_chat(report_id)
    return await agent_service.get_history(report_id)

@router.get("/reports/{report_id}/prediction/chat", summary="Get the current chat history.")
async def chat_history(report_id : int, agent_service: AutomationService = Depends(get_agent_service)):
    return await agent_service.get_history(report_id)

@router.post("/reports/{report_id}/prediction/chat", summary="Get the current chat history.")
async def chat_question(report_id: int, question: str = Body(..., embed=False, description="Question to ask about the prediction"),agent_service: AutomationService = Depends(get_agent_service),):
    return await agent_service.ask_me(report_id, question)

@router.get("/reports/{report_id}/prediction/stream", summary="Stream agent execution for finding a matching study.")
async def predict_stream(report_id : int, agent_service: AutomationService = Depends(get_agent_service)):
    return StreamingResponse(agent_service.report_matching_stream(report_id), media_type="text/event-stream")

@router.get("/reports/{report_id}/prediction", summary="Find a matching existing study or suggest a new study based on AI.")
async def predict(report_id : int, agent_service : AutomationService = Depends(get_agent_service)):
    return await agent_service.report_matching(report_id)