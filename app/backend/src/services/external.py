"""The search of other sources (PubMed, Europe PMC, ClinicalTrials.gov) next to the search of the studies, from the
workbench of a report: so that a study known by another publication of the trial is not created twice. Deterministic, no
AI involved:

- a query that is one registry id is searched as a phrase in every spelling (Europe PMC also finds it in full texts);
  any other query is sent to each source as typed;
- a record found by several sources (or spellings) is one record, merged by its PMID, PMCID, DOI or NCT id;
- what a record is to the report are facts: the report itself, and the studies of the report's database it is a report
  of (by its DOI or NCT id).
"""

import asyncio
import logging
import re
import unicodedata
import urllib.parse
from typing import Dict, List, Mapping, Optional, Tuple

import httpx

from ..database.models import ReportFields
from ..database.repositories.project import ProjectRepository
from ..database.repositories.report import ReportRepository
from ..database.repositories.study import StudyRepository
from ..utils.dto import ExternalRecord, ExternalRecords, ExternalSearch, studies_to_dto
from ..utils.trial_registration_id import ctri, extract_trial_id, extract_trial_ids_from_text, nct
from .authorization import get_authorized_project_id
from .core import StudySimilaritySearchService
from .crawler import normalize_doi

logger = logging.getLogger(__name__)


class ExternalSource:
    """A source searched by ExternalRecordService: returns the total of a query and its first records."""

    name = ""
    TIMEOUT = 25
    # Records kept per query.
    LIMIT = 8

    async def search(self, query: str) -> Tuple[Optional[int], List[ExternalRecord], str]:
        """The total, the first records and the URL of the query on the source's website; raises if it fails."""
        raise NotImplementedError

    async def _get(self, url: str, params: Dict[str, object]) -> dict:
        async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers={"User-Agent": "medidex"})
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _ids(**ids: Optional[str]) -> Dict[str, str]:
        """The identifiers of a record that the source gave."""
        return {name: value for name, value in ids.items() if value}

    def id_query(self, trial_id: str) -> str:
        """The query for a registry id: as a phrase, so that its parts are not searched apart."""
        return f'"{trial_id}"'

    @staticmethod
    def _year(value: object) -> Optional[int]:
        match = re.search(r"\d{4}", str(value or ""))
        return int(match.group()) if match else None


class PubMedSource(ExternalSource):
    """PubMed through the E-utilities (https://www.ncbi.nlm.nih.gov/books/NBK25501/)."""

    name = "PubMed"
    API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    # Without an API key NCBI allows 3 requests a second, per process.
    _sem = asyncio.Semaphore(1)

    async def _eutil(self, tool: str, params: Dict[str, object]) -> dict:
        async with PubMedSource._sem:
            try:
                return await self._get(self.API + tool, {"db": "pubmed", "retmode": "json", **params})
            finally:
                await asyncio.sleep(0.35)

    async def search(self, query: str) -> Tuple[Optional[int], List[ExternalRecord], str]:
        found = (await self._eutil("esearch.fcgi", {"retmax": self.LIMIT, "term": query}))["esearchresult"]
        records = []
        if found.get("idlist"):
            summaries = (await self._eutil("esummary.fcgi", {"id": ",".join(found["idlist"])}))["result"]
            for pmid in found["idlist"]:
                summary = summaries.get(pmid, {})
                ids = {i["idtype"]: i["value"] for i in summary.get("articleids", [])}
                records.append(ExternalRecord(
                    key="",
                    ids=self._ids(pmid=pmid, pmcid=ids.get("pmc"), doi=normalize_doi(ids.get("doi"))),
                    title=summary.get("title", ""),
                    firstAuthor=(summary.get("authors") or [{}])[0].get("name", ""),
                    year=self._year(summary.get("pubdate")),
                    venue=summary.get("source", ""),
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                ))
        return int(found.get("count", 0)), records, "https://pubmed.ncbi.nlm.nih.gov/?term=" + urllib.parse.quote(query)


class EuropePmcSource(ExternalSource):
    """Europe PMC through its REST API (https://europepmc.org/RestfulWebService); it also indexes preprints, patents
    and the full texts of PMC, where registry ids often stand."""

    name = "Europe PMC"
    API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    async def search(self, query: str) -> Tuple[Optional[int], List[ExternalRecord], str]:
        data = await self._get(self.API, {"format": "json", "pageSize": self.LIMIT, "query": query})
        records = []
        for result in data.get("resultList", {}).get("result", []):
            ids = self._ids(pmid=result.get("pmid"), pmcid=result.get("pmcid"), doi=normalize_doi(result.get("doi")))
            if not ids:
                ids["epmc"] = f"{result.get('source', '')}:{result.get('id', '')}"
            records.append(ExternalRecord(
                key="",
                ids=ids,
                title=result.get("title", ""),
                firstAuthor=(result.get("authorString") or "").split(",")[0],
                year=self._year(result.get("pubYear")),
                venue=result.get("journalTitle") or result.get("bookOrReportDetails", {}).get("publisher", "") or result.get("source", ""),
                url=f"https://europepmc.org/article/{result.get('source', '')}/{result.get('id', '')}",
            ))
        return data.get("hitCount"), records, "https://europepmc.org/search?query=" + urllib.parse.quote(query)


