"""Extension point for optional data attached to the reports of a project list.

A downstream deployable registers an enricher under a key; a client asks for it by passing that key
in the list endpoint's `include` query parameter, and gets the enricher's value for each report in
`ReportCuration.extensions[key]`. Without `include` nothing runs, so the core response, the services
and every other caller (e.g. an MCP head) never see enriched data.

Enrichment happens in the route function, after the service has checked access and built the page,
and only for the ids of that page.
"""

from typing import Any, Dict, List, Protocol, Sequence

from src.context import RequestContext
from src.utils.dto import Page, ReportCuration


class ReportEnricher(Protocol):
    key: str

    async def enrich(self, report_ids: Sequence[int], ctx: RequestContext) -> Dict[int, Any]:
        """The value for each of the given reports that has one, keyed by report id."""
        ...


class ReportEnrichers:
    def __init__(self) -> None:
        self._enrichers: Dict[str, ReportEnricher] = {}

    def register(self, enricher: ReportEnricher) -> None:
        self._enrichers[enricher.key] = enricher

    async def apply(self, page: Page[ReportCuration], include: List[str], ctx: RequestContext) -> Page[ReportCuration]:
        """Fills `extensions` of the page's reports for the requested keys; unknown keys are ignored."""
        report_ids = [report.reportId for report in page.items]
        for key in dict.fromkeys(include):
            enricher = self._enrichers.get(key)
            if enricher is None:
                continue
            values = await enricher.enrich(report_ids, ctx)
            for report in page.items:
                if report.reportId in values:
                    report.extensions[key] = values[report.reportId]
        return page


report_enrichers = ReportEnrichers()
