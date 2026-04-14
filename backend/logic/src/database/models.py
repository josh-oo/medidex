from sqlmodel import SQLModel, Field
from sqlalchemy import MetaData
from sqlalchemy import Index
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from typing import Optional, Dict, Any
import datetime

"""
Resources
"""

metadata_resources = MetaData()


def _current_utc_timestamp() -> str:
    """Return a UTC timestamp string that matches existing DB formatting."""
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _current_utc_datetime() -> datetime.datetime:
    """Return timezone-naive UTC datetime for timestamp columns."""
    return datetime.datetime.utcnow()

class Report(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblReport"

    CENTRALReportID: Optional[int]
    CRGReportID: int = Field(primary_key=True)
    ReportNumber: int = -1
    Title: str
    Notes: Optional[str]
    OriginalTitle: Optional[str]
    Authors: str
    Journal: str
    Year: int
    Volume: Optional[str]
    Issue: Optional[str]
    Pages: Optional[str]
    Language: Optional[str]
    Abstract: Optional[str]
    CENTRALSubmissionStatus : Optional[int]
    CopyStatus: Optional[str]
    DatetoCENTRAL: Optional[str]
    Dateentered: str = Field(default_factory=_current_utc_timestamp)
    DateEdited: Optional[str] = Field(default_factory=_current_utc_timestamp)
    Editors: Optional[str]
    Publisher: Optional[str]
    City: Optional[str]
    DupString: Optional[str]
    TypeofReportID: Optional[int]
    PublicationTypeID: int
    Edition: Optional[str]
    Medium: Optional[str]
    StudyDesign: Optional[str]
    DOI: Optional[str]
    UDef3: Optional[str]
    ISBN: Optional[str]
    UDef5: Optional[str]
    PMID: Optional[str]
    TrialRegistrationID: Optional[str]
    UDef9 : Optional[float]
    UDef10: Optional[float]
    UDef8: Optional[float]
    
    #PDFLinks: Optional[str] = Field(default=None, sa_column=None)
    __table_args__ = (
        Index('idx_report_dateentered', 'Dateentered'),  # For date filtering
        Index('idx_report_report_number', 'ReportNumber'),  # For PDF lookups
        Index('idx_report_trial_id', 'TrialRegistrationID'),  # For trial ID searches
    )

class Study(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblStudy"

    CENTRALStudyID: Optional[int] = 0
    CRGStudyID: int = Field(primary_key=True)
    ShortName: str
    StatusofStudy: str
    TrialistContactDetails: Optional[str]
    CENTRALSubmissionStatus: Optional[str]
    Notes: Optional[str]
    DateEntered: str
    DateToCENTRAL: Optional[str]
    DateEdited: Optional[str]
    Search_Tagged: Optional[int]
    NumberParticipants: Optional[str]
    Countries: Optional[str]
    Duration: Optional[str]
    UDef4: Optional[str]
    Comparison: Optional[str]
    ISRCTN: Optional[str]
    UDef6: Optional[str]
    TrialRegistrationID: Optional[str]

    __table_args__ = (
        Index('idx_study_dateentered', 'DateEntered'),  # For cutoff filtering
        Index('idx_study_shortname', 'ShortName'),  # For trial ID matching
        Index('idx_study_trial_id', 'TrialRegistrationID'),  # For trial ID lookups
    )

class StudyReport(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblStudyReport"

    StudyReportID: int = Field(primary_key=True)
    CRGStudyID: int = Field(foreign_key="tblStudy.CRGStudyID", ondelete="CASCADE")
    CRGReportID: int = Field(foreign_key="tblReport.CRGReportID", ondelete="CASCADE")

    __table_args__ = (
        Index('idx_studyreport_report', 'CRGReportID'),  # For report->studies lookups
        Index('idx_studyreport_study', 'CRGStudyID'),  # For study->reports lookups
        Index('uq_studyreport_report_study', 'CRGReportID', 'CRGStudyID', unique=True),  # Prevent duplicate links
    )

class Participant(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblParticipant"

    ParticipantsID: int = Field(primary_key=True)
    ParticipantDescription: str

class StudyParticipant(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblStudyParticipant"

    CRGStudyID: int = Field(primary_key=True, foreign_key="tblStudy.CRGStudyID", ondelete="CASCADE")
    ParticipantsID: int = Field(primary_key=True, foreign_key="tblParticipant.ParticipantsID", ondelete="CASCADE")

class Design(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblDesign"

    DesignID: int = Field(primary_key=True)
    DesignDescription: Optional[str] = None

class StudyDesign(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblStudyDesign"

    CRGStudyID: int = Field(primary_key=True, foreign_key="tblStudy.CRGStudyID", ondelete="CASCADE")
    DesignID: int = Field(primary_key=True, foreign_key="tblDesign.DesignID", ondelete="CASCADE")

class Intervention(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblIntervention"

    InterventionID: int = Field(primary_key=True)
    InterventionDescription: Optional[str] = None

class StudyIntervention(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblStudyIntervention"

    CRGStudyID: int = Field(primary_key=True, foreign_key="tblStudy.CRGStudyID", ondelete="CASCADE")
    InterventionID: int = Field(primary_key=True, foreign_key="tblIntervention.InterventionID", ondelete="CASCADE")

class Condition(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblHealthCareCondition"

    HealthCareConditionID: int = Field(primary_key=True)
    HealthCareConditionDescription: Optional[str] = None

class StudyCondition(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblStudyHealthCareCondition"

    CRGStudyID: int = Field(primary_key=True, foreign_key="tblStudy.CRGStudyID", ondelete="CASCADE")
    HealthCareConditionID: int = Field(primary_key=True, foreign_key="tblHealthCareCondition.HealthCareConditionID", ondelete="CASCADE")

class Outcome(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblOutcome"

    OutcomeID: int = Field(primary_key=True)
    OutcomeDescription: Optional[str] = None

class StudyOutcome(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblStudyOutcome"

    CRGStudyID: int = Field(primary_key=True, foreign_key="tblStudy.CRGStudyID", ondelete="CASCADE")
    OutcomeID: int = Field(primary_key=True, foreign_key="tblOutcome.OutcomeID", ondelete="CASCADE")

class Project(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblBatch"

    BatchHash: str = Field(primary_key=True)
    BatchDescription: str
    DateCreated: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    UploadedBy: Optional[str]

class ProjectAssignees(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblBatchAssignees"

    BatchHash: str = Field(
        primary_key=True,
        foreign_key="tblBatch.BatchHash",
        ondelete="CASCADE",
    )
    Assignee: str = Field(primary_key=True)  # user_id

    __table_args__ = (
        Index("idx_batchassignees_assignee", "Assignee"),
    )

class FulltextExtractions(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblFulltextExtractions"

    CRGReportID: int = Field(primary_key=True, foreign_key="tblReport.CRGReportID", ondelete="CASCADE")
    data: Dict[str, Any] = Field(
        sa_column=Column(JSONB, nullable=False)
    )

class ReportAdded(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblReportAdded"

    CRGReportID: int = Field(primary_key=True, foreign_key="tblReport.CRGReportID", ondelete="CASCADE")
    BatchHash: str = Field(foreign_key="tblBatch.BatchHash", ondelete="CASCADE")
    AutoSearchedPdf: bool = Field(default=False, nullable=False)
    
    __table_args__ = (
        Index('idx_reportadded_batch_report', 'BatchHash', 'CRGReportID'),
    )

class ProjectInnerScore(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblBatchInnerScore"

    CRGReportID: int = Field(primary_key=True, foreign_key="tblReport.CRGReportID", ondelete="CASCADE")
    OtherID: int = Field(primary_key=True, foreign_key="tblReport.CRGReportID", ondelete="CASCADE")
    Score: float

    __table_args__ = (
        Index(
            "idx_batchinnerscore_report_score",
            "CRGReportID",
            "Score",
            postgresql_using="btree",
        ),
        Index(
            "idx_batchinnerscore_other_score",
            "OtherID",
            "Score",
            postgresql_using="btree",
        ),
    )

class StudyAdded(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblStudyAdded"

    CRGStudyID: int = Field(primary_key=True, foreign_key="tblStudy.CRGStudyID", ondelete="CASCADE")
    DateCreated: datetime.datetime = Field(default_factory=_current_utc_datetime)
    CreatedBy: Optional[str]

class StudyReportAdded(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblStudyReportAdded"

    StudyReportID: int = Field(primary_key=True, foreign_key="tblStudyReport.StudyReportID", ondelete="CASCADE")
    DateCreated: datetime.datetime = Field(default_factory=_current_utc_datetime)
    CreatedBy: str = Field(primary_key=True)
    Confirmed: bool = Field(default=False, nullable=False)

    __table_args__ = (
        Index('idx_studyreportadded_created_by', 'CreatedBy'),  # For user filtering
    )

class ReportFlag(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblReportFlag"

    CRGReportID: int = Field(primary_key=True, foreign_key="tblReport.CRGReportID", ondelete="CASCADE")
    CreatedBy: str = Field(primary_key=True)
    DateCreated: datetime.datetime = Field(default_factory=_current_utc_datetime)
    Message: str
    Public: bool = Field(default=False, nullable=False)

    __table_args__ = (
        Index('idx_reportflag_created_by', 'CreatedBy'),
    )

class AnalyticsEvent(SQLModel, table=True, metadata=metadata_resources):
    __tablename__ = "tblEvent"

    EventID: Optional[int] = Field(default=None, primary_key=True)
    DateCreated: datetime.datetime
    CreatedBy: str
    Type: str
    RelatedReport: Optional[int]