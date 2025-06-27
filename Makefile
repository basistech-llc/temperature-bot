DBFILE = '/var/db/temperature-bot.db'

pytest:
	.venv/bin/pytest .

ruff-check:
	ruff check .

dump-schema:
	echo ".schema"| sqlite3 $(DBFILE) > etc/schema.sql


# Create the virtual environment and install both host requirements
# and the lambda requirements for testing
venv:
	python3.12 -m venv venv
	. venv/bin/activate ; pip install --upgrade pip
	. venv/bin/activate ; pip install -r requirements.txt

.PHONY: venv
