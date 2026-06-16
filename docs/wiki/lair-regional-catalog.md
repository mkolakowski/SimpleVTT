# Lair actions & regional effects catalog

*Audience: GMs + contributors. Refreshed for v2.382.0 — closes the last filed follow-up by backfilling regional effects for the metallic dragons + Lich + Kraken (v2.382.0 "The Living Map"). The entire lair-action arc is now end-to-end complete: 22 lair-action slugs + 22 regional-effect slugs + 8 mapped lair-action conditions + every endpoint / UI / fade tracker shipped. Filed-follow-ups list is empty.*

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

**Lair actions (`LAIR_ACTIONS_BY_SLUG`, 22 slugs):**
- 5 **chromatic** dragons (black, blue, green, red, white) — adult + ancient.
- 5 **metallic** dragons (brass, bronze, copper, gold, silver) — adult + ancient. *(v2.377.0)*
- **Lich** (phylactery / necromantic lair) + **Kraken** (submerged ocean lair) — single slug each, no age variants. *(v2.378.0)*

Dragons of every lair-bearing age (adult + ancient) share the lair-action set per color (RAW: lair actions are tied to the LAIR, not the creature's age). Young dragons and wyrmlings have no lair, so no entries.

**Regional effects (`REGIONAL_EFFECTS_BY_SLUG`, 22 slugs — full parity with lair actions as of v2.382.0):**
- 5 **chromatic** dragons (black, blue, green, red, white) — adult + ancient.
- 5 **metallic** dragons (brass, bronze, copper, gold, silver) — adult + ancient. *(v2.382.0)*
- **Lich** + **Kraken** — single slug each, no age variants. *(v2.382.0)*

**Condition map (`_LAIR_ACTION_CONDITION_BUFFS`, 8 keys):**

v2.379.0 closed the condition-map gap — every condition any lair action installs now auto-installs on a failed save:
- v1 chromatic: `prone` / `poisoned` / `blinded` / `restrained` / `charmed`.
- v2.379.0 closure: `unconscious` (Brass Slumberous Magic) / `silenced` (Lich Memory Shred) / `frightened` (Gold Shimmering Visions).

No lair-action condition still falls back to GM-narrate.

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

---

# Metallic dragon lairs (v2.377.0 lair actions + v2.382.0 regional effects)

The five metallic dragons share the chromatic data shape — 3 lair actions + 3 regional effects each, keyed to `adult-*` + `ancient-*`. Lair actions shipped v2.377.0; regional effects shipped v2.382.0 closing the parity gap.

## Brass Dragon — desert / canyon lair

*Slugs: `adult-brass-dragon`, `ancient-brass-dragon`. RAW MM p.107.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Magical Gust** | STR DC 15 | 60-ft line, 5 ft wide; pushed 30 ft + prone on a fail. |
| **Blinding Sandstorm** | CON DC 15 | 20-ft-radius sphere; blinded until the dragon takes another lair action. |
| **Slumberous Magic** | WIS DC 15 | Single target; unconscious for 1 minute on a fail (wakes on damage/shake). |

### Regional effects

- **Warm, Dry Winds** — supernaturally warm dry winds gust through the area within 6 miles of the lair.
- **Whirling Dust Devils** — dust devils whirl across the open within 1 mile, kicking up sand and obscuring sightlines.
- **Speaking Creatures** — beasts and humanoids within 1 mile may briefly speak Draconic at the dragon's whim.

## Bronze Dragon — coastal / sea lair

*Slugs: `adult-bronze-dragon`, `ancient-bronze-dragon`. RAW MM p.110.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Rolling Fog** | — | 20-ft-radius fog sphere; heavily obscured, lingers. (GM places it.) |
| **Lightning Strike** | DEX DC 15 | Up to 3 targets in 120 ft; 4d6 lightning (half on save). |
| **Ocean Currents** | STR DC 15 | Single target; pulled 30 ft into water + prone on a fail. |

### Regional effects

- **Briny Sea Mist** — sea mist drifts inland up to 6 miles, leaving a salty tang in the air.
- **Sudden Sea Storms** — small thunderheads and brief gales gather without warning within 1 mile.
- **Friendly Sea Beasts** — whales, dolphins, and seabirds within 1 mile shadow boats and escort swimmers.

## Copper Dragon — rocky highland lair

*Slugs: `adult-copper-dragon`, `ancient-copper-dragon`. RAW MM p.113.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Rock Storm** | DEX DC 15 | 20-ft-radius sphere; 3d6 bludgeoning (half on save). |
| **Slippery Earth** | DEX DC 15 | 20-ft-radius sphere; ground becomes slick — prone on a fail. |
| **Hilarious Magic** | WIS DC 15 | Up to 2 targets; charmed (harmless, laughing) until start of next turn. |

### Regional effects

- **Echoing Laughter** — distant peals of laughter echo from canyons + cliffs within 6 miles.
- **Rolling Stones** — loose stones within 1 mile tumble downhill without provocation (practical jokes).
- **Trickster Beasts** — animals within 1 mile play harmless tricks: leading travelers astray, hiding supplies, mimicking voices.

## Gold Dragon — auric lair

*Slugs: `adult-gold-dragon`, `ancient-gold-dragon`. RAW MM p.116.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Burning Veil** | DEX DC 15 | 20-ft-radius sphere; 3d6 fire (half on save). |
| **Calming Aura** | WIS DC 15 | 20-ft radius around dragon; can't attack (charmed/pacified) on a fail. |
| **Shimmering Visions** | WIS DC 15 | Single target; frightened until the dragon takes another lair action. |

### Regional effects

- **Benign Weather** — weather within 6 miles is mild and fair regardless of season.
- **Speaking Animals** — beasts within 1 mile can briefly speak (as Speak with Animals) at the dragon's will.
- **Prophetic Dreams** — intruders sleeping within 1 mile receive vivid dreams in which the dragon appears as a sage.

## Silver Dragon — mountain lair

*Slugs: `adult-silver-dragon`, `ancient-silver-dragon`. RAW MM p.119.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Rolling Mist** | — | 20-ft-radius mist sphere; heavily obscured, lingers. (GM places it.) |
| **Treacherous Ice** | DEX DC 15 | 20-ft radius becomes difficult terrain (ice); prone on a fail. |
| **Wintry Blast** | CON DC 15 | 20-ft-radius sphere; 3d6 cold (half on save). |

### Regional effects

- **Gentle Snowfall** — a light snowfall drifts continuously within 6 miles, even in midsummer.
- **Cloud Mounts** — clouds within 1 mile condense into rideable platforms moving as the dragon wills.
- **Inquisitive Birds** — birds within 1 mile watch intruders closely and relay what they see to the dragon.

---

# Non-dragon lairs (v2.378.0 lair actions + v2.382.0 regional effects)

Single-slug entries (no age variants, unlike dragons). Lair-actions shipped v2.378.0; regional effects shipped v2.382.0.

## Lich — phylactery / necromantic lair

*Slug: `lich`. RAW MM p.202.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Spectral Grasp** | WIS DC 18 | Single target within 30 ft; 3d6 necrotic + restrained until end of lich's next turn. |
| **Necrotic Surge** | CON DC 18 | 30-ft-radius sphere around lich; 4d6 necrotic (half on save). |
| **Memory Shred** | WIS DC 18 | Single target within 60 ft; silenced (no verbal-component casting) until end of target's next turn. |

### Regional effects

- **Restless Dead** — corpses within 1 mile twitch + stir, occasionally rising as weak undead.
- **Unsettling Whispers** — voices echo through halls and tunnels within 6 miles: half-heard phrases in long-dead tongues.
- **Creeping Decay** — plants wither + animals shun the area within 1 mile; food spoils faster than nature allows.

## Kraken — submerged ocean lair

*Slug: `kraken`. RAW MM p.197.*

### Lair actions

| Action | Save | Effect |
|---|---|---|
| **Stormy Currents** | STR DC 15 | 60-ft sphere around kraken; pushed 30 ft + prone on a fail. |
| **Lightning Storm** | DEX DC 15 | Up to 3 targets in 120 ft; 3d6 lightning (half on save). |
| **Black Ink Cloud** | — | 30-ft-radius ink sphere; heavily obscured, lingers (underwater). (GM places it.) |

### Regional effects

- **Abrupt Squalls** — squalls and storms gather without warning within 6 miles, scattering ships.
- **Treacherous Currents** — sea currents within 1 mile shift unpredictably, dragging vessels off course.
- **Aggressive Sea Beasts** — sharks + giant octopuses + ocean predators within 1 mile behave with unusual aggression.

---

## See also

- [Legendary actions + lair actions design plan](../plans/legendary-actions.md) — the full implementation roadmap (Phases 1–3 + regional effects + fade tracker + the v2.377.0/.378.0/.379.0 closure).
- `app/content/lair_actions.py` / `app/content/regional_effects.py` — the source of truth this catalog mirrors. Edit those, then refresh this page.
- `_LAIR_ACTION_CONDITION_BUFFS` in `app/routes/tabletop_routes.py` — the condition-key → buff template map the v2.379.0 closure extended.
