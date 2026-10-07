"""The fields of a study that are calculated from its graph while the study has no value of its own (`derive` of a field
in config/study.yaml): the participants of a study as the sum of the sizes of the populations of its arms, its duration
as the longest duration of an arm. A study that gives its own value, e.g. because the report has no numbers per arm,
keeps it."""

from __future__ import annotations

import re
from typing import Any, List, Mapping, Optional

from .durations import Durations
from .graph import GraphFormatError, StoredGraph
from .studyconfig import STUDY_CONFIG, StudyFieldConfig


class DerivedFields:
    def __init__(self):
        self.stored = StoredGraph(STUDY_CONFIG.graph)
        self.durations = Durations()

    def value(self, field: StudyFieldConfig, graph: Optional[Mapping[str, Any] | str]) -> Optional[str]:
        """What the field is, as the study would hold it, according to the graph; None if the graph cannot tell."""
        derive = field.derive
        if derive is None:
            return None
        try:
            document = self.stored.loads(graph)
        except GraphFormatError:
            return None
        if document is None:
            return None
        # One group of values per entity the field is calculated over: those at the end of the path from it.
        groups: List[List[str]] = []
        for start in document.of_kind(derive.source):
            nodes = [start]
            for step in derive.path:
                nodes = [target for node in nodes for target in document.targets(step, node.id)]
            groups.append([str(node.value) for node in nodes if node.value is not None])
        found = [text for group in groups for text in group]
        covered = sum(1 for group in groups if group)
        if not found or (derive.aggregate == "sum" and covered != len(groups)):
            return None
        if field.type == "integer":
            numbers = [int(digits) for text in found if (digits := re.sub(r"[^\d]", "", text))]
            if len(numbers) != len(found):
                return None
            return str({"sum": sum, "max": max, "min": min}[derive.aggregate](numbers))
        seconds = [value for text in found if (value := self.durations.seconds(text)) is not None]
        if len(seconds) != len(found):
            return None
        return self.durations.format({"max": max, "min": min}[derive.aggregate](seconds))
