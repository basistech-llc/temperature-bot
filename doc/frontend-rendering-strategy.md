## Frontend Rendering Strategy

This document describes the **desired frontend rendering approach** for Temperature Bot, plus the
**rationale and concrete guidelines**. It is written for both **human developers** and **LLM
agents** working on this repo.

The overall goal is:

- **Pre-render as much as is reasonable on the server using Jinja2**, so that pages are useful and
  testable from raw HTML.
- **Use JSON APIs plus JavaScript only where true interactivity or live updates are needed.**
- **Avoid moving to a heavy client framework (e.g. React SPA) unless there is a clear, project‑level
  decision to do so.**

---

## 1. Current Architecture (High-Level)

- **Backend framework**: Flask
- **Server-side templating**: Jinja2 templates under `app/templates/`
- **Static assets**: JS/CSS in `app/static/`
- **JSON APIs**: Implemented in `app/routes_api.py`
- **Web pages**: Implemented in `app/routes_web.py`, using `render_template(...)`

Two rendering “layers” coexist:

1. **Server-side HTML (Jinja2)**
   - Route handlers in `routes_web.py` pass Python data structures to templates and return fully
     rendered HTML.
   - Example pages: `index.html`, `rules.html`, `air-quality.html`, `device_log.html`,
     `room_dashboard.html`, etc.

2. **Client-side enhancement / interaction (plain JS + libraries)**
   - JavaScript under `app/static/` calls the `/api/v1/...` endpoints from `routes_api.py`.
   - JS is responsible for **live dashboards, charts, tables, and other highly interactive pieces**:
     - `chart_support.js` + `chart.html` / `chart_aqi.html` (ECharts time-series, AQI charts).
     - `room_dashboard.js` + `room_dashboard.html` (room HVAC control tiles).
     - `logs_today.js`, inline JS in `logs.html`, `alerts.html`, `debug_all_devices.html` (Tabulator
       tables and debug views).

We are **intentionally moving more of the “first useful render” into Jinja2**, while **keeping this
client-side layer** where it adds value.

---

## 2. Why Jinja2 + Server-Side Rendering (SSR)?

### 2.1 Testing and Reliability

- **HTML is the ground truth.** We want core pages to be meaningfully testable by:
  - Fetching HTML via the Flask test client.
  - Asserting on DOM structure and content **without launching Chromium or running JS**.
- This reduces dependency on:
  - Playwright / browser automation for basic correctness.
  - Fragile selectors tied to dynamic, JS-built DOM fragments.

### 2.2 Simpler Mental Model

- For many pages (home, rules, air‑quality tables, device logs):
  - The “shape” of the page is best expressed directly in HTML.
  - The required data comes straight from the database or a single service call.
- Jinja2 keeps:
  - **Layout and loops** in templates.
  - **Data acquisition** in `routes_web.py` and backing modules (`db.py`, `rules_engine.py`, etc.).

### 2.3 Progressive Enhancement

- A page should be **useful and intelligible when JS is disabled or broken.**
- JS should **enhance**:
  - Live refreshing (`room_dashboard.js` polling `/api/v1/status`).
  - Rich charts (ECharts).
  - Interactive tables (Tabulator).

---

## 3. Role of JSON APIs + JavaScript

We **still use client-side JS where it is the right tool**, but we treat it as a second layer.

### 3.1 When to Use JSON APIs + JS

Use the `/api/v1/...` endpoints and client-side rendering when:

- **Data changes frequently** and must be updated without full page reload:
  - Room dashboards polling `status`, setting fan speed/drive/temp.
  - Log or alert tables that refresh in place.
- **Visualization is inherently interactive or complex**:
  - ECharts plots for temperature and AQI.
  - “Select sensors to show” checkboxes and CSV export.
- **Debug tooling**:
  - `debug_all_devices.html` introspection of DB / Hubitat / AE‑200 via debug endpoints.

### 3.2 Expected Pattern

For a client-enhanced page:

- **Jinja2 responsibilities**:
  - Render page shell: headings, layout containers, navigation, and key labels.
  - Include any per-page meta, CSS, and `<script src="...">` tags.
  - Provide initial data that is useful on first paint when it is cheap and stable.

- **JavaScript responsibilities**:
  - Fetch JSON from `routes_api.py`.
  - Mutate the DOM **inside predefined containers** (e.g., `#temp-chart`, `#log-table`,
    `#active-alerts-table`).
  - Handle user interactions (button clicks, toggles, filters).

