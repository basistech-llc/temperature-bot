pytest:
	. venv/bin/activate ; 	pytest .

pylint:
	. venv/bin/activate ; pylint app

# Create the virtual environment and install both host requirements
# and the lambda requirements for testing
venv:
	python3.12 -m venv venv
	. venv/bin/activate ; pip install --upgrade pip
	. venv/bin/activate ; pip install -r requirements.txt

.PHONY: venv
