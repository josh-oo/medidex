"""The fulltext PDFs of the reports on the data volume: one file per report, named by its id
(resources/report_pdfs/<report id>.pdf). Whether a report has a PDF is read from this folder, never stored; a report
without one can be marked as having none (Report.no_pdf)."""

import os
import uuid
from pathlib import Path
from typing import Iterable, Set, Tuple

from dotenv import load_dotenv

load_dotenv()


class PdfFiles:
    FOLDER = Path(os.getenv("DATABASE_VOLUME", "")) / "resources" / "report_pdfs"
    # Up to this many reports are looked up a file at a time; more by listing the folder once.
    STAT_LIMIT = 50

    @classmethod
    def path(cls, report_id: int) -> Path:
        return cls.FOLDER / f"{report_id}.pdf"

    @classmethod
    def stored_ids(cls) -> Set[int]:
        """The ids of every report with a PDF."""
        try:
            entries = os.scandir(cls.FOLDER)
        except FileNotFoundError:
            return set()
        with entries:
            return {
                int(entry.name[:-4]) for entry in entries
                if entry.name.endswith(".pdf") and entry.name[:-4].isdigit()
            }

    @classmethod
    def stored(cls, report_ids: Iterable[int]) -> Set[int]:
        """Those of the reports with a PDF."""
        report_ids = set(report_ids)
        if len(report_ids) <= cls.STAT_LIMIT:
            return {report_id for report_id in report_ids if cls.path(report_id).is_file()}
        return report_ids & cls.stored_ids()

    @classmethod
    def usage(cls, report_ids: Iterable[int]) -> Tuple[int, int]:
        """How many of the reports have a PDF, and how many bytes they take."""
        report_ids = set(report_ids)
        if len(report_ids) <= cls.STAT_LIMIT:
            sizes = [cls.path(report_id).stat().st_size for report_id in cls.stored(report_ids)]
        else:
            try:
                entries = os.scandir(cls.FOLDER)
            except FileNotFoundError:
                return 0, 0
            with entries:
                sizes = [
                    entry.stat().st_size for entry in entries
                    if entry.name.endswith(".pdf") and entry.name[:-4].isdigit() and int(entry.name[:-4]) in report_ids
                ]
        return len(sizes), sum(sizes)

    @classmethod
    def write(cls, report_id: int, content: bytes) -> Path:
        """Stores (or replaces) the PDF of a report. Written next to it first and then moved, so the folder never
        shows a half-written PDF."""
        cls.FOLDER.mkdir(parents=True, exist_ok=True)
        path = cls.path(report_id)
        partial = cls.FOLDER / f".{report_id}.{uuid.uuid4().hex}.part"
        try:
            partial.write_bytes(content)
            os.replace(partial, path)
        finally:
            partial.unlink(missing_ok=True)
        return path

    @classmethod
    def remove(cls, report_ids: Iterable[int]) -> int:
        """Removes the PDFs of the reports; returns how many there were."""
        removed = 0
        for report_id in report_ids:
            try:
                cls.path(report_id).unlink()
                removed += 1
            except FileNotFoundError:
                pass
        return removed
