# Forced movement, speed buffs & summons — Phase 6 sub-plan

**Status:** ⚪ proposed (planning only)
**Parent:** [full-feature-automation.md](full-feature-automation.md) Phase 6 (P6 movement + P7 summons).
**Goal:** Build the two heaviest remaining primitives — **server-side
forced movement** (`_force_move`) + **speed buffs**, and a
**summon-token primitive** (`_summon_companion`) that creates a real
combatant with its own token + init slot — so the ~dozen push/pull and
summon features auto-apply instead of being GM-dragged / GM-placed. Each
retrofit verified by a harness test that asserts the moved token position
/ the new combatant, not just a broadcast.

---

## 1. What already works

### A. Tokens + positions
- `Token` (`app/models.py:349`) carries `x` / `y` (world coords),
  `map_id`, `character_id` (PC) / `token_template_id` (NPC), `size`,
  `team` ("hero"/"villain"/"neutral"). Position lives **only on the
  Token row** — a battle-state combatant links via `source_token_id` /
  `char_id` and has **no x/y of its own**.
- **Move:** `POST /token/{id}/move` (`move_token`, line 10418) mutates
  `token.x/y` server-side, computes distance via
  `_distance_ft_between_points`, enforces the **speed cap** (reads
  `effective_speed_walk` + `economy.dash_bonus_ft`, 409 over-cap),
  fires **opportunity-attack** checks, and broadcasts `token_move`
  (`{id, x, y, from_x, from_y, distance_ft, …}`).
- **Place / delete:** `place_character_token` (line 12473) creates a PC
  Token row + broadcasts `token_add`; `_token_dict` (line 13660) is the
  projection; `token_delete` removes one. All GM-driven.

### B. Speed engine
- `app/content/effective_speed.py`: `effective_speed_walk(combatant)` =
  `base speed_walk − Σ effects.speed_reduction_ft` (clamped ≥ 0). Read by
  the move-endpoint cap. **`speed_bonus_ft` is not read anywhere** —
  filed (Longstrider +10, Haste ×2, Eagle Totem dash, Tempestuous Magic
  fly).

### C. Forced-move precedent (announce-only)
- Open Hand Technique push (`use_open_hand_technique`, line 37393) and
  Pushing Attack (`use_pushing_attack`, line 43127) compute the save +
  surface `push_authorized` / `push_max_ft: 15` — **the GM drags the
  token**. No server-side forced move. Thorn Whip / Gust / Repelling
  Blast / Thunderwave aren't implemented.

### D. Summon precedent (announce-only)
- No server path creates a Token + combatant for a summon. Manifest Echo,
  Pact-of-the-Chain familiar, etc. are data/lore only. The only
  server-side combatant *synthesis* is the NPC auto-add when a
  template-linked token is hit mid-battle (line 18012) — but that reuses
  an existing Token; it doesn't create one.

---

## 2. Target features

| Group | Features | Primitive |
|---|---|---|
| **Push / pull** | Pushing Attack, Open Hand push, Thorn Whip (pull 10 ft), Gust (push 5 ft), Repelling Blast (push 10 ft), Thunderwave (push 10 ft) | `_force_move` |
| **Speed buff** | Longstrider (+10), Haste (×2), Eagle Totem (Dash bonus), Tempestuous Magic, Step of the Wind | `speed_bonus_ft` |
| **Summon** | Spiritual Weapon, Find Familiar, Steel Defender (Battle Smith), Ranger's Companion, Conjure Animals, Flaming Sphere, Bigby's Hand, Drake Companion | `_summon_companion` |

---

## 3. Design

### 3a. Speed bonuses (the small win, ship first)
Extend `effective_speed_walk`: `base + Σ effects.speed_bonus_ft −
Σ speed_reduction_ft` (clamped ≥ 0), plus a `speed_multiplier` for Haste
(×2). Then Longstrider / Haste / Eagle Totem install a buff carrying the
key; the move-endpoint cap reads it for free. Pure additive — one read
site, no new endpoint.

### 3b. `_force_move` (server-side forced movement)
```
POST /api/campaign/{cid}/force_move
body: {combatant_id | token_id, distance_ft, direction: "away_from"|"toward"|"dx,dy",
       source_combatant_id?, source_feature}
```
- Resolve the target's Token + the source's position (for away/toward
  direction). Compute the destination (clamp to map bounds; grid-snap).
- Mutate `token.x/y`, broadcast `token_move` (reuse the existing shape).
- **Does NOT** consume the target's movement or hit the speed cap (forced
  move is involuntary). **Does** run the OA check the move endpoint
  already has (leaving reach can trigger OAs — RAW: forced move doesn't,
  but Sentinel/etc. are edge cases; v1 can skip OA on forced move and
  note it).
- Push features call it after their save resolves (on a fail).

### 3c. `_summon_companion` (the heaviest — P7)
```
_summon_companion(db, cid, *, owner_char_id, template, name, x, y,
                  initiative, lifetime) -> combatant
```
- Create a `Token` row (NPC, `token_template_id` from a small companion
  template registry, position near the owner) + broadcast `token_add`.
- Synthesize a combatant dict (AC/HP/speed from the registry) and add it
  to the active battle state (init slot — share the owner's initiative or
  a supplied one) + broadcast `battle_update`.
