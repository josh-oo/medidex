from pydantic import BaseModel, Field, create_model, model_validator
from .derive import DerivedFields
from .graph import GraphFormatError, StoredGraph
from .studyconfig import GRAPH_FIELD, INLINE_SEPARATOR, STUDY_CONFIG
from typing import Any, Dict, Mapping, Optional, List, TypeVar, Generic
from datetime import datetime
from enum import Enum

T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    """A page of items from any cursor-paginated list endpoint - see
    src/utils/pagination.py for what the cursor itself encodes."""
    items: List[T]
    nextCursor: Optional[str] = None


class FilterMode(str, Enum):
    """How one filter dimension (e.g. "processed") should narrow a report list.

    `any` (the default) means "don't filter on this dimension at all" - it's not one of the
    two categories, it's an explicit no-op. `only` keeps just the reports matching this
    dimension, `exclude` keeps everything else. This replaces the older, less intuitive
    "two booleans that both default true, and setting exactly one to false narrows things
    down" pairing - the equivalent of "only" used to require knowing to leave the *other*
    field at its default rather than being a single, self-contained choice. Shared by every
    head that filters a report list (fastapi_app/projects.py's Query params).
    """
    any = "any"
    only = "only"
    exclude = "exclude"


def matches_filter(value: bool, mode: FilterMode) -> bool:
    if mode is FilterMode.any:
        return True
    if mode is FilterMode.only:
        return value
    return not value


def filter_mode_to_bool(mode: FilterMode) -> Optional[bool]:
    """None = "any" (no filter) - what ReportRepository.query_project_reports_page's
    plain-bool filter params expect; that layer doesn't know about this enum."""
    if mode is FilterMode.any:
        return None
    return mode is FilterMode.only


# Naming convention below: each subclass's name says what it adds over its parent,
# not how "detailed" or "list-like" it is - ReportBase is the bare identity every
# Report* type shares, Report is the full bibliographic record built on it, and
# every further subclass is named for the specific extra data it carries.

class ReportPreview(BaseModel):
    """Bare-bones Report identity (id + title) for list views that don't need the
    full bibliographic record, e.g. GET /studies/{study_id}/reports's Page[ReportBase]
    below, which can page through a study with a lot of linked reports."""
    reportId: int
    title: str

class StudyPreview(BaseModel):
    """Bare-bones Study identity for ReportCuration.assignedStudies below - the frontend
    only ever reads studyId/shortName/createdAt off an assigned study (the badge label,
    click-to-open, and the "linked after this report was entered" highlight), never the
    full bibliographic record."""
    studyId: int
    shortName: str
    createdAt: Optional[str]

class ReportPayload(BaseModel):
    """Bare-bones Report identity (id + title) for list views that don't need the
    full bibliographic record, e.g. GET /studies/{study_id}/reports's Page[ReportBase]
    below, which can page through a study with a lot of linked reports."""
    title: str
    year: int
    abstract: Optional[str]
    trialId: Optional[str]
    authors: List[str]

class Report(ReportPayload):
    reportId: int
    createdAt: Optional[str]
    updatedAt: Optional[str]

class ReportSources(Report):
    """A Report plus where to find it: its DOI and cached OpenAlex fulltext links
    (ReportService.get_fulltext_links). Returned by GET /reports/{report_id} for the
    pdf-upload view. Too heavy/situational to carry on every row of a paginated
    report list (see ReportCuration below) - only fetched for a single report, or for
    ReportIntake's list (below) which specifically needs it up front."""
    doi: Optional[str] = None
    fulltextLinks: List[str] = Field(default_factory=list)

class ReportCuration(Report):
    """A Report plus its state within a project's curation workflow: whether it has a
    PDF, this user's flag on it, and its linked studies - the row shape for the normal/
    review project report lists (Page[ReportCuration].items below). Mirrors report_added
    (src/database/models.py) being project-scoped, temporary metadata rather than
    something that lives on Report itself."""
    hasPdf: Optional[bool]
    flag: Optional[str]
    assignedStudies: List[StudyPreview] = Field(default_factory=list)
    # The unconfirmed .ris-upload/fulltext guess (report_added.trial_registration_id) -
    # distinct from this Report's own trialId, which only ever holds a reviewer-confirmed
    # value. Lets the frontend prefill a trial-id search with a best guess even before
    # anyone has confirmed it.
    preliminaryTrialId: Optional[str] = None
    # Optional data a downstream deployable attaches on request (see fastapi_app/enrichment.py),
    # keyed by enricher. Always empty unless the list was requested with `include`.
    extensions: Dict[str, Any] = Field(default_factory=dict)

