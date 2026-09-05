#
# Makefile for temperature bot
#
# install macOS or Linux environments on clean vm:
#    make install-ubuntu | install-macos
#
# Local development:
#    make check   - static analysis
#    make test    - dynamic analysis
#    make make-dev-db  - creates a local database via Flyway migrations
#    make fetch-dev-db - refreshes var/db/temperature_bot from production and migrates it
#    make migrate-db   - applies pending Flyway migrations to the existing local DB
#    make local-dev-sim - Runs the web backend locally with simulator
#    make local-dev-live - Runs the web backend locally against live hardware
#    make local-dev - Alias for local-dev-sim
#    make live-dev-runner - Runs the collection agent and rules runner locally, with live collection
#
# Environment variables:
# DB_PATH - Environment variable to use for local development.
#           Uses var/db/temperature_bot/temperature-bot.db if not set.
#           For installation, cron & systemd use /var/db/temperature_bot/temperature-bot.db
#
# DEV_DB - your development DB. typically var/db/temperature_bot/temperature-bot.db
# AE200_SIMULATOR - set to 1 for `make local-dev` -


export DB_PATH ?= var/db/temperature_bot/temperature-bot.db
export DEV_DB  ?= $(DB_PATH)
DEV_DB_BACKUP_DIR ?= var/db/backups
LOCAL_DATABASE_ROOT := $(abspath $(dir $(DB_PATH)))

# Flyway migration SQL directory
FLYWAY_SQL_DIR := etc/flyway/sql
# Temporary database used when regenerating etc/schema.sql
FLYWAY_SCHEMA_TEMP := /tmp/temperature-bot-schema-temp.db
FLYWAY_SCHEMA_DUMP := /tmp/temperature-bot-schema-temp.sql
# Temporary database used by the read-only migration validation gate.
FLYWAY_VALIDATE_TEMP := /tmp/temperature-bot-flyway-validate.db

# Production snapshot API used by fetch-dev-db. The host is reachable only on
# the company VPN; the endpoint deliberately has no application credentials.
FETCH_HOST   ?= air.basistech.net
FETCH_DB_URL ?= https://$(FETCH_HOST)/api/v1/database-snapshot

# Deployment defaults. Override only when intentionally targeting a different
# checked-out installation or database.
DEPLOY_FLYWAY          ?= Y
DEPLOY_HOSTNAME        ?= slg1
DEPLOY_APP_DIR         ?= /home/air/temperature-bot
DEPLOY_DB              ?= /var/db/temperature_bot/temperature-bot.db
DEPLOY_BACKUP_DIR      ?= /var/db/temperature-bot-backups
DEPLOY_USER            ?= temperature_bot
MONTHLY_BACKUP_RUNNER  ?= sudo -u $(DEPLOY_USER)
STAGE_APP_DIR     ?= /home/air-stage/temperature-bot
STAGE_DB_DIR      ?= /home/air-stage/var/db
STAGE_DB          ?= $(STAGE_DB_DIR)/temperature-bot.db
STAGE_DB_TEMP     ?= $(STAGE_DB).new
STAGE_BACKUP_DIR  ?= $(STAGE_DB_DIR)/backups
STAGE_SERVICE     ?= air-stage_basistech_net.service

REQ := .venv/pyvenv.cfg
PYTHON := .venv/bin/python
TEMPLATE_DIR := app/templates

# Centralize the Playwright cache path so CI can cache it
export PLAYWRIGHT_BROWSERS_PATH := .playwright

# Pin tool versions (helps avoid "invisible" cache invalidations)
UV_VERSION     ?= 0.11.26
RUFF_VERSION   ?= 0.15.15
FLYWAY_VERSION ?= 12.8.1

DEPLOYMENT_BUILD_DIR    := build/deployment-package
DEPLOYMENT_REQUIREMENTS := $(DEPLOYMENT_BUILD_DIR)/runtime.txt
SYSTEMD_SCHEDULED_DIR  := etc/systemd

# Test selection override, e.g.
#   make PYTEST_ARGS=tests/test_db.py::test_name pytest
PYTEST_ARGS ?= .
DEVICE_TYPE_DB ?= $(DEV_DB)
DEVICE_TYPE_BACKUP ?= $(DEVICE_TYPE_DB).pre-device-type-backfill
DEVICE_TYPE_REPORT ?= var/device-type-report.tsv


