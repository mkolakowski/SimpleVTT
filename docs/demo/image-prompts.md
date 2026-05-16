# Demo image-generation prompts

Ready-to-paste prompts for every entity in the SimpleVTT demo dataset
(`app/demo_seed.py`). Tested against the canonical baseline of the two
shipped tokens at `app/static/demo/tokens/rogue.png` and `wizard.png` —
the style is "painterly fantasy character portrait, three-quarter view,
isolated against a transparent background, suitable for a circular
virtual-tabletop token."

The character descriptions match the seeded sheets verbatim (race,
class, alignment, weapons, signature spells), so the rendered token
slots cleanly into the demo's narrative.

## Token files referenced by the seed

Drop the generated PNGs at:

| Token | Path | Status |
|---|---|---|
| Pip Quickfingers | `app/static/demo/tokens/rogue.png` | shipped |
| Thalindra Moonwhisper | `app/static/demo/tokens/wizard.png` | shipped |
| Brother Tavik Stonebrow | *(not yet wired — would be `cleric.png`)* | needs token wire in `seed_tokens` |
| Vex Vance | *(not yet wired — would be `bandit-captain.png`)* | needs token wire in `seed_tokens` |
| Grixxa | *(not yet wired — would be `goblin-captain.png`)* | needs token wire in `seed_tokens` |
| Bandit (×3) | *(not yet wired — `bandit.png`)* | needs token wire |
| Thug | *(not yet wired — `thug.png`)* | needs token wire |
| Tavern battle map | `app/static/demo/maps/tavern.png` | shipped (placeholder) |

The "needs token wire" rows currently fall back to the colored swatch
in `app/templates/tabletop.html` because `seed_tokens` doesn't set
`image_url` for those NPCs. After dropping a PNG in place, set
`image_url="/static/demo/tokens/<file>.png"` on the corresponding
token in `app/demo_seed.py seed_tokens()`.

---

## Style baseline (apply to every character prompt)

These tokens read best as: **painterly digital fantasy art, three-
quarter front-facing pose from the chest up (or full body for small
races), neutral expression unless noted, isolated against a fully
transparent background (PNG with alpha), suitable for cropping to a
256×256 circular token.** Subtle warm rim-lighting to match the tavern
firelight setting. No frame, no text, no caption.

If your image model accepts negative prompts, append:
`--no text, watermark, signature, frame, busy background, multiple
characters, action shot, motion blur, low quality`

Recommended aspect ratio: **1:1 (square)**. Recommended size: **1024×1024**
then downscale to 256×256 for the token.

---

## Player characters

### Pip Quickfingers — Halfling Rogue 5 (Thief)

> A young halfling rogue, female, three feet tall, slim and nimble.
> Shoulder-length copper-red hair tied back with a leather cord,
> mischievous emerald-green eyes, lightly freckled tan skin, a
> small smirk. Wearing dark brown studded-leather armor over a
> forest-green hooded tunic, a short sword sheathed at her hip,
> two daggers crossed on a leather bandolier across her chest,
> a small pouch of thieves' tools at her belt. Confident ready
> stance, one hand resting on the dagger hilt, the other casually
> at her side. Warm tavern firelight from below-left. Painterly
> fantasy character portrait, three-quarter view, isolated against
> a transparent background, suitable for a 256-pixel circular
> token. Halfling Chaotic Good. Mood: roguish, watchful, just
> waiting for an opening.

### Thalindra Moonwhisper — Elf Wizard 5 (School of Evocation)

> An elf wizard, female, slender and elegant. Long silver-white hair
> flowing past her shoulders, calm violet eyes, pale luminous skin
> with a faint silver sheen at the temples. Wearing flowing midnight-
> blue spellcaster robes embroidered with silver constellations and
> evocation runes around the cuffs, a delicate silver circlet
> across her brow. An open spellbook tucked under one arm; her free
> hand cradles a small floating arcane sigil pulsing soft blue-purple
> light. Neutral composed expression, intellectual and patient.
> Subtle ambient moonlight aesthetic. Painterly fantasy character
> portrait, three-quarter view, isolated against a transparent
> background, suitable for a 256-pixel circular token. Elf Neutral
> Good. Mood: scholarly, precise, quietly powerful.

