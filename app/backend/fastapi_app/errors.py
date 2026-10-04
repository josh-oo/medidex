from fastapi import HTTPException

from src.services.authorization import (
    ReportNotFoundError,
    AuthenticationRequiredError,
    ReportAccessDeniedError,
)


def raise_for_report_access(exc: Exception):
    """Shared translation for the report-access exceptions raised deep inside a
    service call (get_authorized_project_id, src/services/authorization.py) -
    every route below used to gate on these via a separate check_report_access
    FastAPI dependency; now each service call performs its own access check, so
    the router only needs to translate whatever it raises.
    """
    if isinstance(exc, ReportNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, AuthenticationRequiredError):
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if isinstance(exc, ReportAccessDeniedError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
