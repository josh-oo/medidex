from pydantic import BaseModel, Field
from typing import Mapping, Optional, List
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
        tag_data = tag if isinstance(tag, Mapping) else tag.model_dump()
        tag_id = tag_data.get("id")
        result.append(Tag(id=str(tag_id) if tag_id is not None else None, keyword=tag_data.get("description")))
    return result

def report_flag_to_dto(flag) -> ReportFlag:
    return ReportFlag(
        reportId=flag.report_id,
        createdBy=flag.created_by,
        message=flag.message,
        public=flag.public,
        createdAt=flag.date_created.isoformat(),
    )

def studies_to_dto(studies):
    result = []
    for study in studies:
        output_study = Study(
            studyId=study.id,
            shortName=study.short_name,
            numberParticipants=study.number_participants,
            duration=study.duration,
            comparison=study.comparison,
            countries=study.countries.split("//"),
            createdAt=study.date_entered,
            updatedAt=study.date_edited,
            status=study.status,
            trialId=study.trial_registration_id,
        )
        result.append(output_study)
    return result

def similar_studies_to_dto(studies):
    results = []
    for i in range(0, len(studies['Relevance'])):
        study = Study(
            studyId=studies['id'][i],
            shortName=studies['short_name'][i],
            numberParticipants=studies['number_participants'][i],
            duration=studies['duration'][i],
            comparison=studies['comparison'][i],
            countries=studies['countries'][i].split("//"),
            createdAt=studies['date_entered'][i],
            updatedAt=studies['date_edited'][i],
            status=studies['status'][i],
            trialId=studies['trial_registration_id'][i],
        )
        results.append(SimilarStudy(relevance=studies['Relevance'][i], study=study))
    return results