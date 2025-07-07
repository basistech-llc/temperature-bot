DBFILE = '/var/db/temperature-bot.db'
DEV_DB = './temperature-bot.db'
REQ := .venv/pyvenv.cfg
PYTHON := .venv/bin/python

pytest: $(REQ)
	$(PYTHON) -m pytest . --log-cli-level=DEBUG --log-file-level=DEBUG

pytest-coverage: $(REQ)
	$(PYTHON) -m pytest -v --cov=. --cov-report=xml --cov-report=html tests
	@echo covreage report in htmlcov/

tags:
	etags */*.py

PYLINT_THRESHOLD := 9.5
PYLINT_OPTS : =--output-format=parseable --rcfile .pylintrc --fail-under=$(PYLINT_THRESHOLD) --verbose
check:
	ruff check .
	$(PYTHON) -m pylint $(PYLINT_OPTS) app tests *.py

dump-schema:
	echo ".schema"| sqlite3 $(DBFILE) | grep -v 'CREATE TABLE sqlite_sequence' > etc/schema.sql

make-dev-db:
	/bin/rm -f $(DEV_DB)
	sqlite3 $(DEV_DB) < etc/schema.sql
	ls -l $(DEV_DB)

local-dev:
	.venv/bin/fastapi dev
#sleep 1
#browser-sync 'http://localhost:8000' 'static' --watch --files .


install-ubuntu:
	sudo apt install python3-pip
	pip install --user pipx
	pipx ensurepath
	pipx install poetry ruff
	ruff --version
	poetry install
	npm install browser-sync -g

install-macos:
	@echo Use pipx for the latest poetry
	pip install pipx
	pipx ensurepath
	pipx install poetry ruff
	pipx install ruff
	ruff --version
	poetry install
	npm install browser-sync -g


eslint:
	(cd static; make eslint)

# Create the virtual environment and install both host requirements
# and the lambda requirements for testing
.venv/pyvenv.cfg:
	@echo install venv for the development environment
	echo $$PATH
	poetry install
