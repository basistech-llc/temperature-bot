DBFILE = '/var/db/temperature-bot.db'
DEV_DB = 'var/db/temperature-bot.db'
REQ := .venv/pyvenv.cfg
PYTHON := .venv/bin/python

pytest: $(REQ)
	AE200_SIMULATOR=1 $(PYTHON) -m pytest . -v --cov=. --cov-report=xml --cov-report=html --log-cli-level=DEBUG --log-file-level=DEBUG
	@echo covreage report in htmlcov/

PYLINT_THRESHOLD := 9.5
PYLINT_OPTS :=--output-format=parseable --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose
check: $(REQ)
	make lint
	echo $(PYTHON) -m mypy app tests

check-types: $(REQ)
	$(PYTHON) -m mypy app

.PHONY: etc/schema.sql
etc/schema.sql:
	echo ".schema"| sqlite3 $(DEV_DB) | grep -v 'Run Time: real' | grep -v 'CREATE TABLE sqlite_sequence' > etc/schema.sql

make-dev-db:
	/bin/rm -f $(DEV_DB)
	sqlite3 $(DEV_DB) < etc/schema.sql
	ls -l $(DEV_DB)

local-dev: $(REQ)
	FLASK_DEBUG=True $(PYTHON) run_local.py

fetch-slg:
	rsync --verbose --delete --archive slg1.basistech.net:/var/db var/
	echo 'select "devices",count(*) from devices;select "devlog",count(*) from devlog;select "changelog",count(*) from changelog; select "aqi",count(*) from aqi;' | sqlite3 var/db/temperature-bot.db
	echo '.schema' | sqlite3 var/db/temperature-bot.db

tags:
	etags */*.py

## lint
.PHONY: eslint pylint lint
PYLINT_THRESHOLD := 9.5
PYLINT_OPTS :=--output-format=parseable --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose

## test

pylint: .venv/pyvenv.cfg
	.venv/bin/djlint $(DJLINT_FLAGS) $(TEMPLATE_DIR)/*.html
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m pylint $(PYLINT_OPTS) app tests *.py

eslint:
	(cd app/static; make eslint)

lint:
	make pylint
	make eslint

check: $(REQ)
	make lint
	echo do not make check-types

pytest: $(REQ)
	AE200_SIMULATOR=1 $(PYTHON) -m pytest . -v --cov=. --cov-report=xml --cov-report=html --log-cli-level=DEBUG --log-file-level=DEBUG
	@echo covreage report in htmlcov/

check-types: $(REQ)
	$(PYTHON) -m mypy app

# Create the virtual environment and install both host requirements
# and the lambda requirements for testing
.venv/pyvenv.cfg:
	@echo install venv for the development environment
	echo $$PATH
	poetry install


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
