from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from .config import logger
from .evaluator import build_initial_state, run_evaluation
from .evaluation_graph import GRAPH
from .mock_data import MOCK_REPORT, MOCK_STUDIES
from .schemas import EvaluateRequest, EvaluateResponse
from .prompts import (
    BACKGROUND_PROMPT,
    DEFAULT_EVAL_PROMPT,
    DEFAULT_LIKELY_COMPARE_PROMPT,
    DEFAULT_LIKELY_GROUP_PROMPT,
    DEFAULT_LIKELY_REVIEW_PROMPT,
    DEFAULT_SUMMARY_PROMPT,
    DEFAULT_UNSURE_REVIEW_PROMPT,
    PDF_ATTACHMENT_NOTE,
)
from .streaming import summarize_stream_event

router = APIRouter(tags=["agent"])


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    logger.info(
        "evaluate: studies=%s model=%s include_pdf=%s",
        len(req.studies),
        req.model,
        req.include_pdf,
    )
    prompt_overrides = req.prompt_overrides.model_dump() if req.prompt_overrides else None
    return run_evaluation(
        req.report,
        req.studies,
        prompt_overrides,
        req.model,
        bool(req.include_pdf),
    )


@router.post("/evaluate/stream")
def evaluate_stream(req: EvaluateRequest) -> StreamingResponse:
    logger.info(
        "evaluate_stream: studies=%s model=%s include_pdf=%s",
        len(req.studies),
        req.model,
        req.include_pdf,
    )
    prompt_overrides = req.prompt_overrides.model_dump() if req.prompt_overrides else None
    initial_state = build_initial_state(
        req.report,
        req.studies,
        prompt_overrides,
        req.model,
        bool(req.include_pdf),
    )

    def event_stream():
        for event in GRAPH.stream(initial_state, stream_mode="updates"):
            summary = summarize_stream_event(event)
            if summary is None:
                continue
            payload = jsonable_encoder(summary)
            yield f"data: {json.dumps(payload, ensure_ascii=True)}\n\n"
        yield "data: {\"event\":\"complete\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/evaluate/stream/mock")
def evaluate_stream_mock() -> StreamingResponse:
    logger.info("evaluate_stream_mock")
    initial_state = build_initial_state(
        MOCK_REPORT,
        MOCK_STUDIES,
        None,
        None,
        False,
    )

    def event_stream():
        for event in GRAPH.stream(initial_state, stream_mode="updates"):
            summary = summarize_stream_event(event)
            payload = jsonable_encoder(summary)
            yield f"data: {json.dumps(payload, ensure_ascii=True)}\n\n"
        yield "data: {\"event\":\"complete\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/evaluate/mock", response_model=EvaluateResponse)
def evaluate_mock() -> EvaluateResponse:
    logger.info("evaluate_mock")
    return run_evaluation(
        MOCK_REPORT,
        MOCK_STUDIES,
        None,
        None,
        False,
    )


@router.get("/prompts")
def get_default_prompts() -> dict:
    return {
        "background_prompt": BACKGROUND_PROMPT,
        "initial_eval_prompt": DEFAULT_EVAL_PROMPT,
        "likely_group_prompt": DEFAULT_LIKELY_GROUP_PROMPT,
        "likely_compare_prompt": DEFAULT_LIKELY_COMPARE_PROMPT,
        "likely_review_prompt": DEFAULT_LIKELY_REVIEW_PROMPT,
        "unsure_review_prompt": DEFAULT_UNSURE_REVIEW_PROMPT,
        "summary_prompt": DEFAULT_SUMMARY_PROMPT,
        "pdf_prompt": PDF_ATTACHMENT_NOTE,
    }
