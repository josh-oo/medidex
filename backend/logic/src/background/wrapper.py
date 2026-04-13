from typing import List

from ..database import ReportRepository, ProjectRepository, StudyRepository
from ..database.sessions import AsyncSessionLocal
from ..database.models import Report as DbReport
from ..services.aspects import TagSimilaritySearchService
from ..services.authors import AuthorFeatureService
from ..services.crawler import CrawlerService, DoclingService
from ..services.embedding import EmbeddingService
from ..services.llm import LanguageModelService
from ..services.report import DocumentService, ReportService
from ..services.core import StudySimilaritySearchService
from ..services.linkage import LinkageService
from ..services.vectorstore import VectorstoreService
from ..services.maintenance import MaintenanceService
from ..services.pubsub import ProjectPubSubService
from ..services.agent import AutomationService
from ..utils.llm.agent import get_checkpointer


async def run_process_report_background(
    project_id: str,
    report_ids: List[int],
    user_id: str,
    process_report,
) -> None:
    async with AsyncSessionLocal() as db:
        project_repo = ProjectRepository(db=db, user_id=user_id)
        report_repo = ReportRepository(db=db, user_id=user_id)
        embedding_service = EmbeddingService()
        vectorstore = VectorstoreService(user_id=user_id, embedding_service=embedding_service)
        maintenance_service = MaintenanceService(report_repo=report_repo, vectorstore=vectorstore)
        pubsub_service = ProjectPubSubService(project_repo=project_repo)

        reports: List[DbReport] = []
        for report_id in report_ids:
            report = await report_repo.get_report_by_id(report_id)
            if report is not None:
                reports.append(report)

        await process_report(reports, project_id, project_repo, vectorstore, maintenance_service, pubsub_service)


async def run_start_automation_background(
    project_id: str,
    user_id: str,
    model: str,
    start_automation,
) -> None:
    async with AsyncSessionLocal() as db:
        project_repo = ProjectRepository(db=db, user_id=user_id)
        report_repo = ReportRepository(db=db, user_id=user_id)
        study_repo = StudyRepository(db=db, user_id=user_id)
        embedding_service = EmbeddingService()
        vectorstore = VectorstoreService(user_id=user_id, embedding_service=embedding_service)
        tag_similarity_service = TagSimilaritySearchService(vectorstore=vectorstore)
        llm_service = LanguageModelService(tag_similarity_service=tag_similarity_service)
        document_service = DocumentService(
            report_repo=report_repo,
            crawler_service=CrawlerService(),
            docling_service=DoclingService(),
        )
        report_service = ReportService(
            report_repo=report_repo,
            study_repo=study_repo,
            document_service=document_service,
            llm_service=llm_service,
        )
        author_feature_service = AuthorFeatureService(study_repo=study_repo)
        study_similarity_service = StudySimilaritySearchService(
            user_id=user_id,
            vectorstore=vectorstore,
            study_repo=study_repo,
            project_repo=project_repo,
            author_feature_service=author_feature_service,
            report_service=report_service,
        )
        linkage_service = LinkageService(
            report_repo=report_repo,
            study_repo=study_repo,
            vectorstore=vectorstore,
        )
        pubsub_service = ProjectPubSubService(project_repo=project_repo)

        async for checkpointer in get_checkpointer():
            agent_service = AutomationService(
                user_id=user_id,
                report_repo=report_repo,
                study_repo=study_repo,
                document_service=document_service,
                study_similarity_service=study_similarity_service,
                checkpointer=checkpointer,
                model=model,
            )
            await start_automation(
                project_id,
                project_repo,
                report_repo,
                vectorstore,
                linkage_service,
                agent_service,
                pubsub_service,
            )
            break