class ReportIntake(ReportSources):
    """A ReportSources (DOI + fulltext links, so the pdf-upload view can read them
    straight from the list it already loaded instead of issuing a separate
    GET /reports/{report_id} per row) plus hasPdf. Deliberately NOT a ReportCuration:
    an intake report hasn't been curated yet, so flag/assignedStudies don't apply and
    aren't fetched for this list (see ProjectResourceService.hydrate_report_page's
    include_report_detail branch). The row shape for the admin intake list
    (Page[ReportIntake].items below)."""
    hasPdf: Optional[bool] = None
    # Marked as having no PDF ("Not available", Report.no_pdf); hasPdf is true for it too.
    pdfUnavailable: bool = False
    # Optional data a downstream deployable attaches on request, as on ReportCuration.
    extensions: Dict[str, Any] = Field(default_factory=dict)

class Tag(BaseModel):
    id: str
    keyword: str

class StudyGraphNode(BaseModel):
    """A node of the graph of a study: an entity of a kind of config/medidex-study.yaml. A node that is a value holds it: the name
    of the tag (with its id) or the text."""
    id: str
    kind: str
    value: Optional[str] = None
    tagId: Optional[str] = None

class StudyGraphEdge(BaseModel):
    """A relation between two nodes of a study's graph, by their ids (`study` is the study itself)."""
    relation: str
    source: str
    target: str

class StudyGraph(BaseModel):
    """The graph of a study (the study ontology, config/medidex-study.yaml), the tags named. `text` is the plain text an older study holds
    instead of a structure (then there are no nodes)."""
    nodes: List[StudyGraphNode] = Field(default_factory=list)
    edges: List[StudyGraphEdge] = Field(default_factory=list)
    text: Optional[str] = None

class TagCandidate(Tag):
    relevance: float

def _study_fields_model():
    """The fields of a study, made from config/medidex-study.yaml: the attributes of its Study, the tag categories kept in a column of
    the study (as lists of names, e.g. countries). The graph of a study is read with `StudyRepository.get_graphs`."""
    attributes: Dict[str, Any] = {}
    for key, field in STUDY_CONFIG.fields.items():
        if field.required or field.type == "enum":
            attributes[key] = (str, Field(description=field.label))
        else:
            attributes[key] = (Optional[str], Field(default=None, description=field.label))
    for key in STUDY_CONFIG.inline_categories:
        attributes[key] = (List[str], Field(default_factory=list, description=STUDY_CONFIG.categories[key].description))
    return create_model("StudyFields", __doc__="The fields of a study, as configured in config/medidex-study.yaml.", **attributes)

StudyFields = _study_fields_model()

_derived = DerivedFields()

def study_values(study) -> Dict[str, Any]:
    """The fields of a study of the database (see StudyFields), read as config/medidex-study.yaml says. A field the study has
    no value for is calculated from its graph if the config says how (`derive`, e.g. the participants of its arms)."""
    values: Dict[str, Any] = {key: getattr(study, field.column) for key, field in STUDY_CONFIG.fields.items()}
    for key, field in STUDY_CONFIG.fields.items():
        if field.derive is not None and not (values[key] or "").strip():
            values[key] = _derived.value(field, getattr(study, GRAPH_FIELD, None)) or values[key]
    for key in STUDY_CONFIG.inline_categories:
        column = getattr(study, key)
        values[key] = [part.strip() for part in column.split(INLINE_SEPARATOR) if part.strip()] if column else []
    return values

