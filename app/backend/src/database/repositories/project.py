from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from dataclasses import dataclass
from sqlalchemy import exists, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select, delete, insert
from collections import defaultdict

from ..models import (
    Study,
    ReportFlag,
    Project,
    ProjectInnerScore,
    ProjectAssignees,
    ReportCommit,
    UpdateLink,
    UpdateReport,
    UpdateStudy,
)
from typing import Any, Dict, List, Set, Tuple, Optional


@dataclass
class DeletedProject:
    """What a deleted project had that lives outside the database and has to be removed as well."""

    # The reports, whose vectors and PDF files go as well.
    report_ids: List[int]


class ProjectRepository:

    def __init__(self, db : AsyncSession, user_id : str):
        self.db = db
        self.user_id = str(user_id)

    async def add_new_project(self, project_id : str, batch_description : str, reports : List[UpdateReport], database_id : int):
        """Adds the project (the update) with its reports; None if the project exists already."""
        try:
            new_project = Project(
                id=project_id,
                description=batch_description,
                created_by=self.user_id,
                database_id=database_id,
            )
            self.db.add(new_project)
            await self.db.flush()

            for report in reports:
                report.project_id = project_id
            self.db.add_all(reports)
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
        stmt = select(Project).where(Project.id == project_id)
        project = await self.db.execute(stmt)
        return project.scalar_one_or_none()

    async def get_similar_report_studies(self, report_id: int, min_score: float) -> List[Tuple[Any, float]]:
        """The studies (of the core database or of the update) this scope linked the reports of the update similar to
        the report to (see ProjectInnerScore), with the score of the similar report, the most similar first; empty if
        the report is no report of an update."""
        rows: List[Tuple[Any, float]] = []
        for model, column in ((Study, UpdateLink.study_id), (UpdateStudy, UpdateLink.update_study_id)):
            rows += (await self.db.execute(
                select(model, ProjectInnerScore.score)
                .distinct()
                .join(UpdateLink, column == model.id)
                .join(
                    ProjectInnerScore,
                    (ProjectInnerScore.other_id == UpdateLink.report_id) &
                    (ProjectInnerScore.report_id == report_id) &
                    (ProjectInnerScore.score >= min_score)
                )
                .where(UpdateLink.created_by == self.user_id)
            )).all()
        return sorted(rows, key=lambda row: row[1], reverse=True)

    async def get_project_by_id(self, project_id: str):
        if not self.user_id:
            raise ValueError("User ID is required to retrieve projects.")

        stmt = select(Project).where(Project.id == project_id)
        stmt = stmt.where(Project.created_by == self.user_id)

        project = await self.db.execute(stmt)
        return project.scalar_one_or_none()

    async def get_all_projects(self):
        if not self.user_id:
            raise ValueError("User ID is required to retrieve projects.")

        stmt = select(Project)
        stmt = stmt.where(Project.created_by == self.user_id)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_project_associated_report_ids(self, project_id : str):
        result = await self.db.execute(
            select(UpdateReport.id).where(UpdateReport.project_id == project_id)
        )
        return result.scalars().all()

    async def set_report_auto_searched_pdf(
        self,
        report_id: int,
        fulltext_links: Optional[List[str]] = None,
        referenced_dois: Optional[List[str]] = None,
    ) -> None:
        """`fulltext_links`, when given, is the OpenAlex lookup this same background
        pass already did to find a PDF to auto-download (see
        src/background/wrapper.py's _auto_search_report_pdf) - cached here alongside
        the flag so report detail views don't have to re-query OpenAlex live
        (see UpdateReport.fulltext_links's comment in models.py). `referenced_dois` is
        the same pass's list of cited DOIs (see UpdateReport.referenced_dois).
        """
        report = await self.db.get(UpdateReport, report_id)
        if report is None:
            return

        report.auto_searched_pdf = True
        if fulltext_links is not None:
            report.fulltext_links = fulltext_links
        if referenced_dois is not None:
            report.referenced_dois = referenced_dois
        await self.db.flush()

    async def is_project_assignee(self, project_id: str) -> bool:
        if not self.user_id:
            return False

        stmt = select(ProjectAssignees).where(
            (ProjectAssignees.project_id == project_id)
            & (ProjectAssignees.assignee == self.user_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_commit_counts(self, project_id: str) -> Dict[str, int]:
        """How many reports of the project each assignee has committed their links of."""
        result = await self.db.execute(
            select(ReportCommit.assignee, func.count(ReportCommit.report_id))
            .join(UpdateReport, UpdateReport.id == ReportCommit.report_id)
            .where(UpdateReport.project_id == project_id)
            .group_by(ReportCommit.assignee)
        )
        return {assignee: count for assignee, count in result.all()}

    async def get_committed_report_ids(self, project_id: str) -> Set[int]:
        """The reports of the project the caller has committed their links of."""
        if not self.user_id:
            return set()
        result = await self.db.execute(
            select(ReportCommit.report_id)
            .join(UpdateReport, UpdateReport.id == ReportCommit.report_id)
            .where(UpdateReport.project_id == project_id)
            .where(ReportCommit.assignee == self.user_id)
        )
        return set(result.scalars().all())

    async def has_committed_report(self, report_id: int) -> bool:
        if not self.user_id:
            return False
        result = await self.db.execute(
            select(exists().where(ReportCommit.report_id == report_id).where(ReportCommit.assignee == self.user_id))
        )
        return bool(result.scalar())

    async def get_report_committers(self, report_id: int) -> Set[str]:
        """The assignees who have committed their links of the report."""
        result = await self.db.execute(select(ReportCommit.assignee).where(ReportCommit.report_id == report_id))
        return set(result.scalars().all())

    async def get_fully_committed_report_ids(self, project_id: str) -> Set[int]:
        """The reports of the project every one of its assignees has committed their links of: ready to merge."""
        assignees = select(ProjectAssignees.assignee).where(ProjectAssignees.project_id == project_id)
        result = await self.db.execute(
            select(ReportCommit.report_id)
            .join(UpdateReport, UpdateReport.id == ReportCommit.report_id)
            .where(UpdateReport.project_id == project_id)
            .where(ReportCommit.assignee.in_(assignees))
            .group_by(ReportCommit.report_id)
            .having(func.count(ReportCommit.assignee) >= assignees.with_only_columns(func.count()).scalar_subquery())
        )
        return set(result.scalars().all())

    async def get_open_project_id(self, database_id: int) -> Optional[str]:
        """The update of the database that still has reports to merge, if there is one."""
        result = await self.db.execute(
            select(Project.id)
            .where(Project.database_id == database_id)
            .where(exists().where(UpdateReport.project_id == Project.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def commit_reports(self, report_ids: Set[int]) -> None:
        """Marks the caller's links of the reports as committed."""
        if not self.user_id or not report_ids:
            return
        await self.db.execute(
            pg_insert(ReportCommit)
            .values([{"report_id": report_id, "assignee": self.user_id} for report_id in report_ids])
            .on_conflict_do_nothing(index_elements=["report_id", "assignee"])
        )
        await self.db.commit()

    async def get_assigned_projects(self) -> List[Project]:
        if not self.user_id:
            return []

        stmt = (
            select(Project)
            .join(ProjectAssignees, ProjectAssignees.project_id == Project.id)
            .where(ProjectAssignees.assignee == self.user_id)
            .order_by(Project.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_auto_searched_pdf_count_for_project(self, project_id: str) -> int:
        stmt = (
            select(func.count(UpdateReport.id))
            .where(UpdateReport.project_id == project_id)
            .where(UpdateReport.auto_searched_pdf.is_(True))
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def get_user_link_counts_by_project(self) -> Dict[str, int]:
        if not self.user_id:
            raise ValueError("User ID is required to retrieve project information.")

        stmt = (
            select(UpdateReport.project_id, func.count(func.distinct(UpdateLink.report_id)))
            .join(UpdateReport, UpdateReport.id == UpdateLink.report_id)
            .where(UpdateLink.created_by == self.user_id)
            .group_by(UpdateReport.project_id)
        )

        result = await self.db.execute(stmt)
        return {project_id: count for project_id, count in result.all()}

    async def delete_project(self, project_id: str) -> Optional[DeletedProject]:
        """Delete a project with everything it brought in that is not merged yet: its reports of the update with
        their links, and the studies created in it (the foreign keys of the tables of the updates, see UPDATE_DATA).
        The core database stays as it is, the reports already merged into it included.

        Only the uploader can delete a project. Returns None, deleting nothing, if there is no such project
        or it was uploaded by somebody else; otherwise what is left to remove outside the database.
        """
        if not self.user_id:
            raise ValueError("User ID is required to delete a project")

        stmt = (
            select(Project)
            .where(Project.id == project_id)
            .where(Project.created_by == self.user_id)
        )
        project = (await self.db.execute(stmt)).scalar_one_or_none()
        if project is None:
            return None

        deleted = DeletedProject(report_ids=list(await self.get_project_associated_report_ids(project_id)))
        try:
            await self.db.execute(delete(Project).where(Project.id == project_id))
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return deleted

    async def project_item_to_report_id(self, project_id: str, report_index: int):
        stmt = (
            select(UpdateReport.id)
            .where(
                UpdateReport.project_id == project_id,
            )
            .order_by(UpdateReport.id)
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
                    "report_id": report_id,
                    "other_id": other_id,
                    "score": score,
                }
                for report_id, other_id, score in score_pairs
            ]

        stmt = insert(ProjectInnerScore)
        await self.db.execute(stmt, mappings)
        await self.db.commit()

    async def get_project_assignees(self, project_id: str) -> List[Tuple[str, int]]:
        result = await self.db.execute(
            select(ProjectAssignees.assignee).where(ProjectAssignees.project_id == project_id)
        )
        assignees = result.scalars().all()

        if not assignees:
            return []

        count_stmt = (
            select(UpdateLink.created_by, func.count(func.distinct(UpdateLink.report_id)))
            .join(UpdateReport, UpdateReport.id == UpdateLink.report_id)
            .where(
                (UpdateReport.project_id == project_id)
                & (UpdateLink.created_by.in_(assignees))
            )
            .group_by(UpdateLink.created_by)
        )

        count_result = await self.db.execute(count_stmt)
        counts = {user_id: count for user_id, count in count_result.all()}

        return [(user_id, counts.get(user_id, 0)) for user_id in assignees]

    async def get_report_completion_by_users(self, project_id: str) -> Dict[int, Set[str]]:
        stmt = (
            select(UpdateLink.report_id, UpdateLink.created_by)
            .join(UpdateReport, UpdateReport.id == UpdateLink.report_id)
            .where(UpdateReport.project_id == project_id)
        )

        result = await self.db.execute(stmt)
        completion: Dict[int, Set[str]] = {}
        for report_id, user_id in result.all():
            if not user_id:
                continue
            completion.setdefault(report_id, set()).add(user_id)

        # Treat reports with public flags as completed by the users who created those flags.
        public_flag_stmt = (
            select(ReportFlag.report_id, ReportFlag.created_by)
            .select_from(ReportFlag)
            .join(UpdateReport, UpdateReport.id == ReportFlag.report_id)
            .where(UpdateReport.project_id == project_id)
            .where(ReportFlag.public.is_(True))
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

        study_id = func.coalesce(UpdateLink.study_id, UpdateLink.update_study_id)
        stmt = (
            select(
                UpdateLink.report_id,
                UpdateLink.created_by,
                study_id,
                func.coalesce(Study.short_name, UpdateStudy.short_name),
            )
            .join(UpdateReport, UpdateReport.id == UpdateLink.report_id)
            .outerjoin(Study, Study.id == UpdateLink.study_id)
            .outerjoin(UpdateStudy, UpdateStudy.id == UpdateLink.update_study_id)
            .where(UpdateReport.project_id == project_id)
            .where(UpdateLink.created_by.in_(assignees))
            .order_by(UpdateLink.report_id, UpdateLink.created_by, study_id)
        )

        if report_ids:
            stmt = stmt.where(UpdateLink.report_id.in_(report_ids))

        annotations: Dict[int, Dict[str, List[Dict[str, Any]]]] = defaultdict(
            lambda: {"studies": [], "flags": []}
        )

        result = await self.db.execute(stmt)
        rows = result.all()
        for report_id, created_by, study_id, study_name in rows:
            annotations[report_id]["studies"].append(
                {
                    "user": created_by,
                    "studyId": study_id,
                    "studyShortName": study_name,
                }
            )

        flag_stmt = (
            select(
                ReportFlag.report_id,
                ReportFlag.created_by,
                ReportFlag.message,
            )
            .select_from(ReportFlag)
            .join(UpdateReport, UpdateReport.id == ReportFlag.report_id)
            .where(UpdateReport.project_id == project_id)
            .where(ReportFlag.created_by.in_(assignees))
            .where(ReportFlag.public.is_(True))
            .order_by(ReportFlag.report_id, ReportFlag.created_by)
        )

        if report_ids:
            flag_stmt = flag_stmt.where(ReportFlag.report_id.in_(report_ids))

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
            select(Project.id)
            .where(Project.id == project_id)
            .where(Project.created_by == self.user_id)
            .limit(1)
        )
        ownership_result = await self.db.execute(ownership_stmt)
        if not ownership_result.scalar_one_or_none():
            raise PermissionError("You can only modify assignees for your own project.")

        stmt = (
            pg_insert(ProjectAssignees)
            .values(project_id=project_id, assignee=assignee)
            .on_conflict_do_nothing(index_elements=["project_id", "assignee"])
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)

    async def remove_project_assignee(self, project_id: str, assignee: str) -> bool:
        if not self.user_id:
            raise ValueError("User ID is required to modify project assignees.")

        ownership_stmt = (
            select(Project.id)
            .where(Project.id == project_id)
            .where(Project.created_by == self.user_id)
            .limit(1)
        )
        ownership_result = await self.db.execute(ownership_stmt)
        if not ownership_result.scalar_one_or_none():
            raise PermissionError("You can only modify assignees for your own project.")

        result = await self.db.execute(
            delete(ProjectAssignees).where(
                (ProjectAssignees.project_id == project_id) & (ProjectAssignees.assignee == assignee)
            )
        )
        # Their commits go with the assignment: assigned again, they start over.
        await self.db.execute(
            delete(ReportCommit)
            .where(ReportCommit.assignee == assignee)
            .where(ReportCommit.report_id.in_(select(UpdateReport.id).where(UpdateReport.project_id == project_id)))
        )
        await self.db.commit()
        return bool(result.rowcount)

    async def get_database_id_by_report_id(self, report_id: int) -> Optional[int]:
        """The study database of the report's project, None for a report of the core database."""
        stmt = (
            select(Project.database_id)
            .join(UpdateReport, UpdateReport.project_id == Project.id)
            .where(UpdateReport.id == report_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_project_id_by_report_id(self, report_id: int) -> Optional[str]:
        stmt = select(UpdateReport.project_id).where(UpdateReport.id == report_id)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
