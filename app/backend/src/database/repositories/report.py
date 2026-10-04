from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import String, cast, func, or_
from sqlmodel import select, delete

from ..models import Report, ReportAdded, Study, StudyAdded, StudyReport, StudyReportAdded, FulltextExtractions, ReportFlag
from typing import List, Dict, Any, Optional, Set, Tuple

import os

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
PDF_PATH = os.path.join(DATABASE_VOLUME,"resources", "pdfs")

class ReportRepository:
    def __init__(self, db : AsyncSession, user_id : str):
        self.db = db
        self.user_id = str(user_id)

    async def commit(self):
        return await self.db.commit()

    async def rollback(self):
        return await self.db.rollback()

    async def set_embedded(self, report_id: int, value: bool) -> None:
        """Mirrors Qdrant vector existence for one report - call right after the caller
        itself upserts/deletes that report's point (see report_added.embedded's comment
        in models.py for why this is denormalized, and why it lives on the project
        association rather than on Report itself). A report with no report_added row (no
        current project association) has nowhere to record this and is silently skipped -
        this state is only ever meaningful for the lifetime of that association. Commits
        on its own: every call site either has no other pending change worth grouping
        this with, or the pending change is fine to land at the same time - see the call
        sites themselves for why.
        """
        report_added = await self.db.get(ReportAdded, report_id)
        if report_added is None:
            return
        report_added.embedded = value
        await self.db.commit()

    async def get_report_added(self, report_id: int) -> Optional[ReportAdded]:
        return await self.db.get(ReportAdded, report_id)

    async def set_fulltext_links(self, report_id: int, links: List[str]) -> None:
        """Persists a fresh OpenAlex fulltext-link lookup for one report (see
        report_added.fulltext_links's comment in models.py). A report with no
        report_added row (no current project association) has nowhere to cache this
        and is silently skipped - the caller then just re-fetches live next time.
        """
        report_added = await self.db.get(ReportAdded, report_id)
        if report_added is None:
            return
        report_added.fulltext_links = links
        await self.db.commit()

    async def set_referenced_dois(self, report_id: int, dois: List[str]) -> None:
        """Persists the DOIs a report cites (see report_added.referenced_dois's comment in
        models.py); silently skipped for a report with no report_added row, like
        set_fulltext_links.
        """
        report_added = await self.db.get(ReportAdded, report_id)
        if report_added is None:
            return
        report_added.referenced_dois = dois
        await self.db.commit()

    async def get_fulltext_links_for_reports(self, report_ids: List[int]) -> Dict[int, List[str]]:
        """Bulk read of the cached report_added.fulltext_links column (see its comment
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
            select(ReportAdded.report_id, ReportAdded.fulltext_links)
            .where(ReportAdded.report_id.in_(report_ids))
        )
        rows = (await self.db.execute(stmt)).all()
        return {report_id: (links or []) for report_id, links in rows}

    async def get_preliminary_trial_ids_for_reports(self, report_ids: List[int]) -> Dict[int, Optional[str]]:
        """Bulk read of the unconfirmed report_added.trial_registration_id guess (see its
        comment in models.py) for a page of reports - same shape/purpose as
        get_fulltext_links_for_reports, for ReportCuration.preliminaryTrialId.
        """
        report_ids = report_ids or []
        if not report_ids:
            return {}

        stmt = (
            select(ReportAdded.report_id, ReportAdded.trial_registration_id)
            .where(ReportAdded.report_id.in_(report_ids))
        )
        rows = (await self.db.execute(stmt)).all()
        return {report_id: trial_id for report_id, trial_id in rows}

    async def set_trial_registration_id_if_empty(self, report_id: int, trial_id: str) -> None:
        """Persists a fulltext-parsed trial id guess to report_added (see its
        trial_registration_id comment in models.py) - never overwrites an existing value,
        from either this or the .ris-upload guess (ProjectRepository.add_new_project),
        since this is a best-effort guess for a researcher to confirm, not authoritative
        data. A report with no report_added row (no current project association) has
        nowhere to record this and is silently skipped.
        """
        report_added = await self.db.get(ReportAdded, report_id)
        if report_added is None or report_added.trial_registration_id:
            return
        report_added.trial_registration_id = trial_id
        await self.db.flush()

    async def get_readiness_sets(self, report_ids: List[int]) -> Tuple[Set[int], Set[int]]:
        """Plain SQL read of the embedded/has_pdf columns for the given reports -
        replaces what used to be a live Qdrant retrieve + per-file filesystem stat call
        on every read (see ProjectResourceService.get_vectorized_and_ready_report_ids).
        A report with no report_added row never appears in either returned set.
        """
        report_ids = report_ids or []
        if not report_ids:
            return set(), set()

        stmt = (
            select(ReportAdded.report_id, ReportAdded.embedded, ReportAdded.has_pdf)
            .where(ReportAdded.report_id.in_(report_ids))
        )
        rows = (await self.db.execute(stmt)).all()
        embedded = {report_id for report_id, is_embedded, _ in rows if is_embedded}
        has_pdf = {report_id for report_id, _, pdf_ready in rows if pdf_ready}
        return embedded, has_pdf

    async def _remove_orphaned_studies(self, affected_study_ids : set) -> List[int]:
        """
        Helper function to remove orphaned studies.

        Args:
            affected_study_ids: Set of study IDs that were affected by link deletions
            session: The database session

        Returns:
            List of study IDs that were deleted
        """
        if not affected_study_ids:
            return []

        # Get studies that were added by users (tracked in StudyAdded)
        stmt = select(StudyAdded.study_id).where(StudyAdded.study_id.in_(affected_study_ids))
        newly_added_studies = set((await self.db.execute(stmt)).scalars().all())

        if not newly_added_studies:
            return []

        # Check which of these studies still have remaining links
        stmt = select(StudyReport.study_id).where(StudyReport.study_id.in_(newly_added_studies))
        still_linked = set((await self.db.execute(stmt)).scalars().all())

        # Orphaned studies are those with no remaining links
        orphaned_studies = newly_added_studies - still_linked

        if not orphaned_studies:
            return []

        orphan_list = list(orphaned_studies)
        # Delete orphaned studies (cascades to StudyAdded)
        await self.db.execute(
            delete(Study).where(Study.id.in_(orphan_list))
        )

        await self.db.flush()
        return orphan_list

    async def link_study(self, report_id: int, study_id: int, user_id : str = None) -> Dict[str, Any]:
        """
        Append a single study link to a report without touching existing links.
        """
        if user_id is None:
            user_id = self.user_id

        # Validate report exists
        report = await self.db.get(Report, report_id)
        if not report:
            raise Exception("Report not found")

        # Validate study exists
        study = await self.db.get(Study, study_id)
        if not study:
            raise Exception("Study not found")

        # Avoid duplicate links
        existing_stmt = (
            select(StudyReport)
            .where(StudyReport.report_id == report_id)
            .where(StudyReport.study_id == study_id)
        )
        link = (await self.db.execute(existing_stmt)).scalar_one_or_none()

        if not link:
            # Create new link and track creator
            link = StudyReport(report_id=report_id, study_id=study_id)
            self.db.add(link)
            await self.db.flush()

        self.db.add(StudyReportAdded(
            study_report_id=link.id,
            created_by=user_id
        ))

        await self.db.flush()

    async def unlink_study(self, report_id: int, study_id: int = None, user_id : str = None) -> Dict[str, Any]:
        """
        Internal implementation to delete links between a report and studies.
        If study_id is provided, only that link is removed.
        Only deletes links created by the specified user or links with no creator.
        """
        if user_id is None:
            user_id = self.user_id

        # Validate report exists
        report = await self.db.get(Report, report_id)
        if not report:
            raise Exception("Report not found")

        # Build query joining StudyReport with StudyReportAdded
        stmt = (
            select(StudyReport, StudyReportAdded.created_by)
            .outerjoin(StudyReportAdded, StudyReport.id == StudyReportAdded.study_report_id)
            .where(StudyReport.report_id == report_id)
        )

        if study_id is not None:
            stmt = stmt.where(StudyReport.study_id == study_id)

        # If user is provided, filter by created_by
        if user_id:
            stmt = stmt.where(StudyReportAdded.created_by == user_id)

        # Fetch all matching links
        rows = (await self.db.execute(stmt)).all()

        deleted_links: List[Dict[str, int]] = [
            {"report_id": sr.report_id, "study_id": sr.study_id}
            for sr, _ in rows
        ]
        deleted_orphans = []

        # Bulk delete matching links
        if rows:
            study_report_ids = [sr.id for sr, _ in rows]
            await self.db.execute(
                delete(StudyReport).where(StudyReport.id.in_(study_report_ids))
            )
            # Check if some of the affected studies are now orphans and delete them
            affected_studies = {item['study_id'] for item in deleted_links}
            deleted_orphans = await self._remove_orphaned_studies(affected_studies)

        await self.db.flush()

    async def get_linked_studies(self, report_id : int, date_from : Optional[str] = None, date_to : Optional[str] = None):
        report = await self.db.get(Report, report_id)
        if not report:
            return None

        stmt = (
            select(Study)
            .join(StudyReport, StudyReport.study_id == Study.id)
            .outerjoin(StudyReportAdded, StudyReport.id == StudyReportAdded.study_report_id)
            .where(StudyReport.report_id == report_id)
        )

        # If user is provided, filter by created_by
        if self.user_id:
            stmt = stmt.where((StudyReportAdded.created_by == self.user_id) | (StudyReportAdded.created_by.is_(None)))

        if date_from:
            stmt = stmt.where(Study.date_entered >= date_from)
        if date_to:
            stmt = stmt.where(Study.date_entered <= date_to)

        return (await self.db.execute(stmt)).scalars().all()

    async def get_linked_studies_for_reports(
        self,
        report_ids: List[int],
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[int, List[Study]]:
        """Return linked studies for multiple reports keyed by report ID."""
        report_ids = report_ids or []
        if not report_ids:
            return {}

        # Filter out non-existent reports to keep results consistent with get_linked_studies()
        existing_stmt = select(Report.id).where(Report.id.in_(report_ids))
        existing_ids = set((await self.db.execute(existing_stmt)).scalars().all())
        if not existing_ids:
            return {}

        stmt = (
            select(StudyReport.report_id, Study)
            .join(Study, Study.id == StudyReport.study_id)
            .outerjoin(StudyReportAdded, StudyReport.id == StudyReportAdded.study_report_id)
            .where(StudyReport.report_id.in_(existing_ids))
        )

        if self.user_id:
            stmt = stmt.where((StudyReportAdded.created_by == self.user_id) | (StudyReportAdded.created_by.is_(None)))

        if date_from:
            stmt = stmt.where(Study.date_entered >= date_from)
        if date_to:
            stmt = stmt.where(Study.date_entered <= date_to)

        rows = (await self.db.execute(stmt)).all()

        studies_by_report: Dict[int, List[Study]] = {rid: [] for rid in existing_ids}
        for rid, study in rows:
            studies_by_report.setdefault(rid, []).append(study)

        # Preserve the input ordering for convenience and drop non-existent report IDs
        ordered_result: Dict[int, List[Study]] = {}
        for rid in report_ids:
            if rid in studies_by_report:
                ordered_result[rid] = studies_by_report[rid]

        return ordered_result

    async def get_all_reports(self, report_ids : Optional[List[int]] = None, date_from : Optional[str] = None, date_to: Optional[str] = None) -> List[Report]:
        stmt = select(Report).where((Report.title.isnot(None)) | (Report.abstract.isnot(None)))
        if report_ids:
            stmt = stmt.where(Report.id.in_(report_ids))
        # date_entered filtering (string compare works with ISO-like 'YYYY-MM-DD HH:MM:SS')
        if date_from:
            stmt = stmt.where(Report.date_entered >= date_from)
        if date_to:
            stmt = stmt.where(Report.date_entered <= date_to)
        return (await self.db.execute(stmt)).scalars().all()

    def _user_scoped_linked_study_query(self, base_query):
        """Same "created by this user, or unattributed" scoping
        get_linked_studies_for_reports() applies - the processed/new_study filters below
        must agree with that method's own scoping, since both describe the same
        "does this report have a study link this user can see" concept for the same list.
        """
        if not self.user_id:
            return base_query
        return base_query.where(
            or_(StudyReportAdded.created_by == self.user_id, StudyReportAdded.created_by.is_(None))
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
        cursor_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[Report]:
        """One filtered, sorted, keyset-paginated SQL query for a project's report list -
        its callers (ProjectResourceService's get_reports_page/get_intake_reports_page/
        get_review_reports_page, src/services/project.py) used to fetch every report
        (+ every linked study, + every flag) in the project and filter/sort/slice that
        in Python; this does the equivalent filtering/ordering in the database and only
        ever returns up to `limit` + 1 rows (the extra row is a cheap "is there a next
        page" probe, so the caller never needs a separate COUNT).

        `require_ready`/`with_pdf` read report_added.embedded/report_added.has_pdf directly
        (see models.py) instead of calling Qdrant or stat()-ing the filesystem per report.
        `processed`/`flagged`/`new_study` are None ("any", no filter), True ("only") or
        False ("exclude") - the FilterMode -> bool translation happens in
        ProjectResourceService (src/services/project.py), which owns that enum
        (src/utils/dto.py); this layer only knows plain booleans.
        `restrict_to_ids`, when given, narrows to that id set - used by the review
        endpoint's consensus/reviewed/fully-annotated filters, which need annotation rows
        this method has no reason to know about.
        """
        search = search.strip() if search else None

        stmt = (
            select(Report)
            .join(ReportAdded, ReportAdded.report_id == Report.id)
            .where(ReportAdded.project_id == project_id)
            .where(ReportAdded.auto_searched_pdf.is_(True))
            .where((Report.title.isnot(None)) | (Report.abstract.isnot(None)))
        )

        if require_ready:
            stmt = stmt.where(ReportAdded.embedded.is_(True)).where(ReportAdded.has_pdf.is_(True))

        if with_pdf is not None:
            stmt = stmt.where(ReportAdded.has_pdf.is_(with_pdf))

        if restrict_to_ids is not None:
            stmt = stmt.where(Report.id.in_(restrict_to_ids))

        if cursor_id is not None:
            stmt = stmt.where(Report.id > cursor_id)

        if search:
            # Escape LIKE metacharacters so a literal "%" or "_" in the search term is
            # matched literally (the substring match this replaces was plain Python
            # `in`, which had no wildcard semantics at all).
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            stmt = stmt.where(
                Report.title.ilike(pattern, escape="\\")
                | Report.abstract.ilike(pattern, escape="\\")
                | cast(Report.id, String).ilike(pattern, escape="\\")
            )

        if processed is not None:
            processed_exists = self._user_scoped_linked_study_query(
                select(StudyReport.report_id)
                .select_from(StudyReport)
                .outerjoin(StudyReportAdded, StudyReportAdded.study_report_id == StudyReport.id)
                .where(StudyReport.report_id == Report.id)
            ).exists()
            stmt = stmt.where(processed_exists if processed else ~processed_exists)

        if new_study is not None:
            new_study_exists = self._user_scoped_linked_study_query(
                select(StudyReport.report_id)
                .select_from(StudyReport)
                .outerjoin(StudyReportAdded, StudyReportAdded.study_report_id == StudyReport.id)
                .join(Study, Study.id == StudyReport.study_id)
                .where(StudyReport.report_id == Report.id)
                .where(Study.date_entered > Report.date_entered)
            ).exists()
            stmt = stmt.where(new_study_exists if new_study else ~new_study_exists)

        if flagged is not None:
            flagged_exists = (
                select(ReportFlag.report_id)
                .where(ReportFlag.report_id == Report.id)
                .where(ReportFlag.created_by == self.user_id)
                .where(func.length(func.trim(ReportFlag.message)) > 0)
            ).exists()
            stmt = stmt.where(flagged_exists if flagged else ~flagged_exists)

        stmt = stmt.order_by(Report.id).limit(limit + 1)

        return (await self.db.execute(stmt)).scalars().all()

    async def get_report_by_id(self, report_id: int) -> Report:
        return await self.db.get(Report, report_id)

    async def delete_report(self, report_id: int) -> bool:
        stmt = delete(Report).where(Report.id == report_id)
        result = await self.db.execute(stmt)
        await self.db.flush()
        return bool(result.rowcount)

    async def get_report_flag(self, report_id: int) -> Optional[ReportFlag]:
        stmt = (
            select(ReportFlag)
            .where(ReportFlag.report_id == report_id)
            .where(ReportFlag.created_by == self.user_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def upsert_report_flag(self, report_id: int, message: str, public: bool = False) -> ReportFlag:

        report = await self.db.get(Report, report_id)
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

    async def set_study_report_confirmation(self, report_id: int, study_id: int, confirmed: bool) -> bool:
        """
        Set confirmation state for a report-study link tracked in StudyReportAdded.
        The StudyReportAdded row is resolved through the study_report view by report/study ids.
        """
        stmt = (
            select(StudyReportAdded)
            .join(StudyReport, StudyReport.id == StudyReportAdded.study_report_id)
            .where(StudyReport.report_id == report_id)
            .where(StudyReport.study_id == study_id)
        )
        study_report_added = (await self.db.execute(stmt)).scalar_one_or_none()

        if not study_report_added:
            return False

        study_report_added.confirmed = confirmed
        await self.db.flush()
        return True


    async def get_pdf_availabilities(self, report_ids: List[int]) -> List[int]:
        report_ids = report_ids or []
        if not report_ids:
            return []

        # Get all ReportAdded entries for the given report_ids
        report_added_stmt = select(ReportAdded.report_id, ReportAdded.auto_searched_pdf).where(ReportAdded.report_id.in_(report_ids))
        report_added_rows = (await self.db.execute(report_added_stmt)).all()
        report_added_map = {rid: auto for rid, auto in report_added_rows}

        # Get all reports (with report_number) for the given report_ids
        report_stmt = select(Report.id, Report.report_number).where(Report.id.in_(report_ids)).where(Report.report_number >= 0)
        report_rows = (await self.db.execute(report_stmt)).all()

        result = []
        for report_id, report_number in report_rows:
            # If there is a ReportAdded entry, require auto_searched_pdf == True
            if report_id in report_added_map:
                if not report_added_map[report_id]:
                    continue
            # If there is no ReportAdded entry, ignore auto_searched_pdf
            if report_number == 0:
                result.append(report_id)
                continue
            pdf_name = str(report_number).zfill(5) + ".pdf"
            if os.path.exists(os.path.join(PDF_PATH, pdf_name)):
                result.append(report_id)
        return result

    def _compute_has_pdf(self, report: Report, report_added: ReportAdded) -> bool:
        """Single-report version of get_pdf_availabilities()'s rules - kept in sync with
        that method's logic since both express the same "does this report have a usable
        PDF" rule, just for different callers (a live filter there, a value to
        persist here). Unlike get_pdf_availabilities, always has a report_added row to
        check (see recompute_has_pdf), so - unlike that method - always requires
        auto_searched_pdf rather than treating "no report_added row" as an ignore case.
        The auto_searched_pdf gate is checked first, matching get_pdf_availabilities'
        order: report_number == 0 does NOT bypass it there, only the PDF-file check.
        """
        if not report_added.auto_searched_pdf:
            return False
        if report.report_number is None or report.report_number < 0:
            return False
        if report.report_number == 0:
            return True

        pdf_name = str(report.report_number).zfill(5) + ".pdf"
        return os.path.exists(os.path.join(PDF_PATH, pdf_name))

    async def recompute_has_pdf(self, report_id: int) -> bool:
        """Re-derives and persists report_added.has_pdf for one report - call after
        anything that could change its outcome (PDF written/removed, report_number
        changed, or the project's auto_searched_pdf flag flipped). A report with no
        report_added row (no current project association) has nowhere to record this and
        is silently skipped. Commits on its own - see set_embedded()'s docstring for why
        that's the right tradeoff at these call sites.
        """
        report_added = await self.db.get(ReportAdded, report_id)
        if report_added is None:
            return False
        report = await self.db.get(Report, report_id)
        if report is None:
            return False
        value = self._compute_has_pdf(report, report_added)
        report_added.has_pdf = value
        await self.db.commit()
        return value

    async def get_pdf_numbers_by_report_id(self, report_id: int) -> int:
        """
        Returns the PDF report number for a given report ID.
        """
        report = await self.db.get(Report, report_id)
        if not report:
            return None
        if report.report_number is None:
            return -1   # report found, but report_number is NULL
        return report.report_number

    async def assign_pdf_numbers_for_report_id(self, report_id: int) -> int:
        """
        Assigns a unique PDF report number to the given report if it does not already have one.
        Returns the assigned or existing report number.
        """
        report = await self.db.get(Report, report_id)
        if not report:
            return None  # Report not found

        if report.report_number is not None and report.report_number > 0:
            return report.report_number  # Already assigned

        # Find the current max report_number
        stmt = (
            select(Report.report_number)
            .where(Report.report_number.isnot(None))
            .order_by(Report.report_number.desc())
        )
        max_number = (await self.db.execute(stmt)).scalars().first()
        next_number = (max_number or 0) + 1

        report.report_number = next_number
        await self.db.flush()
        return next_number

    async def save_report_metadata_field(self, report_id: int, field: str, value: Any):
        stmt = select(FulltextExtractions).where(FulltextExtractions.report_id == report_id)
        extraction = (await self.db.execute(stmt)).scalar_one_or_none()
        if not extraction:
            # Optionally create a new record if not found
            data = {}
            extraction = FulltextExtractions(report_id=report_id, data=data)
            self.db.add(extraction)
        else:
            data = extraction.data or {}
        data[field] = value
        extraction.data = data
        await self.db.flush()

    async def load_report_metadata(self, report_id : int):
        stmt = select(FulltextExtractions).where(FulltextExtractions.report_id == report_id)
        existing = (await self.db.execute(stmt)).scalar_one_or_none()

        if existing:
            return existing.data
        return None
