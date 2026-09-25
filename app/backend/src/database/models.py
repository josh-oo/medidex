from sqlmodel import SQLModel, Field
from sqlalchemy import MetaData
from sqlalchemy import Index
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import UniqueConstraint
from sqlalchemy import FetchedValue
from typing import Optional, Dict, Any
import datetime

"""
Resources

These models map onto tables named directly after the generic names used
here (report, study, ...). The bundled demo data (deploy/data/seed/
synthetic_seed.sql) creates its tables under these exact names.

If the resources database is instead pointed at a physical schema that uses
different table/column names (e.g. a Cochrane-style CRG/CENTRAL database),
deploy/data/seed/views.sql provides an optional adapter: views with these
same names re-expose that other schema's data so this module -- and
everything built on top of it -- never has to know about it. See
ops/app-init/init.sh and deploy/data/seed/schema-adapter.conf for how to
enable it.

Report and Study only expose the columns the application actually reads or
writes; a CRG/CENTRAL-style physical schema has several more (CENTRAL*
submission tracking, UDef* legacy fields, ...) that nothing here uses -- see
views.sql for the full physical column list those two views would leave out.
"""

metadata_resources = MetaData()


def _current_utc_timestamp() -> str:
    """Return a UTC timestamp string that matches existing DB formatting."""
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _current_utc_datetime() -> datetime.datetime:
    """Return timezone-aware UTC datetime for TIMESTAMPTZ columns."""
    return datetime.datetime.now(datetime.timezone.utc)

class Report(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "report"

    id: int = Field(primary_key=True)
    report_number: int = -1
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
    trial_registration_id: Optional[str]

    __table_args__ = (
        Index('idx_report_date_entered', 'date_entered'),  # For date filtering
        Index('idx_report_report_number', 'report_number'),  # For PDF lookups
        Index('idx_report_trial_id', 'trial_registration_id'),  # For trial ID searches
    )

class Study(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "study"

    id: int = Field(primary_key=True)
    short_name: str
    status: str
    trialist_contact_details: Optional[str]
    date_entered: str = Field(default_factory=_current_utc_timestamp)
    date_edited: Optional[str] = Field(default_factory=_current_utc_timestamp)
    number_participants: Optional[str]
    countries: Optional[str]
    duration: Optional[str]
    comparison: Optional[str]
    trial_registration_id: Optional[str] = Field(default=None, sa_column_kwargs={"server_default": FetchedValue()})

    __table_args__ = (
        Index('idx_study_date_entered', 'date_entered'),  # For cutoff filtering
        Index('idx_study_short_name', 'short_name'),  # For trial ID matching
        Index('idx_study_trial_id', 'trial_registration_id'),  # For trial ID lookups
        UniqueConstraint("short_name", name="uq_study_short_name"),
    )

class StudyReport(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "study_report"

    id: int = Field(primary_key=True)
    study_id: int = Field(foreign_key="study.id", ondelete="CASCADE")
    report_id: int = Field(foreign_key="report.id", ondelete="CASCADE")

    __table_args__ = (
        Index('idx_study_report_report', 'report_id'),  # For report->studies lookups
        Index('idx_study_report_study', 'study_id'),  # For study->reports lookups
        Index('uq_study_report_report_study', 'report_id', 'study_id', unique=True),  # Prevent duplicate links
    )

class Participant(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "participant"

    id: int = Field(primary_key=True)
    description: str

class StudyParticipant(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "study_participant"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    participant_id: int = Field(primary_key=True, foreign_key="participant.id", ondelete="CASCADE")

class Design(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "design"

    id: int = Field(primary_key=True)
    description: Optional[str] = None

class StudyDesign(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "study_design"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    design_id: int = Field(primary_key=True, foreign_key="design.id", ondelete="CASCADE")

class Intervention(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "intervention"

    id: int = Field(primary_key=True)
    description: Optional[str] = None

class StudyIntervention(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "study_intervention"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    intervention_id: int = Field(primary_key=True, foreign_key="intervention.id", ondelete="CASCADE")

class Condition(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "condition"

    id: int = Field(primary_key=True)
    description: Optional[str] = None

class StudyCondition(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "study_condition"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    condition_id: int = Field(primary_key=True, foreign_key="condition.id", ondelete="CASCADE")

class Outcome(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "outcome"

    id: int = Field(primary_key=True)
    description: Optional[str] = None

class StudyOutcome(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "study_outcome"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    outcome_id: int = Field(primary_key=True, foreign_key="outcome.id", ondelete="CASCADE")

class Project(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "project"

    id: str = Field(primary_key=True)
    description: str
    date_created: datetime.datetime = Field(default_factory=_current_utc_datetime)
    uploaded_by: Optional[str]

class ProjectAssignees(SQLModel, table=True, metadata=metadata_resources):
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

class FulltextExtractions(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "fulltext_extraction"

    report_id: int = Field(primary_key=True, foreign_key="report.id", ondelete="CASCADE")
    data: Dict[str, Any] = Field(
        sa_column=Column(JSONB, nullable=False)
    )

class ReportAdded(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "report_added"

    report_id: int = Field(primary_key=True, foreign_key="report.id", ondelete="CASCADE")
    project_id: str = Field(foreign_key="project.id", ondelete="CASCADE")
    auto_searched_pdf: bool = Field(default=False, nullable=False)

    __table_args__ = (
        Index('idx_report_added_project_report', 'project_id', 'report_id'),
    )

class ProjectInnerScore(SQLModel, table=True, metadata=metadata_resources):
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
    )

class StudyAdded(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "study_added"

    study_id: int = Field(primary_key=True, foreign_key="study.id", ondelete="CASCADE")
    date_created: datetime.datetime = Field(default_factory=_current_utc_datetime)
    created_by: Optional[str]

class StudyReportAdded(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "study_report_added"

    study_report_id: int = Field(primary_key=True, foreign_key="study_report.id", ondelete="CASCADE")
    date_created: datetime.datetime = Field(default_factory=_current_utc_datetime)
    created_by: str = Field(primary_key=True)
    confirmed: bool = Field(default=False, nullable=False)

    __table_args__ = (
        Index('idx_study_report_added_created_by', 'created_by'),  # For user filtering
    )

class ReportFlag(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "report_flag"

    report_id: int = Field(primary_key=True, foreign_key="report.id", ondelete="CASCADE")
    created_by: str = Field(primary_key=True)
    date_created: datetime.datetime = Field(default_factory=_current_utc_datetime)
    message: str
    public: bool = Field(default=False, nullable=False)

    __table_args__ = (
        Index('idx_report_flag_created_by', 'created_by'),
    )
