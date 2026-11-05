"""What other sources (PubMed, Europe PMC, ClinicalTrials.gov, OpenAlex) know of the trial of a report, so that a study
described elsewhere already is not created twice. Deterministic, no AI involved:

- the queries are built from the report: each of its registry ids in every spelling, and its first author with the
  distinctive words of its title;
- a record found by several sources (or queries) is one record, merged by its PMID, PMCID or DOI;
- what a record is to the report are facts: the report itself, found by its registry id, a report of a study of the
  database (by DOI or registry id), the same first author, how much of its title it shares.

The searches depend on the report alone, so they run once, as a postprocessing of the upload (ExternalSearchPostprocessor),
and are stored on the report of the update (UpdateReport.external_records); they are repeated only when its registry ids
change. The studies
are matched when read, so that the match stays correct as reports are linked and merged.
"""

import asyncio
import logging
import re
import unicodedata
import urllib.parse
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

import httpx

from sqlmodel import select

from ..background.postprocessing import PostprocessingOptions
from ..database.models import ReportFields, UpdateReport
from ..database.repositories.project import ProjectRepository
from ..database.repositories.report import ReportRepository
from ..database.repositories.study import StudyRepository
from ..utils.dto import ExternalRecord, ExternalRecords, ExternalSearch, studies_to_dto
from ..utils.trial_registration_id import ctri, extract_trial_id, nct
from .authorization import get_authorized_project_id
from .core import StudySimilaritySearchService
from .crawler import OpenAlexService, normalize_doi

if TYPE_CHECKING:  # the context builds ExternalRecordService
    from ..context import RequestContext

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


class OpenAlexSource(ExternalSource):
    """OpenAlex, through the process-wide OpenAlexService (its rate limit). A query is the words searched in title and
    abstract, "author:<surname> <words>" to search the names of the authors as well."""

    name = "OpenAlex"

    def __init__(self, open_alex_service: OpenAlexService):
        self.open_alex_service = open_alex_service

    @staticmethod
    def _filters(query: str) -> Dict[str, str]:
        match = re.match(r"author:(\S+)\s*(.*)$", query)
        author, words = (match.group(1), match.group(2)) if match else (None, query)
        filters = {"raw_author_name.search": author} if author else {}
        if words:
            filters["title_and_abstract.search"] = words
        return filters

    async def search(self, query: str) -> Tuple[Optional[int], List[ExternalRecord], str]:
        filters = self._filters(query)
        total, works = await self.open_alex_service.search_works(filters, self.LIMIT)
        records = []
        for work in works:
            ids = work.get("ids") or {}
            location = (work.get("primary_location") or {}).get("source") or {}
            records.append(ExternalRecord(
                key="",
                ids=self._ids(
                    pmid=(ids.get("pmid") or "").rsplit("/", 1)[-1],
                    pmcid=(ids.get("pmcid") or "").rsplit("/", 1)[-1],
                    doi=normalize_doi(work.get("doi")),
                    openalex=work["id"].rsplit("/", 1)[-1],
                ),
                title=work.get("title") or "",
                firstAuthor=((work.get("authorships") or [{}])[0]).get("raw_author_name", ""),
                year=work.get("publication_year"),
                venue=location.get("display_name", ""),
                url=work["id"],
            ))
        url = "https://openalex.org/works?filter=" + urllib.parse.quote(",".join(f"{k}:{v}" for k, v in filters.items()), safe=":,")
        return total, records, url


