from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from .config import logger
from .evaluation_utils import (
    apply_background_prompt,
    append_prompt_note,
    get_pending_likely_study_ids,
    get_bucket_entry,
    get_background_prompt,
    get_prompt,
    invoke_structured,
    get_study_by_id,
    remove_from_bucket,
    resolve_candidate_study_id,
    upsert_bucket,
)
from .llm_payloads import (
    build_likely_compare_payload,
    build_likely_group_payload,
    build_likely_review_payload,
    build_summary_payload,
    build_unsure_review_payload,
    build_user_payload,
)
from .pdf_utils import (
    apply_pdf_prompt_note,
    build_human_content,
    build_report_pdf_attachment,
    get_pdf_prompt_note,
)
from .prompts import (
    BACKGROUND_PROMPT,
    DEFAULT_EVAL_PROMPT,
    DEFAULT_LIKELY_COMPARE_PROMPT,
    DEFAULT_LIKELY_REVIEW_PROMPT,
    LIKELY_COMPARE_ID_NOTE,
    DEFAULT_LIKELY_GROUP_PROMPT,
    LIKELY_GROUP_ID_NOTE,
    SUMMARY_MATCH_EVAL_NOTE,
    DEFAULT_SUMMARY_PROMPT,
    DEFAULT_UNSURE_REVIEW_PROMPT,
    PDF_ATTACHMENT_NOTE,
    REASON_NOTE,
    SUMMARY_MARKDOWN_NOTE,
    SUGGEST_NEW_STUDY_PROMPT,
)
from .schemas import (
    EvalState,
    InitialDecisionOutput,
    LikelyCompareOutput,
    LikelyGroupOutput,
    LikelyReviewOutput,
    SuggestNewStudyOutput,
    SummaryOutput,
    UnsureReviewOutput,
)


def prepare_report_pdf(state: EvalState) -> dict:
    """Prepare the report PDF attachment once at the start of the graph."""
    if not state.get("include_pdf"):
        logger.info("prepare_report_pdf: include_pdf=false")
        return {"report_pdf_attachment": None, "pdf_status": "disabled"}
    attachment = build_report_pdf_attachment(state["report"])
    logger.info("prepare_report_pdf: attached=%s", bool(attachment))
    status = "attached" if attachment else "missing"
    return {"report_pdf_attachment": attachment, "pdf_status": status}


def load_next_initial(state: EvalState) -> dict:
    """Load the next study for the initial pass, or mark completion."""
    idx = state["idx"]
    logger.info("load_next_initial: idx=%s total=%s", idx, len(state["studies"]))
    if idx >= len(state["studies"]):
        logger.info("load_next_initial: no_more_studies")
        return {"current": None}

    current = state["studies"][idx]
    logger.info(
        "load_next_initial: study_id=%s short_name=%s",
        current.studyId,
        current.shortName,
    )
    return {
        "current": current,
        "decision": None,
        "reason": None,
    }


def route_after_initial_load(state: EvalState) -> str:
    """Route to initial classification or to the likely-match stage when done."""
    next_step = "no_more_initial" if state.get("current") is None else "has_study"
    logger.info("route_after_initial_load: next=%s", next_step)
    return next_step


