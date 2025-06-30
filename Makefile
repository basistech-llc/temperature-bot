DBFILE = '/var/db/temperature-bot.db'
DEV_DB = './temperature-bot.db'

pytest:
	.venv/bin/pytest . --log-cli-level=DEBUG --log-file-level=DEBUG

ruff-check:
	ruff check .

dump-schema:
	echo ".schema"| sqlite3 $(DBFILE) | grep -v 'CREATE TABLE sqlite_sequence' > etc/schema.sql

make-dev-db:
	/bin/rm -f $(DEV_DB)
	sqlite3 $(DV_DB) < etc/schema.sql

dev:
	.venv/bin/fastapi dev


# Create the virtual environment and install both host requirements
# and the lambda requirements for testing
.venv/bin/pytest:
	uv sync
