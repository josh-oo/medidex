from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, delete

from ..models import Report, ReportAdded, Study, StudyAdded, StudyReport, StudyReportAdded, FulltextExtractions, ReportFlag
from typing import List, Dict, Any, Optional

import os

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")
FULLTEXT_PATH = os.path.join(DATABASE_VOLUME,"resources", "fulltexts")

class ReportRepository:
    def __init__(self, db : AsyncSession, user_id : str):
        self.db = db
        self.user_id = str(user_id)

    async def commit(self):
        return await self.db.commit()
    
    async def roolback(self):
        return await self.db.rollback()

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
        stmt = select(StudyAdded.CRGStudyID).where(StudyAdded.CRGStudyID.in_(affected_study_ids))
        newly_added_studies = set((await self.db.execute(stmt)).scalars().all())
        
        if not newly_added_studies:
            return []
        
        # Check which of these studies still have remaining links
        stmt = select(StudyReport.CRGStudyID).where(StudyReport.CRGStudyID.in_(newly_added_studies))
        still_linked = set((await self.db.execute(stmt)).scalars().all())
        
        # Orphaned studies are those with no remaining links
        orphaned_studies = newly_added_studies - still_linked
        
        if not orphaned_studies:
            return []
        
        orphan_list = list(orphaned_studies)
        # Delete orphaned studies (cascades to StudyAdded)
        await self.db.execute(
            delete(Study).where(Study.CRGStudyID.in_(orphan_list))
        )
        
        self.db.flush()
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
            .where(StudyReport.CRGReportID == report_id)
            .where(StudyReport.CRGStudyID == study_id)
        )
        link = (await self.db.execute(existing_stmt)).scalar_one_or_none()

        if not link:
            # Create new link and track creator
            link = StudyReport(CRGReportID=report_id, CRGStudyID=study_id)
            self.db.add(link)
            await self.db.flush()

        self.db.add(StudyReportAdded(
            StudyReportID=link.StudyReportID,
            CreatedBy=user_id
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
            select(StudyReport, StudyReportAdded.CreatedBy)
            .outerjoin(StudyReportAdded, StudyReport.StudyReportID == StudyReportAdded.StudyReportID)
            .where(StudyReport.CRGReportID == report_id)
        )
        
        if study_id is not None:
            stmt = stmt.where(StudyReport.CRGStudyID == study_id)

        # If user is provided, filter by CreatedBy
        if user_id:
            stmt = stmt.where(StudyReportAdded.CreatedBy == user_id)

        # Fetch all matching links
        rows = (await self.db.execute(stmt)).all()

        deleted_links: List[Dict[str, int]] = [
            {"CRGReportID": sr.CRGReportID, "CRGStudyID": sr.CRGStudyID}
            for sr, _ in rows
        ]
        deleted_orphans = []

        # Bulk delete matching links
        if rows:
            study_report_ids = [sr.StudyReportID for sr, _ in rows]
            await self.db.execute(
                delete(StudyReport).where(StudyReport.StudyReportID.in_(study_report_ids))
            )
            # Check if some of the affected studies are now orphans and delete them
            affected_studies = {item['CRGStudyID'] for item in deleted_links}
            deleted_orphans = await self._remove_orphaned_studies(affected_studies)

        await self.db.flush()
        
    async def get_linked_studies(self, report_id : int, date_from : Optional[str] = None, date_to : Optional[str] = None):
        report = await self.db.get(Report, report_id)
        if not report:
            return None
        
        stmt = (
            select(Study)
            .join(StudyReport, StudyReport.CRGStudyID == Study.CRGStudyID)
            .outerjoin(StudyReportAdded, StudyReport.StudyReportID == StudyReportAdded.StudyReportID)
            .where(StudyReport.CRGReportID == report_id)
        )
        
        # If user is provided, filter by CreatedBy
        if self.user_id:
            stmt = stmt.where((StudyReportAdded.CreatedBy == self.user_id) | (StudyReportAdded.CreatedBy.is_(None)))
        
        if date_from:
            stmt = stmt.where(Study.DateEntered >= date_from)
        if date_to:
            stmt = stmt.where(Study.DateEntered <= date_to)
        
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
        existing_stmt = select(Report.CRGReportID).where(Report.CRGReportID.in_(report_ids))
        existing_ids = set((await self.db.execute(existing_stmt)).scalars().all())
        if not existing_ids:
            return {}

        stmt = (
            select(StudyReport.CRGReportID, Study)
            .join(Study, Study.CRGStudyID == StudyReport.CRGStudyID)
            .outerjoin(StudyReportAdded, StudyReport.StudyReportID == StudyReportAdded.StudyReportID)
            .where(StudyReport.CRGReportID.in_(existing_ids))
        )

        if self.user_id:
            stmt = stmt.where((StudyReportAdded.CreatedBy == self.user_id) | (StudyReportAdded.CreatedBy.is_(None)))

        if date_from:
            stmt = stmt.where(Study.DateEntered >= date_from)
        if date_to:
            stmt = stmt.where(Study.DateEntered <= date_to)

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
        stmt = select(Report).where((Report.Title.isnot(None)) | (Report.Abstract.isnot(None)))
        if report_ids:
            stmt = stmt.where(Report.CRGReportID.in_(report_ids))
        # Dateentered filtering (string compare works with ISO-like 'YYYY-MM-DD HH:MM:SS')
        if date_from:
            stmt = stmt.where(Report.Dateentered >= date_from)
        if date_to:
            stmt = stmt.where(Report.Dateentered <= date_to)
        return (await self.db.execute(stmt)).scalars().all()
    
    async def get_report_by_id(self, report_id: int) -> Report:
        return await self.db.get(Report, report_id)

    async def delete_report(self, report_id: int) -> bool:
        stmt = delete(Report).where(Report.CRGReportID == report_id)
        result = await self.db.execute(stmt)
        await self.db.flush()
        return bool(result.rowcount)

    async def get_report_flag(self, report_id: int) -> Optional[ReportFlag]:
        stmt = (
            select(ReportFlag)
            .where(ReportFlag.CRGReportID == report_id)
            .where(ReportFlag.CreatedBy == self.user_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def upsert_report_flag(self, report_id: int, message: str, public: bool = False) -> ReportFlag:

        report = await self.db.get(Report, report_id)
        if not report:
            raise ValueError("Report not found")

        stmt = (
            select(ReportFlag)
            .where(ReportFlag.CRGReportID == report_id)
            .where(ReportFlag.CreatedBy == self.user_id)
        )
        report_flag = (await self.db.execute(stmt)).scalar_one_or_none()

        if report_flag is None:
            report_flag = ReportFlag(
                CRGReportID=report_id,
                CreatedBy=self.user_id,
                Message=message,
                Public=public,
            )
            self.db.add(report_flag)
        else:
            report_flag.Message = message
            report_flag.Public = public

        return report_flag

    async def delete_report_flag(self, report_id: int) -> bool:
        stmt = (
            delete(ReportFlag)
            .where(ReportFlag.CRGReportID == report_id)
            .where(ReportFlag.CreatedBy == self.user_id)
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
            .where(ReportFlag.CRGReportID.in_(report_ids))
            .where(ReportFlag.CreatedBy == self.user_id)
        )
        flags = (await self.db.execute(stmt)).scalars().all()
        return {flag.CRGReportID: flag for flag in flags}

    async def set_study_report_confirmation(self, report_id: int, study_id: int, confirmed: bool) -> bool:
        """
        Set confirmation state for a report-study link tracked in StudyReportAdded.
        The StudyReportAdded row is resolved through tblStudyReport by report/study ids.
        """
        stmt = (
            select(StudyReportAdded)
            .join(StudyReport, StudyReport.StudyReportID == StudyReportAdded.StudyReportID)
            .where(StudyReport.CRGReportID == report_id)
            .where(StudyReport.CRGStudyID == study_id)
        )
        study_report_added = (await self.db.execute(stmt)).scalar_one_or_none()

        if not study_report_added:
            return False

        study_report_added.Confirmed = confirmed
        await self.db.flush()
        return True


    async def get_pdf_availabilities(self, report_ids: List[int]) -> Dict[int, Optional[int]]:
        report_ids = report_ids or []
        if not report_ids:
            return {}

        stmt = (
            select(Report.CRGReportID, Report.ReportNumber)
            .join(ReportAdded, Report.CRGReportID == ReportAdded.CRGReportID)
            .where(Report.CRGReportID.in_(report_ids))
            .where(Report.ReportNumber >= 0)
            .where(ReportAdded.AutoSearchedPdf.is_(True))
        )

        rows = await self.db.execute(stmt)

        result = []
        for report_id, report_number in rows.all():
            if report_number == 0:
                result.append(report_id)
                continue
            txt_name = str(report_id).zfill(5) + ".txt"
            txt_path = os.path.join(FULLTEXT_PATH, txt_name)
            if os.path.exists(txt_path):
                result.append(report_id)
        return result
    
    async def get_pdf_numbers_by_report_id(self, report_id: int) -> int:
        """
        Returns the PDF report number for a given report ID.
        """
        report = await self.db.get(Report, report_id)
        if not report:
            return None
        if report.ReportNumber is None:
            return -1   # report found, but ReportNumber is NULL
        return report.ReportNumber
    
    async def assign_pdf_numbers_for_report_id(self, report_id: int) -> int:
        """
        Assigns a unique PDF report number to the given report if it does not already have one.
        Returns the assigned or existing report number.
        """
        report = await self.db.get(Report, report_id)
        if not report:
            return None  # Report not found

        if report.ReportNumber is not None and report.ReportNumber > 0:
            return report.ReportNumber  # Already assigned

        # Find the current max ReportNumber
        stmt = (
            select(Report.ReportNumber)
            .where(Report.ReportNumber.isnot(None))
            .order_by(Report.ReportNumber.desc())
        )
        max_number = (await self.db.execute(stmt)).scalars().first()
        next_number = (max_number or 0) + 1

        report.ReportNumber = next_number
        await self.db.flush()
        return next_number

    async def save_report_metadata_field(self, report_id: int, field: str, value: Any):
        stmt = select(FulltextExtractions).where(FulltextExtractions.CRGReportID == report_id)
        extraction = (await self.db.execute(stmt)).scalar_one_or_none()
        if not extraction:
            # Optionally create a new record if not found
            data = {}
            extraction = FulltextExtractions(CRGReportID=report_id, data=data)
            self.db.add(extraction)
        else:
            data = extraction.data or {}
        data[field] = value
        extraction.data = data
        await self.db.flush()

    async def load_report_metadata(self, report_id : int):
        stmt = select(FulltextExtractions).where(FulltextExtractions.CRGReportID == report_id)
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        
        if existing:
            return existing.data
        return None