def classify_initial(state: EvalState) -> dict:
    """Run first-pass LLM classification and place the study into a bucket."""
    current = state["current"]
    if current is None:
        logger.info("classify_initial: no_current_study")
        return {"decision": "unsure", "reason": "No study loaded."}

    logger.info("classify_initial: study_id=%s", current.studyId)
    user_payload = build_user_payload(state["report"], current)
    prompt = apply_background_prompt(
        get_prompt(state, "initial_eval_prompt", DEFAULT_EVAL_PROMPT),
        get_background_prompt(state, BACKGROUND_PROMPT),
    )
    prompt = append_prompt_note(prompt, REASON_NOTE)
    prompt = apply_pdf_prompt_note(
        prompt,
        state.get("include_pdf", False),
        bool(state.get("report_pdf_attachment")),
        get_pdf_prompt_note(state),
    )
    logger.info("classify_initial: prompt_used=%s", prompt[:60])
    try:
        messages: list[SystemMessage | HumanMessage] = [SystemMessage(content=prompt)]
        messages.append(HumanMessage(content=build_human_content(state, user_payload)))
        result = invoke_structured(state, messages, InitialDecisionOutput)
        decision = result.decision
        reason = result.reason
        logger.info("classify_initial: decision=%s", decision)
    except Exception as exc:
        decision, reason = "unsure", f"LLM call failed: {exc.__class__.__name__}"
        logger.info("classify_initial: error=%s", exc.__class__.__name__)
        logger.info("classify_initial: reason=%s", str(exc))
    idx = state["idx"]

    study_id = str(current.studyId) if current else f"index-{idx}"
    result = {"study_id": study_id, "decision": decision, "reason": reason}

    not_matches = list(state["not_matches"])
    unsure = list(state["unsure"])
    likely_matches = list(state["likely_matches"])

    if decision == "not_match":
        not_matches.append(result)
    elif decision == "likely_match":
        likely_matches.append(result)
    else:
        unsure.append(result)

    return {
        "study_id": study_id,
        "decision": decision,
        "reason": reason,
        "not_matches": not_matches,
        "unsure": unsure,
        "likely_matches": likely_matches,
        "idx": idx + 1,
    }


def select_very_likely(state: EvalState) -> dict:
    """Choose up to two very-likely studies from the likely-match bucket."""
    candidates = list(state.get("likely_matches", []))
    if not candidates:
        logger.info("select_very_likely: no_candidates")
        return {
            "decision": "unsure",
            "reason": "No likely matches to review.",
            "likely_matches": [],
            "very_likely": [],
        }

    candidate_ids = {str(item.get("study_id")) for item in candidates if item.get("study_id")}
    payload = build_likely_group_payload(state["report"], candidates, state["studies"])
    prompt = apply_background_prompt(
        get_prompt(state, "likely_group_prompt", DEFAULT_LIKELY_GROUP_PROMPT),
        get_background_prompt(state, BACKGROUND_PROMPT),
    )
    prompt = append_prompt_note(prompt, REASON_NOTE)
    prompt = append_prompt_note(prompt, LIKELY_GROUP_ID_NOTE)
    prompt = apply_pdf_prompt_note(
        prompt,
        state.get("include_pdf", False),
        bool(state.get("report_pdf_attachment")),
        get_pdf_prompt_note(state),
    )
    try:
        messages: list[SystemMessage | HumanMessage] = [SystemMessage(content=prompt)]
        messages.append(HumanMessage(content=build_human_content(state, payload)))
        result = invoke_structured(state, messages, LikelyGroupOutput)
        raw_ids = result.very_likely_study_ids or []
        logger.info("select_very_likely: raw_selected_ids=%s", raw_ids)
        selected_ids: list[str] = []
        for item in raw_ids:
            study_id = str(item).strip()
            if not study_id or study_id not in candidate_ids:
                continue
            if study_id not in selected_ids:
                selected_ids.append(study_id)
        selected_ids = selected_ids[:2]
        reason = result.reason
        logger.info("select_very_likely: selected=%s", selected_ids)
    except Exception as exc:
        selected_ids, reason = [], f"LLM call failed: {exc.__class__.__name__}"
        logger.info("select_very_likely: error=%s", exc.__class__.__name__)
        logger.info("select_very_likely: reason=%s", str(exc))

    selected_set = set(selected_ids)
    likely_matches = list(state.get("likely_matches", []))
    very_likely: list[dict] = []

    for item in candidates:
        study_id = str(item.get("study_id"))
        prior_reason = item.get("reason")
        if study_id in selected_set:
            study = get_study_by_id(state["studies"], study_id)
            very_likely.append(
                {
                    "study_id": study_id,
                    "short_name": study.shortName if study else None,
                    "prior_reason": prior_reason,
                    "group_reason": reason,
                }
            )

    return {
        "decision": "unsure",
        "reason": reason,
        "likely_matches": likely_matches,
        "very_likely": very_likely,
    }


