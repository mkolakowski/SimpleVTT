# Paladin oaths (non-Devotion) — design plan

Phase H.2 of the [v2.99.193 class-content completion plan](class-content-status.md).
Path: per-oath subclass shipping for the non-Devotion sacred oaths.

> **Status (re-audited 2026-06-10, v2.158.68):** 🟢 substantial
> progress — non-Devotion oath work shipped in chunks across the
> v2.99.245 → v2.158.x window:
>
> - **Ancients** — Nature's Wrath Channel Divinity ✅ (v2.99.245);
>   Aura of Warding Lv 7+ ✅ (v2.133.0–v2.135.1: full RAW chain
>   plumbing + endpoint + spell-damage resistance through the
>   `is_spell` damage-pipeline kwarg).
> - **Vengeance** — Relentless Avenger Lv 7+ ✅ Phase 1 (v2.149.0:
>   free-move budget + OA-immune flag buff). Phase 2 deferred:
>   `/token/move` consumes the budget + skips OA prompts.
> - **Conquest** — Scornful Rebuke Lv 15+ ✅ (v2.142.0: first
>   on-damage-taken hook in the codebase — recursive CHA-mod psychic
>   to attacker through `_apply_damage_to_combatant`).
> - **Redemption** — Aura of the Guardian Lv 7+ ✅ (v2.99.281).
> - **Devotion (already shipped)** — Purity of Spirit Lv 15+ ✅
>   (v2.158.10: permanent buff with `pfeag_*` payload reusing the
>   Protection from Evil and Good spell-buff engine).
>
> **Outstanding:** (1) Ancients Lv 15/20 (Undying Sentinel / Elder
> Champion); (2) Vengeance Phase 2 OA-flow gate + Lv 15/20 (Soul of
> Vengeance / Avenging Angel — frightful aura partially shipped
> Phase 5 v2.99.428); (3) Conquest Lv 3/7/20 (Conquering Presence /
> Aura of Conquest / Invincible Conqueror); (4) Redemption Lv 3/15/20
> (Emissary of Peace + Rebuke the Violent / Protective Spirit /
> Emissary of Redemption); (5) Glory full oath (Peerless Athlete /
> Inspiring Smite / Aura of Alacrity / Glorious Defense / Living
> Legend); (6) Devotion Lv 20 Holy Nimbus ✅ (v2.99.166) — verify
> shipped per the v2.99.192 audit, not re-tested in this header.

## Why a plan doc

The Devotion Paladin is the demo default (Sir Caelan Lightbringer)
and its features are largely shipped: Sacred Weapon + Turn the
Unholy CD (v2.14.3), Aura of Devotion (v2.x), etc. The other 5
PHB oaths plus 1-2 supplement oaths each have their own Lv 3 CD
+ Lv 7 aura + Lv 15/20 capstone, and shipping them all in one
commit is too big. This plan freezes the per-oath order so we
can ship one per commit on the same cadence as H.1's Cleric
domain batch.

## RAW oath inventory (PHB-first)

| Oath | Source | Lv 3 CD options | Lv 7 aura | Lv 15 | Lv 20 |
|------|--------|-----------------|-----------|-------|-------|
| Devotion (DEMO) | PHB p.85 | Sacred Weapon ✅, Turn the Unholy ✅ | Aura of Devotion ✅ | Purity of Spirit | Holy Nimbus |
| **Ancients** | PHB p.86 | **Nature's Wrath**, Turn the Faithless | Aura of Warding | Undying Sentinel | Elder Champion |
| **Vengeance** | PHB p.87 | Abjure Enemy, Vow of Enmity | Relentless Avenger | Soul of Vengeance | Avenging Angel |
| **Conquest** | XGE p.37 | Conquering Presence, Guided Strike | Aura of Conquest | Scornful Rebuke | Invincible Conqueror |
| **Redemption** | XGE p.38 | Emissary of Peace, Rebuke the Violent | Aura of the Guardian | Protective Spirit | Emissary of Redemption |
| **Glory** | TCE p.55 | Peerless Athlete, Inspiring Smite | Aura of Alacrity | Glorious Defense | Living Legend |

