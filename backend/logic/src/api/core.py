from fastapi import APIRouter
from fastapi import Query, Path, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import List, Optional, Tuple, Set
import os
import logging

from ..utils.logger import setup_logging

import asyncio

import enum
from .auth import is_verified_api_call, is_admin, get_user_id

from ..database import get_study_repo, get_project_repo, get_report_repo

from ..database import StudyRepository
from ..database import ReportRepository
from ..database import ProjectRepository

from ..services import get_tag_similarity_service, TagSimilaritySearchService
from ..services import get_related_tag_service, RelatedTagSearchService
from ..services import get_study_similarity_service, StudySimilaritySearchService

from ..services import get_vectorstore_service, VectorstoreService

from ..services import get_embedding_service, EmbeddingService

from .resources import Study, StudyCreate, transform_to_output_studies

load_dotenv()

DEBUG = os.getenv("DEBUG", None) == "true"

setup_logging("events.log")
logger = logging.getLogger(__name__)

router = APIRouter(tags=["logic"])

cutoff_query = Query(None, description="Cutoff date: for example '2025-01-13 00:00:00' (do not retrieve items entered after that date). Usually only used for testing")

k_query = Query(10, description="Maximum number of returned results.")

# Track background tasks to prevent resource leaks
background_tasks: set = set()

class SimilarStudy(BaseModel):
    relevance: float
    study: Study

class TagResponse(BaseModel):
    id: str
    keyword: str
    relevance: str

class TagCategories(str, enum.Enum):
    default = 'default'
    interventions = 'interventions'
    conditions = 'conditions'
    outcomes = 'outcomes'
    participants = 'participants'

def transform_raw_similar_studies(studies):
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

async def get_vectorized_and_ready_report_ids(
    report_ids: List[int],
    report_repo: ReportRepository,
    vectorstore: VectorstoreService,
) -> Tuple[Set[int], Set[int]]:
    if not report_ids:
        return set(), set()

    vectorized_report_ids_raw, report_numbers = await asyncio.gather(
        vectorstore.reports_exist(report_ids),
        report_repo.get_report_numbers(report_ids),
    )
    embedded_report_ids = set(vectorized_report_ids_raw)
    pdf_ready_reports = {
        report_id
        for report_id, report_number in report_numbers.items()
        if report_number is not None and report_number >= 0
    }
    ready_report_ids = embedded_report_ids & pdf_ready_reports
    return embedded_report_ids, pdf_ready_reports, ready_report_ids

@router.get("/{tag_category}/{tag_value}/related-studies", dependencies=[Depends(is_verified_api_call)], summary="Get studies related to a specific tag (intervention, outcome, ...) currently only vector-similarity search is available.", description="Retrieve studies that are related to a specific tag value (e.g., 'Placebo' for interventions) using vector similarity search based on the embedding of the tag value. The similarity search is done at runtime.")
async def get_aspect_related_studies(tag_category: TagCategories = Path(..., description="The tags category (e.g. 'interventions', 'conditions', ...)"), tag_value: str = Path(..., description="The specific tags value (e.g. 'Placebo' for interventions)"), k : int = k_query, study_similarity_service : StudySimilaritySearchService = Depends(get_study_similarity_service), embedding_service : EmbeddingService = Depends(get_embedding_service)):
    embeddings = await embedding_service.embed_aspect(tag_value)

    aspect = tag_category
    aspect_mapping = {'interventions': 'intervention', 'conditions': 'condition', 'outcomes': 'outcome'}
    if tag_category in aspect_mapping.keys():
        aspect = aspect_mapping[tag_category]

    return await study_similarity_service.get_similar_study_by_query(embeddings['embedding'],aspect, None, k, [], [], [], return_details=False)

@router.get("/{tag_category}/{tag_value}/similar-tags", dependencies=[Depends(is_verified_api_call)], summary="Get related tags (interventions, outcomes, ...) for a specific report in a project based on its embedding vectors.")
async def similar_tags(tag_category: TagCategories =Path(..., description="The tags category (e.g. 'interventions', 'conditions', ...)"), tag_value : str = Path(..., description="The specific tags value (e.g. 'Placebo' for interventions)"), sources: List[str] = Query(..., description="Which source of tags do you want to search ('mesh', 'meerkat' or both)"), k : int = k_query, tag_similarity_service : TagSimilaritySearchService = Depends(get_tag_similarity_service)) -> List[TagResponse]:
    if tag_category == TagCategories.default:
        raise HTTPException(status_code=400, detail="No tags for 'default' embedding.")
    return await tag_similarity_service.get_similar_tags_by_string(tag_value, tag_category, sources, k)

@router.get("/reports/{report_id}/similar-studies", dependencies=[Depends(is_verified_api_call)], summary="")
async def similarity_search_studies_by_id(
    report_id: int,
    aspect: TagCategories = Query(TagCategories.default, description="This value is rarely needed. Just if you want to search studies based on a certain aspect."),
    cutoff: str = Query(None),
    k: int = Query(10),
    source: str = Query(None),
    negative_studies: List[int] = Query(None),
    negative_reports: List[int] = Query(None),
    return_details: bool = False,
    study_similarity_service: StudySimilaritySearchService = Depends(get_study_similarity_service),
    project_repo: ProjectRepository = Depends(get_project_repo),
    report_repo: ReportRepository = Depends(get_report_repo),
    vectorstore: VectorstoreService = Depends(get_vectorstore_service),
) -> List[SimilarStudy]:
    _,_, ready_report_ids = await get_vectorized_and_ready_report_ids(
        [report_id], report_repo, vectorstore
    )
    if report_id not in ready_report_ids:
        raise HTTPException(status_code=409, detail="Report is not ready for processing")

    if source is None:
        result = await study_similarity_service.get_similar_studies_by_id(
            report_id,
            aspect,
            cutoff,
            k,
            negative_studies,
            negative_reports,
            return_details,
        )
    else:
        project_id = await project_repo.get_project_id_by_report_id(report_id)
        if project_id != source:
            raise HTTPException(status_code=404, detail="Report not found in project")

        result = await study_similarity_service.get_similar_studies_by_id(
            report_id,
            aspect,
            cutoff,
            k,
            negative_studies,
            negative_reports,
            return_details,
        )
    studies = transform_raw_similar_studies(result)
    return studies

