import os
import re
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, exists, or_, true
from sqlalchemy import Table
from sqlmodel import SQLModel, delete, select, func, text, update

from dotenv import load_dotenv

from datetime import datetime
from typing import Any, List, Mapping, Optional, Dict, Sequence, Tuple

from ..models import Report, Study, StudyDatabase, StudyFields, Link, StudyTag, Tag as DbTag, UpdateLink, UpdateReport, UpdateStudy
from .graphs import StudyGraphs

from ...utils.postprocessing import normalize_author_names
from ...utils.dto import DatabaseTag, StudyGraph, Tag, study_columns
from ...utils.graph import GraphDocument
from ...utils.studyconfig import GRAPH_FIELD, STUDY_CONFIG
from ...utils.tagconfig import TAG_CATEGORIES
from ...utils.query_parser import AdvancedSearchField, AndGroup, Comparison, OrGroup, QueryNode

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")

class DuplicateShortNameError(ValueError):
    pass

def load_trial_id_mapping():
    file_path = os.path.join(DATABASE_VOLUME,"resources", "trial_id_mapping.json")
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as json_file:
        return json.load(json_file)

trial_id_mapping = load_trial_id_mapping()

# The tag category of each advanced-search field of a tag category (its `search_field`). Keyed by the
# AdvancedSearchField enum (not a raw string) - field-name validity, including
# alias/plural normalization, is already enforced by Comparison's own pydantic
# validation (src/utils/query_parser.py) before a Comparison ever reaches here, so
# there's no "unknown field" case left to check or raise for at this layer.
_TAG_FIELDS = {AdvancedSearchField(TAG_CATEGORIES[name].search_field): name for name in TAG_CATEGORIES}
# What a tag of a study is shown with (StudyRepository._tag).
_TAG_COLUMNS = (DbTag.id, DbTag.name, DbTag.acronym, DbTag.labels)

def _authors_text(model):
    """The authors of the reports (of `model`, Report or UpdateReport) as one text, to match a part of a name in."""
    return func.array_to_string(model.authors, " ")

def _tag_matches(pattern: str):
    """A tag whose name or acronym matches the pattern ("CBT" finds Cognitive Behavior Therapy)."""
    return or_(DbTag.name.ilike(pattern), DbTag.acronym.ilike(pattern))

def _tag_exists(category: str, pattern: str):
    return (
        select(1)
        .where(StudyTag.study_id == Study.id, StudyTag.tag_id == DbTag.id, DbTag.category == category, _tag_matches(pattern))
        .exists()
    )

def _comparison_to_condition(comparison: Comparison):
    field = comparison.field
    pattern = f"%{comparison.value}%"

    if field in _TAG_FIELDS:
        return _tag_exists(_TAG_FIELDS[field], pattern)

    if field == AdvancedSearchField.AUTHOR:
        return (
            select(1)
            .where(Link.study_id == Study.id, Link.report_id == Report.id, _authors_text(Report).ilike(pattern))
            .exists()
        )

    if field == AdvancedSearchField.NAME:
        return Study.short_name.ilike(pattern)

    if field == AdvancedSearchField.TRIAL_ID:
        return or_(
            Study.trial_registration_id.ilike(pattern),
            select(1).where(Link.study_id == Study.id, Link.report_id == Report.id, Report.trial_registration_id.ilike(pattern)).exists(),
        )

    if field == AdvancedSearchField.STATUS:
        return Study.status.ilike(pattern)

    # Unreachable: AdvancedSearchField is a closed enum and every member is handled
    # above - this only trips if a new enum member is added without a case here.
    raise AssertionError(f"No SQL mapping for advanced-search field {field!r}")

def _query_node_to_condition(node: QueryNode):
    if isinstance(node, AndGroup):
        return and_(*[_query_node_to_condition(operand) for operand in node.operands])
    if isinstance(node, OrGroup):
        return or_(*[_query_node_to_condition(operand) for operand in node.operands])
    return _comparison_to_condition(node)

