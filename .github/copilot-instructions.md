# Copilot Instructions for Temperature Bot

## Project Overview

Temperature Bot is a Flask-based web application for monitoring and managing temperature sensors, HVAC systems, and air quality data across multiple locations. It collects data from various sources (Hubitat devices, Airthings sensors, weather services), stores them in a database with run-length encoding, and provides a web interface for visualization and control.

## Technology Stack

- **Python**: 3.12+ (required)
- **Framework**: Flask (web server)
- **Database**: SQLite (dev) / ClickHouse (production)
- **Package Manager**: Poetry 2.1.3
- **Dependencies**: See `pyproject.toml` for complete list
  - `google-api-python-client`, `google-auth` for Google Sheets integration
  - `requests`, `websockets` for API integrations
  - `flask`, `gunicorn` for web serving
  - `clickhouse-connect` for production database
  - `pymodbus` for AE200 device communication

## Project Structure

```
temperature-bot/
├── app/                    # Main application code
│   ├── main.py            # Flask app creation and configuration
│   ├── routes_api.py      # REST API endpoints (/api/v1)
│   ├── routes_web.py      # Web UI routes
│   ├── db.py              # Database access layer
│   ├── rules_engine.py    # HVAC control rules
│   ├── hubitat.py         # Hubitat device integration
│   ├── ae200.py           # AE200 HVAC controller
│   ├── airquality.py      # Air quality data integration
│   ├── weather.py         # Weather service integration
│   ├── templates/         # Jinja2 HTML templates
│   ├── static/            # CSS, JavaScript, images
│   └── utils/             # Utility modules
├── bin/                    # Command-line scripts
│   ├── runner.py          # Main periodic job runner
│   ├── scheduler.py       # Job scheduling
│   └── rules.py           # Rules management CLI
├── tests/                  # Test suite
│   ├── conftest.py        # Pytest fixtures and configuration
│   ├── helpers/           # Test helper modules
│   └── test_*.py          # Test modules
├── etc/                    # Configuration files
│   └── schema.sql         # Database schema
└── lib/                    # External libraries (excluded from linting)
```

## Development Workflow

### Setup

```bash
# Install system dependencies (Ubuntu)
make install-ubuntu

# Install system dependencies (macOS)
make install-macos

# This will:
# 1. Install pipx and poetry
# 2. Configure poetry to use in-project virtualenv
# 3. Run poetry install with dev dependencies
# 4. Install playwright browsers
```

### Running Locally

```bash
# Run development server with local database
make local-dev

# Run periodic jobs manually
make every-minute
make daily
```

### Linting and Type Checking

```bash
# Run all checks (ruff, pylint, djlint, eslint)
make check

# Run individual linters
make pylint      # Python linting (threshold: 9.5/10)
make djlint      # HTML template linting
make eslint      # JavaScript linting
make check-types # Type checking with mypy
```

### Testing

```bash
# Run full test suite with coverage
make test
# or
make pytest

# Tests are in pytest function-style (not class-based)
# Coverage reports generated in htmlcov/
```

### Database

```bash
# Create fresh dev database from schema
make make-dev-db

# Fetch production database to local dev environment
make fetch-dev-db
```

## Coding Standards

### Python Style

- **Python version**: 3.12+ required
- **Formatter**: Ruff (version 0.13.2)
- **Linter**: Pylint (must score ≥9.5/10) + Ruff
- **Type hints**: Encouraged but not strictly enforced (mypy in basic mode)
- **Imports**: Standard library, third-party, then local imports
- **Line length**: Follow existing conventions in files

### Important Conventions

1. **No f-strings in logging**: Use `logger.info("msg %s", var)` instead of `logger.info(f"msg {var}")`
   - Reason: Performance and proper log level filtering
   
2. **Function-style tests only**: Write `def test_*()` functions, NOT test classes
   - No `TestBase` classes or complex test inheritance
   - Use fixtures from `conftest.py`, prefer local in-file fixtures
   
3. **Database connections**: Use context managers and commit explicitly
   - Connections use `sqlite3.Row` factory for dict-like access
   - Enable foreign keys: `conn.execute("PRAGMA foreign_keys = ON;")`

