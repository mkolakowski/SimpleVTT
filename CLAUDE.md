# SimpleVTT — Claude Code guidelines

## Always update the changelog and version when making changes

**Every commit ships its own version bump.** One conceptually-distinct change = one commit = one version bump = one CHANGELOG entry. No batching unrelated edits into a single release: if you fix three unrelated bugs in a session, ship three commits at e.g. `1.11.1`, `1.11.2`, `1.11.3` — not one commit at `1.11.0` listing all three under `### Fixed`. The only thing that may legitimately span multiple files in a single commit is a single coherent change (one feature, one bug, one refactor) that needs the multi-file edit to be reviewable. Read `CHANGELOG.md` in full at the start of any version-related work — the file contains detailed bump rules and a required entry format in its header section.

**Quick rules:**

- `APP_VERSION` lives in `app/version.py` and follows SemVer. **Pick the highest bump that applies** — every commit bumps at least PATCH:
  - **PATCH** (`0.0.x`) — **the default**. Bumps on every commit, including pure bug fixes, copy tweaks, comment-only edits, refactors with no behavior change, dependency updates, doc edits, etc. There is no such thing as a "no bump" commit.
  - **MINOR** — new backward-compatible feature or additive schema change. (A MINOR bump satisfies the "every commit ships a bump" rule too — you don't bump PATCH on top.)
  - **MAJOR** — breaking API/config/schema change that requires operator action. (Same — replaces the PATCH bump for that release. **Also triggers the changelog-archive rule below.**)
- `SCHEMA_VERSION` (also in `app/version.py`) increments by **+1** for every migration block added to `_apply_inline_migrations()` in `app/database.py`.
- Add a new `## [X.Y.Z] - YYYY-MM-DD — "Fun Name"` section at the **top** of the changelog (below the instructions header). Use today's UTC date. **The "Fun Name" is required** — a short, evocative title (1-4 words, Title Case, in straight double quotes) that captures the spirit of the release. Examples: `"The Uncanny Dodge"` for v2.49.243, `"Frosted Glass"` for v2.49.246, `"The Battleship Cartographer"` for v2.50.0. The fun name's job is to make scanning `CHANGELOG.md` feel like reading release notes for a game, not a manifest — so prefer a flavorful noun phrase ("The Quiet Reactor", "Glass Houses") over a literal restatement ("Add Toggle"). Don't recycle a previous release's name.
- Every entry must include: heading (with fun name), `**Schema version:** N`, `**Commit summary:**`, `**Description:**`, and at least one categorised change list (`### Added`, `### Changed`, `### Fixed`, `### Schema`, etc.).
- Also update the version badge in the first paragraph of `README.md` to match.
- `APP_VERSION_NAME` (also in `app/version.py`) holds the **current release's "Fun Name"** and feeds the in-app version stamp (gated by `SHOW_VERSION_NAME`). **Bump it to the new fun name every release**, alongside `APP_VERSION` — it must match the top CHANGELOG entry's fun name and the git subject. It's part of the single-source-of-truth set in `version.py`.
- Do **not** edit version numbers anywhere else — `app/version.py` is the single source of truth.

**Always create the git commit at the end of the change.** A version bump that isn't committed isn't actually a release — it's just an uncommitted working-tree edit that disappears on the next `git reset` or context loss. After finishing the changes for a version bump (code + version + README + CHANGELOG, plus the harness test required by the harness-discipline rule below), `git add` the affected files and `git commit` them as a single commit. The commit message should match the convention seen in `git log --oneline` — short subject line of the form `X.Y.Z — "Fun Name" — <one-line summary>`, body optional but encouraged for non-trivial changes. The fun name in the subject line **must match** the fun name in the corresponding CHANGELOG entry so a reader scanning `git log` and `CHANGELOG.md` side-by-side sees the same handle on both. Do this even if the user didn't say "please commit" — the per-commit / per-bump rule above already implies a commit happens. If the change is mid-flight (broken tests, half-written feature) say so and don't bump the version yet rather than landing an uncommitted bump. **Never run more than one version bump without committing in between** — if you've bumped to `2.50.0` and want to also ship `2.50.1`, commit `2.50.0` first, then start the next change. The "one bump = one commit" rule is meaningless if multiple bumps stack in the working tree.

**Push every commit to `origin/main` immediately after the local commit lands.** A commit that only lives on the local laptop isn't actually a release — GitHub is the canonical source of truth for collaborators, the CI workflow (`.github/workflows/test-harness.yml`), and anyone scanning the project's commit history. A long backlog of unpushed commits is a coordination failure: collaborators see a stale tip, CI doesn't run, and a laptop crash or `git reset --hard` loses all of them at once. After `git commit` (and the container rebuild — both can happen in parallel), run:

```bash
git push origin main
```

Do this for **every** commit, including doc-only bumps. The "every commit ships a bump" rule above is paired with this one: every bump → one commit → one push. No batching: don't accumulate 5 local commits then push the lot at the end of the session, because if the session ends abruptly (context loss, machine reboot, hook failure) the unpushed commits are stranded. Push as you go.

If the push fails (network blip, auth, non-fast-forward because someone else pushed) investigate before retrying. **Never** use `git push --force` to "fix" a non-fast-forward against `origin/main` — fetch first, see what's upstream, and rebase or merge cleanly. Force-push to `main` overwrites collaborators' work and is one of the few git operations that's genuinely unrecoverable for them. The user must explicitly authorize force-push for it to happen.

The CI workflow at `.github/workflows/test-harness.yml` runs the harness suite on every push to `main` — pushing keeps the regression net hot. Skipping pushes lets a broken main accumulate without the GitHub-side signal.

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

## Every doc must be surfaced through the wiki

The in-repo wiki at `/wiki` is the single discovery surface for every reader-facing document — operator guides, GM how-tos, design plans, reference cards, repo-root docs. When you **create or edit a document** under `docs/`, `docs/plans/`, `docs/wiki/`, or the repo-root doc set (`README.md` / `CHANGELOG.md` / `CLAUDE.md` / `CREDITS.md` / `TODO.md` / `CHANGELOG_v*.md`), check that the doc is reachable through the wiki nav. If it isn't, **add it in the same commit.**

This rule exists because v2.49.59 shipped a ruler/range plan that lived on disk for seven commits before anyone noticed it wasn't reachable via `/wiki` (retro-fixed in v2.49.66). The fix is structural: tie the wiki-surfacing edits to the doc-write commit itself so no doc ever lands invisible.

**The three places that need updates depend on doc type:**

| Doc location | Allowlist (`app/routes/wiki_routes.py::_DOC_ALLOWLIST`) | Landing-page table (`app/templates/wiki.html`) | On-disk index (`docs/wiki/README.md`) |
|---|---|---|---|
| `docs/wiki/<slug>.{md,html}` | **Not required** — served by `/wiki/<slug>` directly, no allowlist needed. | Required — "Available guides" table. | Required — "Available guides" table. |
| `docs/plans/<slug>.md` | Required — slug pattern `plan-<slug>` → `Path("docs") / "plans" / "<slug>.md"`. | Required — "Design plans" table. | Required — "Design plans" table. |
| `docs/<slug>.md` (references) | Required — bare slug → `Path("docs") / "<slug>.md"`. | Required — "References" table. | Required — "References" table. |
| Repo-root docs | Already in the allowlist (`readme`, `changelog`, `claude`, `credits`, `todo`, `changelog-v1`). | Already in "Repo documentation". | Already in "Repo documentation". | 

**Plus the per-slug harness test:**

Every entry added to `_DOC_ALLOWLIST` (the bottom three rows above) needs a smoke test in `tests/harness/test_wiki.py` modeled on `test_wiki_doc_serves_plan` / `test_wiki_doc_serves_ruler_plan` — asserts the slug returns 200, the body contains a recognizable substring from the doc's H1, and the wiki nav menu is injected. Plus add the new slug to `test_wiki_home_renders`'s landing-page assertion list so a future regression that removes the table row gets caught.

**Quick decision tree:**

```
Am I editing a doc under docs/ or a repo-root doc?
├── No  → rule doesn't apply.
└── Yes → Is the doc already reachable via /wiki/...?
          ├── Yes → ship the doc edit alone.
          └── No  → in the SAME commit:
                     1. Add the allowlist row (if applicable per the table above).
                     2. Add the wiki.html landing-page table row.
                     3. Add the docs/wiki/README.md table row.
                     4. Add a per-slug test_wiki_doc_serves_<name> harness test
                        (if applicable per the table above).
                     5. Update the test_wiki_home_renders landing-page assertion.
```

**Status text for new entries.** The landing-page table and `docs/wiki/README.md` both have a Status column. Use the same vocabulary as the existing rows — `✅ shipped`, `🟠 partial`, `⚪ proposed`, `⚪ design only · Phase N unstarted` — so the index reads consistently. Update the status as the underlying work moves through phases.

**When NOT to apply.** Files that aren't reader-facing documents: test files (`tests/`), code (`app/`), config (`docker-compose.yml`, `pytest.ini`, `.env.example`), the homebrew JSON content layer, asset files (images, fonts, demo media), the changelog archive (`CHANGELOG_v1.md` is already surfaced). If you're not sure whether a file is a "doc," ask — the rule of thumb is "would a contributor want to find this from the wiki landing page?" If yes, surface it. If no, skip it.

## Offer "what's next" as multiple-choice questions

When wrapping a commit, presenting candidates for the next piece of work, or surfacing a list of options the user might want to pursue, **use the `AskUserQuestion` tool to format the choices as a multiple-choice menu** rather than embedding the candidates as a Markdown bullet list at the end of a chat response. The user has stated this preference explicitly: bulleted "candidates queued" lists at the end of every commit reply force them to retype their choice in prose, while a multiple-choice picker is one click.

**When to use it:**

- After shipping a version bump, when offering 2–4 follow-up candidates for the next commit.
- When the user has said "what's next?" or similar, and there's more than one reasonable next step.
- When you're about to pick between multiple implementation approaches and want explicit guidance (e.g. "Phase A only" vs. "Full F8" vs. "Phase A + B").
- Whenever you'd otherwise write a closing paragraph like "What's next? Candidates queued: ..." or "Say the word for any of these: ...".
- Single-option follow-ups that surface the top-priority item from [`TODO.md`](TODO.md) — even when there's only one obvious next step, frame it as a multi-choice with the to-do's top-priority item as the recommended option (suffix `(Recommended)`) and 1–3 alternatives (lower-priority to-do items, a "different scope" tweak, or "plan it first"). The picker gives the user a 1-click confirm AND a redirect path, where prose would force them to retype.

**When NOT to use it:**

- Confirmations that don't have alternatives ("Should I commit?" — just commit per the per-commit rule).
- Clarifying questions where the option space isn't enumerable (those stay as free-form text).
- When the user has already chosen what's next and you're mid-implementation.

**Format:**

- 2–4 options. If you have more than 4 candidates, pick the 3–4 highest-leverage ones and mention the rest in the "Other" overflow.
- Lead with the option you'd recommend, suffix the label with `(Recommended)` so the user sees the steer first.
- Use the `header` field for a short chip label (e.g. `"Next bump"`, `"F8 scope"`, `"Approach"`).
- Keep `description` to one short sentence on what that choice triggers.
- One question per AskUserQuestion call unless the choices are genuinely independent (rare).

**Why this exists.** The user told the assistant in this conversation: "when a choice is needed, can you format you response to include a multiple choice". That preference is now durable — every "what's next" reply that lists 2+ candidates should use AskUserQuestion. A trailing prose-bullet list at the bottom of a commit reply is the anti-pattern.

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

## SimpleVTT ships SRD 5.1 content only

The shipped image carries **D&D 5e SRD 5.1 mechanics only** — the
CC-BY/OGL perimeter the codebase's attribution cites. Anything outside
the SRD (Tasha's, Xanathar's, the 2024 PHB, third-party books, table
homebrew) is **not** baked into shipped content; it belongs in the
campaign/operator **homebrew tier**. This keeps the redistribution
license clean and the rules surface predictable.

The content layer has two tiers (`app/local_content.py`):

- **Shipped tier** — `app/data/local/dnd5e/<type>/<slug>.json`, loaded as
  `scope: global`. **SRD-only.** Every record must carry `source: "srd"`,
  `scope: "global"`, and an `_attribution` citing the SRD 5.1 / Open5e.
- **Homebrew tier** — `app/data/homebrew/` (or `HOMEBREW_DATA_DIR`) +
  campaign-scoped DB content, `source: "local-homebrew"`. **This is the
  sanctioned home for non-SRD mechanics** — it overrides the shipped tier
  per-campaign and is never part of the image.

**Two halves, enforced asymmetrically:**

- **"Only SRD mechanics"** — *fully enforced.* `tests/harness/test_srd_provenance.py`
  asserts every shipped record is `source: "srd"` + `scope: "global"` + SRD-
  attributed, and that no homebrew-sourced record leaks into the shipped
  tree. **If you must add a non-SRD spell/feat/monster, put it in the
  homebrew tier — do not add it under `app/data/local/`.** New shipped SRD
  content must keep the provenance fields (the build script
  `scripts/build_srd_content.py` sets them; see its header before ever
  re-running it — it does **not** reproduce the curated `area`/`upcast`/
  scaling fields and will clobber them).
- **"All SRD mechanics implemented"** — *tracked, not unit-asserted.* This
  is a VTT where the GM is the rules authority, so a mechanic counts as
  **supported** when it is automated **or** deliberately GM-narrated — full
  automation of every SRD line is explicitly **not** the bar. Coverage is
  tracked by the SRD audit in [`TODO.md`](TODO.md) +
  [`docs/test-harness-coverage.md`](docs/test-harness-coverage.md), and the
  catalog's **completeness floor** (per-type record counts can only grow,
  never silently shrink) is enforced by `test_srd_catalog_meets_completeness_floor`
  so a destructive content regen / deletion can't quietly drop SRD mechanics.
  When you implement a new SRD mechanic, update the audit; when you find an
  SRD gap, file it there — don't claim 100% automation.
