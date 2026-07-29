"""Typed domain errors and the single JSON error envelope for ``/api/v1``.

Every failure returned by the API blueprint uses one envelope::

    {"error": "<human-readable string>", "code": "<machine slug>",
     "details": [ ... ]}

``error`` is always a human-readable string because browser code displays it
directly (``result.error || "fallback"`` in ``unit_speed.js``,
``room_matrix.js``, ``room_dashboard.js``, and ``fcu_history_chart.js``).
``code`` is the stable machine-readable discriminator; add new codes rather than
re-purposing existing ones. ``details`` is always a list and is omitted when
empty.

Routes raise these exceptions instead of building error responses. The handlers
registered by :func:`register_error_handlers` perform the single
exception-to-status mapping for the blueprint.

``NotFound`` and ``Conflict`` deliberately subclass ``LookupError`` and
``ValueError`` so database and service code can raise the precise type while
non-route callers (``bin/runner.py``, ``bin/rules.py``, tests) that catch the
builtin types keep working unchanged. That compatibility only holds while route
handlers do *not* catch the builtins themselves: an ``except ValueError`` in a
route would swallow a ``Conflict`` and answer 400 instead of 409.
"""

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from flask import jsonify, request
from werkzeug.exceptions import HTTPException
from pydantic import ValidationError

from flask_pydantic.exceptions import ValidationError as FlaskPydanticValidationError

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Base class for failures that map to a documented API response.

    Subclasses set ``status`` and ``code``. ``message`` is shown to operators,
    so it must never carry credentials or upstream connection details.
    """

    status = 500
    code = "internal_error"
    message = "Internal server error"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: list[dict[str, Any]] | None = None,
    ):
        self.message = message or type(self).message
        self.code = code or type(self).code
        self.details = details or []
        self.status = type(self).status
        super().__init__(self.message)

    def with_status(self, status: int) -> "ApiError":
        """Override the status for one instance and return self.

        Only the werkzeug passthrough needs this; subclasses carry their own
        status as a class attribute.
        """
        self.status = status
        return self

    def payload(self) -> dict[str, Any]:
        """Return the JSON body for this error."""
        body: dict[str, Any] = {"error": self.message, "code": self.code}
        if self.details:
            body["details"] = self.details
        return body


class BadRequest(ApiError):
    """The request was understood but is not usable as sent."""

    status = 400
    code = "bad_request"
    message = "Bad request"


class ValidationFailed(BadRequest):
    """A request body or query string failed schema validation."""

    code = "validation_error"
    message = "validation error"


class NotFound(ApiError, LookupError):
    """A referenced entity does not exist."""

    status = 404
    code = "not_found"
    message = "Not found"


class Conflict(ApiError, ValueError):
    """The request is well-formed but conflicts with current state."""

    status = 409
    code = "conflict"
    message = "Conflict"


class UpstreamUnavailable(ApiError):
    """A hardware integration or external service could not be reached."""

    status = 502
    code = "upstream_unavailable"
    message = "Upstream request failed"


def _normalize_pydantic_errors(
    errors: Iterable[Mapping[str, Any]], location: str
) -> list[dict[str, Any]]:
    """Return pydantic error entries in the shape used by ``details``.

    ``ctx`` is dropped because it holds arbitrary objects that are not reliably
    JSON-serializable; the human-readable ``msg`` already states the constraint.
    ``url`` is dropped because it embeds the installed pydantic version
    (``errors.pydantic.dev/2.12/...``), and a documented API contract should not
    change when a dependency is upgraded.
    ``location`` records which part of the request failed, which the raw
    per-parameter grouping would otherwise be the only way to express.
    """
    dropped = {"ctx", "url"}
    normalized = []
    for error in errors:
        entry = {key: value for key, value in error.items() if key not in dropped}
        entry["location"] = location
        normalized.append(entry)
    return normalized


def _summarize(details: list[dict[str, Any]]) -> str:
    """Build a human-readable summary of validation failures.

    Browser dialogs surface this string, so it names the offending fields
    instead of reporting a bare "validation error". Only the first few entries
    are included to keep the message readable.
    """
    parts = []
    for entry in details[:3]:
        loc = ".".join(str(part) for part in entry.get("loc", ()))
        msg = entry.get("msg", "is invalid")
        parts.append(f"{loc}: {msg}" if loc else str(msg))
    if not parts:
        return ValidationFailed.message
    summary = "; ".join(parts)
    remaining = len(details) - len(parts)
    if remaining > 0:
        summary += f" (and {remaining} more)"
    return summary


def validation_failed_from_pydantic(
    error: ValidationError, location: str = "body"
) -> ValidationFailed:
    """Convert a pydantic ``ValidationError`` into the standard API error."""
    details = _normalize_pydantic_errors(error.errors(include_context=False), location)
    return ValidationFailed(_summarize(details), details=details)


def validation_failed_from_flask_pydantic(
    error: FlaskPydanticValidationError,
) -> ValidationFailed:
    """Flatten ``flask_pydantic``'s per-location error groups into one list.

    ``flask_pydantic`` reports a mapping keyed by request location. Flattening
    it to a list keeps ``details`` a single uniform type across every endpoint,
    whether the route uses the ``@validate()`` decorator or validates a model
    by hand.
    """
    details: list[dict[str, Any]] = []
    for attribute, location in (
        ("body_params", "body"),
        ("query_params", "query"),
        ("form_params", "form"),
        ("path_params", "path"),
    ):
        errors = getattr(error, attribute, None)
        if errors:
            details.extend(_normalize_pydantic_errors(errors, location))
    return ValidationFailed(_summarize(details), details=details)


def register_error_handlers(blueprint) -> None:
    """Install the blueprint's single exception-to-response mapping."""

    @blueprint.errorhandler(ApiError)
    def _handle_api_error(error: ApiError):
        # Expected, already-classified failures: log at info so operational logs
        # stay readable, and return the error's own status.
        logger.info(
            "%s %s -> %s %s: %s",
            request.method,
            request.path,
            error.status,
            error.code,
            error.message,
        )
        return jsonify(error.payload()), error.status

    @blueprint.errorhandler(FlaskPydanticValidationError)
    def _handle_flask_pydantic_error(error: FlaskPydanticValidationError):
        return _handle_api_error(validation_failed_from_flask_pydantic(error))

    @blueprint.errorhandler(ValidationError)
    def _handle_pydantic_error(error: ValidationError):
        return _handle_api_error(validation_failed_from_pydantic(error))

    @blueprint.errorhandler(HTTPException)
    def _handle_http_exception(error: HTTPException):
        # Werkzeug raises these from inside a view -- a malformed JSON body
        # becomes a BadRequest, for example. Without this arm the generic
        # Exception handler below would catch them first (Flask consults
        # blueprint handlers before app-level ones) and report a client mistake
        # as a 500. Werkzeug's own names map cleanly onto our code slugs:
        # "Bad Request" -> bad_request, "Not Found" -> not_found.
        code = (error.name or "error").strip().lower().replace(" ", "_")
        return _handle_api_error(
            ApiError(
                error.description or error.name,
                code=code or ApiError.code,
            ).with_status(error.code or 500)
        )

    @blueprint.errorhandler(Exception)
    def _handle_unexpected_error(error: Exception):
        # Unexpected failures are logged with request context and a traceback,
        # but the response body stays generic so exception text (which can name
        # devices, hosts, or credentials) never reaches the client.
        logger.exception(
            "Unhandled API error: %s %s: %s",
            request.method,
            request.path,
            type(error).__name__,
        )
        return jsonify(ApiError().payload()), ApiError.status
