from typing import Protocol

from rispy.parser import RisParser
import rispy
import nbib
import io


class RisParseError(ValueError):
    """A bibliography file couldn't be parsed, or its extension isn't supported.

    Carries the HTTP status code the REST API originally responded with
    (fastapi_app/projects.py translates it back to an HTTPException) so that
    mapping stays out of this framework-agnostic module - callers that don't
    care about HTTP (mcp_server/tools.py) can just treat it as the ValueError
    it already is.
    """

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class UploadedFile(Protocol):
    """Structural type for what parse_file() needs from an uploaded file -
    satisfied by FastAPI's UploadFile without importing it, and just as well
    by a plain in-memory stand-in (see mcp_server/tools.py's _InMemoryUpload).
    """

    filename: str

    async def read(self) -> bytes: ...


async def parse_file(file: UploadedFile):
    entries = None
    class CgiParser(RisParser):
        START_TAG = "DB"

    def add_end_tag(text: str) -> str:
        return '\n'.join(
            line if line.strip() else "ER  -  \n\n"
            for line in text.splitlines()
        )

    if file.filename.endswith(".ris"):
        try:
            content = await file.read()
            text_stream = io.StringIO(content.decode('utf-8-sig'))  # RIS is plain text
            entries = rispy.load(text_stream)  # returns a list of dicts
        except Exception as e:
            raise RisParseError(f"Failed to parse .ris: {str(e)}", status_code=500) from e

    elif file.filename.endswith(".cgi"):
        try:
            content = await file.read()
            text_stream = io.StringIO(add_end_tag(content.decode('utf-8-sig')))  # RIS is plain text
            entries = rispy.load(text_stream, implementation=CgiParser, skip_unknown_tags=True)  # returns a list of dicts
        except Exception as e:
            raise RisParseError(f"Failed to parse .cgi: {str(e)}", status_code=500) from e

    elif file.filename.endswith(".nbib"):
        try:
            content = await file.read()
            decoded = content.decode("utf-8-sig")
            entries = nbib.read(decoded)
        except Exception as e:
            raise RisParseError(f"Failed to parse .nbib: {str(e)}", status_code=500) from e

    else:
        raise RisParseError("Only .ris and .nbib files are accepted", status_code=400)

    return entries