4. **Environment variables**:
   - `PYTEST=1` - Running under pytest
   - `AE200_SIMULATOR=1` - Use simulated AE200 device
   - `TEMPERATURE_BOT_CONFIG` - Path to config YAML
   - `DB_PATH` - Database file path

5. **Error handling**: Log errors with context, use appropriate log levels

### File Organization

- Keep route handlers thin - move business logic to separate modules
- Database queries in `db.py` or `utils/db_utils.py`
- Shared test utilities in `tests/helpers/`
- Configuration in YAML files (see `tests/temperature-bot-config-test.yaml`)

## Testing Practices

### Test Structure

```python
def test_feature_name(fixture_name):
    """Brief description of what is being tested."""
    # Arrange: Set up test data
    
    # Act: Execute the code being tested
    
    # Assert: Verify expectations
    assert expected == actual
```

### Available Fixtures (see `tests/conftest.py`)

- `empty_database_conn` - Empty SQLite database with schema
- `test_database_conn` - Database with schema loaded
- `test_database_conn_with_test_data` - Database with test data
- `client` - Flask test client
- `runner` - Click CLI test runner
- `skip_on_github` - Marker to skip tests in GitHub Actions

### Test Data

- Test configurations in `tests/temperature-bot-config-test.yaml`
- Mock data factories in `tests/helpers/data_factories.py`
- Browser test helpers in `tests/helpers/browser_helpers.py`

### Browser Tests

- Use Playwright for end-to-end tests
- Browsers cached in `.playwright/` directory
- Helper functions in `tests/helpers/browser_helpers.py`

## Common Tasks

### Adding a New Route

1. Add route handler to `routes_api.py` (API) or `routes_web.py` (web UI)
2. Create template in `app/templates/` if needed
3. Add tests in `tests/test_routes.py` or `tests/test_endpoints.py`
4. Update API documentation if adding API endpoint

### Adding Database Functionality

1. Add query/update functions to `app/db.py` or `app/utils/db_utils.py`
2. Update schema in `etc/schema.sql` if changing structure
3. Add tests in `tests/test_db.py`
4. Consider migration path for production database

### Adding a New Device Integration

1. Create module in `app/` (e.g., `app/new_device.py`)
2. Implement data fetching and parsing
3. Add device logging to database via `db.insert_devlog_entry()`
4. Integrate into `bin/runner.py` for periodic updates
5. Add tests with mocked responses

### Modifying Rules Engine

1. Rules logic in `app/rules_engine.py`
2. CLI tool in `bin/rules.py`
3. Test rule behavior in `tests/test_rules_disable.py`
4. Rules can be temporarily disabled (expire after set time)

## Dependencies

### External Services

- **Hubitat Hub**: Home automation device API
- **Airthings**: Air quality sensor API
- **AE200**: HVAC controller (Modbus TCP)
- **AQICN**: Air quality data API
- **AirNow**: EPA air quality API
- **Google Sheets**: Configuration and data export

### Configuration

- Environment variables for secrets (tokens, API keys)
- YAML config file for device mappings and settings
- See `tests/temperature-bot-config-test.yaml` for structure

## CI/CD

- **Workflow**: `.github/workflows/cicd.yml`
- **Platforms**: Ubuntu and macOS
- **Steps**: Install → Lint → Test → Upload coverage
- **Caching**: Poetry venv, Playwright browsers, Ruff cache
- **Coverage**: Uploaded to codecov.io (Linux only)

## Important Notes

- The app uses run-length encoding for temperature storage to save space
- Temperatures stored as `temp10x` (temperature * 10, as integer)
- Database uses foreign keys - must be enabled in SQLite
- AE200 simulator available for testing without hardware
- Playwright browsers in `.playwright/` to avoid system conflicts
- All tests should pass on both macOS and Ubuntu

## Resources

- Main config: `pyproject.toml`
- Test config: `tests/temperature-bot-config-test.yaml`
- Schema: `etc/schema.sql`
- Cursor rules: `.cursorrules` (editor-specific guidelines)
- Make targets: `Makefile` (see `make help` equivalent by reading file)
