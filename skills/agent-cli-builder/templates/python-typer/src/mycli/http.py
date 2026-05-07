"""HTTP client helpers for REST-backed CLIs.

Maps HTTP status codes to the CLI's semantic exit codes so an agent can
branch on the real failure type (auth, quota, timeout, network) without
parsing prose.

Usage:

    from .http import HttpClient

    client = HttpClient(
        base_url="https://api.example.com/v1",
        token=os.environ.get("MYCLI_TOKEN"),
        timeout=state.timeout,
    )
    body = client.get("/widgets", params={"limit": 50})
    body = client.post("/widgets", json={"name": "alpha"})

The client uses the `urllib.request` standard library so the template has
no external HTTP dependency. Swap in `httpx` or `requests` when you need
async, retries with backoff, or HTTP/2 — the surface is small enough to
port in a few minutes.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .errors import (
    AuthError,
    CliError,
    ExitCode,
    NetworkError,
    PolicyError,
    QuotaError,
    TimeoutCliError,
    ValidationError,
)


class HttpClient:
    """Minimal JSON HTTP client with semantic-exit-code error mapping."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        timeout: float = 30.0,
        user_agent: str = "mycli/0.1.0",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.user_agent = user_agent

    # ------------------------------------------------------------------
    # Public verbs

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(
        self, path: str, *, json: Any | None = None, params: dict[str, Any] | None = None
    ) -> Any:
        return self._request("POST", path, params=params, body=json)

    def patch(
        self, path: str, *, json: Any | None = None, params: dict[str, Any] | None = None
    ) -> Any:
        return self._request("PATCH", path, params=params, body=json)

    def put(
        self, path: str, *, json: Any | None = None, params: dict[str, Any] | None = None
    ) -> Any:
        return self._request("PUT", path, params=params, body=json)

    def delete(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._request("DELETE", path, params=params)

    # ------------------------------------------------------------------
    # Internals

    def _build_url(self, path: str, params: dict[str, Any] | None) -> str:
        url = self.base_url + ("/" + path.lstrip("/")) if path else self.base_url
        if params:
            qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{qs}" if qs else url
        return url

    def _headers(self) -> dict[str, str]:
        h = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any | None = None,
    ) -> Any:
        url = self._build_url(path, params)
        headers = self._headers()
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
                if not payload:
                    return None
                return json.loads(payload.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self._raise_for_http_status(exc)
        except (urllib.error.URLError, socket.timeout) as exc:
            self._raise_for_transport(exc)

    def _raise_for_http_status(self, exc: urllib.error.HTTPError) -> None:
        """Map HTTP status to a CliError with the right exit code."""
        status = exc.code
        try:
            body_bytes = exc.read()
            body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {}
        message = (body.get("error") or {}).get("message") if isinstance(body, dict) else None
        message = message or body.get("message") if isinstance(body, dict) else None
        message = message or f"HTTP {status} from {exc.url}"

        # Forward upstream suggestions when the API uses our envelope shape;
        # otherwise fall back to a sensible default per status class.
        upstream_suggestions: list[str] = []
        if isinstance(body, dict):
            err_obj = body.get("error") or {}
            if isinstance(err_obj.get("suggestions"), list):
                upstream_suggestions = [str(s) for s in err_obj["suggestions"]]
            elif isinstance(err_obj.get("hint"), str):
                upstream_suggestions = [err_obj["hint"]]

        def _sugg(*defaults: str) -> list[str]:
            return upstream_suggestions or list(defaults)

        if status in (400, 422):
            raise ValidationError(
                message,
                suggestions=_sugg("Inspect the request body for invalid fields."),
            )
        if status == 401:
            raise AuthError(
                message, suggestions=_sugg("Check your credentials and retry.")
            )
        if status == 403:
            raise AuthError(
                message, suggestions=_sugg("The token does not have the required scopes.")
            )
        if status == 404:
            raise CliError(
                code="NOT_FOUND",
                exit_code=ExitCode.VALIDATION,
                message=message,
                suggestions=_sugg("Verify the resource id and try again."),
            )
        if status == 408:
            raise TimeoutCliError(message, suggestions=upstream_suggestions or None)
        if status == 429:
            raise QuotaError(message, suggestions=upstream_suggestions or None)
        if status == 451:
            raise PolicyError(
                message, suggestions=_sugg("The request was blocked by policy.")
            )
        if 500 <= status < 600:
            raise NetworkError(
                f"upstream {status}: {message}",
                suggestions=_sugg(
                    "Retry with backoff; if persistent, the upstream is degraded."
                ),
            )
        raise CliError(
            code=f"HTTP_{status}",
            exit_code=ExitCode.GENERAL,
            message=message,
            suggestions=upstream_suggestions,
        )

    def _raise_for_transport(self, exc: Exception) -> None:
        if isinstance(exc, socket.timeout):
            raise TimeoutCliError(
                f"timed out after {self.timeout}s",
                suggestions=[
                    "Increase --timeout for long-running operations.",
                    "Or use --async if the underlying API supports it.",
                ],
            )
        # urllib.error.URLError wraps socket-level failures
        reason = getattr(exc, "reason", exc)
        raise NetworkError(
            f"transport error: {reason}",
            suggestions=[
                "Check connectivity and DNS, then retry with backoff.",
            ],
        )
