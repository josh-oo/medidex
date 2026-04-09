from __future__ import annotations

import os
import re
import time

from .config import logger
from .llm import MODEL
from .schemas import EvalState, StudyDto


def get_llm(state: EvalState):
    llm = state.get("llm")
    return llm if llm is not None else MODEL


def get_prompt(state: EvalState, key: str, default: str) -> str:
    overrides = state.get("prompt_overrides") or {}
    if isinstance(overrides, dict):
        override = overrides.get(key)
        if isinstance(override, str) and override.strip():
            return override
    return default


def get_background_prompt(state: EvalState, default: str) -> str:
    overrides = state.get("prompt_overrides") or {}
    if isinstance(overrides, dict):
        override = overrides.get("background_prompt")
        if isinstance(override, str) and override.strip():
            return override
    return default


def apply_background_prompt(prompt: str, background: str) -> str:
    if not background.strip():
        return prompt
    if background.strip() in prompt:
        return prompt
    return f"{background} {prompt}"


def append_prompt_note(prompt: str, note: str) -> str:
    if not note.strip():
        return prompt
    return f"{prompt} {note}"


def _get_llm_retry_settings() -> tuple[int, float]:
    try:
        max_retries = int(os.getenv("LLM_STRUCTURED_RETRIES", "1"))
    except ValueError:
        max_retries = 1
    try:
        base_backoff = float(os.getenv("LLM_STRUCTURED_RETRY_BACKOFF_SECONDS", "0.5"))
    except ValueError:
        base_backoff = 0.5
    return max(0, max_retries), max(0.0, base_backoff)


def invoke_structured(state: EvalState, messages: list, schema: object):
    llm = get_llm(state)
    max_retries, base_backoff = _get_llm_retry_settings()
    total_attempts = max_retries + 1
    last_exc: Exception | None = None
    for method in ("json_schema", "function_calling"):
        try:
            structured_llm = llm.with_structured_output(
                schema,
                method=method,
                strict=True,
            )
        except Exception as exc:
            last_exc = exc
            logger.info(
                "invoke_structured: method=%s setup_error=%s",
                method,
                exc.__class__.__name__,
            )
            continue

        for attempt in range(total_attempts):
            try:
                return structured_llm.invoke(messages)
            except Exception as exc:
                last_exc = exc
                attempt_num = attempt + 1
                logger.info(
                    "invoke_structured: method=%s attempt=%s/%s error=%s",
                    method,
                    attempt_num,
                    total_attempts,
                    exc.__class__.__name__,
                )
                if attempt < max_retries:
                    time.sleep(base_backoff * (2 ** attempt))
    if last_exc:
        raise last_exc
    raise RuntimeError("invoke_structured: unknown error")


def get_study_by_id(studies: list[StudyDto], study_id: str) -> StudyDto | None:
    for study in studies:
        if str(study.studyId) == study_id:
            return study
    return None


def get_bucket_entry(bucket: list[dict], study_id: str) -> dict | None:
    for item in bucket:
        if str(item.get("study_id")) == study_id:
            return item
    return None


def upsert_bucket(bucket: list[dict], entry: dict) -> list[dict]:
    study_id = str(entry.get("study_id"))
    updated: list[dict] = []
    replaced = False
    for item in bucket:
        if str(item.get("study_id")) == study_id:
            updated.append(entry)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(entry)
    return updated


def remove_from_bucket(bucket: list[dict], study_id: str) -> list[dict]:
    return [item for item in bucket if str(item.get("study_id")) != study_id]


def get_pending_likely_study_ids(
    likely_matches: list[dict],
    very_likely: list[dict],
    rejected_likely: list[dict],
) -> list[str]:
    selected_ids = {
        str(item.get("study_id"))
        for item in very_likely
        if item.get("study_id") is not None
    }
    reviewed_ids = {
        str(item.get("study_id"))
        for item in rejected_likely
        if item.get("study_id") is not None
    }
    pending: list[str] = []
    for item in likely_matches:
        study_id = str(item.get("study_id", "")).strip()
        if not study_id:
            continue
        if study_id in selected_ids or study_id in reviewed_ids:
            continue
        if study_id not in pending:
            pending.append(study_id)
    return pending


def _normalize_identifier(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value.lower() if ch.isalnum())


def resolve_candidate_study_id(
    raw_study_id: str | None,
    candidates: list[dict],
    studies: list[StudyDto],
) -> str | None:
    token = (raw_study_id or "").strip()
    if not token:
        return None

    candidate_ids = {str(item.get("study_id")) for item in candidates if item.get("study_id")}
    if token in candidate_ids:
        return token

    aliases: dict[str, set[str]] = {}
    study_lookup = {str(study.studyId): study for study in studies}

    def add_alias(alias_value: str | None, study_id: str) -> None:
        normalized = _normalize_identifier(alias_value)
        if not normalized:
            return
        aliases.setdefault(normalized, set()).add(study_id)

    for item in candidates:
        study_id = str(item.get("study_id", "")).strip()
        if not study_id:
            continue
        add_alias(study_id, study_id)
        add_alias(item.get("short_name"), study_id)
        study = study_lookup.get(study_id)
        if study is not None:
            add_alias(study.shortName, study_id)
            add_alias(study.trialId, study_id)

    normalized_token = _normalize_identifier(token)
    mapped_ids = aliases.get(normalized_token, set())
    if len(mapped_ids) == 1:
        return next(iter(mapped_ids))

    # Handle values like "study_id 35006" by extracting candidate numeric IDs.
    numeric_tokens = re.findall(r"\d+", token)
    numeric_matches = [num for num in numeric_tokens if num in candidate_ids]
    if len(numeric_matches) == 1:
        return numeric_matches[0]

    return None
