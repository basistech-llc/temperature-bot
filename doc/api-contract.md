# API Contract: `/api/v1`

How every JSON endpoint under `/api/v1` reports success and failure. Written
for GitHub #185. The implementation lives in `app/api_errors.py`; the request
and response models live in `app/models.py`.

## Database snapshot download

`GET /api/v1/database-snapshot` is a binary, production-only exception to the
JSON response convention. It has no application authentication because the
production hostname is reachable only through the company VPN. Non-production
instances answer 404 so a staging or developer database cannot be downloaded
by mistake.

The response is an `application/vnd.sqlite3` attachment named
`temperature-bot.db`, with `Cache-Control: no-store`, `X-Database-Size`, and
`X-Database-SHA256` headers. The server uses SQLite's backup API, includes
committed WAL data, and runs `PRAGMA quick_check` before responding. Concurrent
snapshot creation for the same database answers 409. `make fetch-dev-db` is the
supported client and verifies the SHA-256 before migration.

## Error envelope

Every failure returns the same JSON object:

```json
{
  "error": "device_id: Field required",
  "code": "validation_error",
  "details": [
    {
      "loc": ["device_id"],
      "msg": "Field required",
      "type": "missing",
      "input": {},
      "location": "body"
    }
  ]
}
```

| Field | Always present | Meaning |
| --- | --- | --- |
| `error` | yes | Human-readable message. Browser code renders this string directly. |
| `code` | yes | Stable machine-readable discriminator. Branch on this, not on `error`. |
| `details` | no | Field-level validation failures. Always a list; omitted when empty. |

Rules for changing this contract:

- `error` must stay a human-readable string. About fifteen browser call sites do
  `result.error || "fallback"` (`unit_speed.js`, `room_matrix.js`,
  `room_dashboard.js`, `fcu_history_chart.js`). Its exact wording is not stable
  and must not be parsed.
- `code` is the stable part. Add new codes rather than re-purposing existing
  ones.
- `details` is always a list, never an object, whether the route used
  `@validate()` or validated a model by hand.

## Status codes

| Status | `code` | Exception | Raised when |
| --- | --- | --- | --- |
| 400 | `bad_request` | `BadRequest` | The request is unusable for a reason no schema expresses. |
| 400 | `validation_error` | `ValidationFailed` | A body or query string failed schema validation. Carries `details`. |
| 404 | `not_found` | `NotFound` | A referenced device, room, or configuration does not exist. |
| 409 | `conflict` | `Conflict` | The request is well-formed but conflicts with current state. |
| 502 | `upstream_unavailable` | `UpstreamUnavailable` | An AE-200, Hubitat, or other integration could not be reached. |
| 500 | `internal_error` | anything unhandled | A bug. Logged with a traceback; the body stays generic. |

Successful mutations return `{"status": "ok", ...}`. Two endpoints
intentionally differ and should stay that way: `POST /api/v1/rooms` returns 201
with the created room, and `DELETE /api/v1/rooms/<id>` returns 204 with an
empty body.

## Where errors are raised

Routes raise; they do not build error responses. `app/api_errors.py` registers
the blueprint's single exception-to-status mapping.

`NotFound` and `Conflict` also subclass `LookupError` and `ValueError` so that
`db.py` can raise the precise type while non-route callers that catch the
builtins keep working.

**This makes route error handling order-sensitive.** `Conflict` *is* a
`ValueError`, so a route that catches `ValueError` without letting `ApiError`
through first will report an already-classified 409 as a generic 400 — a
regression that looks like nothing happened. `routes_api._domain_errors()` is
the only place that catches `ValueError`, and it re-raises `ApiError` first.
`tests/test_api_error_contracts.py::test_db_conflict_is_not_flattened_to_bad_request`
guards this.

## Response serialization

Two dump conventions, and endpoints must pick the right one:

- `models.json_ready()` — `exclude_none=True`. Omits keys whose value is
  unavailable. Correct for command responses and for payloads whose consumers
  test key *presence*.
- `models.alert_json_ready()` — keeps nulls, omits only an absent `details`.
  Alert rows need both behaviors at once: `end_time` is null while an alert is
  unresolved and must stay present, while `details` appears only when the
  caller passes `include_details`.

Adding a response model to an endpoint that currently emits nulls will silently
drop those keys. Check a captured payload for real nulls before wrapping
anything; do not infer from type annotations.

## Endpoints not yet typed, and why

- `/status` and `/devices` return sparse, row-varying dictionaries containing
  real nulls. No single model reproduces that: `exclude_none` drops the nulls,
  and including them adds keys that are absent today. These are also the
  dashboard payloads `routes_web.py` renders into Jinja, so changing their dump
  semantics is an HTML change as well as an API change. Typing them belongs to
  GitHub #182, "Replace dashboard dictionaries with strict Pydantic view
  models".
- `/air_quality` derives its keys from the `aqi` table's columns at runtime and
  returns a list rather than an object when there are no rows.
- `/debug/*` is debug-page scaffolding with no client contract.

## Known gap

Requests that fail *before* a view runs — an unmatched path under `/api/v1/`, or
a wrong method on a real route — never reach the blueprint error handler,
because Flask has no blueprint context at routing time. They fall through to
`main.py`'s app-level `HTTPException` handler, which returns `{"error": "..."}`
with **no `code` field**. Clients must tolerate a missing `code` on 404s from
unknown paths and on 405s.

Werkzeug errors raised *inside* a view — a malformed JSON body, for instance —
do get the full envelope, because the blueprint's `HTTPException` handler sees
them. That handler exists specifically so the generic `Exception` handler cannot
report those client mistakes as 500s.

Closing the remaining gap means branching on `request.path` in `main.py`, which
also currently JSONifies HTTP errors for ordinary web pages.
