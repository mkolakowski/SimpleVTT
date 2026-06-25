# Theming & display preferences

**Audience:** everyone — players and GMs alike.
**Version stamp:** v2.636.0.
**Screenshots refreshed:** v2.636.0 (regenerate with `python3 tests/harness_ui/capture_theming.py`).

SimpleVTT lets you reskin the whole interface to taste. Everything on this page is a **personal** preference — it changes only *your* view and follows your account across devices. It never affects the shared table, the map, or what other players see, so reskin freely.

Find it all under **Settings** (top nav).

![The Settings page: theme swatches and the display-font picker](/static/docs/theming/01-theme-picker.png)

## Themes

There are **14 built-in themes** — eight "classic" UI palettes and six warmer "fantasy" palettes. Click a swatch and it applies **instantly** and saves (no Save button).

| Classic | Fantasy |
|---|---|
| Dark *(default)*, Midnight, Dim, Light, Forest, Bubblegum, Fire, OLED | Hobbiton, Hearthstone, Mosswood, Inkwell, Forge, Sepia |

- **Dark / Midnight / Dim / OLED** — low-light variants; OLED is true-black for battery/contrast.
- **Light** — a bright high-contrast palette for well-lit rooms.
- **Forest / Fire / Bubblegum** — accent-forward color themes.
- **Fantasy themes** — parchment, hearth, and ink palettes that pair nicely with the fantasy display fonts below.

### The same sheet, four looks

The theme swaps a set of CSS color tokens (`--bg`, `--fg`, `--accent`, …) across the entire app. Here's Pip's character sheet under four very different themes:

| | |
|---|---|
| **Dark** (default) | **Light** |
| ![Character sheet in the Dark theme](/static/docs/theming/02-theme-dark.png) | ![Character sheet in the Light theme](/static/docs/theming/03-theme-light.png) |
| **Fire** | **Hobbiton** (fantasy + Cormorant font) |
| ![Character sheet in the Fire theme](/static/docs/theming/04-theme-fire.png) | ![Character sheet in the Hobbiton theme](/static/docs/theming/05-theme-hobbiton.png) |

## Display font

Below the themes, **Display font** restyles headings and body text app-wide:

| Font | Feel |
|---|---|
| **System default** | Clean sans-serif — the standard UI look. |
| **Lora** | Elegant, readable serif. |
| **Cormorant Garamond** | Ornate fantasy serif (slightly larger). |
| **IM Fell English** | Old-book / hand-set feel. |

The serif fonts pair especially well with the fantasy themes (the Hobbiton shot above uses Cormorant Garamond).

## Scale & readability

A few more knobs on the Settings page tune sizing and density:

- **UI scale** and **Font scale** — enlarge the interface / text independently (e.g. 0.85× to 1.5×) for high-DPI displays or readability.
- **Glass alpha** — how opaque the frosted-glass overlay panels are.
- **Sepia texture** — a subtle paper grain, available on the Sepia theme.

## Other display preferences

The same Settings page also carries non-cosmetic personal toggles worth knowing about:

- **Roll-log position** — dock the roll log on the left or right.
- **Reaction prompts** — popup, roll-log-only, or off (how reaction offers like Shield / opportunity attacks reach you; see the [reactions guide](reactions.md)).
- **Animate GIFs** — play or freeze animated portraits/tokens.
- **Tab colors** — accent colors for your Player / Battle tabs.

## Accessibility notes

- **Contrast.** The **Light** and **OLED** themes give the highest contrast; pick those if low-contrast dark palettes are hard to read.
- **Text size.** Use **Font scale** to enlarge text without enlarging the whole UI.
- **Motion — known gap.** SimpleVTT does **not** currently honor the OS `prefers-reduced-motion` setting, so dice-roll and toast animations always play. If motion sensitivity is a concern, this is a tracked limitation rather than a setting today. *(Animated GIFs can be frozen via the toggle above.)*

## How it's stored

Your choices persist per-account (the `users.theme` / `users.font_preference` / scale columns), and the theme is applied server-side as a `data-theme` attribute on the page's root element at render time. Because it's tied to your account — not the browser — your look is the same on every device you log in from.

## Where to go next

- **[Player onboarding](player-onboarding.md)** — the rest of the player's-eye tour.
- **[The character sheet](the-character-sheet.md)** — what all those sheet panels do.
- **[Reactions automation](reactions.md)** — the reaction-prompt modes in depth.
