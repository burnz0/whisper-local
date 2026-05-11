VENV ?= /Users/burnz0/.transcribe-venv
HOST ?= 127.0.0.1
PORT ?= 8765

.PHONY: run check test migrate deps

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
