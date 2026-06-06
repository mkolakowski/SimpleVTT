# Auras — Phase 5 sub-plan

**Status:** ⚪ proposed (planning only)
**Parent:** [full-feature-automation.md](full-feature-automation.md) Phase 5 (P5 aura tick).
**Goal:** Build a **per-turn aura tick** (`_tick_auras`) that, on a turn
advance, applies an aura-emitter's effect to the creatures in its radius
— damage (Storm Aura desert), temp HP / heal (Spirit Totem bear, Elder
Champion, Storm Aura tundra), or a save-or-condition (Avenging Angel) —
so the cluster of announce-only aura features auto-apply each round, each
verified by a harness test that asserts the applied state after a turn
advance.

---

## 1. What already works

All in `app/routes/tabletop_routes.py`.

### A. The turn-advance hook (where the tick lives)
Turn advancement is **client-driven**: the GM mutates `turn_index` and
PUTs the whole battle state to `PUT /api/campaign/{cid}/battle`
(`update_battle`, line 71072). The server detects the change
(`_prev_turn != _new_turn`, line 71350) and already fires per-turn hooks
there — **Heroism's start-of-turn temp-HP re-grant** (71359-71409, reads
`effects.heroism_temp_hp_amount` off the new active combatant's buffs)
and the **end-of-turn repeated-save auto-fire** for the combatant whose
turn just ended (71411+). `_tick_auras` hooks into this same block.

### B. Distance / radius
- `_distance_ft_between_chars(db, campaign_id, a_id, b_id)` (line 2485) →
  feet between two PCs' tokens on the active map (Chebyshev "5-5-5" for
  square grids via `_distance_ft_between_points`, line 2335). Returns
  `None` off-grid / when a token is missing, and `0.0` for self.
- **Precedent:** `_aura_of_protection_bonus` (≈ line 29473) walks
  combatants, gates on level/consciousness, and uses
  `_distance_ft_between_chars` with a **"None → assume in range"**
  fallback for off-grid narrative scenes. The aura tick reuses this
  exact pattern.
- Caveat: the distance helper resolves PC tokens by `char_id`. NPC
  combatants carry `source_token_id`; computing NPC↔anyone distance needs
  a combatant-position helper (extend or add one in P5.1).

### C. Apply helpers (reused, not reinvented)
- `_grant_temp_hp(db, cid, combatant, amount, source=…)` (line ≈ 6675) —
  RAW non-stacking temp HP; PC sheet / NPC volatile; broadcasts.
- `_apply_damage_to_combatant(...)` / `_apply_heal_to_combatant(...)` —
  the resistance/temp-HP-aware damage + heal pipeline.
- `_install_buff_on_combatant_id(...)` — condition install (immunity-gated).
- `_resolve_feature_save(...)` (Phase 3) — for save-on-enter auras
  (Avenging Angel).

---

## 2. Target features (the aura backlog)

| Feature | Endpoint | Aura | Tick effect | Today |
|---|---|---|---|---|
| Storm Aura — Desert | `use_storm_aura` | 10 ft | each OTHER creature takes `2+tiers` fire | announce-only |
| Storm Aura — Sea | `use_storm_aura` | 10 ft | one creature: Dex save or `1d6+tiers` lightning | announce-only |
| Storm Aura — Tundra | `use_storm_aura` | 10 ft | one creature gains `2+tiers` temp HP | announce-only |
| Spirit Totem — Bear | `use_spirit_totem` | 30 ft | allies in range gain `5+druid lv` temp HP (re-grant) | summon-only (P4.2) |
| Elder Champion | `use_elder_champion` | 10 ft | self heal 10 at start of turn | announce-only |
| Avenging Angel | `use_avenging_angel` | 30 ft | creature entering / starting turn: WIS save or frightened | announce-only |

Two timing models:
- **Owner-turn-start, affects-others** (Storm Aura, Spirit Totem bear,
  Elder Champion self-heal): fires when the *owner* becomes the active
  combatant. This is the common case and the v1 scope.
- **Subject-turn-start / on-enter** (Avenging Angel): fires when a
  *non-owner* starts its turn inside the aura. Layer on after the
  owner-turn model works.

---

## 3. Design

### 3a. Aura as a buff on the emitter
An active aura is a buff on the emitter combatant carrying an `effects`
schema the tick reads:
```
effects.aura = {
  "radius_ft": 10,
  "affects": "enemies" | "allies" | "others" | "self",
  "on": "owner_turn_start",        # v1 timing
  # exactly one effect payload:
  "damage": {"expr": "2", "type": "fire"},   # flat or dice
  "temp_hp": 7,
  "heal": 10,
  "save": {"ability": "WIS", "dc": 15, "condition": <cond-shape>},
  "source": "storm-aura-desert",
  "label": "Storm Aura (Desert)",
}
```
The activating endpoint installs this buff (1-minute / feature duration);
the tick consumes it each round. Mirrors how Phase 2/3 activated features
install a rider buff and let a hot-path loop apply it.

