from __future__ import annotations

from .config import logger
from .evaluation_graph import GRAPH
from .llm import build_llm
from .schemas import EvaluateResponse, EvalState, ReportDto, StudyDto


def build_initial_state(
    report: ReportDto,
    studies: list[StudyDto],
    prompt_overrides: dict[str, str | None] | None,
    model: str | None,
    include_pdf: bool,
) -> EvalState:
    llm = build_llm(model=model)
    return {
        "report": report,
        "studies": studies,
        "idx": 0,
        "unsure_idx": 0,
        "unsure_queue": [],
        "current": None,
        "study_id": None,
        "decision": None,
        "reason": None,
        "include_pdf": include_pdf,
        "prompt_overrides": prompt_overrides,
        "llm": llm,
        "match": None,
        "not_matches": [],
        "unsure": [],
        "likely_matches": [],
        "very_likely": [],
        "rejected_likely": [],
        "evaluation_summary": None,
        "report_pdf_attachment": None,
        "pdf_status": None,
        "new_study_suggestion": None,
    }


def run_evaluation(
    report: ReportDto,
    studies: list[StudyDto],
    prompt_overrides: dict[str, str | None] | None,
    model: str | None,
    include_pdf: bool,
) -> EvaluateResponse:
    logger.info("run_evaluation: reports=%s studies=%s", report.reportId, len(studies))
    initial_state = build_initial_state(
        report,
        studies,
        prompt_overrides,
        model,
        include_pdf,
    )

    final_state = GRAPH.invoke(initial_state)
    logger.info(
        "run_evaluation: done match=%s not_matches=%s unsure=%s likely_matches=%s",
        "yes" if final_state["match"] else "no",
        len(final_state["not_matches"]),
        len(final_state["unsure"]),
        len(final_state["likely_matches"]),
    )
    evaluation_summary = (final_state.get("evaluation_summary", {}) or {})
    return EvaluateResponse(
        match=final_state["match"],
        not_matches=final_state["not_matches"],
        unsure=final_state["unsure"],
        likely_matches=final_state["likely_matches"],
        very_likely=final_state["very_likely"],
        evaluation_has_match=evaluation_summary.get("has_match"),
        evaluation_summary=evaluation_summary.get("summary"),
        evaluation_new_study=final_state.get("new_study_suggestion"),
    )
