"""The deterministic short name proposed for a study created from a report (no AI involved)."""

from __future__ import annotations

import re
import string

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database.models import Report, Study
from ..database.repositories.report import ReportRepository
from ..utils.trial_registration_id import is_trial_registration


class StudyNamingService:
    """The trial registration id of the report if it has one, otherwise first author + year
    ("Smith 2020"). If a study of that name exists, a letter is appended: "Smith 2020a" when one
    study has the name already, "Smith 2020b" when two have, and so on."""

    def __init__(self, db: AsyncSession, report_repo: ReportRepository):
        self.db = db
        self.report_repo = report_repo

    async def suggest(self, report_id: int, trial_id: str | None = None) -> str:
        """`trial_id`: a trial registration id of the study, if known (e.g. extracted from the report)."""
        report = await self.report_repo.get_report_by_id(report_id)
        if report is None:
            raise ValueError(f"Report {report_id} not found")

        base = (trial_id or "").strip() or self._author_year(report)
        taken = await self._taken_names(base)
        if base.lower() not in taken:
            return base
        index = len(taken) - 1
        while base.lower() + self._suffix(index) in taken:
            index += 1
        return base + self._suffix(index)

    async def _taken_names(self, base: str) -> set[str]:
        """The lowercased names of the studies called `base`, with or without a letter appended."""
        result = await self.db.execute(
            select(Study.short_name).where(func.lower(Study.short_name).startswith(base.lower(), autoescape=True))
        )
        pattern = re.compile(re.escape(base) + "[a-z]?", re.I)
        return {name.lower() for (name,) in result.all() if pattern.fullmatch(name)}

    @staticmethod
    def _suffix(index: int) -> str:
        return string.ascii_lowercase[index] if index < len(string.ascii_lowercase) else str(index)

    @classmethod
    def _author_year(cls, report: Report) -> str:
        if is_trial_registration(report.authors):
            return report.authors.strip()
        first = next((author.strip() for author in (report.authors or "").split("//") if author.strip()), "")
        return f"{cls._surname(first) or 'Unknown'} {report.year}"

    @staticmethod
    def _surname(author: str) -> str:
        """From "Smith, John", "Smith J" or "John Smith"."""
        if "," in author:
            return author.split(",")[0].strip()
        parts = author.split()
        if len(parts) > 1 and re.fullmatch(r"[A-Z]{1,3}\.?", parts[-1]):
            return " ".join(parts[:-1])
        return parts[-1] if parts else ""
