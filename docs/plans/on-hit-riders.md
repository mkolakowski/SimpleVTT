# On-hit damage riders — Phase 2 sub-plan

**Status:** ⚪ proposed (planning only)
**Parent:** [full-feature-automation.md](full-feature-automation.md) Phase 2.
**Goal:** Make the ~40 announce-only "on a hit, deal extra Xd_ / +N
[type]" subclass features **auto-apply their damage through the attack
pipeline** — so the GM never hand-adds rider damage — and verify each
with a harness test that asserts the applied damage on a real `/attack`.

---

## 1. What already works (the two existing rider patterns)

All in `app/routes/tabletop_routes.py`. `_compute_attack_auto_uplifts`
(≈ line 21643) is called from `/attack` and returns a list of
`{label, expression, total, breakdown, damage_type, source}` uplifts that
the attack flow rolls + adds to the damage total. Two patterns feed it:

### A. Buff-based, target-keyed (Hex, Hunter's Mark)
A buff installed on the attacker carries:
```
effects.weapon_hit_bonus_dice            = "1d6"
effects.weapon_hit_bonus_target_combatant_id = "<id>"  # or [list] (Twinned)
effects.weapon_hit_bonus_damage_type     = "necrotic"  # optional
```
`_compute_attack_auto_uplifts` block 2 matches the current target against
the buff's stored target and rolls the dice. **Fires on every matching
hit** (a known RAW simplification — Hex/Hunter's Mark are RAW once-per-turn
but apply per-hit here). Installed by `/cast_hex`, `/cast_hunters_mark`.

### B. Feature-flag, once-per-turn (Colossus Slayer, Divine Strike)
Hardcoded blocks (3, 4, …) read the attacker's `class_features` + a
`combatant.economy.<feature>_used` boolean. They fire once per turn:
the flag is set by a helper (`_mark_colossus_slayer_used`) after the
hit and cleared when the GM advances the turn (the whole `economy` dict
resets to `{action,bonus,reaction:False, movement:0}`, dropping the
`*_used` flags). Colossus Slayer also gates on target HP < max.

**Takeaways for the design:**
- The uplift list shape + the `weapon_hit_bonus_*` buff keys are the
  reusable substrate. Most new riders should **install a buff** and let
  block 2 apply it — no new attack-path code per feature.
- Once-per-turn riders need the `economy.<flag>_used` mechanism (pattern
  B), which the buff path (pattern A) doesn't currently express.
- Three rider shapes exceed "bonus dice": **flat bonus** (Hexblade's Curse
  +PB, not dice), **damage-type conversion** (Planar Warrior turns all
  damage to force), and **expanded crit range** (Hexblade's Curse crits on
  19–20). These need new effect keys.

---

## 2. Target features (the ~40), by shape

| Shape | Features | Plug-in |
|---|---|---|
| **Per-hit vs marked target, dice** | Slayer's Prey (+1d6), Dreadful Strike (+1d4 psychic, 1/turn), Gathered Swarm damage mode (+1d6 force) | buff with `weapon_hit_bonus_dice` (+ `once_per_turn` for Dreadful Strike) |
| **Per-hit vs marked target, flat** | Hexblade's Curse (+PB) | new `weapon_hit_bonus_flat` key |
| **Once-per-turn, conditional** | Divine Fury (+1d6+½lvl, first hit while raging), Kensei's Shot (+1d4, ranged this turn), Genie's Wrath (+PB by kind, 1/turn) | buff with `once_per_turn` flag or feature-flag block |
| **Damage-type conversion** | Planar Warrior (all → force +1d8) | new `weapon_hit_convert_type` + bonus |
| **Crit-range expansion** | Hexblade's Curse (crit 19–20 vs cursed) | new `weapon_hit_crit_range` key, read at the crit check |
| **First-turn extra attack** | Dread Ambusher (+1d8 on the bonus attack) | out of scope here — needs the extra-attack flow; defer |
| **On-kill** (not on-hit) | Dark One's Blessing, Touch of Death (temp HP on reducing to 0) | Phase 4 temp-HP, not this plan |

---

## 3. Design: extend the buff-rider substrate (don't add 40 attack-path branches)

