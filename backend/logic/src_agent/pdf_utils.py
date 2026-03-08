from __future__ import annotations

import base64
import io
import os
import time
from typing import Optional

from openai import OpenAI

from .config import logger
from .llm_payloads import build_content_blocks_with_report_pdf
from .meerkat_client import fetch_report_pdf
from .prompts import PDF_ATTACHMENT_NOTE, PDF_ATTACHMENT_PAYLOAD_NOTE
from .schemas import EvalState, ReportDto

_REPORT_FILE_CACHE: dict[int, str] = {}


def encode_pdf_to_base64(pdf_bytes: bytes) -> str:
    """
    Encode PDF bytes to base64 string for native LLM upload.

    This allows sending the PDF directly to vision-capable models
    like Claude that can "read" PDFs natively, preserving tables
    and figures.

    Args:
        pdf_bytes: Raw PDF file bytes

    Returns:
        Base64 encoded string
    """
    return base64.b64encode(bytes(pdf_bytes)).decode("utf-8")


def get_cached_report_file_id(report_id: int) -> Optional[str]:
    return _REPORT_FILE_CACHE.get(report_id)


def cache_report_file_id(report_id: int, file_id: str) -> None:
    _REPORT_FILE_CACHE[report_id] = file_id


def _get_upload_retry_settings() -> tuple[int, float]:
    try:
        max_retries = int(os.getenv("OPENAI_PDF_UPLOAD_RETRIES", "2"))
    except ValueError:
        max_retries = 2
    try:
        base_backoff = float(os.getenv("OPENAI_PDF_UPLOAD_RETRY_BACKOFF_SECONDS", "0.5"))
    except ValueError:
        base_backoff = 0.5
    return max(0, max_retries), max(0.0, base_backoff)


def upload_pdf_to_openai(pdf_base64: str, filename: str = "report.pdf") -> Optional[str]:
    """
    Upload a PDF to OpenAI Files API and return the file ID.

    This allows referencing the file in multiple requests without
    re-uploading, significantly reducing bandwidth and cost.

    Args:
        pdf_base64: Base64-encoded PDF string
        filename: Name for the uploaded file

    Returns:
        File ID string if successful, None if upload fails
    """
    try:
        pdf_bytes = base64.b64decode(pdf_base64)
    except Exception as exc:
        logger.error(
            "upload_pdf_to_openai: invalid base64 filename=%s error=%s",
            filename,
            exc,
        )
        return None

    max_retries, base_backoff = _get_upload_retry_settings()
    total_attempts = max_retries + 1
    client = OpenAI()
    last_exc: Exception | None = None

    for attempt in range(total_attempts):
        try:
            pdf_file = io.BytesIO(pdf_bytes)
            pdf_file.name = filename
            response = client.files.create(
                file=pdf_file,
                purpose="assistants"
            )
            return response.id
        except Exception as exc:
            last_exc = exc
            attempt_num = attempt + 1
            logger.warning(
                "upload_pdf_to_openai: failed filename=%s attempt=%s/%s error=%s",
                filename,
                attempt_num,
                total_attempts,
                exc.__class__.__name__,
            )
            if attempt < max_retries:
                time.sleep(base_backoff * (2 ** attempt))

    logger.error(
        "upload_pdf_to_openai: exhausted retries filename=%s error=%s",
        filename,
        last_exc.__class__.__name__ if last_exc else "unknown",
    )
    return None


def upload_pdf_to_openai_cached(
        report_id: int, pdf_base64: str, filename: str = "report.pdf"
) -> Optional[str]:
    cached = get_cached_report_file_id(report_id)
    if cached:
        return cached
    file_id = upload_pdf_to_openai(pdf_base64, filename=filename)
    if file_id:
        cache_report_file_id(report_id, file_id)
    return file_id


def build_report_pdf_attachment(report: ReportDto) -> dict | None:
    """Fetch and prepare a single PDF attachment for the report being matched."""
    report_id = report.reportId
    pdf_bytes = fetch_report_pdf(report_id)
    if not pdf_bytes:
        logger.warning(
            "build_report_pdf_attachment: missing PDF report_id=%s",
            report_id,
        )
        return None

    try:
        pdf_base64 = encode_pdf_to_base64(pdf_bytes)
    except Exception as exc:
        logger.warning(
            "build_report_pdf_attachment: encode failed report_id=%s error=%s",
            report_id,
            exc,
        )
        return None

    file_id = upload_pdf_to_openai_cached(
        report_id,
        pdf_base64,
        filename=f"report_{report_id}.pdf",
    )
    if file_id:
        return {
            "report_id": report_id,
            "title": report.Title,
            "file_id": file_id,
            "base64": None,
        }

    logger.warning(
        "build_report_pdf_attachment: PDF upload failed, using inline base64 report_id=%s",
        report_id,
    )
    return {
        "report_id": report_id,
        "title": report.Title,
        "file_id": None,
        "base64": pdf_base64,
    }


def get_pdf_prompt_note(state: EvalState) -> str:
    overrides = state.get("prompt_overrides") or {}
    if isinstance(overrides, dict):
        override = overrides.get("pdf_prompt")
        if isinstance(override, str) and override.strip():
            return override
    return PDF_ATTACHMENT_NOTE


def apply_pdf_prompt_note(
        prompt: str,
        include_pdf: bool,
        has_attachment: bool,
        pdf_note: str,
) -> str:
    if not include_pdf or not has_attachment:
        return prompt
    note_parts = [PDF_ATTACHMENT_PAYLOAD_NOTE]
    if pdf_note.strip():
        note_parts.append(pdf_note)
    return f"{prompt} {' '.join(note_parts)}"


def build_human_content(state: EvalState, payload: str):
    if not state.get("include_pdf"):
        return payload
    attachment = state.get("report_pdf_attachment")
    if not attachment:
        return payload
    return build_content_blocks_with_report_pdf(payload, attachment)