### Brother Tavik Stonebrow — Hill Dwarf Cleric 5 (Life Domain)

> A hill dwarf cleric, male, mid-life, four and a half feet tall,
> stocky and broad-shouldered. Thick braided rust-red beard with
> two iron beads at the end, kind weathered face, deep brown eyes,
> sun-tanned skin. Wearing well-maintained chain mail under a
> leather tabard bearing an embossed golden sunburst holy symbol,
> a heavy war hammer strapped across his back, a small leather
> healer's kit at his belt. One hand raised in a benediction
> gesture (palm up, two fingers extended), the other resting
> calmly on the rim of a wooden round shield. Warm amber light
> suggesting a holy presence rises from the holy symbol. Painterly
> fantasy character portrait, three-quarter view, isolated against
> a transparent background, suitable for a 256-pixel circular
> token. Hill Dwarf Lawful Good. Mood: stoic, dependable, quietly
> radiant.

---

## NPCs — Tavern Brawl encounter

### Vex Vance — Bandit Captain (CR 2)

> A human bandit captain, female, late thirties, lean and scarred.
> Raven-black hair pulled into a tight high braid, sharp grey eyes,
> a single thin scar from her right cheekbone down to her jaw, weathered
> olive skin. Wearing dark studded-leather armor with a crimson sash
> across the waist, a curved scimitar at her hip and a throwing
> dagger at her belt. Standing with weight on one hip, one hand
> resting on the scimitar's hilt, the other gesturing as if mid-
> bark — issuing a command. Dim warm tavern firelight reflecting
> off the leather. Painterly fantasy character portrait, three-
> quarter view, isolated against a transparent background, suitable
> for a 256-pixel circular token. Human, any non-lawful. Mood:
> dangerous leader, in command of a bad situation.

### Grixxa — Goblin Captain (homebrew CR 1)

> A goblin captain, female, four feet tall, wiry. Mottled green-grey
> skin, oversized pointed ears, bright yellow eyes with vertical
> slit pupils, a wild crown of jet-black hair tied with bones and
> red feathers. Wearing battered studded-leather armor stitched with
> patches taken from bandit-spoils (a fragment of a tabard, a torn
> sleeve), a curved scimitar gripped in one hand and a bone-tipped
> javelin in the other. Standing on top of a wooden tavern table
> mid-shout, mouth open in a battle-cry showing pointed teeth.
> Firelight from below dramatizing the silhouette. Painterly
> fantasy character portrait, dynamic three-quarter pose, isolated
> against a transparent background, suitable for a 256-pixel
> circular token. Small Humanoid, neutral evil. Mood: fierce,
> cunning, the dangerous brain of a band that punches above its
> weight.

### Thug (single token, used as "Thug" in the encounter)

> A burly human thug, male, mid-thirties, six feet tall, heavily
> muscled. Shaved head with stubble shadow, a broken-and-set nose,
> knuckle tattoos (one letter per finger reading "PAID" on the
> right hand), a thick raised scar across his left bicep, dark
> brown eyes that never quite reach his smile. Wearing brown
> leather armor with reinforced metal-studded gauntlets, a heavy
> mace gripped in one hand and a heavy crossbow slung across his
> back. Cracking his knuckles, head tilted, leering with cruel
> anticipation. Painterly fantasy character portrait, three-quarter
> view, isolated against a transparent background, suitable for a
> 256-pixel circular token. Human, any non-good. Mood: imposing
> brute, enjoys his work.

### Bandit — generate three variants (Alpha / Beta / Gamma)

The encounter places three identical-stat bandits as mooks; give
each a slightly different look so the GM can tell them apart at a
glance on the map.

