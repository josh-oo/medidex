from fastapi import APIRouter
from fastapi import Query, Depends
import httpx
import os

from .auth import is_verified
from typing import List, Optional

from pydantic import BaseModel

router = APIRouter(tags=["resources"])

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT")

class FulltextLink(BaseModel):
    report_id: int
    link: str

class ReportData(BaseModel):
    CENTRALReportID: Optional[int]
    CRGReportID: int
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
    CENTRALSubmissionStatus : Optional[str] = None
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
    UDef9 : Optional[str] = None
    UDef10: Optional[str] = None
    UDef8: Optional[str] = None
    PDFLinks: str

@router.get("/studies/{study_id}/reports", dependencies=[Depends(is_verified)], summary="Get all reports (and corresponding data) already belonging to this study")
def get_all_reports_by_study(study_id: int) -> List[ReportData]:
    url = f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/{study_id}/reports"
    with httpx.Client() as client:
        response = client.get(url)
        response.raise_for_status()  # Optional: raises on 4xx/5xx
        data = response.json()
    report_ids = [item['CRGReportID'] for item in data]#data['CRGReportID']

    url = f"http://{DATABASE_HOST}:{DATABASE_PORT}/report/pdf_links"
    with httpx.Client() as client:
        response = client.get(url, params={"report_ids": report_ids} if report_ids else None)
        response.raise_for_status()  # Optional: raises on 4xx/5xx
        pdf_links = response.json()

    for i in range(0, len(data)):
        key = str(data[i]['CRGReportID'])
        if key in pdf_links.keys():
            data[i]['PDFLinks'] = pdf_links[key]
        else:
            data[i]['PDFLinks'] = None

    return data

@router.get("/studies/{study_id}/reports/pdf_links", dependencies=[Depends(is_verified)], summary="Get all links to all fulltext pdfs belonging to this study")
def get_pdf_links_by_study(study_id: int) -> List[FulltextLink]:
    url = f"http://{DATABASE_HOST}:{DATABASE_PORT}/study/{study_id}/reports"
    with httpx.Client() as client:
        response = client.get(url)
        response.raise_for_status()  # Optional: raises on 4xx/5xx
        data = response.json()
    report_ids = [item['CRGReportID'] for item in data]#data['CRGReportID']
    
    url = f"http://{DATABASE_HOST}:{DATABASE_PORT}/report/pdf_links"
    with httpx.Client() as client:
        response = client.get(url, params={"report_ids": report_ids})
        response.raise_for_status()  # Optional: raises on 4xx/5xx
        data = response.json()

    result = [{"report_id": k, "link": v} for k, v in data.items()]
    return result


@router.get("/reports/{report_id}/pdf_link", dependencies=[Depends(is_verified)], summary="Get the link to the fulltext pdf for a given report")
def get_pdf_link_by_reports(report_id: int) -> str:
    url = f"http://{DATABASE_HOST}:{DATABASE_PORT}/report/pdf_links"
    with httpx.Client() as client:
        response = client.get(url, params={"report_ids": [report_id]} if report_id else None)
        response.raise_for_status()  # Optional: raises on 4xx/5xx
        return response.json()[str(report_id)]