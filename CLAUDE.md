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

**Always create the git commit at the end of the change.** A version bump that isn't committed isn't actually a release — it's just an uncommitted working-tree edit that disappears on the next `git reset` or context loss. After finishing the changes for a version bump (code + version + README + CHANGELOG, plus the harness test required by the harness-discipline rule below), `git add` the affected files and `git commit` them as a single commit. The commit message should match the convention seen in `git log --oneline` — short subject line of the form `X.Y.Z — <one-line summary>`, body optional but encouraged for non-trivial changes. Do this even if the user didn't say "please commit" — the per-commit / per-bump rule above already implies a commit happens. If the change is mid-flight (broken tests, half-written feature) say so and don't bump the version yet rather than landing an uncommitted bump. **Never run more than one version bump without committing in between** — if you've bumped to `2.50.0` and want to also ship `2.50.1`, commit `2.50.0` first, then start the next change. The "one bump = one commit" rule is meaningless if multiple bumps stack in the working tree.

**Restart the app container after every version bump.** The dev image bakes the code at build time (no live-reload mount on the `app` service in `docker-compose.yml`) — so a `git commit` that bumps `APP_VERSION` does **not** propagate to the running container automatically. After committing a version bump, run:

```bash
docker compose up -d --build app
```

and then poll `curl -s http://localhost:8013/version` until the response reports the new `APP_VERSION` (usually 5–15 s on Apple Silicon, longer on first build). This applies to **every** version bump — including doc-only commits where the source code didn't change, because `version.py` itself did and `/version` / `/healthz` would otherwise return a stale value to the harness and to any browser client polling for updates.

Why this matters:
- The harness tests at `tests/harness/` talk to `http://localhost:8013` (the docker app) over HTTP + WS, not to in-process code. A new endpoint added in this commit returns **404** until the container is rebuilt, so post-bump test runs against stale containers can mask real test failures or surface spurious ones.
- Manual click-through verification ("does the new button work?") needs the new code in the container too.
- The migration runner (`_apply_inline_migrations` at boot) only fires on container start. A `SCHEMA_VERSION` bump that isn't restarted leaves the DB schema un-migrated even though the code thinks it's been applied.

If the rebuild fails (port in use, db not healthy, image build error), investigate before retrying. Never reach for destructive workarounds like `docker compose down -v` — that wipes the postgres volume and the demo seed has known bugs on partial-state replays. Stop the container with `docker compose stop app`, fix the root cause, then re-run `docker compose up -d --build app`.

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

## Every new endpoint commit lands a harness test

The click-through harness at `tests/harness/` (see
`docs/plans/test-harness.md`) is the safety net for endpoint-contract
regressions. **Every commit that adds an HTTP endpoint or changes a
WebSocket broadcast shape MUST also land at least one harness test**
for the new surface. Doc-only / refactor-only commits are exempt.

**The test contract per endpoint:**

- One happy-path test that asserts on (a) HTTP status, (b) the
  JSON response body shape, and (c) the resulting WS broadcast type
  + the fields the client actually reads.
- At least one error-path test (400 missing fields, 404 unknown
  resource, or 409 contract-specific) — pick what's most likely to
  regress.
- If the endpoint touches the action-economy (`_mark_battle_economy`,
  `_is_slot_used`), the test passes `override: true` to bypass the
  Phase 4 gate (see Phase 1.5 notes in the plan).
- If the endpoint takes a `target_character_id`, fetch the roster via
  `/api/campaign/{cid}/roster` and look up by name — don't hardcode
  character IDs.

**Where it lives:** one file per endpoint, named
`tests/harness/test_<endpoint>.py`. Look at
`tests/harness/test_attack.py` for the canonical shape.

**When the harness can't cover it yet:** if the endpoint needs a
class that isn't in the demo (Paladin / Bard / Druid / etc.), file
the happy-path test for Phase 2's fixture-character work in the plan
doc, and ship the **error-path tests this commit anyway**. Error
paths exercise the contract surface without needing class-specific
state. See `tests/harness/test_use_lay_on_hands.py` for the pattern.

**The CI workflow** (`.github/workflows/test-harness.yml`) runs the
suite on every push to `main`/`dev` and every PR against them. A
regression fails the workflow before merge, not in production.

**Update the coverage catalog.** Every test change — add, remove,
rename, or material assertion shift — also updates
[`docs/test-harness-coverage.md`](docs/test-harness-coverage.md) in
the same commit. That file is the navigable index of what each test
asserts; it's expected to stay in sync with the suite. Bump the
total-test-count line at the top after running
`python3 -m pytest tests/harness/ -q` so the header tracks reality.

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