**Bandit Alpha:**

> A human bandit, male, late twenties, lean and unkempt. Chin-
> length brown hair and a short scruffy beard, sun-browned skin,
> a faint scar across the bridge of his nose. Wearing battered
> dark-brown leather armor over rough commoner clothes, a curved
> scimitar at the hip, a light crossbow slung over the shoulder.
> Standing in a wary half-crouch ready to spring forward. Dim
> tavern firelight. Painterly fantasy character portrait, three-
> quarter view, isolated against a transparent background, suitable
> for a 256-pixel circular token. Mood: opportunistic, jumpy,
> looking for an opening.

**Bandit Beta:** *(re-roll Alpha's prompt with these changes —
keep everything else the same so the trio feels like a unit)*

> ...wheat-blond hair tied back in a stubby ponytail, no beard,
> a missing front tooth visible when his lip pulls back...

**Bandit Gamma:**

> ...short-cropped black hair, a thick black beard streaked with
> grey, a leather eyepatch over the left eye...

---

## Tavern Brawl — battle map

> Top-down isometric battle map of a medieval roadside tavern
> interior, mid-day warm interior lighting filtering through narrow
> shuttered windows. Layout: a long oak bar along the east wall
> with a row of pewter mugs and bottles, four round wooden tables
> with stools scattered across the main floor (one stool on its
> side, one knocked-over chair near the door), a heavy wooden
> double-door on the west wall (currently closed), a stone fireplace
> with low burning logs on the north wall, a small staircase
> banking left to right in the southeast leading to upstairs rooms.
> Wooden plank floor with subtle 5-foot grid overlay (faint dark
> lines, not intrusive). Atmosphere: spilled mug on the floor near
> the bar, a few playing cards scattered near one table, smoke
> rising from the fireplace. Painterly fantasy battle-map style,
> suitable for a virtual tabletop, 1400×900 pixels, slight overhead
> camera angle (≈80° from horizontal) so the GM can see floor
> details. No characters, no tokens, no UI overlay.

Negative prompt suggestions: `text, signage, character figures,
modern objects, electric lights, glowing portals, fantasy ruins,
exterior shots, top-down photo realism`.

---

## Model-specific notes

- **Midjourney**: append `--ar 1:1 --style raw` for the character
  tokens and `--ar 14:9 --style raw` for the map. Use `--v 6` or
  later. The "isolated against a transparent background" hint
  doesn't actually produce transparent PNGs — you'll need to
  background-remove in Photoshop / GIMP / `rembg`.
- **DALL-E 3** (via ChatGPT or API): paste the prompt verbatim.
  Specify "PNG with transparent background" — DALL-E will produce a
  white background that you'll still need to alpha-key. 1024×1024
  default size is fine.
- **Stable Diffusion (any UI)**: use a portrait-tuned checkpoint
  (RealVisXL, AnimagineXL, or similar). Add a negative prompt
  block. Higher CFG (8-10) for tighter character adherence to the
  prompt. Use ControlNet OpenPose if you want the trio of bandits
  to share an identical pose.
- **Hand-painted alternative**: the current `rogue.png` and
  `wizard.png` look generated; if you want hand-painted, append
  "in the style of Tony DiTerlizzi" or "in the style of Jared
  Blando" (for the map). Adjust to taste.

## After generation

1. Background-remove (e.g. https://www.remove.bg, rembg CLI, or
   manual mask in GIMP) to get a transparent PNG.
2. Crop to a 1:1 square centered on the character's head and
   shoulders.
3. Downscale to 256×256 (the existing tokens' size).
4. Save to `app/static/demo/tokens/<file>.png`.
5. In `app/demo_seed.py seed_tokens()`, add `image_url="/static/
   demo/tokens/<file>.png"` to the corresponding `Token(...)` row.
6. Bump version, write a small CHANGELOG entry, redeploy. The
   demo's hourly reseed picks up the new images automatically.
