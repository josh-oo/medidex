"""The views of a study (`views` of config/study.yaml): storing the groups of a stored view when a study is created,
and reading the views of studies with their tags named."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping, Optional

from sqlmodel import func, select

from ...utils.dto import StudyView, Tag, ViewPart
from ...utils.studyconfig import STUDY_CONFIG, StudyViewConfig
from ...utils.views import StoredGroup, StoredPart, StoredView
from ..models import Study
from ..tagstorage import TAG_TABLES

if TYPE_CHECKING:
    from .study import StudyRepository


class StudyViews:
    def __init__(self, repo: StudyRepository):
        self.repo = repo
        self.db = repo.db

    async def store(self, study: Study, values: Mapping[str, Any]) -> None:
        """Stores the stored views of a new study from the payload `values`: the tags of every part, given by
        name or id, become ids of the tags of their category (an unknown name becomes a new tag) and are tags
        of the study. A plain text (no structure) is kept as it is."""
        for key, view in STUDY_CONFIG.stored_views.items():
            stored = StoredView(view)
            groups = stored.parse(values.get(key))
            if groups is None:
                setattr(study, view.column, values.get(key))  # type: ignore[arg-type]
                continue
            resolved: List[StoredGroup] = []
            for group in groups:
                resolved.append({
                    part: StoredPart(await self._resolve(view.parts[part].category, content.tags), content.values)  # type: ignore[arg-type]
                    for part, content in group.items()
                })
            setattr(study, view.column, stored.dumps(resolved))  # type: ignore[arg-type]
            await self._link(study.id, view, resolved)
        await self.db.flush()

    async def _resolve(self, category: str, items: List) -> List[int]:
        """The ids of tags of a category given by id or name. A name is matched to an existing tag (ignoring
        case); an unknown one becomes a new tag."""
        if category not in TAG_TABLES:
            raise ValueError(f"The tags of '{category}' are kept in the study and cannot be part of a stored view")
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

    async def _link(self, study_id: int, view: StudyViewConfig, groups: List[StoredGroup]) -> None:
        """Makes the tags of the groups tags of the study."""
        for category in {part.category for part in view.parts.values()}:
            storage = TAG_TABLES[category]  # type: ignore[index]
            wanted = {item for group in groups for key, part in group.items() if view.parts[key].category == category for item in part.tags}
            existing = set((await self.db.execute(select(storage.link_tag).where(storage.link_study == study_id))).scalars())
            self.db.add_all(
                storage.link(**{storage.link_study.key: study_id, storage.link_tag.key: tag_id}) for tag_id in sorted(wanted - existing)
            )

    async def get(self, studies: List[Study]) -> Dict[int, Dict[str, StudyView]]:
        """The views of the studies by study, each with its tags named. A view a study has nothing in is left out."""
        result: Dict[int, Dict[str, StudyView]] = {study.id: {} for study in studies}
        for key, view in STUDY_CONFIG.views.items():
            views = await (self._stored(view, studies) if view.column else self._derived(view, studies))
            for study_id, content in views.items():
                if content.groups or content.text:
                    result[study_id][key] = content
        return result

    async def _stored(self, view: StudyViewConfig, studies: List[Study]) -> Dict[int, StudyView]:
        stored = StoredView(view)
        parsed = {study.id: stored.parse(getattr(study, view.column)) for study in studies}  # type: ignore[arg-type]
        names = await self._names(
            {
                category: {item for groups in parsed.values() for group in groups or [] for key, part in group.items()
                           if view.parts[key].category == category for item in part.tags if isinstance(item, int)}
                for category in {part.category for part in view.parts.values()}
            }
        )
        views: Dict[int, StudyView] = {}
        for study in studies:
            groups = parsed[study.id]
            text = getattr(study, view.column)  # type: ignore[arg-type]
            if groups is None:
                views[study.id] = StudyView(text=text.strip() if text and text.strip() else None)
                continue
            views[study.id] = StudyView(groups=[
                {
                    key: ViewPart(
                        tags=[Tag(id=str(item), keyword=names[view.parts[key].category][item]) for item in part.tags if item in names[view.parts[key].category]],  # type: ignore[index]
                        values=part.values,
                    )
                    for key, part in group.items()
                }
                for group in groups
            ])
        return views

    async def _names(self, wanted: Mapping[str, Iterable[int]]) -> Dict[str, Dict[int, str]]:
        names: Dict[str, Dict[int, str]] = {}
        for category, ids in wanted.items():
            names[category] = {}
            if ids:
                tag = TAG_TABLES[category].tag
                rows = (await self.db.execute(select(tag.id, tag.description).where(tag.id.in_(set(ids))))).all()
                names[category] = {tag_id: description or "" for tag_id, description in rows}
        return names

    async def _derived(self, view: StudyViewConfig, studies: List[Study]) -> Dict[int, StudyView]:
        ids = [study.id for study in studies]
        tags: Dict[str, Dict[int, List[Tag]]] = {
            category: await self.repo.get_study_tags(category, ids)  # type: ignore[arg-type]
            for category in {part.category for part in view.parts.values() if part.category}
        }
        views: Dict[int, StudyView] = {}
        for study in studies:
            group: Dict[str, ViewPart] = {}
            for key, part in view.parts.items():
                if part.category:
                    group[key] = ViewPart(tags=tags[part.category].get(study.id, []))
                else:
                    value = getattr(study, STUDY_CONFIG.fields[part.field].column)  # type: ignore[index]
                    group[key] = ViewPart(values={part.field: str(value)} if value not in (None, "") else {})  # type: ignore[dict-item]
            views[study.id] = StudyView(groups=[group] if any(item.tags or item.values for item in group.values()) else [])
        return views
