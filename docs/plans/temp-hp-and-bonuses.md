# Temp HP + roll-bonus completion — Phase 4 sub-plan

**Status:** ✅ shipped (P4.1 → P4.4 complete, v2.99.415–.423)
**Parent:** [full-feature-automation.md](full-feature-automation.md) Phase 4 (P4 + P8).
**Goal:** Build a **temp-HP primitive** (`_grant_temp_hp`) and make the
damage pipeline spend temp HP before real HP (RAW), so the cluster of
announce-only "+temp HP" features auto-apply; then **finish the filed
roll-bonus read-sites** (+AC spells, buff-level save advantage) the
earlier phases left as TODOs — each verified by a harness test that
asserts the applied state (HP / AC / save shape), not just a broadcast.

---

## 1. What already works

All in `app/routes/tabletop_routes.py`.

### HP storage + the damage/heal core
- A combatant's working HP lives in the hub battle-state dict
  (`hp_current` / `hp_max`); a PC also persists HP on the sheet at
  `Character.sheet["hp"]` (`{current, max, temp}`).
- **Temp HP is already a sheet field** (`sheet["hp"]["temp"]`, an int) —
  the Heroism spell hand-codes a grant in `/cast_spell` (≈ line 17291):
  read `hp["temp"]`, `max(existing, new)`, write back, log. **Non-stacking
  (take the higher)** is the RAW rule and the established behavior.
- `_apply_damage_to_combatant` (line 5960) computes `new_hp = max(0,
  hp_cur - applied)` for PCs (line 6112) and NPCs (line 6317) and routes
  PCs through `_apply_hp_change` (death-save state machine). **It never
  touches temp HP.**
- `_apply_heal_to_combatant` (line 6478) clamps `new_hp = min(
  effective_max, hp_cur + heal)` and already reads a buff-driven max
  extension (Aid's `effects.aid_hp_bonus`, line ~6516) — the pattern a
  temp-HP grant should mirror.

### Bonus read-sites that ARE wired
- **AC:** `_read_target_ac` (line 5251) sums `effects.ac_bonus` across the
  target's buffs (Shield of Faith, Evasive Footwork, Glorious Defense,
  Bladesong) + the Defense fighting style (`_pc_defense_ac_bonus`). One
  read site, already correct.
- **Bless / Bane:** wired on **both** attack rolls (the `/attack`
  `_buff_attack_suffix` via `_attacker_has_bless` / `_attacker_has_bane`)
  and saves (`_saver_bless_bane_save_suffix`, line ~22595, called at every
  spell/feature save-construction site). No gap.
- **Save advantage (race-keyed):** `_race_grants_save_advantage` (line
  ~25642) swaps `1d20 → 2d20kh1` for Fey Ancestry / Gnome Cunning /
  Dwarven Resilience at the save sites.

---

## 2. The gaps Phase 4 closes

1. **No temp-HP primitive.** Every temp-HP feature except Heroism is
   announce-only — it returns a `temp_hp` number in JSON and broadcasts a
   card, but never writes `sheet["hp"]["temp"]`. Heroism's grant is
   copy-pasteable but not extracted.
2. **Damage ignores temp HP.** Even where temp HP IS set (Heroism), a hit
   subtracts straight from `hp_current` — temp HP is cosmetic. RAW: temp
   HP absorbs damage first, then the remainder hits real HP.
3. **Buff-level save advantage is unread.** Race advantage works, but no
   code reads an `effects.save_advantage` marker off a buff, so a feature
   that should grant "advantage on saves" (Aura of Protection-style,
   Magic Resistance, Holy Nimbus, etc.) can't express it.
4. **A few +AC spells are unwired.** Mage Armor, Haste (+2), Defensive
   Duelist don't install an `ac_bonus` buff yet (the read site is ready).

---

## 3. Design

### 3a. `_grant_temp_hp` (the primitive)
```
_grant_temp_hp(db, campaign_id, combatant, amount, *, source="",
               cast_id=None) -> dict
```
- **PC** (`char_id`): read `sheet["hp"]["temp"]`, set to `max(existing,
  amount)` (RAW non-stacking), persist, broadcast `character_hp_update`
  with the new temp. Returns `{applied, temp_before, temp_after}`.
- **NPC** (`token_template_id` / bare): store on the combatant dict
  (`combatant["temp_hp"] = max(existing, amount)`) in hub state +
  `battle_update`. NPCs have no sheet to persist to; volatile is fine.
