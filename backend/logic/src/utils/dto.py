from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

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

class SimilarStudy(BaseModel):
    relevance: float
    study: Study

class Tag(BaseModel):
    id: str
    keyword: str
    relevance: Optional[float] = None

class ReportSources(BaseModel):
    doi: str
    links: List[str]

class Report(BaseModel):
    reportId: int
    year: int 
    title: str
    abstract: Optional[str]
    trialId: Optional[str]
    authors: List[str]
    createdAt: Optional[str]
    updatedAt: Optional[str]

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

class BatchedReport(BaseModel):
    report: Report
    hasPdf: Optional[bool]
    flag: Optional[str]
    assignedStudies: List[Study] = Field(default_factory=list)

def tags_to_dto(tags) -> List[Tag]:
    result = []
    for tag in tags:
        name = None
        tag_id = None
        for key, value in tag.model_dump().items():
            if "ID" in key:
                tag_id = str(value)
            elif "Description" in key:
                name = value
        result.append(Tag(id=tag_id,keyword=name))
    return result

def report_flag_to_dto(flag) -> ReportFlag:
    return ReportFlag(
        reportId=flag.CRGReportID,
        createdBy=flag.CreatedBy,
        message=flag.Message,
        public=flag.Public,
        createdAt=flag.DateCreated.isoformat(),
    )

def studies_to_dto(studies):
    result = []
    for study in studies:
        output_study = Study(
            studyId=study.CRGStudyID,
            shortName=study.ShortName,
            numberParticipants=study.NumberParticipants,
            duration=study.Duration,
            comparison=study.Comparison,
            countries=study.Countries.split("//"),
            createdAt=study.DateEntered,
            updatedAt=study.DateEdited,
            status=study.StatusofStudy,
            trialId=study.ISRCTN,
        )
        result.append(output_study)
    return result

def similar_studies_to_dto(studies):
    results = []
    for i in range(0, len(studies['Relevance'])):
        study = Study(
            studyId=studies['CRGStudyID'][i],
            shortName=studies['ShortName'][i],
            numberParticipants=studies['NumberParticipants'][i],
            duration=studies['Duration'][i],
            comparison=studies['Comparison'][i],
            countries=studies['Countries'][i].split("//"),
            createdAt=studies['DateEntered'][i],
            updatedAt=studies['DateEdited'][i],
            status=studies['StatusofStudy'][i],
            trialId=studies['ISRCTN'][i],
        )
        results.append(SimilarStudy(relevance=studies['Relevance'][i], study=study))
    return results