class StudyPayload(StudyFields):
    """The fields needed to create a study - everything else (studyId, timestamps) is
    server-generated, so this also doubles as the PUT /studies request body. Besides the fields it takes the
    graph of the study (its arms and their comparisons) as JSON (see utils/graph.py), with the tags by name or id. The values of
    enum fields (config/medidex-study.yaml) must be allowed ones and the graph must be a graph of it; only checked
    here, not for the studies already in the database."""

    graph: Optional[str] = Field(default=None, description="The graph of the study (its arms and their comparisons) as JSON, see utils/graph.py")

    @model_validator(mode="after")
    def _check_enums(self) -> "StudyPayload":
        for key, values in STUDY_CONFIG.enums.items():
            if getattr(self, key) not in values:
                raise ValueError(f"{key} must be one of: {', '.join(values)}")
        return self

    @model_validator(mode="after")
    def _check_graph(self) -> "StudyPayload":
        try:
            StoredGraph(STUDY_CONFIG.graph).loads(getattr(self, GRAPH_FIELD))
        except GraphFormatError as exc:
            raise ValueError(f"{GRAPH_FIELD}: {exc}") from exc
        return self

class Study(StudyFields):
    studyId: int
    createdAt: Optional[str]
    updatedAt: Optional[str]

class StudyFull(Study):
    """A Study plus everything the study details view fetches per-study: its linked
    reports and its tags per category of config/medidex-study.yaml (interventions, conditions,
    countries, ...). Returned by GET /studies/{study_id}. Each nested list is only its
    first page (see that endpoint's `limit` param, default 10) - page further through any
    one of them with the matching /studies/{study_id}/* endpoint and its nextCursor, same
    as fastapi_app/resources.py's standalone aspect endpoints."""
    reports: Page[ReportPreview] = Field(default_factory=lambda: Page[ReportPreview](items=[]))
    tags: Dict[str, Page[Tag]] = Field(default_factory=dict)
    # The graph of config/medidex-study.yaml, with its tags named.
    graph: StudyGraph = Field(default_factory=StudyGraph)

class GraphValueSchema(BaseModel):
    """What an entity that is a value holds: a tag of a category, or a primitive."""
    category: Optional[str] = None
    type: Optional[str] = None
    values: List[str] = []

class GraphEntitySchema(BaseModel):
    """A kind of entity of the graph of a study, e.g. an arm, a population or a dosage (see the study ontology, config/medidex-study.yaml)."""
    key: str
    label: str
    icon: str
    color: str
    # The study itself.
    root: bool = False
    value: Optional[GraphValueSchema] = None

class GraphRelationSchema(BaseModel):
    """A kind of relation between two entities, e.g. the comparison of two arms or the dosage of an arm."""
    key: str
    label: str
    icon: str
    color: str
    # The kinds of entity an edge can start and end at.
    source: List[str]
    target: List[str]
    symmetric: bool
    many: bool
    required: bool
    line: bool
    separator: str
    card: bool
    # Leads to values: it describes its source (the dosage of an arm) instead of connecting two entities.
    attribute: bool
    # The relation it specialises (a primary outcome is an outcome), if any.
    parent: Optional[str] = None

class GraphSchema(BaseModel):
    entities: List[GraphEntitySchema] = []
    relations: List[GraphRelationSchema] = []

class StudyFieldSchema(BaseModel):
    """A primitive value of a study (see the attributes of Study in config/medidex-study.yaml)."""
    key: str
    label: str
    type: str
    icon: str
    color: str
    display: str
    values: List[str] = []

class StudyMetaSchema(BaseModel):
    """A metadata field of the database record of a study (see the attributes of Study annotated `meta` in config/medidex-study.yaml)."""
    key: str
    label: str
    type: str

class TagCategorySchema(BaseModel):
    """A tag category (see the tag categories of config/medidex-study.yaml)."""
    key: str
    label: str
    icon: str
    color: str
    searchField: str
    freeTextSearch: bool
    description: str

class StudySchema(BaseModel):
    """What a study consists of and how it is presented. Returned by GET /study-schema."""
    fields: List[StudyFieldSchema]
    meta: List[StudyMetaSchema]
    tags: List[TagCategorySchema]
    graph: GraphSchema = GraphSchema()

class StudyCandidate(Study):
    """A study suggested as a possible match for a report by the similarity search
    (fastapi_app/core.py's /reports/{report_id}/similar-studies) - a Study plus how
    relevant this particular suggestion is, for the researcher to accept or reject."""
    relevance: float

