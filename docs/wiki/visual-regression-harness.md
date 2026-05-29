# Visual regression harness (`tests/harness_ui/__snapshots__/`)

> **Status:** ✅ shipped (v2.97.13). Local-only — not yet wired into CI.

## What it does

Captures PNG screenshots of specific page elements (typically a roll-log card, a feature card, a sheet section) and compares them against a committed baseline on every test run. Catches **unintended** visual changes — a CSS rule that nudges a pill 2 px the wrong way, a typo that breaks the layout, a refactor that drops a class. Doesn't tell you whether a planned visual change looks **good** — that's still a human judgement on the captured baseline.

## How to run

```bash
# One-time install (matches the rest of the UI harness):
pip install playwright pytest-playwright pillow
playwright install chromium

# Container needs to be up + on the version under test:
docker compose up -d --build app

# Run the visual tests:
pytest tests/harness_ui/test_visual_*.py -v

# Update baselines (after an intentional visual change you've eye-checked):
pytest tests/harness_ui/test_visual_*.py --update-snapshots
```

## Workflow

1. **Land the visual change.** Edit the CSS / template / JS. Click-test in a browser to confirm it looks right.
2. **Run the visual tests.** They fail with a diff fraction. The `*.current.png` next to the baseline (under `__snapshots__/`) shows what the test captured.
3. **Eye-check the diff.** Open `*.current.png` vs `<name>.png` side-by-side. Confirm the change is what you intended.
4. **Update the baseline.** Re-run with `--update-snapshots`. The new PNG replaces the old one.
5. **Commit the new baseline alongside the code change.** Reviewers see both in the same diff and can pull the PR locally to view the PNG.

## Adding a new visual test

Minimal pattern (see `tests/harness_ui/test_visual_spell_card.py`):

```python
import pytest
from playwright.sync_api import Page, expect
from .conftest import assert_visual_match, disable_animations, tabletop_url


def test_visual_my_widget(gm_page: Page, update_snapshots: bool):
    gm_page.set_viewport_size({"width": 1280, "height": 800})
    gm_page.goto(tabletop_url())

    # ... drive the page into the state you want to snapshot:
    # - inject DOM directly with page.evaluate(html_string)
    # - click through real UI (more realistic but more brittle)
    # - send a WS event from the harness (most realistic, hardest to wire)

    widget = gm_page.locator("#my-widget")
    expect(widget).to_be_visible()

    disable_animations(gm_page)            # kill CSS transitions before snapshot
    assert_visual_match(
        widget,
        "my_widget_state_A",                # stable name; ends up in __snapshots__/my_widget_state_A.png
        update=update_snapshots,
        max_diff_fraction=0.01,             # default — 1 % pixel drift allowed for font / AA noise
    )
```

### Tips

- **Stable input.** Inject the DOM via `page.evaluate(html_string)` for pure CSS regressions — the test doesn't depend on a server-side cast (which would require a WS round-trip + roster lookup + variable dice outcomes). When you DO need the real JS render path, capture the timing-sensitive bits in a `mask` or assert structure instead of pixels.
- **Disable animations.** The `disable_animations(page)` helper injects a stylesheet that nukes `transition` and `animation` so frame-timing flake doesn't haunt you.
- **Pin viewport size.** Different viewports → different layouts → different pixels. Always `page.set_viewport_size(...)` before the snapshot.
- **Pin a state.** The expanding `<details>` pill captures differently open vs closed. Use `@pytest.mark.parametrize` to capture multiple states under different names.
- **Mask timestamps + IDs.** If your widget renders the current time or a random ID, either freeze those values in your DOM injection OR mask the region from the screenshot. Pillow's ImageChops doesn't have a built-in mask; the easiest workaround is to put the variable bits inside an element you can `display: none` via the disable-animations stylesheet.

## Cross-machine determinism

PNG snapshots are sensitive to font rendering, anti-aliasing, OS chrome, scrollbar widths. macOS / Linux / Windows produce different pixels even for identical HTML. For now this harness is **local-only** — the captured baselines were taken on the developer's machine. CI integration is deferred so the test workflow doesn't fail on Mac-vs-Linux pixel jitter.

When CI integration is wanted, the recommended approach is:

1. Add a Linux-based snapshot step to the Docker build (Playwright's Chromium docker image is the canonical pin).
2. Re-capture baselines from that container.
3. Run the visual tests from the same container in CI.

A developer would then keep two baseline sets — `__snapshots__/local/` for fast eye-checks during work, `__snapshots__/ci/` for the canonical CI baselines — or just delegate to the container for both (slower iteration, no double maintenance).

## What's currently covered

- `tests/harness_ui/test_visual_spell_card.py` — v2.97.12 spell-card pillification (school / casting time / range / details pills). Two snapshots: collapsed (details closed) and expanded (details open). Sample data is a synthetic Fireball cast injected via DOM mutation; the test exercises the production CSS stylesheet inside the real tabletop page.

## Cross-references

- [Consume-without-refund audit](consume-without-refund-audit.md) — the v2.97.0-v2.97.8 audit that this harness's first proof-of-concept was built to verify (specifically the v2.97.12 spell-card pillification fallout).
- CHANGELOG entry v2.97.12 ("Pill Cabinet") — the visual change being protected.
- CHANGELOG entry v2.97.13 ("Snapshot the Wand") — this harness's ship.
