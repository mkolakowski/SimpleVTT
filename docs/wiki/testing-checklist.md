# Testing checklist

> **Living doc.** Every commit appends a per-version entry below. Read this before declaring a session done; write to this before pushing the next commit.

This file is the **per-change verification log**. It pairs with two other documents:

- [`docs/test-harness-coverage.md`](../test-harness-coverage.md) — a navigable catalog of what the harness suite already asserts. Source of truth for **"is this contract covered by an automated test?"**.
- [`CHANGELOG.md`](../../CHANGELOG.md) — what changed in each version. Source of truth for **"why was this version cut?"**.

This file's job is **"what do I need to check after pulling this version?"** — the shorter list of manual click-throughs, harness runs to spot-check, and regression watches that aren't expressible as a single harness assertion.

## Standing checklist (run on every commit)

The CLAUDE.md per-commit rule covers most of this, but here's the consolidated list so a new session can follow it without cross-referencing.

1. **`APP_VERSION` bumped** in `app/version.py` and matches the new CHANGELOG entry.
2. **README version badge** matches.
3. **CHANGELOG entry** has the `## [X.Y.Z] - YYYY-MM-DD — "Fun Name"` header, **Schema version**, **Commit summary**, **Description**, and at least one categorised change list. Fun name is in straight double quotes and not recycled from a prior release.
4. **Git commit landed** with the `X.Y.Z — "Fun Name" — <one-line summary>` subject convention.
5. **Pushed to `origin/main`** immediately after the local commit.
6. **Container rebuilt:** `docker compose up -d --build app`.
7. **`/version` poll** confirms the new `APP_VERSION` is live on `http://localhost:8013`.
8. **Per-commit harness:** at minimum run the test for any endpoint/feature touched by this commit (e.g. if you touched `/cast_spell`, `python3 -m pytest tests/harness/test_cast_spell_*.py -q`).
9. **Doc surfacing** (if this commit touched any file under `docs/` or any repo-root doc): verify the doc is reachable from `/wiki`. New entries need three updates: allowlist (if applicable), `wiki.html` landing-page row, `docs/wiki/README.md` row. Plus a per-slug harness smoke test for new `_DOC_ALLOWLIST` entries.
10. **End-of-session sweep:** `python3 -m pytest tests/harness/ -q` from the repo root. Expect 658/658 pass (per v2.99.6 — flips when new tests land). Suite runtime ~17 min after v2.99.6 autouse fixture; budget accordingly.

## Per-version verification log