class StudyRepository:
    def __init__(self, db : AsyncSession, user_id : str):
        self.db = db
        self.user_id = str(user_id)
        self.graphs = StudyGraphs(db)

    def _visible_drafts(self):
        """The studies of the updates this scope may see: those it created itself, besides every
        study of the core database. Studies another scope created stay invisible until a report linked to them is
        merged, so that users, MediBot and other clients work without interfering. The owner of a study database reviews
        its updates and sees every study of them."""
        owned = select(StudyDatabase.id).where(StudyDatabase.owner == self.user_id)
        return or_(UpdateStudy.created_by == self.user_id, UpdateStudy.database_id.in_(owned))

    @staticmethod
    def _in_databases(model, databases: Optional[Sequence[int]]):
        """The studies (of `model`, Study or UpdateStudy) of the given study databases; no databases means all of
        them."""
        return model.database_id.in_(list(databases)) if databases else true()

    async def _drafts(self, study_ids: Optional[Sequence[int]] = None, databases: Optional[Sequence[int]] = None) -> List[UpdateStudy]:
        """The studies of the updates this scope sees (see _visible_drafts), of the given ids (all without)."""
        stmt = select(UpdateStudy).where(self._visible_drafts()).where(self._in_databases(UpdateStudy, databases))
        if study_ids:
            stmt = stmt.where(UpdateStudy.id.in_(list(study_ids)))
        return list((await self.db.execute(stmt.order_by(UpdateStudy.id))).scalars().all())

    async def commit(self):
        await self.db.commit()

    async def rollback(self):
        await self.db.rollback()

    async def add_study(self, values: Mapping[str, Any], project_id: str, database_id: int) -> UpdateStudy:
        """Adds a study to the update `project_id` of a study database from its fields (see StudyFields in utils/dto.py):
        the primitive fields and the graph, whose tags stay names until the study is merged (see promote). It is the study of this scope until then (see _visible_drafts). Raises
        GraphFormatError if the graph is no graph of config/medidex-study.yaml, DuplicateShortNameError if the database
        or one of its updates has a study of that name."""
        columns = self._columns(values)
        taken = exists().where(Study.database_id == database_id, Study.short_name == columns["short_name"])
        if (await self.db.execute(select(taken))).scalar():
            raise DuplicateShortNameError("short_name already exists")
        new_study = UpdateStudy(**columns, database_id=database_id, project_id=project_id, created_by=self.user_id)
        self.graphs.draft(new_study, values)
        self.db.add(new_study)
        try:
            await self.db.flush()
        except IntegrityError as e:
            self._raise_duplicate(e, "uq_update_study_short_name")
        await self.db.refresh(new_study)
        return new_study

    async def promote(self, study_id: int) -> Optional[Study]:
        """Makes the study of an update a study of the core database of the same id (when a report linked to it is
        merged, see UpdateMergeService): its tags become tags of the core database (see StudyGraphs.store), and what of
        the update refers to it (its links, and the rows of every table that refers to a study by the pair `study_id`
        and `update_study_id`, e.g. proposals of extensions) refers to that study. None if it is no study of an update. Raises DuplicateShortNameError if
        the database got a study of its name in the meantime."""
        draft = await self.db.get(UpdateStudy, study_id)
        if draft is None:
            return None
        columns = {name: getattr(draft, name) for name in StudyFields.model_fields if name != GRAPH_FIELD}
        study = Study(id=draft.id, **columns)
        self.db.add(study)
        try:
            await self.db.flush()
        except IntegrityError as e:
            self._raise_duplicate(e, "uq_study_short_name")
        await self.graphs.store(study, {GRAPH_FIELD: getattr(draft, GRAPH_FIELD)})
        for table in self._study_referencing_tables():
            await self.db.execute(
                update(table).where(table.c.update_study_id == study_id).values(study_id=study_id, update_study_id=None)
            )
        await self.db.execute(delete(UpdateStudy).where(UpdateStudy.id == study_id))
        await self.db.flush()
        return study

    @staticmethod
    def _study_referencing_tables() -> List[Table]:
        """The tables that refer to a study of the core database or of an update by the pair `study_id` -> study and
        `update_study_id` -> update_study (one of them set, like UpdateLink)."""
        def references(table: Table, column: str, target: str) -> bool:
            return column in table.c and any(key.column.table.name == target for key in table.c[column].foreign_keys)
        return [
            table for table in SQLModel.metadata.sorted_tables
            if references(table, "study_id", Study.__tablename__) and references(table, "update_study_id", UpdateStudy.__tablename__)
        ]

    async def import_study(self, values: Mapping[str, Any], tags: Mapping[str, List[str]], database_id: int, created_at: Optional[datetime] = None) -> Study:
        """Adds a study of an imported database to the core database from its fields (see add_study) and its tags by
        category (e.g. interventions), by name; an unknown name becomes a new tag (see StudyGraphs.resolve). It is
        entered when the database it comes from says (now without). The tags of a category the study holds in its graph
        itself (its countries, see GraphConfig.study_relation) are added to its graph before it is stored, so that the
        graph is stored and checked once."""
        relations = {category: STUDY_CONFIG.graph.study_relation(category) for category in tags}
        held = {category: names for category, names in tags.items() if relations[category] is not None}
        if held:
            document = self.graphs.stored.loads(values.get(GRAPH_FIELD)) or GraphDocument()
            for category, names in held.items():
                self.graphs.stored.add_study_values(document, relations[category], names)  # type: ignore[arg-type]
            values = {**values, GRAPH_FIELD: self.graphs.stored.dumps(document)}
        new_study = await self._insert(values, database_id, created_at)
        others = {category: names for category, names in tags.items() if category not in held and names}
        if others:
            existing = set((await self.db.execute(select(StudyTag.tag_id).where(StudyTag.study_id == new_study.id))).scalars())
            for category, names in others.items():
                for tag_id in await self.graphs.resolve(category, names):
                    if tag_id not in existing:
                        self.db.add(StudyTag(study_id=new_study.id, tag_id=tag_id))
                        existing.add(tag_id)
        return new_study

    async def _insert(self, values: Mapping[str, Any], database_id: int, created_at: Optional[datetime] = None) -> Study:
        new_study = Study(**self._columns(values), database_id=database_id)
        if created_at:
            new_study.created_at = created_at
        self.db.add(new_study)
        try:
            await self.db.flush()
        except IntegrityError as e:
            self._raise_duplicate(e, "uq_study_short_name")
        await self.graphs.store(new_study, values)
        return new_study

    @staticmethod
    def _columns(values: Mapping[str, Any]) -> Dict[str, Any]:
        """The columns of a study from its fields (see add_study), but the graph and the fields derived from it, which the
        graph holds (see StudyGraphs.document)."""
        return study_columns({key: values.get(key) for key, field in STUDY_CONFIG.fields.items() if not field.derive})

    @staticmethod
    def _raise_duplicate(error: IntegrityError, constraint: str) -> None:
        """Raises DuplicateShortNameError if `error` broke the unique short names `constraint`, else `error`."""
        names = {getattr(getattr(cause, "diag", None), "constraint_name", None) for cause in (error.orig, getattr(error.orig, "__cause__", None))}
        if constraint in names:
            raise DuplicateShortNameError("short_name already exists") from error
        raise error

    async def import_tags(self, tags: Sequence[DatabaseTag]) -> None:
        """Adds the vocabulary of an imported database. A tag of the same name in its category (ignoring case) is the same
        tag: it gets the labels, synonyms and source names listed for it besides its own, and the acronym and parent if it
        has none. A parent that is no tag yet becomes one. The studies imported next find their tags in it without a
        query each (see StudyGraphs.remember_tags)."""
        if tags:
            await self._merge_tags(tags)
        await self.graphs.remember_tags()

    async def _merge_tags(self, tags: Sequence[DatabaseTag]) -> None:
        rows = (await self.db.execute(select(DbTag).where(DbTag.category.in_({tag.category for tag in tags})))).scalars().all()
        known = {(row.category, row.name.lower()): row for row in rows}

        def row_of(category: str, name: str) -> DbTag:
            if (category, name.lower()) not in known:
                known[(category, name.lower())] = DbTag(category=category, name=name)
                self.db.add(known[(category, name.lower())])
            return known[(category, name.lower())]

        for tag in tags:
            row = row_of(tag.category, tag.name)
            row.acronym = row.acronym or tag.acronym
            row.synonyms = list(dict.fromkeys([*row.synonyms, *tag.synonyms]))
            row.labels = list(dict.fromkeys([*row.labels, *tag.labels]))
            row.source_names = list(dict.fromkeys([*row.source_names, *tag.sourceNames]))
        parents = [(row_of(tag.category, tag.name), row_of(tag.category, tag.parent)) for tag in tags if tag.parent]
        await self.db.flush()
        for row, parent in parents:
            if row.parent_id is None and parent is not row:
                row.parent_id = parent.id
        await self.db.flush()

    async def get_tag_vocabulary(self, study_ids: List[int]) -> List[DatabaseTag]:
        """The tags of the studies and their parents, as an export lists them (see import_tags)."""
        if not study_ids:
            return []
        used = select(StudyTag.tag_id).where(StudyTag.study_id.in_(study_ids))
        found = {row.id: row for row in (await self.db.execute(select(DbTag).where(DbTag.id.in_(used)))).scalars()}
        missing = {row.parent_id for row in found.values() if row.parent_id is not None} - set(found)
        while missing:
            found.update({row.id: row for row in (await self.db.execute(select(DbTag).where(DbTag.id.in_(missing)))).scalars()})
            missing = {row.parent_id for row in found.values() if row.parent_id is not None} - set(found)
        return [
            DatabaseTag(
                category=row.category, name=row.name, acronym=row.acronym, synonyms=row.synonyms, labels=row.labels,
                parent=found[row.parent_id].name if row.parent_id in found else None, sourceNames=row.source_names,
            )
            for row in sorted(found.values(), key=lambda row: row.id)  # type: ignore[arg-type, return-value]
        ]

    async def update_study_fields(self, study_id: int, values: Mapping[str, Any]) -> None:
        """Sets primitive fields of a study (keys of STUDY_CONFIG.fields, valued as StudyFields has them); a field derived
        from the graph is written into the graph."""
        study = await self.db.get(Study, study_id)
        if study is None:
            raise ValueError(f"Study {study_id} not found")
        for column, value in self._columns(values).items():
            setattr(study, column, value)
        derived = {key: value for key, value in values.items() if STUDY_CONFIG.fields[key].derive}
        if derived:
            await self.graphs.store(study, {GRAPH_FIELD: self.graphs.stored.dump(await self.graphs.named(study)), **derived})
        await self.db.flush()

    async def get_study_graph(self, study_id: int) -> Optional[Any]:
        """The graph of a visible study (of the core database or of an update) with its tags by name, None for no such
        study."""
        study = await self._study_row(study_id)
        return None if study is None else await self.graphs.named(study)

    async def set_study_graph(self, study_id: int, document: Any) -> None:
        """Replaces the graph of a study (of the core database or of an update) with `document`, its tags by name (see
        StudyGraphs.store and draft). Raises GraphFormatError if it breaks the study ontology."""
        study = await self._study_row(study_id)
        if study is None:
            raise ValueError(f"Study {study_id} not found")
        payload = {GRAPH_FIELD: self.graphs.stored.dump(document)}
        if isinstance(study, Study):
            await self.graphs.store(study, payload)
        else:
            self.graphs.draft(study, payload)
        await self.db.flush()

    async def _study_row(self, study_id: int) -> Optional[StudyFields]:
        """The row of a study of the core database, or of an update visible to this scope."""
        study = await self.db.get(Study, study_id)
        if study is not None:
            return study
        drafts = await self._drafts([study_id])
        return drafts[0] if drafts else None

    async def add_study_graph_entries(self, study_id: int, entries: Mapping[str, Sequence[Mapping[str, Mapping[str, Any]]]]) -> None:
        """Adds edges, given as entries with their tags by name (see StoredGraph.from_entries), to the graph of a study."""
        study = await self.db.get(Study, study_id)
        if study is None:
            raise ValueError(f"Study {study_id} not found")
        await self.graphs.add_entries(study, entries)

    async def get_database_studies(self, database_id: int) -> List[Study]:
        """The studies of the core database of a study database, by name."""
        stmt = select(Study).where(Study.database_id == database_id).order_by(Study.short_name, Study.id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_graphs(self, studies: Sequence[StudyFields]) -> Dict[int, StudyGraph]:
        """The graphs (config/medidex-study.yaml) of the studies, by study, with their tags named."""
        return await self.graphs.get(studies)

    async def search_studies(self, query: str, limit: int, offset: int, databases: Optional[Sequence[int]] = None) -> Tuple[List[Study], bool]:
        """Free-text search of the core database across a study's own name/trial ID
        plus its reports' authors/trial ID and the tags of the categories with free_text_search
        (config/medidex-study.yaml), in the given study databases (all without). Returns (page, has_more) - one extra
        id beyond the page is fetched so has_more can be determined without a separate count query, same convention
        as StudySimilaritySearchService.get_similar_studies_by_id.
        """
        pattern = f"%{query}%"
        id_stmt = (
            select(Study.id, Study.short_name)
            .outerjoin(Link, Link.study_id == Study.id)
            .outerjoin(Report, Report.id == Link.report_id)
        )
        matches = [
            Study.short_name.ilike(pattern),
            Study.trial_registration_id.ilike(pattern),
            _authors_text(Report).ilike(pattern),
            Report.trial_registration_id.ilike(pattern),
        ]
        searched = list(TAG_CATEGORIES.where(free_text_search=True))
        if searched:
            id_stmt = (
                id_stmt
                .outerjoin(StudyTag, StudyTag.study_id == Study.id)
                .outerjoin(DbTag, and_(DbTag.id == StudyTag.tag_id, DbTag.category.in_(searched)))
            )
            matches.append(_tag_matches(pattern))
        id_stmt = (
            id_stmt
            .where(or_(*matches))
            .where(self._in_databases(Study, databases))
            .distinct()
            .order_by(Study.short_name, Study.id)
            .offset(offset)
            .limit(limit + 1)
        )
        rows = (await self.db.execute(id_stmt)).all()

        has_more = len(rows) > limit
        study_ids = [study_id for study_id, _short_name in rows[:limit]]
        if not study_ids:
            return [], has_more

        studies_by_id = {study.id: study for study in await self._core_studies(study_ids)}
        page = [studies_by_id[study_id] for study_id in study_ids if study_id in studies_by_id]
        return page, has_more

    async def search_studies_advanced(self, query: QueryNode, limit: int, offset: int, databases: Optional[Sequence[int]] = None) -> Tuple[List[Study], bool]:
        """Boolean AND/OR search of the core database (see search_studies) by field==value comparisons (see
        src/utils/query_parser.py for the grammar and QueryNode shape). Supported fields:
        name/shortName, trialId, author, status and the search field of each tag category
        (config/medidex-study.yaml) - each translated into an ilike match,
        an EXISTS against its join table for the many-to-many aspect fields. Same
        two-phase id-then-hydrate paging convention as search_studies() above.
        """
        condition = _query_node_to_condition(query)
        id_stmt = (
            select(Study.id, Study.short_name)
            .where(condition)
            .where(self._in_databases(Study, databases))
            .distinct()
            .order_by(Study.short_name, Study.id)
            .offset(offset)
            .limit(limit + 1)
        )
        rows = (await self.db.execute(id_stmt)).all()

        has_more = len(rows) > limit
        study_ids = [study_id for study_id, _short_name in rows[:limit]]
        if not study_ids:
            return [], has_more

        studies_by_id = {study.id: study for study in await self._core_studies(study_ids)}
        page = [studies_by_id[study_id] for study_id in study_ids if study_id in studies_by_id]
        return page, has_more

    async def get_studies(self, study_ids: Optional[List[int]] = None, databases: Optional[Sequence[int]] = None) -> List[StudyFields]:
        """The studies of the core database and those of the updates this scope sees (see _visible_drafts), of the
        given ids (all without), in the given study databases (all without)."""
        return [*await self._core_studies(study_ids, databases), *await self._drafts(study_ids, databases)]

    async def _core_studies(self, study_ids: Optional[Sequence[int]] = None, databases: Optional[Sequence[int]] = None) -> List[Study]:
        stmt = select(Study).where(self._in_databases(Study, databases))
        if study_ids:
            stmt = stmt.where(Study.id.in_(list(study_ids)))
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_studies_by_report_dois(self, dois: List[str], databases: Optional[Sequence[int]] = None) -> List[StudyFields]:
        """Studies linked to any report whose DOI is in `dois` (normalized: lowercase, no
        resolver prefix - see crawler.normalize_doi). Report DOIs are stored as uploaded,
        so the bare and https://doi.org/-prefixed spellings are both matched. Link scoping
        mirrors ReportRepository.get_linked_studies: the links of the core database and those
        this scope made in an update, not other scopes' links.
        """
        study_ids = sorted({study_id for ids in (await self.get_study_ids_by_report_dois(dois)).values() for study_id in ids})
        return sorted(await self.get_studies(study_ids, databases), key=lambda study: study.id) if study_ids else []

    async def get_study_ids_by_report_dois(self, dois: List[str]) -> Dict[str, List[int]]:
        """The ids of the studies linked to a report of each DOI (normalized, see get_studies_by_report_dois), by DOI;
        DOIs of no linked report are left out. Visibility and databases are left to get_studies."""
        if not dois:
            return {}

        spellings = set(dois) | {f"https://doi.org/{doi}" for doi in dois}
        doi = func.regexp_replace(func.lower(Report.doi), "^https://doi.org/", "")
        update_doi = func.regexp_replace(func.lower(UpdateReport.doi), "^https://doi.org/", "")
        rows = [*(await self.db.execute(
            select(doi, Link.study_id)
            .join(Report, Report.id == Link.report_id)
            .where(func.lower(Report.doi).in_(spellings))
        )).all(), *(await self.db.execute(
            select(update_doi, func.coalesce(UpdateLink.study_id, UpdateLink.update_study_id))
            .join(UpdateReport, UpdateReport.id == UpdateLink.report_id)
            .where(func.lower(UpdateReport.doi).in_(spellings))
            .where(UpdateLink.created_by == self.user_id)
        )).all()]
        by_doi: Dict[str, List[int]] = {}
        for found, study_id in rows:
            if study_id not in by_doi.setdefault(found, []):
                by_doi[found].append(study_id)
        return by_doi

    async def get_study_ids_by_trial_ids(self, trial_ids: List[str], databases: Optional[Sequence[int]] = None) -> Dict[str, List[int]]:
        """The ids of the studies of each trial registration id, by the id compared without case and separators
        ("CTRI/2025/04/083875" is "CTRI202504083875"); ids of no study are left out. Studies of the updates count
        for the scope that sees them (see _visible_drafts)."""
        wanted = {re.sub(r"[^A-Z0-9]", "", trial_id.upper()) for trial_id in trial_ids if trial_id}
        if not wanted:
            return {}

        by_id: Dict[str, List[int]] = {}
        for model, visible in ((Study, true()), (UpdateStudy, self._visible_drafts())):
            key = func.regexp_replace(func.upper(model.trial_registration_id), "[^A-Z0-9]", "", "g")
            rows = (await self.db.execute(
                select(key, model.id).where(key.in_(wanted)).where(visible).where(self._in_databases(model, databases))
            )).all()
            for found, study_id in rows:
                by_id.setdefault(found, []).append(study_id)
        return by_id

    async def get_study_by_id(self, study_id: int, databases: Optional[Sequence[int]] = None) -> Optional[StudyFields]:
        """The study of the core database or of an update of the id; None if there is no such study, it is not visible
        to this scope or not in the given study databases."""
        studies = await self.get_studies([study_id], databases)
        return studies[0] if studies else None

    async def is_draft(self, study_id: int) -> bool:
        """Whether the study is one of an update (UpdateStudy), not yet of the core database."""
        return await self.db.get(UpdateStudy, study_id) is not None

    async def search_study_by_shortname(self, shortname: str, cutoff: Optional[datetime] = None) -> Optional[StudyFields]:
        for model, visible in ((Study, true()), (UpdateStudy, self._visible_drafts())):
            stmt = select(model).where(model.short_name.ilike(f"%{shortname}%")).where(visible)
            if cutoff:
                stmt = stmt.where(model.created_at < cutoff)
            result = (await self.db.execute(stmt)).scalar_one_or_none()
            if result is not None:
                return result
        return None

    async def get_study_reports_by_study_ids(self, study_ids: Optional[List[int]], cutoff: Optional[datetime] = None) -> Dict[int, List[Report]]:
        stmt = (
            select(Link.study_id, Report)
            .join(Report, Report.id == Link.report_id)
        )

        if study_ids:
            stmt = stmt.where(Link.study_id.in_(study_ids))

        if cutoff:
            stmt = stmt.where(Report.created_at < cutoff)

        rows = (await self.db.execute(stmt)).all()

        grouped = {}
        for study_id, report in rows:
            grouped.setdefault(study_id, []).append(report)
        return grouped

    async def get_study_reports_by_study_id(self, study_id: int, cutoff: Optional[datetime] = None) -> List[Report]:
        result = await self.get_study_reports_by_study_ids(study_ids=[study_id], cutoff=cutoff)
        return result.get(study_id, [])

    async def get_study_reports_by_study_id_page(self, study_id: int, limit: int, offset: int, cutoff: Optional[datetime] = None) -> Tuple[List[Report], bool]:
        """Paginated version of get_study_reports_by_study_id() above - one extra row
        beyond the page is fetched so has_more can be determined without a separate
        count query, same convention as search_studies()."""
        stmt = (
            select(Report)
            .join(Link, Link.report_id == Report.id)
            .where(Link.study_id == study_id)
        )

        if cutoff:
            stmt = stmt.where(Report.created_at < cutoff)

        stmt = stmt.order_by(Report.id).offset(offset).limit(limit + 1)

        reports = (await self.db.execute(stmt)).scalars().all()
        has_more = len(reports) > limit
        return reports[:limit], has_more

    async def get_study_persons(self, study_ids: Optional[List[int]] = None, cutoff: Optional[datetime] = None, normalize_names: bool = True) -> Dict[int, List[str]]:
        stmt = (
            select(Link.study_id.label("study_id"), Report.authors)
            .join(Report, Report.id == Link.report_id)
        )

        if cutoff:
            stmt = stmt.where(Report.created_at < cutoff)

        if study_ids is not None:
            stmt = stmt.where(Link.study_id.in_(study_ids))

        rows = (await self.db.execute(stmt)).all()

        final_result = {}

        for item in rows:
            key = item[0]
            authors = [author.strip() for author in item[1]]
            if normalize_names:
                authors = normalize_author_names(authors=authors)

            current_authors = final_result.get(key, [])
            final_result[key] = current_authors + authors

        return final_result

    async def get_study_persons_single(self, study_id : int, cutoff: Optional[datetime] = None, normalize_names: bool = True) -> List[str]:
        result = await self.get_study_persons(study_ids=[study_id], cutoff=cutoff, normalize_names=normalize_names)
        if study_id in result:
            return result[study_id]
        return []


    async def get_study_date_by_id(self, study_id: int) -> Optional[datetime]:
        study = await self.get_study_by_id(study_id)
        return study.created_at if study is not None else None

    # Study Aspects

    async def _get_study_aspect(self, stmt) -> Dict[int, List[Tag]]:
        rows = (await self.db.execute(stmt)).all()  # -> [(StudyID, ID, Description, Acronym, Labels), ...]

        # --- Group results by StudyID ---
        final_result: Dict[int, List[Tag]] = {}
        for study_id, *tag in rows:
            final_result.setdefault(study_id, []).append(self._tag(*tag))

        return final_result

    async def _get_study_aspect_page(self, stmt, limit: int, offset: int) -> Tuple[List[Tag], bool]:
        """Paginated counterpart of _get_study_aspect() above, for a single study - stmt
        must already be scoped to one study_id and select (id, description) columns in
        a stable order. One extra row beyond the page is fetched so has_more can be
        determined without a separate count query, same convention as
        get_study_reports_by_study_id_page()/search_studies(). Returns Tag directly
        (rather than _get_study_aspect()'s raw {"ID", "Description"} dicts) since every
        caller of the *_single_page() methods below wants a Tag anyway - no reason to
        make them convert a second intermediate shape themselves."""
        rows = (await self.db.execute(stmt.offset(offset).limit(limit + 1))).all()  # -> [(ID, Description, Acronym, Labels), ...]
        has_more = len(rows) > limit
        items = [self._tag(*tag) for tag in rows[:limit]]
        return items, has_more

    @staticmethod
    def _tag(tag_id, name, acronym, labels) -> Tag:
        """A tag of the vocabulary as selected by _TAG_COLUMNS."""
        return Tag(id=str(tag_id), keyword=name or "", acronym=acronym, labels=labels or [])

    async def get_study_tags(self, category: str, study_ids: List[int]) -> Dict[int, List[Tag]]:
        """The tags of a category (a key of config/medidex-study.yaml) of each of the studies, of the core database
        and of the updates."""
        if not study_ids:
            return {}
        drafts = await self._drafts(study_ids)
        draft_ids = {draft.id for draft in drafts}
        tags = await self._core_study_tags(category, [study_id for study_id in study_ids if study_id not in draft_ids])
        for draft in drafts:
            items = await self._draft_tags(category, draft)
            if items:
                tags[draft.id] = items
        return tags

    async def _draft_tags(self, category: str, study: UpdateStudy) -> List[Tag]:
        """The tags of a category of a study of an update: those of its graph, by name (see StudyGraphs.draft)."""
        named = []
        tag_ids = self.graphs.tag_ids(study, category)
        if tag_ids:
            rows = (await self.db.execute(
                select(*_TAG_COLUMNS).where(DbTag.category == category, DbTag.id.in_(tag_ids)).order_by(DbTag.id)
            )).all()
            named = [self._tag(*tag) for tag in rows]
        return named + [Tag(id=name, keyword=name) for name in self.graphs.tag_names(study, category)]

    async def _core_study_tags(self, category: str, study_ids: List[int]) -> Dict[int, List[Tag]]:
        if not study_ids:
            return {}
        stmt = (
            select(StudyTag.study_id, *_TAG_COLUMNS)
            .join(DbTag, DbTag.id == StudyTag.tag_id)
            .where(StudyTag.study_id.in_(study_ids), DbTag.category == category)
            .order_by(DbTag.id)
        )

        return await self._get_study_aspect(stmt)

    async def get_study_tags_single(self, category: str, study_id: int) -> List[Tag]:
        result = await self.get_study_tags(category, study_ids=[study_id])
        return result.get(study_id, [])

    async def get_study_tags_single_page(self, category: str, study_id: int, limit: int, offset: int) -> Tuple[List[Tag], bool]:
        if await self.is_draft(study_id):
            tags = await self.get_study_tags_single(category, study_id)
            return tags[offset:offset + limit], len(tags) > offset + limit
        stmt = (
            select(*_TAG_COLUMNS)
            .join(StudyTag, StudyTag.tag_id == DbTag.id)
            .where(StudyTag.study_id == study_id, DbTag.category == category)
            .order_by(DbTag.id)
        )
        return await self._get_study_aspect_page(stmt, limit, offset)

    async def get_all_studies_connected_to_trial_id(self):
        # Define the reusable regex pattern block for PostgreSQL (~ operator)
        regex_conditions = [
            "{col} ~ 'ISRCTN[0-9]{{8}}'",
            "{col} ~ 'ChiCTR[0-9]{{10}}'",
            "{col} ~ 'ChiCTR\\.TRC\\.[0-9]{{8}}'",
            "{col} ~ 'ChiCTR\\.IOR\\.[0-9]{{8}}'",
            "{col} ~ 'ChiCTR-(INR|IPR|POC|IIR|IOQ|OPC)-[0-9]{{8}}'",
            "{col} ~ 'ACTR(N|[0-9])[0-9]{{14}}'",
            "{col} ~ 'CTRI(/|-)[0-9]{{4}}(/|-)[0-9]{{2,3}}(/|-)[0-9]{{6}}'",
            "{col} ~ 'NCT[0-9]{{8}}'",
            "{col} ~ 'DRKS[0-9]{{8}}'",
            "{col} ~ 'NL-OMON[0-9]{{5}}'",
            "{col} ~ 'NL[0-9]{{4}}'",
            "{col} ~ 'IRCT[0-9]{{11,13}}N[0-9]+'",
            "{col} ~ 'KCT[0-9]{{7}}'",
            "{col} ~ 'TCTR[0-9]{{11}}'",
            "{col} ~ 'RBR-.{{7}}'",
            "{col} ~ 'CTIS[0-9]{{4}}-[0-9]{{6}}-[0-9]{{2}}-[0-9]{{2}}'",
            "{col} ~ '(JPRN-)?UMIN[0-9]{{9}}'",
            "{col} ~ '(JPRN-)?JapicCTI-[0-9]{{6}}'",
            "{col} ~ 'JPRN-jRCTs?[0-9]{{9,10}}'",
            "{col} ~ 'EUCTR[0-9]{{4}}-[0-9]{{6}}-[0-9]{{2}}'",
            "{col} ~ 'ITMCTR[0-9]{{10}}'",
            "{col} ~ 'PACTR[0-9]{{15}}'",
            "{col} ~ 'NTR[0-9]{{4,5}}'",
            "{col} ~ 'UKCRNID[0-9]{{4,5}}'",
            "{col} ~ 'SLCTR-[0-9]{{4}}-[0-9]{{3}}'",
            "{col} ~ 'HKCTR-[0-9]{{4}}'",
            "{col} ~ 'M[0-9]{{2}}-[0-9]{{3}}'",
            "{col} ~ 'MCT-[0-9]{{5}}'",
        ]

        def build_regex_block(col):
            return " OR ".join([cond.format(col=col) for cond in regex_conditions])

        # --- Query 1: studies with trial IDs in short_name ---
        query_studies = text(f"""
            SELECT "id"
            FROM "study"
            WHERE {build_regex_block('"short_name"')}
        """)
        result_studies = (await self.db.execute(query_studies)).fetchall()
        all_studies = [row[0] for row in result_studies]

        # --- Query 2: the studies of the registry records linked to one study only ---
        query_reports = text(f"""
            SELECT l."study_id"
            FROM "report" r
            JOIN "link" l ON r."id" = l."report_id"
            WHERE cardinality(r."authors") = 0
            AND l."report_id" IN (
                SELECT "report_id"
                FROM "link"
                GROUP BY "report_id"
                HAVING COUNT(DISTINCT "study_id") = 1
            )
            AND {build_regex_block('r."trial_registration_id"')}
        """)
        result_reports = (await self.db.execute(query_reports)).fetchall()
        all_reports = [row[0] for row in result_reports]

        return all_studies + all_reports

    async def get_study_acronyms(self) -> List[str]:
        stmt = select(Study.short_name)
        rows = (await self.db.execute(stmt)).all()

        acronyms = []
        for (short_name,) in rows:
            # Exclude if more than 2 digits in the short_name
            if len(re.findall(r"\d", short_name)) > 2:
                continue
            acronyms.append(short_name)
        return acronyms
