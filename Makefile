.PHONY: help install sync dry-run status clean

PYTHON := python3
VENV := venv
BIN := $(VENV)/bin

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -r requirements.txt

sync: ## Run the sync process
	$(BIN)/python -m src.main

dry-run: ## Run sync in dry-run mode
	$(BIN)/python -m src.main --dry-run

status: ## Show sync status
	$(BIN)/python -m src.main --status

clean: ## Remove artifacts and cache
	rm -rf __pycache__ .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