def route_after_very_likely_selection(state: EvalState) -> str:
    """Route to comparison if very-likely exists, else move to likely review."""
    next_step = "has_very_likely" if state.get("very_likely") else "no_very_likely"
    logger.info("route_after_very_likely_selection: next=%s", next_step)
    return next_step


def compare_very_likely(state: EvalState) -> dict:
    """Compare very-likely studies to confirm a single match or defer to unsure."""
    candidates = list(state.get("very_likely", []))
    if not candidates:
        logger.info("compare_very_likely: no_candidates")
        return {
            "decision": "unsure",
            "reason": "No very_likely candidates to compare.",
            "very_likely": [],
        }

    candidate_ids = {str(item.get("study_id")) for item in candidates if item.get("study_id")}
    payload = build_likely_compare_payload(state["report"], candidates, state["studies"])
    prompt = apply_background_prompt(
        get_prompt(state, "likely_compare_prompt", DEFAULT_LIKELY_COMPARE_PROMPT),
        get_background_prompt(state, BACKGROUND_PROMPT),
    )
    prompt = append_prompt_note(prompt, REASON_NOTE)
    prompt = append_prompt_note(prompt, LIKELY_COMPARE_ID_NOTE)
    prompt = apply_pdf_prompt_note(
        prompt,
        state.get("include_pdf", False),
        bool(state.get("report_pdf_attachment")),
        get_pdf_prompt_note(state),
    )
    try:
        messages: list[SystemMessage | HumanMessage] = [SystemMessage(content=prompt)]
        messages.append(HumanMessage(content=build_human_content(state, payload)))
        result = invoke_structured(state, messages, LikelyCompareOutput)
        decision = result.decision
        reason = result.reason
        raw_study_id = result.study_id
        study_id = resolve_candidate_study_id(raw_study_id, candidates, state["studies"])
        if decision == "match":
            if not study_id or study_id not in candidate_ids:
                decision = "unsure"
                reason = "Missing or invalid study_id for match decision."
                study_id = None
        else:
            study_id = None
        logger.info(
            "compare_very_likely: decision=%s raw_study_id=%s resolved_study_id=%s",
            decision,
            raw_study_id,
            study_id,
        )
    except Exception as exc:
        decision, reason, study_id = "unsure", f"LLM call failed: {exc.__class__.__name__}", None
        logger.info("compare_very_likely: error=%s", exc.__class__.__name__)
        logger.info("compare_very_likely: reason=%s", str(exc))

    match = state["match"]
    likely_matches = list(state.get("likely_matches", []))

    if decision == "match" and study_id:
        if match is None:
            match = {"study_id": study_id, "decision": "match", "reason": reason}
        return {
            "decision": decision,
            "reason": reason,
            "match": match,
            "likely_matches": likely_matches,
            "very_likely": candidates,
        }

    return {
        "decision": decision,
        "reason": reason,
        "match": match,
        "likely_matches": likely_matches,
        "very_likely": candidates,
    }


def route_after_very_likely_compare(state: EvalState) -> str:
    """Route to summary if a match is found, otherwise continue to likely review."""
    next_step = "match_found" if state.get("match") is not None else "no_match_after_compare"
    logger.info("route_after_very_likely_compare: next=%s", next_step)
    return next_step