- **Lifetime:** tie to the owner — a `summoned_by` marker + a duration;
  dropped on the owner's death, on rest, or on the spell ending (a
  teardown helper removes the Token + combatant). v1: drop on rest +
  manual dismiss endpoint.
- Companions reuse the existing damage/HP pipeline (they're real
  combatants), so attacking/healing them works for free.

---

## 4. Phased implementation

1. **P6.1 — speed buffs (S). ✅ shipped v2.99.431.** `effective_speed_walk`
   now reads `speed_bonus_ft` (additive) + `speed_multiplier` (Haste ×2);
   Haste + Longstrider install the keys. Unit-tested. (The client JS speed
   mirror is a cosmetic follow-up — the server move-cap is authoritative.)
2. **P6.2 — `_force_move` + endpoint (M). ✅ shipped v2.99.432
   (primitive + endpoint).** `_combatant_token` + `_force_move` (mutates
   the target token's `x/y` along the source→target axis, broadcasts
   `token_move forced:true`, bypasses speed cap + OA) + the `/force_move`
   endpoint. Tested directly (push 15 ft → token moves 3 cells). Pushing
   Attack (v2.99.433) rolls the STR save server-side + force-moves the
   target 15 ft away on a fail.
3. **P6.3 — more forced movers (S-M). ✅ substantially done.** Open Hand
   push ✅ shipped v2.99.434 (force-moves the target 15 ft on a failed
   STR save). Thorn Whip ✅ shipped v2.99.435 (new cantrip endpoint:
   melee spell attack → pull 10 ft toward the caster on a hit; first
   `_force_move(pull=True)` retrofit). Thunderwave ✅ shipped v2.99.436
   (new L1 spell endpoint: multi-target CON save AoE → each failed save
   takes 2d8 thunder + pushed 10 ft away; first *multi-target*
   forced-move retrofit). Remaining nice-to-haves: Gust (push). Repelling
   Blast already has its own bespoke push from v2.99.90 — a candidate to
   consolidate onto `_force_move` later.
4. **P7.1 — `_summon_companion` + a companion registry (L). 🟠 in
   progress.** ✅ shipped v2.99.437: the `_summon_companion` /
   `_dismiss_companion` primitives + a `_COMPANION_TEMPLATES` registry
   (wolf / spiritual-weapon / flaming-sphere) + the `/summon_companion`
   and `/dismiss_companion` endpoints. The summon is a real combatant
   (HP/AC ride on the combatant dict; `_read_target_ac` now honors a
   combatant-dict `ac`), so it reuses the damage/HP pipeline — proven by
   a Thunderwave-damages-the-summon test. ✅ Spiritual Weapon retrofit
   shipped v2.99.438 (`/use_spiritual_weapon` summons the floating-weapon
   combatant + makes the melee spell attack for 1d8+mod force on a hit;
   first real summon retrofit). ✅ rest-teardown shipped v2.99.439
   (`_teardown_summons_for_owner` drops the owner's summons on a long
   rest — combatant + token; a short rest leaves them). **P7.1 done.**
5. **P7.2 — more summons (L, ongoing). 🟠 in progress.** Find Familiar
   ✅ shipped v2.99.440 (`/cast_find_familiar` stands up the tiny
   non-combat `familiar` companion in a chosen animal form). Remaining:
   Steel Defender, Ranger's Companion, Conjure Animals.

---

## 5. Test contract

Forced move: place the target's Token, force-move it, assert the Token's
`x/y` changed by the expected feet (via `token_move` / a token read).
Speed buff: install the buff, assert the move endpoint now accepts a move
that previously 409'd over the cap. Summon: call the summon endpoint,
assert a new combatant in `battle_update` + a new Token in `token_add`,
then attack it and assert its HP drops (it's a real combatant).

---

## 6. Risks & guards

- **New write surfaces:** `_force_move` mutates Token rows and
  `_summon_companion` creates them — both server-authoritative writes the
  GM didn't initiate. Gate on battle-active + membership; broadcast with
  `force_gm_sync` so the GM's canvas updates.
- **Map bounds / overlap:** clamp forced-move destinations to the map;
  don't stack a summon on an occupied square (offset to the nearest free
  cell, or just place adjacent to the owner — v1 simple offset).
- **Companion lifecycle leaks:** a summoned Token + combatant that's
  never torn down clutters the board. Always pair a summon with a
  teardown path (rest hook + dismiss endpoint), and log it.
- **Off-grid scenes:** forced move + summons need a map with positions.
  Off-grid (no active map) → fall back to announce-only (the current
  behavior) and surface it.
- **OA on forced move:** RAW forced movement doesn't provoke; v1 skips
  the OA check on `/force_move` (the move endpoint's OA logic is opt-in).

---

## Related

- [full-feature-automation.md](full-feature-automation.md) — parent plan (P6 + P7).
- [auras.md](auras.md) — Phase 5; `_summon_companion` reuses the same
  combatant + battle-state shape the aura tick walks.
- `move_token` (10418), `effective_speed_walk`
  (`app/content/effective_speed.py`), `_distance_ft_between_points`
  (2335), `_token_dict` (13660), `place_character_token` (12473),
  the NPC auto-add (18012), `use_pushing_attack` (43127) — the reference
  implementations.
- `docs/test-harness-coverage.md` — grows with each retrofit.
