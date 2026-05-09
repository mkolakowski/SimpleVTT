# SimpleVTT — Claude Code guidelines

## Always update the changelog and version when making changes

Every time you make a user-visible, behavior-changing, or schema-changing edit you **must** update both `app/version.py` and `CHANGELOG.md` before finishing. Read `CHANGELOG.md` in full at the start of any version-related work — the file contains detailed bump rules and a required entry format in its header section.

**Quick rules:**

- `APP_VERSION` lives in `app/version.py` and follows SemVer:
  - **PATCH** — bug fixes, copy tweaks, no schema change.
  - **MINOR** — new backward-compatible feature or additive schema change.
  - **MAJOR** — breaking API/config/schema change that requires operator action.
- `SCHEMA_VERSION` (also in `app/version.py`) increments by **+1** for every migration block added to `_apply_inline_migrations()` in `app/database.py`.
- Add a new `## [X.Y.Z] - YYYY-MM-DD` section at the **top** of the changelog (below the instructions header). Use today's UTC date.
- Every entry must include: heading, `**Schema version:** N`, `**Commit summary:**`, `**Description:**`, and at least one categorised change list (`### Added`, `### Changed`, `### Fixed`, `### Schema`, etc.).
- Also update the version badge in the first paragraph of `README.md` to match.
- Do **not** edit version numbers anywhere else — `app/version.py` is the single source of truth.

## Third-party APIs must be Docker Compose services

When integrating any external API or data service, add it as a named service in
`docker-compose.yml` rather than calling a public endpoint directly at request
time. This keeps every dependency on the internal Docker network, works offline,
and removes runtime internet calls from the hot path.

**Pattern to follow for every new API:**

1. Add a service block in `docker-compose.yml` with a `healthcheck`.
2. Add the internal base URL as an env var in the `app` service
   (e.g. `MY_API_BASE_URL: http://myapi:port/v1`).
3. Add the env var (commented out) to `.env.example` with a note that
   docker-compose sets it automatically.
4. Read the env var at module level in the relevant route file with a sensible
   public-internet default so the app still works outside Docker:
   ```python
   _MY_API_BASE = os.getenv("MY_API_BASE_URL", "https://api.example.com/v1").rstrip("/")
   ```
5. Use that variable everywhere instead of a hardcoded URL.
