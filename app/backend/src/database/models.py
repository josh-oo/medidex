from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Index
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import UniqueConstraint
from sqlalchemy import FetchedValue
from sqlalchemy import func
from typing import Optional, Dict, Any, List
import datetime

"""
Resources

These models map onto tables named directly after the generic names used
here (report, study, ...), which the backend creates on start
(src/database/schema.py).
"""

def _current_utc_timestamp() -> str:
    """Return a UTC timestamp string that matches existing DB formatting."""
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _current_utc_datetime() -> datetime.datetime:
    """Return timezone-aware UTC datetime for TIMESTAMPTZ columns."""
    return datetime.datetime.now(datetime.timezone.utc)

# The `info` key of a table whose rows only serve the curation of an update (e.g. the scores between its reports):
# they count as storage of the updates of a database, even for reports already linked to a study, since they go once
# the update is done (DatabaseRepository.get_table_storage). Set it with `__table_args__ = UPDATE_DATA` or as the last
# item of the tuple.
UPDATE_DATA_KEY = "update_data"
UPDATE_DATA = {"info": {UPDATE_DATA_KEY: True}}
# Update data that is only a cache of the curation (e.g. the scores between its reports): dropped when its report is
# merged, not archived (see ReportArchive).
ARCHIVE_KEY = "archive"
UPDATE_CACHE = {"info": {UPDATE_DATA_KEY: True, ARCHIVE_KEY: False}}

class StudyDatabase(SQLModel, table=True):
    """A collection of studies of its own (e.g. the register of one review group): its studies, and the projects
    that bring new reports to them. Matching a report only considers the studies of its project's database. There is
    no default one: every deployment brings (creates or imports) its own databases."""
    __tablename__ = "study_database"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    # Which studies belong in the database (free text, e.g. the inclusion criteria of the register).
    eligibility_criteria: str
    date_created: datetime.datetime = Field(default_factory=_current_utc_datetime)
    created_by: Optional[str] = None

class Report(SQLModel, table=True):
    __tablename__ = "report"

    id: int = Field(primary_key=True)
    # No fulltext PDF of the report exists ("Not Available"): it counts as having one, and its PDF is the
    # placeholder. Whether it has a PDF is read from the data volume (src/utils/pdfs.py), never stored.
    no_pdf: bool = Field(default=False, nullable=False)
    title: str
    authors: str
    journal: Optional[str]
    year: int
    volume: Optional[str]
    issue: Optional[str]
    pages: Optional[str]
    language: Optional[str]
    abstract: Optional[str]
    date_entered: str = Field(default_factory=_current_utc_timestamp)
    date_edited: Optional[str] = Field(default_factory=_current_utc_timestamp)
    publisher: Optional[str]
    city: Optional[str]
    doi: Optional[str]
    # Confirmed trial registration id - only set once a reviewer has confirmed it, unlike
    # ReportAdded.trial_registration_id below (the unconfirmed .ris-upload/fulltext guess).
    trial_registration_id: Optional[str]

    __table_args__ = (
        Index('idx_report_date_entered', 'date_entered'),  # For date filtering
        Index('idx_report_trial_id', 'trial_registration_id'),  # For trial ID searches
    )

# Looking reports up by DOI ignores case (StudyRepository.get_studies_by_report_dois).
Index("idx_report_doi_lower", func.lower(Report.doi))

class Study(SQLModel, table=True):
    __tablename__ = "study"

    id: int = Field(primary_key=True)
    short_name: str
    status: str
    trialist_contact_details: Optional[str]
    date_entered: str = Field(default_factory=_current_utc_timestamp)
    date_edited: Optional[str] = Field(default_factory=_current_utc_timestamp)
    number_participants: Optional[str]
    countries: Optional[str]
    # Legacy plain texts of studies from before the graph, no longer read as fields (`graph.text_column` of
    # config/medidex-study.yaml shows the comparison).
    duration: Optional[str]
    comparison: Optional[str]
    # The arms of the study and their comparisons: JSON, see src/utils/graph.py.
    graph: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB, nullable=True))
    trial_registration_id: Optional[str] = Field(default=None, sa_column_kwargs={"server_default": FetchedValue()})
    database_id: int = Field(foreign_key="study_database.id")

    __table_args__ = (
        Index('idx_study_date_entered', 'date_entered'),  # For cutoff filtering
        Index('idx_study_database', 'database_id'),  # For matching within a database
        Index('idx_study_short_name', 'short_name'),  # For trial ID matching
        Index('idx_study_trial_id', 'trial_registration_id'),  # For trial ID lookups
        # Unique within a database: an imported database may name its studies like those of another one.
        UniqueConstraint("database_id", "short_name", name="uq_study_short_name"),
    )