The most recent version is at the top. **Append new entries above older ones.** Each entry should follow the [template at the bottom](#template-for-future-entries).

### v2.99.9 — "The Spotter on the Shore"

**Scope:** Land the Phase 1.5 follow-up filed by v2.99.7 — three harness tests at `tests/harness/test_monster_sheet_init.py` codifying the monster-sheet contract so a future regression breaks CI before it breaks manual click-through.

**Automated coverage:**

- `test_monster_sheet_page_exposes_globals` — GETs the monster sheet page, asserts `window.IS_MONSTER_SHEET = true;`, `MONSTER_NAME` populated, `MONSTER_COMBATANT_ID` present.
- `test_monster_roll_attributes_to_actor_name` — POSTs `/roll` with `skip_roll_state: true` + `actor_name`, asserts the broadcast carries `no_char_attribution: true` + `actor_name` + `char_name: null`.
- `test_monster_sheet_strike_routes_to_npc_attack` — POSTs `/npc_attack` with the v2.99.7 Strike body shape, asserts 200 + `weapon_attack` broadcast with `is_npc_attack: true` + `caster_combatant_id` set.

**Manual verification:** None required — pure test addition. The v2.99.7 click-through steps stay the v1 verification path (they exercise things harness can't reach, like the multi-target picker UI and the uplift modal suppression).

**Regression watch:**

- If a future commit edits `monster_page.html`, test 1 fires fast — the three globals are the contract.
- If a future commit refactors `/roll`'s attribution path, test 2 fires before any monster-sheet user sees mis-attribution.
- If a future commit changes `/npc_attack`'s body shape or broadcast shape, test 3 fires.

**Filed for follow-up:**

- Playwright UI test in `tests/harness_ui/` that exercises the actual click (button → fetch → broadcast). Out of scope for the harness layer; needs the visual-regression-harness scaffold.
- Phase 2 monster sheet (Spells fieldset un-gate, legendary/lair actions as first-class buttons) still pending — when it ships, append tests for the new mechanic to this file.

---

### v2.99.8 — "The Pre-Flight Card"

**Scope:** Add `docs/wiki/testing-checklist.md` (this file) as a per-version verification log.

**Automated coverage:**

- `tests/harness/test_wiki.py::test_wiki_home_renders` extended with one assertion (`/wiki/testing-checklist` is in the landing page response) so a future regression that removes the table row gets caught.

**Manual verification:**

1. Browse to `http://localhost:8013/wiki` → "Available guides" table includes a "Testing checklist" row linking to `/wiki/testing-checklist`.
2. Click the link → page renders with the standing checklist, per-version log, and template.

**Regression watch:**

- `docs/wiki/README.md`'s table row stays in sync — if a future contributor removes the doc, both indexes need updating.

**Filed for follow-up:**

- None.

---

### v2.99.7 — "The Monster Picks Up the Sword"

**Scope:** Monster init-tracker sheet now supports click-to-roll for ability/save/skill checks and Strike attacks. Routes Strikes to `/npc_attack` and rolls to `/roll` with `actor_name + skip_roll_state` so attribution lands on the monster.

**Automated coverage:** None new — Phase 1 ships manual-verified per the planning question. `tests/harness/test_monster_sheet_init.py` is filed for Phase 1.5 follow-up.

**Manual verification (GM browser session on the demo campaign):**

1. Log in as `demo-gm@example.com` at `http://localhost:8013`.
2. Open the tabletop, ensure an NPC is in the init tracker (the demo seeds bandits).
3. Click the **📋 Sheet** button on the NPC row → drawer slides in with the full sheet shell.
4. Verify the **Abilities** / **Saving Throws** / **Skills** / **Attacks** fieldsets render; **Spells** / **Resources** / **Class** / **Multiclass** / **Inventory** / **Features** / **Notes** are hidden (gated by `is_monster_sheet`).
5. Click any **ability** button (e.g. **STR**). Roll toast fires; roll-log card attributes to the **monster's name** (NOT the GM's first owned PC).
6. Click any **save** and any **skill** button — same attribution path.
7. Open an Attack row's chevron and confirm the **+N to-hit chip** renders (was empty pre-v2.99.7).
8. Click **🗡 Strike** on any attack:
   - Multi-target picker opens (canvas crosshair if the tabletop window is the parent, modal picker otherwise).
   - Pick a target → `/npc_attack` fires → chat card shows a `weapon_attack` broadcast with the monster as the attacker.
9. **No-context Strike:** open the monster sheet directly via URL with no `?combatant_id=` (e.g. `http://localhost:8013/campaign/1/monster-template/2/sheet`). Click 🗡 Strike → toast warns *"Open this monster from the initiative tracker to strike…"* and no request fires.

**Regression watch:**

- **PC sheets unaffected.** Open a PC sheet (`/campaign/1/character/<id>`). Click any ability/save/skill button → roll attributes to the PC (not via `actor_name`), `character_id` is in the request body, no `IS_MONSTER_SHEET` console errors.
- **Strike on a PC sheet** still POSTs to `/attack` (PC endpoint), not `/npc_attack`. The uplift modal (Divine Smite, Sneak Attack) still pops for eligible PCs.
- **Attack bonus chip on PC sheet** still renders (the fallback chain only got broader, not narrower).
- **`monster_template_sheet_page` route** still serves with `?combatant_id=tok_xyz` carrying live HP overlays.

**Filed for follow-up:**

- `tests/harness/test_monster_sheet_init.py` — exercise the strike + ability button broadcasts.
- Phase 2: un-gate the Spells fieldset on monster sheets + wire to `/npc_cast_spell`.
- Phase 2: legendary / lair actions as first-class buttons (new projection field in `_monster_template_to_sheet`).
- Phase 2: per-combatant `roll_state` so monster sheet rolls honor adv/disadv.

### Template for future entries

Copy this block, fill it in, and place it ABOVE the most-recent existing entry.

```markdown
### v<X.Y.Z> — "<Fun Name>"

**Scope:** <one-or-two-sentence summary — what surfaces or contracts changed>

**Automated coverage:** <list new tests in `tests/harness/`, or "none — manual verification only">.

**Manual verification:**

1. <Step 1 — concrete enough that a new contributor can run it cold>
2. <Step 2>
3. <Step 3>

**Regression watch:**

- <What to keep an eye on in adjacent features that might be affected>
- <Existing surface that should be unchanged but lives close to what was edited>

**Filed for follow-up:**

- <Test you didn't write, mechanic you punted on, edge case for next commit>
```

## When to add an entry

**Always add** — every commit lands an entry, even doc-only or refactor-only commits. The entry can be a single line on "no behavior change, no manual test needed" — that's still valuable because it documents the **decision to skip**.

**Entry length guide:**

- **PATCH bumps:** 3–6 lines. Often just the manual verification step you ran before committing.
- **MINOR bumps (new feature):** Full template. Manual verification AND regression watch.
- **MAJOR bumps:** Full template + an explicit "operator-facing changes" section under Regression watch (config / schema / breaking API).

## Why this file exists, in one paragraph

A session at v2.97.77 ended with 99.85% suite pass and one unexplained NPC-concentration flake that took four commits to chase. The flake wasn't dice — it was a state leak from earlier tests that was invisible until a full-suite run. The lesson: most regressions don't fail loud at commit time; they fail quiet in the third unrelated test that runs after them. This file is the discipline that catches those by forcing every commit to **declare what it verified, both automated and by-hand**, so a future session reading the log can spot the regression class before it cascades.
