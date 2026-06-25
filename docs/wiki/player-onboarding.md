# Player onboarding — your first session

**Audience:** brand-new players who just got invited to a SimpleVTT campaign.
**Version stamp:** v2.634.0.
**Screenshots refreshed:** v2.634.0 (regenerate with `python3 tests/harness_ui/capture_onboarding.py`).

You got an invite to a game. This guide walks you from "I have a login" to "I can find my character, read my sheet, and roll dice in front of the whole table" — with a screenshot of every screen you'll touch. No D&D-software experience needed. The GM handles the map, the monsters, and the rules calls; your job is your character.

The screenshots come from the demo campaign **The Sundered Vault** and the player **Pip Quickfingers** (a Halfling Rogue). Your campaign and character will differ, but the screens are the same.

> Tip: every page has the same top nav strip — **Wiki**, your name, **My Characters**, **Settings**, **Logout** — so you can always get back to your characters or settings from anywhere.

## 1. Create your account

If your GM sent you a registration link, open it and create an account with your email + a password. (Some instances are invite-only — if registration is closed, your GM will create the account for you and send credentials.)

![The registration page](/static/docs/onboarding/01-register.png)

## 2. Sign in

Once you have an account, sign in from the login page.

![The sign-in page](/static/docs/onboarding/02-login.png)

## 3. The lobby — your campaigns

After signing in you land in the **lobby**. It has two halves:

- **Campaigns you run** — games where *you* are the GM (empty for most players).
- **Campaigns you're playing in** — the games you've been invited to. Click one to open it.

![The lobby showing the campaigns you're playing in](/static/docs/onboarding/03-lobby.png)

Each campaign card shows the game system (e.g. *Dungeons & Dragons 5e*), the level band, and whether the session is **LIVE**.

## 4. Your characters

**My Characters** (top nav) is your personal hub across *every* campaign you're in. Each character card shows the essentials — class, level, race, HP, AC, speed — plus a **View Sheet** button. From here you can also create a new character (**+ New Character**) when a GM asks you to, or **Retire** one you're done with.

![The My Characters hub listing your characters across campaigns](/static/docs/onboarding/04-my-characters.png)

## 5. Jump into a campaign

Open a campaign and you'll see your character(s) *for that game*, with two ways in:

- **View Sheet →** opens the full character sheet (read and roll).
- **Open tabletop** drops you onto the battle map for the live session.

![A campaign's character launchpad with View Sheet and Open tabletop](/static/docs/onboarding/05-campaign-roster.png)

## 6. Reading your character sheet

The sheet is your home base. The top band shows your **portrait, HP, AC, initiative, speed, and proficiency bonus**; below it are your **ability scores** (STR/DEX/CON/INT/WIS/CHA) and your **skills**. Scroll down for attacks, spells, inventory, and class features.

![Pip Quickfingers' D&D 5e character sheet](/static/docs/onboarding/06-character-sheet.png)

Anything with a little die or a highlighted box is **clickable to roll** — abilities, saving throws, skills, and attacks. You don't add up modifiers by hand; the sheet does the math.

For a deeper tour of every section of the sheet, see **[The character sheet](the-character-sheet.md)**.

## 7. Rolling dice

Click an ability, save, skill, or attack and SimpleVTT rolls it for you, shows the breakdown, and announces the result to the whole table with an animated **roll toast**. Here Pip rolled a check — the toast shows the total and how it got there.

![A dice roll result toast on the character sheet](/static/docs/onboarding/07-rolling-dice.png)

That's the core loop: the GM asks for a check or attack, you click it on your sheet, everyone sees the result instantly.

## 8. The roll log

Every roll at the table is recorded in the **roll log**, newest first — yours and everyone else's. It's great for "wait, what did I just roll?" and for the GM to keep the game honest. You can pop it out into its own window so it stays visible next to the tabletop.

![The campaign roll log](/static/docs/onboarding/08-roll-log.png)

## 9. The tabletop (battle map)

When the GM starts an encounter, **Open tabletop** puts you on the shared battle map. You'll see the map, the tokens (yours and the rest of the party, plus any monsters the GM has revealed), and the roll log alongside. Your token is the one you control; the GM moves the monsters.

![The tabletop battle map with party tokens and the roll log](/static/docs/onboarding/09-tabletop.png)

During combat the GM tracks initiative and turn order; you act on your turn using the roll controls on your sheet and the action chips.

## 10. Monster stat blocks

When the GM reveals a monster, you can open its **stat block** — AC, HP, abilities, and attacks — the same way you read your own sheet. (The GM controls what's revealed; you only see monsters they've shown the table.)

![An Adult Red Dragon monster stat block](/static/docs/onboarding/10-monster-statblock.png)

## 11. Settings & themes

**Settings** (top nav) is where you make SimpleVTT yours: pick a **theme** (Dark, Midnight, Light, Forest, Fire, and more), choose a **display font**, and set your profile. Purely cosmetic — it only changes *your* view, never the shared table.

![The user settings page with theme and font pickers](/static/docs/onboarding/11-settings.png)

## Where to go next

- **[The character sheet](the-character-sheet.md)** — a section-by-section tour of the 5e sheet.
- **[Reactions automation](reactions.md)** — how reaction prompts (opportunity attacks, Shield, etc.) reach you at the table.
- **[Running a session as GM](running-a-session-as-gm.md)** — if you ever want to run a game yourself.

Welcome to the table — now go roll some dice.