def prepare_likely_review(state: EvalState) -> dict:
    """Compute remaining likely candidates to review before unsure review."""
    pending_ids = get_pending_likely_study_ids(
        state.get("likely_matches", []),
        state.get("very_likely", []),
        state.get("rejected_likely", []),
    )
    logger.info("prepare_likely_review: count=%s", len(pending_ids))
    return {
        "current": None,
        "decision": None,
        "reason": None,
        "count": len(pending_ids),
    }


def load_next_likely(state: EvalState) -> dict:
    """Load the next pending likely study, derived from current buckets."""
    if state.get("match") is not None:
        logger.info("load_next_likely: match_already_found")
        return {"current": None}

    pending_ids = get_pending_likely_study_ids(
        state.get("likely_matches", []),
        state.get("very_likely", []),
        state.get("rejected_likely", []),
    )
    logger.info("load_next_likely: count=%s", len(pending_ids))
    rejected_likely = list(state.get("rejected_likely", []))
    for study_id in pending_ids:
        current = get_study_by_id(state["studies"], study_id)
        if current is not None:
            logger.info(
                "load_next_likely: study_id=%s short_name=%s",
                current.studyId,
                current.shortName,
            )
            return {
                "current": current,
                "decision": None,
                "reason": None,
            }
        logger.info("load_next_likely: missing_study_id=%s", study_id)
        rejected_likely = upsert_bucket(
            rejected_likely,
            {
                "study_id": study_id,
                "initial_reason": None,
                "review_reason": "Study could not be loaded for likely review.",
            },
        )
    if rejected_likely != list(state.get("rejected_likely", [])):
        return {"current": None, "rejected_likely": rejected_likely}

    logger.info("load_next_likely: no_more_likely")
    return {"current": None}


def route_after_likely_load(state: EvalState) -> str:
    """Route from likely review loader based on match or remaining studies."""
    if state.get("match") is not None:
        next_step = "match_found"
    elif state.get("current") is None:
        next_step = "no_more_likely"
    else:
        next_step = "has_likely"
    logger.info("route_after_likely_load: next=%s", next_step)
    return next_step


def classify_likely_review(state: EvalState) -> dict:
    """Re-review a likely study while keeping likely bucket stable unless match."""
    current = state["current"]
    if current is None:
        logger.info("classify_likely_review: no_current_study")
        return {"decision": "unsure", "reason": "No study loaded."}

    study_id = str(current.studyId)
    prior_entry = get_bucket_entry(state.get("likely_matches", []), study_id)
    prior_reason = prior_entry.get("reason") if prior_entry else None
    logger.info("classify_likely_review: study_id=%s", study_id)

    payload = build_likely_review_payload(
        state["report"],
        current,
        prior_reason,
        state.get("rejected_likely", []),
        state["studies"],
    )
    prompt = apply_background_prompt(
        get_prompt(state, "likely_review_prompt", DEFAULT_LIKELY_REVIEW_PROMPT),
        get_background_prompt(state, BACKGROUND_PROMPT),
    )
    prompt = append_prompt_note(prompt, REASON_NOTE)
    prompt = apply_pdf_prompt_note(
        prompt,
        state.get("include_pdf", False),
        bool(state.get("report_pdf_attachment")),
        get_pdf_prompt_note(state),
    )
    try:
        messages: list[SystemMessage | HumanMessage] = [SystemMessage(content=prompt)]
        messages.append(HumanMessage(content=build_human_content(state, payload)))
        result = invoke_structured(state, messages, LikelyReviewOutput)
        decision = result.decision
        reason = result.reason
        logger.info("classify_likely_review: decision=%s", decision)
    except Exception as exc:
        decision, reason = "unsure", f"LLM call failed: {exc.__class__.__name__}"
        logger.info("classify_likely_review: error=%s", exc.__class__.__name__)
        logger.info("classify_likely_review: reason=%s", str(exc))

    match = state["match"]
    rejected_likely = list(state.get("rejected_likely", []))
    if decision == "match":
        if match is None:
            match = {"study_id": study_id, "decision": "match", "reason": reason}
    else:
        existing_rejected = get_bucket_entry(rejected_likely, study_id)
        initial_reason = (
            existing_rejected.get("initial_reason")
            if existing_rejected
            else prior_reason
        )
        rejected_likely = upsert_bucket(
            rejected_likely,
            {
                "study_id": study_id,
                "initial_reason": initial_reason,
                "review_reason": reason,
            },
        )

    return {
        "study_id": study_id,
        "decision": decision,
        "reason": reason,
        "match": match,
        "rejected_likely": rejected_likely,
    }