@router.get("/reports/{report_id}/similar-studies/tags", dependencies=[Depends(is_verified_api_call)], summary="")
async def search_related_tags(report_id: int, aspect: TagCategories = Query(TagCategories.interventions, description="The tag category which you are interested in"), cutoff: str = Query(None), k : int = Query(..., description="The number of related studies considered for retrieving relevant tags."), related_tag_service : RelatedTagSearchService = Depends(get_related_tag_service)):
    if aspect not in [TagCategories.interventions, TagCategories.conditions, TagCategories.outcomes]:
         raise HTTPException(status_code=501, detail="Not implemented")
    return await related_tag_service.search_related_tags_by_report_id(report_id, aspect, k, cutoff)

@router.put("/reports/{report_id}/studies/{study_id}", dependencies=[Depends(is_verified_api_call)], summary="Assign studies to a specific report in a project.", status_code=200)
async def assign_studies(report_id : int, study_id: int, report_repo : ReportRepository = Depends(get_report_repo), user_id: Optional[str] = Depends(get_user_id), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    #TODO get corresponding project and check access rights
    await asyncio.gather(
        report_repo.append_study_link(report_id, study_id),
        vectorstore.link_report_to_study_id(report_id, study_id, user_id)
    )

    #await publish_project_update(project_id)
    
    payload = {"user": user_id, "event_type": "study::links::changed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)

@router.delete("/reports/{report_id}/studies/{study_id}", dependencies=[Depends(is_verified_api_call)], summary="Remove assigned studies from a specific report.", status_code=200)
async def delete_assigned_studies(report_id : int, study_id: int, report_repo : ReportRepository = Depends(get_report_repo), user_id: Optional[str] = Depends(get_user_id), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    #TODO get corresponding project and check access rights

    await asyncio.gather(
        report_repo.unlink_studies(report_id, study_id),
        vectorstore.unlink_report_from_study_id(report_id, study_id, user_id)
    )

    #await publish_project_update(project_id)

    payload = {"user": user_id, "event_type": "study::links::changed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)

@router.post("/reports/{report_id}/studies", dependencies=[Depends(is_verified_api_call)], summary="Remove assigned studies from a specific report.", status_code=200)
async def link_to_new_study(report_id : int, study: StudyCreate, report_repo : ReportRepository = Depends(get_report_repo), study_repo : StudyRepository = Depends(get_study_repo), user_id: Optional[str] = Depends(get_user_id), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    #TODO get corresponding project and check access rights
    new_study = await study_repo.add_study(short_name=study.shortName, study_status=study.status, countries=study.countries, duration =study.duration, number_of_participants = study.numberParticipants, comparison = study.comparison)
    study_id = new_study.CRGStudyID

    #TODO if already dailed stop here

    await asyncio.gather(
        report_repo.append_study_link(report_id, study_id),
        vectorstore.link_report_to_study_id(report_id, study_id, user_id)
    )

    #TODO orphan removal -> return error if needed

    #await publish_project_update(project_id)
    
    payload = {"user": user_id, "event_type": "study::links::changed::new", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    output_study = transform_to_output_studies([new_study])[0]

    return output_study

@router.put("/reports/{report_id}/studies/{study_id}/confirmation", dependencies=[Depends(is_admin)], summary="After reviewing the annotations the admin uses this endpoint to confirm that the report belongs to the study.", status_code=200)
async def confirm_report_study_link(report_id : int, study_id: int, report_repo : ReportRepository = Depends(get_report_repo), project_repo: ProjectRepository = Depends(get_project_repo), user_id: Optional[str] = Depends(get_user_id), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    project_id = await project_repo.get_project_id_by_report_id(report_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="Report not found in project")

    project = await project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=403, detail="You can only confirm links for reports in your own projects")

    updated = await report_repo.set_study_report_confirmation(report_id, study_id, True)
    if not updated:
        raise HTTPException(status_code=404, detail="Tracked report-study link not found")

    payload = {"user": user_id, "event_type": "study::links::confirmed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)

@router.delete("/reports/{report_id}/studies/{study_id}/confirmation", dependencies=[Depends(is_admin)], summary="After reviewing the annotations the admin uses this endpoint to confirm that the report belongs to the study.", status_code=200)
async def unconfirm_report_study_link(report_id : int, study_id: int, report_repo : ReportRepository = Depends(get_report_repo), project_repo: ProjectRepository = Depends(get_project_repo), user_id: Optional[str] = Depends(get_user_id), vectorstore: VectorstoreService = Depends(get_vectorstore_service)):
    project_id = await project_repo.get_project_id_by_report_id(report_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="Report not found in project")

    project = await project_repo.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=403, detail="You can only confirm links for reports in your own projects")

    updated = await report_repo.set_study_report_confirmation(report_id, study_id, False)
    if not updated:
        raise HTTPException(status_code=404, detail="Tracked report-study link not found")

    payload = {"user": user_id, "event_type": "study::links::unconfirmed", "report_id": report_id, "original_timestamp": "-"}
    logger.info("ReportInteraction", extra={"payload": payload})

    return Response(content=None, status_code=200)