.PHONY: help
help: ## Show this help message
	@printf "\033[1;34mUsage:\033[0m make [target]\n\n"
	@printf "\033[1;36mTargets:\033[0m\n"
	@# List every command target. A target missing its '## ' doc prints
	@# "(no description)", which makes the omission obvious in this output.
	@awk -F: '/^[a-zA-Z0-9_-]+:/ { \
	    desc = "(no description)"; \
	    if (match($$0, /## /)) { desc = substr($$0, RSTART + 3); } \
	    printf "  \033[1;32m%-20s\033[0m \033[0;37m%s\033[0m\n", $$1, desc; \
	}' $(MAKEFILE_LIST) | sort
	@printf "\n"


################################################################
# Create the virtual environment and install python modules.
.venv/pyvenv.cfg:
	@echo install venv for the development environment
	echo $$PATH
	uv sync --locked

################################################################
# Manage the local development database and configuration file.
#

make-dev-db: ## Create a fresh local dev database from scratch via Flyway migrations
	/bin/rm -f $(DEV_DB)
	mkdir -p $(dir $(DEV_DB))
	flyway migrate \
	    -url="jdbc:sqlite:$(abspath $(DEV_DB))" \
	    -locations="filesystem:$(FLYWAY_SQL_DIR)"
	ls -l $(DEV_DB)

device-type-backfill: $(REQ) ## Infer missing device types; add APPLY=1 to persist
	$(if $(APPLY),cp -f $(DEVICE_TYPE_DB) $(DEVICE_TYPE_BACKUP),@true)
	$(PYTHON) bin/backfill_device_types.py $(DEVICE_TYPE_DB) $(if $(APPLY),--apply,)

device-type-report: $(REQ) ## Write a TSV report containing every device and type
	$(PYTHON) bin/backfill_device_types.py $(DEVICE_TYPE_DB) --all > $(DEVICE_TYPE_REPORT)
	@echo "Wrote $(DEVICE_TYPE_REPORT)"

# Explicit rule for the development database file so that schema generation
# fails with a clear, actionable message when the DB is missing.
$(DEV_DB):
	@echo "ERROR: Development database '$(DEV_DB)' does not exist."
	@echo "       Create it with 'make make-dev-db' or fetch it with 'make fetch-dev-db'."
	@false

# Back up the local database directory, download a consistent production
# snapshot over the VPN, verify its server-provided SHA-256, and apply pending
# Flyway migrations. The API snapshot uses SQLite's backup API so committed WAL
# contents are included without copying live database files or credentials.
fetch-dev-db: SHELL := /bin/bash
fetch-dev-db: $(REQ) ## Fetch and migrate a production DB snapshot over the VPN
	@set -euo pipefail; \
	db='$(DEV_DB)'; \
	db_dir="$$(dirname "$$db")"; \
	case "$$db_dir" in ''|.|/) echo "ERROR: unsafe DEV_DB directory: $$db_dir" >&2; exit 1;; esac; \
	backup_dir=; \
	headers="$$(mktemp)"; \
	cleanup_headers() { /bin/rm -f "$$headers"; }; \
	echo "Preparing to refresh $$db from $(FETCH_DB_URL)"; \
	echo "Ensuring the backup directory exists: $(DEV_DB_BACKUP_DIR)"; \
	mkdir -p '$(DEV_DB_BACKUP_DIR)'; \
	if test -d "$$db_dir"; then \
		backup_dir='$(DEV_DB_BACKUP_DIR)'/"$$(basename "$$db_dir").$$(date -u +%Y%m%dT%H%M%SZ)"; \
		test ! -e "$$backup_dir"; \
		echo "Moving the existing database directory $$db_dir to $$backup_dir"; \
		mv -f "$$db_dir" "$$backup_dir"; \
	else \
		echo "No existing database directory to back up: $$db_dir"; \
	fi; \
	restore() { \
		status=$$?; \
		trap - EXIT; \
		cleanup_headers; \
		echo "Fetch failed; removing the incomplete database directory $$db_dir" >&2; \
		/bin/rm -rf "$$db_dir"; \
		if test -n "$$backup_dir"; then \
			echo "Restoring the previous database directory from $$backup_dir" >&2; \
			mv -f "$$backup_dir" "$$db_dir"; \
		fi; \
		exit $$status; \
	}; \
	trap restore EXIT; \
	echo "Creating the new database directory: $$db_dir"; \
	mkdir -p "$$db_dir"; \
	echo "Downloading a consistent SQLite snapshot"; \
	curl --fail --location --silent --show-error \
		--connect-timeout 10 --max-time 300 \
		--dump-header "$$headers" --output "$$db" '$(FETCH_DB_URL)'; \
	expected="$$(awk 'tolower($$1) == "x-database-sha256:" {print $$2}' "$$headers" \
		| tr -d '\r' | tail -1)"; \
	case "$$expected" in (*[!0-9a-f]*|'') echo "ERROR: snapshot response has no valid SHA-256" >&2; exit 1;; esac; \
	test "$${#expected}" -eq 64; \
	actual="$$(shasum -a 256 "$$db" | awk '{print $$1}')"; \
	test "$$actual" = "$$expected"; \
	cleanup_headers; \
	echo "Checking SQLite integrity"; \
	test "$$(sqlite3 -batch -noheader -init /dev/null -readonly "$$db" 'PRAGMA quick_check;')" = ok; \
	echo "Checking that the imported database contains the devices table"; \
	sqlite3 -batch -init /dev/null -readonly "$$db" 'SELECT count(*) FROM devices;' >/dev/null; \
	echo "Applying pending Flyway migrations"; \
	DEV_DB="$$db" $(MAKE) migrate-db; \
	echo "Files in $$(dirname "$$db"):"; \
	ls -l "$$(dirname "$$db")"; \
	echo "Database row counts:"; \
	sqlite3 "$$db" "select 'devices',count(*) from devices;select 'devlog',count(*) from devlog;select 'changelog',count(*) from changelog;select 'aqi',count(*) from aqi;"; \
	trap - EXIT; \
	test -z "$$backup_dir" || echo "Previous database directory retained at $$backup_dir"; \
	echo "Database refresh and migration completed successfully: $$db"

