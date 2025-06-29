DBFILE = '/var/db/temperature-bot.db'

pytest:
	.venv/bin/pytest .

ruff-check:
	ruff check .

dump-schema:
	echo ".schema"| sqlite3 $(DBFILE) | grep -v 'CREATE TABLE sqlite_sequence' > etc/schema.sql


dev:
	.venv/bin/fastapi dev


# Create the virtual environment and install both host requirements
# and the lambda requirements for testing
.venv/bin/pytest:
	uv sync
