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
	sudo snap install ruff
	curl -LO https://github.com/astral-sh/uv/releases/download/0.1.19/uv-x86_64-unknown-linux-gnu.tar.gz
	tar -xzf uv-x86_64-unknown-linux-gnu.tar.gz
	sudo mv uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv

install-macos:
	brew install ruff uv


eslint:
	(cd static; make eslint)

# Create the virtual environment and install both host requirements
# and the lambda requirements for testing
.venv/pyvenv.cfg:
	@echo install venv for the development environment
	echo $$PATH
	uv pip sync