### 3.3 What We Avoid

- Avoid building core page structure entirely in JS with massive `document.createElement` trees
  *unless* there is a compelling reason.
- Avoid duplicating complex formatting logic across Python and JS; prefer one “source of truth” per
  concern.

---

## 4. React and Other SPA Frameworks

We **are not currently using React (or another SPA framework)** for the Temperature Bot UI.

### 4.1 How a React Frontend Would Differ

- Most or all Jinja templates would become a thin shell (or a single `index.html`).
- React components would:
  - Own the DOM tree and state management.
  - Consume `/api/v1/...` endpoints for all data.
  - Potentially implement client-side routing.

### 4.2 Why We Are Not Doing That (For Now)

- **Testing and simplicity**:
  - Our current SSR + light JS approach allows HTML‑level tests without a browser.
  - A full SPA would *increase* reliance on a browser engine for correctness tests.
- **Scope and complexity**:
  - Current UIs (dashboards, tables, charts) are complex but manageable with plain JS modules.
  - Introducing React would add bundling, build steps, and more tooling to maintain.
- **Incremental evolution over rewrite**:
  - We prefer iterating on existing templates and JS rather than rewriting the frontend stack.

**If we ever choose React (or similar), it should be a deliberate project decision**, with its own
design doc and migration plan.

---

## 5. Concrete Guidelines for New Work

This section is intended to be **followable by both humans and LLM agents**.

### 5.1 Choosing Where Rendering Lives

When adding or modifying a page:

1. **Ask: “Can this be largely pre-rendered?”**
   - If yes, **do it in Jinja2**:
     - Add/modify a template in `app/templates/`.
     - Pass the needed data from `routes_web.py` via `render_template`.
   - Use JS only for progressive enhancement (sorting, toggles, minor live updates).

2. **If the page needs frequent, live updates or heavy interactivity**:
   - Use Jinja2 for layout and static pieces.
   - Use a JS module under `app/static/` that:
     - Calls `/api/v1/...` for data.
     - Updates only specific parts of the DOM.

3. **Do not introduce a new templating system**:
   - Stick to **Jinja2 via Flask’s `render_template`** for server-side HTML.

### 5.2 Where to Put New Code

- **New web page route**:
  - Add route handler to `app/routes_web.py`.
  - Render a Jinja2 template in `app/templates/`.
  - Include static JS from `app/static/` via `<script src="/static/...">` in the template.

- **New JSON endpoint (AJAX / fetch)**:
  - Add function to `app/routes_api.py`, under the `/api/v1/...` blueprint.
  - Return `jsonify(...)`.
  - Have JS call it via `fetch`, *not* from Jinja.

- **New JS behavior**:
  - Create/extend a module in `app/static/`.
  - Initialize via `DOMContentLoaded` or equivalent, scoped to pages that include that script.

### 5.3 Testing Strategy Expectations

- **Server-rendered behavior**:
  - Prefer tests that:
    - Use the Flask test client.
    - Assert on HTML snippets, response status, and key text/attributes.
  - Example: Smoke tests that confirm the `/air-quality` route returns the right headings and a few
    critical cells.

- **JS-heavy behavior**:
  - Use Playwright / browser helpers where necessary, but:
    - Keep such tests focused on true interaction flows.
    - Do **not** rely on full browser tests for things that could be tested via HTML SSR.

---

## 6. Mapping: Where Each Style Is Used Today

This section is a reference for future contributors and LLM agents.

### 6.1 Mostly Server-Side Rendered (Jinja2)

These pages are primarily rendered on the server; JS is minimal or optional:

- `index.html` (route `/`):
  - Renders device status tables, labels, links.
- `rules.html` (route `/rules`):
  - Rules overview and precomputed HTML rule table (string built in Python).
- `air-quality.html` (route `/air-quality`):
  - Indoor and outdoor AQ tables using `airmon` data; small inline JS for cell colors.
- `device_log.html` (route `/device_log/<device_id>`):
  - Device info, RLE temp log, change log, alerts rendered by Jinja.
- Content pages: `about.html`, `privacy.html`, `terms.html`, parts of `weather.html`, etc.

### 6.2 Hybrid: Jinja2 + JSON + JS

These pages use Jinja2 for the “skeleton” and JS for dynamic content:

