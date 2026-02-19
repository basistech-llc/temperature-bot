#
# Makefile for temperature bot
#
# install macOS or Linux environments on clean vm:
#    make install-ubuntu | install-macos
#
# Local development:
#    make check   - static analysis
#    make test    - dynamic analysis
#    make make-dev-db  - creates a local database from the schema
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


DB_PATH ?= var/db/temperature-bot.db
DEV_DB   ?= var/db/temperature-bot.db
REQ := .venv/pyvenv.cfg
PYTHON := .venv/bin/python
TEMPLATE_DIR := app/templates

# Centralize the Playwright cache path so CI can cache it
export PLAYWRIGHT_BROWSERS_PATH := .playwright

# Pin tool versions (helps avoid "invisible" cache invalidations)
POETRY_VERSION ?= 2.1.3
RUFF_VERSION   ?= 0.13.2



################################################################
# Create the virtual environment and install both host requirements
# and the lambda requirements for testing
.venv/pyvenv.cfg:
	@echo install venv for the development environment
	echo $$PATH
	poetry install

################################################################
.PHONY: etc/schema.sql
etc/schema.sql:
	echo ".schema"| sqlite3 $(DEV_DB) \
		| grep -v 'Run Time: real' \
		| grep -v 'CREATE TABLE sqlite_sequence' \
		| sed 's/CREATE INDEX/CREATE INDEX IF NOT EXISTS/' \
		| sed 's/CREATE TABLE/CREATE INDEX IF NOT TABLE/' \
		| tee etc/schema.sql

make-dev-db:
	/bin/rm -f $(DEV_DB)
	mkdir -p $(dir $(DEV_DB))
	sqlite3 $(DEV_DB) < etc/schema.sql
	ls -l $(DEV_DB)

fetch-dev-db:
	rsync --verbose --delete --archive slg1.basistech.net:/var/db var/
	echo 'select "devices",count(*) from devices;select "devlog",count(*) from devlog;select "changelog",count(*) from changelog; select "aqi",count(*) from aqi;' | sqlite3 var/db/temperature-bot.db
	/bin/rm -f etc/schema.sql
	make etc/schemq.sql

# Run web backend locally, with simulated data. (needs popuplated db too)
local-dev: $(REQ)
	FLASK_DEBUG=True AE200_SIMULATOR=1 $(PYTHON) run_local.py

# Run the web backend locally, querying the hardware (assumes VPN or running in CALA)
live-dev-web: $(REQ)
	FLASK_DEBUG=True $(PYTHON) run_local.py

# Run the data collection agent and rules runner locally, querying the hardware (assumes VPN or running in CALA)
live-dev-runner: $(REQ)
	LOG_LEVEL=DEBUG $(PYTHON) bin/runner.py

tags:
	etags */*.py

################################################################

## Static Analysis
.PHONY: eslint lint pylint test pytest clean
PYLINT_THRESHOLD := 9.5
PYLINT_OPTS :=--output-format=parseable --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose

pylint: .venv/pyvenv.cfg
	poetry run ruff check --fix app | etc/ruff-reformat.bash
	$(PYTHON) -m pylint $(PYLINT_OPTS) app tests *.py

djlint:
	poetry run djlint $(DJLINT_FLAGS) $(TEMPLATE_DIR)/*.html | etc/djlint-reformat.bash

eslint:
	(cd app/static; make eslint)

lint: check
check: $(REQ)
	make pylint
	make djlint
	make eslint
	echo make check-types

check-types: $(REQ)
	poetry run mypy app

## Dynamic Analysis
pytest: $(REQ)
	make pylint
	$(PYTHON) -m pytest . -v --cov=. --cov-report=xml --cov-report=html --log-cli-level=WARNING --log-file-level=DEBUG
	@echo coverage report in htmlcov/
test-js:
	@echo "Running JavaScript unit tests..."
	node tests/test_time_utils.js
test: $(REQ)
	@python_exit=0; js_exit=0; \
	make pytest || python_exit=$$?; \
	make test-js || js_exit=$$?; \
	exit $$(($$python_exit + $$js_exit))

################################################################
## Every minutes
every-minute: $(REQ)
	$(PYTHON) -m bin.runner
daily: $(REQ)
	$(PYTHON) -m bin.runner --daily

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

install-browser-sync:
	npm install browser-sync -g

# Clean all the tmp and work product files.
clean:
	@echo "Cleaning up generated files and virtual environment..."
	rm -rf .venv
	rm -rf .playwright
	rm -rf htmlcov
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

## Installs the latest source code into the live system.
## Run on the server (slg1.basistech.net).
deploy:
	@if [ "$$(hostname)" = "slg1" ]; then \
		cd /home/air/temperature-bot && git pull && poetry install ; \
	else \
		echo "Deploy skipped: not running on slg1 (current hostname: $$(hostname))"; \
	fi
