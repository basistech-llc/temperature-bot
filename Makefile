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
#    make migrate-db   - applies pending Flyway migrations to the existing local DB
#    make local-dev - Runs the web backend locally with simulator
#    make local-live-dev - Runs the web backend locally against live AE-200
#    make live-dev-runner - Runs the collection agent and rules runner locally, with live collection
#
# Environment variables:
# DB_PATH - Environment variable to use for local development.
#           Uses var/db/temperature-bot.db if not set (note this is a relative path)
#           For installation, cron & systemd use /var/db/temperature-bot.db
#
# DEV_DB - your development DB. typically var/db/temperature-bot
# AE200_SIMULATOR - set to 1 for `make local-dev` -


export DB_PATH ?= var/db/temperature-bot.db
export DEV_DB  ?= var/db/temperature-bot.db

# Flyway migration SQL directory
FLYWAY_SQL_DIR := etc/flyway/sql
# Temporary database used when regenerating etc/schema.sql
FLYWAY_SCHEMA_TEMP := /tmp/temperature-bot-schema-temp.db
FLYWAY_SCHEMA_DUMP := /tmp/temperature-bot-schema-temp.sql
# Temporary database used by the read-only migration validation gate.
FLYWAY_VALIDATE_TEMP := /tmp/temperature-bot-flyway-validate.db

# Remote host and paths used by fetch-dev-db (override as needed for your environment)
FETCH_HOST           ?= air.basistech.net
FETCH_REMOTE_DB_DIR  ?= /var/db/
FETCH_REMOTE_CONFIG  ?= /home/air/temperature-bot/temperature-bot-config.yaml

# Deployment defaults. Override only when intentionally targeting a different
# checked-out installation or database.
DEPLOY_FLYWAY    ?= Y
DEPLOY_HOSTNAME   ?= slg1
DEPLOY_APP_DIR    ?= /home/air/temperature-bot
DEPLOY_DB         ?= /var/db/temperature-bot.db
DEPLOY_BACKUP_DIR ?= /var/db/temperature-bot-backups
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
POETRY_VERSION ?= 2.1.3
RUFF_VERSION   ?= 0.15.15

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
	poetry install

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

# Fetch the dev database and config from the remote host, then print a
# summary of the database contents.
# NOTE: temperature-bot-config.yaml includes production secrets
#       until we move to better secret management system
fetch-dev-db: ## Fetch the dev DB and config from the remote host
	mkdir -p $(dir $(DEV_DB))
	rsync --verbose --delete --archive $(FETCH_HOST):$(FETCH_REMOTE_DB_DIR) $(dir $(DEV_DB))
	rsync --verbose $(FETCH_HOST):$(FETCH_REMOTE_CONFIG) ./temperature-bot-config.yaml
	@ls -l $(dir $(DEV_DB))
	@echo database contents:
	echo 'select "devices",count(*) from devices;select "devlog",count(*) from devlog;select "changelog",count(*) from changelog; select "aqi",count(*) from aqi;' | sqlite3 $(DEV_DB)

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

local-dev: $(REQ) ## Run the web backend locally with simulated hardware data
	@echo Running with simulator
	export AE200_SIMULATOR=1 HUBITAT_SIMULATOR=1 AIRTHINGS_SIMULATOR=1 && $(MAKE) _local-dev-web

rooms-ui-demo: $(REQ) ## Run the room matrix against disposable synthetic data
	$(PYTHON) -m bin.rooms_ui_demo --database /tmp/temperature-bot-rooms-ui-demo.db

local-live-dev: $(REQ) ## Run the web backend locally against live AE-200 hardware
	@echo updating database
	AE200_SIMULATOR= HUBITAT_SIMULATOR= AIRTHINGS_SIMULATOR= $(MAKE) every-minute
	@echo Running without simulator
	AE200_SIMULATOR= HUBITAT_SIMULATOR= AIRTHINGS_SIMULATOR= $(MAKE) _local-dev-web

_local-dev-web: $(REQ) ## Internal: shared web backend runner for local-dev targets
	FLASK_DEBUG=True poetry run flask --app app.main:app run --port 8000

live-dev-runner: $(REQ) ## Run the collection agent and rules runner against live hardware
	LOG_LEVEL=DEBUG $(PYTHON) bin/runner.py

