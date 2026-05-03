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

# Create dirs for uploaded maps and tokens
RUN mkdir -p /app/app/static/uploads/maps /app/app/static/uploads/tokens

# Listening port — overridable via APP_PORT env var.
ENV APP_PORT=8013
EXPOSE 8013

# Use sh -c so APP_PORT is expanded at container start.
CMD sh -c 'uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT:-8013}" --proxy-headers'
