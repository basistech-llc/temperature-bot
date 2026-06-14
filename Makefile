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

# Production deploy defaults. Override only when intentionally targeting a
# different checked-out installation or database.
PROD_HOSTNAME   ?= slg1
PROD_APP_DIR    ?= /home/air/temperature-bot
PROD_DB         ?= /var/db/temperature-bot.db
PROD_BACKUP_DIR ?= /var/db/temperature-bot-backups

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



################################################################
# Create the virtual environment and install python modules.
.venv/pyvenv.cfg:
	@echo install venv for the development environment
	echo $$PATH
	poetry install

################################################################
# Manage the local development database and configuration file.
#

# make a clean local development database from scratch, using Flyway migrations
make-dev-db:
	/bin/rm -f $(DEV_DB)
	mkdir -p $(dir $(DEV_DB))
	flyway migrate \
	    -url="jdbc:sqlite:$(abspath $(DEV_DB))" \
	    -locations="filesystem:$(FLYWAY_SQL_DIR)"
	ls -l $(DEV_DB)

# Explicit rule for the development database file so that schema generation
# fails with a clear, actionable message when the DB is missing.
$(DEV_DB):
	@echo "ERROR: Development database '$(DEV_DB)' does not exist."
	@echo "       Create it with 'make make-dev-db' or fetch it with 'make fetch-dev-db'."
	@false

# fetch the local development database and configuration file.
# Then give the user a status report of what is in the database.
# NOTE: temperature-bot-config.yaml includes production secrets
#       until we move to better secret management system
fetch-dev-db:
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
	sed 's/CREATE INDEX/CREATE INDEX IF NOT EXISTS/' $(FLYWAY_SCHEMA_DUMP) \
		| sed 's/CREATE TABLE/CREATE TABLE IF NOT EXISTS/' \
		> etc/schema.sql
	test -s etc/schema.sql
	/bin/rm -f $(FLYWAY_SCHEMA_TEMP) $(FLYWAY_SCHEMA_DUMP)

# Phony target to force regeneration of etc/schema.sql regardless of timestamps
schema:
	$(MAKE) --always-make etc/schema.sql

# Apply any pending Flyway migrations to the existing development database.
# Uses -baselineOnMigrate=true so databases already at V1 (but without a
# flyway_schema_history entry) are baselined automatically before migrating.
migrate-db: $(DEV_DB)
	flyway migrate \
	    -url="jdbc:sqlite:$(abspath $(DEV_DB))" \
	    -locations="filesystem:$(FLYWAY_SQL_DIR)" \
	    -baselineOnMigrate=true

# Validate that all versioned migrations apply cleanly from scratch and that
# Flyway accepts the resulting schema history. This is safe for CI and local
# checks because it uses only a temporary database under /tmp.
validate-migrations:
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

# Run web backend locally, with simulated data. (needs popuplated db too)
local-dev: $(REQ)
	export AE200_SIMULATOR=1 && $(MAKE) live-dev-web

# Run the web backend locally, querying the hardware (assumes VPN or running in CALA)
live-dev-web: $(REQ)
	FLASK_DEBUG=True poetry run flask --app app.main:app run --port 8000

# Run the data collection agent and rules runner locally, querying the hardware (assumes VPN or running in CALA)
live-dev-runner: $(REQ)
	LOG_LEVEL=DEBUG $(PYTHON) bin/runner.py

