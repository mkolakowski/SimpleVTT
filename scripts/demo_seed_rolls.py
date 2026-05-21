"""One-shot: generate one of each roll-log card variant so the v2.42.1
theme-aware layout has live content to look at in the browser.

Hits the local demo container at http://localhost:8013 and posts:
  1. plain /roll
  2. /attack — Krieger swings Greataxe at a seeded bandit
  3. /cast_spell — Tavik casts Healing Word on Pip (heal chip)
  4. /cast_spell — Tavik casts Hold Person on the bandit (save + buff chips)
  5. /cast_spell — Thalindra casts Fire Bolt at the bandit (attack + damage)
  6. /attack — Rowan shoots Longbow at the bandit (ranged crit chance)
  7. /use_second_wind — Garrik triggers Second Wind (feature_used + dice toast)
  8. /cast_spell — Magnus casts Eldritch Blast at the bandit (multi-beam at L5)
  9. /cast_spell — Thalindra casts Magic Missile at the bandit (no-attack damage)

Run from repo root:  python3 scripts/demo_seed_rolls.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "tests")

from harness.helpers import login_client  # noqa: E402


CAMPAIGN_ID = 1


async def main() -> None:
    gm = await login_client("demo-gm@example.com", "demopass")
    try:
        roster_resp = await gm.get(f"/api/campaign/{CAMPAIGN_ID}/roster")
        roster_resp.raise_for_status()
        roster = {c["name"]: c for c in roster_resp.json()["characters"]}

        pip = roster["Pip Quickfingers"]
        tavik = roster["Brother Tavik Stonebrow"]
        thal = roster["Thalindra Moonwhisper"]
        krieger = roster["Krieger Stonefist"]
        rowan = roster["Rowan Quickbow"]
        garrik = roster["Garrik Ironside"]
        magnus = roster["Magnus Hexbinder"]

        for c in (tavik, thal, krieger, rowan, garrik, magnus):
            await gm.post(
                f"/api/campaign/{CAMPAIGN_ID}/character/{c['id']}/rest",
                json={"type": "long"},
            )
        await gm.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"hp": {"current": 8}},
        )

        templates = (await gm.get(f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
        bandit_tmpl = next(t for t in templates if "bandit" in t["name"].lower())

        bandit_tok = "tok_demo_bandit"
        await gm.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {
                        "id": f"tok_demo_{krieger['id']}", "char_id": krieger["id"],
                        "name": krieger["name"], "initiative": 18,
                        "hp_current": 50, "hp_max": 50, "buffs": [],
                        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                    },
                    {
                        "id": f"tok_demo_{tavik['id']}", "char_id": tavik["id"],
                        "name": tavik["name"], "initiative": 16,
                        "hp_current": 30, "hp_max": 30, "buffs": [],
                        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                    },
                    {
                        "id": f"tok_demo_{thal['id']}", "char_id": thal["id"],
                        "name": thal["name"], "initiative": 14,
                        "hp_current": 24, "hp_max": 24, "buffs": [],
                        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                    },
                    {
                        "id": f"tok_demo_{pip['id']}", "char_id": pip["id"],
                        "name": pip["name"], "initiative": 12,
                        "hp_current": 8, "hp_max": 24, "buffs": [],
                        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                    },
                    {
                        "id": f"tok_demo_{rowan['id']}", "char_id": rowan["id"],
                        "name": rowan["name"], "initiative": 15,
                        "hp_current": 36, "hp_max": 44, "buffs": [],
                        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                    },
                    {
                        "id": f"tok_demo_{garrik['id']}", "char_id": garrik["id"],
                        "name": garrik["name"], "initiative": 11,
                        "hp_current": 25, "hp_max": 49, "buffs": [],
                        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                    },
                    {
                        "id": f"tok_demo_{magnus['id']}", "char_id": magnus["id"],
                        "name": magnus["name"], "initiative": 13,
                        "hp_current": 28, "hp_max": 35, "buffs": [],
                        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                    },
                    {
                        "id": bandit_tok, "char_id": None,
                        "token_template_id": bandit_tmpl["id"],
                        "name": bandit_tmpl["name"], "initiative": 8,
                        "hp_current": 50, "hp_max": 50, "buffs": [],
                        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                    },
                ],
                "turn_index": 0,
                "round": 1,
                "active": True,
            },
        )

        form = {
            "name": "Demo Campaign",
            "description": "demo",
            "game_system": "dnd5e",
            "gm_tab_color": "",
            "font_override": "",
            "default_encounter_id": "",
            "hp_threshold_1": "",
            "hp_threshold_2": "",
            "hp_threshold_3": "",
            "hp_threshold_4": "",
            "auto_play_playlist_id": "",
            "auto_play_mode": "order",
            "auto_play_initial_volume": "0.7",
            "auto_apply_damage": "on",
        }
        await gm.post(f"/campaign/{CAMPAIGN_ID}/settings", data=form, follow_redirects=False)

        print("[1/9] Plain /roll — 2d6+3 (initiative-style)")
        await gm.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll",
            json={"expression": "2d6+3", "label": "Initiative warmup"},
        )

        print("[2/9] /attack — Krieger Greataxe → Bandit")
        await gm.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": bandit_tok,
                "target_name": bandit_tmpl["name"],
                "override": True,
            },
        )

        print("[3/9] /cast_spell — Tavik Healing Word → Pip (heal chip)")
        await gm.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": 5,
                "slot_level": 1,
                "class_slug": "cleric",
                "target_character_id": pip["id"],
                "target_combatant_id": f"tok_demo_{pip['id']}",
                "target_name": pip["name"],
                "override": True,
            },
        )

        print("[4/9] /cast_spell — Tavik Hold Person → Bandit (save + buff chips)")
        await gm.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": 8,
                "slot_level": 2,
                "class_slug": "cleric",
                "target_combatant_id": bandit_tok,
                "target_name": bandit_tmpl["name"],
                "override": True,
            },
        )

        print("[5/9] /cast_spell — Thalindra Fire Bolt → Bandit (attack + damage chips)")
        await gm.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": 0,
                "slot_level": 0,
                "class_slug": "wizard",
                "target_combatant_id": bandit_tok,
                "target_name": bandit_tmpl["name"],
                "override": True,
            },
        )

        print("[6/9] /attack — Rowan Longbow → Bandit (ranged with crit chance)")
        await gm.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": rowan["id"],
                "attack_index": 0,
                "target_combatant_id": bandit_tok,
                "target_name": bandit_tmpl["name"],
                "override": True,
            },
        )

        print("[7/9] /use_second_wind — Garrik (feature_used + dice toast)")
        await gm.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_second_wind",
            json={"character_id": garrik["id"], "override": True},
        )

        print("[8/9] /cast_spell — Magnus Eldritch Blast → Bandit (multi-beam at L5)")
        await gm.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": magnus["id"],
                "spell_index": 0,
                "slot_level": 0,
                "class_slug": "warlock",
                "target_combatant_id": bandit_tok,
                "target_name": bandit_tmpl["name"],
                "override": True,
            },
        )

        print("[9/9] /cast_spell — Thalindra Magic Missile → Bandit (auto-hit darts)")
        await gm.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": 4,
                "slot_level": 1,
                "class_slug": "wizard",
                "target_combatant_id": bandit_tok,
                "target_name": bandit_tmpl["name"],
                "override": True,
            },
        )

        print("\nDone. Open http://localhost:8013/campaign/1 and check the roll-log drawer.")
        print("Each card shows oversized outcome pills (heal / hit / miss / damage / buff / undo).")
        print("Cycle themes from the user menu to confirm the pills re-tint correctly.")
    finally:
        await gm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
