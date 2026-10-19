.PHONY: setup install lint format test test-unit check raw segment pipeline

PYTHON ?= python
DATA ?= data
LAKE ?= freshmart-lake

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"
	.venv/bin/pre-commit install

install:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m mypy

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest -m "not integration"

check: lint test

raw:
	$(PYTHON) scripts/subir_a_raw.py --input $(DATA) --output $(LAKE)/raw

segment:
	$(PYTHON) scripts/segmentar.py --input $(DATA) --verify

pipeline:
	$(PYTHON) scripts/ejecutar_pipeline.py --catalog --input $(DATA) --silver-dir $(LAKE)/silver
	$(PYTHON) scripts/ejecutar_pipeline.py --all --input $(DATA) --silver-dir $(LAKE)/silver --gold-dir $(LAKE)/gold
