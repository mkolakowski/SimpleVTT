# Demo-mode bundled assets (v2.3.0)

Placeholder images used by the demo-mode seed dataset (`app/demo_seed.py`).
All three were generated programmatically with Pillow at build time —
crude grid + colored circles, no third-party art. CC0 / public domain.

- `maps/tavern.png` — 1400×900 tan-with-grid placeholder map, with a
  brown bar on the right and three round tables on the left. Used as
  `Map.image_url` for the seeded "Sundered Tavern" map.
- `tokens/rogue.png` — 256×256 blue circle with the letter R. Used as
  the Rogue PC token's image.
- `tokens/wizard.png` — 256×256 green circle with the letter W. Used
  as the Wizard PC token's image.

These ship inside the Docker image at `app/static/demo/` and are
served by the existing static-files mount at `/static/demo/...`. The
upload Docker volume is **never** touched by the demo, so the hourly
reset doesn't need to clean any disk state.

To replace with better art: drop new PNGs at the same paths (same
filenames) and they'll render automatically on the next reset.
