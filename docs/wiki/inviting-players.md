# Inviting players to your campaign

**Audience:** GMs setting up a campaign roster — plus the operator / site admin who manages accounts.
**Version stamp:** v2.635.0.
**Screenshots refreshed:** v2.635.0 (regenerate with `python3 tests/harness_ui/capture_inviting_players.py`).

Getting players into a SimpleVTT game is a deliberate, two-step process — there's **no public "join by link or code" flow**. Campaign membership is always explicit:

1. **The player gets an account** — self-service registration, or the operator creates it.
2. **A site admin adds that account to the campaign** — from campaign settings (or the Admin Center).

Then you, the GM, do the in-campaign setup: roll colors, co-GMs, and previewing the table as a player. This guide walks all of it, with screenshots from the demo campaign **The Sundered Vault**.

> **Who can add members?** Adding or removing a campaign member is a **site-admin** action (the server returns *403 Admin only* otherwise). Many small instances make the GM a site admin so they can self-serve; if you're a GM without admin rights, your operator does steps 1–2 for you.

## Step 1 — the player gets an account

A player needs a SimpleVTT account before they can be added to anything. Two ways to create one:

- **Self-service registration.** If open registration is on, send the player to the registration page and they make their own account (see the [player onboarding guide](player-onboarding.md) for the player's-eye view).
- **Operator-created.** On invite-only instances, the operator creates the account from the **[Admin Center](admin-center.md)** (`/users` → create) and hands the player their credentials.

Either way, the result is the same: an account that exists in the system, ready to be added to a campaign.

## Step 2 — add the player to the campaign

Open **Campaign settings → People**. The **Members** table lists everyone already in the game (the Primary GM, any co-GMs, and players). Under it, the admin-only **+ Add member** control expands a dropdown of every existing user *not yet* in this campaign — pick one and **Add as player**.

![Campaign settings People tab: the members table and the expanded Add member form](/static/docs/inviting-players/02-add-member.png)

The new member lands as a **Player** (`is_gm = false`). Need to add several players? Repeat — each `Add as player` adds one membership.

> Prefer to manage membership outside the campaign page? The **[Admin Center](admin-center.md)** has the same add/remove member controls (MFA-gated), which is the canonical surface for operators running many campaigns.

## Step 3 — set each player's roll color

Every member row has a **Roll color** swatch. Pick a color and it saves live (you'll see a brief ✓) — that color highlights the player's entries in the roll log and their token accents, so the table can tell at a glance who rolled what. Give each player a distinct color.

![The members table with a roll-color swatch per player](/static/docs/inviting-players/01-people-tab.png)

## Promote a co-GM

Trust a player to help run the game? Hit **Make GM** on their row to grant co-GM rights (they get the GM tools and full visibility); **Demote** takes it back. The Primary GM (campaign owner) can't be demoted here. *(Adding/removing members stays admin-only — Make GM only toggles co-GM status for someone already in the campaign.)*

## Preview the table as a player

Before your players arrive, sanity-check what they'll see. The **Preview Tabletop as Player** control (bottom of the People tab) opens the tabletop in a new tab *as that player* — their roll log, their player view, what's hidden from them. Use it to confirm you haven't left a monster token or secret note revealed.

## The character roster

**Campaign settings → People** also lists characters, and the campaign **Characters** page (`/campaign/<id>/characters`) shows the whole roster at a glance. As the GM you see **every** PC, its owner, and its portrait; a player sees only their own. This is where you confirm each player has a character assigned to them.

![The GM's view of the full campaign character roster](/static/docs/inviting-players/03-character-roster.png)

## Character portraits

A character with art is easier to spot in the roll log and on the map. On any character sheet, the **📷** button at the corner of the portrait uploads art (PNG / JPG / WebP / GIF, 5 MB max). Either the GM **or** the character's owner can set it; until then the sheet shows a letter placeholder.

![The portrait upload button on a character sheet](/static/docs/inviting-players/04-portrait-upload.png)

## Try it with the demo accounts

A fresh demo instance (`DEMO_MODE=true`) seeds accounts you can use to rehearse the whole flow — log in as the GM, add a player, set a color, then log in as that player to see the result. All use the password **`demopass`**:

| Account | Role | Notes |
|---|---|---|
| `demo-gm@example.com` | GM (+ site admin by default) | Owns the demo campaigns; can add members |
| `demo-alice@example.com` | Player | Pip Quickfingers (Rogue) |
| `demo-bob@example.com` | Player | Thalindra Moonwhisper (Wizard) |
| `demo-carol` / `demo-dave` / `demo-erin@example.com` | Players | Spare players to add to a campaign |

(On the public demo box `DEMO_GM_SITE_ADMIN` may be set to `false`, which hides the admin-only **+ Add member** form for `demo-gm` — that's a deployment choice, not the default.)

## Where to go next

- **[Player onboarding](player-onboarding.md)** — what the player does once you've added them.
- **[Running a session as GM](running-a-session-as-gm.md)** — initiative, the target picker, GM tools.
- **[Admin Center](admin-center.md)** — operator-side account + membership management.
- **[First-run setup](first-run-setup.md)** — standing up the instance in the first place.
