from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select, delete, insert
from collections import defaultdict

from ..models import (
    Report,
    Study,
    ReportAdded,
    ReportFlag,
    Project,
    ProjectInnerScore,
    StudyReport,
    StudyReportAdded,
    ProjectAssignees,
)
from typing import Any, Dict, List, Set, Tuple, Optional


"""
IMPORTANT: The external interfaces follow the "project" naming scheme while the internal database implementation uses "batch" as a name
"""

class ProjectRepository:
    def __init__(self, db : AsyncSession, user_id : str):
        self.db = db
        self.user_id = str(user_id)

    async def add_new_project(self, project_id : str, batch_description : str, reports : List[Report]):
        try:
            new_project = Project(
                BatchHash=project_id,
                BatchDescription=batch_description,
                UploadedBy=self.user_id
            )
            self.db.add(new_project)

            # Add all reports at once
            self.db.add_all(reports)
            await self.db.flush()  # Flush once to get all IDs
            
            # Create all ReportAdded entries
            report_added_entries = [
                ReportAdded(CRGReportID=report.CRGReportID, BatchHash=project_id)
                for report in reports
            ]
            self.db.add_all(report_added_entries)
            
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing_project = await self.get_project_by_hash(project_id)
            if existing_project is not None:
                return None
            raise

        for report in reports:
            await self.db.refresh(report)

        return reports

    async def get_project_by_hash(self, project_id: str) -> Optional[Project]:
        stmt = select(Project).where(Project.BatchHash == project_id)
        project = await self.db.execute(stmt)
        return project.scalar_one_or_none()
    
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
        # Note: We select ProjectInnerScore.Score to make it available for ORDER BY
        stmt = (
            select(Study, ProjectInnerScore.Score)
            .distinct()
            .join(StudyReport, StudyReport.CRGStudyID == Study.CRGStudyID)
            .join(
                ProjectInnerScore,
                (ProjectInnerScore.OtherID == StudyReport.CRGReportID) &
                (ProjectInnerScore.CRGReportID == report_id) &
                (ProjectInnerScore.Score >= min_score)
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
        stmt = stmt.order_by(ProjectInnerScore.Score.desc())
        
        result = await self.db.execute(stmt)
        
        return result.all()
    
    async def get_project_by_id(self, project_id: str):
        if not self.user_id:
            raise ValueError("User ID is required to retrieve projects.")
        
        stmt = select(Project).where(Project.BatchHash == project_id)
        stmt = stmt.where(Project.UploadedBy == self.user_id)

        project = await self.db.execute(stmt)
        return project.scalar_one_or_none()
    
    async def get_all_projects(self):
        if not self.user_id:
            raise ValueError("User ID is required to retrieve projects.")
        
        stmt = select(Project)
        stmt = stmt.where(Project.UploadedBy == self.user_id)

        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_project_associated_report_ids(self, project_id : str):
        result = await self.db.execute(
            select(ReportAdded.CRGReportID).where(ReportAdded.BatchHash == project_id)
        )
        return result.scalars().all()

    async def get_assigned_projects(self) -> List[Project]:
        if not self.user_id:
            return []

        stmt = (
            select(Project)
            .join(ProjectAssignees, ProjectAssignees.BatchHash == Project.BatchHash)
            .where(ProjectAssignees.Assignee == self.user_id)
            .order_by(Project.DateCreated.desc())
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_report_counts_for_projects(self, project_ids: List[str]) -> Dict[str, int]:
        if not project_ids:
            return {}

        stmt = (
            select(ReportAdded.BatchHash, func.count(ReportAdded.CRGReportID))
            .where(ReportAdded.BatchHash.in_(project_ids))
            .group_by(ReportAdded.BatchHash)
        )

        result = await self.db.execute(stmt)
        return {batch_hash: count for batch_hash, count in result.all()}

    async def get_user_link_counts_by_project(self) -> Dict[str, int]:
        if not self.user_id:
            raise ValueError("User ID is required to retrieve project information.")

        stmt = (
            select(ReportAdded.BatchHash, func.count(func.distinct(StudyReport.CRGReportID)))
            .select_from(StudyReportAdded)
            .join(StudyReport, StudyReportAdded.StudyReportID == StudyReport.StudyReportID)
            .join(ReportAdded, ReportAdded.CRGReportID == StudyReport.CRGReportID)
            .where(StudyReportAdded.CreatedBy == self.user_id)
            .group_by(ReportAdded.BatchHash)
        )

        result = await self.db.execute(stmt)
        return {batch_hash: count for batch_hash, count in result.all()}
    
    async def delete_project(self, project_id : str):
        if not self.user_id:
            raise ValueError("User ID is required to delete a project")

        stmt = delete(Project).where(Project.BatchHash == project_id)
        stmt = stmt.where(Project.UploadedBy == self.user_id)

        await self.db.execute(stmt)
        await self.db.commit()

    async def project_item_to_report_id(self, project_id: str, report_index: int):
        stmt = (
            select(ReportAdded.CRGReportID)
            .where(
                ReportAdded.BatchHash == project_id,
            )
            .order_by(ReportAdded.CRGReportID)
            .offset(report_index)
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def insert_project_scores(self, score_pairs):
        if not score_pairs:
            return

        if isinstance(score_pairs[0], dict):
            mappings = score_pairs
        else:
            mappings = [
                {
                    "CRGReportID": report_id,
                    "OtherID": other_id,
                    "Score": score,
                }
                for report_id, other_id, score in score_pairs
            ]

        stmt = insert(ProjectInnerScore)
        await self.db.execute(stmt, mappings)
        await self.db.commit()

    async def get_project_assignees(self, project_id: str) -> List[Tuple[str, int]]:
        result = await self.db.execute(
            select(ProjectAssignees.Assignee).where(ProjectAssignees.BatchHash == project_id)
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
                (ReportAdded.BatchHash == project_id)
                & (StudyReportAdded.CreatedBy.in_(assignees))
            )
            .group_by(StudyReportAdded.CreatedBy)
        )

        count_result = await self.db.execute(count_stmt)
        counts = {user_id: count for user_id, count in count_result.all()}

        return [(user_id, counts.get(user_id, 0)) for user_id in assignees]

    async def get_report_completion_by_users(self, project_id: str) -> Dict[int, Set[str]]:
        stmt = (
            select(StudyReport.CRGReportID, StudyReportAdded.CreatedBy)
            .select_from(StudyReportAdded)
            .join(StudyReport, StudyReportAdded.StudyReportID == StudyReport.StudyReportID)
            .join(ReportAdded, ReportAdded.CRGReportID == StudyReport.CRGReportID)
            .where(ReportAdded.BatchHash == project_id)
            .where(StudyReportAdded.CreatedBy.isnot(None))
        )

        result = await self.db.execute(stmt)
        completion: Dict[int, Set[str]] = {}
        for report_id, user_id in result.all():
            if not user_id:
                continue
            completion.setdefault(report_id, set()).add(user_id)

        # Treat reports with public flags as completed by the users who created those flags.
        public_flag_stmt = (
            select(ReportFlag.CRGReportID, ReportFlag.CreatedBy)
            .select_from(ReportFlag)
            .join(ReportAdded, ReportAdded.CRGReportID == ReportFlag.CRGReportID)
            .where(ReportAdded.BatchHash == project_id)
            .where(ReportFlag.Public.is_(True))
        )

        public_flag_result = await self.db.execute(public_flag_stmt)
        for report_id, user_id in public_flag_result.all():
            if not user_id:
                continue
            completion.setdefault(report_id, set()).add(user_id)

        return completion

    async def get_project_annotations_by_assignees(
        self,
        project_id: str,
        assignees: Set[str],
        report_ids: Optional[List[int]] = None,
    ) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:
        if not assignees:
            return {}

        stmt = (
            select(
                StudyReport.CRGReportID,
                StudyReportAdded.CreatedBy,
                Study.CRGStudyID,
                Study.ShortName,
                StudyReportAdded.Confirmed,
            )
            .select_from(StudyReport)
            .join(StudyReportAdded, StudyReportAdded.StudyReportID == StudyReport.StudyReportID)
            .join(ReportAdded, ReportAdded.CRGReportID == StudyReport.CRGReportID)
            .join(Study, Study.CRGStudyID == StudyReport.CRGStudyID)
            .where(ReportAdded.BatchHash == project_id)
            .where(StudyReportAdded.CreatedBy.in_(assignees))
            .order_by(StudyReport.CRGReportID, StudyReportAdded.CreatedBy, Study.CRGStudyID)
        )

        if report_ids:
            stmt = stmt.where(StudyReport.CRGReportID.in_(report_ids))

        annotations: Dict[int, Dict[str, List[Dict[str, Any]]]] = defaultdict(
            lambda: {"studies": [], "flags": []}
        )

        result = await self.db.execute(stmt)
        rows = result.all()
        for report_id, created_by, study_id, study_name, confirmed in rows:
            annotations[report_id]["studies"].append(
                {
                    "user": created_by,
                    "studyId": study_id,
                    "studyShortName": study_name,
                    "confirmed": bool(confirmed),
                }
            )

        flag_stmt = (
            select(
                ReportFlag.CRGReportID,
                ReportFlag.CreatedBy,
                ReportFlag.Message,
            )
            .select_from(ReportFlag)
            .join(ReportAdded, ReportAdded.CRGReportID == ReportFlag.CRGReportID)
            .where(ReportAdded.BatchHash == project_id)
            .where(ReportFlag.CreatedBy.in_(assignees))
            .where(ReportFlag.Public.is_(True))
            .order_by(ReportFlag.CRGReportID, ReportFlag.CreatedBy)
        )

        if report_ids:
            flag_stmt = flag_stmt.where(ReportFlag.CRGReportID.in_(report_ids))

        flag_result = await self.db.execute(flag_stmt)
        for report_id, created_by, message in flag_result.all():
            annotations[report_id]["flags"].append(
                {
                    "user": created_by,
                    "flag": message,
                    "public": True,
                }
            )

        return dict(annotations)

    async def add_project_assignee(self, project_id: str, assignee: str) -> bool:
        if not self.user_id:
            raise ValueError("User ID is required to modify project assignees.")

        ownership_stmt = (
            select(Project.BatchHash)
            .where(Project.BatchHash == project_id)
            .where(Project.UploadedBy == self.user_id)
            .limit(1)
        )
        ownership_result = await self.db.execute(ownership_stmt)
        if not ownership_result.scalar_one_or_none():
            raise PermissionError("You can only modify assignees for your own project.")

        stmt = (
            pg_insert(ProjectAssignees)
            .values(BatchHash=project_id, Assignee=assignee)
            .on_conflict_do_nothing(index_elements=["BatchHash", "Assignee"])
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)

    async def remove_project_assignee(self, project_id: str, assignee: str) -> bool:
        if not self.user_id:
            raise ValueError("User ID is required to modify project assignees.")

        ownership_stmt = (
            select(Project.BatchHash)
            .where(Project.BatchHash == project_id)
            .where(Project.UploadedBy == self.user_id)
            .limit(1)
        )
        ownership_result = await self.db.execute(ownership_stmt)
        if not ownership_result.scalar_one_or_none():
            raise PermissionError("You can only modify assignees for your own project.")

        result = await self.db.execute(
            delete(ProjectAssignees).where(
                (ProjectAssignees.BatchHash == project_id) & (ProjectAssignees.Assignee == assignee)
            )
        )
        await self.db.commit()
        return bool(result.rowcount)

    async def get_project_id_by_report_id(self, report_id: int) -> Optional[str]:
        stmt = (
            select(ReportAdded.BatchHash)
            .where(ReportAdded.CRGReportID == report_id)
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()