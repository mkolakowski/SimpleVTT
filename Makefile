# SimpleVTT — convenience targets. The canonical workflow is
# `docker compose up -d --build`; these targets wrap common dev tasks.
.PHONY: help test-harness test-harness-install up down rebuild logs

help:
	@echo "Targets:"
	@echo "  make test-harness          Run the click-through test harness against a running stack"
	@echo "  make test-harness-install  Install dev deps (pytest + plugins) — one-time"
	@echo "  make up                    docker compose up -d --build"
	@echo "  make down                  docker compose down"
	@echo "  make rebuild               docker compose up -d --build (alias of up)"
	@echo "  make logs                  docker compose logs -f app"

test-harness-install:
	pip install -r requirements-dev.txt

# Runs the click-through harness from docs/plans/test-harness.md.
# Defaults: HARNESS_BASE_URL=http://localhost:8013, demo accounts,
# campaign 1. Override via env vars (see helpers.py for the full list).
test-harness:
	pytest tests/harness/ -v

up rebuild:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f app
