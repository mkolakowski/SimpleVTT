# Multi-arch (works on amd64 + arm64) Python base
FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app /app/app

# v2.43.3: copy the wiki content into the image so the /wiki/<slug>
# route in app/routes/wiki_routes.py can serve the guides from
# /app/docs/wiki/. The route's slug guard restricts to alphanumerics +
# dashes/underscores so we don't traverse outside this directory.
COPY docs/wiki /app/docs/wiki

# v2.49.9: also bake the plans + reference docs so /wiki/doc/<slug>
# can resolve them through the _DOC_ALLOWLIST mapping in
# app/routes/wiki_routes.py. Same security stance — the allowlist
# plus the slug guard restrict reachable files to a fixed set.
COPY docs/plans /app/docs/plans
COPY docs/demo /app/docs/demo
COPY docs/encounters-plan.md /app/docs/encounters-plan.md
COPY docs/multi-system-refactor.md /app/docs/multi-system-refactor.md
COPY docs/roll-log-card-layout.md /app/docs/roll-log-card-layout.md
COPY docs/test-harness-coverage.md /app/docs/test-harness-coverage.md
COPY docs/automation-coverage.md /app/docs/automation-coverage.md

# v2.49.9: repo-root docs surfaced through /wiki/doc/<slug>.
COPY README.md /app/README.md
COPY CHANGELOG.md /app/CHANGELOG.md
COPY CHANGELOG_v1.md /app/CHANGELOG_v1.md
COPY CLAUDE.md /app/CLAUDE.md
COPY CREDITS.md /app/CREDITS.md
COPY TODO.md /app/TODO.md

# Create dirs for uploaded maps and tokens, and the homebrew volume mountpoint
# (so the volume can mount cleanly on a fresh container before anything is
# written to it).
RUN mkdir -p /app/app/static/uploads/maps /app/app/static/uploads/tokens /app/app/data/homebrew

# Listening port — overridable via APP_PORT env var.
ENV APP_PORT=8013
EXPOSE 8013

# Use sh -c so APP_PORT is expanded at container start.
CMD sh -c 'uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT:-8013}" --proxy-headers'