class StudyReport(SQLModel, table=True):
    __tablename__ = "study_report"

    id: int = Field(primary_key=True)
    study_id: int = Field(foreign_key="study.id", ondelete="CASCADE")
    report_id: int = Field(foreign_key="report.id", ondelete="CASCADE")

    __table_args__ = (
        Index('idx_study_report_report', 'report_id'),  # For report->studies lookups
        Index('idx_study_report_study', 'study_id'),  # For study->reports lookups
        Index('uq_study_report_report_study', 'report_id', 'study_id', unique=True),  # Prevent duplicate links
    )

class Participant(SQLModel, table=True):
    __tablename__ = "participant"

    id: int = Field(primary_key=True)
    description: str

class StudyParticipant(SQLModel, table=True):
    __tablename__ = "study_participant"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    participant_id: int = Field(primary_key=True, foreign_key="participant.id", ondelete="CASCADE")

class Design(SQLModel, table=True):
    __tablename__ = "design"

    id: int = Field(primary_key=True)
    description: Optional[str] = None

class StudyDesign(SQLModel, table=True):
    __tablename__ = "study_design"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    design_id: int = Field(primary_key=True, foreign_key="design.id", ondelete="CASCADE")

class Intervention(SQLModel, table=True):
    __tablename__ = "intervention"

    id: int = Field(primary_key=True)
    description: Optional[str] = None

class StudyIntervention(SQLModel, table=True):
    __tablename__ = "study_intervention"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    intervention_id: int = Field(primary_key=True, foreign_key="intervention.id", ondelete="CASCADE")

class Condition(SQLModel, table=True):
    __tablename__ = "condition"

    id: int = Field(primary_key=True)
    description: Optional[str] = None

class StudyCondition(SQLModel, table=True):
    __tablename__ = "study_condition"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    condition_id: int = Field(primary_key=True, foreign_key="condition.id", ondelete="CASCADE")

class Outcome(SQLModel, table=True):
    __tablename__ = "outcome"

    id: int = Field(primary_key=True)
    description: Optional[str] = None

class StudyOutcome(SQLModel, table=True):
    __tablename__ = "study_outcome"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    outcome_id: int = Field(primary_key=True, foreign_key="outcome.id", ondelete="CASCADE")

class Project(SQLModel, table=True):
    __tablename__ = "project"

    id: str = Field(primary_key=True)
    description: str
    date_created: datetime.datetime = Field(default_factory=_current_utc_datetime)
    uploaded_by: Optional[str]
    # The database whose studies the reports of the project are matched against and added to.
    database_id: int = Field(foreign_key="study_database.id")

    # Deleting a project deletes the reports it brought in, also those already linked to a study: the
    # cascade runs project -> report_added -> report here, everything below a report (links to studies,
    # flags, scores, ...) is removed by the foreign keys of the database.
    reports_added: List["ReportAdded"] = Relationship(
        back_populates="project", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

class ProjectAssignees(SQLModel, table=True):
    __tablename__ = "project_assignee"

    project_id: str = Field(
        primary_key=True,
        foreign_key="project.id",
        ondelete="CASCADE",
    )
    assignee: str = Field(primary_key=True)  # user_id

    __table_args__ = (
        Index("idx_project_assignee_assignee", "assignee"),
    )

class ReportCommit(SQLModel, table=True):
    """An assignee has handed in their links of the report: they cannot change them any more. Once every assignee has
    committed every report of a project, the project is locked and its owner merges their links (see
    ProjectResourceService.commit_project_work)."""
    __tablename__ = "report_commit"

    report_id: int = Field(primary_key=True, foreign_key="report.id", ondelete="CASCADE")
    assignee: str = Field(primary_key=True)  # user_id
    date_created: datetime.datetime = Field(default_factory=_current_utc_datetime)

    __table_args__ = (
        Index("idx_report_commit_assignee", "assignee"),
        UPDATE_DATA,
    )

class ReportArchive(SQLModel, table=True):
    """A report of an update that is done with: merged into the core database or deleted. Read-only, kept for later use
    (e.g. training models): what the update knew of the report - its links in every scope, flags, commits, the update
    data of the tables (see UPDATE_DATA) and of the extensions (see src/utils/storage.py) - while the update data itself
    is removed (see UpdateMergeService). No foreign keys: the archive outlives the report, the project and the
    database."""
    __tablename__ = "report_archive"

    report_id: int = Field(primary_key=True)
    project_id: str = Field(index=True)
    project_name: str
    database_id: int = Field(index=True)
    outcome: str  # merged | deleted
    # The studies the report was merged into; empty for a deleted report.
    study_ids: List[int] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    archived_by: Optional[str] = None
    archived_at: datetime.datetime = Field(default_factory=_current_utc_datetime)
    # Postgres compresses large values of it on its own (TOAST).
    data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))

