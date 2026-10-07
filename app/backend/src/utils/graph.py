"""The graph of a study (`graph` of config/study.yaml) as the study keeps it: JSON with nodes and edges. A node is an
entity of a kind of the config; it has no properties, only edges (relations) to other nodes. What looks like a property
of an arm, its dosage or its interventions, is an edge to a node that is a value:

    {"nodes": [{"id": "arm1", "kind": "arm"},
               {"id": "arm2", "kind": "arm"},
               {"id": "intervention1", "kind": "intervention", "value": 3000001},
               {"id": "dosage1", "kind": "dosage", "value": "10 mg"},
               {"id": "population1", "kind": "population"},
               {"id": "size1", "kind": "size", "value": "60"}],
     "edges": [{"relation": "interventions", "source": "arm1", "target": "intervention1"},
               {"relation": "dosage", "source": "arm1", "target": "dosage1"},
               {"relation": "comparison", "source": "arm1", "target": "arm2"},
               {"relation": "participated", "source": "arm1", "target": "population1"},
               {"relation": "size", "source": "population1", "target": "size1"}]}

The value of a node that is a tag is the id of the tag. The study itself is a node too (the root entity of
config/study.yaml), with the id `study` and no JSON of its own, so that a relation can start at the study as a whole:
{"relation": "participated", "source": "study", "target": "population1"}. A study has as many arms as it has arm
nodes, and a comparison connects any two of them; arms without one are fine. A value is one node however many edges
lead to it (every arm with the dosage "10 mg" points to the same node).

The study stores it as a JSONB object; creating a study takes the JSON text, also with names instead of ids for the
tags. Studies from before the entity model hold the arms and populations with their properties inline ({"nodes":
{"arm": [{"id": ..., "interventions": [...], "dosage": ...}]}, "relations": {"comparison": [...]}}); reading
converts them."""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from .studyconfig import GraphConfig

Item = Union[int, str]


class GraphFormatError(ValueError):
    """The graph of a study does not follow the graph of config/study.yaml."""


@dataclass
class GraphNode:
    id: str
    kind: str
    value: Optional[Item] = None  # the id (or, in a payload, the name) of a tag, or the text of a primitive value


@dataclass
class GraphEdge:
    relation: str
    source: str
    target: str


@dataclass
class GraphDocument:
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.nodes

    def node(self, node_id: str) -> Optional[GraphNode]:
        return next((node for node in self.nodes if node.id == node_id), None)

    def of_kind(self, kind: str) -> List[GraphNode]:
        return [node for node in self.nodes if node.kind == kind]

    def targets(self, relation: str, source: str) -> List[GraphNode]:
        """The nodes the relation leads to from the node, in the order of the edges."""
        found = (self.node(edge.target) for edge in self.edges if edge.relation == relation and edge.source == source)
        return [node for node in found if node is not None]


