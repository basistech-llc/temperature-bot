# FastAPI, Async, and AE-200 Control

This note captures a possible future direction for Temperature Bot: moving from
Flask plus synchronous request handlers to an async ASGI application, likely
FastAPI, with websocket support for the browser UI.

## Current Position

The application is a Flask service with server-rendered Jinja pages, JSON API
endpoints, SQLite persistence, and a mix of synchronous app code plus async
AE-200 websocket calls hidden behind `app/ae200.py`.

The immediate problem is not Flask itself. The boundary where synchronous Flask
handlers call async AE-200 WebSocket code needs to be explicit and timeout-aware
so Mitsubishi control failures do not become Flask request failures or
event-loop ownership bugs. It does not need to serialize independent requests:
each request uses its own WebSocket, and Mitsubishi documents concurrent
clients.

The Mitsubishi technical manual lists simultaneous browser and Integrated
Centralized Control Web clients, and the native protocol broadcasts
`notifyRequest` state changes to connected WebSocket clients. See issue #233
for the official limits, protocol captures, independent implementations, and
security-advisory analysis behind this decision.

## Benefits of Moving to FastAPI and Async

FastAPI or another ASGI framework could be a good fit if the project needs a
broader async service model:

- Native async request handlers for AE-200, Hubitat, Airthings, AQI, and other
  network I/O.
- First-class browser websockets for live dashboards instead of status polling.
- One application model for HTTP JSON APIs and websocket streams.
- Cleaner typing at API boundaries through Pydantic request and response models.
- Better fit for long-lived client sessions, live command status, and push-based
  updates when a device changes state.

Browser websockets would be especially useful for the FCU matrix and room pages:
the server could push device status, command progress, simulator/live state,
alerts, and rule-disable changes as they happen, instead of making JavaScript
poll `/api/v1/status`.

## Why We Are Not Doing That Now

A FastAPI migration would be a service rewrite, not a bug fix.

The current failures can be addressed without replacing Flask:

- The async bridge can stop reusing event loops across requests.
- Each command can use an independent, short-lived WebSocket connection.
- Writes can validate `setResponse` and read back state when confirmation is
  required.
- Flask routes can continue returning the same JSON contracts and rendering the
  same Jinja templates.
- Existing tests, Makefile targets, local-dev flows, and production deployment
  behavior remain valid.

Moving now would create avoidable risk:

- SQLite and rules-engine work is still synchronous, so a naive async migration
  could block the ASGI event loop anyway.
- The browser UI is mostly server-rendered plus targeted JavaScript; converting
  it to websocket-driven state needs design and test work.
- AE-200 hardware control needs timeout behavior, response validation, and
  error reporting regardless of whether the web framework is Flask or FastAPI.

The pragmatic path is to first isolate AE-200 I/O behind a small command
boundary. That makes the current Flask app more reliable and keeps a future
FastAPI migration cleaner.

## Current AE-200 Boundary

For now, application code should use the module-level synchronous functions in
`app/ae200.py` (`get_devices`, `get_device_info`, `set_mode`,
`set_fan_speed`, `set_drive`, and related wrappers). Those functions pass live
AE-200 websocket reads and writes through one runner. That runner should:

- Run async websocket calls without reusing a stale event loop.
- Allow independent one-request-per-WebSocket commands to overlap.
- Return structured errors to route handlers rather than leaking low-level
  event-loop failures.

This is enough for the current Flask app because each UI action can still make a
simple synchronous request while other controller clients continue operating.

## Workqueue Option

A workqueue for AE-200 commands could support product features, but it is not
required for protocol correctness.

It would be useful if we need:

- User-visible command status, such as queued, running, succeeded, failed, or
  timed out.
- Backpressure when a browser, cronjob, or rules pass submits several commands.
- Centralized timeout and retry policy.
- Durable logging of command attempts and outcomes.
- Optional isolation in a worker thread or separate process.

The queue should be careful with retries. Read operations such as
`get_device_info` are safe to retry after connection failures. Write operations
such as `set_mode`, `set_fan_speed`, and `set_drive` are usually idempotent when
the desired final value is explicit, but retries can still confuse the UI if the
AE-200 applied the command and the acknowledgement failed. A future queue should
record the desired final state, retry only bounded recoverable failures, then
read back device state to confirm the result.

Recommended future shape:

1. Define Pydantic command/result models for AE-200 operations.
2. Add a bounded queue only if measurements show backpressure is needed.
3. Coalesce superseded writes to the same device where semantics permit it.
4. Add bounded retries for reads and idempotent writes.
5. Report command status through JSON first.
6. Add browser websockets later to stream status and device updates.
7. Move the worker to a separate process only if hardware calls can hang or
   destabilize the Flask process.

## Migration Trigger

Revisit FastAPI when at least one of these is true:

- The browser UI needs push updates across multiple pages.
- AE-200 command status needs to be tracked as first-class state.
- Multiple network integrations benefit from concurrent async polling.
- The current Flask/Jinja architecture blocks a feature rather than merely
  feeling old.

Until then, the lower-risk architecture is Flask plus a disciplined AE-200
command boundary.
