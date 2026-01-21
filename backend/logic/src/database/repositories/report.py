from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, delete, func

from ..models import Report, Study, StudyAdded, StudyReport, StudyReportAdded, FulltextExtractions
from typing import List, Dict, Any, Optional

class ReportRepository:
    def __init__(self, db : AsyncSession, user_id : str):
        self.db = db
        self.user_id = str(user_id)

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
        
        return orphan_list

    async def link_studies(self, report_id: int, study_ids: List[int]) -> Dict[str, Any]:
        """
        Internal implementation to link a report to multiple studies.

        Returns:
            {
            "report_id": int,
            "created_count": int,
            "invalid_study_ids": List[int],
            "created_links": List[Dict[str, int]]
            }
        """
        study_ids = study_ids or []
        if not study_ids:
            return {
                "report_id": report_id,
                "created_count": 0,
                "invalid_study_ids": [],
                "created_links": []
            }

        try:
            # Validate report exists
            report = await self.db.get(Report, report_id)
            if not report:
                raise Exception("Report not found")

            # Validate studies exist
            valid_id_rows = await self.db.execute(
                select(Study.CRGStudyID).where(Study.CRGStudyID.in_(study_ids))
            )
            valid_ids = set(valid_id_rows.scalars().all())
            invalid_ids = [sid for sid in study_ids if sid not in valid_ids]

            # Get existing links before deletion to check for orphans later
            existing_stmt = (
                select(StudyReport.CRGStudyID)
                .outerjoin(StudyReportAdded, StudyReport.StudyReportID == StudyReportAdded.StudyReportID)
                .where(StudyReport.CRGReportID == report_id)
            )
            if self.user_id:
                existing_stmt = existing_stmt.where(StudyReportAdded.CreatedBy == self.user_id)
            
            affected_studies = set((await self.db.execute(existing_stmt)).scalars().all())

            # Only delete existing links created by this user (or with no creator)
            if self.user_id:
                # Delete StudyReport links that were created by this user
                await self.db.execute(
                    delete(StudyReport)
                    .where(StudyReport.CRGReportID == report_id)
                    .where(StudyReport.StudyReportID.in_(
                        select(StudyReportAdded.StudyReportID)
                        .where(StudyReportAdded.CreatedBy == self.user_id)
                    ))
                )
            else:
                # If no user specified, delete all existing links for this report
                await self.db.execute(delete(StudyReport).where(StudyReport.CRGReportID == report_id))

            await self.db.flush()

            # Check for orphaned newly-added studies
            deleted_orphans = await self._remove_orphaned_studies(affected_studies)
            if deleted_orphans:
                await self.db.flush()

            # Create new links and track them in StudyReportAdded
            created_links: List[Dict[str, int]] = []
            for sid in valid_ids:
                new_study_report = StudyReport(CRGReportID=report_id, CRGStudyID=sid)
                self.db.add(new_study_report)
                await self.db.flush()  # Flush to get the StudyReportID
                
                # Track who created this link
                self.db.add(StudyReportAdded(
                    StudyReportID=new_study_report.StudyReportID,
                    CreatedBy=self.user_id
                ))
                
                created_links.append({"CRGReportID": report_id, "CRGStudyID": sid})

            await self.db.commit()

            return {
                "report_id": report_id,
                "created_count": len(valid_ids),
                "invalid_study_ids": invalid_ids,
                "created_links": created_links,
                "deleted_orphans": deleted_orphans
            }
        
        except Exception as e:
            await self.db.rollback()
            raise Exception(f"Failed to update report-study links: {str(e)}")
        
    async def unlink_studies(self, report_id: int) -> Dict[str, Any]:
        """
        Internal implementation to delete all links between a report and studies.
        Only deletes links created by the specified user or links with no creator.
        """
        try:
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
            
            # If user is provided, filter by CreatedBy
            if self.user_id:
                stmt = stmt.where(StudyReportAdded.CreatedBy == self.user_id)

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

                await self.db.commit()

            return {
                "report_id": report_id,
                "deleted_count": len(rows),
                "deleted_links": deleted_links,
                "deleted_orphans": deleted_orphans
            }
        
        except Exception as e:
            await self.db.rollback()
            raise Exception(f"Failed to delete report-study links: {str(e)}")
        
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

        if report.ReportNumber is not None:
            return report.ReportNumber  # Already assigned

        # Find the current max ReportNumber
        stmt = select(Report.ReportNumber).order_by(Report.ReportNumber.desc())
        max_number = (await self.db.execute(stmt)).scalars().first()
        next_number = (max_number or 0) + 1

        report.ReportNumber = next_number
        await self.db.flush()  # Update the existing report in the session
        await self.db.commit()
        return next_number
    
    async def save_report_metadata(self, report_id : int, data : Any):
        # Save to database
        new_extraction = FulltextExtractions(
            CRGReportID=report_id,
            data=data
        )
        self.db.add(new_extraction)
        await self.db.commit()

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
        await self.db.commit()

    async def load_report_metadata(self, report_id : int):
        stmt = select(FulltextExtractions).where(FulltextExtractions.CRGReportID == report_id)
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        
        if existing:
            return existing.data
        return None