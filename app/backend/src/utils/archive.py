"""An exported study database as a file: a zip archive with the database (`database.json`, see DatabaseExport in
dto.py) and the PDFs of its reports (`pdfs/...`, named by the `pdf` of a report). The demo database
(deploy/data/seed/synthetic_database.zip) is one. The same layout unpacked into a directory and a bare `database.json`
without PDFs are read as well."""

import zipfile
from pathlib import Path
from typing import BinaryIO, Iterable, Optional, Tuple, Union


class DatabaseArchiveError(ValueError):
    """The file is no database archive."""


class DatabaseArchive:
    DOCUMENT = "database.json"
    PDF_FOLDER = "pdfs"

    def __init__(self, document: bytes, zip_file: Optional[zipfile.ZipFile] = None, directory: Optional[Path] = None):
        self.document = document
        self._zip = zip_file
        self._directory = directory

    @classmethod
    def open(cls, source: Union[Path, BinaryIO]) -> "DatabaseArchive":
        """The archive of a path (a zip, a directory or a JSON file) or of an open file (a zip or JSON, e.g. an
        upload, read as it is needed rather than all at once)."""
        if isinstance(source, Path):
            if source.is_dir():
                document = source / cls.DOCUMENT
                if not document.is_file():
                    raise DatabaseArchiveError(f"{source} has no {cls.DOCUMENT}")
                return cls(document.read_bytes(), directory=source)
            source = source.open("rb")
        if zipfile.is_zipfile(source):
            archive = zipfile.ZipFile(source)
            try:
                return cls(archive.read(cls.DOCUMENT), zip_file=archive)
            except KeyError as exc:
                raise DatabaseArchiveError(f"The archive has no {cls.DOCUMENT}") from exc
        source.seek(0)
        return cls(source.read())

    def pdf(self, name: str) -> Optional[bytes]:
        """The PDF of a report by its name in the archive (e.g. "pdfs/12.pdf"); None if it is not there. Only files
        of the PDF folder are read: a name never leads out of the archive."""
        parts = Path(name).parts
        if len(parts) < 2 or parts[0] != self.PDF_FOLDER or ".." in parts:
            return None
        if self._zip is not None:
            try:
                return self._zip.read(name)
            except KeyError:
                return None
        if self._directory is not None:
            path = self._directory.joinpath(*parts)
            return path.read_bytes() if path.is_file() else None
        return None

    @classmethod
    def write(cls, target: BinaryIO, document: bytes, pdfs: Iterable[Tuple[str, Path]]) -> None:
        """Writes an archive: the database and the PDF files given as (name in the archive, file on disk)."""
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(cls.DOCUMENT, document)
            for name, path in pdfs:
                # PDFs are compressed already.
                archive.write(path, name, compress_type=zipfile.ZIP_STORED)
