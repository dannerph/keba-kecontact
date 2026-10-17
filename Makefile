.PHONY: install test

install:
	curl -LsSf https://astral.sh/uv/install.sh | sh
	uv sync --extra dev

test:
	uv run pytest