### 3a. New effect keys on the weapon-hit-rider buff
Extend block 2 of `_compute_attack_auto_uplifts` to honor:
- `weapon_hit_bonus_flat: int` — flat bonus (rolled as `+N`, like Rage).
- `weapon_hit_once_per_turn: True` + `weapon_hit_flag: "<slug>"` — fire
  only if `attacker.economy["<slug>_used"]` is falsy; the attack flow
  sets it after applying (generalize `_mark_colossus_slayer_used` into
  `_mark_attack_flag(campaign_id, char_id, flag)`).
- `weapon_hit_convert_type: "force"` — the attack flow re-types the
  weapon's own damage (read where damage type is resolved, not in the
  uplift list).
- `weapon_hit_crit_range: 19` — read at the natural-crit check so a 19
  vs the marked target crits.

### 3b. "Arming" — activated riders install the buff
The activated rider endpoints (Slayer's Prey, Hexblade's Curse, Divine
Fury, Kensei's Shot, Gathered Swarm, Planar Warrior) stop announcing and
instead `_install_buff` on the attacker with the appropriate
`weapon_hit_bonus_*` effects keyed to the target (or self for
"this-turn" riders with no specific target). They already compute the
right numbers today — the change is *install a buff* instead of
*broadcast a card*. The Phase-1 use-tracking they already have stays.

### 3c. Passive/conditional riders register a feature-flag entry
Colossus Slayer + Divine Strike are already hardcoded; fold them (and any
new always-on conditional riders) into a small `_ATTACK_RIDERS` table of
`{gate_fn, dice_fn(sheet), damage_type_fn, once_per_turn, condition_fn}`
so the hardcoded blocks become one data-driven loop. Lower priority than
3a/3b since they already work.

---

## 4. Phased implementation

1. **P2.1 — extend the rider substrate (M).** Add `weapon_hit_bonus_flat`
   + `weapon_hit_once_per_turn`/`_flag` to block 2; generalize
   `_mark_colossus_slayer_used` → `_mark_attack_flag`. Unit-cover with a
   synthetic buff + `/attack` asserting applied damage. **No feature
   behavior change yet** — pure substrate.
2. **P2.2 — retrofit per-hit dice riders (M).** Slayer's Prey, Dreadful
   Strike, Gathered Swarm: install the buff; test asserts the rider
   damage lands on a `/attack` against the marked target.
3. **P2.3 — flat + once-per-turn riders (M).** Hexblade's Curse (+PB,
   crit-19), Divine Fury, Kensei's Shot, Genie's Wrath.
4. **P2.4 — damage-type conversion (S).** Planar Warrior via
   `weapon_hit_convert_type`.
5. **P2.5 — registry-ize the feature-flag riders (S).** Fold Colossus
   Slayer + Divine Strike into `_ATTACK_RIDERS`; no behavior change.

---

## 5. Test contract (the bar that makes a rider "automated")

Each retrofit's test must: put attacker + target in a battle (`PUT
/battle`), arm the rider (call the feature endpoint), then `/attack` the
target and assert the **damage total includes the rider** (and the
target's HP dropped by the expected amount), plus once-per-turn riders
don't fire twice in one turn. Use the existing `test_attack.py` /
`test_wild_magic_tides.py` battle-setup helpers as the template.

---

## 6. Risks & guards

- **Hot path:** block 2 runs on every `/attack`. Keep the new branches
  cheap (dict lookups) and gated; lean on the harness suite (the attack +
  rider tests) to catch regressions before merge.
- **Double-application:** the once-per-turn flag must be set *after* a
  confirmed hit and cleared on turn advance. Reuse the proven
  Colossus Slayer flag flow; don't invent a parallel mechanism.
- **Buff teardown:** activated rider buffs should drop on rest / when the
  marked target dies / on re-mark (Slayer's Prey "ends if you mark a new
  target"). Reuse the concentration/duration + `source_char_id` plumbing.
- **Stacking:** RAW most riders don't stack with themselves; installing a
  same-`key` buff already replaces (refresh semantics in `_install_buff`).

---

## Related

- [full-feature-automation.md](full-feature-automation.md) — parent plan.
- `_compute_attack_auto_uplifts`, `_mark_colossus_slayer_used`,
  `/cast_hex`, `/cast_hunters_mark` — the reference implementations.
- `docs/test-harness-coverage.md` — grows with each retrofit.
