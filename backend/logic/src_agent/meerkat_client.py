from __future__ import annotations

import os
import http.client
import time
import urllib.error
import urllib.request

from .config import logger


def _build_meerkat_url(path: str) -> str:
    base_url = os.getenv("MEERKAT_API_URL", "").strip()
    if not base_url:
        raise ValueError("MEERKAT_API_URL is not set")
    return f"{base_url.rstrip('/')}/api{path}"


def _build_meerkat_headers(accept: str) -> dict[str, str]:
    headers = {"Accept": accept}
    api_key = os.getenv("MEERKAT_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def fetch_report_pdf(report_id: int) -> bytes | None:
    url = _build_meerkat_url(f"/reports/{report_id}/pdf")
    headers = _build_meerkat_headers("application/pdf")
    request = urllib.request.Request(url, headers=headers, method="GET")
    timeout_seconds = float(os.getenv("MEERKAT_TIMEOUT_SECONDS", "60"))
    max_retries = int(os.getenv("MEERKAT_PDF_RETRIES", "2"))
    base_backoff = float(os.getenv("MEERKAT_PDF_RETRY_BACKOFF_SECONDS", "0.5"))

    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                try:
                    return response.read()
                except http.client.IncompleteRead as exc:
                    logger.warning(
                        "fetch_report_pdf: incomplete read report_id=%s read=%s expected=%s attempt=%s",
                        report_id,
                        len(exc.partial or b""),
                        exc.expected,
                        attempt + 1,
                    )
        except urllib.error.HTTPError as exc:
            status = getattr(exc, "code", None)
            logger.warning(
                "fetch_report_pdf: http error report_id=%s status=%s attempt=%s",
                report_id,
                status,
                attempt + 1,
            )
            if status not in {500, 502, 503, 504}:
                return None
        except (urllib.error.URLError, ValueError) as exc:
            logger.warning(
                "fetch_report_pdf: failed report_id=%s error=%s attempt=%s",
                report_id,
                exc,
                attempt + 1,
            )

        if attempt < max_retries:
            time.sleep(base_backoff * (2 ** attempt))

    return None

