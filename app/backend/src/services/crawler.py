import asyncio
import httpx
from bs4 import BeautifulSoup
from httpx import ReadTimeout

from typing import Any, List

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

class OpenAlexService:
    OPEN_ALEX_API = "https://api.openalex.org/works/https://doi.org/{doi}"
    def __init__(self):
        # OPEN Alex is limited to 10 requests per second
        self.sem = asyncio.Semaphore(1)

    async def get_data_by_doi(self, doi : str) -> Any:
        url = OpenAlexService.OPEN_ALEX_API.format(doi=doi)
        async with self.sem:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
            except ReadTimeout:
                raise Exception("Upstream request timed out")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return {}
                else:
                    raise
            await asyncio.sleep(0.1)  # Non-blocking cooldown after each request
        return resp.json()
    
    async def get_pdf_links_by_doi(self, doi : str) -> List[str]:
        record = await self.get_data_by_doi(doi)
        urls = []
        try:
            for loc in record.get('locations', []):
                if loc.get('pdf_url'):
                    urls.append(loc['pdf_url'])
        except:
            pass
        return set(urls)

# Singletons: OpenAlexService's semaphore is meant to cap concurrent calls to
# OpenAlex process-wide (CrawlerService is stateless but kept consistent with
# the same pattern). A new instance per call site - `OpenAlexService()` in
# fastapi_app/resources.py and fastapi_app/projects.py, the old FastAPI
# Depends(get_document_service) factory - gives each caller its own semaphore
# instead, so the cap never actually applies across concurrent use.
crawler_service = CrawlerService()
open_alex_service = OpenAlexService()