class ExternalRecordService:
    """Searches the other sources for the trial of a report and relates what they return to the report and to the
    studies of its database (see the module docstring)."""

    # Registry ids of a report searched at most; spellings of one id.
    MAX_TRIAL_IDS = 3
    # Words of the title in a query; with the first author fewer, the author narrows the search already.
    TERM_WORDS = 4
    AUTHOR_WORDS = 3
    # Words that say nothing about which trial a title is about.
    STOPWORDS = frozenset("""
        a about after against all among an and any are as at be been before between both but by can could during each
        effect effects efficacy for from has have in into is it its more non not of on or other over per pilot
        than that the their there these this those through to under use using versus via vs was were what when which
        while who with within without
        analysis arm arms assessment associated clinical comparative compared comparison controlled cross design double
        evaluation evidence follow group groups intervention interventions investigate investigating multicenter
        multicentre open outcome outcomes participants patient patients phase placebo preliminary prospective protocol
        randomised randomized randomly report response results safety sectional secondary single study studies
        treatment treatments trial trials years
    """.split())

    def __init__(
        self,
        report_repo: ReportRepository,
        study_repo: StudyRepository,
        project_repo: ProjectRepository,
        study_similarity_service: StudySimilaritySearchService,
        open_alex_service: OpenAlexService,
    ):
        self.report_repo = report_repo
        self.study_repo = study_repo
        self.project_repo = project_repo
        self.study_similarity_service = study_similarity_service
        self.id_sources: List[ExternalSource] = [PubMedSource(), EuropePmcSource(), ClinicalTrialsGovSource()]
        # OpenAlex finds nothing more by a registry id than Europe PMC does, so it only gets the terms.
        self.term_sources: List[ExternalSource] = [*self.id_sources, OpenAlexSource(open_alex_service)]

    async def get_external_records(self, report_id: int, user_id: Optional[str], refresh: bool = False) -> ExternalRecords:
        """The external records of the report, with the studies they belong to as of now. The searches come from the
        upload (see ExternalSearchPostprocessor); they run here when the report has none yet (a report of the core
        database, one whose postprocessing has not got to it or failed), when its registry ids changed since (a reviewer confirmed another one), or with
        `refresh`. Raises ReportNotFoundError/AuthenticationRequiredError/ReportAccessDeniedError like the other report
        endpoints."""
        await get_authorized_project_id(report_id, self.report_repo, self.project_repo, user_id)
        report = await self.report_repo.get_report_by_id(report_id)
        update_report = await self.report_repo.get_update_report(report_id)

        cached = update_report.external_records if update_report is not None else None
        if refresh or cached is None or "error" in cached or not self._same_trial_ids(cached.get("trialIds", []), self._report_trial_ids(report, update_report)):
            cached = await self._search_and_store(report, update_report)

        result = ExternalRecords(**{**cached, "studies": []})
        return await self._relate(report_id, report, result, user_id)

    async def search(self, report_id: int) -> None:
        """Searches the other sources for a report of an update and stores what they returned on it (see
        ExternalSearchPostprocessor)."""
        update_report = await self.report_repo.get_update_report(report_id)
        if update_report is not None:
            await self._search_and_store(update_report, update_report)

    async def _search_and_store(self, report: ReportFields, update_report) -> Dict:
        searched = (await self._search(report, update_report)).model_dump(mode="json")
        if update_report is not None:
            await self.report_repo.set_external_records(update_report.id, searched)
        return searched

    def _report_trial_ids(self, report: ReportFields, update_report) -> List[str]:
        return self._trial_ids(report, getattr(update_report, "preliminary_trial_id", None))

    def _same_trial_ids(self, searched: List[str], current: List[str]) -> bool:
        return [self.trial_key(t) for t in searched] == [self.trial_key(t) for t in current]

    # Searching

    async def _search(self, report: ReportFields, update_report) -> ExternalRecords:
        trial_ids = self._report_trial_ids(report, update_report)
        queries = [("id", source, source.id_query(spelling))
                   for trial_id in trial_ids for i, spelling in enumerate(self._spellings(trial_id))
                   for source in self.id_sources
                   # ClinicalTrials.gov matches every spelling of an id alike.
                   if i == 0 or not isinstance(source, ClinicalTrialsGovSource)]
        queries += [("terms", source, query) for source, query in self._term_queries(report)]

        results = await asyncio.gather(*(self._run(source, query) for _, source, query in queries))
        searches, records = [], []
        for (kind, source, query), (hits, found, url, error) in zip(queries, results):
            for record in found:
                record.key = self._key(record.ids)
            records += found
            searches.append(ExternalSearch(kind=kind, source=source.name, query=query, hits=hits, url=url, error=error,
                                           found=list(dict.fromkeys(record.key for record in found))))
        merged, remap = self._merge(records)
        for search in searches:
            search.found = list(dict.fromkeys(remap[key] for key in search.found))
        return ExternalRecords(searchedAt=datetime.now(timezone.utc), trialIds=trial_ids, searches=searches,
                               records=merged, studies=[])

    @staticmethod
    async def _run(source: ExternalSource, query: str) -> Tuple[Optional[int], List[ExternalRecord], str, Optional[str]]:
        try:
            hits, records, url = await source.search(query)
            return hits, records, url, None
        except Exception as exc:  # an unreachable source is shown as such, the others still count
            logger.warning("External search failed (%s, %r): %s", source.name, query, exc)
            return None, [], "", str(exc)[:200] or type(exc).__name__

    def _trial_ids(self, report: ReportFields, preliminary: Optional[str]) -> List[str]:
        """The registry ids of the report: the confirmed one, the guess of the upload, those in its title, abstract
        and authors; one per trial, in that order."""
        candidates = [report.trial_registration_id, preliminary,
                      *extract_trial_id(report.title, report.abstract, report.authors)]
        ids: Dict[str, str] = {}
        for trial_id in candidates:
            if trial_id and trial_id.strip():
                ids.setdefault(self.trial_key(trial_id), trial_id.strip())
        return list(ids.values())[:self.MAX_TRIAL_IDS]

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

    def _term_queries(self, report: ReportFields) -> List[Tuple[ExternalSource, str]]:
        """The first author with the most distinctive words of the title, and the words alone (to find the other
        publications of the trial, by other first authors). A registry record has no authors: only the words."""
        words = self._distinctive(report.title, self.TERM_WORDS)
        if len(words) < 2:
            return []
        surname = self._surname(report.authors[0]) if report.authors else None
        top = words[:self.AUTHOR_WORDS]
        pubmed, epmc, ctgov, openalex = self.term_sources
        queries: List[Tuple[ExternalSource, str]] = []
        if surname:
            queries += [
                (pubmed, f"{surname}[au] AND " + " AND ".join(top)),
                (epmc, f'AUTH:"{surname}" AND ' + " AND ".join(top)),
                (openalex, f"author:{surname} " + " ".join(top)),
            ]
        queries += [
            (pubmed, " AND ".join(f"{word}[tiab]" for word in words)),
            (epmc, " AND ".join(words)),
            (ctgov, " ".join(words)),
        ]
        return queries

    @classmethod
    def _words(cls, text: Optional[str]) -> List[str]:
        """The words of a text that say something (no stopwords, numbers or short words), lowercase, accents removed, in
        order and once each."""
        plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
        words = re.findall(r"[a-z][a-z0-9-]*[a-z0-9]", plain)
        return list(dict.fromkeys(w for w in words if len(w) >= 4 and w not in cls.STOPWORDS))

    @classmethod
    def _distinctive(cls, title: Optional[str], count: int) -> List[str]:
        """The `count` longest words of the title (longer words are rarer), in the order of the title."""
        words = cls._words(title)
        keep = set(sorted(words, key=len, reverse=True)[:count])
        return [w for w in words if w in keep]

    @staticmethod
    def _surname(author: str) -> Optional[str]:
        """The family name of an author as uploaded ("Smith, John", "Smith J", "John Smith")."""
        author = author.strip()
        if "," in author:
            name = author.split(",")[0]
        else:
            parts = author.split()
            if not parts:
                return None
            # "Smith J" / "Smith JA": initials after the surname.
            name = " ".join(parts[:-1]) if len(parts) > 1 and re.fullmatch(r"[A-Z]{1,3}", parts[-1]) else parts[-1]
        name = re.sub(r"[^\w' -]", "", name).strip()
        return name or None

    # Merging

    @staticmethod
    def _key(ids: Dict[str, Optional[str]]) -> str:
        """The key of a record by its best identifier."""
        for name in ("pmid", "pmcid", "doi", "nct", "openalex", "epmc"):
            if ids.get(name):
                return f"{name}:{ids[name]}"
        return "unknown"

    def _merge(self, records: List[ExternalRecord]) -> Tuple[List[ExternalRecord], Dict[str, str]]:
        """One record per publication: records sharing a PMID, PMCID, DOI, NCT id or OpenAlex id are merged (their ids
        joined, the first value of every other field kept). Returns them and the key each key became."""
        parent = list(range(len(records)))

        def root(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        owner: Dict[str, int] = {}
        for i, record in enumerate(records):
            for name in ("pmid", "pmcid", "doi", "nct", "openalex", "epmc"):
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
        by_trial = await self.study_repo.get_study_ids_by_trial_ids(result.trialIds, databases)
        result.trialIdStudies = {t: by_trial[self.trial_key(t)] for t in result.trialIds if self.trial_key(t) in by_trial}

        dois = [r.ids["doi"] for r in result.records if r.ids.get("doi")]
        by_doi = await self.study_repo.get_study_ids_by_report_dois(dois)
        nct_ids = [r.ids["nct"] for r in result.records if r.ids.get("nct")]
        by_nct = await self.study_repo.get_study_ids_by_trial_ids(nct_ids, databases)

        id_keys = {key for s in result.searches if s.kind == "id" for key in s.found}
        own_ids = {self.trial_key(t) for t in result.trialIds}
        own_doi = normalize_doi(report.doi) if report.doi else None
        own_title = self._title_key(report.title)
        own_words = set(self._words(report.title))
        own_surname = self._name_key(self._surname(report.authors[0]) if report.authors else None)

        for record in result.records:
            doi, nct_id = record.ids.get("doi"), record.ids.get("nct")
            record.thisReport = bool(
                (own_doi and doi == own_doi)
                or (own_title and self._title_key(record.title) == own_title and record.year in (None, report.year))
                or (not report.authors and nct_id and self.trial_key(nct_id) in own_ids)
            )
            record.carriesTrialId = record.key in id_keys or bool(nct_id and self.trial_key(nct_id) in own_ids)
            record.studyIds = list(dict.fromkeys([*by_doi.get(doi or "", []), *by_nct.get(self.trial_key(nct_id or ""), [])]))
            record.sameFirstAuthor = bool(own_surname) and self._name_key(self._surname(record.firstAuthor)) == own_surname
            words = set(self._words(record.title))
            record.titleOverlap = round(len(words & own_words) / len(words | own_words), 2) if words and own_words else 0.0

        # Studies of linked reports are filtered to the report's database here (get_study_ids_by_report_dois is not).
        study_ids = list(dict.fromkeys([i for r in result.records for i in r.studyIds]
                                       + [i for ids in result.trialIdStudies.values() for i in ids]))
        studies = studies_to_dto(await self.study_repo.get_studies(study_ids, databases)) if study_ids else []
        visible = {study.studyId for study in studies}
        for record in result.records:
            record.studyIds = [i for i in record.studyIds if i in visible]
        result.studies = await self.study_similarity_service.add_relevance(report_id, studies, user_id)
        result.records.sort(key=self._rank)
        return result

    @staticmethod
    def _rank(record: ExternalRecord) -> Tuple:
        """Records to look at first: the trial's id outside the database, then those of a study, then by likeness."""
        return (record.thisReport, not (record.carriesTrialId and not record.studyIds), not record.studyIds,
                not record.sameFirstAuthor, -record.titleOverlap)

    @staticmethod
    def _title_key(title: Optional[str]) -> str:
        return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower())

    @staticmethod
    def _name_key(name: Optional[str]) -> str:
        return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower())


