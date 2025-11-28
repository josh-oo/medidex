from sqlmodel import SQLModel, Field
from pydantic import EmailStr
from typing import Optional
import datetime

"""
Resources
"""

class Report(SQLModel, table=True):
    __tablename__ = "tblReport"

    CENTRALReportID: Optional[int]
    CRGReportID: int = Field(primary_key=True)
    Title: str
    Notes: Optional[str]
    ReportNumber: int
    OriginalTitle: Optional[str]
    Authors: str
    Journal: str
    Year: int
    Volume: Optional[int]
    Issue: Optional[str]
    Pages: Optional[str]
    Language: Optional[str]
    Abstract: Optional[str]
    CENTRALSubmissionStatus : Optional[str]
    CopyStatus: Optional[str]
    DatetoCENTRAL: Optional[str]
    Dateentered: str
    DateEdited: Optional[str]
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
    UDef9 : Optional[str]
    UDef10: Optional[str]
    UDef8: Optional[str]
    
    #PDFLinks: Optional[str] = Field(default=None, sa_column=None)

class Study(SQLModel, table=True):
    __tablename__ = "tblStudy"

    CENTRALStudyID: Optional[int]
    CRGStudyID: int = Field(primary_key=True)
    ShortName: str
    StatusofStudy: str
    TrialistContactDetails: Optional[str]
    CENTRALSubmissionStatus: Optional[str]
    Notes: Optional[str]
    DateEntered: str
    DateToCENTRAL: Optional[str]
    DateEdited: Optional[str]
    Search_Tagged: Optional[bool]
    NumberParticipants: Optional[str]
    Countries: Optional[str]
    Duration: Optional[str]
    UDef4: Optional[str]
    Comparison: Optional[str]
    ISRCTN: Optional[str]
    UDef6: Optional[str]
    TrialRegistrationID: Optional[str]

class StudyReport(SQLModel, table=True):
    __tablename__ = "tblStudyReport"

    StudyReportID: int = Field(primary_key=True)
    CRGStudyID: int 
    CRGReportID: int

class Participant(SQLModel, table=True):
    __tablename__ = "tblParticipant"

    ParticipantsID: int = Field(primary_key=True)
    ParticipantDescription: str

class StudyParticipant(SQLModel, table=True):
    __tablename__ = "tblStudyParticipant"

    CRGStudyID: int = Field(primary_key=True)
    ParticipantsID: int = Field(primary_key=True)

class Design(SQLModel, table=True):
    __tablename__ = "tblDesign"

    DesignID: int = Field(primary_key=True)
    DesignDescription: Optional[str] = None

class StudyDesign(SQLModel, table=True):
    __tablename__ = "tblStudyDesign"

    CRGStudyID: int = Field(primary_key=True)
    DesignID: int = Field(primary_key=True)

class Intervention(SQLModel, table=True):
    __tablename__ = "tblIntervention"

    InterventionID: int = Field(primary_key=True)
    InterventionDescription: Optional[str] = None

class StudyIntervention(SQLModel, table=True):
    __tablename__ = "tblStudyIntervention"

    CRGStudyID: int = Field(primary_key=True)
    InterventionID: int = Field(primary_key=True)

class Condition(SQLModel, table=True):
    __tablename__ = "tblHealthCareCondition"

    HealthCareConditionID: int = Field(primary_key=True)
    HealthCareConditionDescription: Optional[str] = None

class StudyCondition(SQLModel, table=True):
    __tablename__ = "tblStudyHealthCareCondition"

    CRGStudyID: int = Field(primary_key=True)
    HealthCareConditionID: int = Field(primary_key=True)

class Outcome(SQLModel, table=True):
    __tablename__ = "tblOutcome"

    OutcomeID: int = Field(primary_key=True)
    OutcomeDescription: Optional[str] = None

class StudyOutcome(SQLModel, table=True):
    __tablename__ = "tblStudyOutcome"

    CRGStudyID: int = Field(primary_key=True)
    OutcomeID: int = Field(primary_key=True)


"""
Authentication
"""

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int = Field(default=None, primary_key=True)
    email: EmailStr = Field(index=True, unique=True)
    role: str = Field(default="user")
    verified: bool = Field(default=False)
    password: str

class APIKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: str = Field(primary_key=True, index=True)
    owner: int = Field(foreign_key="users.id")
    hash: str = Field(index=True)


"""
User Data
"""

class TmpReportBatch(SQLModel, table=True):
    __tablename__ = "tmp_report_batches"

    batch_hash: str = Field(primary_key=True)
    batch_description: Optional[str]
    number_reports: Optional[int]
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)

class TmpReport(SQLModel, table=True):
    __tablename__ = "tmp_reports"

    batch_hash: str = Field(primary_key=True)
    batch_inner_id: int = Field(primary_key=True)
    title: Optional[str] #TI
    abstract: Optional[str] #AB
    authors: Optional[str]  #AU
    year: Optional[int] #pY
    report_number: Optional[int] #RN
    journal: Optional[str] #T2
    pages: Optional[str] #SP
    place: Optional[str] #CY
    language: Optional[str] #LA
    issue: Optional[str] #M1
    volume: Optional[str] #VL
    doi: Optional[str] #DO
    trial_id: Optional[str] #derived from title/abstract/authors
    vectors: Optional[bytes]  # pickled vectors
    assigned_studies: Optional[str]  # JSON-encoded list