- Room dashboards (`/kitchen`, `/hickory`):
  - Template: `room_dashboard.html` (pre-renders tiles, sensor cards).
  - JS: `room_dashboard.js` (fetches `/api/v1/status`, calls `/api/v1/set_*`, updates DOM).
- Charts:
  - `chart.html` (temperature, `/chart`) + `chart_support.js` (ECharts, `/api/v1/temperature`,
    `/api/v1/air_quality`, `/api/v1/status`).
  - `chart_aqi.html` (AQI, `/chart_aqi`) + `chart_aqi_support.js`.
- Logs and alerts:
  - `logs_today.html` + `logs_today.js` (Tabulator, `/api/v1/logs`).
  - `logs.html` + `unit_speed.js` for log table.
  - `alerts.html`:
    - Jinja renders tabs and device filter dropdown.
    - Inline JS sets up Tabulator tables using `/api/v1/alerts/active` and `/api/v1/alerts/history`.
- Debug:
  - `debug_all_devices.html`:
    - Jinja renders sections and `<pre>` areas.
    - Inline JS populates via `/api/v1/debug/db_devices`, `/api/v1/debug/hubitat_devices`,
      `/api/v1/debug/ae200_devices`.

### 6.3 Pure JSON APIs

- `app/routes_api.py` defines the `/api/v1/...` endpoints. They **never render templates**:
  - Status, weather, temperature series, AQI series.
  - Logs and alerts data.
  - Device control (`set_fan_speed`, `set_drive`, `set_temp`, `update_note`).
  - Debug views for DB, Hubitat, and AE‑200.

---

## 7. Legacy Areas and Migration Stance

Some older or more JS-heavy areas **do not fully follow our current “SSR-first, JS-enhanced”
philosophy**:

- **Charting UIs**:
  - `chart.html` / `chart_aqi.html` plus `chart_support.js` / `chart_aqi_support.js` do most of
    their work on the client:
    - Chart configuration, sensor checkbox generation, CSV export, and layout tweaks are highly
      JS-centric.
- **Log and alert tables**:
  - `logs_today.html` + `logs_today.js` and `logs.html` + `unit_speed.js` rely on Tabulator and JSON
    APIs for almost all tabular content and formatting.
  - `alerts.html` uses Jinja for page chrome and the device dropdown, but Tabulator and inline JS
    control most of the UX.
- **Debug views**:
  - `debug_all_devices.html` defers almost all meaningful content to JS that fetches
    `/api/v1/debug/...` and dumps JSON into `<pre>` elements.
- **Older JS modules**:
  - Some scripts in `app/static/` (e.g., parts of `unit_speed.js` and other helpers) build
    substantial DOM structures or couple tightly to specific HTML, instead of treating the Jinja
    template as the primary source of layout truth.

This is **acceptable and expected for now**:

- It is **not** a goal to spend time rewriting these sections solely to match the new philosophy.
- However, when you are **already touching these areas for feature work or refactors**, it is
  desirable to:
  - **Gradually shift more initial structure and “static” content into Jinja2 templates.**
  - **Reduce unnecessary client-side DOM construction** when the same result can be obtained through
    SSR.
  - **Align new or refactored pieces** (routes, templates, JS modules) with the guidelines in
    Sections 2–5.

Think of this as a **“boy scout rule” for rendering**: do not initiate big-bang rewrites, but when
you are already changing a file and it is low-risk to move a small piece toward SSR-first patterns,
doing so is encouraged.

---

## 8. Guidance for LLM Agents

When you (an LLM agent) are asked to modify or add frontend behavior:

1. **Prefer Jinja2 for page structure and initial content.**
2. **Use existing patterns**:
   - For static/mostly-static pages: copy style from `index.html`, `air-quality.html`,
     `device_log.html`.
   - For interactive charts/dashboards: copy style from `chart.html` + `chart_support.js` or
     `room_dashboard.html` + `room_dashboard.js`.
3. **Add server routes in the right place**:
   - HTML pages → `routes_web.py` + Jinja template.
   - JSON data / actions → `routes_api.py` + JS in `app/static/`.
4. **Keep testing in mind**:
   - If a feature can be validated via HTML-only tests, structure it so.
   - Use browser-based tests only where browser-only behavior is essential.
5. **Do not introduce React or alternative template engines** unless explicitly requested in a new
   design/change request.

Following these principles keeps the Temperature Bot frontend:

- Testable without a full browser for most flows.
- Reasonably simple to maintain.
- Flexible enough to support rich dashboards and charts where needed.
