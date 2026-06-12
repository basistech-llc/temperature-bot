# app/

The Flask application is split by integration and route surface:

- `main.py`: Flask application setup, blueprint registration, static serving,
  and HTTP error handling.
- `routes_api.py`: `/api/v1/*` JSON API endpoints.
- `routes_web.py`: server-rendered web pages.
- `db.py`: SQLite access and application-level query helpers.
- `models.py`: Pydantic request and response data contracts.
- `rules_engine.py`: HVAC command logic and rules-disable behavior.
- `hubitat.py`, `ae200.py`, `airthings.py`, `airquality.py`, `weather.py`:
  external integrations.
- `templates/`: Jinja templates.
- `static/`: JavaScript, CSS, images, and vendored browser assets.

Schema changes belong in `etc/flyway/sql/`, not in this directory. Refresh the
generated compatibility schema with `make schema`.
