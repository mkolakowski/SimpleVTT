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

## Touch targets must meet Apple's 44×44pt minimum

All interactive elements (buttons, links, inputs, selects) must have a minimum tap target of **44×44 px**.

**Rules:**

- Never create a button or interactive element with a combined height (padding + line-height) below 44 px unless it is inside a deliberately compact panel (e.g. dense row-based UIs like the initiative tracker or mini-sheet). In those cases use a minimum of **32 px** and add a code comment explaining the exception.
- The global `button` rule in `app/static/style.css` already sets `min-height: 44px; display: inline-flex; align-items: center; justify-content: center;` — do not remove these.
- The global `input` / `select` rule in `app/static/style.css` already sets `min-height: 44px` — do not remove it.
- When writing new compact button classes (e.g. for a dense panel), explicitly set `min-height: 32px` (not lower) and do **not** rely on the fallback from the base rule.
- For absolutely-positioned overlay buttons (like the roll-expression clear button), set `width` and `height` to at least 44 px, or expand the target area with `padding` so the total touch area is 44×44 px.
- Avoid `padding: 0`, `padding: 1px`, or `padding: 2px` on any clickable element.

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
