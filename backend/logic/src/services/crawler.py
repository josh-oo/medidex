import asyncio
import httpx
import os
from httpx import ReadTimeout
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Any, List

from dotenv import load_dotenv

load_dotenv()

DOCLING_URL = os.getenv("DOCLING_URL")
OPEN_ALEX_API = "https://api.openalex.org/works/https://doi.org/{doi}"

class OpenAlexService:
    def __init__(self):
        #OPEN Alex limited to 10 requests per second
        self.sem = asyncio.Semaphore(8)

    async def get_data_by_doi(self, doi : str) -> Any:
        url = OPEN_ALEX_API.format(doi=doi)
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
            
        return resp.json()
    
    async def resolve_redirect_async(self, url : str):
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            response = await client.get(url)
            return response.url
    
    async def get_pdf_links_by_doi(self, doi : str) -> List[str]:
        #record = await self.get_data_by_doi(doi)
        #tasks =  [self.resolve_redirect_async(loc['landing_page_url']) for loc in record.get('locations', [])]
        #resolved_urls = await asyncio.gather(*tasks)
        #return [str(url) for url in resolved_urls]
        record = await self.get_data_by_doi(doi)
        urls = []
        for loc in record.get('locations', []):
            if loc.get('pdf_url'):
                urls.append({"type": "pdf", "source": loc['pdf_url']})
            elif loc.get('landing_page_url'):
                urls.append({ "type": "link", "source": loc['landing_page_url']})
        return urls
    
    async def get_pmc_link_by_doi(self, doi : str):
        record = await self.get_data_by_doi(doi)
                
        pmc_info = {}
    
        # Iterate through all locations to find the one hosted on PubMed Central
        for loc in record.get("locations", []):
            source_name = loc.get("source", {}).get("display_name", "")
            
            if "PubMed Central" in source_name:
                pmc_info["landing_page"] = loc.get("landing_page_url")
                pmc_info["pdf_url"] = loc.get("pdf_url")
                break # Exit once found
                
        return pmc_info


class PdfRetrieverService:
    def __init__(self):
        self.open_alex_service = OpenAlexService()

    async def get_pdf_by_doi(self, doi : str) -> Any:
        pmc_info = await self.open_alex_service.get_pmc_link_by_doi(doi)
        return pmc_info

class CrawlerService:
    def __init__(self):
        pass

    def html_to_lowest_level_markdown(self, html_content : str):
        soup = BeautifulSoup(html_content, 'lxml')
        markdown_output = []
        found_content = False

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
                if len(rows) > 1:
                    found_content = True
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

        if found_content == False:
            return None
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

    async def get_html_for_trial_id(self, trial_id : str):
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
                #TODO handle not found
                parsed_html = await asyncio.to_thread(self.extract_fourth_top_level_table, resp.text)
                markdown = await asyncio.to_thread(self.html_to_lowest_level_markdown, parsed_html)
                return markdown
            
        except ReadTimeout:
            raise Exception("Upstream request timed out")
        
class DoclingService:
    def __init__(self):
        self.sem = asyncio.Semaphore(1)

    async def parse_pdf(self, pdf_path : str) -> str:
        url = f"{DOCLING_URL}/v1/convert/file"

        path = Path(pdf_path)

        if not path.exists():
            raise FileNotFoundError(path)
        
        files = {
            "files": (path.name, path.open("rb"), "application/pdf"),
        }

        payload = {
            "from_formats": ["pdf"],
            "to_formats": ["md"],
            "image_export_mode": "placeholder",
            "ocr": False,
            "abort_on_error": False,
            "table_mode": "fast",
        }

        file_size_mb = path.stat().st_size / (1024 * 1024)
        timeout = 30 + int(file_size_mb) * 30

        async with self.sem:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, files=files, data=payload)
                    resp.raise_for_status()
            except ReadTimeout:
                raise Exception("Upstream request timed out")

        return resp.json()['document']['md_content']