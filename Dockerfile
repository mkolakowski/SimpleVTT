# Multi-arch (works on amd64 + arm64) Python base
FROM python:3.12-slim

# System deps
# v2.474.0 — add `gosu` so the entrypoint can drop from root to
# `appuser` after fixing volume permissions. gosu is a single-file
# Go binary that does setuid+setgid+exec without PAM / TTY churn.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        gosu \
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
COPY docs/self-test.md /app/docs/self-test.md
COPY docs/test-harness-coverage.md /app/docs/test-harness-coverage.md
COPY docs/automation-coverage.md /app/docs/automation-coverage.md
# v2.384.1 — condition-enforcement audit doc (v2.384.0 shipped the file
# + the allowlist entry but the COPY line was missing, so /wiki/doc/
# condition-enforcement-audit returned 404 in the rebuilt container).
COPY docs/condition-enforcement-audit.md /app/docs/condition-enforcement-audit.md

# v2.49.9: repo-root docs surfaced through /wiki/doc/<slug>.
COPY README.md /app/README.md
COPY CHANGELOG.md /app/CHANGELOG.md
COPY CHANGELOG_v1.md /app/CHANGELOG_v1.md
COPY CLAUDE.md /app/CLAUDE.md
COPY CREDITS.md /app/CREDITS.md
COPY TODO.md /app/TODO.md
COPY TODONE.md /app/TODONE.md
COPY BUGS.md /app/BUGS.md

# Create dirs for uploaded maps and tokens, and the homebrew volume mountpoint
# (so the volume can mount cleanly on a fresh container before anything is
# written to it).
# v2.474.0 — also bake the audit-log directory (/var/log/simplevtt) so the
# v2.469.0 RotatingFileHandler has a path it can write to even before
# the entrypoint chown runs.
RUN mkdir -p /app/app/static/uploads/maps \
             /app/app/static/uploads/tokens \
             /app/app/static/uploads/thumbnails \
             /app/app/static/uploads/audio \
             /app/app/data/homebrew \
             /var/log/simplevtt

# v2.474.0 — non-root hardening. Create an unprivileged `appuser`
# system account + own the runtime-writable paths. The container
# still starts as root so the entrypoint can chown named-volume
# mount points (whose owner is determined by first-touch, not by
# the image), then drops via gosu to `appuser` before exec'ing
# uvicorn. App listens on port 8013 (>1024), so no capability
# inheritance is required.
RUN groupadd --system appuser \
    && useradd --system --gid appuser --home /app --shell /sbin/nologin appuser \
    && chown -R appuser:appuser /app /var/log/simplevtt

# Install the entrypoint that does chown-then-drop.
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Listening port — overridable via APP_PORT env var.
ENV APP_PORT=8013
EXPOSE 8013
# v2.483.0 — the admin-center service (docker-compose.yml) reuses this
# image and listens on 8015 via `uvicorn app.admin_center.main:app`.
EXPOSE 8015

# v2.474.0 — entrypoint chowns the volume mount points (idempotent)
# then `exec gosu appuser ...`. CMD is the uvicorn invocation; the
# entrypoint forwards "$@" to gosu.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port \"${APP_PORT:-8013}\" --proxy-headers"]
