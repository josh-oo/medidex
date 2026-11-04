"""Uploads of files too large for one request: a proxy in front of the backend may limit the size of a request (a
Cloudflare tunnel to 100 MB), while an exported database can be many GB. The client sends such a file in parts with the
tus protocol (https://tus.io, the /databases/uploads endpoints), each appended to a file on disk, and then hands its id
to the endpoint that reads it (POST /databases/import)."""

import json
import re
import secrets
import tempfile
import time
from pathlib import Path
from typing import AsyncIterator, BinaryIO, Optional, Tuple


class UploadNotFoundError(Exception):
    """The upload is unknown: never started, already used, discarded or abandoned."""


class UploadOffsetError(Exception):
    """A part does not start where the upload ends (e.g. one sent again after it arrived)."""


class UploadLengthError(Exception):
    """A part goes past the length of the upload, or the upload is used before all of it has arrived."""


class UploadService:
    # An upload left alone that long (the client went away) is removed when the next one starts.
    MAX_AGE_SECONDS = 24 * 60 * 60
    _ID = re.compile(r"[0-9a-f]{32}")

    def __init__(self, directory: Optional[Path] = None):
        # The temporary directory: TMPDIR, which a deployment points at a volume with room for the largest archive.
        self._directory = directory or Path(tempfile.gettempdir()) / "medidex-uploads"

    def _paths(self, upload_id: str) -> Tuple[Path, Path]:
        """The file of an upload and the file with its length."""
        if not self._ID.fullmatch(upload_id):
            raise UploadNotFoundError(f"Upload {upload_id} not found")
        data, info = self._directory / f"{upload_id}.part", self._directory / f"{upload_id}.json"
        if not data.is_file() or not info.is_file():
            raise UploadNotFoundError(f"Upload {upload_id} not found")
        return data, info

    def start(self, length: int) -> str:
        """A new, empty upload of a file of `length` bytes; its id is the secret its parts are sent with."""
        self._directory.mkdir(parents=True, exist_ok=True)
        self._remove_abandoned()
        upload_id = secrets.token_hex(16)
        (self._directory / f"{upload_id}.json").write_text(json.dumps({"length": length}))
        (self._directory / f"{upload_id}.part").touch()
        return upload_id

    def status(self, upload_id: str) -> Tuple[int, int]:
        """How many bytes of the upload have arrived (where its next part starts) and how many it has."""
        data, info = self._paths(upload_id)
        return data.stat().st_size, json.loads(info.read_text())["length"]

    async def append(self, upload_id: str, offset: int, chunks: AsyncIterator[bytes]) -> int:
        """Appends a part, starting at `offset`, and returns how many bytes have arrived. A part that broke off is
        kept as far as it came; the client goes on from there."""
        data, info = self._paths(upload_id)
        length = json.loads(info.read_text())["length"]
        with data.open("ab") as target:
            received = target.tell()
            if offset != received:
                raise UploadOffsetError(f"The upload has {received} bytes; a part has to start there.")
            async for chunk in chunks:
                if received + len(chunk) > length:
                    raise UploadLengthError(f"The upload has only {length} bytes.")
                target.write(chunk)
                received += len(chunk)
            return received

    def take(self, upload_id: str) -> BinaryIO:
        """The uploaded file, open for reading, and the upload done: the file is removed from the directory, and from
        disk once the handle is closed."""
        received, length = self.status(upload_id)
        if received != length:
            raise UploadLengthError(f"Only {received} of the {length} bytes of the upload have arrived.")
        data, info = self._paths(upload_id)
        source = data.open("rb")
        data.unlink()
        info.unlink()
        return source

    def discard(self, upload_id: str) -> None:
        for path in self._paths(upload_id):
            path.unlink(missing_ok=True)

    def _remove_abandoned(self) -> None:
        oldest = time.time() - self.MAX_AGE_SECONDS
        for path in self._directory.iterdir():
            try:
                if path.stat().st_mtime < oldest:
                    path.unlink()
            except FileNotFoundError:
                pass


upload_service = UploadService()
