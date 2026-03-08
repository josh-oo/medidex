from __future__ import annotations

BACKGROUND_PROMPT = (
    "You are a clinical research assistant tasked with determining whether a new report belongs to an existing candidate study."
)

PDF_ATTACHMENT_PAYLOAD_NOTE = (
    "The text payload includes pdf_attachment with attachment_index, report_id, and title."
)

PDF_ATTACHMENT_NOTE = (
    "If provided, the PDF attachment is the report being matched. Use this attachment "
    "as supporting evidence."
)

SUMMARY_MARKDOWN_NOTE = (
    "Return the summary field in markdown. Do not wrap the output in code fences."
)

SUMMARY_MATCH_EVAL_NOTE = (
    "Check the field \"match\" in the payload to see if there is a definitive match."
    " Beware that items in very_likely and likely_matches are not considered as definitive matches. "
)

REASON_NOTE = "Always address studies by their short names."
LIKELY_GROUP_ID_NOTE = (
    "Return very_likely_study_ids using only candidate study_id values (Study IDs). "
    "Do not return trial registration IDs, short names, or free text in very_likely_study_ids. "
    "If none qualify, return an empty list."
)
LIKELY_COMPARE_ID_NOTE = (
    "If decision is match, study_id must be exactly one candidate study_id (Study ID) from the payload. "
    "Do not return trial registration IDs, short names, or free text in study_id."
)

from .constants import (
    COUNTRY_OPTIONS,
    DURATION_UNITS,
    STATUS_OF_STUDY_OPTIONS,
)

_COUNTRY_OPTIONS_TEXT = ", ".join(COUNTRY_OPTIONS)
_STATUS_OPTIONS_TEXT = ", ".join(STATUS_OF_STUDY_OPTIONS)
_DURATION_UNITS_TEXT = "|".join(DURATION_UNITS)

SUGGEST_NEW_STUDY_PROMPT = (
    "You are suggesting the creation of a new study based on the report and the evaluation context. "
    "Return a single new_study object that fits the add-study form. "
    "If a field is unknown, return an empty string for that field. "
    f"Allowed status_of_study values: {_STATUS_OPTIONS_TEXT}. "
    f"Allowed countries values: {_COUNTRY_OPTIONS_TEXT}. "
    f"duration_value must be 'None' if uncertain or 'integer'."
    f"duration_unit is one out of {_DURATION_UNITS_TEXT}. If not available convert it to the closest unit for example 30 minutes -> 0.5 hours"
    "number_of_participants must be a numeric string. "
    "Example output: "
    "{"
    "\"new_study\":{"
    "\"short_name\":\"Zhang 2025\","
    "\"status_of_study\":\"Planned\","
    "\"countries\":[\"Unclear\"],"
    "\"duration_value\":3,"
    "\"duration_unit\": \"months\,"
    "\"number_of_participants\":600,"
    "\"comparison\":[{\"intervention\": [\"Cognitive behavioural therapy\", \"Apriprozol\"], \"control\":[\"Treatment as usual\"]}]"
    "}"
    "}"
)

DEFAULT_EVAL_PROMPT = (
    "Determine whether the study is relevant to the report's intent. This is the first pass: "
    "respond ONLY with one of not_match, unsure, or likely_match. Never respond match "
    "in this pass."
)

DEFAULT_LIKELY_GROUP_PROMPT = (
    "You are reviewing studies previously marked as likely_match. Select 2 studies to "
    "mark as very_likely for a final comparison. Explain why you picked them but not the "
    "other studies. If none are strong, return an empty list."
)

DEFAULT_LIKELY_COMPARE_PROMPT = (
    "You are comparing the very_likely studie(s) to decide if any is a definitive match. "
    "Choose at most one match if you are highly confident; otherwise respond unsure. "
    "Explain why you picked / did not pick that study."
)

DEFAULT_LIKELY_REVIEW_PROMPT = (
    "You are reviewing studies that were initially marked likely_match but were not selected as very_likely. "
    "Use prior likely reasoning as context. Only choose match if you are highly confident; "
    "otherwise respond unsure or not_match."
)

DEFAULT_UNSURE_REVIEW_PROMPT = (
    "You are reviewing unsure studies. Use the rejected likely_match list as historical "
    "context. Only choose match if you are highly confident; otherwise respond unsure or "
    "not_match."
)

DEFAULT_SUMMARY_PROMPT = (
    "You are summarizing the evaluation results for the report. Use the report details "
    "and prior decisions. "
    "Explain why it matches and explicitly "
    "state why the other studies are not matched. If there is no definitive match, explain why no "
    "study matches."
)
