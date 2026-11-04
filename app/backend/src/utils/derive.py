"""The fields of a study that are views of its graph (`derive` of a field in config/medidex-study.yaml): the participants of
a study as the size of its population (else the sum of the sizes of the populations of its arms), its duration as the
longest duration of an arm, its trial id as the first of its registration ids. The graph is the only source of truth: the
column of such a field is a copy of what is read here, written whenever the graph is (src/database/repositories/graphs.py),
and a value given for the field is written into the graph by its first rule (`write`)."""

from __future__ import annotations

import re
from typing import Any, List, Mapping, Optional

from .durations import Durations
from .graph import GraphDocument, GraphEdge, GraphFormatError, GraphNode, StoredGraph
from .studyconfig import STUDY_CONFIG, FieldDeriveConfig, StudyFieldConfig


class DerivedFields:
    def __init__(self):
        self.config = STUDY_CONFIG.graph
        self.stored = StoredGraph(self.config)
        self.durations = Durations()

    def value(self, field: StudyFieldConfig, graph: Optional[Mapping[str, Any] | str | GraphDocument]) -> Optional[Any]:
        """What the field is according to the graph, as the study holds it (a number, a duration in seconds, a text); None
        if the graph cannot tell."""
        try:
            document = graph if isinstance(graph, GraphDocument) else self.stored.loads(graph)
        except GraphFormatError:
            return None
        if document is None:
            return None
        for rule in field.derive:
            found = self._read(field, rule, document)
            if found is not None:
                return found
        return None

    def columns(self, document: Optional[GraphDocument]) -> dict[str, Any]:
        """The columns of the derived fields of a study (src/database/models.py) as its graph says."""
        return {
            field.column: (self.value(field, document) if document is not None else None)
            for field in STUDY_CONFIG.fields.values()
            if field.derive
        }

    def writable(self, field: StudyFieldConfig) -> bool:
        """Whether a value of the field can be written into the graph: its first rule starts at the study."""
        return bool(field.derive) and self.config.entities[field.derive[0].source].root

    def write(self, document: GraphDocument, field: StudyFieldConfig, value: Any) -> None:
        """Writes the value of the field into the graph by its first rule, which starts at the study: the entities on its path
        are the first ones there, made if there are none (the population of the study), and the value replaces what is at
        its end. Raises GraphFormatError for a value the field cannot hold or a field that is not written so."""
        if not self.writable(field):
            raise GraphFormatError(f"the field {field.label} is read from the graph and cannot be set itself")
        rule = field.derive[0]
        node_id = self.config.root_id
        for step in rule.path[:-1]:
            found = [edge.target for edge in document.edges if edge.relation == step and edge.source == node_id]
            if found:
                node_id = found[0]
                continue
            kind = self.config.relations[step].target[0]
            created = GraphNode(StoredGraph.new_id(document, kind), kind)
            document.nodes.append(created)
            document.edges.append(GraphEdge(step, node_id, created.id))
            node_id = created.id
        last = rule.path[-1]
        document.edges[:] = [edge for edge in document.edges if not (edge.relation == last and edge.source == node_id)]
        if value is None or value == "":
            self.stored.prune(document)
            return
        text = self.durations.format(int(value)) if field.type == "duration" and isinstance(value, int) else str(value)
        target = self.stored.value_node(document, self.config.relations[last].target[0], text)
        document.edges.append(GraphEdge(last, node_id, target))
        self.stored.prune(document)

    def _read(self, field: StudyFieldConfig, rule: FieldDeriveConfig, document: GraphDocument) -> Optional[Any]:
        # One group of values per entity the field is calculated over: those at the end of the path from it.
        starts = [self.config.root_id] if self.config.entities[rule.source].root else [node.id for node in document.of_kind(rule.source)]
        groups: List[List[str]] = []
        for start in starts:
            ids = [start]
            for step in rule.path:
                ids = [edge.target for node_id in ids for edge in document.edges if edge.relation == step and edge.source == node_id]
            values = [node.value for node_id in ids if (node := document.node(node_id)) is not None and node.value is not None]
            groups.append([str(value) for value in values])
        found = [text for group in groups for text in group]
        covered = sum(1 for group in groups if group)
        if not found or (rule.aggregate == "sum" and covered != len(groups)):
            return None
        if field.type == "integer":
            numbers = [int(digits) for text in found if (digits := re.sub(r"[^\d]", "", text))]
            if len(numbers) != len(found):
                return None
            return numbers[0] if rule.aggregate == "first" else {"sum": sum, "max": max, "min": min}[rule.aggregate](numbers)
        if field.type == "duration":
            seconds = [value for text in found if (value := self.durations.seconds(text)) is not None]
            if len(seconds) != len(found):
                return None
            return int(seconds[0] if rule.aggregate == "first" else {"max": max, "min": min}[rule.aggregate](seconds))
        return found[0]
