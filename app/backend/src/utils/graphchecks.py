"""Extension point for rules a deployable checks the graph of a study against beyond its shape (which StoredGraph.loads
checks), e.g. that the arms of a study have no more participants than the study. Downstream deployables register their
checks at startup.

Every graph a study stores (created, edited, imported, merged) goes through the checks in the order they were registered
(StudyGraphs.document): a check returns the graph, normalized where that loses nothing, or raises GraphFormatError naming
what the graph breaks, and the graph is not stored (422; 409 for a merge).
"""

from typing import List, Protocol

from .graph import GraphDocument


class GraphCheck(Protocol):
    def check(self, document: GraphDocument) -> GraphDocument:
        """The graph, normalized; raises GraphFormatError if it breaks a rule."""
        ...


class GraphCheckRegistry:
    def __init__(self) -> None:
        self._checks: List[GraphCheck] = []

    def register(self, check: GraphCheck) -> None:
        self._checks.append(check)

    def all(self) -> List[GraphCheck]:
        return list(self._checks)

    def check(self, document: GraphDocument) -> GraphDocument:
        for check in self._checks:
            document = check.check(document)
        return document


graph_check_registry = GraphCheckRegistry()
