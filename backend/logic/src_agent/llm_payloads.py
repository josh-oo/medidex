from __future__ import annotations

import json

from .schemas import ReportDto, StudyDto


def build_user_payload(report: ReportDto, study: StudyDto) -> str:
    """Serialize a single report + study for first-pass evaluation."""
    report_payload = report.model_dump()
    study_payload = study.model_dump()
    return json.dumps(
        {
            "report": report_payload,
            "study": study_payload,
            "study_short_name": study.shortName,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )


def build_likely_group_payload(
    report: ReportDto,
    candidates: list[dict],
    studies: list[StudyDto],
) -> str:
    """Serialize likely-match candidates for very-likely selection.

    Each candidate includes the original study + the initial reason.
    """
    by_id = {str(study.studyId): study for study in studies}
    payload_candidates: list[dict] = []
    for item in candidates:
        study_id = str(item.get("study_id", ""))
        study = by_id.get(study_id)
        if study is None:
            continue
        payload_candidates.append(
            {
                "study_id": study_id,
                "short_name": study.shortName,
                "study": study.model_dump(),
                "prior_reason": item.get("reason"),
            }
        )
    return json.dumps(
        {"report": report.model_dump(), "candidates": payload_candidates},
        ensure_ascii=True,
        separators=(",", ":"),
    )


def build_likely_compare_payload(
    report: ReportDto,
    candidates: list[dict],
    studies: list[StudyDto],
) -> str:
    """Serialize very-likely candidates for final comparison.

    Each candidate includes prior and group-level reasons for context.
    """
    by_id = {str(study.studyId): study for study in studies}
    payload_candidates: list[dict] = []
    for item in candidates:
        study_id = str(item.get("study_id", ""))
        study = by_id.get(study_id)
        if study is None:
            continue
        payload_candidates.append(
            {
                "study_id": study_id,
                "short_name": study.shortName,
                "study": study.model_dump(),
                "prior_reason": item.get("prior_reason"),
                "group_reason": item.get("group_reason"),
            }
        )
    return json.dumps(
        {"report": report.model_dump(), "candidates": payload_candidates},
        ensure_ascii=True,
        separators=(",", ":"),
    )


def build_likely_review_payload(
    report: ReportDto,
    current_study: StudyDto,
    prior_reason: str | None,
    rejected_likely: list[dict],
    studies: list[StudyDto],
) -> str:
    """Serialize the likely review context for non-selected likely studies.

    Includes the current likely study and previously reviewed likely history.
    """
    by_id = {str(study.studyId): study for study in studies}
    rejected_payload: list[dict] = []
    for item in rejected_likely:
        study_id = str(item.get("study_id", ""))
        study = by_id.get(study_id)
        if study is None:
            continue
        rejected_payload.append(
            {
                "study_id": study_id,
                "short_name": study.shortName,
                "study": study.model_dump(),
                "initial_reason": item.get("initial_reason"),
                "review_reason": item.get("review_reason"),
            }
        )
    return json.dumps(
        {
            "report": report.model_dump(),
            "rejected_likely": rejected_payload,
            "current": {
                "study_id": str(current_study.studyId),
                "short_name": current_study.shortName,
                "study": current_study.model_dump(),
                "prior_reason": prior_reason,
            },
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )


def build_unsure_review_payload(
    report: ReportDto,
    rejected_likely: list[dict],
    current_study: StudyDto,
    prior_reason: str | None,
    studies: list[StudyDto],
) -> str:
    """Serialize the unsure review context.

    Includes rejected likely-match history plus the current study and its prior reason.
    """
    by_id = {str(study.studyId): study for study in studies}
    rejected_payload: list[dict] = []
    for item in rejected_likely:
        study_id = str(item.get("study_id", ""))
        study = by_id.get(study_id)
        if study is None:
            continue
        rejected_payload.append(
            {
                "study_id": study_id,
                "short_name": study.shortName,
                "study": study.model_dump(),
                "initial_reason": item.get("initial_reason"),
                "review_reason": item.get("review_reason"),
            }
        )
    return json.dumps(
        {
            "report": report.model_dump(),
            "rejected_likely": rejected_payload,
            "current": {
                "study_id": str(current_study.studyId),
                "short_name": current_study.shortName,
                "study": current_study.model_dump(),
                "prior_reason": prior_reason,
            },
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )


def build_summary_payload(
    report: ReportDto,
    studies: list[StudyDto],
    match: dict | None,
    not_matches: list[dict],
    unsure: list[dict],
    likely_matches: list[dict],
    very_likely: list[dict],
) -> str:
    """Serialize the full evaluation state for final summarization."""
    by_id = {str(study.studyId): study for study in studies}

    def attach_study(item: dict) -> dict:
        study_id = str(item.get("study_id", ""))
        study = by_id.get(study_id)
        return {
            "study_id": study_id,
            "short_name": study.shortName if study else None,
            "study": study.model_dump() if study else None,
            "decision": item.get("decision"),
            "reason": item.get("reason"),
        }

    payload = {
        "report": report.model_dump(),
        "match": attach_study(match) if match else None,
        "not_matches": [attach_study(item) for item in not_matches],
        "unsure": [attach_study(item) for item in unsure],
        "likely_matches": [attach_study(item) for item in likely_matches],
        "very_likely": very_likely,
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def build_content_blocks_with_report_pdf(
    text_payload: str,
    attachment: dict | None,
) -> list[dict]:
    """Build content blocks with the current report PDF attachment.

    Expects attachment with report_id, title, file_id/base64.
    If no attachment is provided, returns a single text block.
    """
    if not attachment:
        return [{"type": "text", "text": text_payload}]

    file_id = attachment.get("file_id")
    pdf_base64 = attachment.get("base64")
    if not file_id and not pdf_base64:
        return [{"type": "text", "text": text_payload}]

    report_id = attachment.get("report_id")
    title = attachment.get("title")
    if file_id:
        pdf_block = {"type": "file", "file_id": file_id}
    else:
        pdf_block = {
            "type": "file",
            "base64": pdf_base64,
            "mime_type": "application/pdf",
            "filename": f"report_{report_id}.pdf",
        }

    attachment_meta = {
        "attachment_index": 0,
        "report_id": report_id,
        "title": title,
    }

    try:
        payload_obj = json.loads(text_payload)
        payload_obj["pdf_attachment"] = attachment_meta
        text_payload = json.dumps(payload_obj, ensure_ascii=True, separators=(",", ":"))
    except json.JSONDecodeError:
        text_payload = (
            f"{text_payload}\n\nPDF_ATTACHMENT={json.dumps(attachment_meta, ensure_ascii=True)}"
        )

    return [pdf_block, {"type": "text", "text": text_payload}]
