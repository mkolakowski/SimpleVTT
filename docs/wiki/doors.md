# Doors — checks, locks & keys

Doors in SimpleVTT are more than a gap in a wall you click open. A door can be a
plain toggle, a **stuck door** that a creature must *force* with an ability
check, or a **locked door** that needs the right **key** or a successful
**lock-pick**. This guide covers how a GM sets that up in the map editor and how
it plays at the table.

> Doors live inside a map's walls. Everything here is set per-door in the **map
> editor** and enforced live on the **tabletop**. There's no schema or setup
> beyond placing the door — the check/lock settings ride along in the map data.

## Placing a door

In the **map editor** (a map's ⚙ → *Edit map*, or the Maps panel):

- Use the **🚪 Door** tool and click an existing wall to drop a door into it, or
  right-click a plain wall → **🚪 Insert door here**.
- Right-click a door for its options: Move/resize, **Type** (Wall / Door / Gate
  / Window / Invisible), **Material**, **↻ Flip swing**, **🔒 Secret**, and the
  two gates below.

A door with no gate set just **toggles open/closed** when anyone clicks it — the
original behavior.

## Open-checks — forcing a stuck door

Right-click a door → **🎲 Open check** → pick a check and enter a DC:

- Choices: **Strength**, **Dexterity**, **Athletics**, **Acrobatics**, **Sleight
  of Hand**, **Perception**, **Investigation** — or **None (opens freely)** to
  clear it.
- Enter a **DC** (1–40) when prompted.

Now, when a player opens that door, their token **rolls the check** (`1d20` +
the relevant ability/skill modifier from its sheet):

- **Pass** → the door opens.
- **Fail** → it stays shut, and the roll is posted to the log so the whole table
  sees the attempt (`🚪 Force the door | Athletics (prof) | DC 15 — ✗ Fail`).

Use this for a swollen, warped, or barred door that a character muscles through.

## Locked doors — keys & lockpicking

Right-click a door → **🔒 Lock**:

- **🔒 Locked** — toggle the door locked. A locked door won't open on a click
  unless it's unlocked (below).
- **🗝 Key item** — the *name* of an inventory item that unlocks it (e.g.
  `Iron Key`). A token carrying an item with that name (matched case-insensitively
  against its sheet inventory) opens the door instantly.
- **🪛 Pick lock** — a check + DC to pick the lock (e.g. *Sleight of Hand* DC 18),
  or **Can't be picked**.

When a player opens a locked door, the game resolves, in order:

1. **Holds the key** → the door unlocks and opens (`🗝 unlocked the door with
   the Iron Key`).
2. **Otherwise, can it be picked?** → the token rolls the pick check. Pass →
   unlock + open; fail → it holds (roll posted to the log either way).
3. **Neither** → *"It's locked."*

A successful key-use or pick **stays unlocked** afterward (you can close and
re-open it freely) until you re-lock it in the editor. The key + pick settings
persist through lock/unlock, so re-locking keeps them.

> An open-check and a lock can both be set on one door, but the **lock resolves
> first** — unlocking opens it, and the open-check only matters for an *unlocked*
> door.

## What players see

A **closed** gated door shows a small badge at its midpoint on the tabletop so
players know what they're up against before they try:

- **🔒** — the door is locked (needs a key or a pick).
- **🎲** — the door needs an open-check to force.

Hovering the door shows the detail: the required **key name** and/or **pick DC**
for a lock, or the **check + DC** for an open-check. Secret doors stay hidden
from players, and fog still hides a door the party hasn't seen — the badges never
leak a door's existence.

## Who rolls — and the GM

- **Players** roll with their controlled token automatically.
- **The GM** is the rules authority and **opens gated doors freely** by default
  (a narrative open) — *unless* they have a token **selected**. Click a token on
  the map to select it (a cyan ring marks it), then click the door: that token
  rolls the gate. This works for a **PC or an NPC** — a selected monster rolls
  its own ability/skill from its stat block. Press **Escape** to clear the
  selection and go back to bypassing.

This lets you make an ogre *force* a barred gate, or a goblin *fail* to pick a
lock, right in front of the party.

### Note on SRD monsters

A monster token rolls its own stats from its stat block. Templates you author (or
the demo/homebrew NPCs) resolve every check — ability checks, skills, and
proficiency. **SRD-catalog (slug-backed) monsters** currently resolve **ability
checks** (Strength, Dexterity) accurately, but **skill-named** checks (Athletics,
Perception) fall back to the raw ability modifier without proficiency. For those
NPCs, prefer an ability-based open-check/pick, or use an authored template.
