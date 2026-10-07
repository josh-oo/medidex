"""The graph of a study (`graph` of config/study.yaml): storing it when a study is created, and reading the graphs of
studies with their tags named."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from sqlmodel import func, select

from ...utils.dto import StudyGraph, StudyGraphEdge, StudyGraphNode
from ...utils.graph import GraphDocument, GraphFormatError, Item, StoredGraph
from ...utils.studyconfig import GRAPH_FIELD, STUDY_CONFIG
from ..models import Study
from ..tagstorage import TAG_TABLES


class StudyGraphs:
    def __init__(self, db):
        self.db = db
        self.config = STUDY_CONFIG.graph
        self.stored = StoredGraph(self.config)

    def _category(self, kind: str) -> Optional[str]:
        value = self.config.entities[kind].value
        return value.category if value else None

    async def store(self, study: Study, values: Mapping[str, Any]) -> None:
        """Stores the graph of a new study from the payload `values`: the tags of its nodes, given by name or id, become
        ids of the tags of their category (an unknown name becomes a new tag) and are tags of the study. Raises
        GraphFormatError if the graph is no graph of config/study.yaml."""
        document = self.stored.loads(values.get(GRAPH_FIELD))
        if document is None:
            setattr(study, GRAPH_FIELD, None)
            return
        for node in document.nodes:
            category = self._category(node.kind)
            if category is not None:
                node.value = (await self._resolve(category, [node.value]))[0]  # type: ignore[list-item]
        setattr(study, GRAPH_FIELD, self.stored.dump(document))
        await self._link(study.id, document)
        await self.db.flush()

    async def _resolve(self, category: str, items: List[Item]) -> List[int]:
        """The ids of tags of a category given by id or name. A name is matched to an existing tag (ignoring
        case); an unknown one becomes a new tag."""
        if category not in TAG_TABLES:
            raise ValueError(f"The tags of '{category}' are kept in the study and cannot be the value of an entity")
        tag = TAG_TABLES[category].tag
        ids: List[int] = []
        for item in items:
            if isinstance(item, str):
                found = (await self.db.execute(select(tag.id).where(func.lower(tag.description) == item.lower()).limit(1))).scalar_one_or_none()
                if found is None:
                    found = ((await self.db.execute(select(func.max(tag.id)))).scalar_one_or_none() or 0) + 1
                    self.db.add(tag(id=found, description=item))
                    await self.db.flush()
                item = found
            if item not in ids:
                ids.append(item)
        return ids

    async def _link(self, study_id: int, document: GraphDocument) -> None:
        """Makes the tags of the nodes tags of the study."""
        for category in self.config.tag_categories():
            storage = TAG_TABLES[category]
            wanted = {node.value for node in document.nodes if self._category(node.kind) == category}
            existing = set((await self.db.execute(select(storage.link_tag).where(storage.link_study == study_id))).scalars())
            self.db.add_all(
                storage.link(**{storage.link_study.key: study_id, storage.link_tag.key: tag_id}) for tag_id in sorted(wanted - existing)  # type: ignore[type-var]
            )

    async def get(self, studies: List[Study]) -> Dict[int, StudyGraph]:
        """The graphs of the studies by study, with their tags named. A study without a graph has an empty one (or the
        plain text it holds instead)."""
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

    def _graph(self, study: Study, document: Optional[GraphDocument], names: Mapping[str, Mapping[int, str]]) -> StudyGraph:
        if document is None or document.is_empty():
            return StudyGraph(text=self._text(study))
        nodes = []
        for node in document.nodes:
            category = self._category(node.kind)
            if category is None:
                nodes.append(StudyGraphNode(id=node.id, kind=node.kind, value=None if node.value is None else str(node.value)))
            elif node.value in names[category]:  # a tag that no longer exists is left out
                nodes.append(StudyGraphNode(id=node.id, kind=node.kind, value=names[category][node.value], tagId=str(node.value)))  # type: ignore[index]
        known = {node.id for node in nodes} | {self.config.root_id}
        edges = [
            StudyGraphEdge(relation=edge.relation, source=edge.source, target=edge.target)
            for edge in document.edges
            if edge.source in known and edge.target in known
        ]
        return StudyGraph(nodes=nodes, edges=edges)

    def _text(self, study: Study) -> Optional[str]:
        """The plain text of an older study; the structured JSON older versions kept there is no text."""
        column = self.config.text_column
        text = getattr(study, column) if column else None
        if not text or not text.strip() or text.strip().startswith(("[", "{")):
            return None
        return text.strip()

    async def _names(self, wanted: Mapping[str, Iterable[int]]) -> Dict[str, Dict[int, str]]:
        names: Dict[str, Dict[int, str]] = {}
        for category, ids in wanted.items():
            names[category] = {}
            if ids:
                tag = TAG_TABLES[category].tag
                rows = (await self.db.execute(select(tag.id, tag.description).where(tag.id.in_(set(ids))))).all()
                names[category] = {tag_id: description or "" for tag_id, description in rows}
        return names