def route_after_summary(state: EvalState) -> str:
    summary = state.get("evaluation_summary") or {}
    has_match = summary.get("has_match")
    if has_match is False:
        return "needs_new_study"
    if has_match is True and state.get("match") is None:
        return "needs_new_study"
    return "done"


def prepare_unsure_review(state: EvalState) -> dict:
    """Initialize the unsure queue for a second-pass review."""
    queue = [str(item.get("study_id")) for item in state.get("unsure", []) if item.get("study_id")]
    logger.info("prepare_unsure_review: count=%s", len(queue))
    return {
        "unsure_queue": queue,
        "unsure_idx": 0,
        "current": None,
        "decision": None,
        "reason": None,
    }


def load_next_unsure(state: EvalState) -> dict:
    """Load the next unsure study to re-evaluate, or mark completion."""
    idx = state["unsure_idx"]
    queue = state.get("unsure_queue", [])
    logger.info("load_next_unsure: idx=%s total=%s", idx, len(queue))
    while idx < len(queue):
        study_id = queue[idx]
        current = get_study_by_id(state["studies"], study_id)
        if current is not None:
            logger.info(
                "load_next_unsure: study_id=%s short_name=%s",
                current.studyId,
                current.shortName,
            )
            return {
                "current": current,
                "decision": None,
                "reason": None,
                "unsure_idx": idx,
            }
        logger.info("load_next_unsure: missing_study_id=%s", study_id)
        idx += 1

    logger.info("load_next_unsure: no_more_unsure")
    return {"current": None, "unsure_idx": idx}


def route_after_unsure_load(state: EvalState) -> str:
    """Route based on whether a match already exists, or if more unsure remain."""
    if state.get("match") is not None:
        next_step = "match_found"
    elif state.get("current") is None:
        next_step = "match_not_found"
    else:
        next_step = "has_unsure"
    logger.info("route_after_unsure_load: next=%s", next_step)
    return next_step


def classify_unsure(state: EvalState) -> dict:
    """Re-evaluate an unsure study and update buckets or set a final match."""
    current = state["current"]
    if current is None:
        logger.info("classify_unsure: no_current_study")
        return {"decision": "unsure", "reason": "No study loaded."}

    study_id = str(current.studyId)
    prior_entry = get_bucket_entry(state.get("unsure", []), study_id)
    prior_reason = prior_entry.get("reason") if prior_entry else None

    logger.info("classify_unsure: study_id=%s", study_id)
    payload = build_unsure_review_payload(
        state["report"],
        state.get("rejected_likely", []),
        current,
        prior_reason,
        state["studies"],
    )
    prompt = apply_background_prompt(
        get_prompt(state, "unsure_review_prompt", DEFAULT_UNSURE_REVIEW_PROMPT),
        get_background_prompt(state, BACKGROUND_PROMPT),
    )
    prompt = append_prompt_note(prompt, REASON_NOTE)
    prompt = apply_pdf_prompt_note(
        prompt,
        state.get("include_pdf", False),
        bool(state.get("report_pdf_attachment")),
        get_pdf_prompt_note(state),
    )
    try:
        messages: list[SystemMessage | HumanMessage] = [SystemMessage(content=prompt)]
        messages.append(HumanMessage(content=build_human_content(state, payload)))
        result = invoke_structured(state, messages, UnsureReviewOutput)
        decision = result.decision
        reason = result.reason
        logger.info("classify_unsure: decision=%s", decision)
    except Exception as exc:
        decision, reason = "unsure", f"LLM call failed: {exc.__class__.__name__}"
        logger.info("classify_unsure: error=%s", exc.__class__.__name__)
        logger.info("classify_unsure: reason=%s", str(exc))

    match = state["match"]
    not_matches = list(state["not_matches"])
    unsure = list(state["unsure"])

    if decision == "match":
        if match is None:
            match = {"study_id": study_id, "decision": "match", "reason": reason}
        unsure = remove_from_bucket(unsure, study_id)
    elif decision == "not_match":
        unsure = remove_from_bucket(unsure, study_id)
        not_matches = upsert_bucket(
            not_matches,
            {"study_id": study_id, "decision": "not_match", "reason": reason},
        )
    else:
        unsure = upsert_bucket(
            unsure,
            {"study_id": study_id, "decision": "unsure", "reason": reason},
        )

    return {
        "study_id": study_id,
        "decision": decision,
        "reason": reason,
        "match": match,
        "not_matches": not_matches,
        "unsure": unsure,
        "unsure_idx": state["unsure_idx"] + 1,
    }


