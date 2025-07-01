DBFILE = '/var/db/temperature-bot.db'
DEV_DB = './temperature-bot.db'
REQ := .venv/pyvenv.cfg
PYTHON := .venv/bin/python

pytest: $(REQ)
	$(PYTHON) -m pytest . --log-cli-level=DEBUG --log-file-level=DEBUG

pytest-coverage: $(REQ)
	$(PYTHON) -m pytest -v --cov=. --cov-report=xml --cov-report=html tests
	@echo covreage report in htmlcov/

ruff-check:
	ruff check .

dump-schema:
	echo ".schema"| sqlite3 $(DBFILE) | grep -v 'CREATE TABLE sqlite_sequence' > etc/schema.sql

make-dev-db:
	/bin/rm -f $(DEV_DB)
	sqlite3 $(DV_DB) < etc/schema.sql

dev:
	.venv/bin/fastapi dev

install-ubuntu:
	sudo apt install python3-pip
	pip install --user pipx
	pipx ensurepath
	pipx install uv
	uv --version
	pipx install ruff
	ruff --version

install-macos:
	@echo Use pipx for the latest uv
	pip install pipx
	pipx ensurepath
	pipx install uv
	uv --version # Check this output: it *must* be 0.1.18 or higher
	pipx install ruff
	ruff --version


eslint:
	(cd static; make eslint)

# Create the virtual environment and install both host requirements
# and the lambda requirements for testing
.venv/pyvenv.cfg:
	@echo install venv for the development environment
	echo $$PATH
	uv venv
	uv pip sync pyproject.toml
	uv add --dev pytest
