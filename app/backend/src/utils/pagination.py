"""Opaque pagination cursors, shared across every list endpoint that pages results -
framework-agnostic so every head (the REST API, and any MCP tool doing the same) can
mint and consume the same cursor values. The encoded integer means whatever the caller
needs it to: a keyset cursor (the last row id, e.g. ReportPage.nextCursor) for results
ordered by a stable id, or a plain offset for results ordered by something else (e.g.
SimilarStudyPage.nextCursor, which pages a relevance-ranked list).
"""

import base64


class InvalidCursorError(ValueError):
    """A pagination cursor couldn't be decoded."""


def encode_cursor(position: int) -> str:
    return base64.urlsafe_b64encode(str(position).encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursorError(f"Invalid cursor: {cursor!r}") from exc
