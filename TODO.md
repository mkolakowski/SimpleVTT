# SimpleVTT — Planned Features

Backlog of features to implement. Not prioritized — order is arbitrary.

---

## Touch Target Remediation

Apple's HIG minimum of 44×44 px was applied globally in v1.2.7 via the base `button`, `input`, and `select` CSS rules, and class-level overrides were added for the tabletop panel elements. The following inline-styled elements were not covered by that pass and still need updating. Grouped into three phases ordered by effort.

### ~~Phase 1 — Campaign Settings~~ ✓ Done (v1.2.8)

`app/templates/campaign_settings.html`

| Line | Element | Current style | Fix |
|------|---------|---------------|-----|
| ~83 | `.track-actions button` (rename / save / cancel / play / delete audio track) | `padding:2px 7px; font-size:12px` | Add CSS class `.track-action-btn` with `min-height:44px` and replace inline style |
| ~624 | `select.pl-category-select` (playlist category dropdown) | `font-size:11px; padding:2px 4px` | Increase to `padding:6px 8px` or remove inline style and rely on global `select` rule |
| ~1071 | `select#enc-lib-sort` (encounter library sort) | `font-size:12px; padding:2px 6px` | Same — remove inline padding override so global rule applies |

**Approach:** Remove the inline `padding` overrides from the two selects (they will then inherit the global `min-height:44px` rule). For `.track-actions button`, add a named CSS class at the top of the template so it can be shared across all track action buttons.

---

### ~~Phase 2 — Tabletop JS-created buttons~~ ✓ Done (v1.2.9)

`app/templates/tabletop.html` · `app/static/tabletop.js`

Defined `.enc-action-btn` (32 px), `.enc-modal-btn` (44 px), and `.enc-spawn-btn` (32 px) CSS classes. Replaced `style.cssText` assignments on encounter action buttons, save/cancel, and spawn set/clear with `className` assignments. Removed padding overrides from encounter edit form inputs/selects, roll-request panel controls, audio-enable button, and Import & Place button.

---

### ~~Phase 3 — D&D 5e Character Sheet~~ ✓ Done (v1.2.10)

`app/templates/sheet_dnd5e.html`

Nearly all 24 buttons share the same inline style (`font-size:11px; padding:2px 8px`). The fix is to introduce a single shared CSS class and replace every occurrence.