tags:
	etags */*.py

.PHONY: local-dev live-dev-web live-dev-runner tags
################################################################
## Analysis tools
## Static Analysis
PYLINT_THRESHOLD := 10.0
PYLINT_OPTS :=--output-format=parseable --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose

lint: check
check: $(REQ)
	$(MAKE) ruff-check
	$(MAKE) no-type-ignore
	$(MAKE) pylint-check
	$(MAKE) djlint
	$(MAKE) eslint
	$(MAKE) check-types
	$(MAKE) validate-migrations

format: $(REQ)
	poetry run ruff check --fix app | etc/ruff-reformat.bash

pylint: ruff-check pylint-check

ruff-check: $(REQ)
	poetry run ruff check app

no-type-ignore:
	@! rg -n 'type:\s*ignore|type:ignore' app bin tests *.py

pylint-check: $(REQ)
	$(PYTHON) -m pylint $(PYLINT_OPTS) app tests *.py

djlint: $(REQ)
	poetry run djlint $(DJLINT_FLAGS) $(TEMPLATE_DIR)/*.html

eslint: $(REQ)
	(cd app/static; make eslint)

check-types: $(REQ)
	poetry run mypy app

## Dynamic Analysis
pytest: $(REQ)
	make pylint
	$(PYTHON) -m pytest $(PYTEST_ARGS) -v --cov=. --cov-report=xml --cov-report=html --log-cli-level=WARNING --log-file-level=DEBUG
	@echo coverage report in htmlcov/
test-js: $(REQ)
	@echo "Running JavaScript unit tests..."
	node tests/test_time_utils.js
	node tests/test_temperature_utils.js
	node tests/test_unit_speed.js
test: $(REQ)
	@python_exit=0; js_exit=0; \
	make pytest || python_exit=$$?; \
	make test-js || js_exit=$$?; \
	exit $$(($$python_exit + $$js_exit))

playwright-install: $(REQ)
	poetry run playwright install --with-deps chromium

web-screenshots: $(REQ) playwright-install
	$(PYTHON) bin/render_web_ui_pages.py

outdated: $(REQ)
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
##  * * * * * cd /home/air/temperature-bot ; DB_PATH=/var/db/temperature-bot.db .venv/bin/python -m bin.runner --loglevel INFO >> /home/air/temperature-bot.log 2>&1
##
##
## @daily    cd /home/air/temperature-bot ; sleep 15 ; DB_PATH=/var/db/temperature-bot.db .venv/bin/python -m bin.runner --loglevel INFO --daily  >> /home/air/temperature-bot-daily.log 2>&1
## @hourly   cd /home/air/temperature-bot ; sleep 30 ; DB_PATH=/var/db/temperature-bot.db .venv/bin/python -m bin.runner --loglevel INFO --aqi    >> /home/air/temperature-bot-hourly.log 2>&1
##
## Question - should we just have cron do a 'make daily' and 'make every-minute' ?

every-minute: $(REQ)
	$(PYTHON) -m bin.runner

daily: $(REQ)
	$(PYTHON) -m bin.runner --daily

monthly-backup:
	sudo cp /var/db/temperature-bot.db /var/db/temperature-bot.backup.$$(date -I).db

.PHONY: every-minute daily monthly-backup

################################################################
## Installation targets

install-either:
	pipx ensurepath
	pipx install poetry==$(POETRY_VERSION)
	poetry config virtualenvs.in-project true
	poetry lock
	poetry install --with dev
	poetry run playwright install --with-deps # This will be fast if CI restored .playwright

install-ubuntu:
	sudo apt install python3-pip pipx
	make install-either

install-macos:
	@echo Use pipx for the latest poetry
	@if ! command -v brew >/dev/null 2>&1; then \
		echo "Error: Homebrew is not installed. Please install Homebrew from https://brew.sh/ and try again."; \
		exit 1; \
	fi
	brew install pipx
	make install-either

# Clean all the tmp and work product files.
clean:
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

# Clean very aggressively, including the local db
# [TODO] Should this also clear the private data in temperature-bot-config.yaml?
cleanall: clean
	@echo "Doing aggressive cleanup. This will delete the local database!"
	@printf "Are you sure you want to delete $(DEV_DB)? [y/N] "
	@read -r confirm && [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ] && rm -f $(DEV_DB) || echo "Cancelled."

## Installs the latest source code into the live system and applies any pending
## database migrations. Run on the server (slg1.basistech.net).
deploy:
	@if [ "$$(hostname)" = "$(PROD_HOSTNAME)" ]; then \
		cd $(PROD_APP_DIR) && \
		git pull && \
		poetry install && \
		flyway validate \
		    -url="jdbc:sqlite:$(PROD_DB)" \
		    -locations="filesystem:etc/flyway/sql" && \
		/bin/mkdir -p $(PROD_BACKUP_DIR) && \
		/bin/cp -f $(PROD_DB) $(PROD_BACKUP_DIR)/temperature-bot.$$(date -u +%Y%m%dT%H%M%SZ).db && \
		flyway migrate \
		    -url="jdbc:sqlite:$(PROD_DB)" \
		    -locations="filesystem:etc/flyway/sql" \
		    -baselineOnMigrate=true && \
		flyway validate \
		    -url="jdbc:sqlite:$(PROD_DB)" \
		    -locations="filesystem:etc/flyway/sql" ; \
	else \
		echo "Deploy skipped: not running on $(PROD_HOSTNAME) (current hostname: $$(hostname))"; \
	fi


.PHONY: install-either install-ubuntu install-macos clean cleanall deploy
