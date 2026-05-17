# Demo-mode bundled assets

Images used by the demo-mode seed dataset (`app/demo_seed.py`).

- `maps/tavern.png` — 1400×900 tan-with-grid placeholder map
  (Pillow-generated at v2.3.0, CC0). Used as `Map.image_url` for the
  seeded "Sundered Tavern" map.
- `tokens/rogue.jpg`, `tokens/wizard.jpg`, `tokens/cleric.jpg` — PC
  portraits for the three demo characters (Pip / Thalindra / Brother
  Tavik). Wired in v2.3.44.
- `tokens/bandit-captain.jpg`, `tokens/bandit-alpha.jpg`,
  `tokens/bandit-beta.jpg`, `tokens/bandit-gamma.jpg`,
  `tokens/thug.jpg`, `tokens/goblin-captain.jpg` — NPC portraits
  for the six seeded combatants in the "Tavern Brawl" encounter.
  Wired in v2.3.44.

These ship inside the Docker image at `app/static/demo/` and are
served by the existing static-files mount at `/static/demo/...`. The
upload Docker volume is **never** touched by the demo, so the hourly
reset doesn't need to clean any disk state.

To replace with better art: drop a new file at the same path (same
filename, jpg or png) and it'll render automatically on the next
reset. To wire a brand-new portrait (e.g. an added NPC), edit
`seed_tokens` in `app/demo_seed.py` to set `image_url` to the new
`/static/demo/tokens/<file>` path. See
[`docs/demo/image-prompts.md`](../../../docs/demo/image-prompts.md)
for ready-to-paste image-generator prompts matching every seeded
character's visual identity.