tags: ## Build an etags TAGS file for all Python sources
	etags */*.py

.PHONY: local-dev rooms-ui-demo local-live-dev _local-dev-web live-dev-runner tags
################################################################
## Analysis tools
## Static Analysis
PYLINT_THRESHOLD := 10.0
PYLINT_OPTS :=--output-format=parseable --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose

lint: check ## Run all static analysis checks (alias for check)
check: $(REQ) ## Run all static analysis checks
	$(MAKE) ruff-check
	$(MAKE) no-type-ignore
	$(MAKE) pylint-check
	$(MAKE) djlint
	$(MAKE) eslint
	$(MAKE) check-types
	$(MAKE) validate-migrations

format: $(REQ) ## Auto-fix Python style issues with ruff
	poetry run ruff check --fix app | etc/ruff-reformat.bash

pylint: ruff-check pylint-check ## Run ruff and pylint checks

ruff-check: $(REQ) ## Run the ruff linter on app/
	poetry run ruff check app

no-type-ignore: ## Fail if any type-ignore comments exist in source
	@! rg -n 'type:\s*ignore|type:ignore' app bin tests *.py

pylint-check: $(REQ) ## Run pylint on app, tests, and top-level modules
	$(PYTHON) -m pylint $(PYLINT_OPTS) app tests *.py

djlint: $(REQ) ## Lint Jinja2 HTML templates with djlint
	poetry run djlint $(DJLINT_FLAGS) $(TEMPLATE_DIR)/*.html

eslint: $(REQ) ## Run ESLint on frontend JavaScript
	(cd app/static; make eslint)

check-types: $(REQ) ## Run mypy type checking on app/
	poetry run mypy app

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
	poetry run playwright install --with-deps chromium

web-screenshots: $(REQ) playwright-install ## Render screenshots of web UI pages
	$(PYTHON) bin/render_web_ui_pages.py

outdated: $(REQ) ## Report outdated Python and CDN dependencies
	poetry lock
	poetry install
	@echo "=== Python ==="
	poetry show --outdated --top-level || true
	@echo ""
	@echo "=== CDN libraries (in templates) ==="
	bash etc/check-cdn-versions.bash

.PHONY: lint check format pylint ruff-check no-type-ignore pylint-check djlint eslint check-types pytest test-js test playwright-install web-screenshots outdated

################################################################
## Cron targets
## Here mostly for testing. The actual cron entries are:
##
##  * * * * * cd /home/air/temperature-bot ; DB_PATH=/var/db/temperature-bot.db TEMPERATURE_BOT_INSTANCE=production PERFORMANCE_CLIENT_ID=minute-runner .venv/bin/python -m bin.runner --loglevel INFO >> /home/air/temperature-bot.log 2>&1
##
##
## @daily    cd /home/air/temperature-bot ; sleep 15 ; DB_PATH=/var/db/temperature-bot.db .venv/bin/python -m bin.runner --loglevel INFO --daily  >> /home/air/temperature-bot-daily.log 2>&1
## @hourly   cd /home/air/temperature-bot ; sleep 30 ; DB_PATH=/var/db/temperature-bot.db .venv/bin/python -m bin.runner --loglevel INFO --aqi    >> /home/air/temperature-bot-hourly.log 2>&1
##
## Question - should we just have cron do a 'make daily' and 'make every-minute' ?

every-minute: $(REQ) ## Run the per-minute data collection runner
	PERFORMANCE_CLIENT_ID=minute-runner $(PYTHON) -m bin.runner

performance-probe: $(REQ) ## Record one AE-200 DNS, ICMP, and TCP-reject probe
	PERFORMANCE_CLIENT_ID=network-probe $(PYTHON) -m bin.performance_monitor --once

daily: $(REQ) ## Run the daily data collection runner
	$(PYTHON) -m bin.runner --daily

monthly-backup: ## Back up the production database with a dated copy
	sudo cp /var/db/temperature-bot.db /var/db/temperature-bot.backup.$$(date -I).db

.PHONY: every-minute performance-probe daily monthly-backup

################################################################
## Installation targets

install-either: ## Shared install steps for macOS and Ubuntu
	pipx ensurepath
	pipx install poetry==$(POETRY_VERSION)
	poetry config virtualenvs.in-project true
	poetry lock
	poetry install --with dev
	poetry run playwright install --with-deps # This will be fast if CI restored .playwright

install-ubuntu: ## Install the development environment on Ubuntu
	sudo apt install python3-pip pipx
	make install-either

install-macos: ## Install the development environment on macOS
	@echo Use pipx for the latest poetry
	@if ! command -v brew >/dev/null 2>&1; then \
		echo "Error: Homebrew is not installed. Please install Homebrew from https://brew.sh/ and try again."; \
		exit 1; \
	fi
	brew install pipx
	make install-either

clean: ## Remove generated files and the virtual environment
	@echo "Cleaning up generated files and virtual environment..."
	rm -rf .venv
	rm -rf .playwright
	rm -rf htmlcov
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
		poetry install && \
		if [ "$(DEPLOY_FLYWAY)" = Y ]; then $(MAKE) deploy-flyway ; fi; \
	else \
		echo "Deploy refused: not running on $(DEPLOY_HOSTNAME) (current hostname: $$(hostname))"; \
		exit 1; \
	fi


deploy-flyway: ## Back up, migrate, and validate the deployment database
	flyway validate -url="jdbc:sqlite:$(DEPLOY_DB)" -locations="filesystem:$(FLYWAY_SQL_DIR)" -ignoreMigrationPatterns="*:pending"
	/bin/mkdir -p $(DEPLOY_BACKUP_DIR)
	/bin/cp -f $(DEPLOY_DB) $(DEPLOY_BACKUP_DIR)/temperature-bot.$$(date -u +%Y%m%dT%H%M%SZ).db
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
