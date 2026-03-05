from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func
from sqlmodel import select, delete, insert

from ..models import (
    Report,
    Study,
    ReportAdded,
    Batch,
    BatchInnerScore,
    StudyReport,
    StudyReportAdded,
    BatchAssignees,
)
from typing import Dict, List, Optional, Set, Tuple

class BatchRepository:
    def __init__(self, db : AsyncSession, user_id : str):
        self.db = db
        self.user_id = str(user_id)

    async def add_new_batch(self, batch_hash : str, batch_description : str, reports : List[Report]):
        new_batch = Batch(
            BatchHash=batch_hash,
            BatchDescription=batch_description,
            UploadedBy=self.user_id
        )
        self.db.add(new_batch)

        # Add all reports at once
        self.db.add_all(reports)
        await self.db.flush()  # Flush once to get all IDs
        
        # Create all ReportAdded entries
        report_added_entries = [
            ReportAdded(CRGReportID=report.CRGReportID, BatchHash=batch_hash)
            for report in reports
        ]
        self.db.add_all(report_added_entries)
        
        await self.db.commit()

        for report in reports:
            await self.db.refresh(report)

        return reports
    
    async def get_similar_report_studies(self, report_id: int, min_score: float) -> List[Study]:
        """
        Internal implementation to get studies linked to similar reports.
        
        Args:
            report_id: The reference report ID
            min_score: Minimum similarity score threshold
            user_id: Filter by user who created the study-report link
            session: Database session
            
        Returns:
            List of Study objects linked to similar reports, or empty list if report doesn't exist
        """
        # Check if report exists
        report = await self.db.get(Report, report_id)
        if not report:
            return []
        
        # Query to get studies from similar reports
        # Note: We select BatchInnerScore.Score to make it available for ORDER BY
        stmt = (
            select(Study, BatchInnerScore.Score)
            .distinct()
            .join(StudyReport, StudyReport.CRGStudyID == Study.CRGStudyID)
            .join(
                BatchInnerScore,
                (BatchInnerScore.OtherID == StudyReport.CRGReportID) &
                (BatchInnerScore.CRGReportID == report_id) &
                (BatchInnerScore.Score >= min_score)
            )
            .outerjoin(StudyReportAdded, StudyReport.StudyReportID == StudyReportAdded.StudyReportID)
        )
        
        # Filter by user if specified
        if self.user_id:
            stmt = stmt.where(
                (StudyReportAdded.CreatedBy == self.user_id) | 
                (StudyReportAdded.CreatedBy.is_(None))
            )
        
        # Order by similarity score (descending)
        stmt = stmt.order_by(BatchInnerScore.Score.desc())
        
        result = await self.db.execute(stmt)
        
        return result.all()
    
    async def get_batch_by_hash(self, batch_hash: str):
        batch = await self.db.execute(select(Batch).where(Batch.BatchHash == batch_hash))
        return batch.scalar_one_or_none()
    
    async def get_batch_associated_report_ids(self, batch_hash : str):
        result = await self.db.execute(
            select(ReportAdded.CRGReportID).where(ReportAdded.BatchHash == batch_hash)
        )
        return result.scalars().all()
    
    async def get_all_batches(self, only_own_batches=False):
        stmt = select(Batch)

        if only_own_batches and self.user_id:
            stmt = stmt.where(Batch.UploadedBy == self.user_id)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_assigned_batches(self) -> List[Batch]:
        if not self.user_id:
            return []

        stmt = (
            select(Batch)
            .join(BatchAssignees, BatchAssignees.BatchHash == Batch.BatchHash)
            .where(BatchAssignees.Assignee == self.user_id)
            .order_by(Batch.DateCreated.desc())
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_report_counts_for_batches(self, batch_hashes: List[str]) -> Dict[str, int]:
        if not batch_hashes:
            return {}

        stmt = (
            select(ReportAdded.BatchHash, func.count(ReportAdded.CRGReportID))
            .where(ReportAdded.BatchHash.in_(batch_hashes))
            .group_by(ReportAdded.BatchHash)
        )

        result = await self.db.execute(stmt)
        return {batch_hash: count for batch_hash, count in result.all()}

    async def get_user_link_counts_by_batch(self) -> Dict[str, int]:
        if not self.user_id:
            return {}

        stmt = (
            select(ReportAdded.BatchHash, func.count(StudyReportAdded.StudyReportID))
            .select_from(StudyReportAdded)
            .join(StudyReport, StudyReportAdded.StudyReportID == StudyReport.StudyReportID)
            .join(ReportAdded, ReportAdded.CRGReportID == StudyReport.CRGReportID)
            .where(StudyReportAdded.CreatedBy == self.user_id)
            .group_by(ReportAdded.BatchHash)
        )

        result = await self.db.execute(stmt)
        return {batch_hash: count for batch_hash, count in result.all()}
    
    async def delete_batch(self, batch_hash : str):
        await self.db.execute(delete(Batch).where(Batch.BatchHash == batch_hash))
        await self.db.commit()

    async def batch_item_to_report_id(self, batch_hash: str, report_index: int):
        stmt = (
            select(ReportAdded.CRGReportID)
            .where(
                ReportAdded.BatchHash == batch_hash,
            )
            .order_by(ReportAdded.CRGReportID)
            .offset(report_index)
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def insert_batch_scores(self, score_pairs):
        stmt = insert(BatchInnerScore)
        self.db.execute(stmt, score_pairs)
        await self.db.commit()

    async def get_batch_hash_by_report_id(self, report_id: int) -> Optional[str]:
        stmt = (
            select(ReportAdded.BatchHash)
            .where(ReportAdded.CRGReportID == report_id)
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_batch_assignees(self, batch_hash: str) -> List[Tuple[str, int]]:
        result = await self.db.execute(
            select(BatchAssignees.Assignee).where(BatchAssignees.BatchHash == batch_hash)
        )
        assignees = result.scalars().all()

        if not assignees:
            return []

        count_stmt = (
            select(StudyReportAdded.CreatedBy, func.count(StudyReportAdded.StudyReportID))
            .select_from(StudyReportAdded)
            .join(StudyReport, StudyReportAdded.StudyReportID == StudyReport.StudyReportID)
            .join(ReportAdded, ReportAdded.CRGReportID == StudyReport.CRGReportID)
            .where(
                (ReportAdded.BatchHash == batch_hash)
                & (StudyReportAdded.CreatedBy.in_(assignees))
            )
            .group_by(StudyReportAdded.CreatedBy)
        )

        count_result = await self.db.execute(count_stmt)
        counts = {user_id: count for user_id, count in count_result.all()}

        return [(user_id, counts.get(user_id, 0)) for user_id in assignees]

    async def get_report_completion_by_users(self, batch_hash: str) -> Dict[int, Set[str]]:
        stmt = (
            select(StudyReport.CRGReportID, StudyReportAdded.CreatedBy)
            .select_from(StudyReportAdded)
            .join(StudyReport, StudyReportAdded.StudyReportID == StudyReport.StudyReportID)
            .join(ReportAdded, ReportAdded.CRGReportID == StudyReport.CRGReportID)
            .where(ReportAdded.BatchHash == batch_hash)
            .where(StudyReportAdded.CreatedBy.isnot(None))
        )

        result = await self.db.execute(stmt)
        completion: Dict[int, Set[str]] = {}
        for report_id, user_id in result.all():
            if not user_id:
                continue
            completion.setdefault(report_id, set()).add(user_id)

        return completion

    async def add_batch_assignee(self, batch_hash: str, assignee: str) -> bool:
        stmt = (
            pg_insert(BatchAssignees)
            .values(BatchHash=batch_hash, Assignee=assignee)
            .on_conflict_do_nothing(index_elements=["BatchHash", "Assignee"])
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)

    async def remove_batch_assignee(self, batch_hash: str, assignee: str) -> bool:
        result = await self.db.execute(
            delete(BatchAssignees).where(
                (BatchAssignees.BatchHash == batch_hash) & (BatchAssignees.Assignee == assignee)
            )
        )
        await self.db.commit()
        return bool(result.rowcount)