class FlagPayload(BaseModel):
    message: str
    public: bool = False

class Flag(FlagPayload):
    reportId: int
    createdBy: str
    createdAt: str

class Assignee(BaseModel):
    userId : str
    numberReportsLinked: int = 0
    # Reports the assignee is done with: linked to a study or flagged publicly.
    numberReportsCompleted: int = 0
    # Reports the assignee has handed in their links of (see ReportCommit).
    numberReportsCommitted: int = 0
    # Has handed in their links of every report.
    committed: bool = False

class Project(BaseModel):
    projectId: str
    name: str
    owner: str
    createdAt: datetime
    # The study database its reports are matched against and added to.
    databaseId: int
    numberReportsReadyForProcessing: int = 0
    numberReportsTotal: int
    numberReportsPreProcessed: int = 0
    numberReportsWithPdf: int = 0
    numberReportsReadyForReview: int = 0
    # Reports every assignee has committed their links of: the owner can merge them (finished ones included).
    numberReportsReadyForMerge: int = 0
    numberReportsAutoSearchedPdf: int = 0
    numberReportsConfirmed: int = 0
    # Reports finished with: merged into the core database or deleted (see UpdateMergeService); both are archived.
    numberReportsMerged: int = 0
    numberReportsDeleted: int = 0
    # Reports put through a postprocessor (chosen at upload) and how many of them have finished it.
    numberReportsPostprocessing: int = 0
    numberReportsPostprocessed: int = 0
    assignees: List[Assignee] = Field(default_factory=list)
    # Every assignee has committed their links of every report still in the project: nothing is left to link.
    locked: bool = False
    # When its last report was merged or deleted; None while reports are left.
    completedAt: Optional[datetime] = None

class Task(BaseModel):
    projectId: str
    name: str
    owner: str
    createdAt: datetime
    databaseId: int
    numberReportsTotal: int = 0
    numberReportsReadyForProcessing: int = 0
    numberReportsProcessed: int
    # Reports the user is done with: linked to a study or flagged publicly; those not committed yet they can commit.
    numberReportsCompleted: int = 0
    # Reports the user has handed in their links of; they are left out of their curation view.
    numberReportsCommitted: int = 0
    # Has handed in their links of every report.
    committed: bool = False
    # The assignees (user ids) who have not committed their links yet: whom the update waits for.
    pendingAssignees: List[str] = Field(default_factory=list)

class DatabasePayload(BaseModel):
    """What describes a study database; the body of POST /databases."""
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    eligibilityCriteria: str = Field(min_length=1, description="Which studies belong in the database, e.g. the inclusion criteria of the register.")

