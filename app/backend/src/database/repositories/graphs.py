"""The graph of a study (the study ontology, config/medidex-study.yaml): storing it when a study is created or changed,
adding edges to it, and reading the graphs of studies with their tags named. The graph is the only source of truth of what
it holds: a value given for a field that is derived from it (the participants of the study) is written into it, the
columns of those fields are copies of it, and the tags of its values are the tags of the study. A graph that breaks a rule
a deployable checks (src/utils/graphchecks.py) is not stored."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from sqlmodel import delete, func, select

from ...utils.derive import DerivedFields
from ...utils.dto import StudyGraph, StudyGraphEdge, StudyGraphNode
from ...utils.graph import GraphDocument, GraphFormatError, Item, StoredGraph
from ...utils.graphchecks import GraphCheckRegistry, graph_check_registry
from ...utils.studyconfig import GRAPH_FIELD, STUDY_CONFIG
from ..models import Study, StudyFields, StudyTag, Tag, UpdateStudy
from ...utils.tagconfig import TAG_CATEGORIES


class StudyGraphs:
    def __init__(self, db, checks: GraphCheckRegistry = graph_check_registry):
        self.db = db
        self.config = STUDY_CONFIG.graph
        self.stored = StoredGraph(self.config)
        self.checks = checks
        self.derived = DerivedFields()

    def _category(self, kind: str) -> Optional[str]:
        value = self.config.entities[kind].value
        return value.category if value else None

    def document(self, values: Mapping[str, Any]) -> GraphDocument:
        """The graph of the payload `values`, with the values given for the fields derived from it written into it (see
        DerivedFields.write; a field it cannot be written into, such as the duration of the arms, is read from it only),
        checked (src/utils/graphchecks.py). Raises GraphFormatError if it is no graph of config/medidex-study.yaml or breaks
        a rule of a check."""
        document = self.stored.loads(values.get(GRAPH_FIELD)) or GraphDocument()
        for key, field in STUDY_CONFIG.fields.items():
            value = values.get(key)
            if value in (None, "") or not self.derived.writable(field):
                continue
            if field.type == "integer":
                value = int(value)
            if self.derived.value(field, document) != value:
                self.derived.write(document, field, value)
        return self.checks.check(document)

    def draft(self, study: UpdateStudy, values: Mapping[str, Any]) -> None:
        """Stores the graph of a study of an update from the payload `values` (see `document`): its tags stay names (or ids
        of tags that exist) and only become tags of the core database when the study is merged (see store)."""
        document = self.document(values)
        setattr(study, GRAPH_FIELD, self.stored.dump(document))
        self._copy_fields(study, document)

    async def store(self, study: Study, values: Mapping[str, Any]) -> None:
        """Stores the graph of a study of the core database from the payload `values` (see `document`; or the graph of the
        study of an update it is merged from): the tags of its nodes, given by name or id, become ids of the tags of their
        category (an unknown name becomes a new tag), and the tags of the study are those of its graph (a tag the graph no
        longer has is no tag of the study any more)."""
        document = self.document(values)
        try:
            before = self.stored.loads(getattr(study, GRAPH_FIELD, None)) or GraphDocument()
        except GraphFormatError:
            before = GraphDocument()
        for node in document.nodes:
            category = self._category(node.kind)
            if category is not None:
                node.value = (await self.resolve(category, [node.value]))[0]  # type: ignore[list-item]
        setattr(study, GRAPH_FIELD, self.stored.dump(document))
        self._copy_fields(study, document)
        await self._link(study.id, document, before)
        await self.db.flush()

    async def named(self, study: StudyFields) -> GraphDocument:
        """The graph of a study (of the core database or of an update) with its tags by name (an empty one for a study
        without)."""
        return await self._named(study)

    def _copy_fields(self, study: StudyFields, document: GraphDocument) -> None:
        """The columns of the fields derived from the graph, as the graph says."""
        for column, value in self.derived.columns(document).items():
            setattr(study, column, value)

    async def add_entries(self, study: Study, entries: Mapping[str, Sequence[Mapping[str, Mapping[str, Any]]]]) -> None:
        """Adds edges given as entries (see StoredGraph.from_entries, tags by name) to the graph of a study: their tags
        become tags of the study, an unknown name a new tag. A study without a graph gets one."""
        document = await self._named(study)
        self.stored.add_entries(document, entries)
        await self.store(study, {GRAPH_FIELD: self.stored.dump(document)})

    async def add_study_values(self, study: Study, relation: str, names: Sequence[str]) -> None:
        """Adds tags the study itself holds by the attribute relation (e.g. its countries), by name, to the graph of a
        study: they become tags of the study, an unknown name a new tag."""
        document = await self._named(study)
        self.stored.add_study_values(document, relation, names)
        await self.store(study, {GRAPH_FIELD: self.stored.dump(document)})

    async def _named(self, study: StudyFields) -> GraphDocument:
        """The graph of a study with its tags by name (an empty one for a study without)."""
        try:
            document = self.stored.loads(getattr(study, GRAPH_FIELD)) or GraphDocument()
        except GraphFormatError:
            document = GraphDocument()
        # Entries name their tags, the stored graph has their ids: named, the entities of both compare.
        names = await self._names({
            category: {node.value for node in document.nodes if self._category(node.kind) == category and isinstance(node.value, int)}
            for category in self.config.tag_categories()
        })
        for node in document.nodes:
            category = self._category(node.kind)
            if category is not None and isinstance(node.value, int):
                node.value = names[category].get(node.value, node.value)
        return document

    async def resolve(self, category: str, items: List[Item]) -> List[int]:
        """The ids of tags of a category given by id or name. A name is matched to an existing tag (ignoring
        case); an unknown one becomes a new tag."""
        if category not in TAG_CATEGORIES:
            raise ValueError(f"Unknown tag category '{category}'")
        ids: List[int] = []
        for item in items:
            if isinstance(item, str):
                found = (await self.db.execute(
                    select(Tag.id).where(Tag.category == category, func.lower(Tag.name) == item.lower())
                )).scalar_one_or_none()
                if found is None:
                    tag = Tag(category=category, name=item)
                    self.db.add(tag)
                    await self.db.flush()
                    found = tag.id
                item = found
            if item not in ids:
                ids.append(item)
        return ids

    async def _link(self, study_id: int, document: GraphDocument, before: GraphDocument) -> None:
        """Makes the tags of the nodes tags of the study, and those the graph had `before` and no longer has no tags of
        it any more (a tag the study has besides its graph stays)."""
        wanted = {node.value for node in document.nodes if self._category(node.kind) is not None}
        dropped = {node.value for node in before.nodes if self._category(node.kind) is not None and isinstance(node.value, int)} - wanted
        existing = set((await self.db.execute(select(StudyTag.tag_id).where(StudyTag.study_id == study_id))).scalars())
        self.db.add_all(StudyTag(study_id=study_id, tag_id=tag_id) for tag_id in sorted(wanted - existing))  # type: ignore[type-var]
        if dropped:
            await self.db.execute(delete(StudyTag).where(StudyTag.study_id == study_id, StudyTag.tag_id.in_(dropped)))

    async def get(self, studies: Sequence[StudyFields]) -> Dict[int, StudyGraph]:
        """The graphs of the studies (of the core database or of an update) by study, with their tags named. A study
        without a graph has an empty one."""
        parsed: Dict[int, Optional[GraphDocument]] = {}
        for study in studies:
            try:
                parsed[study.id] = self.stored.loads(getattr(study, GRAPH_FIELD))
            except GraphFormatError:
                parsed[study.id] = None
        names = await self._names({
            category: {
                node.value
                for document in parsed.values() if document
                for node in document.nodes
                if self._category(node.kind) == category and isinstance(node.value, int)
            }
            for category in self.config.tag_categories()
        })
        return {study.id: self._graph(study, parsed[study.id], names) for study in studies}

    def tag_names(self, study: UpdateStudy, category: str) -> List[str]:
        """The tags of a category a study of an update has, by name: those of its graph (see draft) that are given by
        name. Those given by id are named by StudyRepository.get_study_tags."""
        return list(dict.fromkeys(value for value in self._values(study, category) if isinstance(value, str)))

    def tag_ids(self, study: UpdateStudy, category: str) -> List[int]:
        """The tags of a category a study of an update names by the id of a tag that exists (see tag_names)."""
        return list(dict.fromkeys(value for value in self._values(study, category) if isinstance(value, int)))

    def _values(self, study: UpdateStudy, category: str) -> List[Any]:
        try:
            document = self.stored.loads(getattr(study, GRAPH_FIELD))
        except GraphFormatError:
            return []
        return [node.value for node in document.nodes if self._category(node.kind) == category] if document else []

    def _graph(self, study: StudyFields, document: Optional[GraphDocument], names: Mapping[str, Mapping[int, str]]) -> StudyGraph:
        if document is None or document.is_empty():
            return StudyGraph()
        nodes = []
        for node in document.nodes:
            category = self._category(node.kind)
            if category is None:
                nodes.append(StudyGraphNode(id=node.id, kind=node.kind, value=None if node.value is None else str(node.value)))
            elif isinstance(node.value, str):  # a tag of a study of an update that is no tag of the core database yet
                nodes.append(StudyGraphNode(id=node.id, kind=node.kind, value=node.value))
            elif node.value in names[category]:  # a tag that no longer exists is left out
                nodes.append(StudyGraphNode(id=node.id, kind=node.kind, value=names[category][node.value], tagId=str(node.value)))  # type: ignore[index]
        known = {node.id for node in nodes} | {self.config.root_id}
        edges = [
            StudyGraphEdge(relation=edge.relation, source=edge.source, target=edge.target)
            for edge in document.edges
            if edge.source in known and edge.target in known
        ]
        return StudyGraph(nodes=nodes, edges=edges)

    async def _names(self, wanted: Mapping[str, Iterable[int]]) -> Dict[str, Dict[int, str]]:
        names: Dict[str, Dict[int, str]] = {}
        for category, ids in wanted.items():
            names[category] = {}
            if ids:
                rows = (await self.db.execute(
                    select(Tag.id, Tag.name).where(Tag.category == category, Tag.id.in_(set(ids)))
                )).all()
                names[category] = dict(rows)
        return names
