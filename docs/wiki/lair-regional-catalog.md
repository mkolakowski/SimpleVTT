# Lair actions & regional effects catalog

*Audience: GMs + contributors. Written for v2.181.1.*

A reader-facing catalog of every lair's **lair actions** (initiative-count-20
effects) and **regional effects** (passive zone-wide flavor) currently
authored in SimpleVTT. RAW MM p.11. This is the human-readable mirror of the
two curated leaf modules:

- Lair actions — `app/content/lair_actions.py` (`LAIR_ACTIONS_BY_SLUG`)
- Regional effects — `app/content/regional_effects.py` (`REGIONAL_EFFECTS_BY_SLUG`)

Both are folded onto the projected monster sheet by `_monster_dict_to_sheet`
(keyed by monster `slug`) and surfaced in play through the floating
`#_lair_action_panel` (GM) and `#_regional_effects_panel` (player). The
GM-driven fade tracker (`POST /set_regional_fade`, v2.181.0) models the RAW
"regional effects fade over 1d10 days" countdown once the lair-dweller dies.

## How the two differ

| | Lair actions | Regional effects |
|---|---|---|
| When | On initiative count 20 (losing ties), once per round, no repeat two rounds running | Passive — radiate continuously while the creature dwells in its lair |
| Engine | Save-or-damage / condition dispatch (`/trigger_lair_action`) | Flavor-only descriptive text (no save/damage in v1) |
| Shape | `{id, name, desc, save_ability, save_dc, damage, damage_type, half_on_save, effect, area}` | `{id, name, desc}` |
| Fade on death | n/a (only fires while in lair) | Fades over 1d10 days (`/set_regional_fade` tracker) |

## Coverage

All five **chromatic** dragons (black, blue, green, red, white). Lair actions
and regional effects are tied to the lair, not the creature's age, so each
color's `adult-*` and `ancient-*` slugs share the same set. Young dragons and
wyrmlings have no lair, so no entries. Metallic dragons + the Lich / Kraken are
a filed follow-up data backfill (they drop into the two `*_BY_SLUG` dicts with
no code change).

---

## Red Dragon — volcanic lair

*Slugs: `adult-red-dragon`, `ancient-red-dragon`. RAW MM p.98.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Magma Erupts** | DEX DC 15 | 6d6 fire in a 20-ft-radius burst (half on save). |
| **Tremor** | DEX DC 15 | Creatures on the ground within 60 ft. knocked prone on a fail. |
| **Volcanic Gases** | CON DC 13 | 20-ft-radius sphere; poisoned until end of next turn on a fail. |

### Regional effects

- **Minor Earthquakes** — small quakes are common within 6 miles of the lair.
- **Warm, Foul Water** — water within 1 mile runs supernaturally warm + sulfur-tainted.
- **Fissures to the Plane of Fire** — rocky fissures within 1 mile become fire-plane portals.

---

## Black Dragon — fetid swamp lair

*Slugs: `adult-black-dragon`, `ancient-black-dragon`. RAW MM p.88.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Grasping Tide** | STR DC 15 | Pulled up to 20 ft. into the water + knocked prone on a fail. |
| **Swarming Insects** | CON DC 15 | 3d6 piercing in a 20-ft-radius sphere (half on save); lingers as difficult terrain. |
| **Magical Darkness** | — | 15-ft-radius magical darkness; darkvision can't pierce it (GM places the area). |

### Regional effects

- **Obscuring Fog** — fog lightly obscures the land within 6 miles of the lair.
- **Twisted Plant Growth** — plants within 1 mile grow thorny, becoming difficult terrain.
- **Tainted Waters** — water within 1 mile is fouled; drinking risks sickness.

---

## Blue Dragon — arid desert lair

*Slugs: `adult-blue-dragon`, `ancient-blue-dragon`. RAW MM p.91.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Ceiling Collapse** | DEX DC 15 | 3d6 bludgeoning on one target (half on save); prone + buried on a fail. |
| **Sand Cloud** | CON DC 15 | 20-ft-radius sphere; blinded for 1 minute on a fail (repeat save each turn). |
| **Lightning Arc** | DEX DC 15 | 3d6 lightning in a 5-ft line (no half on success). |

### Regional effects

- **Frequent Thunderstorms** — storms roll across the land within 6 miles.
- **Treacherous Sand** — sinkholes within 1 mile behave like quicksand.
- **Whirling Sand Spouts** — sand spouts scour travelers caught in the open within 1 mile.

---

## Green Dragon — forest lair

*Slugs: `adult-green-dragon`, `ancient-green-dragon`. RAW MM p.94.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Grasping Roots and Vines** | STR DC 15 | 20-ft radius becomes difficult terrain; restrained on a fail. |
| **Wall of Tangled Brush** | DEX DC 15 | 4d8 piercing to creatures in the wall's space (half on save), pushed out. |
| **Magical Fog** | WIS DC 15 | One target charmed by the dragon until initiative 20 next round on a fail. |

### Regional effects

- **Labyrinthine Thickets** — thickets within 1 mile form a shifting maze (difficult terrain).
- **Unnaturally Cunning Predators** — beasts + plants within 1 mile hunt intruders for the dragon.
- **Insidious Whispers** — faint whispers within 1 mile seed paranoia among intruders.

---

## White Dragon — frigid arctic lair

*Slugs: `adult-white-dragon`, `ancient-white-dragon`. RAW MM p.101.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Freezing Fog** | CON DC 10 | 3d6 cold in a 20-ft-radius sphere (half on save); heavily obscured, lingers. |
| **Jagged Ice Shards** | — | Ranged attack (+7) vs up to three targets; 3d6 piercing per hit (GM rolls). |
| **Opaque Wall of Ice** | — | 30-ft wall of ice; creatures in its space pushed 5 ft. out (GM places it). |

### Regional effects

- **Chilling Fog** — frigid fog lightly obscures the land within 6 miles.
- **Freezing Precipitation** — icy sleet + snow glaze the ground within 1 mile at the dragon's will.
- **Frozen Sculptures** — creatures slain within 1 mile are encased in ice.

---

## See also

- [Legendary actions + lair actions design plan](../plans/legendary-actions.md) — the full implementation roadmap (Phases 1–3 + regional effects + fade tracker).
- `app/content/lair_actions.py` / `app/content/regional_effects.py` — the source of truth this catalog mirrors. Edit those, then refresh this page.
