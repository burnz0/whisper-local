VENV ?= /Users/burnz0/.transcribe-venv
HOST ?= 127.0.0.1
PORT ?= 8765

.PHONY: run check

run:
	$(VENV)/bin/python app.py --host $(HOST) --port $(PORT)

check:
	PYTHONPYCACHEPREFIX=.pycache python3 -m py_compile app.py
