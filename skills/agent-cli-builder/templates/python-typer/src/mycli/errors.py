"""Exit code taxonomy and the structured error envelope.

The taxonomy and the envelope are the two things the agent will branch on
when something goes wrong. Keep them stable across versions; bumping an
exit code or renaming an error code is a breaking change.

Errors carry a list of `suggestions` (recovery actions, in priority order)
rather than a single `hint`. Agents reliably benefit from multiple options.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class ExitCode:
    OK = 0
    GENERAL = 1
    VALIDATION = 2
    AUTH = 3
    QUOTA = 4
    TIMEOUT = 5
    NETWORK = 6
    POLICY = 10
    INTERRUPTED = 130


@dataclass
class CliError(Exception):
    """An error with a stable code and actionable suggestions.

    The CLI's top-level handler turns this into the JSON error envelope
    and exits with `exit_code`. Always include at least one suggestion
    when you can — they reduce repair-loop length more than any other
    change.
    """

    code: str
    exit_code: int
    message: str
    suggestions: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict:
        """Render to the agent-facing error body. The envelope is built around this."""
        return {
            "code": self.code,
            "exit_code": self.exit_code,
            "message": self.message,
            "suggestions": list(self.suggestions),
        }


class ValidationError(CliError):
    def __init__(self, message: str, *, suggestions: list[str] | None = None) -> None:
        super().__init__(
            code="VALIDATION_ERROR",
            exit_code=ExitCode.VALIDATION,
            message=message,
            suggestions=suggestions or [],
        )


class AuthError(CliError):
    def __init__(self, message: str, *, suggestions: list[str] | None = None) -> None:
        super().__init__(
            code="AUTH_ERROR",
            exit_code=ExitCode.AUTH,
            message=message,
            suggestions=suggestions
            or ["Run `mycli auth status` to inspect credentials."],
        )


class QuotaError(CliError):
    def __init__(self, message: str, *, suggestions: list[str] | None = None) -> None:
        super().__init__(
            code="QUOTA_EXCEEDED",
            exit_code=ExitCode.QUOTA,
            message=message,
            suggestions=suggestions or ["Backoff and retry after the rate-limit window."],
        )


class TimeoutCliError(CliError):
    def __init__(self, message: str, *, suggestions: list[str] | None = None) -> None:
        super().__init__(
            code="TIMEOUT",
            exit_code=ExitCode.TIMEOUT,
            message=message,
            suggestions=suggestions
            or ["Increase --timeout or use --async for long-running work."],
        )


class NetworkError(CliError):
    def __init__(self, message: str, *, suggestions: list[str] | None = None) -> None:
        super().__init__(
            code="NETWORK_ERROR",
            exit_code=ExitCode.NETWORK,
            message=message,
            suggestions=suggestions or ["Retry with backoff."],
        )


class PolicyError(CliError):
    def __init__(self, message: str, *, suggestions: list[str] | None = None) -> None:
        super().__init__(
            code="POLICY_BLOCK",
            exit_code=ExitCode.POLICY,
            message=message,
            suggestions=suggestions or [],
        )
