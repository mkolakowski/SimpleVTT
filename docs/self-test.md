# Demo self-test

The **Self-Test** is a one-click, live smoke test of the whole SimpleVTT game
loop. It drives real gameplay against every built-in demo campaign — moving a
token across the map, starting initiative, and simulating a couple of combat
rounds — then hands back a readable pass/fail report of **what was tested, the
expected outcome, and the actual outcome**. Use it after a deploy or a risky
change to answer "does the VTT still work end-to-end?" without clicking through
six campaigns by hand.

## Where it lives

It's a page in the **Admin Center** (the standalone operator console, default
port `8015`): **🧬 Self-Test** in the top nav. It is opt-in and demo-only:

- **`ADMIN_CENTER_ADMIN_TOOLS=true`** — the self-test drives live gameplay (and
  then restores it), so it sits behind the same opt-in flag as the other write
  tools. With it off, the page shows a disabled notice and the run endpoint 404s.
- **`DEMO_MODE=true`** — it validates the built-in demo campaigns using the demo
  GM accounts, so it only runs on a demo instance.

## How it works

The runner talks to the main app exactly like the test harness — over HTTP +
WebSocket — logging in as **each campaign's own demo GM** (a GM's actions bypass
the action-economy and turn gates, so the sim can drive freely). It runs on a
background thread and publishes its report after every check, so the page can
stream results in **while the run is still going**.

It is **non-destructive**: before touching a campaign it snapshots the token
positions and battle state, and restores them at the end. (A demo instance also
reseeds hourly as a backstop.) A full run across all six campaigns takes only a
few seconds.

## Running a subset

You don't have to run everything. The page has a **scope picker**: tick which
**campaigns** and which **phases** (`movement`, `combat`, `spells`, `gates`) to
run, then **▶ Run selected** — handy for monitoring one focused slice. Each
campaign row also has a **▶ only this** shortcut that runs just that campaign
with the current phase selection. Reachability always runs, and
`combat`/`spells`/`gates` each start initiative automatically; a run that never
starts a battle leaves it untouched. The chosen scope is shown above the report
and recorded in the run history.

## What it checks, per campaign

1. **Reachability** — log in as the campaign GM; fetch the roster and the map's
   tokens; expect at least one hero and one villain token on the active map.
2. **Movement across the map** — a hero token **glides** several cells in hops
   (so it visibly travels), asserting the position changed *and* `token_move`
   broadcasts fired.
3. **Doors** — open then close a door on the map (the GM bypasses any gate),
   asserting the `walls_update` broadcast and the `open` flag flipping each way;
   maps without doors record a skip.
4. **Start initiative** — `PUT` the battle state with combatants built from the
   tokens; assert the `battle_update` broadcast and that the battle is active.
5. **Combat rounds** — two rounds. Each round groups a representative set of
   actors (a few PCs and a couple of NPCs); each actor:
   - **advances** — the PC token glides toward its target before swinging, so it
     looks like real play;
   - **attacks** — PCs via the weapon-attack endpoint (asserting the attack /
     damage totals and the `weapon_attack` broadcast, and reporting the target's
     HP change); NPCs via the monster-strike endpoint;
   - **casts a spell** (caster PCs) — a leveled spell when a slot is free
     (asserting the `spell_cast` broadcast *and* that one slot was consumed), or
     a cantrip otherwise; a leveled cast refused by slot rules (e.g. a Warlock's
     pact slot) falls back to a cantrip, and non-casters record a skip. Spent
     slots are refilled with a long rest during restore;
   - **ends its turn** — advance initiative and assert the `battle_update`
     broadcast and that the turn index moved (wrapping to the next round).
6. **Gate checks (negative paths)** — because the GM bypasses the gates, the
   runner logs in as the **player who owns a hero token** and asserts two
   rejections: an **off-turn move** returns `403`, and an **attack with the
   action already spent** (no override) returns `409 over_budget`. Both are
   expected to fail, so nothing is mutated.
7. **Restore** — move every token back to its start position, reset the battle to
   its prepped state, and long-rest any caster that spent a slot.

Every visible action (moves, door toggles) is **paced** so a GM watching the
campaign sees the tokens glide and interact in real time — like a session in
progress. Set `SELFTEST_STEP_DELAY=0` for a fast headless run.

## Reading the report

The report is a **collapsible tree**: **campaign → group (Setup / Round N /
Teardown) → actor (PC/NPC) → checks**. Every level shows a roll-up badge of
completed vs. total plus a pass/fail count, and a colored status dot, so an
incomplete branch reads as "not done yet" while the run streams. Each leaf check
is a row showing its **category, what was tested, expected, actual, and result**.
Open any branch to drill into a single attack or turn advance; the tree keeps
the sections you've opened as it refreshes.

## Run history

Every completed run is archived (the most recent 25) and listed in the
**📜 Run history** table — date, app version, pass/fail/error/skip totals, and
duration, newest first. **Click a row to reopen that run's full report** in the
tree above (a "back to latest" link returns to the live view). The table
refreshes automatically when a live run finishes, so you can watch the trend
across deploys.

A green run means the core loop — auth, map movement + realtime broadcasts,
initiative, attacks, damage application, and turn advancement — is working across
all the demo campaigns. Any red or amber check points at exactly which endpoint
or broadcast regressed, and on which campaign.
