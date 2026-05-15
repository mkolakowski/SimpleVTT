# SimpleVTT — Claude Code guidelines

## Always update the changelog and version when making changes

**Every commit ships its own version bump.** One conceptually-distinct change = one commit = one version bump = one CHANGELOG entry. No batching unrelated edits into a single release: if you fix three unrelated bugs in a session, ship three commits at e.g. `1.11.1`, `1.11.2`, `1.11.3` — not one commit at `1.11.0` listing all three under `### Fixed`. The only thing that may legitimately span multiple files in a single commit is a single coherent change (one feature, one bug, one refactor) that needs the multi-file edit to be reviewable. Read `CHANGELOG.md` in full at the start of any version-related work — the file contains detailed bump rules and a required entry format in its header section.

**Quick rules:**

- `APP_VERSION` lives in `app/version.py` and follows SemVer. **Pick the highest bump that applies** — every commit bumps at least PATCH:
  - **PATCH** (`0.0.x`) — **the default**. Bumps on every commit, including pure bug fixes, copy tweaks, comment-only edits, refactors with no behavior change, dependency updates, doc edits, etc. There is no such thing as a "no bump" commit.
  - **MINOR** — new backward-compatible feature or additive schema change. (A MINOR bump satisfies the "every commit ships a bump" rule too — you don't bump PATCH on top.)
  - **MAJOR** — breaking API/config/schema change that requires operator action. (Same — replaces the PATCH bump for that release. **Also triggers the changelog-archive rule below.**)
- `SCHEMA_VERSION` (also in `app/version.py`) increments by **+1** for every migration block added to `_apply_inline_migrations()` in `app/database.py`.
- Add a new `## [X.Y.Z] - YYYY-MM-DD` section at the **top** of the changelog (below the instructions header). Use today's UTC date.
- Every entry must include: heading, `**Schema version:** N`, `**Commit summary:**`, `**Description:**`, and at least one categorised change list (`### Added`, `### Changed`, `### Fixed`, `### Schema`, etc.).
- Also update the version badge in the first paragraph of `README.md` to match.
- Do **not** edit version numbers anywhere else — `app/version.py` is the single source of truth.

**On MAJOR version bumps, archive the prior changelog.**

When `APP_VERSION`'s MAJOR segment increments (e.g. `1.x.x` → `2.0.0`):

1. **Rename** the existing `CHANGELOG.md` to `CHANGELOG_v<N>.md` where `<N>` is the **outgoing** major version (e.g. `CHANGELOG_v1.md` when cutting `2.0.0`). Keep the file at the repo root so it's grep-able next to the active `CHANGELOG.md`.
2. **Create a fresh `CHANGELOG.md`** that opens with the same header preamble (the `# Changelog` heading + the keep-a-changelog / SemVer one-liner + the version-management pointer paragraph) and then the new `## [X.0.0] - YYYY-MM-DD` entry at the top. No older entries belong in the new file.
3. **Add a pointer line** at the very top of the active `CHANGELOG.md`, just under the header, in the form: `> For pre-X.0.0 history, see [CHANGELOG_v<N>.md](CHANGELOG_v<N>.md).` so future readers find the archive.
4. The archive file is read-only after the rename — never back-patch entries into it. If a `1.x.x` bug fix lands after `2.0.0` ships, it goes on the active `CHANGELOG.md` under its own `2.x.y` entry.

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
