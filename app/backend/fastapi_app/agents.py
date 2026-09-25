from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse

from src.context import RequestContext
from src.services.agent import AutomationService, QuestionAnsweringService
from src.utils.llm.agent import get_checkpointer

from .auth import is_verified_api_call
from .deps import get_context

router = APIRouter(tags=["agents"], dependencies=[Depends(is_verified_api_call)])

cutoff_query = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")

async def get_agent_service(
    ctx : RequestContext = Depends(get_context),
    model: str = Query("gpt-5-nano", description="LLM model name to use for study prediction"),
    checkpointer: Any = Depends(get_checkpointer),
    cutoff: Optional[str] = cutoff_query,
) -> AutomationService:
    await checkpointer.setup()
    return AutomationService(
        user_id=ctx.user_id,
        report_repo=ctx.report_repo,
        study_repo=ctx.study_repo,
        document_service=ctx.document_service,
        study_similarity_service=ctx.study_similarity_service,
        checkpointer=checkpointer,
        model=model,
        cutoff=cutoff,
    )

async def get_question_answering_service(
    ctx : RequestContext = Depends(get_context),
    model: str = Query("gpt-5-nano", description="LLM model name to use for report question answering"),
    checkpointer: Any = Depends(get_checkpointer),
) -> QuestionAnsweringService:
    await checkpointer.setup()
    return QuestionAnsweringService(
        user_id=ctx.user_id,
        report_repo=ctx.report_repo,
        study_repo=ctx.study_repo,
        document_service=ctx.document_service,
        study_similarity_service=ctx.study_similarity_service,
        checkpointer=checkpointer,
        model=model,
        cutoff=None,
    )

@router.get("/reports/{report_id}/chat", summary="Get the current chat history for a given report.")
async def chat_history(report_id : int, agent_service: QuestionAnsweringService = Depends(get_question_answering_service)):
    return await agent_service.get_history(report_id)

@router.post("/reports/{report_id}/chat", summary="Text with the chatbot.")
async def chat_question(report_id: int, question: str = Body(..., embed=False, description="Question to ask about the prediction"),agent_service: QuestionAnsweringService = Depends(get_question_answering_service)):
    return await agent_service.ask_me(report_id, question)

@router.delete("/reports/{report_id}/chat", summary="Delete the current chat history.")
async def chat_delete(report_id: int, agent_service: QuestionAnsweringService = Depends(get_question_answering_service)):
    await agent_service.delete_chat(report_id)
    return await agent_service.get_history(report_id)

@router.get("/reports/{report_id}/prediction/logs", summary="Get the logs for the given prediction")
async def prediction_log(report_id : int, agent_service: AutomationService = Depends(get_agent_service)):
    return await agent_service.get_history(report_id)

@router.get("/reports/{report_id}/prediction/stream", summary="Stream agent execution for finding a matching study.")
async def predict_stream(report_id : int, agent_service: AutomationService = Depends(get_agent_service)):
    return StreamingResponse(agent_service.report_matching_stream(report_id), media_type="text/event-stream")

@router.get("/reports/{report_id}/prediction", summary="Find a matching existing study or suggest a new study based on AI.")
async def predict(report_id : int, agent_service : AutomationService = Depends(get_agent_service)):
    return await agent_service.report_matching(report_id)