### 3b. `_tick_auras` (the primitive)
Called from the turn-advance hook (after the Heroism block, line ≈ 71409):
```
_tick_auras(db, campaign_id, state, active_combatant) -> None
```
- The aura **owner** is `active_combatant` (owner-turn-start model). Walk
  its buffs for an `effects.aura`.
- For each aura, select the subjects: every other combatant, filtered by
  `affects` (ally/enemy via the PC-vs-NPC / faction heuristic the codebase
  already uses) and by `radius_ft` (distance helper; off-grid → all-in-init
  fallback, mirroring Aura of Protection).
- Apply the payload via the reused helpers (`_apply_damage_to_combatant`
  / `_grant_temp_hp` / `_apply_heal_to_combatant` / `_resolve_feature_save`),
  broadcast a `feature_used` summary line.
- Idempotency: the tick fires once per owner-turn (the hook already fires
  once per `turn_index` change).

### 3c. Faction / "affects" resolution
"Allies vs enemies" — reuse the existing PC-vs-NPC split (PCs have
`char_id`, NPCs `token_template_id`) as the v1 faction heuristic
(emitter's side = same kind), the same simplification Aura of Protection /
Countercharm already make. A GM-supplied target list can override later.

---

## 4. Phased implementation

1. **P5.1 — `_tick_auras` substrate (M). ✅ shipped v2.99.425.** Built
   `_tick_auras` + `_apply_aura_payload` (temp_hp / heal / damage),
   wired into the `PUT /battle` turn-advance hook. Range uses
   `_distance_ft_between_chars` (PC↔PC) with the off-grid/NPC "all-in-init"
   fallback. Proven with a synthetic aura buff + a turn advance. (A
   fully NPC-aware combatant-distance helper for on-grid NPC auras is a
   follow-up — v1 uses the documented fallback.)
2. **P5.2 — Storm Aura (M). ✅ shipped v2.99.426 (Desert).** Desert
   installs a `storm-aura` aura buff (fire `damage`, `affects: others`,
   10 ft) the tick applies each barbarian turn. Sea (one creature, Dex
   save) + Tundra (one chosen creature temp HP) are single-target
   *choices*, not auto-tick-all — they stay announce-only (a per-turn
   single-target endpoint could automate them later).
3. **P5.3 — Spirit Totem bear ongoing re-grant (S).** Install the aura
   buff so the bear's temp HP re-grants each turn (closes the P4.2 defer).
4. **P5.4 — Paladin Lv 20 auras (S-M).** Elder Champion self-heal,
   Avenging Angel frightened-on-enter (the subject-turn-start model +
   `_resolve_feature_save`).

---

## 5. Test contract

Each retrofit: put the emitter + subjects in a battle (`PUT /battle`,
with token positions when the radius matters), activate the aura, then
advance the turn (`PUT /battle` with a new `turn_index`) and assert the
**applied state** — the in-range subject's HP dropped / temp HP rose /
condition installed, AND an out-of-range subject was untouched. Off-grid
(no positions) asserts the all-in-init fallback fired.

---

## 6. Risks & guards

- **Hot path:** the tick runs on every turn advance. Keep the
  combatant walk + distance checks cheap; one pass over the init list.
- **Double-apply:** the hook fires once per `turn_index` change — don't
  also tick on the buff-duration decrement. One tick per owner-turn.
- **Off-grid fallback:** when token positions are absent, "all in init"
  can over-apply a damage aura. Mirror Aura of Protection's documented
  fallback and surface it in the broadcast so the GM can adjudicate.
- **Faction heuristic:** PC-vs-NPC is a simplification (charmed allies,
  summoned creatures, mixed parties). Acceptable v1; a GM target-list
  override is the escape hatch.

---

## Related

- [full-feature-automation.md](full-feature-automation.md) — parent plan (P5).
- [temp-hp-and-bonuses.md](temp-hp-and-bonuses.md) — Phase 4; the tick
  reuses `_grant_temp_hp` + the temp-HP damage pipeline.
- [feature-saves.md](feature-saves.md) — Phase 3; P5.4 reuses
  `_resolve_feature_save` for on-enter saves.
- `update_battle` turn-advance hook (≈ 71346), `_distance_ft_between_chars`
  (2485), `_aura_of_protection_bonus` (≈ 29473), `_grant_temp_hp`,
  `_apply_damage_to_combatant`, `use_storm_aura`, `use_spirit_totem` —
  the reference implementations.
- `docs/test-harness-coverage.md` — grows with each retrofit.
