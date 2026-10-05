"""Extension point for work that runs on each report of a freshly uploaded project
once its embedding is computed and its PDF search has settled (see
wrapper.process_report).

Which postprocessors run is chosen per upload: the create-project request carries a
free-form `options` object, and each postprocessor decides from it whether it is
enabled. Downstream deployables register their implementations at startup.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Protocol, Sequence

from sqlalchemy import Select

if TYPE_CHECKING:  # the context imports the repositories, which import this module
    from ..context import RequestContext

logger = logging.getLogger(__name__)

PostprocessingOptions = Dict[str, Any]


class ReportPostprocessor(Protocol):
    def is_enabled(self, options: PostprocessingOptions) -> bool:
        """Whether this upload asked for this postprocessor."""
        ...

    async def prepare(
        self, project_id: str, report_ids: Sequence[int], options: PostprocessingOptions, ctx: "RequestContext"
    ) -> None:
        """Called once, before any report is processed (e.g. to mark every report as pending)."""
        ...

    async def process(
        self, report_id: int, project_id: str, options: PostprocessingOptions, ctx: "RequestContext"
    ) -> None:
        """Called per report after its embedding is stored and its PDF search has settled.
        `ctx` is a fresh session owned by this call; commit what you write."""
        ...

    def pending_report_ids(self) -> Select:
        """A single-column select of the report ids whose postprocessing has not finished.
        Such reports are not ready for review; a failed run counts as finished."""
        ...

    def tracked_report_ids(self) -> Select:
        """A single-column select of every report id this postprocessor was requested for
        (pending, finished or failed); drives the postprocessing progress of a project."""
        ...


class PostprocessorRegistry:
    def __init__(self) -> None:
        self._postprocessors: List[ReportPostprocessor] = []

    def register(self, postprocessor: ReportPostprocessor) -> None:
        self._postprocessors.append(postprocessor)

    def all(self) -> List[ReportPostprocessor]:
        return list(self._postprocessors)

    def enabled_for(self, options: PostprocessingOptions) -> List[ReportPostprocessor]:
        return [postprocessor for postprocessor in self._postprocessors if postprocessor.is_enabled(options)]

    def pending_report_ids_selects(self) -> List[Select]:
        return [postprocessor.pending_report_ids() for postprocessor in self._postprocessors]

    def tracked_report_ids_selects(self) -> List[Select]:
        return [postprocessor.tracked_report_ids() for postprocessor in self._postprocessors]


postprocessor_registry = PostprocessorRegistry()
