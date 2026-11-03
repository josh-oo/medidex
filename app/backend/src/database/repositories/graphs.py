"""The graph of a study (the study ontology, config/medidex-study.yaml): storing it when a study is created, adding edges
to it, and reading the graphs of studies with their tags named."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from sqlmodel import func, select

from ...utils.dto import StudyGraph, StudyGraphEdge, StudyGraphNode
from ...utils.graph import GraphDocument, GraphFormatError, Item, StoredGraph
from ...utils.studyconfig import GRAPH_FIELD, STUDY_CONFIG
from ..models import Study, StudyFields, StudyTag, Tag, UpdateStudy
from ...utils.tagconfig import TAG_CATEGORIES


class StudyGraphs:
    def __init__(self, db):
        self.db = db
        self.config = STUDY_CONFIG.graph
        self.stored = StoredGraph(self.config)

    def _category(self, kind: str) -> Optional[str]:
        value = self.config.entities[kind].value
        return value.category if value else None

    def draft(self, study: UpdateStudy, values: Mapping[str, Any]) -> None:
        """Stores the graph of a new study of an update from the payload `values` as it is: its tags stay names (or ids
        of tags that exist) and only become tags of the core database when the study is merged (see store). Raises
        GraphFormatError if the graph is no graph of config/medidex-study.yaml."""
        document = self.stored.loads(values.get(GRAPH_FIELD))
        setattr(study, GRAPH_FIELD, self.stored.dump(document) if document is not None else None)

    async def store(self, study: Study, values: Mapping[str, Any]) -> None:
        """Stores the graph of a study of the core database from the payload `values` (or the graph of the study of an
        update it is merged from): the tags of its nodes, given by name or id, become ids of the tags of their category
        (an unknown name becomes a new tag) and are tags of the study. Raises GraphFormatError if the graph is no graph
        of config/medidex-study.yaml."""
        document = self.stored.loads(values.get(GRAPH_FIELD))
        if document is None:
            setattr(study, GRAPH_FIELD, None)
            return
        for node in document.nodes:
            category = self._category(node.kind)
            if category is not None:
                node.value = (await self.resolve(category, [node.value]))[0]  # type: ignore[list-item]
        setattr(study, GRAPH_FIELD, self.stored.dump(document))
        await self._link(study.id, document)
        await self.db.flush()

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

    async def _named(self, study: Study) -> GraphDocument:
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
                    select(Tag.id).where(Tag.category == category, func.lower(Tag.description) == item.lower())
                )).scalar_one_or_none()
                if found is None:
                    tag = Tag(category=category, description=item)
                    self.db.add(tag)
                    await self.db.flush()
                    found = tag.id
                item = found
            if item not in ids:
                ids.append(item)
        return ids

    async def _link(self, study_id: int, document: GraphDocument) -> None:
        """Makes the tags of the nodes tags of the study."""
        wanted = {node.value for node in document.nodes if self._category(node.kind) is not None}
        existing = set((await self.db.execute(select(StudyTag.tag_id).where(StudyTag.study_id == study_id))).scalars())
        self.db.add_all(StudyTag(study_id=study_id, tag_id=tag_id) for tag_id in sorted(wanted - existing))  # type: ignore[type-var]

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
                    select(Tag.id, Tag.description).where(Tag.category == category, Tag.id.in_(set(ids)))
                )).all()
                names[category] = dict(rows)
        return names