class StoredGraph:
    def __init__(self, config: GraphConfig):
        self.config = config

    # -- reading ------------------------------------------------------------------------------------------------

    def loads(self, raw: Union[str, Mapping[str, Any], None]) -> Optional[GraphDocument]:
        """The graph of the stored JSON (an object) or of a JSON text, None if there is nothing. Raises
        GraphFormatError if it is no graph of config/study.yaml."""
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError as exc:
            raise GraphFormatError(f"the graph is no JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise GraphFormatError("the graph is a JSON object with `nodes` and `edges`")
        if isinstance(data.get("nodes"), dict):  # a study from before the entity model
            data = self._legacy(data)
        unknown = set(data) - {"nodes", "edges"}
        if unknown:
            raise GraphFormatError(f"unknown keys of the graph: {sorted(unknown)}")
        nodes, edges = data.get("nodes") or [], data.get("edges") or []
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise GraphFormatError("`nodes` and `edges` are lists")
        document = GraphDocument([self._node(entry) for entry in nodes])
        ids = [node.id for node in document.nodes]
        if len(set(ids)) != len(ids) or self.config.root_id in ids:
            raise GraphFormatError(f"the ids of the nodes must be unique (and not `{self.config.root_id}`, which is the study itself)")
        for entry in edges:
            document.edges.append(self._edge(document, entry))
        self._check_cardinality(document)
        return document

    def _node(self, entry: Any) -> GraphNode:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"].strip():
            raise GraphFormatError("every node has an `id` (text) and a `kind`")
        unknown = set(entry) - {"id", "kind", "value"}
        kind = entry.get("kind")
        if unknown or kind not in self.config.entities or self.config.entities[kind].root:
            known = [key for key, entity in self.config.entities.items() if not entity.root]
            raise GraphFormatError(f"node {entry['id']!r}: it has a `kind` ({', '.join(known)}) and a `value` if the kind is a value")
        node = GraphNode(entry["id"].strip(), kind, self._value(kind, entry.get("value")))
        return node

    def _value(self, kind: str, value: Any) -> Optional[Item]:
        config = self.config.entities[kind].value
        if config is None:
            if value not in (None, ""):
                raise GraphFormatError(f"a node of kind '{kind}' has no value")
            return None
        if config.category is not None:
            if isinstance(value, bool) or not isinstance(value, (int, str)) or value == "":
                raise GraphFormatError(f"a node of kind '{kind}' has the id or the name of a tag as its value")
            return value.strip() if isinstance(value, str) else value
        text = str(value).strip() if value is not None else ""
        if not text:
            raise GraphFormatError(f"a node of kind '{kind}' needs a value")
        if config.type == "enum" and text not in config.values:
            raise GraphFormatError(f"a node of kind '{kind}' has one of these values: {', '.join(config.values)}")
        if config.type == "integer" and not re.fullmatch(r"\d+", text):
            raise GraphFormatError(f"a node of kind '{kind}' has a whole number as its value")
        return text

    def _edge(self, document: GraphDocument, entry: Any) -> GraphEdge:
        if not isinstance(entry, dict) or set(entry) != {"relation", "source", "target"}:
            raise GraphFormatError('an edge is {"relation": name, "source": id, "target": id}')
        relation = self.config.relations.get(entry["relation"])
        if relation is None:
            raise GraphFormatError(f"unknown relation '{entry['relation']}' (known: {', '.join(self.config.relations)})")
        kinds = []
        for end in ("source", "target"):
            node_id = str(entry[end])
            node = document.node(node_id)
            kinds.append(self.config.root if node_id == self.config.root_id else (node.kind if node else None))
        if kinds[0] not in relation.source or kinds[1] not in relation.target:
            raise GraphFormatError(
                f"relation '{entry['relation']}': an edge goes from a node of kind {kinds[0]} to one of kind {kinds[1]}, "
                f"which it cannot ({'/'.join(relation.source)} to {'/'.join(relation.target)})"
            )
        return GraphEdge(entry["relation"], str(entry["source"]), str(entry["target"]))

    def _check_cardinality(self, document: GraphDocument) -> None:
        seen: set = set()
        for edge in document.edges:
            if not self.config.relations[edge.relation].many:
                if (edge.relation, edge.source) in seen:
                    raise GraphFormatError(f"relation '{edge.relation}': {edge.source} has more than one (it is not `many`)")
                seen.add((edge.relation, edge.source))

    def _legacy(self, data: Mapping[str, Any]) -> Dict[str, Any]:
        """The graph of an older study, with the properties of its entities inline, as nodes and edges."""
        document = GraphDocument()
        for kind, entries in data["nodes"].items():
            for entry in entries if isinstance(entries, list) else []:
                if not isinstance(entry, dict) or "id" not in entry:
                    raise GraphFormatError("every node has an `id`")
                document.nodes.append(GraphNode(str(entry["id"]), kind))
                for key, value in entry.items():
                    relation = self.config.relations.get(key)
                    if key == "id" or relation is None or kind not in relation.source or not self.config.is_attribute(key):
                        continue
                    for item in value if isinstance(value, list) else [value]:
                        if item not in (None, ""):
                            target = self._value_node(document, relation.target[0], item)
                            document.edges.append(GraphEdge(key, str(entry["id"]), target))
        for key, edges in (data.get("relations") or {}).items():
            document.edges.extend(GraphEdge(key, str(edge["source"]), str(edge["target"])) for edge in edges)
        return self.dump(document) or {}

    # -- writing ------------------------------------------------------------------------------------------------

    def dumps(self, document: GraphDocument) -> Optional[str]:
        """The JSON text of the graph, None if it has no nodes."""
        data = self.dump(document)
        return None if data is None else json.dumps(data)

    def dump(self, document: GraphDocument) -> Optional[Dict[str, Any]]:
        """The graph as the JSON object the study stores, None if it has no nodes."""
        if document.is_empty():
            return None
        return {
            "nodes": [
                {"id": node.id, "kind": node.kind, **({"value": node.value} if node.value is not None else {})}
                for node in document.nodes
            ],
            "edges": [{"relation": edge.relation, "source": edge.source, "target": edge.target} for edge in document.edges],
        }

    # -- profiles: a node as the values it is related to --------------------------------------------------------------

    def profile(self, document: GraphDocument, node: GraphNode) -> Dict[str, List[Item]]:
        """What the node says about itself: the values at the end of its attribute relations (the interventions, dosage,
        duration of an arm), by relation, in the order of the config."""
        profile: Dict[str, List[Item]] = {}
        for key in self.config.attributes_of(node.kind):
            values = [target.value for target in document.targets(key, node.id) if target.value is not None]
            if values:
                profile[key] = values
        return profile

    def from_entries(self, entries: Mapping[str, Sequence[Mapping[str, Mapping[str, Any]]]]) -> GraphDocument:
        """The graph of entries, which are edges with their two entities inline: `{relation: [{"source": end, "target":
        end}]}`, an end being its `kind` (left out if the relation allows one kind there) and what it says about itself by
        attribute relation (a list of values, or one value): {"kind": "arm", "interventions": ["Drug A"], "dosage": "10
        mg"}. The study itself is `{"kind": "study"}`. An entity that several entries mention with the same attributes
        (e.g. the placebo arm of two comparisons) is one node, and a value is one node however often it occurs."""
        document = GraphDocument()
        for relation_key, relation_entries in entries.items():
            relation = self.config.relations[relation_key]
            for entry in relation_entries:
                ids = {
                    end: self._merge(document, relation.source if end == "source" else relation.target, entry.get(end) or {})
                    for end in ("source", "target")
                }
                document.edges.append(GraphEdge(relation_key, ids["source"], ids["target"]))
        return document

    def _merge(self, document: GraphDocument, allowed: Sequence[str], end: Mapping[str, Any]) -> str:
        """The id of the entity the end describes: the study itself, or a node (an existing one with the same attributes,
        else a new one with its value nodes)."""
        kind = end.get("kind") or (allowed[0] if len(allowed) == 1 else None)
        if kind not in allowed:
            raise GraphFormatError(f"an entity of kind {kind!r} is not allowed here (allowed: {', '.join(allowed)})")
        if self.config.entities[kind].root:
            return self.config.root_id
        attributes = self.config.attributes_of(kind)
        wanted: Dict[str, List[Item]] = {}
        for key in attributes:
            raw = end.get(key)
            values = [item for item in (raw if isinstance(raw, list) else [raw]) if item not in (None, "")]
            if values:
                wanted[key] = values if attributes[key].many else values[:1]
        identity = self._identity(wanted)
        for node in document.of_kind(kind):
            if node.kind == kind and self._identity(self.profile(document, node)) == identity:
                return node.id
        node = GraphNode(self._new_id(document, kind), kind)
        document.nodes.append(node)
        for key, values in wanted.items():
            for value in values:
                target = self._value_node(document, attributes[key].target[0], value)
                document.edges.append(GraphEdge(key, node.id, target))
        return node.id

    def _value_node(self, document: GraphDocument, kind: str, value: Any) -> str:
        """The id of the node of this kind with this value; a new one if there is none yet."""
        checked = self._value(kind, value)
        for node in document.of_kind(kind):
            if str(node.value).casefold() == str(checked).casefold():
                return node.id
        node = GraphNode(self._new_id(document, kind), kind, checked)
        document.nodes.append(node)
        return node.id

    @staticmethod
    def _new_id(document: GraphDocument, kind: str) -> str:
        return f"{kind}{len(document.of_kind(kind)) + 1}"

    @staticmethod
    def _identity(profile: Mapping[str, Sequence[Item]]) -> Any:
        """What makes two entities the same: the same values, ignoring case and order."""
        return frozenset((key, frozenset(str(item).casefold() for item in items)) for key, items in profile.items())
