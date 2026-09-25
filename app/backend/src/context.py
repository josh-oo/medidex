"""Composition root: builds the repository/service object graph for one
caller (a REST request or an MCP tool/resource call), given just a DB session
and the caller's user id.

This is the single place that knows how repos/services are wired together.
Deliberately has no FastAPI import: FastAPI callers get a RequestContext via
`Depends(get_context)` (fastapi_app/deps.py, a thin adapter over this
file), while the MCP server - which isn't a FastAPI app and can't resolve a
`Depends(...)` graph - builds one directly (mcp_server/context.py). Either
way, both heads ask the same object for what they need instead of each
constructing repos/services by hand.
"""

from functools import cached_property
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .database.repositories.aspects import AspectRepository
from .database.repositories.project import ProjectRepository
from .database.repositories.report import ReportRepository
from .database.repositories.study import StudyRepository

from .services.aspects import TagScoringService, TagSimilaritySearchService
from .services.authors import AuthorFeatureService
from .services.core import RelatedTagSearchService, StudySimilaritySearchService
from .services.crawler import CrawlerService, DoclingService, OpenAlexService, crawler_service, docling_service, open_alex_service
from .services.embedding import EmbeddingService, embedding_service
from .services.linkage import LinkageService
from .services.llm import LanguageModelService
from .services.maintenance import MaintenanceService
from .services.pubsub import ProjectPubSubService
from .services.report import DocumentService, ReportService
from .services.study import StudyResourceService
from .services.vectorstore import VectorstoreService


class RequestContext:
    """Lazily builds and memoizes repos/services for one db session + user.

    Each property is a `cached_property`, so asking for the same repo/service
    twice on one RequestContext returns the same instance (mirroring FastAPI's
    own per-request Depends caching) without needing FastAPI to do it.
    """

    def __init__(self, db: AsyncSession, user_id: Optional[str]):
        self.db = db
        self.user_id = user_id

    # Repositories

    @cached_property
    def report_repo(self) -> ReportRepository:
        return ReportRepository(db=self.db, user_id=self.user_id)

    @cached_property
    def project_repo(self) -> ProjectRepository:
        return ProjectRepository(db=self.db, user_id=self.user_id)

    @cached_property
    def study_repo(self) -> StudyRepository:
        return StudyRepository(db=self.db, user_id=self.user_id)

    @cached_property
    def aspect_repo(self) -> AspectRepository:
        return AspectRepository(db=self.db)

    # Process-wide singletons (stateless, or hold a semaphore that's only
    # meaningful if shared - see services/embedding.py, services/crawler.py)

    @property
    def embedding_service(self) -> EmbeddingService:
        return embedding_service

    @property
    def crawler_service(self) -> CrawlerService:
        return crawler_service

    @property
    def docling_service(self) -> DoclingService:
        return docling_service

    @property
    def open_alex_service(self) -> OpenAlexService:
        return open_alex_service

    # Services

    @cached_property
    def vectorstore_service(self) -> VectorstoreService:
        return VectorstoreService(user_id=self.user_id, embedding_service=self.embedding_service)

    @cached_property
    def document_service(self) -> DocumentService:
        return DocumentService(
            report_repo=self.report_repo,
            crawler_service=self.crawler_service,
            docling_service=self.docling_service,
        )

    @cached_property
    def llm_service(self) -> LanguageModelService:
        return LanguageModelService(tag_similarity_service=self.tag_similarity_service)

    @cached_property
    def report_service(self) -> ReportService:
        return ReportService(
            report_repo=self.report_repo,
            study_repo=self.study_repo,
            document_service=self.document_service,
            llm_service=self.llm_service,
        )

    @cached_property
    def author_feature_service(self) -> AuthorFeatureService:
        return AuthorFeatureService(study_repo=self.study_repo)

    @cached_property
    def tag_similarity_service(self) -> TagSimilaritySearchService:
        return TagSimilaritySearchService(vectorstore=self.vectorstore_service)

    @cached_property
    def tag_scoring_service(self) -> TagScoringService:
        return TagScoringService(vectorstore=self.vectorstore_service, aspect_repo=self.aspect_repo)

    @cached_property
    def study_similarity_service(self) -> StudySimilaritySearchService:
        return StudySimilaritySearchService(
            user_id=self.user_id,
            vectorstore=self.vectorstore_service,
            study_repo=self.study_repo,
            project_repo=self.project_repo,
            author_feature_service=self.author_feature_service,
            report_service=self.report_service,
        )

    @cached_property
    def related_tag_service(self) -> RelatedTagSearchService:
        return RelatedTagSearchService(
            vectorstore=self.vectorstore_service,
            tag_scoring_service=self.tag_scoring_service,
            study_similarity_service=self.study_similarity_service,
            study_repo=self.study_repo,
        )

    @cached_property
    def linkage_service(self) -> LinkageService:
        return LinkageService(
            report_repo=self.report_repo,
            study_repo=self.study_repo,
            vectorstore=self.vectorstore_service,
        )

    @cached_property
    def pubsub_service(self) -> ProjectPubSubService:
        return ProjectPubSubService(project_repo=self.project_repo)

    @cached_property
    def maintenance_service(self) -> MaintenanceService:
        return MaintenanceService(report_repo=self.report_repo, vectorstore=self.vectorstore_service)

    @cached_property
    def study_service(self) -> StudyResourceService:
        return StudyResourceService(study_repo=self.study_repo)
