from sqlmodel import SQLModel, Field
from sqlalchemy import CheckConstraint, Column, Index, Integer, Sequence, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from typing import Optional, Dict, Any, List
import datetime

"""
The models are the schema: the backend creates missing tables on start (src/database/schema.py), there are no
migrations.

The core database and its updates are kept apart by table (report/update_report, study/update_study,
link/update_link). Merging a report of an update moves its rows into the core tables under the same ids, which
is why both tables of a pair draw their ids from one sequence (REPORT_ID, STUDY_ID).
"""

def server_now(updated: bool = False) -> Any:
    """A TIMESTAMPTZ column set by the database (now()) on insert, and with `updated` on every update too. An explicit
    value (e.g. of an imported study) is kept. Tables with such a column need EAGER_DEFAULTS."""
    kwargs: Dict[str, Any] = {"server_default": func.now()}
    if updated:
        kwargs["onupdate"] = func.now()
    return Field(default=None, nullable=False, sa_column_kwargs=kwargs)


# Reads values set by the database back with RETURNING: an async session cannot load an expired attribute lazily.
EAGER_DEFAULTS = {"eager_defaults": True}

# Marks a table of the updates: its rows only serve the curation of an update, hang off it by ON DELETE CASCADE and count
# as storage of the updates (DatabaseRepository.get_table_storage). A table with a foreign key to a table of the updates
# must be one itself, so removing an update never removes a row of the core database (ResourceSchema checks it).
UPDATE_DATA_KEY = "update_data"
UPDATE_DATA = {"info": {UPDATE_DATA_KEY: True}}
# Update data that is only a cache: not archived when its report is merged (see ReportArchive).
ARCHIVE_KEY = "archive"
UPDATE_CACHE = {"info": {UPDATE_DATA_KEY: True, ARCHIVE_KEY: False}}

REPORT_ID = Sequence("report_id_seq")
STUDY_ID = Sequence("study_id_seq")


def _id_column(sequence: Sequence) -> Column:
    return Column(Integer, sequence, primary_key=True, server_default=sequence.next_value())


class StudyDatabase(SQLModel, table=True):
    """A collection of studies of its own (e.g. the register of one review group). Matching a report only considers the
    studies of its project's database."""
    __tablename__ = "study_database"
    __mapper_args__ = EAGER_DEFAULTS

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    # See EligibilityCriterion in src/utils/eligibility.py.
    eligibility_criteria: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    created_at: Optional[datetime.datetime] = server_now()
    created_by: Optional[str] = None

class ReportFields(SQLModel):
    """The fields of a report, of the core database (Report) and of an update (UpdateReport) alike."""

    # No fulltext PDF exists ("Not Available"): it counts as having one, the placeholder. Whether a report has a PDF is
    # read from the data volume (src/utils/pdfs.py), never stored.
    no_pdf: bool = Field(default=False, nullable=False)
    title: str
    authors: List[str] = Field(default_factory=list, sa_type=ARRAY(Text), nullable=False)
    journal: Optional[str]
    year: int
    volume: Optional[str]
    issue: Optional[str]
    pages: Optional[str]
    language: Optional[str]
    abstract: Optional[str]
    created_at: Optional[datetime.datetime] = server_now()
    updated_at: Optional[datetime.datetime] = server_now(updated=True)
    publisher: Optional[str]
    city: Optional[str]
    doi: Optional[str]
    # Only set once confirmed (by a reviewer, or for a registry record); the unconfirmed guess is
    # UpdateReport.preliminary_trial_id.
    trial_registration_id: Optional[str] = None

    def is_registry_record(self) -> bool:
        """The record of a trial in a registry rather than a publication: no authors, only its trial (see
        ProjectResourceService.build_reports_from_entries). Its PDF is rendered from the registry."""
        return not self.authors and bool(self.trial_registration_id)

class Report(ReportFields, table=True):
    __tablename__ = "report"
    __mapper_args__ = EAGER_DEFAULTS

    id: Optional[int] = Field(default=None, sa_column=_id_column(REPORT_ID))

    __table_args__ = (
        Index('idx_report_created_at', 'created_at'),
        Index('idx_report_trial_id', 'trial_registration_id'),
    )

Index("idx_report_doi_lower", func.lower(Report.doi))

