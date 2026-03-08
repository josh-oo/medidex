from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, field_validator

from .constants import (
    COUNTRY_OPTIONS,
    DURATION_UNCERTAIN_VALUE,
    DURATION_UNITS,
    STATUS_OF_STUDY_OPTIONS,
)
Decision = Literal["match", "not_match", "unsure", "likely_match"]
ModelName = Literal["gpt-5.2", "gpt-5", "gpt-5-mini", "gpt-4.1"]


class ReportDto(BaseModel):
    reportId: int
    year: int 
    title: str
    abstract: str | None
    trialId: str | None
    authors: list[str]

class StudyDto(BaseModel):
    studyId: int
    shortName: str
    countries: list[str]
    numberParticipants: str | None
    duration: str | None
    comparison: str | None
    trialId: str | None
    status: str
    createdAt: str
    updatedAt: str

class PromptOverrides(BaseModel):
    background_prompt: str | None = None
    initial_eval_prompt: str | None = None
    likely_group_prompt: str | None = None
    likely_compare_prompt: str | None = None
    likely_review_prompt: str | None = None
    unsure_review_prompt: str | None = None
    summary_prompt: str | None = None
    pdf_prompt: str | None = None


class InitialDecisionOutput(BaseModel):
    decision: Literal["not_match", "unsure", "likely_match"]
    reason: str


class LikelyGroupOutput(BaseModel):
    very_likely_study_ids: list[str]
    reason: str


class LikelyCompareOutput(BaseModel):
    decision: Literal["match", "unsure"]
    study_id: str
    reason: str


class LikelyReviewOutput(BaseModel):
    decision: Literal["match", "unsure", "not_match"]
    reason: str


class UnsureReviewOutput(BaseModel):
    decision: Literal["match", "unsure", "not_match"]
    reason: str

class Comparison(BaseModel):
    intervention: list[str]
    control: list[str]

class NewStudySuggestion(BaseModel):
    short_name: str
    status_of_study: Literal["Closed", "Stopped early", "Open/Ongoing", "Planned"]
    countries: list[str]
    duration_value: int
    duration_unit: Literal["hours", "days", "weeks", "months", "years"]
    number_of_participants: int
    comparison: list[Comparison]

    #@field_validator("countries")
    #@classmethod
    #def validate_countries(cls, value: list[str]) -> list[str]:
    #    value = value.strip()
    #    if not value:
    #        return ""
    #    if value not in set(COUNTRY_OPTIONS):
    #        raise ValueError("Invalid country value.")
    #    return value

    #@field_validator("duration")
    #@classmethod
    #def validate_duration(cls, value: str) -> str:
    #    value = value.strip()
    #    if not value:
    #        return ""
    #    if value == DURATION_UNCERTAIN_VALUE:
    #        return value
    #    parts = value.split(" ")
    #    if len(parts) != 2:
    #        raise ValueError("Invalid duration format.")
     #   number, unit = parts
     #   if not number.isdigit():
    #      raise ValueError("Invalid duration number.")
    #    if unit not in set(DURATION_UNITS):
    #        raise ValueError("Invalid duration unit.")
    #    return value

    #@field_validator("number_of_participants")
    #@classmethod
    #def validate_participants(cls, value: str) -> str:
    #    value = value.strip()
    #    if not value:
    #        return ""
    #    if not value.isdigit():
    #        raise ValueError("Invalid number_of_participants.")
    #    return value

    #@field_validator("status_of_study")
    #@classmethod
    #def validate_status(cls, value: str) -> str:
    #    value = value.strip()
    #    if value not in set(STATUS_OF_STUDY_OPTIONS):
    #        raise ValueError("Invalid status_of_study.")
    #    return value


class SummaryOutput(BaseModel):
    has_match: bool
    summary: str


class SuggestNewStudyOutput(BaseModel):
    new_study: NewStudySuggestion


class EvaluateRequest(BaseModel):
    report: ReportDto
    studies: list[StudyDto]
    model: ModelName | None = None
    include_pdf: bool | None = False
    prompt_overrides: PromptOverrides | None = None


class StudyDecision(BaseModel):
    study_id: str
    decision: Decision
    reason: str


class VeryLikelyDecision(BaseModel):
    study_id: str
    prior_reason: str | None
    group_reason: str | None


class EvaluateResponse(BaseModel):
    match: StudyDecision | None
    not_matches: list[StudyDecision]
    unsure: list[StudyDecision]
    likely_matches: list[StudyDecision]
    very_likely: list[VeryLikelyDecision]
    evaluation_has_match: bool | None = None
    evaluation_summary: str | None = None
    evaluation_new_study: NewStudySuggestion | None = None


class EvalState(TypedDict):
    report: ReportDto
    studies: list[StudyDto]
    idx: int
    unsure_idx: int
    unsure_queue: list[str]
    current: StudyDto | None
    study_id: str | None  # Current study ID being processed (for streaming)
    decision: Decision | None
    reason: str | None
    include_pdf: bool
    prompt_overrides: dict[str, str | None] | None
    llm: Any | None
    match: dict | None
    not_matches: list[dict]
    unsure: list[dict]
    likely_matches: list[dict]
    very_likely: list[dict]
    rejected_likely: list[dict]
    evaluation_summary: dict | None
    report_pdf_attachment: dict | None
    pdf_status: str | None
    new_study_suggestion: dict | None
