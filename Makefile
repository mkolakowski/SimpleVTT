# SimpleVTT — convenience targets. The canonical workflow is
# `docker compose up -d --build`; these targets wrap common dev tasks.
.PHONY: help test-harness test-harness-install up down rebuild logs

help:
	@echo "Targets:"
	@echo "  make test-harness          Run the HTTP+WS click-through harness against a running stack"
	@echo "  make test-harness-ui       Run the Playwright UI harness (slower; needs 'playwright install chromium' first)"
	@echo "  make test-harness-install  Install dev deps (pytest + plugins + Playwright) — one-time"
	@echo "  make up                    docker compose up -d --build"
	@echo "  make down                  docker compose down"
	@echo "  make rebuild               docker compose up -d --build (alias of up)"
	@echo "  make logs                  docker compose logs -f app"

test-harness-install:
	pip install -r requirements-dev.txt
	@echo ""
	@echo "Next step (one-time, ~250MB download for chromium):"
	@echo "  playwright install chromium"

# Phase 1+1.5 of the test harness — HTTP+WS contract tests against
# every clickable endpoint. Fast (~17s). See docs/plans/test-harness.md.
test-harness:
	pytest tests/harness/ -v

# Phase 4 of the test harness — Playwright UI-layer tests. Slower
# (~30-60s for the current vertical slice; will grow as coverage
# expands). Requires `playwright install chromium` after the dev-
# deps install. Run separately from `make test-harness` because of
# the browser overhead.
test-harness-ui:
	pytest tests/harness_ui/ -v

up rebuild:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f app
