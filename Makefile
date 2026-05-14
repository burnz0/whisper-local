PYTHON ?= $(shell command -v python3.12 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3 2>/dev/null)
VENV ?= .venv
HOST ?= 127.0.0.1
PORT ?= 8765
MODEL ?= small
MODELS ?= $(MODEL)
LANGUAGE ?= de
EXPECTED_TERMS ?=

VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip

.PHONY: venv install install-core install-ml run check test migrate deps benchmark

$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip

venv: $(VENV_PYTHON)

install-core: venv
	$(VENV_PIP) install -r requirements-core.txt

install-ml: install-core
	$(VENV_PIP) install -r requirements-ml.txt

install: install-ml

run: install-core
	$(VENV_PYTHON) app.py --host $(HOST) --port $(PORT)

check:
	PYTHONPYCACHEPREFIX=.pycache $(VENV_PYTHON) -m py_compile app.py
	PYTHONPYCACHEPREFIX=.pycache $(VENV_PYTHON) -m unittest discover -s tests

test:
	PYTHONPYCACHEPREFIX=.pycache $(VENV_PYTHON) -m unittest discover -s tests

migrate:
	$(VENV_PYTHON) app.py --migrate-library

deps:
	$(VENV_PYTHON) app.py --check-deps

benchmark:
	$(VENV_PYTHON) benchmarks.py --audio "$(AUDIO)" --models "$(MODELS)" --language "$(LANGUAGE)" --expected-terms "$(EXPECTED_TERMS)"