Plus the v3.x candidates from MOoT (Watchers) and Wildemount
(Open Sea / Cobalt Soul). Filed past 3.0.0.

## Phasing

### Phase 1 — Ancients Nature's Wrath (✅ v2.99.245)

**Endpoint:** `/api/campaign/{cid}/use_natures_wrath`.
**Body:** `{character_id, target_combatant_id, save_ability,
override?}` where `save_ability ∈ {STR, DEX}` (target's choice
RAW — we accept either as a body field).

- Validates Ancients Paladin Lv 3+ + `sheet.resources` has a
  `channel-divinity` entry with `current >= 1` + Phase 4 action
  chip.
- Decrements CD counter.
- Computes spell save DC = 8 + prof + CHA mod.
- Broadcasts: target makes a {save_ability} save DC <DC> or be
  restrained until the end of {caster}'s next turn.
- v1 ships announce-only — the GM rolls the target's save +
  installs the Restrained condition manually.

### Phase 2 — Ancients Turn the Faithless (⚪ deferred)

Lv 3. CD action. Same DC. AOE: all fey/fiends within 30 ft, Wis
save or be turned for 1 minute. Same /use_* shape, broadcasts a
30-ft Wis-save check with creature-type filter.

### Phase 3 — Vengeance + Conquest + Redemption + Glory CDs (⚪ deferred)

One oath per commit; each ships its primary Lv 3 CD as the v1
spine. Per-oath plan:

- **Vengeance — Vow of Enmity**: bonus action; advantage on
  attacks against the chosen target for 1 minute.
- **Conquest — Conquering Presence**: action; AOE Wis save or
  Frightened.
- **Redemption — Rebuke the Violent**: reaction; on dealing
  damage to ally, force attacker to Wis save or take psychic
  damage equal to damage dealt.
- **Glory — Inspiring Smite**: bonus action after Divine Smite;
  grant 2d8 + paladin level temp HP to chosen creature in 30 ft.

### Phase 4 — Lv 7 auras (⚪ deferred)

Each oath's 10-ft aura. Mostly passive; some need /save site
hooks (Aura of Warding for spell-damage resistance, Aura of
Conquest for slowed enemies, etc.). Filed as per-oath follow-up
commits.

### Phase 5 — Lv 15 capstone (⚪ deferred)

Mostly long-rest-tracked features. Roughly one commit each.

### Phase 6 — Lv 20 transformation (⚪ deferred)

The capstone forms (Holy Nimbus, Avenging Angel, Elder Champion,
…). Multi-effect buff installs + 1/long-rest. Each is a hefty
follow-up.

## What this plan does NOT cover

- Devotion (DEMO) — already shipped.
- Smite spells / Divine Smite tier — already shipped at the
  paladin-class level (not subclass-gated).
- Lay on Hands — paladin-class, not subclass-gated.
- Multi-oath multiclassing edge cases — out of scope until
  someone files a real-world test case.

## Sequencing

Phase 1 (Ancients Nature's Wrath) ships first because:
1. It's the cleanest Lv 3 CD — single target, save-based, no
   aura state to track.
2. Caelan PATCHing his subclass to "Oath of the Ancients" works
   with the existing channel-divinity resource on his sheet.

Phase 2-3 (the remaining CDs) follow at one commit each in the
order listed above. Phase 4-6 (auras + capstones) batch by oath
once the CD spine is in place across all 6 oaths.

## References

- [Class / Subclass / Feat / Race content status](class-content-status.md)
- [Wild Magic (Sorcerer subclass)](wild-magic.md) — 5-phase template.
- [Eldritch Knight (Fighter subclass)](eldritch-knight.md) — 4-phase template.
- [Battle Master (Fighter subclass)](battle-master.md) — 5-phase + 15-maneuver template.
