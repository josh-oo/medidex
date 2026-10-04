import asyncio
from typing import List, Dict

import pypdf

from ..utils.trial_registration_id import extract_trial_ids_from_text
from ..database import StudyRepository, ReportRepository
from ..database.repositories.report import Report

import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
PDF_PATH = os.path.join(DATABASE_VOLUME,"resources", "pdfs")
PLACEHOLDER_PDF_PATH = os.getenv("PLACEHOLDER_PDF_PATH", "/app/placeholder.pdf")

class DocumentService:

    def __init__(self, report_repo : ReportRepository):
        self.path_cache = {}
        self.pages_cache = {}
        self.report_repo = report_repo

    async def get_path(self, report_id: int, mkdirs=False):
        if report_id not in self.path_cache:
            report_number = await self.report_repo.get_pdf_numbers_by_report_id(report_id)
            if report_number is None:
                raise Exception("Report not found")
            if not mkdirs and report_number == -1:
                raise Exception("Report number not found")   
            if report_number <= 0 and mkdirs:
                report_number = await self.report_repo.assign_pdf_numbers_for_report_id(report_id)
            
            pdf_name = str(report_number).zfill(5) + ".pdf"
            file_name = os.path.join(PDF_PATH, pdf_name)
            if report_number == 0 and not os.path.isfile(file_name):
                file_name = PLACEHOLDER_PDF_PATH

            self.path_cache[report_id] = file_name
        return self.path_cache[report_id]

    async def get_pages(self, report_id: int) -> List[str]:
        """Plain per-page text of the report's PDF (pypdf; no layout analysis or
        OCR), cached per report. Empty list when the PDF can't be parsed."""
        def _sync_extract(path):
            try:
                reader = pypdf.PdfReader(path)
                return [page.extract_text() or "" for page in reader.pages]
            except pypdf.errors.PyPdfError:
                return []
            except Exception as e:
                print(f"Error extracting text from PDF: {e}")
                return []
        if report_id not in self.pages_cache:
            try:
                path = await self.get_path(report_id)
                await self.report_repo.db.commit()
            except:
                await self.report_repo.db.rollback()
                raise
            self.pages_cache[report_id] = await asyncio.to_thread(_sync_extract, path)
        return self.pages_cache[report_id]

    async def find_registration_ids(self, report_id: int) -> List[str]:
        """Trial registration ids (NCT, ISRCTN, DRKS, ...) mentioned anywhere in
        the report's PDF, in order of first appearance."""
        pages = await self.get_pages(report_id)
        return await asyncio.to_thread(extract_trial_ids_from_text, "\n".join(pages))

    async def delete_pdf(self, report_id: int) -> Dict[str, object]:
        report = await self.report_repo.get_report_by_id(report_id)
        if not report:
            raise Exception("Report not found")

        deleted_pdf = False
        previous_report_number = report.report_number
        if previous_report_number is not None and previous_report_number > 0:
            pdf_name = str(previous_report_number).zfill(5) + ".pdf"
            pdf_path = os.path.join(PDF_PATH, pdf_name)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
                deleted_pdf = True

        # Reset the report number so future uploads are re-assigned cleanly.
        report.report_number = -1
        await self.report_repo.recompute_has_pdf(report_id)
        await self.report_repo.db.flush()
        await self.report_repo.db.commit()

        self.path_cache.pop(report_id, None)

        return {
            "report_id": report_id,
            "deleted_pdf": deleted_pdf,
            "previous_report_number": previous_report_number,
        }
    
    async def upload_pdf(self, report_id: int, file):

        if file is None:
            # Set report_number to 0 and stop
            report = await self.report_repo.get_report_by_id(report_id)
            if report:
                report.report_number = 0
                await self.report_repo.recompute_has_pdf(report_id)
                await self.report_repo.db.flush()
            return {"report_id": report_id, "file_path": None, "size_bytes": 0}

        path = None
        try:
            path = await self.get_path(report_id, mkdirs=True)

            with open(path, "wb") as f:
                content = await file.read()
                f.write(content)

            await self.report_repo.recompute_has_pdf(report_id)

            return {
                "report_id": report_id,
                "file_path": path,
                "size_bytes": len(content)
            }
        except Exception:
            self.path_cache.pop(report_id, None)
            if path and os.path.exists(path):
                os.remove(path)
            raise
        
class ReportService:
    def __init__(self, report_repo : ReportRepository, study_repo : StudyRepository, document_service : DocumentService, open_alex_service):
        self.report_repo = report_repo
        self.study_repo = study_repo

        self.document_service = document_service
        self.open_alex_service = open_alex_service

        self.report_cache = {}

    async def get_fulltext_links(self, report_id: int) -> List[str]:
        """OpenAlex fulltext links for a report's DOI. Normally just reads the cache
        the post-upload background job populates (report_added.fulltext_links - see
        ProjectRepository.set_report_auto_searched_pdf); falls back to a live OpenAlex
        lookup (and caches it) only for reports that cache predates - e.g. reports
        added before this field existed, or added outside the normal project-upload
        pipeline - so this is a live call at most once per report.
        """
        report_added = await self.report_repo.get_report_added(report_id)
        if report_added is not None and report_added.fulltext_links is not None:
            return report_added.fulltext_links

        report = await self.get_report(report_id)
        if report is None or not report.doi:
            return []

        links = list(await self.open_alex_service.get_pdf_links_by_doi(report.doi))
        if report_added is not None:
            await self.report_repo.set_fulltext_links(report_id, links)
        return links

    async def get_report(self, report_id: int) -> Report:
        if report_id not in self.report_cache:
            self.report_cache[report_id] = await self.report_repo.get_report_by_id(report_id)
        return self.report_cache[report_id]

    async def is_ready(self, report_id: int) -> bool:
        """Whether a report has finished both embedding and PDF processing (see
        ReportRepository.get_readiness_sets) - the same readiness definition
        ProjectResourceService.get_vectorized_and_ready_report_ids uses per-project,
        here for callers (e.g. StudySimilaritySearchService) that only have a
        single report id.
        """
        embedded, has_pdf = await self.report_repo.get_readiness_sets([report_id])
        return report_id in embedded and report_id in has_pdf

    