# Build the etc/schema.sql file by applying all Flyway migrations to a fresh
# temp database and dumping the resulting schema. This keeps schema.sql in sync
# with the canonical migration history. Run 'make schema' to regenerate.
etc/schema.sql: $(wildcard $(FLYWAY_SQL_DIR)/*.sql)
	/bin/rm -f $(FLYWAY_SCHEMA_TEMP) $(FLYWAY_SCHEMA_DUMP)
	flyway migrate \
	    -url="jdbc:sqlite:$(FLYWAY_SCHEMA_TEMP)" \
	    -locations="filesystem:$(FLYWAY_SQL_DIR)"
	sqlite3 $(FLYWAY_SCHEMA_TEMP) \
		"SELECT sql || ';' FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' AND name <> 'flyway_schema_history' AND COALESCE(tbl_name, '') <> 'flyway_schema_history' ORDER BY rowid;" \
		> $(FLYWAY_SCHEMA_DUMP)
	test -s $(FLYWAY_SCHEMA_DUMP)
	sed 's/CREATE UNIQUE INDEX/CREATE UNIQUE INDEX IF NOT EXISTS/' $(FLYWAY_SCHEMA_DUMP) \
		| sed 's/CREATE INDEX/CREATE INDEX IF NOT EXISTS/' \
		| sed 's/CREATE TABLE/CREATE TABLE IF NOT EXISTS/' \
		> etc/schema.sql
	test -s etc/schema.sql
	/bin/rm -f $(FLYWAY_SCHEMA_TEMP) $(FLYWAY_SCHEMA_DUMP)

schema: ## Regenerate etc/schema.sql from the Flyway migration history
	$(MAKE) --always-make etc/schema.sql

# doc/site-manual.md is the source of truth; the .docx is generated from it.
# Run this after editing the manual so the two do not drift apart.
site-manual-docx: $(REQ) ## Regenerate doc/site-manual.docx from doc/site-manual.md
	$(PYTHON) bin/render_site_manual.py

# Apply pending Flyway migrations to the existing dev database.
# Uses -baselineOnMigrate=true so databases already at V1 (but without a
# flyway_schema_history entry) are baselined automatically before migrating.
migrate-db: $(DEV_DB) ## Apply pending Flyway migrations to the dev DB
	flyway migrate \
	    -url="jdbc:sqlite:$(abspath $(DEV_DB))" \
	    -locations="filesystem:$(FLYWAY_SQL_DIR)" \
	    -baselineOnMigrate=true

# Validate that all Flyway migrations apply cleanly from scratch.
# Runs entirely against a temporary /tmp database, so it is safe for CI and
# local use and never touches your real dev database.
validate-migrations: ## Validate that all migrations apply from scratch
	@set -eu; \
	/bin/rm -f "$(FLYWAY_VALIDATE_TEMP)"; \
	trap '/bin/rm -f "$(FLYWAY_VALIDATE_TEMP)"' EXIT; \
	flyway migrate \
	    -url="jdbc:sqlite:$(FLYWAY_VALIDATE_TEMP)" \
	    -locations="filesystem:$(FLYWAY_SQL_DIR)"; \
	flyway validate \
	    -url="jdbc:sqlite:$(FLYWAY_VALIDATE_TEMP)" \
	    -locations="filesystem:$(FLYWAY_SQL_DIR)"

.PHONY: make-dev-db fetch-dev-db schema migrate-db validate-migrations

################################################################
## Local development targets. These use the flask built-in web server,
## which automatically does a live reload when any files are changed.
## NOTE: It does not do JavaScript live reload; you need to use node for that
##       or just hit shift-reload on the web browser

local-dev-sim: $(REQ) ## Run the web backend locally with simulated hardware data
	@echo Running with simulator
	TEMPERATURE_BOT_INSTANCE=local-dev-sim \
	TEMPERATURE_BOT_DATABASE_IDENTITY=local-dev-sim \
	TEMPERATURE_BOT_DATABASE_ROOT="$(LOCAL_DATABASE_ROOT)" \
	TEMPERATURE_BOT_CONFIG="$(abspath tests/temperature-bot-config-test.yaml)" \
	TEMPERATURE_BOT_CONTROL_MODE=simulator TEMPERATURE_BOT_SCHEDULER_MODE=disabled \
	AE200_SIMULATOR=1 HUBITAT_SIMULATOR=1 AIRTHINGS_SIMULATOR=1 AQICN_SIMULATOR=1 \
	$(MAKE) _local-dev-web

local-dev: local-dev-sim ## Alias for local-dev-sim

rooms-ui-demo: $(REQ) ## Run the room matrix against disposable synthetic data
	$(PYTHON) -m bin.rooms_ui_demo --database /tmp/temperature-bot-rooms-ui-demo.db

local-dev-live: $(REQ) ## Run the web backend locally against live hardware
	@echo updating database
	TEMPERATURE_BOT_INSTANCE=local-dev-live \
	TEMPERATURE_BOT_DATABASE_IDENTITY=local-dev-live \
	TEMPERATURE_BOT_DATABASE_ROOT="$(LOCAL_DATABASE_ROOT)" \
	TEMPERATURE_BOT_CONTROL_MODE=live TEMPERATURE_BOT_SCHEDULER_MODE=disabled \
	AE200_SIMULATOR= HUBITAT_SIMULATOR= AIRTHINGS_SIMULATOR= AQICN_SIMULATOR= \
	$(MAKE) every-minute
	@echo Running without simulator
	TEMPERATURE_BOT_INSTANCE=local-dev-live \
	TEMPERATURE_BOT_DATABASE_IDENTITY=local-dev-live \
	TEMPERATURE_BOT_DATABASE_ROOT="$(LOCAL_DATABASE_ROOT)" \
	TEMPERATURE_BOT_CONTROL_MODE=live TEMPERATURE_BOT_SCHEDULER_MODE=disabled \
	AE200_SIMULATOR= HUBITAT_SIMULATOR= AIRTHINGS_SIMULATOR= AQICN_SIMULATOR= \
	$(MAKE) _local-dev-web

local-live-dev: local-dev-live ## Compatibility alias for local-dev-live

_local-dev-web: $(REQ) ## Internal: shared web backend runner for local-dev targets
	FLASK_DEBUG=True uv run --locked flask --app app.main:app run --port 8000

live-dev-runner: $(REQ) ## Run the collection agent and rules runner against live hardware
	LOG_LEVEL=DEBUG $(PYTHON) bin/runner.py

tags: ## Build an etags TAGS file for all Python sources
	etags */*.py

.PHONY: local-dev local-dev-sim local-dev-live local-live-dev rooms-ui-demo _local-dev-web live-dev-runner tags
################################################################
## Analysis tools
## Static Analysis
PYLINT_THRESHOLD := 10.0
PYLINT_OPTS :=--output-format=parseable --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose

lint: check ## Run all static analysis checks (alias for check)
check: $(REQ) dependency-check ## Run all static analysis checks
	$(MAKE) ruff-check
	$(MAKE) no-type-ignore
	$(MAKE) pylint-check
	$(MAKE) djlint
	$(MAKE) eslint
	$(MAKE) check-types
	$(MAKE) release-code-check
	$(MAKE) validate-migrations

release-code-check: $(REQ) ## Check release publication and updater code
	uv run --locked ruff check \
		bin/build_deployment_package.py bin/github_release_update.py \
		bin/install_deployment_package.py bin/source_deployment.py \
		bin/release_tag.py tests/test_release_update.py
	$(PYTHON) -m pylint --persistent=n --output-format=parseable \
		--rcfile .pylintrc --fail-under=10.0 \
		bin/build_deployment_package.py bin/github_release_update.py \
		bin/install_deployment_package.py bin/source_deployment.py \
		bin/release_tag.py tests/test_release_update.py
	uv run --locked mypy \
		bin/build_deployment_package.py bin/github_release_update.py \
		bin/install_deployment_package.py bin/source_deployment.py \
		bin/release_tag.py

dependency-check: ## Verify the uv lockfile and reject legacy dependency tooling
	uv lock --check
	@! git grep -n -i 'poe''try' -- ':!.beads/**' ':!doc/RELEASE_NOTES.md'

build: dependency-check ## Build the source distribution and wheel
	uv build --no-sources

build-check: dependency-check ## Build/install only one wheel in a clean environment
	@build_tmp="$$(mktemp -d)"; \
	trap 'rm -rf "$$build_tmp"' EXIT; \
	uv build --no-sources --out-dir "$$build_tmp/dist"; \
	uv venv --python 3.12 "$$build_tmp/venv"; \
	uv pip install --python "$$build_tmp/venv/bin/python" "$$build_tmp"/dist/*.whl; \
	cd "$$build_tmp"; \
	DB_PATH="$$build_tmp/temperature-bot.db" \
	TEMPERATURE_BOT_INSTANCE=slg1 \
	TEMPERATURE_BOT_DATABASE_ROOT="$$build_tmp" \
	TEMPERATURE_BOT_CONFIG="$(abspath tests/temperature-bot-config-test.yaml)" \
	AE200_SIMULATOR=1 HUBITAT_SIMULATOR=1 AIRTHINGS_SIMULATOR=1 AQICN_SIMULATOR=1 \
	"$$build_tmp/venv/bin/python" -c 'from wsgi import app; assert app.name == "app.main"'

$(DEPLOYMENT_REQUIREMENTS): uv.lock pyproject.toml | $(REQ)
	mkdir -p $(DEPLOYMENT_BUILD_DIR)
	uv export --quiet --locked --no-dev --no-editable --no-emit-project \
	    --output-file $(DEPLOYMENT_REQUIREMENTS)

deployment-package: build $(DEPLOYMENT_REQUIREMENTS) ## Build the deployment ZIP and SHA-256 sidecar
	$(PYTHON) -m bin.build_deployment_package \
	    --requirements $(DEPLOYMENT_REQUIREMENTS) \
	    --output-dir dist \
	    --flyway-version $(FLYWAY_VERSION)

deployment-package-verify: deployment-package ## Verify the deployment ZIP inventory and hashes
	@package="$$(ls -1t dist/temperature-bot-deployment-*.zip | head -1)"; \
	$(PYTHON) -m bin.install_deployment_package \
	    "$$package" --require-checksum --verify-only >/dev/null; \
	echo "Verified $$package"

deployment-package-check: deployment-package ## Install the package into a disposable immutable root
	@set -eu; \
	package="$$(ls -1t dist/temperature-bot-deployment-*.zip | head -1)"; \
	install_tmp="$$(mktemp -d)"; \
	trap 'rm -rf "$$install_tmp"' EXIT; \
	$(PYTHON) -m bin.install_deployment_package \
	    "$$package" --require-checksum \
	    --root "$$install_tmp/opt/temperature-bot" \
	    --activate >/dev/null; \
	test -L "$$install_tmp/opt/temperature-bot/current"; \
	test -x "$$install_tmp/opt/temperature-bot/current/venv/bin/python"; \
	echo "Verifying installed runner imports outside the source checkout"; \
	DB_PATH="$$install_tmp/opt/temperature-bot/temperature-bot.db" \
	TEMPERATURE_BOT_INSTANCE=slg1 \
	TEMPERATURE_BOT_DATABASE_ROOT="$$install_tmp/opt/temperature-bot" \
	TEMPERATURE_BOT_CONFIG="$(abspath tests/temperature-bot-config-test.yaml)" \
	AE200_SIMULATOR=1 HUBITAT_SIMULATOR=1 AIRTHINGS_SIMULATOR=1 AQICN_SIMULATOR=1 \
	"$$install_tmp/opt/temperature-bot/current/venv/bin/python" -I -c \
	    'import bin.runner; import app.clogging'; \
	echo "Executing the relocated Gunicorn console script"; \
	"$$install_tmp/opt/temperature-bot/current/venv/bin/gunicorn" --version; \
	test -f "$$install_tmp/opt/temperature-bot/current/systemd/temperature-bot-minute.timer"; \
	test -f "$$install_tmp/opt/temperature-bot/current/configuration/slg1_basistech_net.socket"; \
	test -f "$$install_tmp/opt/temperature-bot/current/configuration/deg1_basistech_net.socket"; \
	test ! -e "$$install_tmp/etc"; \
	echo "Installed and activated $$package in a disposable root"

release-tag-check: $(REQ) ## Verify the current tag matches the canonical project version
	$(PYTHON) -m bin.release_tag \
		$(if $(GITHUB_OUTPUT),--github-output $(GITHUB_OUTPUT),)

systemd-verify: ## Validate packaged scheduled-job units on Linux
	@command -v systemd-analyze >/dev/null || \
	    { echo "systemd-analyze is required for systemd-verify"; exit 1; }
	systemd-analyze verify \
	    $(wildcard $(SYSTEMD_SCHEDULED_DIR)/*.service) \
	    $(wildcard $(SYSTEMD_SCHEDULED_DIR)/*.socket) \
	    $(wildcard $(SYSTEMD_SCHEDULED_DIR)/*.timer)
	@if command -v rg >/dev/null; then \
		! rg -n 'User=(simsong|deg|root)|Group=(simsong|deg|root)|/home/' \
		    $(SYSTEMD_SCHEDULED_DIR)/temperature-bot-minute.service \
		    $(SYSTEMD_SCHEDULED_DIR)/temperature-bot-hourly.service \
		    $(SYSTEMD_SCHEDULED_DIR)/temperature-bot-daily.service; \
	else \
		! grep -ERn 'User=(simsong|deg|root)|Group=(simsong|deg|root)|/home/' \
		    $(SYSTEMD_SCHEDULED_DIR)/temperature-bot-minute.service \
		    $(SYSTEMD_SCHEDULED_DIR)/temperature-bot-hourly.service \
		    $(SYSTEMD_SCHEDULED_DIR)/temperature-bot-daily.service; \
	fi

format: $(REQ) ## Auto-fix Python style issues with ruff
	uv run --locked ruff check --fix app | etc/ruff-reformat.bash

pylint: ruff-check pylint-check ## Run ruff and pylint checks

ruff-check: $(REQ) ## Run the ruff linter on app/
	uv run --locked ruff check app

no-type-ignore: ## Fail if any type-ignore comments exist in source
	@command -v rg >/dev/null || { echo "Error: ripgrep is required for no-type-ignore"; exit 1; }
	@! rg -n 'type:\s*ignore|type:ignore' app bin tests *.py

pylint-check: $(REQ) ## Run pylint on app, tests, and top-level modules
	$(PYTHON) -m pylint $(PYLINT_OPTS) app tests *.py

djlint: $(REQ) ## Lint Jinja2 HTML templates with djlint
	uv run --locked djlint $(DJLINT_FLAGS) $(TEMPLATE_DIR)/*.html

eslint: $(REQ) ## Run ESLint on frontend JavaScript
	(cd app/static; make eslint)

check-types: $(REQ) ## Run mypy type checking on app/
	uv run --locked mypy app

## Dynamic Analysis
pytest: $(REQ) ## Run the Python test suite with coverage
	make pylint
	$(PYTHON) -m pytest $(PYTEST_ARGS) -v --cov=. --cov-report=xml --cov-report=html --log-cli-level=WARNING --log-file-level=DEBUG
	@echo coverage report in htmlcov/
test-js: $(REQ) ## Run the JavaScript unit tests
	@echo "Running JavaScript unit tests..."
	node tests/test_time_utils.js
	node tests/test_time_series_chart_core.js
	node tests/test_temperature_utils.js
	node tests/test_air_quality_thresholds.js
	node tests/test_unit_speed.js
	node tests/test_metric_chart_support.js
	node tests/test_chart_aqi_support.js
	node tests/test_room_scale.js
	node tests/test_hickory_life.js
	node tests/test_room_matrix.js
	node tests/test_room_map.js
	node tests/test_fcu_history_chart.js
	node tests/test_performance_monitoring.js
	node tests/test_outdoor_aqi.js
	node tests/test_ae200_page.js
	node tests/test_logs_today.js
test: $(REQ) ## Run both Python and JavaScript test suites
	@python_exit=0; js_exit=0; \
	make pytest || python_exit=$$?; \
	make test-js || js_exit=$$?; \
	exit $$(($$python_exit + $$js_exit))

playwright-install: $(REQ) ## Install the Playwright Chromium browser
	uv run --locked playwright install --with-deps chromium

web-screenshots: $(REQ) playwright-install ## Render screenshots of web UI pages
	$(PYTHON) bin/render_web_ui_pages.py

outdated: $(REQ) ## Report outdated Python and CDN dependencies
	uv lock --check
	uv sync --locked
	@echo "=== Python ==="
	uv tree --outdated --depth 1 || true
	@echo ""
	@echo "=== CDN libraries (in templates) ==="
	bash etc/check-cdn-versions.bash

.PHONY: lint check release-code-check dependency-check build build-check deployment-package deployment-package-verify deployment-package-check release-tag-check systemd-verify format pylint ruff-check no-type-ignore pylint-check djlint eslint check-types pytest test-js test playwright-install web-screenshots outdated

################################################################
## Scheduled runner targets
## Production uses the checked-in systemd oneshot services and timers described
## in doc/systemd-scheduled-jobs.md. These targets remain useful for manual runs.

every-minute: $(REQ) ## Run the per-minute data collection runner
	PERFORMANCE_CLIENT_ID=minute-runner $(PYTHON) -m bin.runner

hourly: $(REQ) ## Run the hourly AQI collection runner
	PERFORMANCE_CLIENT_ID=hourly-runner $(PYTHON) -m bin.runner --aqi

performance-probe: $(REQ) ## Record one AE-200 DNS, ICMP, and TCP-reject probe
	PERFORMANCE_CLIENT_ID=network-probe $(PYTHON) -m bin.performance_monitor --once

daily: $(REQ) ## Run the daily data collection runner
	PERFORMANCE_CLIENT_ID=daily-runner $(PYTHON) -m bin.runner --daily

monthly-backup: ## Back up the production database with a dated copy
	@set -eu; \
	umask 077; \
	backup="$(DEPLOY_BACKUP_DIR)/temperature-bot.$$(date -u +%Y%m%dT%H%M%SZ).db"; \
	$(MONTHLY_BACKUP_RUNNER) sqlite3 -batch -init /dev/null -cmd ".timeout 30000" \
	    "$(DEPLOY_DB)" "VACUUM INTO '$$backup';"; \
	test "$$($(MONTHLY_BACKUP_RUNNER) sqlite3 -batch -noheader -init /dev/null -readonly "$$backup" \
	    "PRAGMA quick_check;")" = ok; \
	echo "Created $$backup"

.PHONY: every-minute hourly performance-probe daily monthly-backup

################################################################
## Installation targets

install-either: ## Shared install steps for macOS and Ubuntu
	pipx ensurepath
	@if ! command -v uv >/dev/null 2>&1 || [ "$$(uv --version | awk '{print $$2}')" != "$(UV_VERSION)" ]; then \
		pipx install --force uv==$(UV_VERSION); \
	fi
	uv sync --locked
	uv run --locked playwright install --with-deps # This will be fast if CI restored .playwright

install-ubuntu: ## Install the development environment on Ubuntu
	sudo apt-get install -y python3-pip pipx ripgrep
	make install-either

install-macos: ## Install the development environment on macOS
	@echo Use pipx for the pinned uv version
	@if ! command -v brew >/dev/null 2>&1; then \
		echo "Error: Homebrew is not installed. Please install Homebrew from https://brew.sh/ and try again."; \
		exit 1; \
	fi
	HOMEBREW_NO_AUTO_UPDATE=1 brew install pipx ripgrep
	make install-either

clean: ## Remove generated files and the virtual environment
	@echo "Cleaning up generated files and virtual environment..."
	rm -rf .venv
	rm -rf .playwright
	rm -rf htmlcov
	rm -rf dist
	rm -rf build
	rm -rf var/web-ui-screenshots
	rm -f coverage.xml
	rm -f .coverage
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name "*.pyo" -delete 2>/dev/null || true
	rm -f TAGS
	rm -f debug_page_20*
	@echo "Clean complete."

# Clean aggressively, including the local database.
# [TODO] Should this also clear the private data in temperature-bot-config.yaml?
cleanall: clean ## Clean aggressively, including the local DB
	@echo "Doing aggressive cleanup. This will delete the local database!"
	@printf "Are you sure you want to delete $(DEV_DB)? [y/N] "
	@read -r confirm && [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ] && rm -f $(DEV_DB) || echo "Cancelled."

## Installs the latest source code into the live system and applies any pending
## database migrations. Run on the server (slg1.basistech.net).
deploy: ## Deploy latest code and run DB migrations on the production server
	if [ "$$(hostname)" = "$(DEPLOY_HOSTNAME)" ]; then \
		cd $(DEPLOY_APP_DIR) && \
		git pull --ff-only && \
		uv sync --locked --no-dev && \
		if [ "$(DEPLOY_FLYWAY)" = Y ]; then $(MAKE) deploy-flyway ; fi; \
	else \
		echo "Deploy refused: not running on $(DEPLOY_HOSTNAME) (current hostname: $$(hostname))"; \
		exit 1; \
	fi


deploy-flyway: ## Back up, migrate, and validate the deployment database
	flyway validate -url="jdbc:sqlite:$(DEPLOY_DB)" -locations="filesystem:$(FLYWAY_SQL_DIR)" -ignoreMigrationPatterns="*:pending"
	/bin/mkdir -p $(DEPLOY_BACKUP_DIR)
	@set -eu; \
	umask 077; \
	backup="$(DEPLOY_BACKUP_DIR)/temperature-bot.$$(date -u +%Y%m%dT%H%M%SZ).db"; \
	sqlite3 -batch -init /dev/null -cmd ".timeout 30000" \
	    "$(DEPLOY_DB)" "VACUUM INTO '$$backup';"; \
	test "$$(sqlite3 -batch -noheader -init /dev/null -readonly "$$backup" \
	    "PRAGMA quick_check;")" = ok; \
	echo "Created $$backup"
	flyway migrate -url="jdbc:sqlite:$(DEPLOY_DB)" -locations="filesystem:$(FLYWAY_SQL_DIR)" -baselineOnMigrate=true
	flyway validate -url="jdbc:sqlite:$(DEPLOY_DB)" -locations="filesystem:$(FLYWAY_SQL_DIR)"


deploy-stage: ## Refresh the staging database, deploy dev-stage, and restart staging
	DEPLOY_APP_DIR=$(STAGE_APP_DIR) DEPLOY_FLYWAY=N $(MAKE) deploy
	/bin/mkdir -p $(STAGE_DB_DIR) $(STAGE_BACKUP_DIR)
	/bin/rm -f $(STAGE_DB_TEMP)
	sqlite3 $(DEPLOY_DB) ".backup '$(STAGE_DB_TEMP)'"
	$(MAKE) -C $(STAGE_APP_DIR) DEPLOY_DB=$(STAGE_DB_TEMP) DEPLOY_BACKUP_DIR=$(STAGE_BACKUP_DIR) deploy-flyway
	@if sudo systemctl is-active --quiet $(STAGE_SERVICE); then sudo systemctl stop $(STAGE_SERVICE); fi
	/bin/rm -f $(STAGE_DB)-wal $(STAGE_DB)-shm
	/bin/mv -f $(STAGE_DB_TEMP) $(STAGE_DB)
	sudo systemctl restart $(STAGE_SERVICE)

.PHONY: install-either install-ubuntu install-macos clean cleanall deploy deploy-flyway deploy-stage