class ExternalSearchPostprocessor:
    """Searches the other sources for every report of an upload (ExternalRecordService.search), registered by medidex
    itself (fastapi_app/__init__.py); not an option of the upload. It needs neither the PDF nor the criteria, but runs
    as a postprocessing so that a report is reviewed with its external records at hand. Pending is a report without
    stored searches; a failed run stores its error, so it counts as finished and the report view searches again."""

    # Each report sends about ten requests to public APIs (PubMed allows 3 a second without a key).
    _semaphore = asyncio.Semaphore(2)

    def is_enabled(self, options: PostprocessingOptions) -> bool:
        return True

    def pending_report_ids(self) -> Any:
        return select(UpdateReport.id).where(UpdateReport.external_records.is_(None))

    def tracked_report_ids(self) -> Any:
        return select(UpdateReport.id)

    async def prepare(
        self, project_id: str, report_ids: Sequence[int], options: PostprocessingOptions, ctx: "RequestContext"
    ) -> None:
        """Nothing to mark: a new report has no searches, so it is pending."""

    async def pdf_changed(self, report_id: int, project_id: str, ctx: "RequestContext") -> None:
        """The searches do not read the PDF."""

    async def criteria_changed(self, database_id: int, ctx: "RequestContext") -> Sequence[int]:
        return []

    async def process(
        self, report_id: int, project_id: str, options: PostprocessingOptions, ctx: "RequestContext"
    ) -> None:
        async with self._semaphore:
            try:
                await ctx.external_record_service.search(report_id)
            except Exception as exc:
                logger.exception("External search failed for report %s", report_id)
                await ctx.db.rollback()
                await ctx.report_repo.set_external_records(report_id, {"error": str(exc)[:500] or type(exc).__name__})