**New class to add** (at the top of the template's `<style>` block):
```css
.sheet-section-btn { font-size: 11px; min-height: 44px; padding: 0 10px; }
```

**Buttons to update** (replace `style="font-size:11px;padding:2px 8px"` with `class="sheet-section-btn"`):

| Line | Button ID | Purpose |
|------|-----------|---------|
| ~109 | `#char-edit-btn` | Edit character details |
| ~255 | `#bg-sync-btn` | Re-fetch background |
| ~268 | `#feats-add-btn` | Add feat |
| ~282 | `#mc-add-class-btn` | Add multiclass |
| ~522 | `#ab-edit-btn` | Edit ability scores |
| ~523 | `#ab-done-btn` | Save ability scores |
| ~568 | `#st-edit-btn` | Edit saving throws |
| ~569 | `#st-done-btn` | Save saving throws |
| ~618 | `#sk-edit-btn` | Edit skills |
| ~619 | `#sk-done-btn` | Save skills |
| ~819 | `#browse-weapons-btn` | Browse weapons |
| ~820 | `#add-custom-attack-btn` | Add custom attack |
| ~905 | `#spell-browser-btn` | Browse spells |
| ~906 | `#add-custom-spell-btn` | Add custom spell |
| ~909 | `#hide-unprepared-btn` | Toggle unprepared spells |
| ~911 | `#sc-autofill-btn` | Autofill spell slots |
| ~1125 | `#resources-sync-btn` | Sync resources |
| ~1126 | `#resources-add-btn` | Add resource |
| ~1127 | `#wild-shape-btn` | Wild Shape (Druid) |
| ~1128 | `#polymorph-btn` | Polymorph |
| ~1165 | `#browse-items-btn` | Browse items |
| ~1166 | `#add-custom-item-btn` | Add custom item |
| ~1306 | `#sync-race-btn` | Sync racial traits |
| ~1320 | `#sync-class-btn` | Sync class details |

Two additional buttons use slightly different padding and may need individual review:
- `#short-rest-btn` / `#long-rest-btn` (~line 167–168): `padding:4px 8px` — closer to compliant, verify with `.mini-rest-btn` class already applied.

---

## Character Sheet

### Hide Spells from Non-Casters
The spells section of the character sheet should be hidden (or collapsed) when the character's class has no spellcasting ability. Currently the spell panel is visible for all characters regardless of class. Detection should use the `class_spellcasting` field — hide the section when it is blank, and show it for any class with a spellcasting ability set (INT, WIS, CHA, etc.). Should also handle multiclass characters where at least one class is a caster.

### Ability Score Generation
Two methods for players to generate ability scores during character creation:
- **Point buy** — players spend a fixed pool of points (standard D&D 5e: 27 points, scores 8–15 before racial bonuses) with an interactive cost table shown in the sheet UI. Should enforce the budget in real time and show remaining points.
- **Dice rolling** — roll 4d6 drop lowest for each attribute, with an in-sheet button per score and a "Re-roll all" option. Should show the individual dice results before committing. Optionally allow the GM to lock or unlock rerolls per campaign.

### Dynamic Character Art Updates
When a player updates their character portrait on their sheet, the change should propagate in real time to the tabletop — updating the token image, the player list, and any other places the portrait is displayed — without requiring a page reload. Should use the existing WebSocket broadcast infrastructure so all connected clients (GM and other players) see the new art immediately.

---

## GM Tools

### GM Access to All Character Sheets
GMs should be able to open and read any player's character sheet in the campaign directly from the tabletop or campaign settings, without needing to be assigned as the character's owner. Read-only access is the minimum; optionally allow the GM to make edits (e.g. to update HP after a session or correct a mistake). Needs a clear UI entry point — likely a "View Sheet" button next to each character in the GM's player list.

### Reporting Page
Admin/GM dashboard showing campaign activity: session count, token move history, roll statistics, active players over time. Useful for GMs who want a post-session summary.

### Initiative Tracker Roll Prompt
When a combatant is added to the initiative order without a roll (e.g. added mid-combat from the token sheet or manually), show the GM a "Prompt Roll" button next to that entry. Clicking it sends a WebSocket message to the relevant player's client asking them to roll initiative. The button disappears automatically once the player's initiative is recorded (either via self-roll or GM entry).

### Roll Request — Per-Player Targeting
The roll-request panel currently broadcasts the prompt to everyone in the campaign; only the targeted player(s) should see the click-to-roll button. Add a player picker next to the existing roll-type / DC / ability inputs that lets the GM target one specific player, multiple selected players, or "all players" (current behaviour, kept as the default). UI: a multi-select dropdown listing every player member of the campaign by display name — keep it compact so it fits inline with the rest of the roll-request form. Backend: extend the WebSocket payload with a `target_user_ids: list[int]` field; the client only renders the prompt button when `ME.id` is in that list (or the list is empty, meaning broadcast). The GM's roll log should reflect which players were prompted so it's clear who the request went to.

---

## Maps & Map Editor

### Bulk Map Upload
Allow GMs and admins to upload multiple map images at once (e.g. a zip or multi-file picker) rather than one at a time. Should probably show a progress indicator and let the user assign names/grid settings to each before committing.

### Map Editor Framework
Groundwork for in-browser map authoring tools. Planned capabilities:
- **Fog of war** — GM-controlled reveal of map regions; players see only explored areas
- **Walls** — line segments that block token line-of-sight
- **Doors** — interactive wall segments that players/GMs can open or close
- **Clickable items** — hotspots on the map that trigger a description popup or roll prompt
- **Multi-map encounters** — link multiple maps into a single encounter (e.g. interior/exterior transitions) without switching the active map for the whole campaign

---

## Media & Content

### Resources
A dedicated section for GMs and admins to upload documents (PDFs, images, handouts) that players can view directly in the browser — inline PDF rendering, no download required. Needs access control so GMs can choose whether a resource is visible to all players or GM-only.

### Playlist Builder with Existing Songs
Allow GMs to create playlists from tracks already uploaded to the campaign rather than re-uploading. UI: a picker listing existing campaign audio tracks, drag-to-reorder, save as a named playlist. Backend: new playlist model + endpoints; guard file deletion to prevent removing audio that is still referenced by a playlist.

---

## Player Features

### Player Notes
Per-player scratchpad (rich text or markdown) scoped to a campaign. Notes should be private to the player by default, with an optional "share with GM" toggle. Persisted server-side so they survive page refreshes.

---

## UI / Mobile

### Slide-Out Menu for Mobile
On small screens, replace the current sidebar with a proper slide-out drawer triggered by a hamburger button. The map should fill the full viewport and the drawer overlays it rather than pushing it. Needs gesture support (swipe to open/close).

### Darker Sepia Themes
Add a few darker sepia/warm-brown colour themes as alternatives to the existing dark theme. Candidates: a deep parchment (dark tan background, inked-brown text), a candlelit tavern (very dark brown with amber accents), and a burnt manuscript (near-black with faded sepia highlights). Should slot into the existing theme system with new CSS variable sets — no structural changes needed.

---

## Integrations

### Philips Hue Integration
Allow GMs to sync Philips Hue smart lights with tabletop events — e.g. dim lights on combat start, flash red on a critical hit, restore brightness when combat ends. Should connect to the local Hue Bridge (mDNS or manual IP) and allow the GM to map VTT events to Hue scenes or brightness/colour changes in campaign settings.