def match_not_found_end(state: EvalState) -> dict:
    """Terminal node when no match is found after all reviews."""
    logger.info("match_not_found_end: no_match")
    return {}


def summarize_evaluation(state: EvalState) -> dict:
    """Summarize the full evaluation state into a final explanation."""
    payload = build_summary_payload(
        state["report"],
        state["studies"],
        state.get("match"),
        state.get("not_matches", []),
        state.get("unsure", []),
        state.get("likely_matches", []),
        state.get("very_likely", []),
    )
    prompt = apply_background_prompt(
        get_prompt(state, "summary_prompt", DEFAULT_SUMMARY_PROMPT),
        get_background_prompt(state, BACKGROUND_PROMPT),
    )
    prompt = append_prompt_note(prompt, SUMMARY_MATCH_EVAL_NOTE)
    prompt = append_prompt_note(prompt, REASON_NOTE)
    prompt = append_prompt_note(prompt, SUMMARY_MARKDOWN_NOTE)
    prompt = apply_pdf_prompt_note(
        prompt,
        state.get("include_pdf", False),
        bool(state.get("report_pdf_attachment")),
        get_pdf_prompt_note(state),
    )

    try:
        messages: list[SystemMessage | HumanMessage] = [SystemMessage(content=prompt)]
        messages.append(HumanMessage(content=build_human_content(state, payload)))
        result = invoke_structured(state, messages, SummaryOutput)
        has_match = result.has_match
        summary = result.summary
        logger.info("summarize_evaluation: has_match=%s", has_match)
    except Exception as exc:
        has_match, summary = None, f"LLM call failed: {exc.__class__.__name__}"
        logger.info("summarize_evaluation: error=%s", exc.__class__.__name__)
        logger.info("summarize_evaluation: reason=%s", str(exc))

    return {
        "evaluation_summary": {
            "has_match": has_match,
            "summary": summary,
        }
    }


def suggest_new_study(state: EvalState) -> dict:
    """Suggest a new study when no match is found."""
    payload = build_summary_payload(
        state["report"],
        state["studies"],
        state.get("match"),
        state.get("not_matches", []),
        state.get("unsure", []),
        state.get("likely_matches", []),
        state.get("very_likely", []),
    )
    prompt = f"{BACKGROUND_PROMPT} {SUGGEST_NEW_STUDY_PROMPT}"
    prompt = apply_pdf_prompt_note(
        prompt,
        state.get("include_pdf", False),
        bool(state.get("report_pdf_attachment")),
        PDF_ATTACHMENT_NOTE,
    )
    try:
        messages: list[SystemMessage | HumanMessage] = [SystemMessage(content=prompt)]
        messages.append(HumanMessage(content=build_human_content(state, payload)))
        result = invoke_structured(state, messages, SuggestNewStudyOutput)
        new_study = result.new_study.model_dump()
        logger.info("suggest_new_study: ok")
    except Exception as exc:
        new_study = None
        logger.info("suggest_new_study: error=%s", exc.__class__.__name__)
        logger.info("suggest_new_study: reason=%s", str(exc))
    return {"new_study_suggestion": new_study}