class ClinicalTrialsGovSource(ExternalSource):
    """ClinicalTrials.gov through its public API (https://clinicaltrials.gov/data-api/api); it lists the other ids of a
    trial too, so a search for a trial's id of another register finds its record there."""

    name = "ClinicalTrials.gov"
    API = "https://clinicaltrials.gov/api/v2/studies"

    def id_query(self, trial_id: str) -> str:
        return trial_id

    async def search(self, query: str) -> Tuple[Optional[int], List[ExternalRecord], str]:
        data = await self._get(self.API, {"pageSize": self.LIMIT, "countTotal": "true", "query.term": query})
        records = []
        for study in data.get("studies", []):
            protocol = study.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            records.append(ExternalRecord(
                key="",
                ids=self._ids(nct=ident.get("nctId")),
                title=ident.get("officialTitle") or ident.get("briefTitle", ""),
                year=self._year(protocol.get("statusModule", {}).get("startDateStruct", {}).get("date")),
                venue="ClinicalTrials.gov",
                url=f"https://clinicaltrials.gov/study/{ident.get('nctId')}",
            ))
        return data.get("totalCount"), records, "https://clinicaltrials.gov/search?term=" + urllib.parse.quote(query)


class ExternalRecordService:
    """Searches the other sources for a query and relates what they return to a report and to the studies of its
    database (see the module docstring)."""

    def __init__(
        self,
        report_repo: ReportRepository,
        study_repo: StudyRepository,
        project_repo: ProjectRepository,
        study_similarity_service: StudySimilaritySearchService,
    ):
        self.report_repo = report_repo
        self.study_repo = study_repo
        self.project_repo = project_repo
        self.study_similarity_service = study_similarity_service
        # OpenAlex is not searched: by a registry id it finds what Europe PMC finds (NCT ids) or less (CTRI ids).
        self.sources: List[ExternalSource] = [PubMedSource(), EuropePmcSource(), ClinicalTrialsGovSource()]

    async def search(self, report_id: int, query: str, user_id: Optional[str]) -> ExternalRecords:
        """What the sources find for the query, with the studies of the report's database the records belong to.
        Raises ReportNotFoundError/AuthenticationRequiredError/ReportAccessDeniedError like the other report endpoints."""
        await get_authorized_project_id(report_id, self.report_repo, self.project_repo, user_id)
        report = await self.report_repo.get_report_by_id(report_id)
        query = query.strip()
        queries = [(source, source.id_query(spelling))
                   for i, spelling in enumerate(self._spellings(query))
                   for source in self.sources
                   # ClinicalTrials.gov matches every spelling of an id alike.
                   if i == 0 or not isinstance(source, ClinicalTrialsGovSource)
                   ] if self._is_trial_id(query) else [(source, query) for source in self.sources]

        results = await asyncio.gather(*(self._run(source, q) for source, q in queries))
        searches, records = [], []
        for (source, q), (hits, found, url, error) in zip(queries, results):
            for record in found:
                record.key = self._key(record.ids)
            records += found
            searches.append(ExternalSearch(source=source.name, query=q, hits=hits, url=url, error=error,
                                           found=list(dict.fromkeys(record.key for record in found))))
        merged, remap = self._merge(records)
        for search in searches:
            search.found = list(dict.fromkeys(remap[key] for key in search.found))
        result = ExternalRecords(query=query, searches=searches, records=merged, studies=[])
        return await self._relate(report_id, report, result, user_id)

    @staticmethod
    async def _run(source: ExternalSource, query: str) -> Tuple[Optional[int], List[ExternalRecord], str, Optional[str]]:
        try:
            hits, records, url = await source.search(query)
            return hits, records, url, None
        except Exception as exc:  # an unreachable source is shown as such, the others still count
            logger.warning("External search failed (%s, %r): %s", source.name, query, exc)
            return None, [], "", str(exc)[:200] or type(exc).__name__

    @classmethod
    def _is_trial_id(cls, query: str) -> bool:
        """Whether the query is one registry id (searched as a phrase, in every spelling) rather than words (sent as
        typed)."""
        found = extract_trial_ids_from_text(query)
        return len(found) == 1 and cls.trial_key(found[0]) == cls.trial_key(query)

    @staticmethod
    def trial_key(trial_id: str) -> str:
        """A registry id without case and separators, as StudyRepository.get_study_ids_by_trial_ids compares them."""
        return re.sub(r"[^A-Z0-9]", "", trial_id.upper())

    @staticmethod
    def _spellings(trial_id: str) -> List[str]:
        """The ways the id is written in publications: CTRI ids with "/" and with "-", NCT ids without separators."""
        trial_id = trial_id.strip()
        if ctri.fullmatch(trial_id):
            parts = re.split(r"[/-]", trial_id.upper())
            return ["/".join(parts), "-".join(parts)]
        if nct.fullmatch(trial_id):
            return ["NCT" + re.sub(r"\D", "", trial_id)]
        return [trial_id]

    # Merging

    @staticmethod
    def _key(ids: Mapping[str, Optional[str]]) -> str:
        """The key of a record by its best identifier."""
        for name in ("pmid", "pmcid", "doi", "nct", "epmc"):
            if ids.get(name):
                return f"{name}:{ids[name]}"
        return "unknown"

    def _merge(self, records: List[ExternalRecord]) -> Tuple[List[ExternalRecord], Dict[str, str]]:
        """One record per publication: records sharing a PMID, PMCID, DOI or NCT id are merged (their ids
        joined, the first value of every other field kept). Returns them and the key each key became."""
        parent = list(range(len(records)))

        def root(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        owner: Dict[str, int] = {}
        for i, record in enumerate(records):
            for name in ("pmid", "pmcid", "doi", "nct", "epmc"):
                value = record.ids.get(name)
                if value:
                    token = f"{name}:{value.lower()}"
                    if token in owner:
                        parent[root(i)] = root(owner[token])
                    else:
                        owner[token] = i

        groups: Dict[int, List[ExternalRecord]] = {}
        for i, record in enumerate(records):
            groups.setdefault(root(i), []).append(record)
        merged, remap = [], {}
        for group in groups.values():
            ids: Dict[str, str] = {}
            for record in group:
                ids.update({k: v for k, v in record.ids.items() if v and k not in ids})
            first = lambda field: next((getattr(r, field) for r in group if getattr(r, field)), getattr(group[0], field))
            record = ExternalRecord(key=self._key(ids), ids=ids, title=first("title"), firstAuthor=first("firstAuthor"),
                                    year=first("year"), venue=first("venue"), url=first("url"))
            if record.ids.get("pmid"):
                record.url = f"https://pubmed.ncbi.nlm.nih.gov/{record.ids['pmid']}/"
            merged.append(record)
            remap.update({r.key: record.key for r in group})
        return merged, remap

    # Relating the records to the report and the database

    async def _relate(self, report_id: int, report: ReportFields, result: ExternalRecords, user_id: Optional[str]) -> ExternalRecords:
        databases = await self.study_similarity_service.databases_of_report(report_id)

        dois = [r.ids["doi"] for r in result.records if r.ids.get("doi")]
        by_doi = await self.study_repo.get_study_ids_by_report_dois(dois)
        nct_ids = [r.ids["nct"] for r in result.records if r.ids.get("nct")]
        by_nct = await self.study_repo.get_study_ids_by_trial_ids(nct_ids, databases)

        own_ids = {self.trial_key(t) for t in [report.trial_registration_id, *extract_trial_id(report.title, report.abstract, report.authors)] if t}
        own_doi = normalize_doi(report.doi) if report.doi else None
        own_title = self._title_key(report.title)

        for record in result.records:
            doi, nct_id = record.ids.get("doi"), record.ids.get("nct")
            record.thisReport = bool(
                (own_doi and doi == own_doi)
                or (own_title and self._title_key(record.title) == own_title and record.year in (None, report.year))
                or (not report.authors and nct_id and self.trial_key(nct_id) in own_ids)
            )
            record.studyIds = list(dict.fromkeys([*by_doi.get(doi or "", []), *by_nct.get(self.trial_key(nct_id or ""), [])]))

        # Studies of linked reports are filtered to the report's database here (get_study_ids_by_report_dois is not).
        study_ids = list(dict.fromkeys(i for r in result.records for i in r.studyIds))
        studies = studies_to_dto(await self.study_repo.get_studies(study_ids, databases)) if study_ids else []
        visible = {study.studyId for study in studies}
        for record in result.records:
            record.studyIds = [i for i in record.studyIds if i in visible]
        result.studies = await self.study_similarity_service.add_relevance(report_id, studies, user_id)
        result.records.sort(key=self._rank)
        return result

    @staticmethod
    def _rank(record: ExternalRecord) -> Tuple:
        """Those of a study of the database first, the report itself last; otherwise in the order the sources gave."""
        return (record.thisReport, not record.studyIds)

    @staticmethod
    def _title_key(title: Optional[str]) -> str:
        return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower())

