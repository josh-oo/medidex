"""Opaque keyset-pagination cursors for report list pages (ReportPage.nextCursor) -
framework-agnostic so every head that paginates a project's reports (the REST API,
and any MCP tool doing the same) can mint and consume the same cursor values.
"""

import base64


class InvalidCursorError(ValueError):
    """A pagination cursor couldn't be decoded."""


def encode_cursor(report_id: int) -> str:
    return base64.urlsafe_b64encode(str(report_id).encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursorError(f"Invalid cursor: {cursor!r}") from exc
