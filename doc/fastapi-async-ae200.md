# FastAPI, Async, and AE-200 Control

This note captures a possible future direction for Temperature Bot: moving from
Flask plus synchronous request handlers to an async ASGI application, likely
FastAPI, with websocket support for the browser UI.

## Current Position

The application is a Flask service with server-rendered Jinja pages, JSON API
endpoints, SQLite persistence, and a mix of synchronous app code plus async
AE-200 websocket calls hidden behind `app/ae200.py`.

The immediate problem is not Flask itself. The problem is the boundary where
synchronous Flask handlers call async AE-200 websocket code. That boundary needs
to be explicit, serialized, and timeout-aware so Mitsubishi control failures do
not become Flask request failures or event-loop ownership bugs.

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

- AE-200 commands can be serialized at the existing command boundary.
- Web and runner processes can share a file-backed command lock.
- The async bridge can stop reusing event loops across requests.
- Flask routes can continue returning the same JSON contracts and rendering the
  same Jinja templates.
- Existing tests, Makefile targets, local-dev flows, and production deployment
  behavior remain valid.

Moving now would create avoidable risk:

- SQLite and rules-engine work is still synchronous, so a naive async migration
  could block the ASGI event loop anyway.
- The browser UI is mostly server-rendered plus targeted JavaScript; converting
  it to websocket-driven state needs design and test work.
- AE-200 hardware control needs command isolation, timeout behavior, and error
  reporting regardless of whether the web framework is Flask or FastAPI.

The pragmatic path is to first isolate AE-200 I/O behind a small command
boundary. That makes the current Flask app more reliable and keeps a future
FastAPI migration cleaner.

## Current AE-200 Boundary

For now, application code should use the module-level synchronous functions in
`app/ae200.py` (`get_devices`, `get_device_info`, `set_mode`,
`set_fan_speed`, `set_drive`, and related wrappers). Those functions pass live
AE-200 websocket reads and writes through one runner. That runner should:

- Run async websocket calls without reusing a stale event loop.
- Allow only one in-flight AE-200 command at a time inside the process.
- Use a file-backed lock so the web process and runner process do not talk to
  the AE-200 simultaneously.
- Return structured errors to route handlers rather than leaking low-level
  event-loop failures.

This is enough for the current Flask app because each UI action can still make a
simple synchronous request while AE-200 access is serialized underneath.

## Workqueue Option

A workqueue for AE-200 commands makes sense, but it is a larger design choice
than the current semaphore.

It would be useful if we need:

- User-visible command status, such as queued, running, succeeded, failed, or
  timed out.
- Backpressure when a browser, cronjob, or rules pass submits several commands.
- Cross-process ownership of all AE-200 commands rather than cooperative locks.
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
2. Put all commands into one in-memory worker queue with a small timeout.
3. Serialize execution in a dedicated worker thread.
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
