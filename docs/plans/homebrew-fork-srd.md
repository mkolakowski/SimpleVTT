# Fork & tweak SRD mechanics as homebrew

**Status:** 🟠 partial · **Phase 1 shipped v2.569.0** (fork-SRD + revert endpoints, all types, variant/override). **Phase 2a shipped v2.570.0** (the GM editor *write path* — a GM-gated, campaign-scope-forced edit endpoint that tweaks a forked record's mechanics). Remaining: **Phase 2b** (the editor UI panel in campaign settings) and **Phase 3** (browse-and-fork affordance in the pickers).

Let a **GM copy any shipped SRD mechanic into their campaign's homebrew and
tweak it** — change Fireball's damage, give a monster an extra action, bump
a magic item's bonus — without hand-authoring JSON and without touching the
shipped SRD library. Today the homebrew suite can import non-SRD content
from Open5e and duplicate *existing homebrew*, but it **explicitly refuses
to clone shipped SRD records**, and its rich editor is admin-only. This
plan closes that: a GM-facing "Fork to homebrew" flow + an in-campaign
editor, riding the loader's existing override priority.

---

## Substrate as-built (verified v2.568.3)

The homebrew engine is mature; the gap is a missing *source* (SRD) and a
missing *audience* (GM, not admin) for the copy path — not new storage.

- **Two-tier file loader** — `app/local_content.py`. `resolve(slug, type,
  campaign_id)` walks **campaign-`N` homebrew → global homebrew → shipped
  SRD** and returns `(record, source_label)`. So a campaign-scoped homebrew
  record with the **same slug** as an SRD record transparently **shadows**
  it for that campaign. `write_homebrew` / `delete_homebrew` validate
  against the per-type Pydantic model and write `HOMEBREW_ROOT/<system>/
  <scope>/<type>/<slug>.json` atomically; `search()` lists a tier.
- **Cast path already honors overrides** — `/cast_spell` reads the caster's
  inline sheet spell then *enriches* it from `resolve(_slug, campaign_id)`
  (`test_cast_homebrew_spell.py`). So a same-slug campaign fork of Fireball
  is picked up by every sheet that references `fireball` — no sheet edits.
- **Admin CRUD** — `app/routes/homebrew_routes.py` (`/admin/homebrew`,
  `require_admin`): list / new / edit / delete via a `payload` JSON built by
  an Action editor (`app/templates/admin/homebrew/list.html`), plus
  `import/open5e/<slug>` (network, **non-SRD**) and `import/upload` (paste/
  file). **Admin-gated — GMs can't reach it.**
- **GM-facing campaign homebrew** — `app/routes/tabletop_routes.py`:
  `/api/campaign/{id}/homebrew/export|template|import` (GM-gated, surfaced
  in `campaign_settings.html`) for JSON round-trips, and
  `_clone_homebrew_record` + per-type clone routes (`/campaign/{id}/
  custom-feats|custom-backgrounds|custom-races/{slug}/clone`). **The clone
  helper raises 404 unless the source is `local-homebrew`** — i.e. it
  *deliberately won't clone shipped SRD content*, and only feats /
  backgrounds / races have clone routes.
- **SRD-only guardrail** — `tests/harness/test_srd_provenance.py`
  (v2.568.3): the shipped tree must stay 100% `source:"srd"`. **Forks must
  land in the homebrew tier, never `app/data/local/`** — this plan is
  designed to keep that gate green.

### The gap, exactly

1. No path to copy a **shipped SRD** record into homebrew (clone refuses
   SRD; Open5e import is the wrong, network, non-SRD source).
2. The capable editor is **admin-only**; GMs have JSON round-trip + 3
   narrow clone routes.
3. Clone covers only feats / backgrounds / races — not spells / monsters /
   items / conditions / class & subclass features.

---

## Design

### Two fork modes (both ride the loader as-is)

- **Override** — write the fork at `campaign-N` scope **with the same
  slug**. The campaign's version shadows the SRD record everywhere
  (`resolve` priority + cast enrichment), so "tweak Fireball" means Fireball
  itself behaves differently *in this campaign*; revert = delete the fork.
- **Variant** — write the fork with a **fresh slug** ("copy-of-fireball",
  name "Fireball (Homebrew)"), a distinct new mechanic the GM adds to
  sheets / encounters explicitly. (This is what `_clone_homebrew_record`
  already does for homebrew→homebrew; we extend the *source* to SRD.)

The GM picks the mode at fork time; default **Variant** (non-destructive —
override silently changes existing behavior and is the sharper tool).

### Provenance

Forked records carry `source: "custom"`, `scope: "campaign-N"`, and an
`_attribution` noting "Tweaked from SRD <slug>" + the forking user. The
loader's `_label_for_record` already maps `source=="custom"` →
`"local-custom"`, so the UI can badge forks as *"tweaked from SRD"* distinct
from both pristine SRD and net-new homebrew. `test_srd_provenance` is
unaffected — forks never enter the shipped tree.

---

## Phases

1. **Phase 1 — Fork-SRD endpoint (all types).** ✅ **Shipped v2.569.0.**
   `_fork_record_into_campaign` + `POST /api/campaign/{id}/homebrew/fork`
   (`{type, src_slug, mode}`) accept a **shipped SRD** source (or an
   inherited global homebrew), writing a campaign-scoped homebrew copy in
   the chosen mode (override = same slug, shadows SRD for the campaign /
   variant = fresh `copy-of-…` slug), `source:"custom"`, GM-gated, for
   **every** content type. Companion `DELETE /api/campaign/{id}/homebrew/
   {type}/{slug}` reverts (un-forks). 409 on re-overriding an existing
   campaign fork; the shipped tree is never written (provenance gate stays
   green). Covered by `tests/harness/test_homebrew_fork_srd.py`.
2. **Phase 2 — GM-facing editor.**
   - **Phase 2a — write path. ✅ Shipped v2.570.0.** `POST /api/campaign/
     {id}/homebrew/{type}/{slug}/edit` takes the full record JSON, **forces
     `scope=campaign-N`** + `source:"custom"` (a GM can't escalate to global
     or write the shipped tree), validates via `write_homebrew`, and is
     GM-gated with a URL-slug/record-slug match check. Create-or-update, all
     content types. The admin editor's payload shape is just the record JSON
     (a `<textarea name="payload">`), so 2b's UI shares this contract.
     Covered by `tests/harness/test_homebrew_fork_srd.py`.
   - **Phase 2b — editor UI (unstarted).** A campaign-settings "Homebrew
     workshop" panel: list the campaign's `source:"custom"` records, open one
     in a JSON editor pre-filled via `/api/content/{type}/{slug}?campaign_id=`,
     Save → the 2a endpoint, plus the Phase 1 fork form + revert. Playwright
     smoke.
3. **Phase 3 — Browse-and-fork affordance.** A "Fork to homebrew" button
   where GMs already see SRD mechanics — the spell picker
   (`spell_picker.js`), monster page (`monster_page.html` /
   `beast_picker.js`), item list — calling the Phase 1 endpoint then opening
   the Phase 2 editor on the new record. Forks list in the campaign's
   homebrew view with the *"tweaked from SRD"* badge + a "revert" (delete)
   for override forks.

---

## Test contract

- **Phase 1** (`tests/harness/test_homebrew_fork_srd.py`):
  - Fork a shipped SRD spell (e.g. `fireball`) in **variant** mode → 200,
    a new `campaign-N` homebrew file with a fresh slug, `source:"custom"`,
    name flagged; `resolve(new_slug, campaign_id)` returns the fork.
  - Fork in **override** mode → same slug at `campaign-N`;
    `resolve("fireball", campaign_id)` now returns the homebrew copy while
    `resolve("fireball", campaign_id=None)` still returns pristine SRD
    (other campaigns unaffected).
  - Non-GM caller → 403; unknown `src_slug` → 404; unknown `type` → 404.
  - Covers a non-spell type (monster or item) to prove type-generality.
  - **`test_srd_provenance` still passes** — the shipped tree is untouched
    (assert no file written under `app/data/local/`).
- **Phase 2**: GM edit of a forked record persists (damage tweak round-trips
  via `resolve`); a GM cannot write `global` scope or another campaign's
  scope (403 / forced campaign-N).
- **Phase 3**: UI smoke (Playwright) — fork button → editor opens pre-filled
  → save → the tweaked value resolves.

---

## Non-goals

- **Editing the shipped SRD files** — forbidden by the "SimpleVTT ships SRD
  5.1 content only" rule; forks always go to the homebrew tier.
- **GM writes to `global` scope** — GMs fork to *their* campaign only;
  cross-campaign / global homebrew stays admin (`/admin/homebrew`).
- **A from-scratch visual mechanic builder** — reuse the existing Action/
  field editor; this plan adds the SRD *source* + the GM *audience*, not a
  new editor engine.
- **Auto-balancing / validation of tweaks** — a GM can make Fireball deal
  100d6; that's their table's call (GM is the rules authority).

This doc is surfaced through the wiki at `/wiki/doc/plan-homebrew-fork-srd`.
