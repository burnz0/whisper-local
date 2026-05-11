PYTHON ?= python3.12
VENV ?= .venv
HOST ?= 127.0.0.1
PORT ?= 8765

.PHONY: venv install install-core install-ml run check test migrate deps benchmark

venv:
	$(PYTHON) -m venv $(VENV)

install-core: venv
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements-core.txt

install-ml: install-core
	$(VENV)/bin/pip install -r requirements-ml.txt

install: install-ml

run:
	$(VENV)/bin/python app.py --host $(HOST) --port $(PORT)

check:
	PYTHONPYCACHEPREFIX=.pycache $(VENV)/bin/python -m py_compile app.py
	PYTHONPYCACHEPREFIX=.pycache $(VENV)/bin/python -m unittest discover -s tests

test:
	PYTHONPYCACHEPREFIX=.pycache $(VENV)/bin/python -m unittest discover -s tests

migrate:
	$(VENV)/bin/python app.py --migrate-library

deps:
	$(VENV)/bin/python app.py --check-deps

benchmark:
	$(VENV)/bin/python benchmarks.py --audio "$(AUDIO)" --model "$(MODEL)" --language "$(LANGUAGE)"