class StudyFields(SQLModel):
    """The fields of a study, of the core database (Study) and of an update (UpdateStudy) alike."""

    short_name: str
    status: str
    created_at: Optional[datetime.datetime] = server_now()
    updated_at: Optional[datetime.datetime] = server_now(updated=True)
    # Overrides of what is derived from the graph (`derive` in config/medidex-study.yaml); the duration in seconds.
    number_participants: Optional[int] = None
    duration: Optional[int] = None
    # See src/utils/graph.py. Tags are tag ids in a study of the core database, but names (or ids) in a study of an
    # update: they only become tags when it is merged.
    graph: Optional[Dict[str, Any]] = Field(default=None, sa_type=JSONB, nullable=True)
    trial_registration_id: Optional[str] = None
    database_id: int = Field(foreign_key="study_database.id")

class Study(StudyFields, table=True):
    __tablename__ = "study"
    __mapper_args__ = EAGER_DEFAULTS

    id: Optional[int] = Field(default=None, sa_column=_id_column(STUDY_ID))

    __table_args__ = (
        Index('idx_study_created_at', 'created_at'),
        Index('idx_study_database', 'database_id'),
        Index('idx_study_short_name', 'short_name'),
        Index('idx_study_trial_id', 'trial_registration_id'),
        # Per database: an imported database may name its studies like another one does.
        UniqueConstraint("database_id", "short_name", name="uq_study_short_name"),
    )

class Link(SQLModel, table=True):
    __tablename__ = "link"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    report_id: int = Field(primary_key=True, foreign_key="report.id", ondelete="CASCADE")

    __table_args__ = (
        Index('idx_link_report', 'report_id'),
    )

class Tag(SQLModel, table=True):
    """A term of the vocabulary of a tag category of config/medidex-study.yaml, shared by every study database."""
    __tablename__ = "tag"

    id: Optional[int] = Field(default=None, primary_key=True)
    category: str
    description: str

# Tags are matched by name ignoring case (StudyGraphs.resolve).
Index("uq_tag_description", Tag.category, func.lower(Tag.description), unique=True)

class StudyTag(SQLModel, table=True):
    """A tag of a study of the core database: those of its graph and those added on their own (e.g. its designs)."""
    __tablename__ = "study_tag"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    tag_id: int = Field(primary_key=True, foreign_key="tag.id", ondelete="CASCADE")

    __table_args__ = (
        Index('idx_study_tag_tag', 'tag_id'),
    )


class Project(SQLModel, table=True):
    """An update of a study database: the reports it brought in, until each of them is merged or deleted."""
    __tablename__ = "project"
    __mapper_args__ = EAGER_DEFAULTS

    id: str = Field(primary_key=True)
    description: str
    created_at: Optional[datetime.datetime] = server_now()
    created_by: str
    database_id: int = Field(foreign_key="study_database.id")

    __table_args__ = UPDATE_DATA

class ProjectAssignees(SQLModel, table=True):
    __tablename__ = "project_assignee"

    project_id: str = Field(
        primary_key=True,
        foreign_key="project.id",
        ondelete="CASCADE",
    )
    assignee: str = Field(primary_key=True)

    __table_args__ = (
        Index("idx_project_assignee_assignee", "assignee"),
        UPDATE_DATA,
    )

class UpdateReport(ReportFields, table=True):
    """A report of an update until it is merged (it becomes a Report of the same id) or deleted. Everything of the
    update about it goes with it through the foreign keys."""
    __tablename__ = "update_report"
    __mapper_args__ = EAGER_DEFAULTS

    id: Optional[int] = Field(default=None, sa_column=_id_column(REPORT_ID))
    project_id: str = Field(foreign_key="project.id", ondelete="CASCADE")
    auto_searched_pdf: bool = Field(default=False, nullable=False)
    # Mirror of whether Qdrant has its vector, kept in sync where it changes (ReportRepository.set_embedded).
    embedded: bool = Field(default=False, nullable=False)
    # Cached OpenAlex lookups: None means not looked up yet, an empty list looked up without result.
    fulltext_links: Optional[List[str]] = Field(default=None, sa_type=ARRAY(Text), nullable=True)
    # Matched against Report.doi when read, so it stays correct as reports are added.
    referenced_dois: Optional[List[str]] = Field(default=None, sa_type=ARRAY(Text), nullable=True)
    # Unconfirmed guess from the upload; never copied to trial_registration_id without a reviewer.
    preliminary_trial_id: Optional[str] = Field(default=None)

    __table_args__ = (
        Index('idx_update_report_project', 'project_id', 'id'),
        Index('idx_update_report_embedded', 'embedded'),
        Index('idx_update_report_preliminary_trial_id', 'preliminary_trial_id'),
        UPDATE_DATA,
    )

