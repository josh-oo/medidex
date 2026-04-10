from fastapi import Depends, Path, HTTPException, Query
from langchain_openai import ChatOpenAI

from .vectorstore import VectorstoreService
from .aspects import TagScoringService, TagSimilaritySearchService
from .core import RelatedTagSearchService, StudySimilaritySearchService
from .authors import AuthorFeatureService
from .embedding import EmbeddingService
from .agent import AgentContext, AgentService
from .report import DocumentService, ReportService
from .llm import LanguageModelService
from .crawler import CrawlerService, DoclingService
from .maintenance import MaintenanceService

from ..database import get_aspect_repo, get_report_repo, get_study_repo, get_project_repo

from ..database.repositories.study import StudyRepository
from ..database.repositories.aspects import AspectRepository
from ..database.repositories.report import ReportRepository
from ..database.repositories.project import ProjectRepository

from ..api.auth import get_user_id

async def project_path_to_report_id(project_id: str = Path(...), report_index: int = Path(...),  project_repo: ProjectRepository = Depends(get_project_repo)) -> int:
    result = await project_repo.project_item_to_report_id(project_id, report_index)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Project item not found")
    return result

def get_embedding_service():
    return EmbeddingService()

def get_vectorstore_service(user_id : str = Depends(get_user_id), embedding_service : EmbeddingService = Depends(get_embedding_service)):
    return VectorstoreService(user_id=user_id, embedding_service=embedding_service)

def get_author_feature_service(study_repo : StudyRepository = Depends(get_study_repo)) -> AuthorFeatureService:
    return AuthorFeatureService(study_repo=study_repo)

def get_tag_similarity_service(vectorstore : VectorstoreService = Depends(get_vectorstore_service)) -> TagSimilaritySearchService:
    return TagSimilaritySearchService(vectorstore=vectorstore)

def get_tag_scoring_service(aspect_repo : AspectRepository = Depends(get_aspect_repo), vectorstore : VectorstoreService = Depends(get_vectorstore_service)) -> TagScoringService:
    return TagScoringService(vectorstore=vectorstore, aspect_repo=aspect_repo)

def get_document_service(report_id : int, report_repo : ReportRepository = Depends(get_report_repo)) -> DocumentService:
    return DocumentService(report_id=report_id, report_repo=report_repo, crawler_service=CrawlerService(), docling_service=DoclingService())

def get_document_service_project(report_id : int = Depends(project_path_to_report_id), report_repo : ReportRepository = Depends(get_report_repo)) -> DocumentService:
    return DocumentService(report_id=report_id, report_repo=report_repo, crawler_service=CrawlerService(), docling_service=DoclingService())

def get_llm_service(tag_similarity_service : TagSimilaritySearchService = Depends(get_tag_similarity_service)) -> LanguageModelService:
    return LanguageModelService(tag_similarity_service=tag_similarity_service)

def get_report_service_project(report_id : int = Depends(project_path_to_report_id), report_repo : ReportRepository = Depends(get_report_repo), study_repo : StudyRepository = Depends(get_study_repo),document_service : DocumentService = Depends(get_document_service_project), llm_service : LanguageModelService = Depends(get_llm_service)) -> ReportService:
    return ReportService(report_id=report_id, report_repo=report_repo, study_repo=study_repo, document_service=document_service, llm_service=llm_service )

def get_report_service(report_id : int, report_repo : ReportRepository = Depends(get_report_repo), study_repo : StudyRepository = Depends(get_study_repo),document_service : DocumentService = Depends(get_document_service), llm_service : LanguageModelService = Depends(get_llm_service)) -> ReportService:
    return ReportService(report_id=report_id, report_repo=report_repo, study_repo=study_repo, document_service=document_service, llm_service=llm_service )

def get_study_similarity_service(user_id : str = Depends(get_user_id), study_repo : StudyRepository = Depends(get_study_repo), project_repo : ProjectRepository = Depends(get_project_repo), author_feature_service : AuthorFeatureService = Depends(get_author_feature_service), vectorstore : VectorstoreService = Depends(get_vectorstore_service), report_service : ReportService = Depends(get_report_service)) -> StudySimilaritySearchService:
    return StudySimilaritySearchService(user_id=user_id, vectorstore=vectorstore, study_repo=study_repo, project_repo=project_repo, author_feature_service=author_feature_service, report_service=report_service)

def get_study_similarity_service_project(user_id : str = Depends(get_user_id), study_repo : StudyRepository = Depends(get_study_repo), project_repo : ProjectRepository = Depends(get_project_repo), author_feature_service : AuthorFeatureService = Depends(get_author_feature_service), vectorstore : VectorstoreService = Depends(get_vectorstore_service), report_service : ReportService = Depends(get_report_service_project)) -> StudySimilaritySearchService:
    return StudySimilaritySearchService(user_id=user_id, vectorstore=vectorstore, study_repo=study_repo, project_repo=project_repo, author_feature_service=author_feature_service, report_service=report_service)

def get_related_tag_service(tag_scoring_service : TagScoringService = Depends(get_tag_scoring_service), study_similarity_service : StudySimilaritySearchService = Depends(get_study_similarity_service), study_repo : StudyRepository = Depends(get_study_repo), vectorstore : VectorstoreService = Depends(get_vectorstore_service)) -> RelatedTagSearchService:
    return RelatedTagSearchService(vectorstore=vectorstore, tag_scoring_service=tag_scoring_service, study_similarity_service=study_similarity_service, study_repo=study_repo)

def get_maintenance_service(report_repo : ReportRepository = Depends(get_report_repo), vectorstore : VectorstoreService = Depends(get_vectorstore_service)) -> RelatedTagSearchService:
    return MaintenanceService(report_repo=report_repo, vectorstore=vectorstore)

def get_agent_service(
    report_id : int,
    model: str = Query("gpt-5-nano", description="LLM model name to use for study prediction"),
    report_repo : ReportRepository = Depends(get_report_repo),
    study_repo : StudyRepository = Depends(get_study_repo),
    study_similarity_service : StudySimilaritySearchService = Depends(get_study_similarity_service),
) -> AgentService:
    return AgentService(
        report_id=report_id,
        report_repo=report_repo,
        study_repo=study_repo,
        study_similarity_service=study_similarity_service,
        model=model,
    )