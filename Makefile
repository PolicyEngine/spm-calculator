.PHONY: install test format lint docs clean

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --cov=spm_calculator --cov-report=term-missing

format:
	black .
	ruff check --fix .

lint:
	black --check .
	ruff check .

docs:
	myst build docs --html

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage coverage.xml
	rm -rf docs/_build/
	find . -type d -name __pycache__ -exec rm -rf {} +
