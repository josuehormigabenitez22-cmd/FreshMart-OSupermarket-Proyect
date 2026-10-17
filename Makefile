
.PHONY: install lint format test check

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .

test:
	pytest

check:
	ruff check .
	ruff format --check .
	pytest