class DatabaseUpdate(BaseModel):
    """The body of PATCH /databases/{id}: the fields given are changed, the others kept. An empty description removes it;
    name and eligibility criteria cannot be empty."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    eligibilityCriteria: Optional[str] = Field(default=None, min_length=1)

class Database(BaseModel):
    databaseId: int
    # Not all its reports are in the vectorstore yet (e.g. right after an import): its studies are found by the
    # search, but not yet suggested for new reports. Seen in the vectorstore on every request, not stored.
    indexing: bool = False
    numberReportsIndexed: int = 0
    name: str
    description: Optional[str] = None
    eligibilityCriteria: str
    createdAt: datetime
    numberStudies: int = 0
    numberReports: int = 0

class StorageExtra(BaseModel):
    """Storage an extension keeps elsewhere (see utils/storage.py), e.g. chat histories."""
    label: str
    bytes: int

class StorageUsage(BaseModel):
    """What one part of a database takes: its rows in the tables of the resource database, its points in the search
    index (vectors and payloads, without the index of the collection) and its PDFs."""
    dataBytes: int
    searchIndexBytes: int
    pdfBytes: int
    pdfFiles: int
    extras: List[StorageExtra] = []

class DatabaseStorage(BaseModel):
    """What a database takes in storage (GET /databases/{id}/storage), estimates. `database` is what stays: its studies,
    the reports linked to them and their search index and PDFs. `updates` only serves the curation of its updates
    (their projects, the reports not linked yet, scores, extracted metadata, proposals, chat histories) and goes
    once they are done."""
    databaseId: int
    # The reports linked to its studies (numberReports of the database).
    numberReports: int
    numberUpdates: int
    # The reports its updates brought in, linked or not.
    numberReportsInUpdates: int
    database: StorageUsage
    updates: StorageUsage

class DatabaseReport(BaseModel):
    """A report of a study in the exchange format of a database (see DatabaseExport)."""
    title: str
    year: int
    authors: List[str] = Field(default_factory=list)
    abstract: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    language: Optional[str] = None
    publisher: Optional[str] = None
    city: Optional[str] = None
    doi: Optional[str] = None
    trialId: Optional[str] = None
    # When the report was entered into the database it comes from ("YYYY-MM-DD HH:MM:SS"); now if left out.
    createdAt: Optional[str] = None
    # Its fulltext PDF: the name of the file in the archive of the database (e.g. "pdfs/12.pdf", see utils/archive.py).
    pdf: Optional[str] = None

class DatabaseStudy(StudyFields):
    """A study in the exchange format of a database: its fields (config/medidex-study.yaml), its graph with the tags by
    name, the names of its tags per category kept in tables (e.g. interventions; those kept in a column, e.g. countries,
    are fields) and its reports."""
    graph: Optional[Dict[str, Any]] = None
    tags: Dict[str, List[str]] = Field(default_factory=dict)
    reports: List[DatabaseReport] = Field(default_factory=list)
    # When the study was entered into the database it comes from ("YYYY-MM-DD HH:MM:SS"); now if left out.
    createdAt: Optional[str] = None

class DatabaseExport(BaseModel):
    """A whole study database as one JSON document, `database.json` of its archive (utils/archive.py) with the PDFs of
    its reports: what GET /databases/{id}/export returns and POST /databases/import reads (where the request names and
    describes the new database). Reports linked to several studies are listed under each of them (and imported once)."""
    format: str = "medidex-database"
    version: int = 1
    name: str
    description: Optional[str] = None
    eligibilityCriteria: Optional[str] = None
    studies: List[DatabaseStudy] = Field(default_factory=list)

def tags_to_dto(tags) -> List[Tag]:
    """Converts SQLModel aspect rows (Intervention/Condition/Outcome, dumped to their
    lowercase "id"/"description" field names) into Tag - used by the /interventions,
    /conditions, /outcomes "all items" endpoints. StudyRepository's own study-scoped
    aspect lookups (interventions/conditions/outcomes/participants/design) build Tag
    directly instead of going through here."""
    result = []
    for tag in tags:
        tag_data = tag if isinstance(tag, Mapping) else tag.model_dump()
        tag_id = tag_data.get("id")
        keyword = tag_data.get("description")
        result.append(Tag(id=str(tag_id) if tag_id is not None else "", keyword=keyword or ""))
    return result

def report_flag_to_dto(flag) -> Flag:
    return Flag(
        reportId=flag.report_id,
        createdBy=flag.created_by,
        message=flag.message,
        public=flag.public,
        createdAt=flag.date_created.isoformat(),
    )

def reports_to_dto(reports) -> List[Report]:
    result = []
    for report in reports:
        result.append(Report(
            reportId=report.id,
            year=report.year,
            title=report.title,
            abstract=report.abstract,
            trialId=report.trial_registration_id,
            authors=report.authors.split("//") if report.authors else [],
            createdAt=report.date_entered,
            updatedAt=report.date_edited,
        ))
    return result

def reports_to_base_dto(reports) -> List[ReportPreview]:
    return [ReportPreview(reportId=report.id, title=report.title) for report in reports]

def studies_to_dto(studies):
    return [
        Study(studyId=study.id, createdAt=study.date_entered, updatedAt=study.date_edited, **study_values(study))
        for study in studies
    ]

def studies_to_preview_dto(studies) -> List[StudyPreview]:
    return [
        StudyPreview(studyId=study.id, shortName=study.short_name, createdAt=study.date_entered)
        for study in studies
    ]

def candidate_studies_to_dto(studies) -> List[StudyCandidate]:
    return [
        StudyCandidate(
            studyId=study.id, createdAt=study.date_entered, updatedAt=study.date_edited, relevance=study.relevance, **study_values(study)
        )
        for study in studies
    ]