def build_graph():
    """Construct the LangGraph workflow and its routing rules.

    Flow:
    - Setup: prepare_report_pdf -> load_next_initial
    - Initial pass: load_next_initial -> classify_initial -> (loop) -> select_very_likely
    - Likely selection pass: select_very_likely -> compare_very_likely
    - Likely review pass: prepare_likely_review -> load_next_likely -> classify_likely_review (loop)
    - Unsure pass: prepare_unsure_review -> load_next_unsure -> classify_unsure (loop)
      -> match_not_found_end -> summarize_evaluation -> suggest_new_study (if no match)
    """
    logger.info("build_graph: init")
    graph = StateGraph(EvalState)
    graph.add_node("prepare_report_pdf", prepare_report_pdf)
    graph.add_node("load_next_initial", load_next_initial)
    graph.add_node("classify_initial", classify_initial)
    graph.add_node("select_very_likely", select_very_likely)
    graph.add_node("compare_very_likely", compare_very_likely)
    graph.add_node("prepare_likely_review", prepare_likely_review)
    graph.add_node("load_next_likely", load_next_likely)
    graph.add_node("classify_likely_review", classify_likely_review)
    graph.add_node("prepare_unsure_review", prepare_unsure_review)
    graph.add_node("load_next_unsure", load_next_unsure)
    graph.add_node("classify_unsure", classify_unsure)
    graph.add_node("match_not_found_end", match_not_found_end)
    graph.add_node("summarize_evaluation", summarize_evaluation)
    graph.add_node("suggest_new_study", suggest_new_study)

    graph.set_entry_point("prepare_report_pdf")
    graph.add_edge("prepare_report_pdf", "load_next_initial")
    graph.add_conditional_edges(
        "load_next_initial",
        route_after_initial_load,
        {"has_study": "classify_initial", "no_more_initial": "select_very_likely"},
    )
    graph.add_edge("classify_initial", "load_next_initial")

    graph.add_conditional_edges(
        "select_very_likely",
        route_after_very_likely_selection,
        {"has_very_likely": "compare_very_likely", "no_very_likely": "prepare_likely_review"},
    )
    graph.add_conditional_edges(
        "compare_very_likely",
        route_after_very_likely_compare,
        {"match_found": "summarize_evaluation", "no_match_after_compare": "prepare_likely_review"},
    )

    graph.add_edge("prepare_likely_review", "load_next_likely")
    graph.add_conditional_edges(
        "load_next_likely",
        route_after_likely_load,
        {
            "has_likely": "classify_likely_review",
            "no_more_likely": "prepare_unsure_review",
            "match_found": "summarize_evaluation",
        },
    )
    graph.add_edge("classify_likely_review", "load_next_likely")

    graph.add_edge("prepare_unsure_review", "load_next_unsure")
    graph.add_conditional_edges(
        "load_next_unsure",
        route_after_unsure_load,
        {
            "has_unsure": "classify_unsure",
            "match_not_found": "match_not_found_end",
            "match_found": "summarize_evaluation",
        },
    )
    graph.add_edge("classify_unsure", "load_next_unsure")
    graph.add_edge("match_not_found_end", "summarize_evaluation")
    graph.add_conditional_edges(
        "summarize_evaluation",
        route_after_summary,
        {"needs_new_study": "suggest_new_study", "done": END},
    )
    graph.add_edge("suggest_new_study", END)
    return graph.compile()


GRAPH = build_graph()