class UpdateStudy(StudyFields, table=True):
    """A study created in an update, visible only to the scope that created it (`created_by`, see README, "Scopes")
    until a report linked to it is merged: then it becomes a Study of the same id. Goes with its project, or when it has
    no link left."""
    __tablename__ = "update_study"
    __mapper_args__ = EAGER_DEFAULTS

    id: Optional[int] = Field(default=None, sa_column=_id_column(STUDY_ID))
    project_id: str = Field(foreign_key="project.id", ondelete="CASCADE")
    created_by: str

    __table_args__ = (
        Index('idx_update_study_created_by', 'created_by'),
        UniqueConstraint("database_id", "short_name", name="uq_update_study_short_name"),
        UPDATE_DATA,
    )

class UpdateLink(SQLModel, table=True):
    """A link a scope made in an update, of a report of the update to a study of the core database (`study_id`) or of
    the update (`update_study_id`), exactly one of them. A table referring to a study by the same pair of columns is
    re-pointed to the core study when the study of the update is merged (StudyRepository.promote)."""
    __tablename__ = "update_link"
    __mapper_args__ = EAGER_DEFAULTS

    id: Optional[int] = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="update_report.id", ondelete="CASCADE")
    study_id: Optional[int] = Field(default=None, foreign_key="study.id", ondelete="CASCADE")
    update_study_id: Optional[int] = Field(default=None, foreign_key="update_study.id", ondelete="CASCADE")
    created_by: str
    created_at: Optional[datetime.datetime] = server_now()

    __table_args__ = (
        CheckConstraint("num_nonnulls(study_id, update_study_id) = 1", name="ck_update_link_study"),
        Index(
            'uq_update_link', 'report_id', text('coalesce(study_id, update_study_id)'), 'created_by',
            unique=True,
        ),
        Index('idx_update_link_created_by', 'created_by'),
        Index('idx_update_link_study', 'study_id'),
        Index('idx_update_link_update_study', 'update_study_id'),
        UPDATE_DATA,
    )

class ReportCommit(SQLModel, table=True):
    """An assignee has handed in their links of the report and cannot change them any more (see
    ProjectResourceService.commit_project_work)."""
    __tablename__ = "report_commit"
    __mapper_args__ = EAGER_DEFAULTS

    report_id: int = Field(primary_key=True, foreign_key="update_report.id", ondelete="CASCADE")
    assignee: str = Field(primary_key=True)
    created_at: Optional[datetime.datetime] = server_now()

    __table_args__ = (
        Index("idx_report_commit_assignee", "assignee"),
        UPDATE_DATA,
    )

class ReportArchive(SQLModel, table=True):
    """What the update knew of a report that was merged or deleted (the report, its links and its rows of the tables of
    the updates), kept read-only for later use. No foreign keys: it outlives the report, the project and the
    database."""
    __tablename__ = "report_archive"
    __mapper_args__ = EAGER_DEFAULTS

    report_id: int = Field(primary_key=True)
    project_id: str = Field(index=True)
    project_name: str
    database_id: int = Field(index=True)
    outcome: str
    # Empty for a deleted report.
    study_ids: List[int] = Field(default_factory=list, sa_column=Column(ARRAY(Integer), nullable=False))
    archived_by: Optional[str] = None
    archived_at: Optional[datetime.datetime] = server_now()
    data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))

    __table_args__ = (
        CheckConstraint("outcome IN ('merged', 'deleted')", name="ck_report_archive_outcome"),
    )

class ProjectInnerScore(SQLModel, table=True):
    __tablename__ = "project_inner_score"

    report_id: int = Field(primary_key=True, foreign_key="update_report.id", ondelete="CASCADE")
    other_id: int = Field(primary_key=True, foreign_key="update_report.id", ondelete="CASCADE")
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

class ReportFlag(SQLModel, table=True):
    __tablename__ = "report_flag"
    __mapper_args__ = EAGER_DEFAULTS

    report_id: int = Field(primary_key=True, foreign_key="update_report.id", ondelete="CASCADE")
    created_by: str = Field(primary_key=True)
    created_at: Optional[datetime.datetime] = server_now()
    message: str
    public: bool = Field(default=False, nullable=False)

    __table_args__ = (
        Index('idx_report_flag_created_by', 'created_by'),
        UPDATE_DATA,
    )
