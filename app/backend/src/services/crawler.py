import asyncio
import httpx
from bs4 import BeautifulSoup
from httpx import ReadTimeout

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List

class CrawlerService:
    def __init__(self):
        pass

    def html_to_lowest_level_markdown(self, html_content):
        soup = BeautifulSoup(html_content, 'lxml')
        markdown_output = []

        for table in soup.find_all('table'):
            # Process only "leaf" tables (no nested tables inside)
            if not table.find('table'):
                rows = []
                max_cols = 0
                
                for tr in table.find_all('tr'):
                    cells = [td.get_text(separator=" ", strip=True).replace('\xa0', ' ') 
                            for td in tr.find_all(['td', 'th'])]
                    if any(cells):
                        rows.append(cells)
                        max_cols = max(max_cols, len(cells))
                
                if rows:
                    # Create Markdown table structure
                    # 1. Empty Header Row
                    header = "| " + " | ".join([" " for _ in range(max_cols)]) + " |"
                    # 2. Separator Row
                    separator = "| " + " | ".join(["---" for _ in range(max_cols)]) + " |"
                    # 3. Data Rows
                    body = []
                    for row in rows:
                        # Pad row if it has fewer columns than max_cols
                        padded_row = row + [""] * (max_cols - len(row))
                        body.append("| " + " | ".join(padded_row) + " |")
                    
                    markdown_output.append(f"{header}\n{separator}\n" + "\n".join(body))

        return "\n\n".join(markdown_output)

    def extract_fourth_top_level_table(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")

        # Remove script and style tags
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()

        # Remove stylesheet links
        for link in soup.find_all("link", rel="stylesheet"):
            link.decompose()

        # Remove styling / scripting attributes
        for tag in soup.find_all(True):
            tag.attrs = {
                k: v for k, v in tag.attrs.items()
                if k != "style" and not k.startswith("on")
            }

        # Get top-level tables (no parent table)
        top_level_tables = [
            table for table in soup.find_all("table")
            if table.find_parent("table") is None
        ]

        # Verify count
        if len(top_level_tables) != 5:
            raise ValueError(f"Expected 5 top-level tables, found {len(top_level_tables)}")

        # Return only the second table
        return top_level_tables[3].prettify()

    async def _fetch_trial_table_html(self, trial_id : str) -> str:
        """The WHO ICTRP registry record's data table for `trial_id`, as HTML."""
        url = f"https://trialsearch.who.int/Trial2.aspx?TrialID={trial_id}"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://trialsearch.who.int/",
        }

        try:
            async with httpx.AsyncClient(headers=headers, timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                #TODO handle nginx 500 bad gateerror
                return await asyncio.to_thread(self.extract_fourth_top_level_table, resp.text)
        except ReadTimeout:
            raise Exception("Upstream request timed out")

    async def get_html_for_trial_id(self, trial_id : str):
        """The registry record as markdown tables."""
        parsed_html = await self._fetch_trial_table_html(trial_id)
        return await asyncio.to_thread(self.html_to_lowest_level_markdown, parsed_html)

    async def get_pdf_for_trial_id(self, trial_id : str) -> bytes:
        """The registry record rendered as a PDF, so a trial registration can be
        stored and shown like any other report's PDF."""
        parsed_html = await self._fetch_trial_table_html(trial_id)
        return await asyncio.to_thread(self.html_to_pdf, trial_id, parsed_html)

    @staticmethod
    def html_to_pdf(title : str, table_html : str) -> bytes:
        # Imported lazily: WeasyPrint loads native libraries (pango) at import time.
        from weasyprint import HTML

        document = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
  body {{ font-family: sans-serif; font-size: 10pt; }}
  table {{ border-collapse: collapse; width: 100%; }}
  td, th {{ border: 1px solid #999; padding: 3px 6px; vertical-align: top; text-align: left; }}
</style></head>
<body><h1>{title}</h1>{table_html}</body></html>"""
        return HTML(string=document).write_pdf()

def normalize_doi(doi: str) -> str:
    """Canonical form used to compare DOIs: lowercase, no resolver prefix."""
    doi = (doi or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if doi.startswith(prefix):
            return doi[len(prefix):].strip()
    return doi

@dataclass
class OpenAlexWork:
    pdf_links: List[str] = field(default_factory=list)
    referenced_dois: List[str] = field(default_factory=list)

class OpenAlexService:
    OPEN_ALEX_API = "https://api.openalex.org/works"
    # Max values per OR-filter ("a|b|c") OpenAlex accepts, and the page size we ask for.
    BATCH_SIZE = 50

    def __init__(self):
        # OPEN Alex is limited to 10 requests per second
        self.sem = asyncio.Semaphore(1)

    async def _get_json(self, client: httpx.AsyncClient, params: dict) -> Any:
        async with self.sem:
            try:
                resp = await client.get(OpenAlexService.OPEN_ALEX_API, params=params)
                resp.raise_for_status()
            except ReadTimeout:
                raise Exception("Upstream request timed out")
            await asyncio.sleep(0.1)  # Non-blocking cooldown after each request
        return resp.json()

    @staticmethod
    def _chunks(items: List[str], size: int):
        for i in range(0, len(items), size):
            yield items[i:i + size]

    @staticmethod
    def _short_id(openalex_id: str) -> str:
        return openalex_id.rsplit("/", 1)[-1]

    @staticmethod
    def _pdf_links(record: dict) -> List[str]:
        links = []
        for loc in record.get('locations') or []:
            url = loc.get('pdf_url')
            if url and url not in links:
                links.append(url)
        return links

    async def _resolve_dois_by_openalex_ids(self, client: httpx.AsyncClient, openalex_ids: List[str]) -> Dict[str, str]:
        """Batched OpenAlex work id -> normalized DOI; works without a DOI are left out."""
        resolved = {}
        for chunk in self._chunks(openalex_ids, self.BATCH_SIZE):
            data = await self._get_json(client, {
                "filter": "openalex:" + "|".join(chunk),
                "per-page": self.BATCH_SIZE,
                "select": "id,doi",
            })
            for record in data.get('results', []):
                if record.get('id') and record.get('doi'):
                    resolved[self._short_id(record['id'])] = normalize_doi(record['doi'])
        return resolved

    async def get_works_by_dois(self, dois: Iterable[str]) -> Dict[str, OpenAlexWork]:
        """Batched lookup of PDF links and referenced DOIs for many DOIs at once: one
        request per BATCH_SIZE DOIs, plus one more per BATCH_SIZE distinct referenced
        works to turn OpenAlex's reference ids into DOIs. Keys are normalized DOIs;
        DOIs OpenAlex doesn't know are absent from the result. Raises on upstream errors.
        """
        wanted = list(dict.fromkeys(normalize_doi(d) for d in dois if d))
        # "," and "|" are filter syntax in OpenAlex and can't be escaped
        wanted = [d for d in wanted if d and "," not in d and "|" not in d]
        if not wanted:
            return {}

        records: Dict[str, dict] = {}
        async with httpx.AsyncClient(timeout=30) as client:
            for chunk in self._chunks(wanted, self.BATCH_SIZE):
                data = await self._get_json(client, {
                    "filter": "doi:" + "|".join(chunk),
                    "per-page": self.BATCH_SIZE,
                    "select": "id,doi,locations,referenced_works",
                })
                for record in data.get('results', []):
                    if record.get('doi'):
                        records[normalize_doi(record['doi'])] = record

            reference_ids = list(dict.fromkeys(
                self._short_id(ref)
                for record in records.values()
                for ref in record.get('referenced_works') or []
            ))
            resolved = await self._resolve_dois_by_openalex_ids(client, reference_ids)

        works = {}
        for doi, record in records.items():
            referenced_dois = list(dict.fromkeys(
                resolved[self._short_id(ref)]
                for ref in record.get('referenced_works') or []
                if self._short_id(ref) in resolved
            ))
            works[doi] = OpenAlexWork(
                pdf_links=self._pdf_links(record),
                referenced_dois=referenced_dois,
            )
        return works

    async def get_work_by_doi(self, doi: str) -> OpenAlexWork:
        works = await self.get_works_by_dois([doi])
        return works.get(normalize_doi(doi), OpenAlexWork())

    async def get_pdf_links_by_doi(self, doi : str) -> List[str]:
        return set((await self.get_work_by_doi(doi)).pdf_links)

# Singletons: OpenAlexService's semaphore is meant to cap concurrent calls to
# OpenAlex process-wide (CrawlerService is stateless but kept consistent with
# the same pattern). A new instance per call site - `OpenAlexService()` in
# fastapi_app/resources.py and fastapi_app/projects.py, the old FastAPI
# Depends(get_document_service) factory - gives each caller its own semaphore
# instead, so the cap never actually applies across concurrent use.
crawler_service = CrawlerService()
open_alex_service = OpenAlexService()