- Log via `cast_id` for undo parity with the heal/damage log.

### 3b. Temp HP absorbs damage (the substrate change)
In `_apply_damage_to_combatant`, before computing `new_hp`, drain the
combatant's temp pool: `absorbed = min(temp, applied)`, `temp -= absorbed`,
`applied -= absorbed`; persist the reduced temp; then the existing
`new_hp = max(0, hp_cur - applied)` runs on the **remainder**. Mirror for
the PC (sheet) and NPC (combatant) branches. Keep it cheap — a couple of
dict reads on the hot path. This is the only hot-path edit.

### 3c. Buff-level save advantage
Add `_buff_grants_save_advantage(campaign_id, char_id, save_ability)` that
walks the saver's buffs for `effects.save_advantage` (a bool or a list of
abilities). Wire it alongside `_race_grants_save_advantage` at the save
sites (one `or` clause) so a buff can grant `2d20kh1`.

### 3d. +AC spell completion
Mage Armor / Haste / Defensive Duelist install a buff carrying
`effects.ac_bonus` (already read). Pure data — no new read site.

---

## 4. Phased implementation

1. **P4.1 — temp-HP substrate (M). ✅ shipped v2.99.416.** Built
   `_grant_temp_hp` (PC `sheet.hp.temp` / NPC `combatant.temp_hp`,
   non-stacking) + the temp-drain in `_apply_damage_to_combatant` (both
   branches). Proven by retrofitting Rally (applies temp HP to a target
   ally) + a deterministic /attack drain test.
2. **P4.2 — retrofit temp-HP features (M). ✅ shipped v2.99.416–.421.**
   Rally (P4.1), Dark One's Blessing, Touch of Death, Fighting Spirit,
   Inspiring Smite (multi-target), and Spirit Totem (bear aura) all call
   `_grant_temp_hp` on the target(s) instead of announce-only.
3. **P4.3 — +AC spell completion (S). ✅ shipped v2.99.422.** Mage Armor
   (+3) and Haste (+2) install an `ac_bonus` buff via `_SPELL_BUFF_MAP`
   (read by `_read_target_ac`); asserted via `/attack`'s `target_ac`.
   Defensive Duelist (a per-attack reaction) is deferred to Phase 7.
4. **P4.4 — buff-level save advantage (S). ✅ shipped v2.99.423.**
   `_buff_grants_save_advantage` (reads `effects.save_advantage`) wired at
   the single-target / AoE-cast / `/place_aoe` PC save sites; a buffed
   save rolls `2d20kh1`. **Completes Phase 4.**

---

## 5. Test contract

Each retrofit asserts **applied state**: a temp-HP grant shows the new
`temp` (via `character_hp_update` / sheet read) AND a subsequent `/attack`
drops temp before `hp_current` (assert `hp_current` unchanged while temp
falls, then real HP falls once temp is exhausted). +AC asserts the
`/attack` response's `target_ac` rose by the bonus. Save advantage asserts
the prompted/rolled save expression became `2d20kh1`.

---

## 6. Risks & guards

- **Hot path:** the temp-HP drain runs on every damage application. Keep
  it to dict reads + a min(); lean on the attack/damage harness suites.
- **Death-save interaction:** temp HP must be drained BEFORE
  `_apply_hp_change` so a hit fully absorbed by temp HP never triggers a
  death save or the dying state. Drain, then call the existing path with
  the remainder.
- **Non-stacking:** `max(existing, new)`, never sum — matches Heroism +
  RAW. Re-granting a smaller amount is a no-op.
- **NPC persistence:** NPC temp HP is volatile (hub state only); that's
  acceptable (NPCs don't survive a battle reset anyway).

---

## Related

- [full-feature-automation.md](full-feature-automation.md) — parent plan
  (P4 temp-HP + P8 roll-bonus completion).
- [feature-saves.md](feature-saves.md) — Phase 3; P4.4 wires alongside its
  save-construction sites.
- `_apply_damage_to_combatant`, `_apply_heal_to_combatant`,
  `_read_target_ac`, `_saver_bless_bane_save_suffix`,
  `_race_grants_save_advantage`, the Heroism temp-HP grant
  (`/cast_spell` ≈ 17291) — the reference implementations.
- `docs/test-harness-coverage.md` — grows with each retrofit.
