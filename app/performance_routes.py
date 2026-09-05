"""Web and JSON routes for integration performance monitoring."""

import time

from flask import Blueprint, jsonify, render_template, request
from pydantic import ValidationError

from . import performance_monitoring
from .api_errors import (
    BadRequest,
    register_error_handlers,
    validation_failed_from_pydantic,
)
from .utils.db_utils import with_db_connection

performance_routes = Blueprint("performance_monitoring", __name__)
register_error_handlers(performance_routes)


def _integer_query_arg(name: str, default: int) -> int:
    raw_value = request.args.get(name)
    return default if raw_value is None else int(raw_value)


@performance_routes.get("/performance-monitoring")
def performance_page():
    """Render the integration and network performance chart."""
    return render_template(
        "performance-monitoring.html", current_page="performance-monitoring"
    )


@performance_routes.get("/api/v1/performance_samples")
@with_db_connection
def performance_samples(conn):
    """Return a bounded time range of typed performance samples."""
    now_ms = time.time_ns() // 1_000_000
    try:
        query = performance_monitoring.PerformanceQuery(
            start_ms=_integer_query_arg(
                "start_ms", now_ms - 24 * 60 * 60 * 1000
            ),
            end_ms=_integer_query_arg("end_ms", now_ms),
            instance_id=request.args.get("instance_id") or None,
            client_id=request.args.get("client_id") or None,
            sample_type=request.args.get("sample_type") or None,
            operation=request.args.get("operation") or None,
            limit=_integer_query_arg(
                "limit", performance_monitoring.DEFAULT_QUERY_LIMIT
            ),
        )
    except ValidationError as error:
        raise validation_failed_from_pydantic(error, "query") from error
    except ValueError as error:
        raise BadRequest(str(error)) from error
    if query.end_ms < query.start_ms:
        raise BadRequest("end_ms must not precede start_ms")
    page = performance_monitoring.fetch_sample_page(conn, query)
    return jsonify(page.model_dump(mode="json"))
