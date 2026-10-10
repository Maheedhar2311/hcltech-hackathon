"""HTTP client the Streamlit UI uses to call the API (architecture: UI -> FastAPI only).

Standard library only, so the UI container needs nothing beyond Streamlit. Every
function raises ApiError with the server's message when the API returns an error.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import date
from typing import Any, Optional


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


def _request(method: str, url: str, body: Optional[bytes] = None,
             headers: Optional[dict] = None, timeout: int = 300) -> Any:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail", exc.reason)
        except Exception:
            detail = exc.reason
        raise ApiError(exc.code, str(detail)) from exc


def ask(base: str, question: str, as_of: Optional[date], student_id: Optional[str]) -> dict:
    payload: dict[str, Any] = {"question": question}
    if as_of:
        payload["as_of_date"] = as_of.isoformat()
    headers = {"Content-Type": "application/json"}
    if student_id:
        headers["X-Student-Id"] = student_id
    return _request("POST", f"{base}/ask", json.dumps(payload).encode(), headers)


def ingest(base: str, filename: str, data: bytes, metadata: dict) -> dict:
    boundary = uuid.uuid4().hex
    parts = [
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="metadata"\r\n\r\n'
        f"{json.dumps(metadata)}\r\n",
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n",
    ]
    body = "".join(parts).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return _request("POST", f"{base}/ingest", body, headers)


def sources(base: str) -> list[dict]:
    return _request("GET", f"{base}/sources")


def audit(base: str, trace_id: str) -> dict:
    return _request("GET", f"{base}/audit/{trace_id}")


def health(base: str) -> dict:
    """Component status. A 503 still returns the per-component body, so read it directly."""
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))
    except Exception as exc:
        return {"api": f"unreachable: {exc}"}
