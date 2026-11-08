from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Integer, Select, String, any_, bindparam, cast, func, or_
from sqlalchemy.dialects.postgresql import ARRAY, insert as pg_insert
from sqlmodel import select, delete

from ...background.postprocessing import postprocessor_registry
from ..models import Report, ReportFields, ReportFlag, Study, StudyFields, Link, UpdateLink, UpdateReport, UpdateStudy
from ...utils.pdfs import PdfFiles
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple

class ReportRepository:
    """The reports of the core database (Report) and of the updates (UpdateReport), which share their ids, and the
    links of the reports of the updates (UpdateLink)."""

    def __init__(self, db : AsyncSession, user_id : str):
        self.db = db
        self.user_id = str(user_id)

    async def commit(self):
        return await self.db.commit()

    async def rollback(self):
        return await self.db.rollback()

    async def set_embedded(self, report_id: int, value: bool) -> None:
        """Mirrors Qdrant vector existence for one report of an update - call right after
        the caller itself upserts/deletes that report's point (see UpdateReport.embedded's
        comment in models.py for why this is denormalized). A report of the core database
        has nowhere to record this and is silently skipped - this state is only ever
        meaningful while the report is in its update. Commits on its own: every call site
        either has no other pending change worth grouping this with, or the pending change
        is fine to land at the same time - see the call sites themselves for why.
        """
        report = await self.db.get(UpdateReport, report_id)
        if report is None:
            return
        report.embedded = value
        await self.db.commit()

    async def get_update_report(self, report_id: int) -> Optional[UpdateReport]:
        """The report if it is one of an update; None for a report of the core database."""
        return await self.db.get(UpdateReport, report_id)

    async def set_fulltext_links(self, report_id: int, links: List[str]) -> None:
        """Persists a fresh OpenAlex fulltext-link lookup for one report of an update (see
        UpdateReport.fulltext_links's comment in models.py). A report of the core database
        has nowhere to cache this and is silently skipped - the caller then just re-fetches
        live next time.
        """
        report = await self.db.get(UpdateReport, report_id)
        if report is None:
            return
        report.fulltext_links = links
        await self.db.commit()

    async def set_referenced_dois(self, report_id: int, dois: List[str]) -> None:
        """Persists the DOIs a report of an update cites (see UpdateReport.referenced_dois's
        comment in models.py); silently skipped for a report of the core database, like
        set_fulltext_links.
        """
        report = await self.db.get(UpdateReport, report_id)
        if report is None:
            return
        report.referenced_dois = dois
        await self.db.commit()

    async def get_fulltext_links_for_reports(self, report_ids: List[int]) -> Dict[int, List[str]]:
        """Bulk read of the cached UpdateReport.fulltext_links column (see its comment
        in models.py) for a page of reports - the intake list's version of
        ReportService.get_fulltext_links, minus that method's live-OpenAlex fallback:
        a paginated list has too many rows to risk an uncached external call per row,
        so it's cache-only here (a report whose cache hasn't been populated yet just
        shows no links until the background job or a detail-view visit fills it in).
        """
        report_ids = report_ids or []
        if not report_ids:
            return {}

        stmt = (
            select(UpdateReport.id, UpdateReport.fulltext_links)
            .where(UpdateReport.id.in_(report_ids))
        )
        rows = (await self.db.execute(stmt)).all()
        return {report_id: (links or []) for report_id, links in rows}

    async def get_preliminary_trial_ids_for_reports(self, report_ids: List[int]) -> Dict[int, Optional[str]]:
        """Bulk read of the unconfirmed UpdateReport.preliminary_trial_id guess (see its
        comment in models.py) for a page of reports - same shape/purpose as
        get_fulltext_links_for_reports, for ReportCuration.preliminaryTrialId.
        """
        report_ids = report_ids or []
        if not report_ids:
            return {}

        stmt = (
            select(UpdateReport.id, UpdateReport.preliminary_trial_id)
            .where(UpdateReport.id.in_(report_ids))
        )
        rows = (await self.db.execute(stmt)).all()
        return {report_id: trial_id for report_id, trial_id in rows}

    async def stored_pdf_ids(self, project_id: str) -> Set[int]:
        """The reports of the project with a PDF file, for has_pdf_clause. Only the project's own reports that may
        have one are looked up, so neither the lookup nor the array of has_pdf_clause grows with the PDFs of the
        other projects."""
        stmt = (
            select(UpdateReport.id)
            .where(UpdateReport.project_id == project_id)
            .where(UpdateReport.auto_searched_pdf.is_(True))
            .where(UpdateReport.no_pdf.is_(False))
        )
        return PdfFiles.stored((await self.db.execute(stmt)).scalars().all())

    async def get_readiness_sets(self, report_ids: List[int]) -> Tuple[Set[int], Set[int]]:
        """The given reports of an update that are embedded (UpdateReport.embedded) and those
        that have a PDF: their PDF search has run (UpdateReport.auto_searched_pdf) and there
        is a file of theirs on the data volume (src/utils/pdfs.py), or they are marked as
        having none (no_pdf) - the same rule as has_pdf_clause. A report of the core database
        never appears in either returned set.
        """
        report_ids = report_ids or []
        if not report_ids:
            return set(), set()

        stmt = (
            select(UpdateReport.id, UpdateReport.embedded, UpdateReport.auto_searched_pdf, UpdateReport.no_pdf)
            .where(UpdateReport.id.in_(report_ids))
        )
        rows = (await self.db.execute(stmt)).all()
        embedded = {report_id for report_id, is_embedded, _, _ in rows if is_embedded}
        searched = [(report_id, no_pdf) for report_id, _, auto_searched, no_pdf in rows if auto_searched]
        stored = PdfFiles.stored(report_id for report_id, no_pdf in searched if not no_pdf)
        has_pdf = {report_id for report_id, no_pdf in searched if no_pdf or report_id in stored}
        return embedded, has_pdf

    @staticmethod
    def has_pdf_clause(stored_ids: Set[int]):
        """Whether a report of an update of a query on UpdateReport has a PDF (see
        get_readiness_sets), given the ids of the reports with a file (see stored_pdf_ids).
        The ids go in as one array."""
        stored = bindparam("stored_pdf_ids", sorted(stored_ids), type_=ARRAY(Integer))
        return UpdateReport.auto_searched_pdf.is_(True) & or_(UpdateReport.no_pdf.is_(True), UpdateReport.id == any_(stored))

    async def get_postprocessing_pending(self, report_ids: List[int]) -> Set[int]:
        """The given reports whose registered postprocessors (src/background/postprocessing.py)
        have not finished yet; such reports are not ready for review."""
        if not report_ids:
            return set()
        pending: Set[int] = set()
        for pending_select in postprocessor_registry.pending_report_ids_selects():
            rows = await self.db.execute(pending_select.where(pending_select.selected_columns[0].in_(report_ids)))
            pending.update(report_id for (report_id,) in rows.all())
        return pending

    async def get_postprocessing_progress(self, report_ids: List[int]) -> Tuple[int, int]:
        """(requested, finished) number of the given reports that were put through a registered
        postprocessor (src/background/postprocessing.py) and that have finished it."""
        if not report_ids:
            return 0, 0
        tracked: Set[int] = set()
        for tracked_select in postprocessor_registry.tracked_report_ids_selects():
            rows = await self.db.execute(tracked_select.where(tracked_select.selected_columns[0].in_(report_ids)))
            tracked.update(report_id for (report_id,) in rows.all())
        pending = await self.get_postprocessing_pending(report_ids)
        return len(tracked), len(tracked - pending)

    async def link_study(self, report_id: int, study_id: int, user_id : str = None) -> None:
        """Links a report of an update to a study - of the core database or of an update - in the scope `user_id`
        (this scope without), without touching its other links."""
        if user_id is None:
            user_id = self.user_id

        if await self.db.get(UpdateReport, report_id) is None:
            raise Exception("Report not found")
        if await self.db.get(UpdateStudy, study_id) is not None:
            target = {"update_study_id": study_id}
        elif await self.db.get(Study, study_id) is not None:
            target = {"study_id": study_id}
        else:
            raise Exception("Study not found")

        await self.db.execute(
            pg_insert(UpdateLink)
            .values(report_id=report_id, created_by=user_id, **target)
            .on_conflict_do_nothing()
        )
        await self.db.flush()

    async def unlink_study(self, report_id: int, study_id: int = None, user_id : str = None) -> None:
        """Removes the links of a report of an update in the scope `user_id` (this scope without), only that to
        `study_id` if it is given; the studies of the updates left without a link go as well."""
        if user_id is None:
            user_id = self.user_id

        if await self.db.get(UpdateReport, report_id) is None:
            raise Exception("Report not found")

        study = func.coalesce(UpdateLink.study_id, UpdateLink.update_study_id)
        stmt = delete(UpdateLink).where(UpdateLink.report_id == report_id).where(UpdateLink.created_by == user_id)
        if study_id is not None:
            stmt = stmt.where(study == study_id)
        drafts = (await self.db.execute(stmt.returning(UpdateLink.update_study_id))).scalars().all()
        await self.delete_orphaned_drafts([draft_id for draft_id in drafts if draft_id is not None])

    async def delete_orphaned_drafts(self, study_ids: List[int]) -> None:
        """Deletes the studies of the updates among `study_ids` that no link of an update has any more."""
        if not study_ids:
            return
        linked = select(UpdateLink.update_study_id).where(UpdateLink.update_study_id.isnot(None))
        await self.db.execute(delete(UpdateStudy).where(UpdateStudy.id.in_(study_ids)).where(UpdateStudy.id.not_in(linked)))
        await self.db.flush()

    async def get_linked_studies(self, report_id : int, date_from : Optional[datetime] = None, date_to : Optional[datetime] = None) -> Optional[List[StudyFields]]:
        """The studies the report is linked to: those of the core database for a report of the core database, those
        this scope linked it to for a report of an update. None if there is no such report."""
        result = await self.get_linked_studies_for_reports([report_id], date_from, date_to)
        return result.get(report_id)

    async def get_linked_studies_for_reports(
        self,
        report_ids: List[int],
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> Dict[int, List[StudyFields]]:
        """Return linked studies for multiple reports keyed by report ID (see get_linked_studies)."""
        report_ids = report_ids or []
        if not report_ids:
            return {}

        in_updates = set((await self.db.execute(select(UpdateReport.id).where(UpdateReport.id.in_(report_ids)))).scalars().all())
        in_core = set((await self.db.execute(select(Report.id).where(Report.id.in_(report_ids)))).scalars().all())
        if not in_updates and not in_core:
            return {}

        def dated(stmt, model):
            if date_from:
                stmt = stmt.where(model.created_at >= date_from)
            if date_to:
                stmt = stmt.where(model.created_at <= date_to)
            return stmt

        rows = []
        if in_core:
            rows += (await self.db.execute(dated(
                select(Link.report_id, Study).join(Study, Study.id == Link.study_id).where(Link.report_id.in_(in_core)),
                Study,
            ))).all()
        if in_updates:
            for model, column in ((Study, UpdateLink.study_id), (UpdateStudy, UpdateLink.update_study_id)):
                rows += (await self.db.execute(dated(
                    select(UpdateLink.report_id, model)
                    .join(model, model.id == column)
                    .where(UpdateLink.report_id.in_(in_updates))
                    .where(UpdateLink.created_by == self.user_id),
                    model,
                ))).all()

        studies_by_report: Dict[int, List[StudyFields]] = {rid: [] for rid in in_core | in_updates}
        for rid, study in rows:
            studies_by_report[rid].append(study)

        # Preserve the input ordering for convenience and drop non-existent report IDs
        return {rid: studies_by_report[rid] for rid in report_ids if rid in studies_by_report}

    async def get_all_reports(self, report_ids : Optional[List[int]] = None, date_from : Optional[datetime] = None, date_to: Optional[datetime] = None) -> List[ReportFields]:
        """The reports of the core database and of the updates."""
        reports: List[ReportFields] = []
        for model in (Report, UpdateReport):
            stmt = select(model).where((model.title.isnot(None)) | (model.abstract.isnot(None)))
            if report_ids:
                stmt = stmt.where(model.id.in_(report_ids))
            if date_from:
                stmt = stmt.where(model.created_at >= date_from)
            if date_to:
                stmt = stmt.where(model.created_at <= date_to)
            reports += (await self.db.execute(stmt)).scalars().all()
        return reports

    def _scope_links(self):
        """The links this scope made of the report of the row (UpdateReport): the same scoping
        get_linked_studies_for_reports() applies - the processed/new_study filters below
        must agree with it, since both describe the same "does this report have a study link
        this user can see" concept for the same list.
        """
        return (
            select(UpdateLink.id)
            .where(UpdateLink.report_id == UpdateReport.id)
            .where(UpdateLink.created_by == self.user_id)
        )

    async def query_project_reports_page(
        self,
        project_id: str,
        *,
        require_ready: bool,
        with_pdf: Optional[bool] = None,
        search: Optional[str] = None,
        processed: Optional[bool] = None,
        flagged: Optional[bool] = None,
        new_study: Optional[bool] = None,
        restrict_to_ids: Optional[Set[int]] = None,
        exclude_ids: Optional[Set[int]] = None,
        cursor_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[UpdateReport]:
        """One filtered, sorted, keyset-paginated SQL query for a project's report list -
        its callers (ProjectResourceService's get_reports_page/get_intake_reports_page/
        get_review_reports_page, src/services/project.py) used to fetch every report
        (+ every linked study, + every flag) in the project and filter/sort/slice that
        in Python; this does the equivalent filtering/ordering in the database and only
        ever returns up to `limit` + 1 rows (the extra row is a cheap "is there a next
        page" probe). count_project_reports counts the same filtered list.

        `require_ready`/`with_pdf` read UpdateReport.embedded (see models.py) instead of
        calling Qdrant, and whether a report has a PDF from one listing of the PDF folder
        (stored_pdf_ids, has_pdf_clause) instead of per report.
        `processed`/`flagged`/`new_study` are None ("any", no filter), True ("only") or
        False ("exclude") - the FilterMode -> bool translation happens in
        ProjectResourceService (src/services/project.py), which owns that enum
        (src/utils/dto.py); this layer only knows plain booleans. A new study is one created
        in the update, or one of the core database entered after the report (one merged from
        the update).
        `restrict_to_ids`, when given, narrows to that id set - used by the review
        endpoint's consensus/reviewed/fully-annotated filters, which need annotation rows
        this method has no reason to know about. `exclude_ids` leaves that id set out - used
        by the curation view for the reports the caller has committed.
        """
        stmt = await self._project_reports_stmt(
            project_id,
            require_ready=require_ready,
            with_pdf=with_pdf,
            search=search,
            processed=processed,
            flagged=flagged,
            new_study=new_study,
            restrict_to_ids=restrict_to_ids,
            exclude_ids=exclude_ids,
        )
        if cursor_id is not None:
            stmt = stmt.where(UpdateReport.id > cursor_id)
        stmt = stmt.order_by(UpdateReport.id).limit(limit + 1)

        return (await self.db.execute(stmt)).scalars().all()

    async def count_project_reports(self, project_id: str, **filters) -> int:
        """How many reports query_project_reports_page pages through with these filters (the same keywords, without
        the cursor and limit), all pages together."""
        stmt = await self._project_reports_stmt(project_id, **filters)
        return (await self.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    async def _project_reports_stmt(
        self,
        project_id: str,
        *,
        require_ready: bool,
        with_pdf: Optional[bool] = None,
        search: Optional[str] = None,
        processed: Optional[bool] = None,
        flagged: Optional[bool] = None,
        new_study: Optional[bool] = None,
        restrict_to_ids: Optional[Set[int]] = None,
        exclude_ids: Optional[Set[int]] = None,
    ) -> Select:
        """The filtered select of a project's report list, unordered and unpaged (see query_project_reports_page)."""
        search = search.strip() if search else None

        stmt = (
            select(UpdateReport)
            .where(UpdateReport.project_id == project_id)
            .where(UpdateReport.auto_searched_pdf.is_(True))
            .where((UpdateReport.title.isnot(None)) | (UpdateReport.abstract.isnot(None)))
        )

        if require_ready or with_pdf is not None:
            has_pdf = self.has_pdf_clause(await self.stored_pdf_ids(project_id))

        if require_ready:
            stmt = stmt.where(UpdateReport.embedded.is_(True)).where(has_pdf)
            for pending_select in postprocessor_registry.pending_report_ids_selects():
                stmt = stmt.where(UpdateReport.id.not_in(pending_select))

        if with_pdf is not None:
            stmt = stmt.where(has_pdf if with_pdf else ~has_pdf)

        if restrict_to_ids is not None:
            stmt = stmt.where(UpdateReport.id.in_(restrict_to_ids))

        if exclude_ids:
            stmt = stmt.where(UpdateReport.id.not_in(exclude_ids))

        if search:
            # Escape LIKE metacharacters so a literal "%" or "_" in the search term is
            # matched literally (the substring match this replaces was plain Python
            # `in`, which had no wildcard semantics at all).
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            stmt = stmt.where(
                UpdateReport.title.ilike(pattern, escape="\\")
                | UpdateReport.abstract.ilike(pattern, escape="\\")
                | cast(UpdateReport.id, String).ilike(pattern, escape="\\")
            )

        if processed is not None:
            processed_exists = self._scope_links().exists()
            stmt = stmt.where(processed_exists if processed else ~processed_exists)

        if new_study is not None:
            new_study_exists = or_(
                self._scope_links().where(UpdateLink.update_study_id.isnot(None)).exists(),
                self._scope_links()
                .join(Study, Study.id == UpdateLink.study_id)
                .where(Study.created_at > UpdateReport.created_at)
                .exists(),
            )
            if new_study:
                stmt = stmt.where(new_study_exists)
            else:
                # "Existing study" means the report is linked to a study, none of them new -
                # unlinked (unprocessed) reports have no study at all, so they're neither.
                stmt = stmt.where(self._scope_links().exists(), ~new_study_exists)

        if flagged is not None:
            flagged_exists = (
                select(ReportFlag.report_id)
                .where(ReportFlag.report_id == UpdateReport.id)
                .where(ReportFlag.created_by == self.user_id)
                .where(func.length(func.trim(ReportFlag.message)) > 0)
            ).exists()
            stmt = stmt.where(flagged_exists if flagged else ~flagged_exists)

        return stmt

    async def get_report_by_id(self, report_id: int) -> Optional[ReportFields]:
        """The report of the id, of an update (UpdateReport) or of the core database (Report)."""
        return await self.db.get(UpdateReport, report_id) or await self.db.get(Report, report_id)

    async def get_report_flag(self, report_id: int) -> Optional[ReportFlag]:
        stmt = (
            select(ReportFlag)
            .where(ReportFlag.report_id == report_id)
            .where(ReportFlag.created_by == self.user_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def upsert_report_flag(self, report_id: int, message: str, public: bool = False) -> ReportFlag:
        """Flags a report of an update in this scope (raises ValueError for any other report)."""
        report = await self.db.get(UpdateReport, report_id)
        if not report:
            raise ValueError("Report not found")

        stmt = (
            select(ReportFlag)
            .where(ReportFlag.report_id == report_id)
            .where(ReportFlag.created_by == self.user_id)
        )
        report_flag = (await self.db.execute(stmt)).scalar_one_or_none()

        if report_flag is None:
            report_flag = ReportFlag(
                report_id=report_id,
                created_by=self.user_id,
                message=message,
                public=public,
            )
            self.db.add(report_flag)
        else:
            report_flag.message = message
            report_flag.public = public

        return report_flag

    async def delete_report_flag(self, report_id: int) -> bool:
        stmt = (
            delete(ReportFlag)
            .where(ReportFlag.report_id == report_id)
            .where(ReportFlag.created_by == self.user_id)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return bool(result.rowcount)

    async def get_report_flags_for_reports(self, report_ids: List[int]) -> Dict[int, ReportFlag]:
        report_ids = report_ids or []
        if not report_ids:
            return {}

        stmt = (
            select(ReportFlag)
            .where(ReportFlag.report_id.in_(report_ids))
            .where(ReportFlag.created_by == self.user_id)
        )
        flags = (await self.db.execute(stmt)).scalars().all()
        return {flag.report_id: flag for flag in flags}
