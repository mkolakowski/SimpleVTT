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

# Create dirs for uploaded maps and tokens, and the homebrew volume mountpoint
# (so the volume can mount cleanly on a fresh container before anything is
# written to it).
RUN mkdir -p /app/app/static/uploads/maps /app/app/static/uploads/tokens /app/app/data/homebrew

# Listening port — overridable via APP_PORT env var.
ENV APP_PORT=8013
EXPOSE 8013

# Use sh -c so APP_PORT is expanded at container start.
CMD sh -c 'uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT:-8013}" --proxy-headers'
