DBFILE = '/var/db/temperature-bot.db'
DEV_DB = './temperature-bot.db'
REQ := .venv/pyvenv.cfg
PYTHON := .venv/bin/python

pytest: $(REQ)
	$(PYTHON) -m pytest . --log-cli-level=DEBUG --log-file-level=DEBUG

pytest-coverage: $(REQ)
	$(PYTHON) -m pytest . -v --cov=. --cov-report=xml --cov-report=html --log-cli-level=DEBUG --log-file-level=DEBUG
	@echo covreage report in htmlcov/

tags:
	etags */*.py

PYLINT_THRESHOLD := 9.5
PYLINT_OPTS :=--output-format=parseable --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose
check: $(REQ)
	$(PYTHON) -m ruff check .
	$(PYTHON) -m pylint $(PYLINT_OPTS) app tests *.py
	$(PYTHON) -m mypy app

type-check: $(REQ)
	$(PYTHON) -m mypy app

dump-schema:
	echo ".schema"| sqlite3 $(DBFILE) | grep -v 'CREATE TABLE sqlite_sequence' > etc/schema.sql

make-dev-db:
	/bin/rm -f $(DEV_DB)
	sqlite3 $(DEV_DB) < etc/schema.sql
	ls -l $(DEV_DB)

local-dev: $(REQ)
	FLASK_DEBUG=True $(PYTHON) run_local.py

################################################################
## Every minutes
every-minute: $(REQ)
	$(PYTHON) -m bin.runner
daily: $(REQ)
	$(PYTHON) -m bin.runner --daily


install-ubuntu:
	sudo apt install python3-pip pipx
	pipx ensurepath
	pipx install poetry ruff
	poetry config virtualenvs.in-project true
	ruff --version
	poetry lock && poetry install
	echo disabled - npm install browser-sync -g

install-macos:
	@echo Use pipx for the latest poetry
	pip install pipx
	pipx ensurepath
	pipx install poetry ruff
	poetry config virtualenvs.in-project true
	ruff --version
	poetry lock && poetry install
	echo disabled - npm install browser-sync -g


eslint:
	(cd app/static; make eslint)

# Create the virtual environment and install both host requirements
# and the lambda requirements for testing
.venv/pyvenv.cfg:
	@echo install venv for the development environment
	echo $$PATH
	poetry install