class FulltextExtractions(SQLModel, table=True):
    __tablename__ = "fulltext_extraction"

    report_id: int = Field(primary_key=True, foreign_key="report.id", ondelete="CASCADE")
    data: Dict[str, Any] = Field(
        sa_column=Column(JSONB, nullable=False)
    )

class ReportAdded(SQLModel, table=True):
    __tablename__ = "report_added"

    report_id: int = Field(primary_key=True, foreign_key="report.id", ondelete="CASCADE")
    project_id: str = Field(foreign_key="project.id", ondelete="CASCADE")
    auto_searched_pdf: bool = Field(default=False, nullable=False)
    # Denormalized mirror of external state (Qdrant vector existence), scoped here rather
    # than on Report because it's only meaningful for the lifetime of this report's project
    # association: cascading away with this row when the project is deleted is the wanted
    # behavior, not a gap to work around - Report itself shouldn't carry project-scoped,
    # temporary metadata. Kept in sync at every write site that changes the underlying
    # state - see ReportRepository.set_embedded() and its callers - rather than computed on
    # read. Whether the report has a PDF is not mirrored: it is read from the data volume
    # (src/utils/pdfs.py, ReportRepository.get_readiness_sets).
    embedded: bool = Field(default=False, nullable=False)
    # Cached OpenAlex fulltext-link search result for this report's DOI (see
    # OpenAlexService.get_pdf_links_by_doi) - populated by the post-upload background
    # job (src/background/wrapper.py's _auto_search_report_pdf, via
    # ProjectRepository.set_report_auto_searched_pdf) so report detail views
    # (ReportService.get_fulltext_links) don't re-hit OpenAlex on every read. None means
    # "not searched yet" (falls back to a live lookup); an empty list means "searched,
    # nothing found" - that distinction matters so the fallback doesn't refetch forever.
    fulltext_links: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    # Normalized DOIs of the works this report cites, from the same OpenAlex lookup as
    # fulltext_links (see OpenAlexService.get_works_by_dois) and cached the same way:
    # None means "not looked up yet", an empty list "looked up, nothing found". Matched
    # against Report.doi at read time (ReportService.get_referenced_studies), not stored
    # as links, so it stays correct as reports are added later.
    referenced_dois: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    # Best-effort, UNCONFIRMED trial registration id guess for this report - parsed from
    # the .ris upload (src/services/project.py's build_reports_from_entries) or from the
    # report's fulltext (ReportService.get_trial_ids). Report.trial_registration_id above
    # is the confirmed counterpart; this one is never written there automatically - a
    # reviewer has to confirm a guess before it counts as authoritative.
    trial_registration_id: Optional[str] = Field(default=None)

    project: Optional[Project] = Relationship(back_populates="reports_added")
    # Deleting this record (as part of its project) deletes the report itself.
    report: Optional[Report] = Relationship(sa_relationship_kwargs={"cascade": "all, delete"})

    __table_args__ = (
        Index('idx_report_added_project_report', 'project_id', 'report_id'),
        Index('idx_report_added_embedded', 'embedded'),  # For readiness filtering
        Index('idx_report_added_trial_id', 'trial_registration_id'),  # For trial ID searches
    )

class ProjectInnerScore(SQLModel, table=True):
    __tablename__ = "project_inner_score"

    report_id: int = Field(primary_key=True, foreign_key="report.id", ondelete="CASCADE")
    other_id: int = Field(primary_key=True, foreign_key="report.id", ondelete="CASCADE")
    score: float

    __table_args__ = (
        Index(
            "idx_project_inner_score_report_score",
            "report_id",
            "score",
            postgresql_using="btree",
        ),
        Index(
            "idx_project_inner_score_other_score",
            "other_id",
            "score",
            postgresql_using="btree",
        ),
        UPDATE_CACHE,
    )

class StudyAdded(SQLModel, table=True):
    __tablename__ = "study_added"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    date_created: datetime.datetime = Field(default_factory=_current_utc_datetime)
    created_by: Optional[str]

class StudyReportAdded(SQLModel, table=True):
    __tablename__ = "study_report_added"

    study_report_id: int = Field(primary_key=True, foreign_key="study_report.id", ondelete="CASCADE")
    date_created: datetime.datetime = Field(default_factory=_current_utc_datetime)
    created_by: str = Field(primary_key=True)
    confirmed: bool = Field(default=False, nullable=False)

    __table_args__ = (
        Index('idx_study_report_added_created_by', 'created_by'),  # For user filtering
    )

class ReportFlag(SQLModel, table=True):
    __tablename__ = "report_flag"

    report_id: int = Field(primary_key=True, foreign_key="report.id", ondelete="CASCADE")
    created_by: str = Field(primary_key=True)
    date_created: datetime.datetime = Field(default_factory=_current_utc_datetime)
    message: str
    public: bool = Field(default=False, nullable=False)

    __table_args__ = (
        Index('idx_report_flag_created_by', 'created_by'),
    )
