# Makefile – common commands for RaterHub Tracker

# Configurable vars
PYTHON=python3
ENV=.env
DOCKER_IMAGE=raterhub-tracker
APP_DIR=app

.PHONY: help run dev shell lint format test build clean

help:
	@echo "Makefile commands:"
	@echo "  make run           # Run the app with uvicorn"
	@echo "  make dev           # Run in auto-reload dev mode"
	@echo "  make shell         # Launch interactive Python shell"
	@echo "  make lint          # Run flake8 linter"
	@echo "  make format        # Run black code formatter"
	@echo "  make test          # Run tests (pytest)"
	@echo "  make build         # Build Docker image"
	@echo "  make clean         # Clean __pycache__ etc."

run:
	$(PYTHON) -m uvicorn $(APP_DIR).main:app --host 0.0.0.0 --port 8000 --env-file $(ENV)

dev:
	$(PYTHON) -m uvicorn $(APP_DIR).main:app --reload --env-file $(ENV)

shell:
	$(PYTHON)

lint:
	flake8 $(APP_DIR)

format:
	black $(APP_DIR)

test:
	pytest

build:
	docker build -t $(DOCKER_IMAGE) .

clean:
	find . -type d -name '__pycache__' -exec rm -rf {} +
