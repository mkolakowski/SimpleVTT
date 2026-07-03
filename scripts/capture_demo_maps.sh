#!/usr/bin/env bash
# Capture the live demo maps' editor state into paste-ready seed snippets.
# Pipes scripts/capture_demo_maps.py into the app container's Python (which has
# the app package + DB access) and prints the blocks to stdout. See the Python
# file's docstring for the workflow. Run from the repo root:
#
#     scripts/capture_demo_maps.sh
#
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
docker compose exec -T app python - < "$here/capture_demo_maps.py"
