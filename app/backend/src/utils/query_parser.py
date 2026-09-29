"""The advanced study-search query language: a tree of field==value comparisons
combined with AND/OR groups. Modeled as pydantic types (Comparison/AndGroup/OrGroup
below) rather than a bespoke AST class, for two reasons:

- It's the type an MCP tool can take directly as a structured argument
  (mcp_server/tools.py's search_studies) - a client fills in the JSON schema pydantic
  derives from these models, so there's no string grammar for a model to get wrong in
  the first place, and no field-name typo to reject at runtime (AdvancedSearchField is
  a closed enum, validated before the tool body ever runs).
- The REST API (fastapi_app/resources.py) still takes a plain query string, since
  that's what a URL query param is - parse_advanced_query() below turns that string
  into the same pydantic tree, so both callers end up with one shape and
  StudyRepository.search_studies_advanced only has to translate one thing to SQL.

Precedence note: the string grammar has AND bind tighter than OR (both
left-associative), matching how most people read "A and B or C". The structured
(pydantic) form has no such ambiguity to begin with - AndGroup/OrGroup nesting *is*
the precedence, spelled out explicitly - which is one of the reasons it's the better
fit for a tool-calling model.
"""

from enum import Enum
from typing import Annotated, List, Literal, Union

from pydantic import BaseModel, Field, ValidationError, field_validator
from pyparsing import (
    CaselessKeyword,
    Group,
    ParseBaseException,
    ParseFatalException,
    QuotedString,
    SkipTo,
    StringEnd,
    Word,
    alphanums,
    alphas,
    infix_notation,
    oneOf,
    opAssoc,
)


class QuerySyntaxError(ValueError):
    pass


class AdvancedSearchField(str, Enum):
    NAME = "name"
    TRIAL_ID = "trialId"
    AUTHOR = "author"
    STATUS = "status"
    COUNTRY = "country"
    INTERVENTION = "intervention"
    CONDITION = "condition"
    OUTCOME = "outcome"
    PARTICIPANT = "participant"
    DESIGN = "design"


# Common alternate spellings (plurals, the REST DTO's camelCase, snake_case) that both
# a human typing the string grammar and a model filling in the structured form tend to
# reach for instead of the exact enum value - accepted as synonyms rather than rejected.
_FIELD_ALIASES = {
    "shortname": AdvancedSearchField.NAME,
    "studyname": AdvancedSearchField.NAME,
    "trial_id": AdvancedSearchField.TRIAL_ID,
    "trialregistrationid": AdvancedSearchField.TRIAL_ID,
    "trial_registration_id": AdvancedSearchField.TRIAL_ID,
    "authors": AdvancedSearchField.AUTHOR,
    "countries": AdvancedSearchField.COUNTRY,
    "interventions": AdvancedSearchField.INTERVENTION,
    "conditions": AdvancedSearchField.CONDITION,
    "outcomes": AdvancedSearchField.OUTCOME,
    "participants": AdvancedSearchField.PARTICIPANT,
    "designs": AdvancedSearchField.DESIGN,
}


class Comparison(BaseModel):
    """A single field==value condition - a case-insensitive substring match."""

    type: Literal["comparison"] = "comparison"
    field: AdvancedSearchField = Field(description="Which study attribute to match.")
    value: str = Field(min_length=1, description="Substring to match against that field, case-insensitively.")

    @field_validator("field", mode="before")
    @classmethod
    def _normalize_field(cls, value):
        if isinstance(value, str):
            return _FIELD_ALIASES.get(value.strip().lower(), value.strip().lower())
        return value


class AndGroup(BaseModel):
    """Matches only if every operand matches."""

    type: Literal["and"] = "and"
    operands: List["QueryNode"] = Field(min_length=2, description="Conditions that must all match.")


class OrGroup(BaseModel):
    """Matches if at least one operand matches."""

    type: Literal["or"] = "or"
    operands: List["QueryNode"] = Field(min_length=2, description="Conditions where at least one must match.")


QueryNode = Annotated[Union[Comparison, AndGroup, OrGroup], Field(discriminator="type")]

AndGroup.model_rebuild()
OrGroup.model_rebuild()


"""
String grammar (REST only) - parses into the same Comparison/AndGroup/OrGroup tree.

`field==value` (or `field=value`) comparisons combined with AND/OR (AND binds tighter
than OR, both left-associative) and optional parentheses for grouping, e.g.
`intervention==Drug A AND condition==Sick OR condition==Healthy`. Values may be quoted
(single or double quotes) to include literal "AND"/"OR"/")" text; otherwise a value
runs up to the next AND/OR/")"/end of string.
"""

_AND = CaselessKeyword("AND")
_OR = CaselessKeyword("OR")
_value_boundary = _AND | _OR | ")" | StringEnd()

_field = Word(alphas, alphanums + "_")
_operator = oneOf(["==", "="])
_quoted_value = QuotedString('"') | QuotedString("'")
_bare_value = SkipTo(_value_boundary).set_parse_action(lambda t: t[0].strip())
_value = _quoted_value | _bare_value


def _to_comparison(tokens):
    # ParseFatalException (unlike plain ParseException) aborts parsing immediately with
    # this exact message instead of being swallowed as an ordinary backtracking failure
    # by infix_notation trying other alternatives - both failures below are unambiguous
    # (the comparison already matched the field==value shape), so there's nothing useful
    # left to backtrack into.
    field, _op, value = tokens[0]
    if not value:
        raise ParseFatalException(f"Empty value for field '{field}'")
    try:
        return Comparison(field=field, value=value)
    except ValidationError as exc:
        valid_fields = ", ".join(member.value for member in AdvancedSearchField)
        raise ParseFatalException(f"Unknown field '{field}'. Valid fields: {valid_fields}") from exc


_comparison = Group(_field + _operator + _value)
_comparison.set_parse_action(_to_comparison)

_expr = infix_notation(
    _comparison,
    [
        (_AND, 2, opAssoc.LEFT, lambda t: AndGroup(operands=list(t[0][0::2]))),
        (_OR, 2, opAssoc.LEFT, lambda t: OrGroup(operands=list(t[0][0::2]))),
    ],
)


_SYNTAX_HINT = (
    "Expected one or more field==value comparisons combined with AND/OR (AND binds "
    "tighter than OR; use parentheses to override), e.g. "
    'intervention==Metformin AND condition==Diabetes OR condition==Prediabetes. '
    'Quote a value that itself contains the word AND/OR, a closing parenthesis, or '
    'leading/trailing whitespace to keep, e.g. condition=="Type 2 Diabetes".'
)


def parse_advanced_query(query: str) -> "QueryNode":
    """Parse an advanced-search query string (REST API only - the MCP tool takes the
    Comparison/AndGroup/OrGroup tree directly) into that same tree.

    Raises QuerySyntaxError on malformed input (bad syntax, empty value, unknown field,
    unmatched parentheses, ...) - the message always restates the expected grammar and
    a worked example, since a human retyping a URL query param is the only caller left
    who ever sees it.
    """
    if not query or not query.strip():
        raise QuerySyntaxError(f"Query must not be empty. {_SYNTAX_HINT}")
    try:
        result = _expr.parse_string(query, parse_all=True)
    except ParseBaseException as exc:
        raise QuerySyntaxError(
            f"Invalid query syntax at position {exc.col}: {exc.msg}. {_SYNTAX_HINT}"
        ) from exc
    return result[0]
