import fitz
import re
from rapidfuzz import fuzz

from typing import List, Dict

from ..utils.trial_registration_id import extract_trial_ids_from_text, extract_trial_id

from ..database import StudyRepository, ReportRepository
from ..database.repositories.report import Report

from .llm import LanguageModelService
from .crawler import CrawlerService, DoclingService

import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
PDF_PATH = os.path.join(DATABASE_VOLUME,"resources", "pdfs")
FULLTEXT_PATH = os.path.join(DATABASE_VOLUME,"resources", "fulltexts")

class DocumentService:

    def __init__(self, report_repo : ReportRepository, crawler_service : CrawlerService, docling_service : DoclingService):
        self.path_cache = {}
        self.pages_cache = {}
        self.report_repo = report_repo
        self.crawler_service = crawler_service
        self.docling_service = docling_service

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

            self.path_cache[report_id] = file_name
        return self.path_cache[report_id]

    async def get_pages(self, report_id: int) -> List[str]:
        def _sync_extract(path):
            try:
                doc = fitz.open(path)
                parts = []
                for page in doc:
                    parts.append(page.get_text() or "")
                doc.close()
                return parts
            except fitz.FileDataError:
                return []
            except Exception as e:
                print(f"Error extracting text from PDF: {e}")
                return []
        if report_id not in self.pages_cache:
            path = await self.get_path(report_id)
            self.pages_cache[report_id] = await asyncio.to_thread(_sync_extract, path)
        return self.pages_cache[report_id]
    
    async def is_trial_registration(self, report_id: int) -> bool:
        report = await self.report_repo.get_report_by_id(report_id)
        authors = report.Authors.split("//")
        if len(authors) != 1:
            return False
        trial_ids = extract_trial_id(None, None,authors)
        if trial_ids == authors:
            return True
        return False

    async def is_abstract_collection(self, report_id: int) -> bool:
        """
        gets pdf_file_path
        returns if it is an abstract collection and the number of pages
        """

        #a dict of suspicious abstract collection patterns and their corresponding "occurences per page"
        PATTERNS_PER_PAGE = {
                        r"\n[A-Z]\.\d\.[a-z]\.\d\d\d\s": 2,
                        r"\nPS\d\d-\d\d\d\n" : 2,
                        r"BIOL PSYCHIATRY [0-9][0-9][0-9][0-9].*S": 1,
                        r"ACNP [0-9][0-9][0-9][0-9] Annual Meeting": 1,
                        r"\nP[0-9]+\n" : 3,
                        r"\nO[0-9][0-9][A-Z]?\n": 3,
                        r"\nS-?[0-9][0-9]-?[0-9][0-9]\s": 2,
                        r"\n[A-Z]-[0-9][0-9]-[0-9][0-9][0-9]\s":2,
                        r"Talk\s[0-9]+\n":2,
                        r"Poster\s[0-9]+\n":2,
                        r"SIRS [0-9][0-9][0-9][0-9] Abstracts": 1,
                        r"\s[A-Z][0-9][0-9]\.[0-9][0-9]:?\s": 2,
                        r"\n[A-Z][A-Z_\W]*\n([A-Z]\.\s?)+ [A-Za-z]*(,|\n)": 2,
                        r"\n[A-Z][A-Z_\W]*\n[A-Z][A-Za-z-]+ ([A-Z]\. )*[A-Z][A-Za-z-]+," : 2,
                        r"(?i)summary": 3,
                        r"(?i)references": 3,
                        r"(?i)CORRESPONDING":2,
                        r"Year.*Volume.*Issue.*Pages.*Abstract.*www.pdffactory.com": 1,
                        "doi:10.1016":2,
                        "Symposium of AGNP, Nuremberg": 0.85,
                        "International Conference on Early Psychosis":0.9,
                        "International Congress on Schizophrenia Research": 0.9,
                        "Abstracts of the _ Biennial Schizophrenia International Research Conference / Schizophrenia Research": 0.85,
                        "Abstracts for the": 0.9,
                        "CONFERENCE SUMMARY": 0.9,
                        "Chairman": 0.9,
                        #"www.nrr.nhs.uk":-1
                        }
                        #Not found:
                        #cleaned_Tarrier 1996 - The use of cognitive behaviour.pdf
                        #cleaned_Bell, Milstein et al. 1993 - Pay and participation in work.pdf
                        #cleaned_Matthews 1981 - The process and outcome.pdf (last two pages)
        
        found_words = []
        num_pages = 0
        pages = await self.get_pages(report_id)
        for page_text in pages:
            for key, threshold in PATTERNS_PER_PAGE.items():
                #look for all marker pattersn in the dict
                if threshold < 0: #just look for one occurence in the whole document
                    if key in page_text:
                        return True, len(pages)
                elif threshold > 0 and threshold < 1: #we can do fuzzy search in this case
                    ratio = fuzz.partial_ratio(key.lower(), page_text.lower())
                    if ratio > threshold * 100:
                        found_words.append(key)
                else:
                    pattern = re.compile(key)
                    results = pattern.findall(page_text)
                    if len(results) >= threshold:
                        found_words.append(key)
            num_pages += 1
        
        for key in PATTERNS_PER_PAGE.keys():
            #return true if the requirements are met on every second page:
            if found_words.count(key) > (num_pages-1)/2.0:
                return True
        return False
    
    async def get_fulltext(self, report_id: int, fast : bool) -> str:
        if fast:
            pages = await self.get_pages(report_id)
            return " ".join(pages)
        # Use report_id as the filename, zero-padded to 5 digits
        txt_name = str(report_id).zfill(5) + ".txt"
        txt_path = os.path.join(FULLTEXT_PATH, txt_name)

        # Try to read cached fulltext asynchronously
        if os.path.exists(txt_path):
            def _read_file(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            return await asyncio.to_thread(_read_file, txt_path)

        # Otherwise, generate the fulltext
        if await self.is_abstract_collection(report_id):
            text = ""
        elif await self.is_trial_registration(report_id):
            report = await self.report_repo.get_report_by_id(report_id)
            text = await self.crawler_service.get_html_for_trial_id(report.Authors)
        else:
            text = await self.docling_service.parse_pdf(await self.get_path(report_id))
            #pages = await self.get_pages()
            #text = " ".join(pages)

        # Ensure the directory exists
        os.makedirs(FULLTEXT_PATH, exist_ok=True)

        # Write the fulltext asynchronously
        def _write_file(path, content):
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        await asyncio.to_thread(_write_file, txt_path, text)

        return text
    
    def delete_fulltext(self, report_id: int):
        txt_name = str(report_id).zfill(5) + ".txt"
        txt_path = os.path.join(FULLTEXT_PATH, txt_name)
        if os.path.exists(txt_path):
            os.remove(txt_path)

    async def delete_pdf(self, report_id: int) -> Dict[str, object]:
        report = await self.report_repo.get_report_by_id(report_id)
        if not report:
            raise Exception("Report not found")

        deleted_pdf = False
        deleted_fulltext = False
        previous_report_number = report.ReportNumber
        if previous_report_number is not None and previous_report_number > 0:
            pdf_name = str(previous_report_number).zfill(5) + ".pdf"
            pdf_path = os.path.join(PDF_PATH, pdf_name)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
                deleted_pdf = True

        txt_name = str(report_id).zfill(5) + ".txt"
        txt_path = os.path.join(FULLTEXT_PATH, txt_name)
        deleted_fulltext = os.path.exists(txt_path)

        # Clear derived artifacts and reset report number so future uploads are re-assigned cleanly.
        await asyncio.to_thread(self.delete_fulltext, report_id)
        report.ReportNumber = -1
        await self.report_repo.db.flush()
        await self.report_repo.db.commit()

        self.path_cache.pop(report_id, None)
        self.pages_cache.pop(report_id, None)

        return {
            "report_id": report_id,
            "deleted_pdf": deleted_pdf,
            "deleted_fulltext": deleted_fulltext,
            "previous_report_number": previous_report_number,
        }
    
    async def upload_pdf(self, report_id: int, file):
        async def _clear_report_number():
            report = await self.report_repo.get_report_by_id(report_id)
            if report:
                report.ReportNumber = -1
                await self.report_repo.db.flush()
                await self.report_repo.db.commit()
            self.path_cache.pop(report_id, None)
            self.pages_cache.pop(report_id, None)

        if file is None:
            # Set ReportNumber to 0 and stop
            report = await self.report_repo.get_report_by_id(report_id)
            if report:
                report.ReportNumber = 0
                await self.report_repo.db.flush()
                await self.report_repo.db.commit()
            return {"report_id": report_id, "file_path": None, "size_bytes": 0}

        path = None
        try:
            path = await self.get_path(report_id, mkdirs=True)

            with open(path, "wb") as f:
                content = await file.read()
                f.write(content)

            await asyncio.to_thread(self.delete_fulltext, report_id)
            await self.get_fulltext(report_id, fast=False)

            return {
                "report_id": report_id,
                "file_path": path,
                "size_bytes": len(content)
            }
        except Exception:
            await _clear_report_number()
            if path and os.path.exists(path):
                os.remove(path)
            raise
        
class ReportService:
    def __init__(self, report_repo : ReportRepository, study_repo : StudyRepository, document_service : DocumentService, llm_service : LanguageModelService):
        self.report_repo = report_repo
        self.study_repo = study_repo

        self.document_service = document_service
        self.llm_service = llm_service

        self.report_cache = {}

    async def get_trial_ids(self, report_id: int, include_fulltext: bool, use_cache : bool = True) -> List:
        if include_fulltext and use_cache:
            data = await self.report_repo.load_report_metadata(report_id)
            if data is not None and "trial_id" in data:
                return data["trial_id"]
        trial_ids = await self._get_trial_ids(report_id, include_fulltext)
        if include_fulltext and use_cache:
            await self.report_repo.save_report_metadata_field(report_id, "trial_id", trial_ids)
        return trial_ids

    async def _get_trial_ids(self, report_id: int, include_fulltext: bool) -> List[str]:
        """Internal function to get trial IDs from a report"""
        report = await self.get_report(report_id)
        if not report:
            return None
        
        if include_fulltext:
            try:
                text = await self.document_service.get_fulltext(report_id, fast=True)
                return extract_trial_ids_from_text(text)
            except:
                pass
        
        authors = [item.strip() for item in report.Authors.split("//")]
        all_ids = extract_trial_id(report.Title, report.Abstract, authors)
        return all_ids
    
    async def get_study_acronyms(self, report_id: int, include_fulltext : bool) -> List[str]:
        async def _get_study_acronyms(text):
            acronyms = []
            for acronym in await self.study_repo.get_study_acronyms():
                if acronym in text:
                    acronyms.append(acronym)
            return acronyms

        report = await self.get_report(report_id)
        if not report:
            return None
        
        if include_fulltext:
            try:
                text = await self.document_service.get_fulltext(report_id, fast=True)
                return await _get_study_acronyms(text)
            except:
                pass
        
        acronyms = []
        acronyms.extend(_get_study_acronyms(report.Title))
        acronyms.extend(_get_study_acronyms(report.Abstract))
        return acronyms
        
    
    async def extract_metadata(self, report_id: int) -> Dict[str, List[str]]: 
        meta_data = {}
        meta_data['report_type'] = None   
        fulltext = None
        
        is_abstract = await self.document_service.is_abstract_collection(report_id)
        if is_abstract:
            meta_data['report_type'] = 'abstract'       
        else:
            fulltext = await self.document_service.get_fulltext(report_id, fast=False) 

        async def _extract_pico():
            report = await self.get_report(report_id)
            return await self.llm_service.extract_pico(report.Title, report.Abstract, fulltext)

        trial_ids_task = self.get_trial_ids(report_id, include_fulltext=not is_abstract)
        study_acronyms_task = self.get_study_acronyms(report_id, include_fulltext=not is_abstract)
        extract_pico_task = _extract_pico()
        trial_ids, study_acronyms, pico_values = await asyncio.gather(trial_ids_task, study_acronyms_task, extract_pico_task)

        meta_data['trial_id'] = trial_ids
        meta_data['study_acronyms'] = study_acronyms


        meta_data['data_extraction'] = pico_values

        return meta_data
    
    async def get_metadata(self, report_id: int) -> Dict:
        data = None
        
        if data is None:
            # Process PDF to extract metadata
            data = await self.extract_metadata(report_id)
        
        return data
    
    async def get_report(self, report_id: int) -> Report:
        if report_id not in self.report_cache:
            self.report_cache[report_id] = await self.report_repo.get_report_by_id(report_id)
        return self.report_cache[report_id]

    