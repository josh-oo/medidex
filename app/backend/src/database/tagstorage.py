"""Where the tags of each category of config/study.yaml are stored."""

from dataclasses import dataclass
from typing import Any, Dict, List, Union

from .models import (
    Condition, Design, Intervention, Outcome, Participant, Study,
    StudyCondition, StudyDesign, StudyIntervention, StudyOutcome, StudyParticipant,
)
from ..utils.studyconfig import INLINE_SEPARATOR
from ..utils.tagconfig import TAG_CATEGORIES


@dataclass(frozen=True)
class TagTable:
    """Tags in a table of their own (id, description), linked to studies by a link table."""

    tag: Any  # table of the tags
    link: Any  # table linking studies and tags
    link_study: Any  # its study column
    link_tag: Any  # its tag column


@dataclass(frozen=True)
class StudyColumn:
    """Tags kept in a column of the study itself, separated by `//`."""

    column: Any
    separator: str = INLINE_SEPARATOR

    def split(self, value: str | None) -> List[str]:
        return [part.strip() for part in (value or "").split(self.separator) if part.strip()]


TAG_STORAGE: Dict[str, Union[TagTable, StudyColumn]] = {
    "interventions": TagTable(Intervention, StudyIntervention, StudyIntervention.study_id, StudyIntervention.intervention_id),
    "conditions": TagTable(Condition, StudyCondition, StudyCondition.study_id, StudyCondition.condition_id),
    "outcomes": TagTable(Outcome, StudyOutcome, StudyOutcome.study_id, StudyOutcome.outcome_id),
    "participants": TagTable(Participant, StudyParticipant, StudyParticipant.study_id, StudyParticipant.participant_id),
    "design": TagTable(Design, StudyDesign, StudyDesign.study_id, StudyDesign.design_id),
    "countries": StudyColumn(Study.countries),
}

TAG_TABLES: Dict[str, TagTable] = {name: storage for name, storage in TAG_STORAGE.items() if isinstance(storage, TagTable)}
TAG_COLUMNS: Dict[str, StudyColumn] = {name: storage for name, storage in TAG_STORAGE.items() if isinstance(storage, StudyColumn)}

_missing = [name for name in TAG_CATEGORIES if name not in TAG_STORAGE]
if _missing:
    raise RuntimeError(f"config/study.yaml defines categories without storage in tagstorage.py: {_missing}")

_inconsistent = [name for name, storage in TAG_STORAGE.items() if TAG_CATEGORIES[name].inline != isinstance(storage, StudyColumn)]
if _inconsistent:
    raise RuntimeError(f"config/study.yaml `inline` disagrees with the storage in tagstorage.py for: {_inconsistent}")
