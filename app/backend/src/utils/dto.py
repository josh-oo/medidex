from pydantic import BaseModel, Field
from typing import Mapping, Optional, List
from datetime import datetime
from enum import Enum


class FilterMode(str, Enum):
    """How one filter dimension (e.g. "processed") should narrow a report list.

    `any` (the default) means "don't filter on this dimension at all" - it's not one of the
    two categories, it's an explicit no-op. `only` keeps just the reports matching this
    dimension, `exclude` keeps everything else. This replaces the older, less intuitive
    "two booleans that both default true, and setting exactly one to false narrows things
    down" pairing - the equivalent of "only" used to require knowing to leave the *other*
    field at its default rather than being a single, self-contained choice. Shared by every
    head that filters a report list (fastapi_app/projects.py's Query params, and any MCP
    tool with the same tri-state filter needs).
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


class Study(BaseModel):
    studyId: int
    shortName: str
    status: str
    countries: List[str]
    numberParticipants: Optional[str]
    duration: Optional[str]
    comparison: Optional[str]
    trialId: Optional[str]
    createdAt: Optional[str]
    updatedAt: Optional[str]

class StudyCreate(BaseModel):
    shortName: str
    status: str
    countries: List[str]
    numberParticipants: Optional[str]
    duration: Optional[str]
    comparison: Optional[str]
    trialId: Optional[str] = None

class StudyPage(BaseModel):
    """A page of the free-text study search (fastapi_app/resources.py's GET /studies/search)."""
    items: List[Study]
    nextCursor: Optional[str] = None

class CandidateStudy(Study):
    """A study suggested as a possible match for a report by the similarity search
    (fastapi_app/core.py's /reports/{report_id}/similar-studies) - a Study plus how
    relevant this particular suggestion is, for the researcher to accept or reject."""
    relevance: float

class CandidateStudyPage(BaseModel):
    items: List[CandidateStudy]
    nextCursor: Optional[str] = None

class Tag(BaseModel):
    id: str
    keyword: str
    relevance: Optional[float] = None

# Naming convention below: each subclass's name says what it adds over its parent,
# not how "detailed" or "list-like" it is - Report is the shared bibliographic base;
# every other Report* type is named for the specific extra data it carries.

class Report(BaseModel):
    reportId: int
    year: int
    title: str
    abstract: Optional[str]
    trialId: Optional[str]
    authors: List[str]
    createdAt: Optional[str]
    updatedAt: Optional[str]

class ReportSources(Report):
    """A Report plus where to find it: its DOI and cached OpenAlex fulltext links
    (ReportService.get_fulltext_links). Returned by GET /reports/{report_id} for the
    pdf-upload view. Too heavy/situational to carry on every row of a paginated
    report list (see ProjectReport below) - only fetched for a single report, or for
    IntakeReport's list (below) which specifically needs it up front."""
    doi: Optional[str] = None
    fulltextLinks: List[str] = Field(default_factory=list)

class ReportFlagUpdate(BaseModel):
    message: str
    public: bool = False

class ReportFlag(BaseModel):
    reportId: int
    createdBy: str
    message: str
    public: bool
    createdAt: str

class ProjectAssignee(BaseModel):
    userId : str
    numberReportsLinked: int = 0

class Project(BaseModel):
    projectId: str
    name: str
    owner: str
    createdAt: datetime
    numberReportsReadyForProcessing: int = 0

class ProjectDetails(Project):
    numberReportsTotal: int
    numberReportsPreProcessed: int = 0
    numberReportsWithPdf: int = 0
    numberReportsReadyForReview: int = 0
    numberReportsAutoSearchedPdf: int = 0
    numberReportsConfirmed: int = 0
    assignees: List[ProjectAssignee] = Field(default_factory=list)

class ProjectTask(BaseModel):
    project: Project
    numberReportsProcessed: int

class ProjectReport(Report):
    """A Report plus its state within a project's curation workflow: whether it has a
    PDF, this user's flag on it, and its linked studies - the row shape for the normal/
    review project report lists (ProjectReportPage.items below). Mirrors report_added
    (src/database/models.py) being project-scoped, temporary metadata rather than
    something that lives on Report itself."""
    hasPdf: Optional[bool]
    flag: Optional[str]
    assignedStudies: List[Study] = Field(default_factory=list)

class ProjectReportPage(BaseModel):
    items: List[ProjectReport]
    nextCursor: Optional[str] = None

class IntakeReport(ReportSources):
    """A ReportSources (DOI + fulltext links, so the pdf-upload view can read them
    straight from the list it already loaded instead of issuing a separate
    GET /reports/{report_id} per row) plus hasPdf. Deliberately NOT a ProjectReport:
    an intake report hasn't been curated yet, so flag/assignedStudies don't apply and
    aren't fetched for this list (see ProjectResourceService.hydrate_report_page's
    include_report_detail branch). The row shape for the admin intake list
    (IntakeReportPage.items below)."""
    hasPdf: Optional[bool] = None

class IntakeReportPage(BaseModel):
    items: List[IntakeReport]
    nextCursor: Optional[str] = None

def tags_to_dto(tags) -> List[Tag]:
    result = []
    for tag in tags:
        tag_data = tag if isinstance(tag, Mapping) else tag.model_dump()
        # Two shapes flow through here: SQLModel objects dumped to lowercase field
        # names ("id"/"description"), and StudyRepository._get_study_aspect's plain
        # dicts, which use "ID"/"Description" instead.
        tag_id = tag_data.get("id", tag_data.get("ID"))
        keyword = tag_data.get("description", tag_data.get("Description"))
        result.append(Tag(id=str(tag_id) if tag_id is not None else "", keyword=keyword or ""))
    return result

def report_flag_to_dto(flag) -> ReportFlag:
    return ReportFlag(
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

def studies_to_dto(studies):
    result = []
    for study in studies:
        output_study = Study(
            studyId=study.id,
            shortName=study.short_name,
            numberParticipants=study.number_participants,
            duration=study.duration,
            comparison=study.comparison,
            countries=study.countries.split("//") if study.countries else [],
            createdAt=study.date_entered,
            updatedAt=study.date_edited,
            status=study.status,
            trialId=study.trial_registration_id,
        )
        result.append(output_study)
    return result

def candidate_studies_to_dto(studies) -> List[CandidateStudy]:
    results = []
    for study in studies:
        results.append(CandidateStudy(
            studyId=study.id,
            shortName=study.short_name,
            numberParticipants=study.number_participants,
            duration=study.duration,
            comparison=study.comparison,
            countries=study.countries.split("//") if study.countries else [],
            createdAt=study.date_entered,
            updatedAt=study.date_edited,
            status=study.status,
            trialId=study.trial_registration_id,
            relevance=study.relevance,
        ))
    return results