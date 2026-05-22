"""Tabletop pages + REST/WebSocket APIs.

REST is used for state-changing actions (move token, roll dice, edit sheet).
The WebSocket pushes those changes to other connected clients.
"""
from __future__ import annotations

import logging
import os
import re as _re
import time as _time
import uuid
from datetime import timezone
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import dice as dice_mod
from ..auth import get_current_user, require_user
from ..config import get_settings
from ..database import SessionLocal, get_db
from ..game_systems import SYSTEMS, get_system, system_choices
from ..models import (
    AudioPlayEvent,
    Campaign,
    CampaignMembership,
    Character,
    ConcentrationEffect,
    DiceRoll,
    Encounter,
    GridType,
    Map,
    Playlist,
    PlaylistTrack,
    RollRequest,
    Token,
    TokenTemplate,
    User,
    Visibility,
)
from ..realtime import hub
from .. import local_content
from ..sheet_templates import (
    class_levels_summary,
    class_slug as _class_slug,
    get_template,
    normalize_dnd5e_sheet,
)
from ..templates import templates


router = APIRouter()
log = logging.getLogger(__name__)

_OPEN5E_BASE = os.getenv("OPEN5E_BASE_URL", "https://api.open5e.com").rstrip("/")

# In-memory heal-claim store (cast_id → claim dict). Entries expire after 8 h.
_heal_claims: dict[str, dict] = {}

def _purge_heal_claims() -> None:
    now = _time.time()
    for k in [k for k, v in _heal_claims.items() if v["expires"] < now]:
        del _heal_claims[k]


# v2.5.5 (action-economy Phase 2b): server-side mirrors of the JS
# helpers in tabletop.html. Full-character-sheet clicks (.atk-strike,
# .sp-cast) live on a separate page from the tabletop, so the player's
# browser can't directly mutate the GM's init-tracker chips. Instead
# cast_spell / use_attack call _mark_battle_economy which updates the
# in-memory hub state and broadcasts ``economy_update``; both GM and
# player tabletop clients listen and re-render. Mini-sheet / monster
# clicks (Phase 2) still go through the JS path because they happen
# inside the tabletop page where ``battle`` is already in scope.

def _casting_time_to_economy(ct: str) -> str:
    """Map a spell's ``casting_time`` string to an economy slot.

    Mirrors ``_castingTimeToEconomy`` in tabletop.html. Returns one of
    ``action`` / ``bonus`` / ``reaction`` / ``none``; the ``none`` branch
    covers cantrip-free utility spells (10-minute rituals, etc.) and
    legacy rows with missing casting_time.
    """
    lc = (ct or "").lower()
    if "bonus action" in lc:
        return "bonus"
    if "reaction" in lc:
        return "reaction"
    if "action" in lc:
        return "action"
    return "none"


# v2.6.0 (action-economy Phase 3): Python mirror of
# app/static/dnd5e_feature_economy.js. The /use_feature endpoint reads
# this dict to derive the slot from a (feature_key, option_key) pair
# instead of trusting the client. Keep the two tables in sync — slot
# values diverge → server discards the client's claim and uses the
# canonical one, so silent UI-only changes won't grant phantom slots.
#
# v2.43.11: descriptions added so the feature_used broadcast gets a
# desc populated even when the client didn't include one (mini-sheet
# Use buttons, GM-tools panel, etc.). The roll-log feature card
# inlines the desc next to the feature name. Source-of-truth still
# stays the JS file — these descs are the server-side fallback used
# when ``request.body.desc`` is empty.
_FEATURE_ECONOMY: dict[str, dict] = {
    "cunning-action": {
        "slot": "bonus",
        "desc": "Take Dash, Disengage, or Hide as a bonus action.",
        "options": {
            "dash":      {"desc": "Move up to your speed again this turn."},
            "disengage": {"desc": "Your movement doesn't provoke opportunity attacks this turn."},
            "hide":      {"desc": "Make a Dexterity (Stealth) check to hide."},
        },
    },
    "second-wind": {
        "slot": "bonus",
        "desc": "Regain 1d10 + your fighter level HP. Recharges on a short or long rest.",
    },
    "action-surge": {
        "slot": "free",
        "desc": "Take one additional action on this turn. Recharges on a short or long rest.",
    },
    "channel-divinity": {
        "slot": "action",
        "desc": "Channel divine energy to fuel a class- and subclass-specific effect.",
        # v2.14.3: per-option entries cover both Cleric + Paladin
        # options under the same resource key. The picker filters by
        # class/subclass client-side; the server only needs the keys
        # to validate incoming option_keys + a desc to fall back to.
        "options": {
            # Cleric options
            "turn-undead":         {"desc": "Each undead within 30 ft makes a Wisdom save or flees for 1 minute."},
            "preserve-life":       {"desc": "Distribute 5 × cleric level HP among creatures within 30 ft (none raised above half max HP)."},
            "radiance-of-the-dawn": {"desc": "Dispel magical darkness; deal 2d10 + cleric level radiant damage on a failed Con save (each enemy within 30 ft)."},
            "guided-strike":       {"desc": "+10 bonus to one attack roll, declared after seeing the d20."},
            # Paladin options (v2.14.3)
            "sacred-weapon":       {"desc": "Imbue a weapon you hold with positive energy for 1 minute: +CHA mod to attack rolls, deals magical damage, emits 20 ft bright light."},
            "turn-the-unholy":     {"desc": "Each fiend or undead within 30 ft that can see/hear you must succeed on a Wisdom save or be turned for 1 minute."},
        },
    },
    "lay-on-hands": {
        "slot": "action",
        "desc": "Spend from your pool (5 × paladin level) to heal a touched creature or cure poison/disease.",
    },
    "divine-smite": {
        "slot": "free",
        "desc": "After hitting with a melee weapon attack, expend a spell slot for +2d8 radiant (+1d8 per slot level above 1st; +1d8 vs undead/fiends).",
    },
    "divine-sense": {
        "slot": "action",
        "desc": "Detect celestial / fiend / undead within 60 ft until end of next turn. 1 + CHA mod uses per long rest.",
    },
    "cleansing-touch": {
        "slot": "action",
        "desc": "End one spell on yourself or one willing creature you touch. CHA mod uses per long rest.",
    },
    "bardic-inspiration": {
        "slot": "bonus",
        "desc": "Pick one creature within 60 ft (other than yourself). They gain a bonus die to add to one ability check, attack roll, or save in the next 10 minutes.",
    },
    "cutting-words": {
        "slot": "reaction",
        "desc": "Reaction: spend 1 Bardic Inspiration use to subtract a BI die from an enemy attack roll, ability check, or damage roll within 60 ft.",
    },
    "flurry-of-blows": {
        "slot": "bonus",
        "desc": "Immediately after the Attack action, spend 1 ki to make two unarmed strikes as a bonus action.",
    },
    "patient-defense": {
        "slot": "bonus",
        "desc": "Spend 1 ki to take the Dodge action as a bonus action.",
    },
    "step-of-the-wind": {
        "slot": "bonus",
        "desc": "Spend 1 ki to take Disengage or Dash as a bonus action; your jump distance doubles for the turn.",
    },
    "wild-shape": {
        "slot": "action",
        "desc": "Transform into a beast you have seen before.",
    },
    "rage": {
        "slot": "bonus",
        "desc": "+damage on STR melee attacks, advantage on STR checks/saves, resistance to bludgeoning/piercing/slashing.",
    },
    "reckless-attack": {
        "slot": "free",
        "desc": "On your first attack this turn, gain advantage on melee STR attacks but attacks against you have advantage until your next turn.",
    },
    "quickened-spell": {"slot": "bonus"},
    "arcane-recovery": {
        "slot": "free",
        "desc": "Once per day during a short rest, regain spell slots whose combined level ≤ ⌈wizard_lv/2⌉. L6+ slots are not eligible.",
    },
    "indomitable": {
        "slot": "free",
        "desc": "Reroll a failed saving throw. Must use the new roll. 1/short rest at Lv 9, 2/short rest at Lv 13, 3/short rest at Lv 17.",
    },
    "stroke-of-luck": {
        "slot": "free",
        "desc": "Once per short or long rest: turn a missed attack into a hit, OR turn a failed ability check into a 20.",
    },
    "font-of-magic": {
        "slot": "free",
        "desc": "Spend or gain sorcery points; convert sorcery points to spell slots and vice-versa.",
    },
}


def _feature_economy_slot(feature_key: str, option_key: str | None) -> str | None:
    """Resolve (feature, option) to a slot using the curated table.

    Returns "action" / "bonus" / "reaction" / "free", or None when the
    feature isn't in the table. Option slot can override the parent's;
    if the option doesn't specify, the parent's slot wins. Unknown
    options return the parent's slot (the picker treats a no-match as
    "any of the listed options", same as the JS lookup).
    """
    feat = _FEATURE_ECONOMY.get((feature_key or "").lower())
    if not feat:
        return None
    parent_slot = feat.get("slot")
    if option_key:
        opt = (feat.get("options") or {}).get(option_key.lower())
        if opt and opt.get("slot"):
            return opt["slot"]
    return parent_slot


def _feature_economy_desc(feature_key: str, option_key: str | None) -> str:
    """Resolve (feature, option) to a description string for the
    feature_used broadcast. Option's desc takes precedence over the
    parent feature's desc; falls back to the parent when the option
    doesn't carry one. Returns "" when the feature isn't in the table.

    Used by /use_feature as the fallback when the client request didn't
    include a ``desc`` field — the mini-sheet's Use button, the GM-tools
    panel, and the cf-use button on the full sheet all hit the same
    endpoint, but only the full sheet's cf-use sends a desc today. v2.43.11
    populates the desc from this table on every path so the roll-log
    card always renders the inline tail next to the feature name.
    """
    feat = _FEATURE_ECONOMY.get((feature_key or "").lower())
    if not feat:
        return ""
    opt_key = (option_key or "").lower() if option_key else None
    if opt_key:
        opt = (feat.get("options") or {}).get(opt_key) or {}
        if opt.get("desc"):
            return str(opt["desc"])
    return str(feat.get("desc") or "")
    parent_slot = feat.get("slot")
    if option_key:
        opt = (feat.get("options") or {}).get(option_key.lower())
        if opt and opt.get("slot"):
            return opt["slot"]
    return parent_slot


def _is_slot_used(campaign_id: int, character_id: int, slot: str) -> bool:
    """Look up the current battle state and return True if ``character_id``'s
    ``slot`` chip is already burnt. Used by Phase 4 over-budget gating to
    decide whether a player click needs a Layer B confirm modal. False on
    "free" / "movement" / "none" / unknown slots, or when no battle is
    active or the character isn't in init.
    """
    if slot not in ("action", "bonus", "reaction"):
        return False
    state = hub.get_battle(campaign_id)
    if not state:
        return False
    for c in state.get("combatants") or []:
        if c.get("char_id") == character_id:
            economy = c.get("economy") or {}
            return bool(economy.get(slot))
    return False


async def _mark_battle_economy(
    campaign_id: int, character_id: int, slot: str, *, used: bool = True,
) -> None:
    """Mark / unmark a PC's action-economy slot in the hub battle state.

    No-op when the campaign has no active battle, the character isn't in
    init, the slot is invalid, or the slot is already at the requested
    state (matches the JS ``_markCombatantEconomy`` idempotence — clicking
    Strike twice doesn't free up your action). Broadcasts ``economy_update``
    so every connected tabletop client (GM included — GM ignores
    ``battle_update`` but listens to this) updates its chip strip.

    v2.17.2: ``used`` keyword arg lets the helper UNMARK a slot
    ("refund" the chip). Used by Action Surge to give the fighter
    their action back after spending the feature. Existing callers
    that pass only positional args (mark-as-used) work unchanged.
    """
    if slot not in ("action", "bonus", "reaction"):
        return
    state = hub.get_battle(campaign_id)
    if not state:
        return
    target = None
    for c in state.get("combatants") or []:
        if c.get("char_id") == character_id:
            target = c
            break
    if target is None:
        return
    economy = target.get("economy")
    if not isinstance(economy, dict):
        economy = {"action": False, "bonus": False, "reaction": False, "movement": 0}
        target["economy"] = economy
    if bool(economy.get(slot)) == bool(used):
        return  # already at the requested state — idempotent
    economy[slot] = bool(used)
    hub.set_battle(campaign_id, state)
    await hub.broadcast(campaign_id, {
        "type": "economy_update",
        "data": {"character_id": character_id, "slot": slot, "used": bool(used)},
    })


# v2.19.0 Phase C.1: buff slot helpers. A "buff" is a structured timed
# effect installed on a combatant in the hub battle state — Rage,
# Hunter's Mark, Hex, Bless, Faerie Fire, etc. Unlike the action-economy
# chips (single bool per slot), buffs are a list per combatant carrying
# (key, name, duration, effects) so the future (B) roll-time intercept
# can read the effects without a separate lookup table.
#
# Storage: ``combatant["buffs"]`` — a list of dicts, each:
#   {
#     "key":               str slug, unique per combatant (rage / hunters-mark / ...),
#     "name":              str display name,
#     "icon":              str emoji,
#     "source_caster_id":  str combatant id of who installed it (for concentration tracking in C.2),
#     "target_combatant_id": str combatant id of who it affects (self for rage),
#     "duration_rounds":   int rounds remaining; client-side tick decrements at turn boundary,
#     "duration_max":      int original duration,
#     "concentration":     bool (C.2 will gate one-at-a-time),
#     "effects":           dict — informational structure read by (B) intercepts (damage_bonus, advantage_on, resistance_to, etc.),
#     "desc":              str short tooltip text,
#   }
#
# Mutations broadcast ``buff_update`` so every connected client refreshes
# its init-tracker badges. The same WS handler runs for install /
# refresh / remove — clients diff against the prior list.

async def _install_buff(
    campaign_id: int, character_id: int, buff: dict,
) -> bool:
    """Install (or replace) a buff on the combatant whose ``char_id``
    matches. Returns True if the install succeeded, False if there's
    no active battle or the character isn't in init. If a buff with
    the same ``key`` already exists, it's overwritten (refresh
    semantics — re-casting Rage extends the duration cleanly).
    Broadcasts ``buff_update`` with the full new buff list for the
    target combatant.

    v2.19.1: when ``buff["concentration"]`` is truthy, the caster can
    only sustain ONE concentration buff at a time RAW — installing a
    new concentration buff drops any existing concentration buff on
    the same combatant first (Hunter's Mark replaces Hex, etc.). This
    matches the RAW "you lose concentration on the previous spell"
    rule. The dropped buff's removal is included in the same
    ``buff_update`` broadcast (single message, one render pass).
    """
    if not isinstance(buff, dict) or not buff.get("key"):
        return False
    state = hub.get_battle(campaign_id)
    if not state:
        return False
    target = None
    for c in state.get("combatants") or []:
        if c.get("char_id") == character_id:
            target = c
            break
    if target is None:
        return False
    buffs = target.get("buffs")
    if not isinstance(buffs, list):
        buffs = []
        target["buffs"] = buffs
    key = str(buff["key"])
    is_concentration = bool(buff.get("concentration"))
    # v2.49.51: if the incoming buff incapacitates the target (and
    # it's not self-cast — rare edge case), snapshot the target's
    # OWN concentration anchors BEFORE the replacement loop chews
    # through them. The 💀 log emission below names the incapacitating
    # buff as the cause, distinct from the concentration-swap mechanic
    # which the existing replacement logic also exercises.
    src_of_new = buff.get("source_char_id")
    incapacitates_target = (
        key in _INCAPACITATING_BUFF_KEYS
        and (src_of_new is None or src_of_new != character_id)
    )
    preexisting_own_anchors: list[tuple[str, str]] = []
    if incapacitates_target:
        for b in buffs:
            b = b or {}
            if not b.get("concentration"):
                continue
            src = b.get("source_char_id")
            if src is not None and src != character_id:
                continue
            anchor_key = b.get("key")
            if anchor_key:
                preexisting_own_anchors.append(
                    (anchor_key, b.get("name") or anchor_key)
                )
    # Build new list: drop the same-key entry (refresh), AND if this is
    # a concentration buff drop any OTHER concentration buff on the
    # combatant (RAW "you can only concentrate on one thing"). The
    # dropped concentration buff(s) ride out on the broadcast so the
    # client renders the swap atomically.
    new_list = []
    replaced_concentration_keys = []
    # v2.49.53: capture the (name, source_char_id) of each replaced
    # concentration buff so the 🔁 GM log below can name the old
    # spell.
    # v2.49.54: source filter at the swap-loop level. RAW's one-
    # concentration-at-a-time rule only applies to the combatant's
    # OWN anchors — a paired condition buff sustained by another
    # caster (e.g. Paralyzed on a Hold Person victim, where source
    # = enemy caster) isn't "the combatant's concentration." Pre-fix,
    # if Magnus was a Hold Person victim AND cast Hex, the swap
    # loop dropped Paralyzed too — wrong, because Tavik (the source
    # caster) is still concentrating on Hold Person. The fix:
    # treat buffs with source_char_id != self as non-swap candidates
    # (keep them in new_list).
    replaced_concentration_meta: list[tuple[str, str, object]] = []
    for b in buffs:
        b = b or {}
        b_key = b.get("key")
        if b_key == key:
            continue  # refresh — drop the old, append the new below
        if is_concentration and b.get("concentration"):
            b_src = b.get("source_char_id")
            if b_src is not None and b_src != character_id:
                # v2.49.54: paired condition from another caster.
                # Keep it; not ours to drop.
                new_list.append(b)
                continue
            replaced_concentration_keys.append(b_key)
            replaced_concentration_meta.append((
                b_key or "",
                b.get("name") or b_key or "Concentration",
                b_src,
            ))
            continue
        new_list.append(b)
    new_list.append(dict(buff))
    target["buffs"] = new_list
    hub.set_battle(campaign_id, state)
    await hub.broadcast(campaign_id, {
        "type": "buff_update",
        "data": {
            "character_id": character_id,
            "buffs": new_list,
            "replaced_concentration": replaced_concentration_keys,
        },
    })
    # v2.38.0 Phase T.3e: when a new concentration buff replaces the
    # caster's previous one, also drop any condition buffs sourced by
    # this caster + flagged concentration on OTHER combatants. The
    # caster lost concentration on the previous spell; its paired
    # effects (Paralyzed via Hold Person, Frightened via Fear, …)
    # drop in lock-step.
    if is_concentration and replaced_concentration_keys:
        await _drop_paired_concentration_buffs(campaign_id, character_id)
    # v2.49.51: RAW PHB p.203 — "you also lose concentration on a
    # spell if you are incapacitated." Drop the target's pre-existing
    # OWN concentration anchors AND emit a 💀 log naming the cause.
    # When the incapacitating buff is concentration=True (Paralyzed
    # via Hold Person, Incapacitated via Hideous Laughter), the
    # replacement loop above has already removed the anchor — we
    # only need to emit the log. When the incapacitating buff is
    # concentration=False (e.g. Sleep), the anchor is still in
    # new_list and we explicitly remove it here.
    if incapacitates_target and preexisting_own_anchors:
        buff_label = buff.get("name") or key
        caster_name = target.get("name") or "Unknown"
        current_keys = {(b or {}).get("key") for b in new_list}
        for anchor_key, anchor_name in preexisting_own_anchors:
            # If the anchor survived the replacement (incapacitating
            # buff was concentration=False), remove it now via the
            # full _remove_buff path so paired cleanup + buff_update
            # broadcast both fire.
            if anchor_key in current_keys:
                await _remove_buff(campaign_id, character_id, anchor_key)
            await hub.broadcast(campaign_id, {
                "type": "roll",
                "data": {
                    "expression": "—",
                    "total": 0,
                    "breakdown": f"Concentration ends — incapacitated ({buff_label})",
                    "note": f"💀 {caster_name} lost concentration on {anchor_name}",
                    "visibility": Visibility.GM_ONLY.value,
                    "user_id": None,
                    "user_name": "GM log",
                    "char_name": caster_name,
                },
            })
    # v2.49.53: 🔁 GM log when a new concentration cast voluntarily
    # replaces an existing anchor the caster owned (one-at-a-time
    # rule, RAW "you lose concentration on the previous spell").
    # Filtered out when incapacitates_target is True — that path
    # already emits 💀 above with the correct RAW cause; the swap
    # is the mechanical cleanup, not the reason.
    if (
        is_concentration
        and replaced_concentration_meta
        and not incapacitates_target
    ):
        new_name = buff.get("name") or key
        caster_name = target.get("name") or "Unknown"
        for _, old_name, old_src in replaced_concentration_meta:
            # Only log swaps of anchors the caster owned. A paired
            # condition buff (concentration=True but source=enemy)
            # would be wrongly dragged out by the swap loop today
            # — filed as a follow-up bug; for now skip the log.
            if old_src is not None and old_src != character_id:
                continue
            await hub.broadcast(campaign_id, {
                "type": "roll",
                "data": {
                    "expression": "—",
                    "total": 0,
                    "breakdown": f"Concentration swapped — cast {new_name}",
                    "note": (
                        f"🔁 {caster_name} swapped concentration: "
                        f"{old_name} → {new_name}"
                    ),
                    "visibility": Visibility.GM_ONLY.value,
                    "user_id": None,
                    "user_name": "GM log",
                    "char_name": caster_name,
                },
            })
    return True


# v2.32.0 Phase T.3c: save-or-suck condition mapping. Keyed by the
# spell's ``_slug`` (resolved from the SRD JSON or demo seed). Each
# entry describes the condition installed on the target when their
# save fails — name + key (matches D&D 5e condition vocabulary) +
# duration + concentration flag + a list of mechanical effects the
# mini-sheet can surface. Save-or-suck spells without a damage roll
# look up this map after the save resolves; failing the save
# installs the buff on the target via _install_buff_on_combatant_id.
# Expand this dict to support more spells; the empty case skips the
# install gracefully.
_SPELL_CONDITION_MAP = {
    "hold-person": {
        "key": "paralyzed",
        "name": "Paralyzed",
        "icon": "🥶",
        "duration_rounds": 10,  # 1 minute (10 rounds at 6s/round)
        "concentration": True,
        "effects": [
            "incapacitated",
            "auto-fail STR / DEX saves",
            "attacks vs target have advantage",
            "melee within 5 ft auto-crits",
        ],
    },
    "hold-monster": {
        "key": "paralyzed",
        "name": "Paralyzed",
        "icon": "🥶",
        "duration_rounds": 10,
        "concentration": True,
        "effects": [
            "incapacitated",
            "auto-fail STR / DEX saves",
            "attacks vs target have advantage",
            "melee within 5 ft auto-crits",
        ],
    },
    "charm-person": {
        "key": "charmed",
        "name": "Charmed",
        "icon": "💗",
        "duration_rounds": 600,  # 1 hour
        "concentration": False,
        "effects": [
            "regards caster as friendly",
            "advantage on social interactions with caster",
        ],
    },
    "fear": {
        "key": "frightened",
        "name": "Frightened",
        "icon": "😱",
        "duration_rounds": 10,
        "concentration": True,
        "effects": [
            "disadvantage on ability checks / attacks while caster in sight",
            "can't willingly move closer to caster",
            "drops what it's holding",
        ],
    },
    "hideous-laughter": {
        "key": "incapacitated",
        "name": "Incapacitated (Laughing)",
        "icon": "🤣",
        "duration_rounds": 10,
        "concentration": True,
        "effects": [
            "prone",
            "incapacitated — no actions or reactions",
            "saves again at end of each turn",
        ],
    },
    # v2.49.55: Monk Stunning Strike (class feature). Used by the
    # /use_stunning_strike endpoint via the same save-or-suck pipeline
    # as Hold Person etc. The Stunned condition is NOT a concentration
    # effect (1-turn duration, RAW), so this entry exercises the v2.49.51
    # "incapacitating buff with concentration=False" branch — installing
    # Stunned on a PC drops their own concentration anchors via the
    # _install_buff incapacitation hook.
    "stunning-strike": {
        "key": "stunned",
        "name": "Stunned",
        "icon": "✨",
        "duration_rounds": 1,
        "concentration": False,
        "effects": [
            "incapacitated — no actions or reactions",
            "can't move, speaks falteringly",
            "auto-fail STR / DEX saves",
            "attacks vs target have advantage",
        ],
    },
    # v2.49.57: Monk Open Hand Technique — "prone" mode. Used by the
    # /use_open_hand_technique endpoint, which routes the DEX-save
    # rider through the same save-or-suck pipeline as Stunning Strike.
    # Prone has no RAW timer (ends when target spends half movement
    # to stand); 10 rounds is a generous default and the GM ends it
    # via /end_buff when the target stands. NOT in _INCAPACITATING_BUFF_KEYS
    # — Prone constrains movement / grants advantage-disadvantage to
    # nearby attackers, but doesn't incapacitate.
    "open-hand-prone": {
        "key": "prone",
        "name": "Prone",
        "icon": "🫳",
        "duration_rounds": 10,
        "concentration": False,
        "effects": [
            "movement costs double to crawl; rising costs half speed",
            "disadvantage on attack rolls while prone",
            "attacks against prone target: advantage within 5 ft, disadvantage at range",
        ],
    },
}


# v2.49.51 — RAW (PHB p.290 condition definitions): these condition
# buff keys all imply the "incapacitated" state, which RAW (PHB p.203
# concentration rules) ends any concentration the affected creature
# is sustaining. Used by ``_install_buff`` to call
# ``_drop_caster_concentration`` on the TARGET when the buff lands.
# Charmed and Frightened are NOT in this set — those conditions
# constrain action choice but don't incapacitate.
_INCAPACITATING_BUFF_KEYS = frozenset({
    "paralyzed",      # Hold Person, Hold Monster
    "incapacitated",  # Hideous Laughter (and the generic state)
    "stunned",        # Stunning Strike, Power Word Stun
    "petrified",      # Flesh to Stone
    "unconscious",    # Sleep, knockout
    "asleep",         # alt key surface for Sleep
})


async def _install_buff_on_combatant_id(
    campaign_id: int, combatant_id: str, buff: dict,
) -> bool:
    """v2.32.0 Phase T.3c — NPC-friendly buff installer. Mutates the
    target combatant's ``buffs`` list in the hub state and broadcasts
    ``battle_update`` (NPCs don't have a Character row, so the
    ``buff_update`` broadcast that ``_install_buff`` uses for PCs
    isn't routable here). Refresh semantics: re-casting the same
    condition replaces the existing entry on the same combatant.
    """
    if not isinstance(buff, dict) or not buff.get("key"):
        return False
    state = hub.get_battle(campaign_id)
    if not state:
        return False
    target = None
    for c in state.get("combatants") or []:
        if c.get("id") == combatant_id:
            target = c
            break
    if target is None:
        return False
    buffs = target.get("buffs")
    if not isinstance(buffs, list):
        buffs = []
        target["buffs"] = buffs
    key = str(buff["key"])
    new_list = [b for b in buffs if (b or {}).get("key") != key]
    new_list.append(dict(buff))
    target["buffs"] = new_list
    hub.set_battle(campaign_id, state)
    # v2.49.43 — server-initiated state change, so force_gm_sync (see
    # v2.49.40 for the broader audit). Without it the GM ignores the
    # broadcast and a freshly-installed NPC buff (e.g. Paralyzed on a
    # bandit from Hold Person) only shows up after the next push.
    await hub.broadcast(campaign_id, {
        "type": "battle_update",
        "data": state,
        "force_gm_sync": True,
    })
    return True


def _concentration_buff_for(
    campaign_id: int, character_id: int,
) -> dict | None:
    """Return the (single) concentration buff active on the combatant,
    or None. There can be at most one per combatant — ``_install_buff``
    enforces the invariant. Used by the concentration-save hook to
    decide whether a damage event needs to trigger a save.
    """
    for b in _get_buffs(campaign_id, character_id):
        if (b or {}).get("concentration"):
            return b
    return None


async def _maybe_concentration_save(
    campaign_id: int, char: Character, damage_amount: int,
    db: Session | None = None,
) -> dict | None:
    """If the character is concentrating on a buff and just took
    ``damage_amount`` damage, roll a CON save (DC = max(10, damage //
    2)) and act on the result. Returns ``None`` if no concentration
    buff is active or no damage was taken; otherwise returns
    ``{rolled, total, dc, passed, dropped_key}`` and broadcasts a
    ``concentration_save`` event. On fail, the concentration buff is
    removed via ``_remove_buff`` (which fires its own ``buff_update``).

    v2.19.1: auto-roll keeps the player UX consistent with the rest of
    the demo's "click → roll → result" loop. Players who prefer to
    hand-roll their concentration save can reinstall the buff after a
    miss; the GM can also rebroadcast via /use_rage / /cast_hunters_mark
    / /cast_hex.
    """
    if damage_amount <= 0:
        return None
    buff = _concentration_buff_for(campaign_id, char.id)
    if buff is None:
        return None

    # DC = max(10, damage // 2). Floor division per RAW.
    dc = max(10, damage_amount // 2)
    sheet = dict(char.sheet or {})
    abilities = dict(sheet.get("abilities") or {})
    con_score = int(abilities.get("CON") or 10)
    con_mod = (con_score - 10) // 2
    # CON save proficiency? RAW: Barbarian + Fighter + Sorcerer have
    # CON save proficiency; nothing else on the demo's PC roster. War
    # Caster / Resilient (CON) feats also grant it, but neither is in
    # the demo today — defer feat-driven proficiency to a future commit.
    saves = dict(sheet.get("saving_throws") or {})
    pb = int(sheet.get("proficiency_bonus") or 0)
    prof_bonus = pb if saves.get("CON") else 0
    bonus = con_mod + prof_bonus

    # v2.49.48 — RAW: a creature loses concentration AUTOMATICALLY
    # if its hit points drop to 0 (PHB p.203), independent of the
    # CON save. Pre-fix the server still rolled the save and could
    # leave a dying / dead PC concentrating on Hex / Hunter's Mark
    # / Hold Person if they happened to pass — visible as the chip
    # staying on the unconscious PC's row, the marked target still
    # taking +1d6 necrotic, etc. The CON save still happens for
    # damage that doesn't drop to 0 (the standard branch). When at
    # 0 HP we still roll for telemetry but force passed=False so
    # the existing _remove_buff path runs.
    hp_current_after = int((sheet.get("hp") or {}).get("current") or 0)
    forced_drop_on_zero_hp = hp_current_after <= 0

    try:
        result = dice_mod.roll(f"1d20+{bonus}" if bonus >= 0 else f"1d20{bonus}")
        total = result.total
        raw = total - bonus  # the d20 face value
    except dice_mod.DiceParseError:
        raw = 10
        total = 10 + bonus

    passed = (total >= dc) and not forced_drop_on_zero_hp
    dropped_key = None
    paired_pre_drop: list[dict] = []
    if not passed:
        dropped_key = buff.get("key")
        if dropped_key:
            # v2.39.0: capture the paired buffs about to drop BEFORE
            # ``_remove_buff`` triggers the cleanup helper. We need
            # the list of (combatant_name, buff_name) tuples to
            # build the GM-only roll-log entry below — the helper
            # mutates state, so reading after the call would return
            # an empty list.
            state_snapshot = hub.get_battle(campaign_id)
            if state_snapshot:
                for c in state_snapshot.get("combatants") or []:
                    for b in c.get("buffs") or []:
                        b = b or {}
                        if (
                            b.get("source_char_id") == char.id
                            and bool(b.get("concentration"))
                            and b.get("key") != dropped_key
                        ):
                            paired_pre_drop.append({
                                "combatant_name": c.get("name") or "Unknown",
                                "buff_name": b.get("name") or b.get("key") or "Effect",
                            })
            await _remove_buff(campaign_id, char.id, dropped_key)
            # v2.19.2 Phase C.3: sync the sheet mirror so the Active
            # Effects panel updates when concentration breaks mid-fight.
            if db is not None:
                _mirror_buffs_to_sheet(
                    db, char.id, _get_buffs(campaign_id, char.id),
                )

    await hub.broadcast(campaign_id, {
        "type": "concentration_save",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "buff_key": buff.get("key"),
            "buff_name": buff.get("name"),
            "damage_amount": damage_amount,
            "dc": dc,
            "rolled": raw,
            "bonus": bonus,
            "total": total,
            "passed": passed,
            # v2.49.48 — distinguishes the RAW "drops to 0 HP" forced
            # drop from a regular failed save, so the client roll-log
            # can render "💀 Concentration broken (0 HP)" instead of
            # "❌ Concentration save failed". Always present; True
            # only when the drop was forced regardless of roll outcome.
            "forced_drop_on_zero_hp": forced_drop_on_zero_hp,
            "dropped_key": dropped_key,
        },
    })

    # v2.39.0: GM-only narrative roll-log entry summarising the
    # concentration loss + the paired effects that dropped. Players
    # see their own buff vanish via the buff_update broadcast and
    # the concentration_save toast; the GM gets an extra log entry
    # naming exactly what was let go (Hold Person on Bandit Alpha,
    # etc.) so cleanup is auditable from one place.
    if not passed:
        buff_name = buff.get("name") or buff.get("key") or "concentration"
        if paired_pre_drop:
            paired_summary = " · ".join(
                f"{p['buff_name']} → {p['combatant_name']}"
                for p in paired_pre_drop
            )
            paired_note = f" — dropped: {paired_summary}"
        else:
            paired_note = ""
        # v2.49.50 — distinguish 💀 forced 0-HP drop from 💔 failed
        # CON save. The save was still ROLLED for telemetry parity
        # (existing tests assert on rolled/total/bonus) but a 0-HP
        # drop is conceptually different — the rule ended the spell,
        # not the save. The breakdown shows what the save would have
        # been so the GM can see whether the roll itself was a pass.
        if forced_drop_on_zero_hp:
            emoji = "💀"
            would_have_been = (
                f"1d20[{raw}]{'+' if bonus >= 0 else ''}{bonus} = {total} vs DC {dc}"
                if bonus != 0 else
                f"1d20[{raw}] = {total} vs DC {dc}"
            )
            gm_log_breakdown = (
                f"Concentration ends — incapacitated (0 HP) — "
                f"save would have been {would_have_been}"
            )
        else:
            emoji = "💔"
            gm_log_breakdown = (
                f"1d20[{raw}]{'+' if bonus >= 0 else ''}{bonus} = {total} vs DC {dc} — ✗ Failed"
                if bonus != 0 else
                f"1d20[{raw}] = {total} vs DC {dc} — ✗ Failed"
            )
        await hub.broadcast(campaign_id, {
            "type": "roll",
            "data": {
                "expression": "1d20",
                "total": total,
                "breakdown": gm_log_breakdown,
                "note": (
                    f"{emoji} {char.name} lost concentration on {buff_name}"
                    f"{paired_note}"
                ),
                "visibility": Visibility.GM_ONLY.value,
                "user_id": None,
                "user_name": "GM log",
                "char_name": char.name,
            },
        })

    return {
        "rolled": raw,
        "total": total,
        "dc": dc,
        "passed": passed,
        "dropped_key": dropped_key,
    }


async def _drop_paired_concentration_buffs(
    campaign_id: int, caster_char_id: int,
) -> list[dict]:
    """v2.38.0 Phase T.3e: when a caster's concentration drops (broke
    on damage, was replaced by a new concentration cast, or was ended
    manually), scan every combatant in init and remove buffs they
    granted under that concentration. T.3c/T.3d install Paralyzed /
    Charmed / Frightened conditions with ``source_char_id: <caster>``
    + ``concentration: True``; this helper drops them in lock-step
    with the caster's concentration buff.

    Returns the list of removed buff dicts (each shape preserved,
    plus ``_dropped_from_combatant_id`` field) so the caller can log.
    Broadcasts a single ``battle_update`` covering all removals.
    """
    state = hub.get_battle(campaign_id)
    if not state:
        return []
    removed: list[dict] = []
    dirty = False
    for c in state.get("combatants") or []:
        buffs = c.get("buffs") or []
        kept = []
        for b in buffs:
            b = b or {}
            if (
                b.get("source_char_id") == caster_char_id
                and bool(b.get("concentration"))
            ):
                rec = dict(b)
                rec["_dropped_from_combatant_id"] = c.get("id")
                removed.append(rec)
                continue
            kept.append(b)
        if len(kept) != len(buffs):
            c["buffs"] = kept
            dirty = True
    if dirty:
        hub.set_battle(campaign_id, state)
        # v2.49.43 — server-initiated paired-buff cleanup, force_gm_sync
        # (see v2.49.40 audit). Without it the GM's view of "concentration
        # ended → all paired buffs dropped" only updates on the next push.
        await hub.broadcast(campaign_id, {
            "type": "battle_update",
            "data": state,
            "force_gm_sync": True,
        })
    # v2.49.0 — also clear any persistent AoE markers this caster
    # placed (Spirit Guardians, Hypnotic Pattern, etc.). The marker
    # is keyed to the caster's concentration; once concentration
    # breaks, the marker should vanish from the map.
    await _clear_caster_concentration_aoes(campaign_id, caster_char_id)
    return removed


async def _remove_buff(
    campaign_id: int, character_id: int, key: str,
) -> bool:
    """Remove a single buff by key. Returns True if removed, False if
    nothing matched. Broadcasts ``buff_update`` with the new (possibly
    empty) buff list when a removal happened; no-op silently otherwise.

    v2.38.0 Phase T.3e: if the removed buff was a concentration buff,
    also scans all combatants for paired condition buffs (Hold
    Person's Paralyzed, Fear's Frightened, …) sourced by this
    character and removes them too — RAW concentration cleanup.
    """
    state = hub.get_battle(campaign_id)
    if not state:
        return False
    target = None
    for c in state.get("combatants") or []:
        if c.get("char_id") == character_id:
            target = c
            break
    if target is None:
        return False
    buffs = target.get("buffs") or []
    # Capture the buff we're about to remove so we know whether it's
    # a concentration buff (drives the paired-cleanup decision).
    removed_buff = next(
        (b for b in buffs if (b or {}).get("key") == key), None,
    )
    new_list = [b for b in buffs if (b or {}).get("key") != key]
    if len(new_list) == len(buffs):
        return False
    target["buffs"] = new_list
    hub.set_battle(campaign_id, state)
    await hub.broadcast(campaign_id, {
        "type": "buff_update",
        "data": {
            "character_id": character_id,
            "buffs": new_list,
            "removed_key": key,
        },
    })
    if removed_buff and bool(removed_buff.get("concentration")):
        await _drop_paired_concentration_buffs(campaign_id, character_id)
    return True


# v2.49.61 — Sleep wake-on-damage hook. RAW (PHB Sleep): "each creature
# affected by this spell falls unconscious until the spell ends, THE
# SLEEPER TAKES DAMAGE, or someone uses an action to shake or slap the
# sleeper awake." The damage pipeline calls this helper after applying
# damage; if the target has an Unconscious buff with `source_spell ==
# "Sleep"`, the buff is removed and a public 🌅 roll-log entry fires.
# Scoped tightly to `source_spell == "Sleep"` so other Unconscious
# sources (a future Power Word Knockout, etc.) aren't accidentally
# cleared by stray damage. The dying-at-0-HP state lives on
# `Character.sheet.death_saves`, NOT in a buff, so it's untouched.
async def _wake_sleeping_on_damage(
    campaign_id: int,
    character_id: int | None,
    combatant_id: str | None,
    damage_applied: int,
    *,
    db: Session | None = None,
) -> None:
    """If damage > 0 lands on a target carrying a Sleep-sourced
    Unconscious buff, remove the buff + emit a wake log.

    No-op when ``damage_applied <= 0`` (resistance reduced to 0 → no
    damage taken → no wake, RAW). No-op when the target has no
    Unconscious buff or the buff was sourced by something other than
    Sleep. Either ``character_id`` (PC) or ``combatant_id`` (NPC) is
    required; PC takes precedence when both are set.
    """
    if damage_applied <= 0:
        return
    state = hub.get_battle(campaign_id)
    if not state:
        return
    target = None
    for c in state.get("combatants") or []:
        if character_id and c.get("char_id") == character_id:
            target = c
            break
        if combatant_id and c.get("id") == combatant_id and not character_id:
            target = c
            break
    if target is None:
        return
    buffs = list(target.get("buffs") or [])
    sleep_keys = [
        b.get("key") for b in buffs
        if (b or {}).get("key") in ("unconscious", "asleep")
        and (b or {}).get("source_spell") == "Sleep"
    ]
    if not sleep_keys:
        return
    if character_id:
        # PC path: route through _remove_buff so the buff_update
        # broadcast + paired-cleanup hook (no-op for concentration=
        # False Sleep buffs) fire consistently.
        for key in sleep_keys:
            await _remove_buff(campaign_id, int(character_id), key)
        # Keep the sheet mirror in sync — cast_sleep's install path
        # mirrors via _mirror_buffs_to_sheet, so the removal should too.
        if db is not None:
            _mirror_buffs_to_sheet(
                db, int(character_id),
                _get_buffs(campaign_id, int(character_id)),
            )
    else:
        # NPC path: mutate the combatant's buff list + broadcast
        # battle_update with force_gm_sync (mirrors the v2.49.40 NPC
        # HP-damage pattern in _apply_damage_to_combatant).
        new_list = [
            b for b in buffs
            if not (
                (b or {}).get("key") in ("unconscious", "asleep")
                and (b or {}).get("source_spell") == "Sleep"
            )
        ]
        target["buffs"] = new_list
        hub.set_battle(campaign_id, state)
        await hub.broadcast(campaign_id, {
            "type": "battle_update",
            "data": state,
            "force_gm_sync": True,
        })
    # Public wake log.
    target_name = target.get("name") or "Unknown"
    await hub.broadcast(campaign_id, {
        "type": "roll",
        "data": {
            "expression": "—",
            "total": 0,
            "breakdown": "Damage wakes the sleeper — Sleep ends (RAW PHB Sleep)",
            "note": f"🌅 {target_name} wakes — damaged",
            "user_name": "GM log",
            "char_name": target_name,
            "visibility": Visibility.PUBLIC.value,
        },
    })


def _get_buffs(campaign_id: int, character_id: int) -> list[dict]:
    """Read helper: return the current buff list for a character (or
    empty list if no battle / not in init). Read-only — never mutates.
    """
    state = hub.get_battle(campaign_id)
    if not state:
        return []
    for c in state.get("combatants") or []:
        if c.get("char_id") == character_id:
            return list(c.get("buffs") or [])
    return []


def _lookup_combatant_name(campaign_id: int, combatant_id: str | None) -> str:
    """v2.23.0 Phase T.8: resolve a hub combatant id to its display
    name. Returns the empty string when ``combatant_id`` is falsy, no
    battle is active, or the combatant isn't in init. Used by the
    /attack broadcast so the chat card can render ``→ NAME`` without
    a second client lookup.
    """
    if not combatant_id:
        return ""
    state = hub.get_battle(campaign_id)
    if not state:
        return ""
    for c in state.get("combatants") or []:
        if c.get("id") == combatant_id:
            return c.get("name") or ""
    return ""


def _lookup_combatant(campaign_id: int, combatant_id: str | None) -> dict | None:
    """v2.24.0 Phase T.2: return the full combatant dict (or None)."""
    if not combatant_id:
        return None
    state = hub.get_battle(campaign_id)
    if not state:
        return None
    for c in state.get("combatants") or []:
        if c.get("id") == combatant_id:
            return c
    return None


# v2.49.73 — distance-on-grid primitive. Extracted from token_move
# (line ~5040, formerly inline). Matches the JS _computeRulerDistanceFt
# math exactly so server-side range checks and client-side ruler
# readings agree to the foot. Chebyshev (RAW 5e "5-5-5" diagonals) on
# square grids; Euclidean on hex / no-grid. 5 ft per cell, rounded to
# 0.1 ft. Returns 0.0 when grid_size_px <= 0 (no-grid maps have no
# meaningful distance concept — same fallback as token_move had).
# Phase 2A of docs/plans/ruler-and-range.md. Phase 2B/C/D will call
# this from the range-enforcement check sites.
def _distance_ft_between_points(
    grid_size_px: int, grid_type: str,
    ax: float, ay: float, bx: float, by: float,
) -> float:
    if grid_size_px <= 0:
        return 0.0
    dx = bx - ax
    dy = by - ay
    if (grid_type or "square").lower() == "square":
        cells = max(abs(dx), abs(dy)) / grid_size_px
    else:
        cells = (dx * dx + dy * dy) ** 0.5 / grid_size_px
    return round(cells * 5, 1)


# v2.49.75 — Phase 2C range-enforcement helper. Given a caster + a
# spell / weapon range string + a target descriptor, returns either
# None (in range / unchecked / overridden) or an error dict suitable
# for a 409 ``out_of_range`` response. The contract is shared by all
# cast / attack endpoints in Phase 2C (cast_spell) + Phase 2D
# (cast_hex, cast_sleep, attack, use_stunning_strike,
# use_open_hand_technique).
#
# Override semantics — three tiers, mirrors the existing Phase 4
# over-budget gate:
#   - GM: auto-bypass. The GM is the rules authority and may
#     narrate a cast at any distance.
#   - Player + override_range=True + strict mode off: bypass.
#   - Player + override_range=True + strict mode on: still enforced
#     (strict mode disables player-side overrides).
#
# Skip semantics — return None (no 409) when:
#   - The spell range parses to None (Special / Unlimited / Sight /
#     unknown — content we don't understand, trust the GM).
#   - The spell range is 0 (Self / Self+radius — no target distance).
#   - The campaign has no active map (off-map narrative cast).
#   - The caster has no token on the active map.
#   - The target has no token on the active map.
#
# Returns the 409 error dict shape documented in
# docs/plans/ruler-and-range.md Phase 2.
def _check_cast_range(
    db: Session,
    campaign: Campaign,
    caster_char: Character,
    spell_range_str: str,
    spell_name: str,
    target_combatant_id: str | None,
    target_character_id: int | None,
    target_name_in: str | None,
    *,
    override_range: bool,
    user_is_gm: bool,
    strict: bool,
) -> dict | None:
    # Tier 1: GM bypass.
    if user_is_gm:
        return None
    # Tier 2: player + override + not strict.
    if override_range and not strict:
        return None
    # Parse the range string. None / 0 → skip the check.
    from ..content.range_parser import max_range_ft, parse_range_ft
    max_ft = max_range_ft(parse_range_ft(spell_range_str))
    if max_ft is None or max_ft <= 0:
        return None
    # Resolve the active map.
    map_id = campaign.active_map_id
    if not map_id:
        return None
    map_row = db.query(Map).filter(Map.id == map_id).first()
    if not map_row:
        return None
    # Caster token on the active map.
    caster_token = (
        db.query(Token)
        .filter(Token.character_id == caster_char.id, Token.map_id == map_id)
        .first()
    )
    if not caster_token:
        return None
    # Target token + display name.
    target_pos, target_name = _resolve_target_token_pos(
        db, campaign.id, map_id,
        target_combatant_id, target_character_id, target_name_in,
    )
    if target_pos is None:
        return None
    # Distance.
    distance_ft = _distance_ft_between_points(
        int(map_row.grid_size_px or 0),
        (map_row.grid_type.value if map_row.grid_type else "square").lower(),
        float(caster_token.x or 0), float(caster_token.y or 0),
        target_pos[0], target_pos[1],
    )
    if distance_ft <= max_ft:
        return None
    return {
        "error": "out_of_range",
        "source_name": caster_char.name,
        "target_name": target_name or "",
        "distance_ft": distance_ft,
        "range_ft": int(max_ft),
        "spell_name": spell_name or "",
    }


def _resolve_target_token_pos(
    db: Session,
    campaign_id: int,
    map_id: int,
    target_combatant_id: str | None,
    target_character_id: int | None,
    target_name_in: str | None = None,
) -> tuple[tuple[float, float] | None, str]:
    """Return ((x, y), display_name) for the target — or (None, name)
    if the target has no token on the given map (off-map / synthesized
    target).

    Resolution order:
      1. ``target_combatant_id`` → hub state → ``source_token_id`` for
         NPCs, ``char_id`` → Token row for PCs.
      2. ``target_character_id`` → Token row directly.
      3. Fallback to ``target_name_in`` for the display name; pos = None.
    """
    name_out = target_name_in or ""
    # Step 1: combatant id lookup.
    if target_combatant_id:
        combatant = _lookup_combatant(campaign_id, target_combatant_id)
        if combatant:
            name_out = combatant.get("name") or name_out
            src_token_id = combatant.get("source_token_id")
            if src_token_id:
                t = db.query(Token).filter(
                    Token.id == int(src_token_id), Token.map_id == map_id,
                ).first()
                if t:
                    return (float(t.x or 0), float(t.y or 0)), name_out
            ccid = combatant.get("char_id")
            if ccid:
                t = (
                    db.query(Token)
                    .filter(Token.character_id == int(ccid), Token.map_id == map_id)
                    .first()
                )
                if t:
                    return (float(t.x or 0), float(t.y or 0)), name_out
    # Step 2: character id fallback.
    if target_character_id:
        t = (
            db.query(Token)
            .filter(Token.character_id == int(target_character_id), Token.map_id == map_id)
            .first()
        )
        if t:
            if not name_out:
                ch = db.query(Character).filter(Character.id == int(target_character_id)).first()
                name_out = ch.name if ch else name_out
            return (float(t.x or 0), float(t.y or 0)), name_out
    # Step 3: no token found.
    return None, name_out


def _read_target_ac(
    db: Session, campaign_id: int, combatant: dict | None,
) -> int:
    """v2.24.0 Phase T.2: read the target's AC for hit determination.

    Resolution order:
    1. PC combatant (has ``char_id``): ``character.sheet["ac"]``.
    2. Monster combatant (has ``token_template_id``): the template's
       ``sheet["armor_class"]`` or ``sheet["ac"]``.
    3. Fallback: 10 (DC for an unarmored medium creature; matches the
       SRD default when AC is missing).

    Returns 10 on any lookup miss so the hit determination still
    produces a sane comparison rather than skipping it.
    """
    if not combatant:
        return 10
    char_id = combatant.get("char_id")
    if char_id:
        char = db.query(Character).filter(Character.id == char_id).first()
        if char:
            ac = (char.sheet or {}).get("ac")
            try:
                return int(ac) if ac is not None else 10
            except (TypeError, ValueError):
                return 10
    tmpl_id = combatant.get("token_template_id")
    if tmpl_id:
        tmpl = db.query(TokenTemplate).filter(TokenTemplate.id == tmpl_id).first()
        if tmpl:
            sheet = tmpl.sheet or {}
            ac = sheet.get("armor_class") or sheet.get("ac")
            try:
                return int(ac) if ac is not None else 10
            except (TypeError, ValueError):
                return 10
    return 10


def _pick_damage_tier(scaling: list | None, level: int) -> dict | None:
    """v2.36.0 Phase T.4c: pick the highest-level entry from an
    ``action.damage_scaling`` list whose ``level`` is ≤ the caster's
    character level. Server-side mirror of the JS ``_pickDamageTier``
    in ``action_buttons.js`` so cantrip damage scales correctly when
    /cast_spell auto-rolls the attack (e.g. Fire Bolt 1d10 at L1-4
    → 2d10 at L5-10 → 3d10 at L11-16 → 4d10 at L17). Returns the
    matching tier dict (or None if no tier qualifies)."""
    if not scaling or not isinstance(scaling, list):
        return None
    eligible = [t for t in scaling if isinstance(t, dict) and int(t.get("level") or 1) <= level]
    if not eligible:
        return None
    eligible.sort(key=lambda t: int(t.get("level") or 0), reverse=True)
    return eligible[0]


def _double_dice_for_crit(expr: str) -> str:
    """v2.24.0 Phase T.2: RAW crit doubles weapon damage DICE (not the
    flat modifier). ``1d12+4`` becomes ``2d12+4``; ``2d6+3`` becomes
    ``4d6+3``. Preserves flat modifiers untouched. Works on
    multi-die-group expressions like ``1d8+1d4+5`` by doubling each
    die-group it finds.

    Implementation: regex-substitute every ``Nd...`` token (with
    optional sign prefix) by ``(2N)d...``. Leaves +N / -N flat
    modifiers alone.
    """
    import re as _re
    if not expr or not expr.strip():
        return expr
    def _double(m: "_re.Match[str]") -> str:
        sign = m.group("sign") or ""
        count = int(m.group("count") or 1)
        sides = m.group("sides")
        mod = m.group("mod") or ""
        return f"{sign}{count * 2}d{sides}{mod}"
    pat = _re.compile(
        r"(?P<sign>[+-])?(?P<count>\d*)d(?P<sides>\d+)(?P<mod>(?:kh|kl|a|d)\d*)?",
        _re.IGNORECASE,
    )
    return pat.sub(_double, expr)


# v2.24.0 Phase T.2: in-memory log of recent damage applications per
# attack_id so the rolling player can undo their last hit if they
# misclicked. Keyed by attack_id; entry holds the campaign, the target
# (char_id OR combatant_id), and the actual HP delta applied. Capped
# implicitly by clear-on-restart + the ``_purge_attack_damage_log``
# call at write time (drops entries older than 8 hours).
_attack_damage_log: dict[str, dict] = {}


def _purge_attack_damage_log() -> None:
    """Drop entries older than 8 hours so an idle demo doesn't grow
    the dict unbounded. Called at every write site."""
    cutoff = _time.time() - 8 * 3600
    stale = [k for k, v in _attack_damage_log.items() if v.get("ts", 0) < cutoff]
    for k in stale:
        _attack_damage_log.pop(k, None)


# v2.37.0 Phase T.3d: side-channel context for PC save-or-suck spells.
# When ``/cast_spell`` creates a RollRequest for a PC-targeted save
# spell (Hold Person at a player ally), we stash the spell's slug +
# the target's character_id here so that when the PC clicks Roll on
# their prompt — which lands in ``/roll_request/{id}/respond`` —
# we can install the matching condition buff on the PC if they
# failed the save. Keyed by ``roll_request.id``. 8-hour TTL.
_save_request_context: dict[int, dict] = {}


def _purge_save_request_context() -> None:
    cutoff = _time.time() - 8 * 3600
    stale = [k for k, v in _save_request_context.items() if v.get("ts", 0) < cutoff]
    for k in stale:
        _save_request_context.pop(k, None)


# v2.48.0 Phase T.5e: caster-gated AoE placement. When an AoE spell
# (Fireball / Burning Hands / etc.) is cast WITHOUT a target list,
# the cast card lands in "pending placement" state — the caster (or
# GM) sees a "📍 Place AoE" button on the card that, when clicked,
# opens the on-canvas placement picker and POSTs ``/place_aoe`` with
# the swept-up target_combatant_ids. The stash carries everything
# the place_aoe endpoint needs to resolve targets: damage expr,
# damage type, save ability, DC, the auto_apply_damage flag the
# campaign had at cast time, the caster id (for auth), the spell
# slug/name (for the broadcast metadata). Keyed by cast_id; 8-hour
# TTL same as the save-request context.
_pending_aoe_casts: dict[str, dict] = {}


def _purge_pending_aoe_casts() -> None:
    cutoff = _time.time() - 8 * 3600
    stale = [k for k, v in _pending_aoe_casts.items() if v.get("ts", 0) < cutoff]
    for k in stale:
        _pending_aoe_casts.pop(k, None)


# v2.49.0 — persistent AoE markers for concentration spells. When a
# concentration AoE (Spirit Guardians, Hypnotic Pattern, Sleet Storm,
# etc.) is placed, the marker stays on the map until the caster's
# concentration breaks. Cleared via ``_clear_caster_concentration_aoes``
# from the existing concentration-cleanup helpers
# (``_drop_paired_concentration_buffs``, the concentration save
# failure path). Keyed by campaign_id; value is a list of marker
# dicts. Each marker carries everything the client needs to render
# the shape (shape, size, center, caster_char_id for self-anchored
# shapes) AND everything the future re-trigger-on-enter follow-up
# will need (dc, damage_expr, damage_type, save_ability).
_concentration_aoes: dict[int, list[dict]] = {}


async def _broadcast_concentration_aoes(campaign_id: int) -> None:
    await hub.broadcast(campaign_id, {
        "type": "concentration_aoe_update",
        "data": {
            "markers": list(_concentration_aoes.get(campaign_id, [])),
        },
    })


async def _clear_caster_concentration_aoes(
    campaign_id: int, caster_char_id: int,
) -> bool:
    """Drop every persistent AoE marker placed by this caster + tell
    every client. Called from the concentration-cleanup paths when
    the caster's concentration ends (manually dropped, failed con
    save, dead, dual-cast another concentration spell)."""
    markers = _concentration_aoes.get(campaign_id) or []
    kept = [m for m in markers if int(m.get("caster_char_id") or 0) != int(caster_char_id)]
    if len(kept) == len(markers):
        return False
    _concentration_aoes[campaign_id] = kept
    await _broadcast_concentration_aoes(campaign_id)
    return True


# Shape names from app/data/local/dnd5e/spells/*.json that trigger
# the AoE placement picker on the client. Mirrors the client-side
# ``_AOE_SHAPES`` Set in sheet_dnd5e.html.
_AOE_SHAPE_SET = frozenset({
    "sphere", "cone", "line", "cube", "self_sphere", "self_cube",
})


def _extract_aoe_area(spell: dict) -> dict | None:
    """Return the first AoE area block on a spell's actions list, or
    None if the spell isn't a recognised AoE. Used by ``/cast_spell``
    to flip the cast into pending-placement mode when no targets were
    supplied, AND by ``/place_aoe`` to pull the area for the broadcast
    metadata."""
    for action in (spell.get("actions") or []):
        area = action.get("area") or {}
        shape = (area.get("shape") or "").strip()
        size_ft = int(area.get("size_ft") or 0)
        if shape in _AOE_SHAPE_SET and size_ft > 0:
            return {
                "shape": shape,
                "size_ft": size_ft,
                "secondary_ft": int(area.get("secondary_ft") or 0),
            }
    return None


async def _apply_damage_to_combatant(
    db: Session,
    campaign_id: int,
    combatant: dict,
    damage_amount: int,
    damage_type: str,
    *,
    is_crit: bool = False,
    attack_id: str | None = None,
) -> dict:
    """Apply ``damage_amount`` damage to the target combatant. Two
    paths:

    - PC (``combatant['char_id']`` set): routes through
      ``_apply_hp_change`` so the death-save state machine + the
      Phase B resistance halving + the Phase C.2 concentration-save
      hook all fire. Commits db.
    - NPC (``token_template_id`` only): mutates the hub combatant's
      ``hp_current`` directly and broadcasts ``battle_update`` so
      every client refreshes. No resistance lookup yet — monsters
      don't carry the v2.19.2 ``_buffs_active`` sheet field.

    Logs the applied delta in ``_attack_damage_log[attack_id]`` so
    the chat card's Undo button can revert it.

    Returns ``{applied, hp_before, hp_after, resistance_applied,
    is_dying, is_dead}``.
    """
    _purge_attack_damage_log()
    char_id = combatant.get("char_id")
    if char_id:
        char = db.query(Character).filter(Character.id == char_id).first()
        if not char:
            return {"applied": 0, "hp_before": 0, "hp_after": 0,
                    "resistance_applied": False, "is_dying": False, "is_dead": False}
        sheet = char.sheet or {}
        hp = dict(sheet.get("hp") or {})
        hp_cur = int(hp.get("current") or 0)
        # Apply resistance (Phase B) BEFORE _apply_hp_change so the
        # massive-damage threshold uses the post-resistance number.
        applied, resistance_applied = _resistance_halve(
            damage_amount, damage_type, sheet,
        )
        new_hp = max(0, hp_cur - applied)
        result = _apply_hp_change(
            char, new_hp,
            is_damage=True, is_crit=is_crit, damage_amount=applied,
        )
        db.commit()
        # Phase C.2 concentration save trigger.
        if applied > 0:
            await _maybe_concentration_save(campaign_id, char, applied, db=db)
        await hub.broadcast(campaign_id, {
            "type": "character_hp_update",
            "data": {
                "character_id": char.id,
                "hp": result["hp"],
                "delta": -applied,
                "source": "attack",
            },
        })
        # v2.49.61: RAW Sleep — taking damage wakes the sleeper.
        await _wake_sleeping_on_damage(campaign_id, char.id, None, applied, db=db)
        if attack_id:
            _attack_damage_log[attack_id] = {
                "ts": _time.time(),
                "campaign_id": campaign_id,
                "target_char_id": char.id,
                "applied": applied,
                "was_resistance": resistance_applied,
            }
        return {
            "applied": applied,
            "hp_before": hp_cur,
            "hp_after": result["hp"]["current"],
            "resistance_applied": resistance_applied,
            "is_dying": result["death_saves"]["status"] == "dying",
            "is_dead": result["death_saves"]["status"] == "dead",
        }
    # NPC path: mutate hub combatant directly.
    state = hub.get_battle(campaign_id)
    if not state:
        return {"applied": 0, "hp_before": 0, "hp_after": 0,
                "resistance_applied": False, "is_dying": False, "is_dead": False}
    # Re-find the combatant by id in case the caller passed a stale ref.
    target = None
    for c in state.get("combatants") or []:
        if c.get("id") == combatant.get("id"):
            target = c
            break
    if target is None:
        return {"applied": 0, "hp_before": 0, "hp_after": 0,
                "resistance_applied": False, "is_dying": False, "is_dead": False}
    hp_cur = int(target.get("hp_current") or 0)
    hp_max = int(target.get("hp_max") or 0)
    # v2.49.109: NPCs now get resistance halving via the template's
    # ``damage_resistances`` list + the combatant's own ``buffs``.
    # Pre-v2.49.109 this branch hardcoded ``applied = damage_amount``
    # so a bandit with template-listed fire resistance still took
    # full Fireball damage. See ``_resistance_halve_npc`` for the
    # contract; damage immunity + vulnerability are not yet applied
    # (filed for follow-up).
    applied, resistance_applied = _resistance_halve_npc(
        damage_amount, damage_type, target, db,
    )
    new_hp = max(0, hp_cur - applied)
    target["hp_current"] = new_hp
    hub.set_battle(campaign_id, state)
    # v2.49.40 — ``force_gm_sync: True`` so the GM client picks up the
    # NPC HP change. Without this flag the GM ignores the broadcast
    # (the v2.5.5 echo-loop guard at tabletop.html:5543) and their
    # local ``battle.combatants[…].hp_current`` stays at the pre-
    # damage value. A subsequent ``pushBattle()`` (any drag / init
    # edit) then overwrites the server-authoritative new HP with the
    # GM's stale local value — the bandit visually "comes back to
    # life" the moment the GM moves a token. Encounter-sim Phase 1's
    # test_garrik_strike docstring documented this as the GM-driver
    # caveat; now resolved.
    # Mirrors the v2.48.8 /place_aoe pattern (tabletop_routes.py:7986).
    await hub.broadcast(campaign_id, {
        "type": "battle_update",
        "data": state,
        "force_gm_sync": True,
    })
    # v2.49.61: RAW Sleep — taking damage wakes the sleeper.
    await _wake_sleeping_on_damage(campaign_id, None, target.get("id"), applied)
    if attack_id:
        _attack_damage_log[attack_id] = {
            "ts": _time.time(),
            "campaign_id": campaign_id,
            "target_combatant_id": target.get("id"),
            "applied": applied,
            "was_resistance": resistance_applied,
        }
    return {
        "applied": applied,
        "hp_before": hp_cur,
        "hp_after": new_hp,
        "resistance_applied": resistance_applied,
        "is_dying": False,
        "is_dead": new_hp == 0 and hp_max > 0,
    }


async def _apply_heal_to_combatant(
    db: Session,
    campaign_id: int,
    combatant: dict,
    heal_amount: int,
    *,
    cast_id: str | None = None,
) -> dict:
    """v2.26.0 Phase T.4: apply healing to a target combatant. Mirror
    of ``_apply_damage_to_combatant`` but additive. PC heals route
    through ``_apply_hp_change`` so the death-save state machine
    revives a dying target cleanly (heal > 0 → status flips from
    ``dying`` / ``stable`` / ``dead`` back to ``alive``). NPC heals
    mutate the hub combatant's ``hp_current`` directly. Heals cap at
    the target's max HP — RAW.

    The applied amount is logged in ``_attack_damage_log[cast_id]``
    with ``is_heal: True`` so the chat-card Undo button can reverse
    the heal (i.e. damage the target by the same amount). Broadcasts
    ``character_hp_update`` (PC) or ``battle_update`` (NPC).
    """
    _purge_attack_damage_log()
    char_id = combatant.get("char_id")
    if char_id:
        char = db.query(Character).filter(Character.id == char_id).first()
        if not char:
            return {"applied": 0, "hp_before": 0, "hp_after": 0,
                    "revived": False}
        sheet = char.sheet or {}
        hp = dict(sheet.get("hp") or {})
        hp_cur = int(hp.get("current") or 0)
        hp_max = int(hp.get("max") or 0)
        ds_before = (sheet.get("death_saves") or {}).get("status", "alive")
        new_hp = (
            min(hp_max, hp_cur + heal_amount) if hp_max > 0
            else (hp_cur + heal_amount)
        )
        actual = new_hp - hp_cur
        result = _apply_hp_change(char, new_hp)
        db.commit()
        ds_after = result["death_saves"]["status"]
        revived = ds_before != "alive" and ds_after == "alive"
        await hub.broadcast(campaign_id, {
            "type": "character_hp_update",
            "data": {
                "character_id": char.id,
                "hp": result["hp"],
                "delta": +actual,
                "source": "heal",
            },
        })
        if cast_id:
            _attack_damage_log[cast_id] = {
                "ts": _time.time(),
                "campaign_id": campaign_id,
                "target_char_id": char.id,
                "applied": actual,
                "is_heal": True,
            }
        return {
            "applied": actual,
            "hp_before": hp_cur,
            "hp_after": result["hp"]["current"],
            "revived": revived,
        }
    # NPC path.
    state = hub.get_battle(campaign_id)
    if not state:
        return {"applied": 0, "hp_before": 0, "hp_after": 0, "revived": False}
    target = None
    for c in state.get("combatants") or []:
        if c.get("id") == combatant.get("id"):
            target = c
            break
    if target is None:
        return {"applied": 0, "hp_before": 0, "hp_after": 0, "revived": False}
    hp_cur = int(target.get("hp_current") or 0)
    hp_max = int(target.get("hp_max") or 0)
    new_hp = min(hp_max, hp_cur + heal_amount) if hp_max > 0 else (hp_cur + heal_amount)
    actual = new_hp - hp_cur
    target["hp_current"] = new_hp
    hub.set_battle(campaign_id, state)
    # v2.49.43 — server-initiated NPC heal, force_gm_sync (see v2.49.40
    # audit). Heal is the mirror of /attack's damage broadcast at
    # _apply_damage_to_combatant; both need the flag for the GM to see
    # the HP bar move.
    await hub.broadcast(campaign_id, {
        "type": "battle_update",
        "data": state,
        "force_gm_sync": True,
    })
    if cast_id:
        _attack_damage_log[cast_id] = {
            "ts": _time.time(),
            "campaign_id": campaign_id,
            "target_combatant_id": target.get("id"),
            "applied": actual,
            "is_heal": True,
        }
    return {
        "applied": actual,
        "hp_before": hp_cur,
        "hp_after": new_hp,
        "revived": False,
    }


def _mirror_buffs_to_sheet(
    db: Session, character_id: int, buffs: list[dict],
) -> None:
    """v2.19.2 Phase C.3: mirror the (live) buff list onto the
    character sheet's ``_buffs_active`` field so out-of-combat display
    works AND so the sheet survives across page loads. The
    ``duration_rounds`` + ``duration_max`` fields are stripped from the
    sheet copy — the init tracker is the source of truth for live
    countdowns; the sheet only renders presence + effects.

    Caller must commit the session (helper does flag_modified + a
    commit so the sheet write is visible immediately, mirroring the
    pattern other helpers use).
    """
    char = db.query(Character).filter(Character.id == character_id).first()
    if not char:
        return
    from sqlalchemy.orm.attributes import flag_modified
    stripped = [
        {k: v for k, v in (b or {}).items()
         if k not in ("duration_rounds", "duration_max")}
        for b in (buffs or [])
    ]
    sheet = dict(char.sheet or {})
    if sheet.get("_buffs_active") == stripped:
        return  # idempotent — nothing changed
    sheet["_buffs_active"] = stripped
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()


# ----------- helpers -----------

def _user_can_view_campaign(db: Session, user: User, campaign: Campaign) -> bool:
    if user.is_admin:
        return True
    if campaign.gm_user_id == user.id:
        return True
    member = (
        db.query(CampaignMembership)
        .filter(
            CampaignMembership.campaign_id == campaign.id,
            CampaignMembership.user_id == user.id,
        )
        .first()
    )
    return member is not None


def _user_is_gm(user: User, campaign: Campaign, db: Optional[Session] = None) -> bool:
    """True if `user` has GM powers in `campaign`.

    Sources of GM rights, in order of cost: site admin (free, no DB), primary
    GM/owner (free, no DB), or co-GM (membership row with is_gm=True; needs db).
    """
    if user.is_admin:
        return True
    if campaign.gm_user_id == user.id:
        return True
    if db is None:
        return False
    co_gm = (
        db.query(CampaignMembership)
        .filter(
            CampaignMembership.campaign_id == campaign.id,
            CampaignMembership.user_id == user.id,
            CampaignMembership.is_gm == True,  # noqa: E712
        )
        .first()
    )
    return co_gm is not None


def _user_is_primary_gm(user: User, campaign: Campaign) -> bool:
    return campaign.gm_user_id == user.id


def _user_can_move_token(db: Session, user: User, token: Token, campaign: Campaign) -> bool:
    if _user_is_gm(user, campaign, db):
        return True
    if token.is_hidden:
        return False
    if token.controller_user_id is not None and token.controller_user_id == user.id:
        return True
    if token.character_id is None:
        return False
    char = db.query(Character).filter(Character.id == token.character_id).first()
    return char is not None and char.owner_user_id == user.id


def _filter_roll_for_user(roll: DiceRoll, user: User, campaign: Campaign, db: Optional[Session] = None) -> bool:
    if _user_is_gm(user, campaign, db):
        return True
    if roll.visibility == Visibility.PUBLIC:
        return True
    if roll.visibility == Visibility.GM_AND_ROLLER:
        return roll.user_id == user.id
    return False


def _build_user_maps(db: Session, campaign: Campaign):
    """Return (user_color_map, user_portrait_map, user_char_name_map) for a campaign.

    user_color_map    : {user_id: hex_color_str}  — char color if set, else player color
    user_portrait_map : {user_id: portrait_url}   — first character portrait per user
    user_char_name_map: {user_id: char_name}       — first character name per user
    """
    # Start with player-level colors from memberships and GM
    memberships = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign.id)
        .all()
    )
    user_color_map: dict[int, str] = {}
    for m in memberships:
        if m.color:
            user_color_map[m.user_id] = m.color
    if campaign.gm_color:
        user_color_map[campaign.gm_user_id] = campaign.gm_color

    # Characters: first per user wins for name/portrait; char color overrides player color
    chars = (
        db.query(Character)
        .filter(
            Character.campaign_id == campaign.id,
            Character.owner_user_id.isnot(None),
        )
        .all()
    )
    user_portrait_map: dict[int, str] = {}
    user_char_name_map: dict[int, str] = {}
    for c in chars:
        uid = c.owner_user_id
        if uid not in user_char_name_map:
            # First character per user wins
            user_char_name_map[uid] = c.name
            if c.portrait_url:
                user_portrait_map[uid] = c.portrait_url
            if c.color:
                user_color_map[uid] = c.color  # char color overrides player color
        elif c.color and uid not in user_portrait_map:
            # Still might pick up portrait from a later char if first had none
            if c.portrait_url:
                user_portrait_map[uid] = c.portrait_url

    return user_color_map, user_portrait_map, user_char_name_map


# ----------- pages -----------

@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    primary_gm_campaigns = db.query(Campaign).filter(Campaign.gm_user_id == user.id).all()
    co_gm_memberships = (
        db.query(CampaignMembership)
        .filter(
            CampaignMembership.user_id == user.id,
            CampaignMembership.is_gm == True,  # noqa: E712
        )
        .all()
    )
    co_gm_ids = [m.campaign_id for m in co_gm_memberships]
    co_gm_campaigns = (
        db.query(Campaign).filter(Campaign.id.in_(co_gm_ids)).all() if co_gm_ids else []
    )
    seen = {c.id for c in primary_gm_campaigns}
    gm_campaigns = primary_gm_campaigns + [c for c in co_gm_campaigns if c.id not in seen]
    player_member_ids = [
        m.campaign_id
        for m in db.query(CampaignMembership)
        .filter(
            CampaignMembership.user_id == user.id,
            CampaignMembership.is_gm == False,  # noqa: E712
        )
        .all()
    ]
    member_campaigns = (
        db.query(Campaign).filter(Campaign.id.in_(player_member_ids)).all() if player_member_ids else []
    )
    if user.is_admin:
        all_campaigns = db.query(Campaign).all()
    else:
        all_campaigns = []
    gm_names = {
        c.id: (
            db.query(User).filter(User.id == c.gm_user_id).first().display_name
            if db.query(User).filter(User.id == c.gm_user_id).first()
            else "?"
        )
        for c in member_campaigns + all_campaigns
    }
    return templates.TemplateResponse(
        "lobby.html",
        {
            "request": request,
            "user": user,
            "gm_campaigns": gm_campaigns,
            "member_campaigns": member_campaigns,
            "all_campaigns": all_campaigns,
            "gm_names": gm_names,
            "system_choices": system_choices(),
            "get_system": get_system,
        },
    )


@router.post("/campaigns")
async def create_campaign(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    game_system: str = Form("generic"),
    thumbnail: UploadFile = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    sys = get_system(game_system)
    c = Campaign(
        name=name.strip(),
        description=description.strip(),
        gm_user_id=user.id,
        game_system=sys.key,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    if thumbnail and thumbnail.filename:
        from ..routes.admin_routes import _save_thumbnail
        c.thumbnail_url = await _save_thumbnail(thumbnail)
        db.commit()
    m = Map(campaign_id=c.id, name="Default map")
    db.add(m)
    db.commit()
    db.refresh(m)
    c.active_map_id = m.id
    db.commit()
    return RedirectResponse(f"/campaign/{c.id}", status_code=303)


@router.get("/campaign/{campaign_id}", response_class=HTMLResponse)
def campaign_view(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    view_as: Optional[int] = Query(None),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member of this campaign")
    is_gm = _user_is_gm(user, campaign, db)

    # GM preview mode: render the tabletop as if the requester were a specific player.
    view_as_user = None
    if view_as and is_gm:
        target = db.query(User).filter(User.id == view_as).first()
        if target and _user_can_view_campaign(db, target, campaign):
            view_as_user = user          # keep real GM reference for the banner
            user = target                # override user context for template rendering
            is_gm = False

    # Session gate: players (non-GM members) only see the tabletop while the
    # GM has the session active. They get a "waiting" page that auto-redirects
    # via WebSocket the moment the GM hits Start.
    if not is_gm and not view_as_user and not campaign.session_active:
        return templates.TemplateResponse(
            "session_waiting.html",
            {
                "request": request,
                "user": user,
                "campaign": campaign,
            },
        )
    active_map = (
        db.query(Map).filter(Map.id == campaign.active_map_id).first()
        if campaign.active_map_id
        else None
    )
    tokens = (
        db.query(Token).filter(Token.map_id == active_map.id).all() if active_map else []
    )
    characters = db.query(Character).filter(Character.campaign_id == campaign.id).all()
    # Normalize D&D 5e sheets so the tabletop mini-sheet sees a multiclass-aware
    # ``classes`` roster + nested ``spell_slots`` even on legacy data.
    for _ch in characters:
        if _ch.template == "dnd5e" and isinstance(_ch.sheet, dict):
            normalize_dnd5e_sheet(_ch.sheet)
    rolls = (
        db.query(DiceRoll)
        .filter(DiceRoll.campaign_id == campaign.id)
        .order_by(DiceRoll.created_at.desc())
        .limit(100)
        .all()
    )
    visible_rolls = list(reversed([r for r in rolls if _filter_roll_for_user(r, user, campaign, db)]))
    members = (
        db.query(User)
        .join(CampaignMembership, CampaignMembership.user_id == User.id)
        .filter(CampaignMembership.campaign_id == campaign.id)
        .all()
    )
    # Audio context: currently-playing track (if any) so reconnecting clients
    # immediately resume on page load. started_at_ms is sent so the client
    # can compute the seek offset and stay in sync with everyone else.
    now_playing = (
        db.query(PlaylistTrack).filter(PlaylistTrack.id == campaign.now_playing_track_id).first()
        if campaign.now_playing_track_id
        else None
    )
    now_playing_started_at_ms = None
    if now_playing and campaign.now_playing_started_at:
        now_playing_started_at_ms = int(
            campaign.now_playing_started_at.replace(tzinfo=timezone.utc).timestamp() * 1000
        )
    playlists = (
        db.query(Playlist)
        .filter(Playlist.campaign_id == campaign.id)
        .order_by(Playlist.id)
        .all()
        if is_gm
        else []
    )
    # All maps in the campaign — surfaced for the Encounters panel's map
    # dropdown in the Save / Edit forms. GM-only (the panel itself is
    # gated), so we skip the query for non-GMs.
    all_maps = (
        db.query(Map)
        .filter(Map.campaign_id == campaign.id)
        .order_by(Map.id)
        .all()
        if is_gm
        else []
    )
    tmpl_objs = db.query(TokenTemplate).filter(TokenTemplate.campaign_id == campaign.id).order_by(TokenTemplate.name).all()
    char_data = [
        {
            "id": c.id,
            "name": c.name,
            "owner_user_id": c.owner_user_id,
            "template": c.template,
            "sheet": c.sheet or {},
            # Surfaced for the GM's "Players" tab in the Add Token modal —
            # mini-sheet rendering already pulls portrait/color from the
            # user_*_map helpers, so these fields cover the per-character
            # avatar in the picker without duplicating the merge logic.
            "portrait_url": c.portrait_url,
            "color": c.color,
            "ring_style": c.ring_style,
        }
        for c in characters
    ]
    token_data = [_token_dict(t) for t in tokens]
    # v2.3.34: each template's ``sheet`` is pre-resolved through the
    # monster adapter so the client-side init-tracker reads real stats
    # (HP / AC / abilities / structured actions) instead of the minimal
    # ``_npc_sheet`` slug-pointer placeholders (``abilities={STR:10,...}``)
    # the demo seeds. For non-monster templates the adapter returns the
    # input sheet unchanged so this is a no-op. Replaces the v2.3.17
    # ``monster_templates`` context which built a hidden pool of
    # synthesized PC-style mini-sheets — the user preferred the older
    # 2.3.9 inline stat-block view that ``buildMonsterInitSheet``
    # produces directly from this resolved sheet.
    tmpl_data = []
    for t in tmpl_objs:
        raw_sheet = t.sheet or {}
        if (t.template or "dnd5e") == "dnd5e":
            try:
                resolved = _monster_template_to_sheet(t, campaign.id)
            except Exception:  # noqa: BLE001
                resolved = raw_sheet
        else:
            resolved = raw_sheet
        tmpl_data.append({
            "id": t.id,
            "name": t.name,
            "image_url": t.image_url,
            "tags": t.tags or [],
            "template": t.template,
            "sheet": resolved,
        })

    user_color_map, user_portrait_map, user_char_name_map = _build_user_maps(db, campaign)
    conc_effects = db.query(ConcentrationEffect).filter(ConcentrationEffect.campaign_id == campaign_id).all()
    conc_by_char = {
        e.character_id: {
            "id": e.id,
            "spell_name": e.spell_name,
            "rounds_remaining": e.rounds_remaining,
            "notes": e.notes or "",
        }
        for e in conc_effects
    }
    return templates.TemplateResponse(
        "tabletop.html",
        {
            "request": request,
            "user": user,
            "is_gm": is_gm,
            "campaign": campaign,
            "active_map": active_map,
            "tokens": tokens,
            "characters": characters,
            "members": members,
            "rolls": visible_rolls,
            "settings": get_settings(),
            "system": get_system(campaign.game_system),
            "now_playing": now_playing,
            "now_playing_started_at_ms": now_playing_started_at_ms,
            "playlists": playlists,
            "all_maps": all_maps,
            "char_data": char_data,
            "token_data": token_data,
            "tmpl_data": tmpl_data,
            "user_color_map": user_color_map,
            "user_portrait_map": user_portrait_map,
            "user_char_name_map": user_char_name_map,
            "conc_by_char": conc_by_char,
            "hp_thresholds": campaign.hp_thresholds or _DEFAULT_HP_THRESHOLDS,
            "view_as_user": view_as_user,
        },
    )


@router.get("/campaign/{campaign_id}/settings", response_class=HTMLResponse)
def campaign_settings(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM-accessible settings page (also reachable by admins)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    member_rows = (
        db.query(CampaignMembership, User)
        .join(User, User.id == CampaignMembership.user_id)
        .filter(CampaignMembership.campaign_id == campaign_id)
        .all()
    )
    members_with_role = [
        {"user": u, "is_gm": m.is_gm, "membership_id": m.id, "color": m.color or ""} for m, u in member_rows
    ]
    member_user_ids = {m["user"].id for m in members_with_role}
    primary_gm = db.query(User).filter(User.id == campaign.gm_user_id).first()
    all_users = db.query(User).order_by(User.display_name).all()
    non_members = [
        u for u in all_users
        if u.id not in member_user_ids and u.id != campaign.gm_user_id
    ]
    characters = (
        db.query(Character)
        .filter(Character.campaign_id == campaign_id)
        .order_by(Character.name)
        .all()
    )
    maps = db.query(Map).filter(Map.campaign_id == campaign_id).order_by(Map.id).all()
    playlists = (
        db.query(Playlist)
        .filter(Playlist.campaign_id == campaign_id)
        .order_by(Playlist.id)
        .all()
    )
    tmpl_objs = db.query(TokenTemplate).filter(TokenTemplate.campaign_id == campaign_id).order_by(TokenTemplate.name).all()
    # v2.0.0: file-based subclasses. The file's `slug` field carries the
    # combined `<class>__<sub>` form so each entry is addressable by a single
    # path-safe key. We also expose split `class_slug` / `sub_slug` for the
    # template form's existing field names.
    _subclass_records, _ = local_content.search(
        type="subclass_features", campaign_id=campaign_id, limit=500,
    )
    custom_subclasses = []
    for _r in _subclass_records:
        if _r.get("_source") != "local-homebrew":
            continue
        _combined = _r.get("slug") or ""
        if "__" in _combined:
            _cls, _, _sub = _combined.partition("__")
        else:
            _cls, _sub = _r.get("class_slug") or "", _combined
        custom_subclasses.append({
            **_r,
            "class_slug": _cls,
            "sub_slug": _sub,
            "combined_slug": _combined,
        })
    # Match the legacy ORM ordering: by parent class, then by subclass name.
    custom_subclasses.sort(key=lambda r: (r.get("class_slug") or "", (r.get("name") or "").lower()))
    # v2.0.0: file-based class_features. Project the homebrew records back to
    # the legacy template field names (``class_slug``) so the existing edit
    # form keeps working without template changes; the schema types
    # ``features`` as Any so the editor's structured list round-trips.
    _class_records, _ = local_content.search(
        type="class_features", campaign_id=campaign_id, limit=500,
    )
    custom_classes = []
    for _c in _class_records:
        if _c.get("_source") != "local-homebrew":
            continue
        custom_classes.append({
            **_c,
            "class_slug": _c.get("slug"),  # template legacy alias
        })
    custom_classes.sort(key=lambda r: (r.get("name") or "").lower())
    # v2.0.0: file-based races.
    custom_races, _ = local_content.search(
        type="races", campaign_id=campaign_id, limit=500,
    )
    # v2.0.0: file-based monsters. The Pydantic Monster model stores a single
    # `actions: list[Action]` array with a `category` discriminator; the
    # template's edit form expects the 4 legacy split lists. We split here so
    # the per-textarea editor populates correctly.
    _monster_records, _ = local_content.search(
        type="monsters", campaign_id=campaign_id, limit=500,
    )
    custom_monsters = []
    for _m in _monster_records:
        if _m.get("_source") != "local-homebrew":
            continue
        # Split unified actions back into category buckets for the template.
        # v2.3.8: also pass through the structured attack fields so the editor
        # can re-render them after a save (otherwise the next form load would
        # show them blank and a subsequent save would silently drop them).
        _by_cat: dict[str, list] = {"action": [], "reaction": [], "special_ability": [], "legendary_action": []}
        for _a in _m.get("actions") or []:
            _cat = (_a.get("category") or "action")
            if _cat in _by_cat:
                _entry = {"name": _a.get("name"), "desc": _a.get("desc"), "level": _a.get("min_level")}
                for _k in ("attack_roll", "attack_bonus", "damage", "damage_type",
                           "save_ability", "save_dc"):
                    _v = _a.get(_k)
                    if _v not in (None, "", False, 0):
                        _entry[_k] = _v
                _by_cat[_cat].append(_entry)
        custom_monsters.append({
            **_m,
            "monster_slug": _m.get("slug"),  # template legacy alias
            # Split actions for the 4-textarea form:
            "actions_split": _by_cat["action"],
            "reactions": _by_cat["reaction"],
            "special_abilities": _by_cat["special_ability"],
            "legendary_actions": _by_cat["legendary_action"],
        })
    custom_monsters.sort(key=lambda r: (r.get("name") or "").lower())
    # v2.0.0: file-based backgrounds (see custom_feats above for the pattern).
    custom_backgrounds, _ = local_content.search(
        type="backgrounds", campaign_id=campaign_id, limit=500,
    )
    # File-based homebrew at v2.0.0: feats live as JSON files under the
    # homebrew Docker volume rather than rows in custom_feats. The records
    # carry the same display fields the template expects (name, prerequisite,
    # desc) plus the new `slug` field (replacing the legacy int `id` for URL
    # addressing). See app/local_content.py for the resolver.
    custom_feats, _custom_feats_total = local_content.search(
        type="feats", campaign_id=campaign_id, limit=500,
    )
    # ── Encounters (Phase 1, v0.64.0) ────────────────────────────────────
    # Read-only listing of saved encounters; save / load / edit / delete
    # land in later phases. See docs/encounters-plan.md.
    encounters = (
        db.query(Encounter)
        .filter(Encounter.campaign_id == campaign_id)
        .order_by(Encounter.created_at.desc())
        .all()
    )

    # ── Audio history (PR 4) ─────────────────────────────────────────────
    # Recent plays (last 50, newest first), top tracks (by play count,
    # top 10), and a summary line. The table grows by ~1 row per track
    # play so capping the page render is important.
    from sqlalchemy import func
    audio_recent = (
        db.query(AudioPlayEvent)
        .filter(AudioPlayEvent.campaign_id == campaign_id)
        .order_by(AudioPlayEvent.started_at.desc())
        .limit(50)
        .all()
    )
    # Aggregate by the snapshot ``track_name`` so renamed/deleted tracks
    # still group correctly (the FK can be NULL after a delete).
    audio_top_rows = (
        db.query(
            AudioPlayEvent.track_name,
            func.count(AudioPlayEvent.id).label("play_count"),
            func.coalesce(func.sum(AudioPlayEvent.duration_s), 0).label("total_s"),
        )
        .filter(AudioPlayEvent.campaign_id == campaign_id)
        .filter(AudioPlayEvent.track_name != "")
        .group_by(AudioPlayEvent.track_name)
        .order_by(func.count(AudioPlayEvent.id).desc())
        .limit(10)
        .all()
    )
    audio_top = [
        {"track_name": r.track_name, "play_count": r.play_count, "total_s": int(r.total_s or 0)}
        for r in audio_top_rows
    ]
    audio_summary = (
        db.query(
            func.count(AudioPlayEvent.id).label("total"),
            func.coalesce(func.sum(AudioPlayEvent.duration_s), 0).label("total_s"),
        )
        .filter(AudioPlayEvent.campaign_id == campaign_id)
        .first()
    )
    audio_stats = {
        "total_plays": int(audio_summary.total or 0) if audio_summary else 0,
        "total_seconds": int(audio_summary.total_s or 0) if audio_summary else 0,
    }

    # Characters owned by campaign members (from any campaign) that aren't already here
    all_member_ids = list(member_user_ids | {campaign.gm_user_id})
    existing_char_ids = {c.id for c in characters}
    importable_chars = (
        db.query(Character)
        .filter(Character.owner_user_id.in_(all_member_ids))
        .filter(Character.campaign_id != campaign_id)
        .order_by(Character.name)
        .all()
    ) if all_member_ids else []

    # Annotate with owner display name for the template
    user_map = {u.id: u for u in all_users}
    importable = [
        {"char": c, "owner_name": user_map.get(c.owner_user_id, None)}
        for c in importable_chars
    ]

    return templates.TemplateResponse(
        "campaign_settings.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "system_choices": system_choices(),
            "current_system": get_system(campaign.game_system),
            "members_with_role": members_with_role,
            "primary_gm": primary_gm,
            "all_users": all_users,
            "non_members": non_members,
            "characters": characters,
            "maps": maps,
            "playlists": playlists,
            "templates": tmpl_objs,
            "importable": importable,
            "custom_subclasses": custom_subclasses,
            "custom_classes": custom_classes,
            "custom_races": custom_races,
            "custom_monsters": custom_monsters,
            "custom_backgrounds": custom_backgrounds,
            "custom_feats": custom_feats,
            "audio_recent": audio_recent,
            "audio_top": audio_top,
            "audio_stats": audio_stats,
            "encounters": encounters,
            "hp_thresholds": campaign.hp_thresholds or _DEFAULT_HP_THRESHOLDS,
        },
    )


_VALID_CAMPAIGN_FONTS = {"", "lora", "cormorant", "im-fell"}

_DEFAULT_HP_THRESHOLDS = [
    {"label": "Healthy",  "min_pct": 76},
    {"label": "Wounded",  "min_pct": 51},
    {"label": "Bloodied", "min_pct": 26},
    {"label": "Critical", "min_pct": 1},
    {"label": "Dead",     "min_pct": 0},
]


@router.post("/campaign/{campaign_id}/settings")
async def campaign_settings_save(
    campaign_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    game_system: str = Form("generic"),
    gm_tab_color: str = Form(""),
    font_override: str = Form(""),
    auto_play_playlist_id: str = Form(""),
    auto_play_mode: str = Form("order"),
    default_encounter_id: str = Form(""),
    thumbnail: UploadFile = File(None),
    clear_thumbnail: bool = Form(False),
    hp_threshold_0: str = Form(""),
    hp_threshold_1: str = Form(""),
    hp_threshold_2: str = Form(""),
    hp_threshold_3: str = Form(""),
    hp_threshold_4: str = Form(""),
    # v2.5.0: house-rule toggles. Each one's a bool that defaults False
    # if the checkbox isn't checked (HTML form idiom: unchecked checkbox
    # doesn't submit the field). ``Form(False)`` recovers the default.
    potions_as_bonus_action: bool = Form(False),
    # v2.8.0: strict action-economy. When on, players can't override the
    # Phase 4 over-budget modal — only the GM can clear a spent chip.
    strict_action_economy: bool = Form(False),
    # v2.24.0 Phase T.2: auto-apply HP damage on attacks that hit. Off
    # by default — GM opts in via the campaign settings page.
    auto_apply_damage: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404)
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    campaign.name = name.strip()[:120] or campaign.name
    campaign.description = description.strip()
    campaign.game_system = get_system(game_system).key
    campaign.gm_tab_color = gm_tab_color.strip()[:20] or None
    fo = font_override.strip()
    campaign.font_override = fo if fo in _VALID_CAMPAIGN_FONTS and fo else None
    # v2.5.0: house rules
    campaign.potions_as_bonus_action = potions_as_bonus_action
    # v2.8.0: strict action-economy gating
    campaign.strict_action_economy = strict_action_economy
    # v2.24.0 Phase T.2: auto-apply damage toggle
    campaign.auto_apply_damage = auto_apply_damage
    # Default-encounter-on-session-start setting. Validate the encounter
    # belongs to this campaign before assigning; empty / invalid clears.
    de_raw = (default_encounter_id or "").strip()
    if de_raw:
        try:
            de_id = int(de_raw)
        except ValueError:
            de_id = None
        if de_id:
            owned = (
                db.query(Encounter.id)
                .filter(Encounter.id == de_id, Encounter.campaign_id == campaign_id)
                .first()
            )
            campaign.default_encounter_id = owned[0] if owned else None
        else:
            campaign.default_encounter_id = None
    else:
        campaign.default_encounter_id = None
    # Audio auto-start config. Empty value = no auto-play. Validate the
    # playlist belongs to this campaign before assigning.
    ap_raw = (auto_play_playlist_id or "").strip()
    if ap_raw:
        try:
            ap_id = int(ap_raw)
        except ValueError:
            ap_id = None
        if ap_id:
            owned = (
                db.query(Playlist.id)
                .filter(Playlist.id == ap_id, Playlist.campaign_id == campaign_id)
                .first()
            )
            campaign.auto_play_playlist_id = owned[0] if owned else None
        else:
            campaign.auto_play_playlist_id = None
    else:
        campaign.auto_play_playlist_id = None
    mode = (auto_play_mode or "order").strip().lower()
    campaign.auto_play_mode = "shuffle" if mode == "shuffle" else "order"
    if clear_thumbnail:
        campaign.thumbnail_url = None
    if thumbnail and thumbnail.filename:
        from ..routes.admin_routes import _save_thumbnail
        campaign.thumbnail_url = await _save_thumbnail(thumbnail)
    raw_labels = [hp_threshold_0, hp_threshold_1, hp_threshold_2, hp_threshold_3, hp_threshold_4]
    if any(l.strip() for l in raw_labels):
        new_thresholds = []
        for i, (default, label) in enumerate(zip(_DEFAULT_HP_THRESHOLDS, raw_labels)):
            new_thresholds.append({
                "label": label.strip()[:40] or default["label"],
                "min_pct": default["min_pct"],
            })
        campaign.hp_thresholds = new_thresholds
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings", status_code=303)


# ── Custom subclasses (GM-authored homebrew) ─────────────────────────────────
#
# GM-only CRUD for rows in the ``custom_subclasses`` table introduced in
# v0.42.0.  The resolver in app/local_features.py picks these up under
# scope ``campaign:<id>`` and returns them in place of the shipped global
# SRD content when a player opens a subclass detail panel for a character
# in this campaign.

import re as _re_csub

_SLUG_CLEAN = _re_csub.compile(r"[^a-z0-9]+")


def _slugify_for_subclass(value: str, max_len: int = 80) -> str:
    """Lowercase, replace runs of non-alphanumerics with single dashes, trim.

    Used for both the parent class slug (e.g. "Fighter" -> "fighter") and
    the subclass slug derived from its display name (e.g. "Circle of the
    Deep" -> "circle-of-the-deep").
    """
    s = (value or "").strip().lower()
    s = _SLUG_CLEAN.sub("-", s).strip("-")
    return s[:max_len]


def _parse_custom_subclass_features(raw: str, *, extra_keys: tuple[str, ...] = ()) -> list:
    """Parse and normalise the features JSON textarea.

    Required shape::

        [
          {"name": "Combat Wild Shape", "level": 2, "desc": "..."},
          {"name": "Primal Strike",     "level": 6, "desc": "..."}
        ]

    ``level`` may be null/missing. ``desc`` may be empty. Raises
    ``HTTPException(400, ...)`` with a human-readable message on any
    structural problem so the form can render it back to the GM.

    ``extra_keys`` (v2.3.8): names of optional additional keys to preserve
    verbatim from each input dict. Used by the monster-actions coalescer
    to pass through the structured attack fields (``attack_roll``,
    ``attack_bonus``, ``damage``, ``damage_type``, ``save_ability``,
    ``save_dc``) that the action-mode editor now emits. Default empty
    tuple keeps the strict feature/trait behavior unchanged.
    """
    if not raw or not raw.strip():
        return []
    import json as _json
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as e:
        raise HTTPException(400, f"Features JSON: invalid syntax — {e.msg} (line {e.lineno})")
    if not isinstance(parsed, list):
        raise HTTPException(
            400,
            'Features JSON: must be a list, e.g. [{"name":"...","level":2,"desc":"..."}]',
        )
    out: list = []
    for i, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise HTTPException(400, f"Features JSON: entry #{i} must be an object")
        name = (item.get("name") or "").strip()
        if not name:
            raise HTTPException(400, f"Features JSON: entry #{i} is missing a non-empty 'name'")
        lvl_raw = item.get("level")
        if lvl_raw is None or lvl_raw == "":
            level_norm: int | None = None
        else:
            try:
                level_norm = int(lvl_raw)
            except (TypeError, ValueError):
                raise HTTPException(
                    400, f"Features JSON: entry #{i} 'level' must be an integer (got {lvl_raw!r})"
                )
        desc = (item.get("desc") or "").strip()
        rec: dict = {"name": name[:160], "level": level_norm, "desc": desc[:4000]}
        for ek in extra_keys:
            if ek in item:
                rec[ek] = item[ek]
        out.append(rec)
    return out


def _require_gm_for_campaign(campaign_id: int, user: User, db: Session) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    return campaign


@router.post("/campaign/{campaign_id}/custom-subclasses")
def create_custom_subclass(
    campaign_id: int,
    name: str = Form(...),
    class_slug: str = Form(...),
    flavor: str = Form(""),
    features_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    cls_slug = _slugify_for_subclass(class_slug, max_len=60)
    sub_slug = _slugify_for_subclass(name_n)
    if not name_n:
        raise HTTPException(400, "Name is required")
    if not cls_slug:
        raise HTTPException(400, "Parent class is required")
    if not sub_slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    features = _parse_custom_subclass_features(features_json)

    combined = f"{cls_slug}__{sub_slug}"
    existing = local_content.resolve(combined, type="subclass_features", campaign_id=campaign_id)
    if existing and existing[1] == "local-homebrew":
        raise HTTPException(
            400,
            f"A homebrew subclass with slug '{sub_slug}' already exists for class '{cls_slug}' in this campaign",
        )
    try:
        local_content.write_homebrew(
            {
                "slug": combined,
                "name": name_n,
                "class_slug": cls_slug,
                "subclass_flavor": (flavor or "").strip()[:4000],
                "features": features,
                "actions": [],
                "system": "dnd5e",
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
                "owner": user.id,
            },
            type="subclass_features",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-subclasses", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-subclasses/{combined_slug}")
def update_custom_subclass(
    campaign_id: int,
    combined_slug: str,
    name: str = Form(...),
    class_slug: str = Form(...),
    flavor: str = Form(""),
    features_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based subclass update. ``combined_slug`` is the file's
    `<class>__<sub>` identifier. Reassigning the parent class effectively
    means moving to a new file path; we write the new file under the new
    combined slug and delete the old file."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(combined_slug, type="subclass_features", campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Custom subclass not found")
    existing = hit[0]

    name_n = (name or "").strip()[:120]
    new_cls = _slugify_for_subclass(class_slug, max_len=60)
    if not name_n:
        raise HTTPException(400, "Name is required")
    if not new_cls:
        raise HTTPException(400, "Parent class is required")
    features = _parse_custom_subclass_features(features_json)

    old_cls, _, old_sub = combined_slug.partition("__")
    if not old_sub:
        old_sub = combined_slug  # legacy file without class prefix
    new_combined = f"{new_cls}__{old_sub}"

    if new_combined != combined_slug:
        # Class reassignment: would the new combined slug collide with another
        # homebrew under the same campaign? Reject rather than overwrite.
        collision = local_content.resolve(new_combined, type="subclass_features", campaign_id=campaign_id)
        if collision and collision[1] == "local-homebrew":
            raise HTTPException(
                400,
                f"Class '{new_cls}' already has a homebrew subclass with slug '{old_sub}'",
            )

    try:
        local_content.write_homebrew(
            {
                **existing,
                "slug": new_combined,
                "name": name_n,
                "class_slug": new_cls,
                "subclass_flavor": (flavor or "").strip()[:4000],
                "features": features,
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
            },
            type="subclass_features",
            scope=f"campaign-{campaign_id}",
        )
        # Remove the old file if the combined slug changed (class reassignment).
        if new_combined != combined_slug:
            local_content.delete_homebrew(
                combined_slug, type="subclass_features", scope=f"campaign-{campaign_id}",
            )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-subclasses", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-subclasses/{combined_slug}/delete")
def delete_custom_subclass(
    campaign_id: int,
    combined_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based subclass delete by combined `<class>__<sub>` slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    try:
        removed = local_content.delete_homebrew(
            combined_slug, type="subclass_features", scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not removed:
        raise HTTPException(404, "Custom subclass not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-subclasses", status_code=303
    )


# ── Custom classes (GM-authored homebrew base classes) ───────────────────────
#
# Mirror of the custom-subclass routes above but for the parent class itself.
# Slug is fixed at creation (character sheets reference it); proficiency
# fields are bounded strings; features re-use the same JSON shape parser as
# subclasses.  MVP scope: no spell list, no class-resource counters, no
# multiclass-prereq fields.

_VALID_SPELLCASTING_ABILITIES = {"", "str", "dex", "con", "int", "wis", "cha"}


def _normalize_spellcasting_ability(raw: str) -> str:
    v = (raw or "").strip().lower()
    if v not in _VALID_SPELLCASTING_ABILITIES:
        raise HTTPException(400, "Spellcasting ability must be one of: str, dex, con, int, wis, cha (or blank)")
    return v


def _normalize_hit_die(raw) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(400, "Hit die must be an integer between 4 and 12")
    if n < 4 or n > 12:
        raise HTTPException(400, "Hit die must be between 4 and 12")
    return n


_ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")


def _parse_multiclass_prereq_abilities(values: dict) -> dict:
    """Coerce six ability-minimum form fields into a clean ``{ability: int}``
    dict.  Empty strings are dropped (no requirement on that ability).
    Pass in ``{"str": form_str, "dex": form_dex, …}``.
    """
    out: dict = {}
    for ab, raw in values.items():
        v = (raw or "").strip()
        if not v:
            continue
        try:
            n = int(v)
        except ValueError:
            raise HTTPException(400, f"Multiclass prereq for {ab.upper()} must be an integer (got {raw!r})")
        if n < 1 or n > 30:
            raise HTTPException(400, f"Multiclass prereq for {ab.upper()} must be between 1 and 30")
        out[ab] = n
    return out


def _normalize_multiclass_mode(raw: str) -> str:
    v = (raw or "all").strip().lower()
    if v not in ("all", "any"):
        raise HTTPException(400, "Multiclass mode must be 'all' or 'any'")
    return v


_VALID_RESOURCE_KINDS = {"static", "ability_mod", "proficiency", "level_table"}
_VALID_RESOURCE_RESETS = {"short", "long", "none"}


def _parse_class_resources_json(raw: str) -> list:
    """Parse and normalise the resources JSON field on the custom class form.

    Each entry shape::

        {
          "key": "channel-divinity",          # optional — auto-derived from name
          "name": "Channel Divinity",
          "min_level": 2,
          "max_kind": "static" | "ability_mod" | "proficiency" | "level_table",
          "max_static": 1,                    # required when max_kind = "static"
          "max_ability": "cha",               # required when max_kind = "ability_mod"
          "max_table": {"2":1, "6":2, "18":3},# required when max_kind = "level_table"
          "reset": "short" | "long" | "none",
          "desc": "..."
        }

    Drops rows where ``name`` is empty (treated as an abandoned editor row).
    Generates a stable ``key`` from the name when one isn't provided, and
    dedupes by key so the frontend doesn't see two recipes with the same
    identifier (which would break its uses-tracking state).
    """
    if not raw or not raw.strip():
        return []
    import json as _json
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as e:
        raise HTTPException(400, f"Resources JSON: invalid syntax — {e.msg} (line {e.lineno})")
    if not isinstance(parsed, list):
        raise HTTPException(400, "Resources JSON: must be a list of resource objects")

    out: list = []
    used_keys: set[str] = set()
    for i, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise HTTPException(400, f"Resources JSON: entry #{i} must be an object")
        name = (item.get("name") or "").strip()
        if not name:
            continue  # quietly drop abandoned rows
        kind = (item.get("max_kind") or "static").strip().lower()
        if kind not in _VALID_RESOURCE_KINDS:
            raise HTTPException(
                400,
                f"Resources JSON: entry #{i} 'max_kind' must be one of {sorted(_VALID_RESOURCE_KINDS)}",
            )
        reset = (item.get("reset") or "long").strip().lower()
        if reset not in _VALID_RESOURCE_RESETS:
            raise HTTPException(
                400,
                f"Resources JSON: entry #{i} 'reset' must be one of {sorted(_VALID_RESOURCE_RESETS)}",
            )
        try:
            min_level = int(item.get("min_level", 1))
        except (TypeError, ValueError):
            raise HTTPException(400, f"Resources JSON: entry #{i} 'min_level' must be an integer")
        if min_level < 1 or min_level > 20:
            raise HTTPException(400, f"Resources JSON: entry #{i} 'min_level' must be between 1 and 20")

        rec: dict = {
            "name": name[:120],
            "min_level": min_level,
            "max_kind": kind,
            "reset": reset,
            "desc": (item.get("desc") or "").strip()[:1000],
        }

        if kind == "static":
            try:
                rec["max_static"] = int(item.get("max_static", 1))
            except (TypeError, ValueError):
                raise HTTPException(400, f"Resources JSON: entry #{i} 'max_static' must be an integer")
            if rec["max_static"] < 0 or rec["max_static"] > 999:
                raise HTTPException(400, f"Resources JSON: entry #{i} 'max_static' out of range")
        elif kind == "ability_mod":
            ab = (item.get("max_ability") or "").strip().lower()
            if ab not in ("str", "dex", "con", "int", "wis", "cha"):
                raise HTTPException(
                    400, f"Resources JSON: entry #{i} 'max_ability' must be one of str/dex/con/int/wis/cha"
                )
            rec["max_ability"] = ab
        elif kind == "level_table":
            tbl_raw = item.get("max_table") or {}
            if not isinstance(tbl_raw, dict):
                raise HTTPException(400, f"Resources JSON: entry #{i} 'max_table' must be an object")
            clean: dict = {}
            for k, v in tbl_raw.items():
                try:
                    kk = int(k)
                    vv = int(v)
                except (TypeError, ValueError):
                    raise HTTPException(
                        400, f"Resources JSON: entry #{i} 'max_table' must map integer level → integer count"
                    )
                if kk < 1 or kk > 20:
                    continue
                clean[str(kk)] = vv
            if not clean:
                raise HTTPException(400, f"Resources JSON: entry #{i} 'max_table' is empty")
            rec["max_table"] = clean
        # "proficiency" needs no extra fields.

        # Derive a stable key. Prefer explicit, then slugify the name, then
        # fall back to "resource-<index>" so we never collide on empty keys.
        key = (item.get("key") or "").strip().lower() or _slugify_for_subclass(name, max_len=60) or f"resource-{i}"
        if key in used_keys:
            key = f"{key}-{i}"
        used_keys.add(key)
        rec["key"] = key
        out.append(rec)

    return out[:50]  # cap so we don't let GMs paste hundreds


def _parse_spell_list_json(raw: str) -> list:
    """Parse + dedupe + normalise the spell_list JSON field on the custom
    class form. Accepts either a list of slug strings or a list of objects
    with a ``slug`` field (the picker emits the latter for convenience)."""
    if not raw or not raw.strip():
        return []
    import json as _json
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as e:
        raise HTTPException(400, f"Spell list JSON: invalid syntax — {e.msg} (line {e.lineno})")
    if not isinstance(parsed, list):
        raise HTTPException(400, 'Spell list JSON: must be a list of spell slugs')
    out: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(parsed, start=1):
        if isinstance(item, str):
            slug = item.strip().lower()
        elif isinstance(item, dict):
            slug = (item.get("slug") or "").strip().lower()
        else:
            raise HTTPException(400, f"Spell list entry #{i} must be a slug string or {{slug: ...}} object")
        if not slug:
            continue
        # Allow only lowercase letters / digits / dashes — matches Open5e slugs.
        if not _re_csub.match(r'^[a-z0-9-]+$', slug):
            raise HTTPException(400, f"Spell list entry #{i} contains invalid slug characters: {slug!r}")
        if slug in seen:
            continue
        seen.add(slug)
        out.append(slug)
    return out[:500]  # cap so we don't let GMs paste tens-of-thousands


@router.post("/campaign/{campaign_id}/custom-classes")
def create_custom_class(
    campaign_id: int,
    name: str = Form(...),
    hit_die: str = Form("8"),
    prof_armor: str = Form(""),
    prof_weapons: str = Form(""),
    prof_tools: str = Form(""),
    prof_saving_throws: str = Form(""),
    prof_skills: str = Form(""),
    spellcasting_ability: str = Form(""),
    equipment: str = Form(""),
    features_json: str = Form(""),
    spell_list_json: str = Form(""),
    resources_json: str = Form(""),
    mc_prereq_str: str = Form(""),
    mc_prereq_dex: str = Form(""),
    mc_prereq_con: str = Form(""),
    mc_prereq_int: str = Form(""),
    mc_prereq_wis: str = Form(""),
    mc_prereq_cha: str = Form(""),
    mc_prereq_mode: str = Form("all"),
    multiclass_proficiencies: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    cls_slug = _slugify_for_subclass(name_n, max_len=60)
    if not cls_slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    hd = _normalize_hit_die(hit_die)
    spc = _normalize_spellcasting_ability(spellcasting_ability)
    features = _parse_custom_subclass_features(features_json)
    spell_list = _parse_spell_list_json(spell_list_json)
    resources = _parse_class_resources_json(resources_json)
    mc_prereqs = _parse_multiclass_prereq_abilities({
        "str": mc_prereq_str, "dex": mc_prereq_dex, "con": mc_prereq_con,
        "int": mc_prereq_int, "wis": mc_prereq_wis, "cha": mc_prereq_cha,
    })
    mc_mode = _normalize_multiclass_mode(mc_prereq_mode)

    scope = f"campaign-{campaign_id}"
    existing = local_content.resolve(cls_slug, type="class_features", campaign_id=campaign_id)
    if existing and existing[1] == "local-homebrew":
        raise HTTPException(400, f"A homebrew class with slug '{cls_slug}' already exists in this campaign")

    local_content.write_homebrew(
        {
            "slug": cls_slug,
            "name": name_n,
            "hit_die": hd,
            "prof_armor": (prof_armor or "").strip()[:500],
            "prof_weapons": (prof_weapons or "").strip()[:500],
            "prof_tools": (prof_tools or "").strip()[:500],
            "prof_saving_throws": (prof_saving_throws or "").strip()[:120],
            "prof_skills": (prof_skills or "").strip()[:500],
            "spellcasting_ability": spc,
            "equipment": (equipment or "").strip()[:4000],
            "features": features,
            "spell_list": spell_list,
            "resources": resources,
            "multiclass_prereq_abilities": mc_prereqs,
            "multiclass_prereq_mode": mc_mode,
            "multiclass_proficiencies": (multiclass_proficiencies or "").strip()[:500],
            "actions": [],
            "system": "dnd5e",
            "scope": scope,
            "source": "homebrew",
            "owner": user.id,
        },
        type="class_features",
        scope=scope,
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-classes", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-classes/{class_slug}")
def update_custom_class(
    campaign_id: int,
    class_slug: str,
    name: str = Form(...),
    hit_die: str = Form("8"),
    prof_armor: str = Form(""),
    prof_weapons: str = Form(""),
    prof_tools: str = Form(""),
    prof_saving_throws: str = Form(""),
    prof_skills: str = Form(""),
    spellcasting_ability: str = Form(""),
    equipment: str = Form(""),
    features_json: str = Form(""),
    spell_list_json: str = Form(""),
    resources_json: str = Form(""),
    mc_prereq_str: str = Form(""),
    mc_prereq_dex: str = Form(""),
    mc_prereq_con: str = Form(""),
    mc_prereq_int: str = Form(""),
    mc_prereq_wis: str = Form(""),
    mc_prereq_cha: str = Form(""),
    mc_prereq_mode: str = Form("all"),
    multiclass_proficiencies: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Update everything but the slug. Sheets reference it; renames
    change the display name only. Delete + recreate to change the slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    scope = f"campaign-{campaign_id}"
    existing = local_content.resolve(class_slug, type="class_features", campaign_id=campaign_id)
    if not existing or existing[1] != "local-homebrew":
        raise HTTPException(404, "Custom class not found")
    prev = existing[0]

    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    hd = _normalize_hit_die(hit_die)
    spc = _normalize_spellcasting_ability(spellcasting_ability)
    features = _parse_custom_subclass_features(features_json)
    spell_list = _parse_spell_list_json(spell_list_json)
    resources = _parse_class_resources_json(resources_json)
    mc_prereqs = _parse_multiclass_prereq_abilities({
        "str": mc_prereq_str, "dex": mc_prereq_dex, "con": mc_prereq_con,
        "int": mc_prereq_int, "wis": mc_prereq_wis, "cha": mc_prereq_cha,
    })
    mc_mode = _normalize_multiclass_mode(mc_prereq_mode)

    local_content.write_homebrew(
        {
            "slug": class_slug,
            "name": name_n,
            "hit_die": hd,
            "prof_armor": (prof_armor or "").strip()[:500],
            "prof_weapons": (prof_weapons or "").strip()[:500],
            "prof_tools": (prof_tools or "").strip()[:500],
            "prof_saving_throws": (prof_saving_throws or "").strip()[:120],
            "prof_skills": (prof_skills or "").strip()[:500],
            "spellcasting_ability": spc,
            "equipment": (equipment or "").strip()[:4000],
            "features": features,
            "spell_list": spell_list,
            "resources": resources,
            "multiclass_prereq_abilities": mc_prereqs,
            "multiclass_prereq_mode": mc_mode,
            "multiclass_proficiencies": (multiclass_proficiencies or "").strip()[:500],
            "actions": prev.get("actions") or [],
            "system": "dnd5e",
            "scope": scope,
            "source": "homebrew",
            "owner": prev.get("owner") or user.id,
        },
        type="class_features",
        scope=scope,
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-classes", status_code=303
    )


@router.get("/api/campaign/{campaign_id}/custom-class-resources")
def custom_class_resources(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return every homebrew class resource recipe for this campaign.

    The sheet merges these into ``window._CLASS_RESOURCES`` at load time
    so the existing Class Resources panel surfaces homebrew counters
    alongside the curated SRD ones. Each record carries the ``class``
    slug it belongs to so the panel's existing filter-by-class logic
    works unchanged.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    # Any campaign member can read this (it's static homebrew data — the
    # GM authored it so the players could see it). Admins always allowed.
    if not user.is_admin and not _user_is_gm(user, campaign, db):
        is_member = db.query(CampaignMembership).filter(
            CampaignMembership.campaign_id == campaign_id,
            CampaignMembership.user_id == user.id,
        ).first()
        if not is_member:
            raise HTTPException(403, "Not a member of this campaign")

    records, _ = local_content.search(
        type="class_features", campaign_id=campaign_id, limit=500,
    )
    results: list[dict] = []
    for rec_file in records:
        if rec_file.get("_source") != "local-homebrew":
            continue
        cls_slug = rec_file.get("slug") or ""
        for rec in (rec_file.get("resources") or []):
            if not isinstance(rec, dict):
                continue
            results.append({**rec, "class": cls_slug, "subclass": None})
    return {"results": results}


@router.get("/api/character/{char_id}/multiclass-check")
def multiclass_check(
    char_id: int,
    target_class: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Check whether a character meets the multiclass prerequisites to add
    a level in ``target_class``.

    Resolution: campaign-scoped homebrew classes win over the shipped FS
    overrides, just like every other class lookup. If the target class has
    no prereq data, returns ``ok=true`` with an explanatory ``note`` —
    callers should treat that as "framework doesn't know the rules; trust
    the GM."
    """
    if not target_class:
        raise HTTPException(400, "target_class required")
    char = db.query(Character).filter(Character.id == char_id).first()
    if not char:
        raise HTTPException(404, "Character not found")

    # Auth: owner OR GM/admin of the campaign.
    campaign = None
    if char.campaign_id:
        campaign = db.query(Campaign).filter(Campaign.id == char.campaign_id).first()
    if not (char.owner_user_id == user.id
            or user.is_admin
            or (campaign and _user_is_gm(user, campaign, db))):
        raise HTTPException(403, "No access to this character")

    target_slug = target_class.strip().lower()
    scopes = [f"campaign:{char.campaign_id}", "global"] if char.campaign_id else ["global"]
    from .. import local_features
    record, _source = local_features.resolve_class(target_slug, scopes=scopes, db=db)

    if not record:
        return {
            "ok": True,
            "target_name": target_class,
            "reasons": [],
            "prereqs": {"abilities": {}, "mode": "all"},
            "proficiencies": "",
            "note": "No prerequisite data found for this class — no checks enforced.",
        }

    prereqs = record.get("multiclass_prereq_abilities") or {}
    mode = (record.get("multiclass_prereq_mode") or "all").lower()
    profs = record.get("multiclass_proficiencies") or ""
    target_name = record.get("name") or target_class

    if not prereqs:
        return {
            "ok": True,
            "target_name": target_name,
            "reasons": [],
            "prereqs": {"abilities": {}, "mode": mode},
            "proficiencies": profs,
            "note": f"{target_name} has no defined multiclass prerequisites.",
        }

    # Sheets store ability scores as uppercase 3-letter keys under
    # ``sheet.abilities`` (STR, DEX, …).  Fall through to lowercase and
    # default to 10 so partially-built sheets don't crash the check.
    abilities = (char.sheet or {}).get("abilities") or {}

    def _score(ab: str) -> int:
        v = abilities.get(ab.upper())
        if v is None:
            v = abilities.get(ab.lower())
        try:
            return int(v) if v is not None else 10
        except (TypeError, ValueError):
            return 10

    failed: list[str] = []
    passed: list[str] = []
    for ab, min_score in prereqs.items():
        cur = _score(ab)
        if cur < int(min_score):
            failed.append(f"{ab.upper()} {cur} (needs {min_score})")
        else:
            passed.append(f"{ab.upper()} {cur} >= {min_score}")

    if mode == "any":
        ok = bool(passed)
        if ok:
            reasons: list[str] = []
        else:
            reasons = [
                "At least one ability minimum must be met (mode: any). "
                "All failed: " + ", ".join(failed)
            ]
    else:  # "all"
        ok = not failed
        reasons = [f"Missing required minimum: {r}" for r in failed]

    return {
        "ok": ok,
        "target_name": target_name,
        "reasons": reasons,
        "prereqs": {"abilities": prereqs, "mode": mode},
        "proficiencies": profs,
    }


@router.post("/campaign/{campaign_id}/custom-classes/{class_slug}/delete")
def delete_custom_class(
    campaign_id: int,
    class_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_gm_for_campaign(campaign_id, user, db)
    scope = f"campaign-{campaign_id}"
    ok = local_content.delete_homebrew(class_slug, type="class_features", scope=scope)
    if not ok:
        raise HTTPException(404, "Custom class not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-classes", status_code=303
    )


# ── Custom races (GM-authored homebrew) ─────────────────────────────────────
#
# Mirror of the custom-class routes for races.  Shape closely matches the
# Open5e v1 race object so the existing ``format_race_text`` /
# ``parse_race_traits`` helpers in ``open5e_local.py`` can render homebrew
# without any code changes.

_VALID_SIZES = {"", "Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan"}


def _normalize_race_size(raw: str) -> str:
    v = (raw or "").strip()
    if not v:
        return ""
    # Accept any-case input but persist the canonical capitalisation.
    canon = v.title()
    if canon not in _VALID_SIZES:
        raise HTTPException(400, f"Race size must be one of: {', '.join(s for s in sorted(_VALID_SIZES) if s)}")
    return canon


def _parse_ability_bonuses(values: dict) -> list:
    """Build the Open5e-shaped ``ability_bonuses`` list from six form fields.

    Returns a list of ``{"attribute": "Strength", "bonus": 2}`` records.
    Empty fields are dropped; zero is treated as "no bonus" rather than
    explicitly storing a +0.
    """
    canonical = {
        "str": "Strength", "dex": "Dexterity", "con": "Constitution",
        "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma",
    }
    out: list = []
    for ab, raw in values.items():
        v = (raw or "").strip()
        if not v:
            continue
        try:
            n = int(v)
        except ValueError:
            raise HTTPException(400, f"Ability bonus for {ab.upper()} must be an integer (got {raw!r})")
        if n == 0:
            continue
        if n < -10 or n > 10:
            raise HTTPException(400, f"Ability bonus for {ab.upper()} out of range (-10 to 10)")
        out.append({"attribute": canonical.get(ab, ab.title()), "bonus": n})
    return out


@router.post("/campaign/{campaign_id}/custom-races")
def create_custom_race(
    campaign_id: int,
    name: str = Form(...),
    size: str = Form(""),
    speed: str = Form("30"),
    age: str = Form(""),
    alignment: str = Form(""),
    languages: str = Form(""),
    ab_str: str = Form(""),
    ab_dex: str = Form(""),
    ab_con: str = Form(""),
    ab_int: str = Form(""),
    ab_wis: str = Form(""),
    ab_cha: str = Form(""),
    traits_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    race_slug = _slugify_for_subclass(name_n, max_len=60)
    if not race_slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    size_n = _normalize_race_size(size)
    try:
        speed_n = int(speed or "30")
    except ValueError:
        raise HTTPException(400, "Speed must be an integer (feet per round)")
    if speed_n < 0 or speed_n > 200:
        raise HTTPException(400, "Speed out of range (0–200)")
    ab_bonuses = _parse_ability_bonuses({
        "str": ab_str, "dex": ab_dex, "con": ab_con,
        "int": ab_int, "wis": ab_wis, "cha": ab_cha,
    })
    # Traits share the features list shape — same parser, same rules.
    traits = _parse_custom_subclass_features(traits_json)

    existing = local_content.resolve(race_slug, type="races", campaign_id=campaign_id)
    if existing and existing[1] == "local-homebrew":
        raise HTTPException(400, f"A homebrew race with slug '{race_slug}' already exists in this campaign")
    try:
        local_content.write_homebrew(
            {
                "slug": race_slug,
                "name": name_n,
                "ability_bonuses": ab_bonuses,
                "size": size_n,
                "speed": speed_n,
                "age": (age or "").strip()[:1000],
                "alignment": (alignment or "").strip()[:1000],
                "languages": (languages or "").strip()[:1000],
                "traits": traits,
                "actions": [],
                "system": "dnd5e",
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
                "owner": user.id,
            },
            type="races",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-races", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-races/{race_slug}")
def update_custom_race(
    campaign_id: int,
    race_slug: str,
    name: str = Form(...),
    size: str = Form(""),
    speed: str = Form("30"),
    age: str = Form(""),
    alignment: str = Form(""),
    languages: str = Form(""),
    ab_str: str = Form(""),
    ab_dex: str = Form(""),
    ab_con: str = Form(""),
    ab_int: str = Form(""),
    ab_wis: str = Form(""),
    ab_cha: str = Form(""),
    traits_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based race update by slug. ``race_slug`` is immutable —
    the form only mutates the display name and other fields."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(race_slug, type="races", campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Custom race not found")
    existing = hit[0]

    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    size_n = _normalize_race_size(size)
    try:
        speed_n = int(speed or "30")
    except ValueError:
        raise HTTPException(400, "Speed must be an integer (feet per round)")
    if speed_n < 0 or speed_n > 200:
        raise HTTPException(400, "Speed out of range (0–200)")
    ab_bonuses = _parse_ability_bonuses({
        "str": ab_str, "dex": ab_dex, "con": ab_con,
        "int": ab_int, "wis": ab_wis, "cha": ab_cha,
    })
    traits = _parse_custom_subclass_features(traits_json)

    try:
        local_content.write_homebrew(
            {
                **existing,
                "slug": existing.get("slug") or race_slug,
                "name": name_n,
                "ability_bonuses": ab_bonuses,
                "size": size_n,
                "speed": speed_n,
                "age": (age or "").strip()[:1000],
                "alignment": (alignment or "").strip()[:1000],
                "languages": (languages or "").strip()[:1000],
                "traits": traits,
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
            },
            type="races",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-races", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-races/{race_slug}/delete")
def delete_custom_race(
    campaign_id: int,
    race_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based race delete by slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    try:
        removed = local_content.delete_homebrew(
            race_slug, type="races", scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not removed:
        raise HTTPException(404, "Custom race not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-races", status_code=303
    )


# ── Custom monsters (GM-authored homebrew stat blocks) ──────────────────────
#
# Mirror of the other custom-content routes. The beast picker filters by
# ``type=beast`` for Wild Shape / Polymorph; other types (humanoid, fiend,
# undead, …) surface in the picker only when "Free pick" is checked.

_VALID_MONSTER_TYPES = {
    "aberration", "beast", "celestial", "construct", "dragon", "elemental",
    "fey", "fiend", "giant", "humanoid", "monstrosity", "ooze", "plant",
    "undead",
}


def _normalize_monster_type(raw: str) -> str:
    v = (raw or "").strip().lower()
    if not v:
        return "beast"
    if v not in _VALID_MONSTER_TYPES:
        raise HTTPException(
            400,
            f"Monster type must be one of: {', '.join(sorted(_VALID_MONSTER_TYPES))}",
        )
    return v


def _parse_monster_speed(form: dict) -> dict:
    """Six optional speed fields (walk/fly/swim/climb/burrow/hover-as-flag)
    → dict suitable for the Open5e shape. Drops zeros. Walk defaults to 30
    if every field is blank so the monster isn't accidentally rooted."""
    out: dict = {}
    for kind in ("walk", "fly", "swim", "climb", "burrow"):
        raw = (form.get(f"speed_{kind}") or "").strip()
        if not raw:
            continue
        try:
            n = int(raw)
        except ValueError:
            raise HTTPException(400, f"Speed.{kind} must be an integer (got {raw!r})")
        if n < 0 or n > 999:
            raise HTTPException(400, f"Speed.{kind} out of range (0–999)")
        if n > 0:
            out[kind] = n
    if not out:
        out["walk"] = 30
    return out


def _parse_cr(raw: str) -> str:
    """Accept "0", "1/8", "1/4", "1/2", or any integer 1–30. Stored as
    text to preserve fractional notation."""
    v = (raw or "0").strip()
    fractions = {"0", "1/8", "1/4", "1/2"}
    if v in fractions:
        return v
    try:
        n = int(v)
    except ValueError:
        raise HTTPException(400, "Challenge rating must be 0, 1/8, 1/4, 1/2, or an integer 1–30")
    if n < 0 or n > 30:
        raise HTTPException(400, "Challenge rating out of range (0–30)")
    return str(n)


def _parse_ability_score(label: str, raw: str) -> int:
    try:
        n = int(raw or "10")
    except ValueError:
        raise HTTPException(400, f"{label} must be an integer (got {raw!r})")
    if n < 1 or n > 40:
        raise HTTPException(400, f"{label} out of range (1–40)")
    return n


def _coalesce_monster_actions(actions_json: str, reactions_json: str,
                              special_abilities_json: str, legendary_actions_json: str) -> list[dict]:
    """v2.0.0 helper: take the 4 legacy action-list JSON form fields and
    fold them into the single ``actions: list[Action]`` array shape that
    the Monster Pydantic model uses, with a ``category`` discriminator on
    each entry. Mirrors the migration helper in app/_migrate_v52.py.

    v2.3.8: preserves the structured attack fields (``attack_roll``,
    ``attack_bonus``, ``damage``, ``damage_type``, ``save_ability``,
    ``save_dc``) that the action-mode editor now emits on the Actions
    fieldset, so the homebrew monster's stat-block view can render
    Attack / Save / Damage buttons via ``renderActionButtons``. Passed
    through via the shared parser's ``extra_keys`` parameter."""
    import re as _re
    _attack_keys = (
        "attack_roll", "attack_bonus", "damage", "damage_type",
        "save_ability", "save_dc",
    )
    out: list[dict] = []
    for raw, cat in (
        (actions_json,            "action"),
        (reactions_json,          "reaction"),
        (special_abilities_json,  "special_ability"),
        (legendary_actions_json,  "legendary_action"),
    ):
        for entry in _parse_custom_subclass_features(raw, extra_keys=_attack_keys):
            if not isinstance(entry, dict):
                continue
            name = (entry.get("name") or "").strip()
            slug_id = _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or f"unnamed-{cat}"
            rec: dict = {
                "id": entry.get("id") or slug_id,
                "name": name,
                "desc": entry.get("desc") or "",
                "min_level": entry.get("level") or 1,
                "category": cat,
            }
            # Accept the attack keys on any category for forward-compatibility
            # (e.g. a Legendary action that itself involves an attack roll).
            for k in _attack_keys:
                v = entry.get(k)
                if v not in (None, "", False, 0):
                    rec[k] = v
            out.append(rec)
    return out


@router.post("/campaign/{campaign_id}/custom-monsters")
def create_custom_monster(
    campaign_id: int,
    name: str = Form(...),
    size: str = Form("Medium"),
    type: str = Form("beast"),
    alignment: str = Form("unaligned"),
    armor_class: str = Form("10"),
    armor_desc: str = Form(""),
    hit_points: str = Form("1"),
    hit_dice: str = Form(""),
    speed_walk: str = Form(""),
    speed_fly: str = Form(""),
    speed_swim: str = Form(""),
    speed_climb: str = Form(""),
    speed_burrow: str = Form(""),
    strength: str = Form("10"),
    dexterity: str = Form("10"),
    constitution: str = Form("10"),
    intelligence: str = Form("10"),
    wisdom: str = Form("10"),
    charisma: str = Form("10"),
    damage_vulnerabilities: str = Form(""),
    damage_resistances: str = Form(""),
    damage_immunities: str = Form(""),
    condition_immunities: str = Form(""),
    senses: str = Form(""),
    languages: str = Form(""),
    challenge_rating: str = Form("0"),
    actions_json: str = Form(""),
    reactions_json: str = Form(""),
    special_abilities_json: str = Form(""),
    legendary_actions_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    monster_slug = _slugify_for_subclass(name_n, max_len=80)
    if not monster_slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    size_n = _normalize_race_size(size) or "Medium"  # reuse the size validator
    type_n = _normalize_monster_type(type)
    try:
        ac = int(armor_class or "10")
    except ValueError:
        raise HTTPException(400, "Armor class must be an integer")
    if ac < 1 or ac > 40:
        raise HTTPException(400, "Armor class out of range (1–40)")
    try:
        hp = int(hit_points or "1")
    except ValueError:
        raise HTTPException(400, "Hit points must be an integer")
    if hp < 1 or hp > 9999:
        raise HTTPException(400, "Hit points out of range (1–9999)")
    speed = _parse_monster_speed({
        "speed_walk": speed_walk, "speed_fly": speed_fly, "speed_swim": speed_swim,
        "speed_climb": speed_climb, "speed_burrow": speed_burrow,
    })
    cr = _parse_cr(challenge_rating)

    existing_hit = local_content.resolve(monster_slug, type="monsters", campaign_id=campaign_id)
    if existing_hit and existing_hit[1] == "local-homebrew":
        raise HTTPException(400, f"A homebrew monster with slug '{monster_slug}' already exists in this campaign")
    try:
        local_content.write_homebrew(
            {
                "slug": monster_slug,
                "name": name_n,
                "size": size_n,
                "type": type_n,
                "alignment": (alignment or "").strip()[:120],
                "armor_class": ac,
                "armor_desc": (armor_desc or "").strip()[:120],
                "hit_points": hp,
                "hit_dice": (hit_dice or "").strip()[:40],
                "speed": speed,
                "strength": _parse_ability_score("STR", strength),
                "dexterity": _parse_ability_score("DEX", dexterity),
                "constitution": _parse_ability_score("CON", constitution),
                "intelligence": _parse_ability_score("INT", intelligence),
                "wisdom": _parse_ability_score("WIS", wisdom),
                "charisma": _parse_ability_score("CHA", charisma),
                "damage_vulnerabilities": (damage_vulnerabilities or "").strip()[:500],
                "damage_resistances": (damage_resistances or "").strip()[:500],
                "damage_immunities": (damage_immunities or "").strip()[:500],
                "condition_immunities": (condition_immunities or "").strip()[:500],
                "senses": (senses or "").strip()[:500],
                "languages": (languages or "").strip()[:500],
                "challenge_rating": cr,
                # v2.0.0 unified action list with category discriminator.
                "actions": _coalesce_monster_actions(
                    actions_json, reactions_json, special_abilities_json, legendary_actions_json,
                ),
                "system": "dnd5e",
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
                "owner": user.id,
            },
            type="monsters",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-monsters", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-monsters/{monster_slug}")
def update_custom_monster(
    campaign_id: int,
    monster_slug: str,
    name: str = Form(...),
    size: str = Form("Medium"),
    type: str = Form("beast"),
    alignment: str = Form("unaligned"),
    armor_class: str = Form("10"),
    armor_desc: str = Form(""),
    hit_points: str = Form("1"),
    hit_dice: str = Form(""),
    speed_walk: str = Form(""),
    speed_fly: str = Form(""),
    speed_swim: str = Form(""),
    speed_climb: str = Form(""),
    speed_burrow: str = Form(""),
    strength: str = Form("10"),
    dexterity: str = Form("10"),
    constitution: str = Form("10"),
    intelligence: str = Form("10"),
    wisdom: str = Form("10"),
    charisma: str = Form("10"),
    damage_vulnerabilities: str = Form(""),
    damage_resistances: str = Form(""),
    damage_immunities: str = Form(""),
    condition_immunities: str = Form(""),
    senses: str = Form(""),
    languages: str = Form(""),
    challenge_rating: str = Form("0"),
    actions_json: str = Form(""),
    reactions_json: str = Form(""),
    special_abilities_json: str = Form(""),
    legendary_actions_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based monster update by slug. ``monster_slug`` is immutable —
    token templates and beast-favorites reference it."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(monster_slug, type="monsters", campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Custom monster not found")
    existing = hit[0]

    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    size_n = _normalize_race_size(size) or "Medium"
    type_n = _normalize_monster_type(type)
    try:
        ac = int(armor_class or "10")
    except ValueError:
        raise HTTPException(400, "Armor class must be an integer")
    if ac < 1 or ac > 40:
        raise HTTPException(400, "Armor class out of range (1–40)")
    try:
        hp = int(hit_points or "1")
    except ValueError:
        raise HTTPException(400, "Hit points must be an integer")
    if hp < 1 or hp > 9999:
        raise HTTPException(400, "Hit points out of range (1–9999)")
    speed = _parse_monster_speed({
        "speed_walk": speed_walk, "speed_fly": speed_fly, "speed_swim": speed_swim,
        "speed_climb": speed_climb, "speed_burrow": speed_burrow,
    })
    cr = _parse_cr(challenge_rating)

    try:
        local_content.write_homebrew(
            {
                **existing,
                "slug": existing.get("slug") or monster_slug,
                "name": name_n,
                "size": size_n,
                "type": type_n,
                "alignment": (alignment or "").strip()[:120],
                "armor_class": ac,
                "armor_desc": (armor_desc or "").strip()[:120],
                "hit_points": hp,
                "hit_dice": (hit_dice or "").strip()[:40],
                "speed": speed,
                "strength": _parse_ability_score("STR", strength),
                "dexterity": _parse_ability_score("DEX", dexterity),
                "constitution": _parse_ability_score("CON", constitution),
                "intelligence": _parse_ability_score("INT", intelligence),
                "wisdom": _parse_ability_score("WIS", wisdom),
                "charisma": _parse_ability_score("CHA", charisma),
                "damage_vulnerabilities": (damage_vulnerabilities or "").strip()[:500],
                "damage_resistances": (damage_resistances or "").strip()[:500],
                "damage_immunities": (damage_immunities or "").strip()[:500],
                "condition_immunities": (condition_immunities or "").strip()[:500],
                "senses": (senses or "").strip()[:500],
                "languages": (languages or "").strip()[:500],
                "challenge_rating": cr,
                "actions": _coalesce_monster_actions(
                    actions_json, reactions_json, special_abilities_json, legendary_actions_json,
                ),
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
            },
            type="monsters",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-monsters", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-monsters/{monster_slug}/delete")
def delete_custom_monster(
    campaign_id: int,
    monster_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based monster delete by slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    try:
        removed = local_content.delete_homebrew(
            monster_slug, type="monsters", scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not removed:
        raise HTTPException(404, "Custom monster not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-monsters", status_code=303
    )


# ── Custom backgrounds (GM-authored homebrew) ───────────────────────────────

@router.post("/campaign/{campaign_id}/custom-backgrounds")
def create_custom_background(
    campaign_id: int,
    name: str = Form(...),
    description: str = Form(""),
    skill_proficiencies: str = Form(""),
    tool_proficiencies: str = Form(""),
    languages: str = Form(""),
    equipment: str = Form(""),
    feature_name: str = Form(""),
    feature_desc: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based homebrew create. See create_custom_feat for the pattern."""
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    slug = _slugify_for_subclass(name_n, max_len=60)
    if not slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    existing = local_content.resolve(slug, type="backgrounds", campaign_id=campaign_id)
    if existing and existing[1] == "local-homebrew":
        raise HTTPException(400, f"A homebrew background with slug '{slug}' already exists in this campaign")
    try:
        local_content.write_homebrew(
            {
                "slug": slug,
                "name": name_n,
                "description": (description or "").strip()[:8000],
                "skill_proficiencies": (skill_proficiencies or "").strip()[:500],
                "tool_proficiencies": (tool_proficiencies or "").strip()[:500],
                "languages": (languages or "").strip()[:500],
                "equipment": (equipment or "").strip()[:4000],
                "feature_name": (feature_name or "").strip()[:160],
                "feature_desc": (feature_desc or "").strip()[:4000],
                "actions": [],
                "system": "dnd5e",
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
                "owner": user.id,
            },
            type="backgrounds",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-backgrounds", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-backgrounds/{bg_slug}")
def update_custom_background(
    campaign_id: int,
    bg_slug: str,
    name: str = Form(...),
    description: str = Form(""),
    skill_proficiencies: str = Form(""),
    tool_proficiencies: str = Form(""),
    languages: str = Form(""),
    equipment: str = Form(""),
    feature_name: str = Form(""),
    feature_desc: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based homebrew update by slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(bg_slug, type="backgrounds", campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Custom background not found")
    existing = hit[0]
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    try:
        local_content.write_homebrew(
            {
                **existing,
                "slug": existing.get("slug") or bg_slug,
                "name": name_n,
                "description": (description or "").strip()[:8000],
                "skill_proficiencies": (skill_proficiencies or "").strip()[:500],
                "tool_proficiencies": (tool_proficiencies or "").strip()[:500],
                "languages": (languages or "").strip()[:500],
                "equipment": (equipment or "").strip()[:4000],
                "feature_name": (feature_name or "").strip()[:160],
                "feature_desc": (feature_desc or "").strip()[:4000],
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
            },
            type="backgrounds",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-backgrounds", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-backgrounds/{bg_slug}/delete")
def delete_custom_background(
    campaign_id: int,
    bg_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.0.0: file-based homebrew delete by slug."""
    _require_gm_for_campaign(campaign_id, user, db)
    try:
        removed = local_content.delete_homebrew(
            bg_slug, type="backgrounds", scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not removed:
        raise HTTPException(404, "Custom background not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-backgrounds", status_code=303
    )


# ── Custom feats (GM-authored homebrew) ─────────────────────────────────────

@router.post("/campaign/{campaign_id}/custom-feats")
def create_custom_feat(
    campaign_id: int,
    name: str = Form(...),
    prerequisite: str = Form(""),
    desc: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Create a campaign-scoped homebrew feat as a JSON file in the homebrew
    Docker volume. The slug is derived from the name and must be unique
    within the campaign-scope directory. v2.0.0: replaces the legacy
    CustomFeat DB write path."""
    _require_gm_for_campaign(campaign_id, user, db)
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    slug = _slugify_for_subclass(name_n, max_len=80)
    if not slug:
        raise HTTPException(400, "Name does not yield a valid slug — use letters or numbers")
    # Uniqueness check against the file-based homebrew. Note: resolve() walks
    # campaign-scope first, then global — we only care about a clash inside
    # this campaign's scope so the broader-tier records don't false-positive.
    existing = local_content.resolve(slug, type="feats", campaign_id=campaign_id)
    if existing and (existing[1] == "local-homebrew"):
        raise HTTPException(400, f"A homebrew feat with slug '{slug}' already exists in this campaign")
    try:
        local_content.write_homebrew(
            {
                "slug": slug,
                "name": name_n,
                "prerequisite": (prerequisite or "").strip()[:500],
                "desc": (desc or "").strip()[:8000],
                "actions": [],
                "system": "dnd5e",
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
                "owner": user.id,
            },
            type="feats",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-feats", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-feats/{feat_slug}")
def update_custom_feat(
    campaign_id: int,
    feat_slug: str,
    name: str = Form(...),
    prerequisite: str = Form(""),
    desc: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Update a campaign-scoped homebrew feat by slug. v2.0.0: feat_slug
    replaces the legacy int feat_id in the URL contract — the file-based
    backing has no integer primary key."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(feat_slug, type="feats", campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Custom feat not found")
    existing = hit[0]
    name_n = (name or "").strip()[:120]
    if not name_n:
        raise HTTPException(400, "Name is required")
    # Atomic rewrite: preserve actions, owner, attribution; replace editable
    # fields with the form payload.
    try:
        local_content.write_homebrew(
            {
                **existing,
                "slug": existing.get("slug") or feat_slug,
                "name": name_n,
                "prerequisite": (prerequisite or "").strip()[:500],
                "desc": (desc or "").strip()[:8000],
                "scope": f"campaign-{campaign_id}",
                "source": "homebrew",
            },
            type="feats",
            scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-feats", status_code=303
    )


@router.post("/campaign/{campaign_id}/custom-feats/{feat_slug}/delete")
def delete_custom_feat(
    campaign_id: int,
    feat_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Delete a campaign-scoped homebrew feat by slug. v2.0.0: feat_slug
    replaces the legacy int feat_id in the URL contract."""
    _require_gm_for_campaign(campaign_id, user, db)
    try:
        removed = local_content.delete_homebrew(
            feat_slug, type="feats", scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not removed:
        raise HTTPException(404, "Custom feat not found")
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-feats", status_code=303
    )


# ── Homebrew clone (v2.3.37) ────────────────────────────────────────────────
# One generic helper + six thin route handlers. Each handler accepts the
# type-specific URL contract (``feat_slug`` / ``bg_slug`` / ``monster_slug``
# / ``race_slug`` / ``class_slug`` / ``combined_slug`` for subclasses) and
# delegates the actual clone work to ``_clone_homebrew_record`` which
# handles the source lookup, slug-collision-safe new slug generation, name
# rewrite (``"Copy of <original>"``), and disk write. Each redirects back
# to ``/campaign/{cid}/settings#custom-{type}`` so the GM sees the newly-
# cloned entry in the homebrew list and can expand its editor inline. No
# clone for shipped SRD content — only ``local-homebrew`` source records
# can be cloned (the resolver source check guards against accidentally
# forking SRD into homebrew).


def _unique_clone_slug(base: str, content_type: str, campaign_id: int) -> str:
    """Build a fresh, collision-safe homebrew slug for a clone.

    Starts with ``copy-of-{base}`` (after re-slugifying — handles base slugs
    that themselves came from "Copy of Copy of …" deep clones). If that
    collides with an existing homebrew record in the campaign scope, appends
    ``-2``, ``-3``, … until the resolver returns no hit. Bounded loop —
    we'll never realistically iterate past a few attempts, but cap at 50
    to be safe.
    """
    base = _slugify_for_subclass(base, max_len=60) or "clone"
    candidate = _slugify_for_subclass(f"copy-of-{base}", max_len=80) or "copy"
    suffix = 1
    while suffix < 50:
        hit = local_content.resolve(
            candidate, type=content_type, campaign_id=campaign_id,
        )
        if not hit:
            return candidate
        suffix += 1
        candidate = _slugify_for_subclass(f"copy-of-{base}-{suffix}", max_len=80)
    raise HTTPException(500, "Could not generate a unique clone slug")


def _clone_homebrew_record(
    *,
    campaign_id: int,
    user: User,
    db: Session,
    src_slug: str,
    content_type: str,
    target_slug: Optional[str] = None,
) -> str:
    """Read a homebrew source record, write a clone with a fresh slug + a
    'Copy of …' name. Returns the new slug. Raises 404 if the source
    isn't a campaign-scope homebrew (won't clone shipped SRD content)
    and 403 if the caller isn't the GM.

    ``target_slug`` lets the subclass clone path supply a fully-qualified
    ``{class_slug}-{subclass_slug}`` instead of letting the helper pick
    a flat ``copy-of-{slug}`` — subclass slugs MUST stay namespaced by
    their parent class so the resolver can route lookups correctly.
    """
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(src_slug, type=content_type, campaign_id=campaign_id)
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Source homebrew record not found")
    source, _ = hit
    new_slug = target_slug or _unique_clone_slug(
        src_slug, content_type, campaign_id,
    )
    new_name = f"Copy of {source.get('name') or src_slug}"
    new_record = {
        **source,
        "slug": new_slug,
        "name": new_name[:200],
        "scope": f"campaign-{campaign_id}",
        "source": "homebrew",
    }
    try:
        local_content.write_homebrew(
            new_record, type=content_type, scope=f"campaign-{campaign_id}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return new_slug


@router.post("/campaign/{campaign_id}/custom-feats/{feat_slug}/clone")
def clone_custom_feat(
    campaign_id: int, feat_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=feat_slug, content_type="feats",
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-feats", status_code=303,
    )


@router.post("/campaign/{campaign_id}/custom-backgrounds/{bg_slug}/clone")
def clone_custom_background(
    campaign_id: int, bg_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=bg_slug, content_type="backgrounds",
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-backgrounds", status_code=303,
    )


@router.post("/campaign/{campaign_id}/custom-races/{race_slug}/clone")
def clone_custom_race(
    campaign_id: int, race_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=race_slug, content_type="races",
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-races", status_code=303,
    )


@router.post("/campaign/{campaign_id}/custom-monsters/{monster_slug}/clone")
def clone_custom_monster(
    campaign_id: int, monster_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=monster_slug, content_type="monsters",
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-monsters", status_code=303,
    )


@router.post("/campaign/{campaign_id}/custom-classes/{class_slug}/clone")
def clone_custom_class(
    campaign_id: int, class_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=class_slug, content_type="class_features",
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-classes", status_code=303,
    )


@router.post("/campaign/{campaign_id}/custom-subclasses/{combined_slug}/clone")
def clone_custom_subclass(
    campaign_id: int, combined_slug: str,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    """Subclass slugs are ``{class_slug}-{subclass_slug}`` to keep them
    namespaced by parent class. Preserve the class prefix; only mutate
    the subclass part so the clone stays a sibling of its parent class.
    Falls back to letting ``_unique_clone_slug`` pick a flat name when
    the source slug doesn't contain a recognizable class prefix."""
    _require_gm_for_campaign(campaign_id, user, db)
    hit = local_content.resolve(
        combined_slug, type="subclass_features", campaign_id=campaign_id,
    )
    if not hit or hit[1] != "local-homebrew":
        raise HTTPException(404, "Source homebrew subclass not found")
    source, _ = hit
    cls_slug = (source.get("class_slug") or "").strip()
    sub_slug = (source.get("slug") or combined_slug).strip()
    # Strip the class prefix from the combined slug to extract just the
    # subclass portion, then re-prefix with ``copy-of-`` so the result
    # stays under the same parent class. ``copy-of-...`` instead of
    # ``...-copy`` matches the flat clones' convention.
    if cls_slug and sub_slug.startswith(cls_slug + "-"):
        bare_sub = sub_slug[len(cls_slug) + 1:]
    else:
        bare_sub = sub_slug
    target_slug = None
    if cls_slug and bare_sub:
        candidate = _slugify_for_subclass(
            f"{cls_slug}-copy-of-{bare_sub}", max_len=80,
        )
        # Collision check — append numeric suffix if needed.
        suffix = 1
        while suffix < 50:
            hit = local_content.resolve(
                candidate, type="subclass_features", campaign_id=campaign_id,
            )
            if not hit:
                target_slug = candidate
                break
            suffix += 1
            candidate = _slugify_for_subclass(
                f"{cls_slug}-copy-of-{bare_sub}-{suffix}", max_len=80,
            )
    _clone_homebrew_record(
        campaign_id=campaign_id, user=user, db=db,
        src_slug=combined_slug, content_type="subclass_features",
        target_slug=target_slug,
    )
    return RedirectResponse(
        f"/campaign/{campaign_id}/settings#custom-subclasses", status_code=303,
    )


# ── Homebrew import / export / template ─────────────────────────────────────
#
# Bulk JSON I/O for every homebrew content type in one combined file. The
# file format is intentionally a near-mirror of the DB column names per row
# so a hand-edited template (downloaded from ``/homebrew/template``) goes
# straight back in without any client-side massaging. Import deduplicates
# on slug — existing rows in the destination campaign are skipped rather
# than overwritten, matching the safer default of "import only adds".

HOMEBREW_EXPORT_VERSION = 1


# _class_to_dict / _subclass_to_dict / _race_to_dict helpers removed in
# v2.0.0 — export endpoint inlines projections from local_content results.


def _monster_record_to_export(r: dict) -> dict:
    """Helper: project a file-based monster record back to the legacy export
    shape (with `monster_slug` + 4 split action lists). v2.0.0."""
    by_cat: dict[str, list] = {"action": [], "reaction": [], "special_ability": [], "legendary_action": []}
    for a in r.get("actions") or []:
        cat = a.get("category") or "action"
        if cat in by_cat:
            by_cat[cat].append({"name": a.get("name"), "desc": a.get("desc"), "level": a.get("min_level")})
    return {
        "monster_slug": r.get("slug"),
        "name": r.get("name"),
        "size": r.get("size") or "Medium",
        "type": r.get("type") or "beast",
        "alignment": r.get("alignment") or "unaligned",
        "armor_class": r.get("armor_class"),
        "armor_desc": r.get("armor_desc") or "",
        "hit_points": r.get("hit_points"),
        "hit_dice": r.get("hit_dice") or "",
        "speed": r.get("speed") or {"walk": 30},
        "strength": r.get("strength"), "dexterity": r.get("dexterity"),
        "constitution": r.get("constitution"), "intelligence": r.get("intelligence"),
        "wisdom": r.get("wisdom"), "charisma": r.get("charisma"),
        "damage_vulnerabilities": r.get("damage_vulnerabilities") or "",
        "damage_resistances": r.get("damage_resistances") or "",
        "damage_immunities": r.get("damage_immunities") or "",
        "condition_immunities": r.get("condition_immunities") or "",
        "senses": r.get("senses") or "",
        "languages": r.get("languages") or "",
        "challenge_rating": r.get("challenge_rating") or "0",
        "actions": by_cat["action"],
        "reactions": by_cat["reaction"],
        "special_abilities": by_cat["special_ability"],
        "legendary_actions": by_cat["legendary_action"],
    }


# _background_to_dict helper removed in v2.0.0 — export endpoint inlines
# the legacy-field-name projection from local_content.search results.


# _feat_to_dict helper removed in v2.0.0 — the export endpoint now reads
# directly from local_content.search() and projects to the legacy field-name
# shape inline. Other Custom* types still have their helpers until their own
# Phase C step lands.


@router.get("/api/campaign/{campaign_id}/homebrew/export")
def export_homebrew(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return every homebrew row for this campaign in one combined JSON
    pack. GM only. The shape matches what /homebrew/import accepts so
    round-tripping export → import into another campaign works without
    edits."""
    campaign = _require_gm_for_campaign(campaign_id, user, db)
    from datetime import datetime as _dt
    return {
        "format": "simplevtt-homebrew",
        "version": HOMEBREW_EXPORT_VERSION,
        "campaign": campaign.name,
        "exported_at": _dt.utcnow().isoformat() + "Z",
        # Classes: v2.0.0 — file-based homebrew tier, project to legacy `class_slug`.
        "classes": [
            {
                "class_slug": r.get("slug"),
                "name": r.get("name"),
                "hit_die": r.get("hit_die") or 8,
                "prof_armor": r.get("prof_armor") or "",
                "prof_weapons": r.get("prof_weapons") or "",
                "prof_tools": r.get("prof_tools") or "",
                "prof_saving_throws": r.get("prof_saving_throws") or "",
                "prof_skills": r.get("prof_skills") or "",
                "spellcasting_ability": r.get("spellcasting_ability") or "",
                "equipment": r.get("equipment") or "",
                "features": r.get("features") or [],
                "spell_list": r.get("spell_list") or [],
                "multiclass_prereq_abilities": r.get("multiclass_prereq_abilities") or {},
                "multiclass_prereq_mode": r.get("multiclass_prereq_mode") or "all",
                "multiclass_proficiencies": r.get("multiclass_proficiencies") or "",
                "resources": r.get("resources") or [],
            }
            for r in local_content.search(type="class_features", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
        # Subclasses: v2.0.0 — file-based homebrew tier, project from combined
        # `<class>__<sub>` slug back to split fields the importer accepts.
        "subclasses": [
            {
                "class_slug": (r.get("slug") or "").partition("__")[0] or r.get("class_slug") or "",
                "sub_slug": (r.get("slug") or "").partition("__")[2] or r.get("slug") or "",
                "name": r.get("name"),
                "flavor": r.get("subclass_flavor") or r.get("flavor") or "",
                "features": r.get("features") or [],
            }
            for r in local_content.search(type="subclass_features", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
        # Races: v2.0.0 — file-based homebrew tier, project to legacy `race_slug`.
        "races": [
            {
                "race_slug": r.get("slug"),
                "name": r.get("name"),
                "ability_bonuses": r.get("ability_bonuses") or [],
                "size": r.get("size") or "",
                "speed": r.get("speed"),
                "age": r.get("age") or "",
                "alignment": r.get("alignment") or "",
                "languages": r.get("languages") or "",
                "traits": r.get("traits") or [],
            }
            for r in local_content.search(type="races", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
        "monsters": [
            _monster_record_to_export(r)
            for r in local_content.search(type="monsters", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
        # Backgrounds: v2.0.0 — file-based homebrew tier, projected back to
        # the legacy `background_slug` field for round-tripping.
        "backgrounds": [
            {
                "background_slug": r.get("slug"),
                "name": r.get("name"),
                "description": r.get("description") or "",
                "skill_proficiencies": r.get("skill_proficiencies") or "",
                "tool_proficiencies": r.get("tool_proficiencies") or "",
                "languages": r.get("languages") or "",
                "equipment": r.get("equipment") or "",
                "feature_name": r.get("feature_name") or "",
                "feature_desc": r.get("feature_desc") or "",
            }
            for r in local_content.search(type="backgrounds", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
        # Feats: v2.0.0 — read from file-based homebrew tier and project back
        # to the legacy `feat_slug` field name so existing exports round-trip
        # cleanly when re-imported (the importer accepts either `feat_slug`
        # or the new `slug` field).
        "feats": [
            {
                "feat_slug": r.get("slug"),
                "name": r.get("name"),
                "prerequisite": r.get("prerequisite") or "",
                "desc": r.get("desc") or "",
            }
            for r in local_content.search(type="feats", campaign_id=campaign_id, limit=500)[0]
            if r.get("_source") == "local-homebrew"
        ],
    }


@router.get("/api/campaign/{campaign_id}/homebrew/template")
def homebrew_template(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return an annotated JSON template with one example row per content
    type. Slugs use the ``example-…`` prefix so a hand-edited template
    that's accidentally imported as-is is easy to spot and clean up."""
    _require_gm_for_campaign(campaign_id, user, db)
    return {
        "format": "simplevtt-homebrew",
        "version": HOMEBREW_EXPORT_VERSION,
        "_doc": [
            "One example row per content type. Fill in or delete each list as needed.",
            "Slugs are auto-generated from name on import — the slug field is informational.",
            "Import skips any row whose slug already exists in the destination campaign.",
        ],
        "classes": [{
            "class_slug": "example-class",
            "name": "Example Class",
            "hit_die": 8,
            "prof_armor": "Light armor",
            "prof_weapons": "Simple weapons",
            "prof_tools": "",
            "prof_saving_throws": "Dexterity, Intelligence",
            "prof_skills": "Choose two from Arcana, Investigation, Perception",
            "spellcasting_ability": "int",
            "equipment": "Starting equipment here",
            "features": [{"name": "Example Feature", "level": 1, "desc": "What it does."}],
            "spell_list": ["fire-bolt", "mage-hand"],
            "multiclass_prereq_abilities": {"int": 13},
            "multiclass_prereq_mode": "all",
            "multiclass_proficiencies": "Light armor",
            "resources": [{
                "key": "example-resource", "name": "Example Resource", "min_level": 2,
                "max_kind": "level_table", "max_table": {"2": 1, "10": 2},
                "reset": "short", "desc": "Refills on a short rest."
            }],
        }],
        "subclasses": [{
            "class_slug": "druid", "sub_slug": "example-circle",
            "name": "Example Circle",
            "flavor": "Druids of the example circle...",
            "features": [{"name": "Bonus Cantrip", "level": 2, "desc": "You learn one extra druid cantrip."}],
        }],
        "races": [{
            "race_slug": "example-race", "name": "Example Race",
            "ability_bonuses": [{"attribute": "Dexterity", "bonus": 2}, {"attribute": "Intelligence", "bonus": 1}],
            "size": "Medium", "speed": 30,
            "age": "Mature like humans; live 200 years.",
            "alignment": "Most are neutral.",
            "languages": "Common, one of your choice.",
            "traits": [{"name": "Darkvision", "desc": "You see in dim light within 60 feet."}],
        }],
        "monsters": [{
            "monster_slug": "example-monster", "name": "Example Monster",
            "size": "Medium", "type": "beast", "alignment": "unaligned",
            "armor_class": 13, "armor_desc": "natural armor",
            "hit_points": 22, "hit_dice": "4d8+4",
            "speed": {"walk": 40},
            "strength": 15, "dexterity": 14, "constitution": 13,
            "intelligence": 3, "wisdom": 12, "charisma": 6,
            "damage_resistances": "", "damage_immunities": "",
            "damage_vulnerabilities": "", "condition_immunities": "",
            "senses": "darkvision 60 ft., passive Perception 12",
            "languages": "",
            "challenge_rating": "1",
            "actions": [{"name": "Bite", "desc": "Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 7 (1d8 + 2) piercing damage."}],
            "reactions": [], "special_abilities": [], "legendary_actions": [],
        }],
        "backgrounds": [{
            "background_slug": "example-background", "name": "Example Background",
            "description": "Short narrative description.",
            "skill_proficiencies": "Survival, History",
            "tool_proficiencies": "Cartographer's tools",
            "languages": "One of your choice",
            "equipment": "A traveler's pack and 10 gp",
            "feature_name": "Signature Feature",
            "feature_desc": "What this background's signature feature does.",
        }],
        "feats": [{
            "feat_slug": "example-feat", "name": "Example Feat",
            "prerequisite": "Strength 13 or higher",
            "desc": "What the feat does.\n\n• Bullet one.\n• Bullet two.",
        }],
    }


def _safe_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_str(v, max_len: int = 500) -> str:
    s = str(v or "").strip()
    return s[:max_len]


@router.post("/api/campaign/{campaign_id}/homebrew/import")
async def import_homebrew(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Bulk-import homebrew rows from a JSON pack (matching the
    ``/homebrew/export`` shape).

    Rows whose slug already exists in this campaign are silently skipped
    so re-importing a pack you've already pulled in is a no-op. Each
    content type is processed independently — a malformed entry in one
    list doesn't kill the rest of the import. Returns per-type counts of
    ``created`` / ``skipped`` / ``errors`` so the GM can see what landed.
    """
    _require_gm_for_campaign(campaign_id, user, db)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Expected a JSON object — the export format root.")
    if body.get("format") and body["format"] != "simplevtt-homebrew":
        raise HTTPException(400, "Wrong format — expected ``simplevtt-homebrew``.")
    if body.get("version") and int(body.get("version", 0)) > HOMEBREW_EXPORT_VERSION:
        raise HTTPException(400, f"Pack version {body.get('version')} is newer than this server supports ({HOMEBREW_EXPORT_VERSION}). Upgrade first.")

    stats: dict[str, dict] = {
        k: {"created": 0, "skipped": 0, "errors": 0}
        for k in ("classes", "subclasses", "races", "monsters", "backgrounds", "feats")
    }

    def _existing_class(slug: str) -> bool:
        hit = local_content.resolve(slug, type="class_features", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    def _existing_subclass(class_slug: str, sub_slug: str) -> bool:
        combined = f"{class_slug}__{sub_slug}"
        hit = local_content.resolve(combined, type="subclass_features", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    def _existing_race(slug: str) -> bool:
        hit = local_content.resolve(slug, type="races", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    def _existing_monster(slug: str) -> bool:
        hit = local_content.resolve(slug, type="monsters", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    def _existing_background(slug: str) -> bool:
        hit = local_content.resolve(slug, type="backgrounds", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    def _existing_feat(slug: str) -> bool:
        # v2.0.0: file-based homebrew tier. resolve() returns the highest-
        # priority hit including shipped SRD; we only want to mark "already
        # exists" if the campaign's own homebrew file claims the slug.
        hit = local_content.resolve(slug, type="feats", campaign_id=campaign_id)
        return bool(hit and hit[1] == "local-homebrew")

    # ── Classes ─────────────────────────────────────────────────────────
    for row in (body.get("classes") or [])[:200]:
        if not isinstance(row, dict):
            stats["classes"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            slug = _slugify_for_subclass(name, max_len=60) or _safe_str(row.get("class_slug"), 60)
            if not name or not slug:
                stats["classes"]["errors"] += 1
                continue
            if _existing_class(slug):
                stats["classes"]["skipped"] += 1
                continue
            local_content.write_homebrew(
                {
                    "slug": slug,
                    "name": name,
                    "hit_die": _safe_int(row.get("hit_die"), 8),
                    "prof_armor": _safe_str(row.get("prof_armor"), 500),
                    "prof_weapons": _safe_str(row.get("prof_weapons"), 500),
                    "prof_tools": _safe_str(row.get("prof_tools"), 500),
                    "prof_saving_throws": _safe_str(row.get("prof_saving_throws"), 120),
                    "prof_skills": _safe_str(row.get("prof_skills"), 500),
                    "spellcasting_ability": _safe_str(row.get("spellcasting_ability"), 10).lower(),
                    "equipment": _safe_str(row.get("equipment"), 4000),
                    "features": row.get("features") if isinstance(row.get("features"), list) else [],
                    "spell_list": row.get("spell_list") if isinstance(row.get("spell_list"), list) else [],
                    "multiclass_prereq_abilities": row.get("multiclass_prereq_abilities") if isinstance(row.get("multiclass_prereq_abilities"), dict) else {},
                    "multiclass_prereq_mode": _safe_str(row.get("multiclass_prereq_mode") or "all", 8),
                    "multiclass_proficiencies": _safe_str(row.get("multiclass_proficiencies"), 500),
                    "resources": row.get("resources") if isinstance(row.get("resources"), list) else [],
                    "actions": [],
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="class_features",
                scope=f"campaign-{campaign_id}",
            )
            stats["classes"]["created"] += 1
        except Exception:
            stats["classes"]["errors"] += 1

    # ── Subclasses ──────────────────────────────────────────────────────
    for row in (body.get("subclasses") or [])[:500]:
        if not isinstance(row, dict):
            stats["subclasses"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            class_slug = _slugify_for_subclass(_safe_str(row.get("class_slug"), 60), max_len=60)
            sub_slug = _slugify_for_subclass(name, max_len=80) or _safe_str(row.get("sub_slug"), 80)
            if not name or not class_slug or not sub_slug:
                stats["subclasses"]["errors"] += 1
                continue
            if _existing_subclass(class_slug, sub_slug):
                stats["subclasses"]["skipped"] += 1
                continue
            local_content.write_homebrew(
                {
                    "slug": f"{class_slug}__{sub_slug}",
                    "name": name,
                    "class_slug": class_slug,
                    "subclass_flavor": _safe_str(row.get("flavor"), 4000),
                    "features": row.get("features") if isinstance(row.get("features"), list) else [],
                    "actions": [],
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="subclass_features",
                scope=f"campaign-{campaign_id}",
            )
            stats["subclasses"]["created"] += 1
        except Exception:
            stats["subclasses"]["errors"] += 1

    # ── Races ───────────────────────────────────────────────────────────
    for row in (body.get("races") or [])[:200]:
        if not isinstance(row, dict):
            stats["races"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            slug = _slugify_for_subclass(name, max_len=60) or _safe_str(row.get("race_slug"), 60)
            if not name or not slug:
                stats["races"]["errors"] += 1
                continue
            if _existing_race(slug):
                stats["races"]["skipped"] += 1
                continue
            local_content.write_homebrew(
                {
                    "slug": slug, "name": name,
                    "ability_bonuses": row.get("ability_bonuses") if isinstance(row.get("ability_bonuses"), list) else [],
                    "size": _safe_str(row.get("size"), 40),
                    "speed": _safe_int(row.get("speed"), 30),
                    "age": _safe_str(row.get("age"), 1000),
                    "alignment": _safe_str(row.get("alignment"), 1000),
                    "languages": _safe_str(row.get("languages"), 1000),
                    "traits": row.get("traits") if isinstance(row.get("traits"), list) else [],
                    "actions": [],
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="races",
                scope=f"campaign-{campaign_id}",
            )
            stats["races"]["created"] += 1
        except Exception:
            stats["races"]["errors"] += 1

    # ── Monsters ────────────────────────────────────────────────────────
    for row in (body.get("monsters") or [])[:500]:
        if not isinstance(row, dict):
            stats["monsters"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            slug = _slugify_for_subclass(name, max_len=80) or _safe_str(row.get("monster_slug"), 80)
            if not name or not slug:
                stats["monsters"]["errors"] += 1
                continue
            if _existing_monster(slug):
                stats["monsters"]["skipped"] += 1
                continue
            # Coalesce the 4 legacy split lists from the import payload into
            # the unified actions array with category labels.
            import re as _re
            _unified: list[dict] = []
            for _src_key, _cat in (
                ("actions", "action"),
                ("reactions", "reaction"),
                ("special_abilities", "special_ability"),
                ("legendary_actions", "legendary_action"),
            ):
                _list = row.get(_src_key)
                if not isinstance(_list, list):
                    continue
                for _entry in _list:
                    if not isinstance(_entry, dict):
                        continue
                    _nm = (_entry.get("name") or "").strip()
                    _slug_id = _re.sub(r"[^a-z0-9]+", "-", _nm.lower()).strip("-") or f"unnamed-{_cat}"
                    _unified.append({
                        "id": _entry.get("id") or _slug_id,
                        "name": _nm,
                        "desc": _entry.get("desc") or "",
                        "min_level": _entry.get("level") or 1,
                        "category": _cat,
                    })
            local_content.write_homebrew(
                {
                    "slug": slug, "name": name,
                    "size": _safe_str(row.get("size") or "Medium", 40),
                    "type": _safe_str(row.get("type") or "beast", 60).lower(),
                    "alignment": _safe_str(row.get("alignment"), 120),
                    "armor_class": _safe_int(row.get("armor_class"), 10),
                    "armor_desc": _safe_str(row.get("armor_desc"), 120),
                    "hit_points": _safe_int(row.get("hit_points"), 1),
                    "hit_dice": _safe_str(row.get("hit_dice"), 40),
                    "speed": row.get("speed") if isinstance(row.get("speed"), dict) else {"walk": 30},
                    "strength": _safe_int(row.get("strength"), 10),
                    "dexterity": _safe_int(row.get("dexterity"), 10),
                    "constitution": _safe_int(row.get("constitution"), 10),
                    "intelligence": _safe_int(row.get("intelligence"), 10),
                    "wisdom": _safe_int(row.get("wisdom"), 10),
                    "charisma": _safe_int(row.get("charisma"), 10),
                    "damage_vulnerabilities": _safe_str(row.get("damage_vulnerabilities"), 500),
                    "damage_resistances": _safe_str(row.get("damage_resistances"), 500),
                    "damage_immunities": _safe_str(row.get("damage_immunities"), 500),
                    "condition_immunities": _safe_str(row.get("condition_immunities"), 500),
                    "senses": _safe_str(row.get("senses"), 500),
                    "languages": _safe_str(row.get("languages"), 500),
                    "challenge_rating": _safe_str(row.get("challenge_rating") or "0", 20),
                    "actions": _unified,
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="monsters",
                scope=f"campaign-{campaign_id}",
            )
            stats["monsters"]["created"] += 1
        except Exception:
            stats["monsters"]["errors"] += 1

    # ── Backgrounds ─────────────────────────────────────────────────────
    for row in (body.get("backgrounds") or [])[:200]:
        if not isinstance(row, dict):
            stats["backgrounds"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            slug = _slugify_for_subclass(name, max_len=60) or _safe_str(row.get("background_slug"), 60)
            if not name or not slug:
                stats["backgrounds"]["errors"] += 1
                continue
            if _existing_background(slug):
                stats["backgrounds"]["skipped"] += 1
                continue
            local_content.write_homebrew(
                {
                    "slug": slug, "name": name,
                    "description": _safe_str(row.get("description"), 8000),
                    "skill_proficiencies": _safe_str(row.get("skill_proficiencies"), 500),
                    "tool_proficiencies": _safe_str(row.get("tool_proficiencies"), 500),
                    "languages": _safe_str(row.get("languages"), 500),
                    "equipment": _safe_str(row.get("equipment"), 4000),
                    "feature_name": _safe_str(row.get("feature_name"), 160),
                    "feature_desc": _safe_str(row.get("feature_desc"), 4000),
                    "actions": [],
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="backgrounds",
                scope=f"campaign-{campaign_id}",
            )
            stats["backgrounds"]["created"] += 1
        except Exception:
            stats["backgrounds"]["errors"] += 1

    # ── Feats ───────────────────────────────────────────────────────────
    for row in (body.get("feats") or [])[:500]:
        if not isinstance(row, dict):
            stats["feats"]["errors"] += 1
            continue
        try:
            name = _safe_str(row.get("name"), 120)
            slug = _slugify_for_subclass(name, max_len=80) or _safe_str(row.get("feat_slug"), 80)
            if not name or not slug:
                stats["feats"]["errors"] += 1
                continue
            if _existing_feat(slug):
                stats["feats"]["skipped"] += 1
                continue
            # v2.0.0: write directly to the homebrew file volume.
            local_content.write_homebrew(
                {
                    "slug": slug, "name": name,
                    "prerequisite": _safe_str(row.get("prerequisite"), 500),
                    "desc": _safe_str(row.get("desc"), 8000),
                    "actions": [],
                    "system": "dnd5e",
                    "scope": f"campaign-{campaign_id}",
                    "source": "homebrew",
                    "owner": user.id,
                },
                type="feats",
                scope=f"campaign-{campaign_id}",
            )
            stats["feats"]["created"] += 1
        except Exception:
            stats["feats"]["errors"] += 1

    db.commit()
    totals = {
        "created": sum(s["created"] for s in stats.values()),
        "skipped": sum(s["skipped"] for s in stats.values()),
        "errors":  sum(s["errors"]  for s in stats.values()),
    }
    return {"ok": True, "stats": stats, "totals": totals}


@router.post("/campaign/{campaign_id}/members/{membership_id}/set_gm")
def set_member_gm(
    campaign_id: int,
    membership_id: int,
    is_gm: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Promote/demote a campaign member to/from co-GM. Any GM (primary,
    co-GM, or admin) of this campaign may toggle the flag."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    membership = (
        db.query(CampaignMembership)
        .filter(
            CampaignMembership.id == membership_id,
            CampaignMembership.campaign_id == campaign_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(404, "Member not found")
    membership.is_gm = bool(is_gm)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings", status_code=303)


@router.post("/campaign/{campaign_id}/session/start")
async def start_session(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM (or admin) opens the tabletop to players. Idempotent: re-Starting
    an already-active session is a no-op except it refreshes started_at.

    Audio auto-start: when ``campaign.auto_play_playlist_id`` is set, the
    configured playlist begins playing the moment the session starts.
    ``auto_play_mode == 'order'`` plays the first track; ``'shuffle'``
    picks a random track. Any audio already playing is replaced. The
    auto-play side-effect tolerates errors (missing playlist, no tracks)
    silently — a broken auto-play config shouldn't block session start.
    """
    from datetime import datetime as _dt
    import random as _random
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    campaign.session_active = True
    campaign.session_started_at = _dt.utcnow()
    db.commit()
    await hub.broadcast(campaign_id, {"type": "session_started", "data": {}})

    # Auto-start audio if configured.
    if campaign.auto_play_playlist_id:
        from .audio_routes import _start_track_for_campaign
        playlist = (
            db.query(Playlist)
            .filter(
                Playlist.id == campaign.auto_play_playlist_id,
                Playlist.campaign_id == campaign_id,
            )
            .first()
        )
        if playlist and playlist.tracks:
            tracks = list(playlist.tracks)   # ordered by position
            if (campaign.auto_play_mode or "order").lower() == "shuffle":
                track = _random.choice(tracks)
            else:
                track = tracks[0]
            try:
                await _start_track_for_campaign(
                    db, campaign, track,
                    source="auto_start",
                    prev_reason="session_end",
                    user_id=user.id,
                )
            except Exception as exc:
                log.warning("Auto-play failed for campaign %s: %s", campaign_id, exc)

    # Auto-load the configured default encounter, if any. Same
    # tolerate-failures pattern as audio above — a broken default
    # encounter config shouldn't block session start. ``start_audio``
    # is False here because we just kicked off audio above (if
    # configured) via the campaign's auto-play setting; letting the
    # encounter clobber that would be surprising.
    if campaign.default_encounter_id:
        default_enc = (
            db.query(Encounter)
            .filter(
                Encounter.id == campaign.default_encounter_id,
                Encounter.campaign_id == campaign_id,
            )
            .first()
        )
        if default_enc:
            try:
                await _perform_encounter_load(
                    db, campaign, default_enc,
                    start_audio=False,
                    user_id=user.id,
                )
            except HTTPException as exc:
                log.warning(
                    "Default encounter %s skipped on session start for campaign %s: %s",
                    default_enc.id, campaign_id, exc.detail,
                )
            except Exception as exc:
                log.warning(
                    "Default encounter %s failed on session start for campaign %s: %s",
                    default_enc.id, campaign_id, exc,
                )

    return RedirectResponse(f"/campaign/{campaign_id}", status_code=303)


@router.post("/campaign/{campaign_id}/session/end")
async def end_session(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM (or admin) closes the tabletop. Players in the tabletop will be
    bounced back to the lobby; new players hitting the URL get the
    waiting page until the GM Starts again.

    Audio auto-stop: any audio still playing is stopped for everyone via
    the same path as the manual ``/audio/stop`` button.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    campaign.session_active = False
    db.commit()
    await hub.broadcast(campaign_id, {"type": "session_ended", "data": {}})

    # Stop any audio that's still playing. Idempotent — safe when nothing
    # is currently playing. ``reason='session_end'`` labels the in-flight
    # AudioPlayEvent (if any) so the history shows why the play ended.
    if campaign.now_playing_track_id is not None:
        from .audio_routes import _stop_audio_for_campaign
        try:
            await _stop_audio_for_campaign(db, campaign, reason="session_end")
        except Exception as exc:
            log.warning("Auto-stop audio failed for campaign %s: %s", campaign_id, exc)

    return RedirectResponse("/", status_code=303)


@router.get("/campaign/{campaign_id}/rolls", response_class=HTMLResponse)
def rolls_popout(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(404, "Not found")
    rolls = (
        db.query(DiceRoll)
        .filter(DiceRoll.campaign_id == campaign.id)
        .order_by(DiceRoll.created_at.desc())
        .limit(500)
        .all()
    )
    visible = [r for r in rolls if _filter_roll_for_user(r, user, campaign, db)]
    user_color_map, user_portrait_map, user_char_name_map = _build_user_maps(db, campaign)
    return templates.TemplateResponse(
        "rolls_popout.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "rolls": visible,
            "is_gm": _user_is_gm(user, campaign, db),
            "user_color_map": user_color_map,
            "user_portrait_map": user_portrait_map,
            "user_char_name_map": user_char_name_map,
        },
    )


# ----------- API: tokens -----------

@router.post("/api/campaign/{campaign_id}/token/{token_id}/move")
async def move_token(
    campaign_id: int,
    token_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    body = await request.json()
    x = float(body.get("x", 0))
    y = float(body.get("y", 0))
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token or token.map.campaign_id != campaign_id:
        raise HTTPException(404, "Token not found")
    if not _user_can_move_token(db, user, token, campaign):
        raise HTTPException(403, "You can't move that token")

    # v2.6.2: Phase 5 movement tracker. Capture the prior position
    # before the mutation so the broadcast can carry both endpoints +
    # the computed distance in feet. The action-economy chip strip on
    # the init tracker adds ``distance_ft`` to the combatant's
    # ``economy.movement`` running total each time the matching token
    # moves. ``character_id`` is included so the client can join the
    # broadcast to the right combatant without a second lookup.
    from_x = float(token.x or 0)
    from_y = float(token.y or 0)
    grid_size_px = int(token.map.grid_size_px or 0)
    # v2.49.73 — distance math moved to ``_distance_ft_between_points``
    # so the ruler / range-check call sites use the same primitive.
    # Chebyshev (RAW 5-5-5 diagonals) on square; Euclidean on hex /
    # no-grid; 5 ft per cell. Grid type enum normalised by the ORM
    # (SQUARE / HEX_FLAT / HEX_POINTY / NONE all map here).
    grid_type = (token.map.grid_type.value if token.map.grid_type else "square").lower()
    distance_ft = _distance_ft_between_points(
        grid_size_px, grid_type, from_x, from_y, x, y,
    )

    token.x = x
    token.y = y
    db.commit()
    await hub.broadcast(
        campaign_id,
        {"type": "token_move", "data": {
            "id": token.id,
            "x": x, "y": y,
            "from_x": from_x, "from_y": from_y,
            "distance_ft": distance_ft,
            "character_id": token.character_id,
            "token_template_id": token.token_template_id,
        }},
    )

    # v2.8.0: strict-mode movement audit. When the campaign has
    # strict_action_economy on AND this drag pushes the combatant past
    # their walking speed for the FIRST time this turn (transition from
    # pre <= speed_walk to post > speed_walk), broadcast a feature_used
    # audit entry to the roll log. We can't snap the token back — the
    # drag IS the GM's authoritative input — but the audit makes the
    # violation visible to everyone at the table.
    if campaign.strict_action_economy and distance_ft > 0:
        state = hub.get_battle(campaign_id) or {}
        combatant = None
        for c in state.get("combatants") or []:
            if c.get("source_token_id") == token.id:
                combatant = c
                break
            if token.character_id and c.get("char_id") == token.character_id:
                combatant = c
                break
        if combatant:
            economy = combatant.get("economy") or {}
            prev_movement = float(economy.get("movement") or 0)
            speed_walk = float(combatant.get("speed_walk") or 30)
            post_total = prev_movement + distance_ft
            if (prev_movement <= speed_walk + 0.001) and (post_total > speed_walk + 0.001):
                # First-transition fire only. Subsequent drags past the cap
                # don't re-fire (avoids spam on a multi-drag movement).
                # If the GM clicks the chip to reset movement to 0 mid-turn
                # and the player drags past again, the audit fires anew —
                # which matches the intent (a fresh overrun is a fresh
                # violation, even after a refund).
                name = combatant.get("name") or "Combatant"
                membership = (
                    db.query(CampaignMembership)
                    .filter(CampaignMembership.campaign_id == campaign_id,
                            CampaignMembership.user_id == user.id)
                    .first()
                )
                player_color = (
                    membership.color if membership and membership.color
                    else (campaign.gm_color if user.id == campaign.gm_user_id else None)
                )
                await hub.broadcast(campaign_id, {
                    "type": "feature_used",
                    "data": {
                        "character_id": combatant.get("char_id"),
                        "character_name": name,
                        "user_color": player_color,
                        "feature_name": "⚠ Movement overrun",
                        "feature_desc": f"{name} moved {round(post_total, 1)}/{int(speed_walk)} ft this turn (strict action economy).",
                        "source": "movement-overrun",
                        "remaining": 0,
                        "max": 0,
                        "over_budget": True,
                        "over_budget_slot": "",
                    },
                })

    return {"ok": True, "distance_ft": distance_ft}


@router.get("/api/campaign/{campaign_id}/tokens")
def list_tokens(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return the campaign's tokens on its active map. Shipped in
    v2.12.1 primarily for the test harness's /move tests (which need
    token IDs + positions to assert on distance_ft), but useful as a
    general-purpose JSON-friendly token endpoint too.

    Shape per entry: ``{id, label, x, y, size, color, image_url,
    character_id, token_template_id, controller_user_id, is_hidden}``.
    Hidden tokens are filtered out for non-GM viewers — same rule the
    tabletop page already applies at render time.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    # The "active map" lives on the campaign, not as a flag on the map
    # itself — pattern mirrors how the tabletop page render fetches it.
    map_row = (
        db.query(Map).filter(Map.id == campaign.active_map_id).first()
        if campaign.active_map_id else None
    )
    if not map_row:
        return {"tokens": []}
    is_gm = _user_is_gm(user, campaign, db)
    tokens = db.query(Token).filter(Token.map_id == map_row.id).all()
    out = []
    for t in tokens:
        if t.is_hidden and not is_gm:
            continue
        out.append({
            "id": t.id,
            "label": t.label,
            "x": float(t.x or 0),
            "y": float(t.y or 0),
            "size": t.size,
            "color": t.color,
            "image_url": t.image_url,
            "character_id": t.character_id,
            "token_template_id": t.token_template_id,
            "controller_user_id": t.controller_user_id,
            "is_hidden": bool(t.is_hidden),
        })
    return {"tokens": out, "map_id": map_row.id,
            "grid_size_px": map_row.grid_size_px,
            "grid_type": map_row.grid_type.value if map_row.grid_type else "square"}


@router.post("/api/campaign/{campaign_id}/tokens")
async def create_token(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    body = await request.json()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    if not campaign.active_map_id:
        raise HTTPException(400, "Campaign has no active map")

    tmpl_id = body.get("token_template_id")
    tmpl = None
    if tmpl_id:
        tmpl = db.query(TokenTemplate).filter(
            TokenTemplate.id == tmpl_id, TokenTemplate.campaign_id == campaign_id
        ).first()

    label = str(body.get("label") or (tmpl.name if tmpl else "Token"))[:120]
    image_url = body.get("image_url") or (tmpl.image_url if tmpl else None)

    t = Token(
        map_id=campaign.active_map_id,
        character_id=body.get("character_id"),
        token_template_id=tmpl_id if tmpl else None,
        label=label,
        color=str(body.get("color", "#cc3333"))[:20],
        image_url=image_url,
        x=float(body.get("x", 100)),
        y=float(body.get("y", 100)),
        size=int(body.get("size", 1)),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    await hub.broadcast(
        campaign_id,
        {"type": "token_add", "data": _token_dict(t)},
    )
    return _token_dict(t)


@router.post("/api/campaign/{campaign_id}/character/{char_id}/place-token")
async def place_character_token(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Place a character's token on the active map. GM-only as of v0.63.0
    (previously the character's owner could also call this; players no
    longer add/remove tokens themselves).

    Optional body: ``{x: float, y: float}`` to override the default
    placement coordinates. The browser client passes the world-space
    center of the GM's current viewport so tokens land where the GM is
    looking instead of at the (often offscreen) geometric center of the
    map. Non-browser callers can omit the body and get the legacy
    map-center default.

    If the character already has a token on this map it is replaced.
    Token image is pre-filled from the character's portrait if one is set."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    if not campaign.active_map_id:
        raise HTTPException(400, "No active map")
    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")

    # Remove any existing token for this character on the active map first.
    existing = (
        db.query(Token)
        .filter(Token.character_id == char_id, Token.map_id == campaign.active_map_id)
        .first()
    )
    if existing:
        old_id = existing.id
        db.delete(existing)
        db.flush()
        await hub.broadcast(campaign_id, {"type": "token_delete", "data": {"id": old_id}})

    active_map = db.query(Map).filter(Map.id == campaign.active_map_id).first()
    gsize = active_map.grid_size_px if active_map else 70
    # Legacy fallback: geometric center of the map, snapped to the grid.
    fallback_x = round((active_map.width_px / 2) / gsize) * gsize if active_map else 0
    fallback_y = round((active_map.height_px / 2) / gsize) * gsize if active_map else 0
    # If the client sent viewport-center coords, snap them to the grid
    # so the new token sits cleanly on a cell instead of mid-tile.
    if isinstance(body, dict) and "x" in body and "y" in body:
        try:
            cx = round(float(body["x"]) / gsize) * gsize
            cy = round(float(body["y"]) / gsize) * gsize
        except (TypeError, ValueError):
            cx, cy = fallback_x, fallback_y
    else:
        cx, cy = fallback_x, fallback_y

    t = Token(
        map_id=campaign.active_map_id,
        character_id=char.id,
        controller_user_id=char.owner_user_id,
        label=char.name[:120],
        color="#cc3333",
        image_url=char.portrait_url,
        x=float(cx),
        y=float(cy),
        size=1,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    await hub.broadcast(campaign_id, {"type": "token_add", "data": _token_dict(t)})
    return _token_dict(t)


@router.delete("/api/campaign/{campaign_id}/character/{char_id}/token")
async def remove_character_token(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Remove a character's token from the active map. GM-only as of
    v0.63.0 (previously the character's owner could also call this)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not campaign.active_map_id:
        return {"ok": True, "removed": False}
    token = (
        db.query(Token)
        .filter(Token.character_id == char_id, Token.map_id == campaign.active_map_id)
        .first()
    )
    if not token:
        return {"ok": True, "removed": False}
    token_id = token.id
    db.delete(token)
    db.commit()
    await hub.broadcast(campaign_id, {"type": "token_delete", "data": {"id": token_id}})
    return {"ok": True, "removed": True}


@router.delete("/api/campaign/{campaign_id}/tokens/{token_id}")
async def delete_token(
    campaign_id: int,
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token or token.map.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    db.delete(token)
    db.commit()
    await hub.broadcast(campaign_id, {"type": "token_delete", "data": {"id": token_id}})
    return {"ok": True}


def _encounter_to_dict(e: Encounter) -> dict:
    """Encounter projection used by the GM listing UIs.

    Includes the lightweight summary fields the Battle drawer + campaign
    settings need to render rows, plus the preview fields Phase 5 added
    (``token_names``, ``map_name``) for the on-hover tooltip and the
    ``tags`` array for client-side filtering / chip rendering."""
    payload = e.payload or {}
    tokens = payload.get("tokens") or []
    initiative = payload.get("initiative") or []
    # Cap names returned to keep payload bounded; the tooltip elides
    # the rest as " + N more". Order matches the saved token order so
    # the GM sees combatants in roughly the same sequence they're
    # rendered on the canvas.
    token_names = [
        (t.get("label_override") or "Token") for t in tokens[:25]
    ]
    extra = max(0, len(tokens) - len(token_names))
    return {
        "id": e.id,
        "name": e.name,
        "description": e.description or "",
        "map_id": e.map_id,
        "map_name": e.map.name if e.map else None,
        "map_image_url": e.map.image_url if e.map else None,
        "map_thumbnail_url": e.map.thumbnail_url if e.map else None,
        "auto_play_playlist_id": e.auto_play_playlist_id,
        "auto_play_mode": e.auto_play_mode or "order",
        "auto_play_playlist_name": (
            e.auto_play_playlist.name if e.auto_play_playlist else None
        ),
        "tags": list(e.tags or []),
        "folder": e.folder or "",
        "stop_audio_on_load": bool(e.stop_audio_on_load),
        "use_spawn_points": bool(e.use_spawn_points),
        "spawn_points": dict(e.spawn_points or {}),
        "token_count": len(tokens),
        "token_names": token_names,
        "token_names_extra": extra,
        "initiative_count": len(initiative),
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _parse_tags(value) -> list[str]:
    """Coerce a tags input (list or comma-separated string) into a
    deduplicated list of short trimmed strings. Used by both the create
    and PATCH endpoints so the wire format is flexible."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [t.strip() for t in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [str(t).strip() for t in value]
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for t in items:
        if not t:
            continue
        t = t[:40]
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= 20:
            break
    return out


@router.get("/api/campaign/{campaign_id}/encounters")
def list_encounters(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """List the GM's saved encounters for a campaign. GM-only.

    Each row carries an ``is_current`` flag so the Battle drawer can pin
    the currently-running encounter (the one most recently loaded via
    ``_perform_encounter_load``) to the top of its panel summary.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    rows = (
        db.query(Encounter)
        .filter(Encounter.campaign_id == campaign_id)
        .order_by(Encounter.created_at.desc())
        .all()
    )
    current_id = campaign.current_encounter_id
    out = []
    for e in rows:
        d = _encounter_to_dict(e)
        d["is_current"] = (current_id is not None and e.id == current_id)
        out.append(d)
    return out


def _snapshot_encounter_payload(db: Session, campaign: Campaign) -> dict:
    """Capture the current token state + battle hub state into the JSON
    payload shape used by the encounters table.

    Both GM-owned and player-controlled tokens are captured (the latter
    flagged by a non-null ``controller_user_id`` + ``character_id``).
    The load flow applies Option B for player tokens — restore only if
    the character has no token on the target map yet — so capturing
    them is non-destructive to ongoing player positions.
    """
    tokens_out = []
    if campaign.active_map_id:
        rows = (
            db.query(Token)
            .filter(Token.map_id == campaign.active_map_id)
            .all()
        )
        for t in rows:
            tokens_out.append({
                "template_id": t.token_template_id,
                "character_id": t.character_id,
                "controller_user_id": t.controller_user_id,
                "label_override": t.label or "",
                "color_override": t.color or "",
                "image_url": t.image_url,
                "size": int(t.size or 1),
                "x": float(t.x or 0),
                "y": float(t.y or 0),
                "is_hidden": bool(t.is_hidden),
            })
    # Battle hub state is opaque to the server — JS PUTs the canonical
    # shape via /api/campaign/.../battle. We snapshot it whole so a load
    # restores combatant order, current turn, round number, HP, …
    # exactly as the GM had it.
    battle_state = hub.get_battle(campaign.id) or {}
    return {
        "tokens": tokens_out,
        "battle_state": battle_state,
    }


@router.post("/api/campaign/{campaign_id}/encounters")
async def create_encounter(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Save an encounter. GM-only.

    Two creation modes:

    1. **Snapshot the current state** (the original Phase 2 path).
       Body: ``{name, description?, tags?, map_id?, auto_play_playlist_id?,
       auto_play_mode?}``. When ``payload`` is absent we capture the
       active map's tokens + the in-memory battle hub state. ``map_id``
       and ``auto_play_playlist_id`` override the active-map / now-playing
       defaults so the GM can bind the snapshot to a different map or
       playlist than the live ones (useful when staging tokens on map A
       but the encounter belongs to map B).

    2. **Build from blank** — Phase-6 prep workflow.
       Body: ``{name, payload: {tokens: [], battle_state: {}}, map_id,
       auto_play_playlist_id?, auto_play_mode?, description?, tags?}``.
       When ``payload`` is present we trust it as-is, don't touch the
       live tabletop state, and create a draft the GM can fill in later
       with 💾 Update once they're staged on the bound map.
    """
    body = await request.json()
    name = str(body.get("name") or "").strip()[:160]
    if not name:
        raise HTTPException(400, "Encounter name required")
    description = str(body.get("description") or "").strip()

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    if "payload" in body:
        # Build-from-blank path. Accept the caller's payload verbatim so
        # they can start with an empty bundle and fill in later.
        raw_payload = body.get("payload") or {}
        if not isinstance(raw_payload, dict):
            raise HTTPException(400, "payload must be an object")
        payload = {
            "tokens": list(raw_payload.get("tokens") or []),
            "battle_state": raw_payload.get("battle_state") or {},
        }
    else:
        payload = _snapshot_encounter_payload(db, campaign)

    # Map binding: explicit > campaign.active_map_id. Validate that any
    # explicit map_id belongs to this campaign so the GM can't bind to
    # another campaign's map.
    if "map_id" in body and body["map_id"] is not None:
        try:
            map_id_val = int(body["map_id"])
        except (TypeError, ValueError):
            raise HTTPException(400, "Invalid map_id")
        m = db.query(Map).filter(Map.id == map_id_val, Map.campaign_id == campaign_id).first()
        if not m:
            raise HTTPException(404, "Map not found in this campaign")
        bound_map_id = m.id
    else:
        bound_map_id = campaign.active_map_id

    # Playlist binding: explicit > inferred from currently-playing track.
    auto_play_mode = str(body.get("auto_play_mode") or campaign.auto_play_mode or "order")
    if auto_play_mode not in ("order", "shuffle", "song"):
        auto_play_mode = "order"
    auto_play_playlist_id: Optional[int] = None
    if "auto_play_playlist_id" in body:
        v = body["auto_play_playlist_id"]
        if v is not None and v != "":
            try:
                pl_id = int(v)
            except (TypeError, ValueError):
                raise HTTPException(400, "Invalid auto_play_playlist_id")
            pl = (
                db.query(Playlist)
                .filter(Playlist.id == pl_id, Playlist.campaign_id == campaign_id)
                .first()
            )
            if not pl:
                raise HTTPException(404, "Playlist not found in this campaign")
            auto_play_playlist_id = pl.id
    elif campaign.now_playing_track_id:
        track = (
            db.query(PlaylistTrack)
            .filter(PlaylistTrack.id == campaign.now_playing_track_id)
            .first()
        )
        if track:
            auto_play_playlist_id = track.playlist_id

    use_spawn_points = bool(body.get("use_spawn_points", False))
    raw_spawns = body.get("spawn_points")
    spawn_points: dict = {}
    if isinstance(raw_spawns, dict):
        for key, coord in raw_spawns.items():
            if not isinstance(coord, dict):
                continue
            try:
                spawn_points[str(int(key))] = {
                    "x": float(coord.get("x", 0)),
                    "y": float(coord.get("y", 0)),
                }
            except (TypeError, ValueError):
                continue

    enc = Encounter(
        campaign_id=campaign_id,
        name=name,
        description=description,
        map_id=bound_map_id,
        auto_play_playlist_id=auto_play_playlist_id,
        auto_play_mode=auto_play_mode,
        auto_play_track_id=int(body["auto_play_track_id"]) if body.get("auto_play_track_id") else None,
        payload=payload,
        tags=_parse_tags(body.get("tags")),
        use_spawn_points=use_spawn_points,
        spawn_points=spawn_points,
        folder=str(body.get("folder") or "").strip()[:120],
        stop_audio_on_load=bool(body.get("stop_audio_on_load", False)),
    )
    db.add(enc)
    db.commit()
    db.refresh(enc)
    return _encounter_to_dict(enc)


@router.patch("/api/campaign/{campaign_id}/encounters/{encounter_id}")
async def update_encounter_meta(
    campaign_id: int,
    encounter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Rename / re-describe a saved encounter. GM-only.

    Body: ``{name?, description?}``. Either or both may be provided;
    omitted fields are left untouched. Empty/whitespace ``name`` is
    rejected — the library row would render as a blank line otherwise.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    enc = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not enc:
        raise HTTPException(404, "Encounter not found")

    if "name" in body:
        new_name = str(body.get("name") or "").strip()[:160]
        if not new_name:
            raise HTTPException(400, "Encounter name cannot be empty")
        enc.name = new_name
    if "description" in body:
        enc.description = str(body.get("description") or "").strip()
    if "tags" in body:
        enc.tags = _parse_tags(body.get("tags"))
    if "map_id" in body:
        v = body.get("map_id")
        if v is None or v == "":
            enc.map_id = None
        else:
            try:
                map_id_val = int(v)
            except (TypeError, ValueError):
                raise HTTPException(400, "Invalid map_id")
            m = (
                db.query(Map)
                .filter(Map.id == map_id_val, Map.campaign_id == campaign_id)
                .first()
            )
            if not m:
                raise HTTPException(404, "Map not found in this campaign")
            enc.map_id = m.id
    if "auto_play_playlist_id" in body:
        v = body.get("auto_play_playlist_id")
        if v is None or v == "":
            enc.auto_play_playlist_id = None
        else:
            try:
                pl_id = int(v)
            except (TypeError, ValueError):
                raise HTTPException(400, "Invalid auto_play_playlist_id")
            pl = (
                db.query(Playlist)
                .filter(Playlist.id == pl_id, Playlist.campaign_id == campaign_id)
                .first()
            )
            if not pl:
                raise HTTPException(404, "Playlist not found in this campaign")
            enc.auto_play_playlist_id = pl.id
    if "auto_play_mode" in body:
        mode = str(body.get("auto_play_mode") or "order")
        if mode not in ("order", "shuffle"):
            raise HTTPException(400, "auto_play_mode must be 'order' or 'shuffle'")
        enc.auto_play_mode = mode
    if "folder" in body:
        enc.folder = str(body.get("folder") or "").strip()[:120]
    if "stop_audio_on_load" in body:
        enc.stop_audio_on_load = bool(body.get("stop_audio_on_load"))
    if "use_spawn_points" in body:
        enc.use_spawn_points = bool(body.get("use_spawn_points"))
    if "spawn_points" in body:
        # Wholesale replace — the per-character endpoint below is the
        # incremental path; this branch is for PATCH callers that want
        # to set the whole dict at once (e.g. duplicating from another
        # encounter, or clearing all spawns with ``{}``).
        raw_spawns = body.get("spawn_points") or {}
        if not isinstance(raw_spawns, dict):
            raise HTTPException(400, "spawn_points must be an object")
        normalised: dict = {}
        for key, coord in raw_spawns.items():
            if not isinstance(coord, dict):
                continue
            try:
                normalised[str(int(key))] = {
                    "x": float(coord.get("x", 0)),
                    "y": float(coord.get("y", 0)),
                }
            except (TypeError, ValueError):
                continue
        enc.spawn_points = normalised

    db.commit()
    db.refresh(enc)
    return _encounter_to_dict(enc)


@router.post("/api/campaign/{campaign_id}/encounters/{encounter_id}/spawn")
async def set_encounter_spawn(
    campaign_id: int,
    encounter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Set or clear a single character's spawn point on an encounter.
    GM-only. Body: ``{character_id: int, x?: float, y?: float}``. When
    ``x`` and ``y`` are both numeric the spawn is recorded; otherwise
    the entry for ``character_id`` is cleared. Used by the click-to-set
    flow in the encounter row's edit form."""
    body = await request.json()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    enc = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not enc:
        raise HTTPException(404, "Encounter not found")
    try:
        char_id = int(body.get("character_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "character_id required")
    char = (
        db.query(Character)
        .filter(Character.id == char_id, Character.campaign_id == campaign_id)
        .first()
    )
    if not char:
        raise HTTPException(404, "Character not found in this campaign")

    spawns = dict(enc.spawn_points or {})
    key = str(char_id)
    x_raw = body.get("x")
    y_raw = body.get("y")
    if x_raw is None or y_raw is None:
        spawns.pop(key, None)
        out = None
    else:
        try:
            spawns[key] = {"x": float(x_raw), "y": float(y_raw)}
        except (TypeError, ValueError):
            raise HTTPException(400, "Invalid x or y")
        out = spawns[key]
    enc.spawn_points = spawns
    db.commit()
    db.refresh(enc)
    return _encounter_to_dict(enc)


@router.post("/api/campaign/{campaign_id}/encounters/{encounter_id}/duplicate")
def duplicate_encounter(
    campaign_id: int,
    encounter_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Copy a saved encounter into a new row with a " (copy)" suffix on
    the name. GM-only. Useful for spinning up variants of the same setup
    ("Goblin Ambush — Dawn", "Goblin Ambush — Night") without recapturing
    the whole bundle each time.

    The copy is a fresh row with new ``created_at`` / ``updated_at``;
    everything else (payload, map, playlist, tags, notes) is duplicated."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    src = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not src:
        raise HTTPException(404, "Encounter not found")

    new_name = (src.name + " (copy)")[:160]
    copy = Encounter(
        campaign_id=campaign_id,
        name=new_name,
        description=src.description or "",
        map_id=src.map_id,
        auto_play_playlist_id=src.auto_play_playlist_id,
        auto_play_mode=src.auto_play_mode or "order",
        payload=src.payload or {},
        tags=list(src.tags or []),
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _encounter_to_dict(copy)


@router.post("/api/campaign/{campaign_id}/encounters/{encounter_id}/update")
async def overwrite_encounter(
    campaign_id: int,
    encounter_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Re-snapshot the current campaign state into an existing encounter.
    GM-only.

    Use this when a saved encounter ("Goblin Ambush") evolves between
    sessions and the GM wants to overwrite the bundle in place instead
    of creating a new sibling row. Name + description + ``created_at``
    are kept; ``payload`` + ``map_id`` + ``auto_play_playlist_id`` +
    ``auto_play_mode`` are replaced from the current state. ``updated_at``
    auto-bumps via the ``onupdate=func.now()`` clause on the column.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    enc = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not enc:
        raise HTTPException(404, "Encounter not found")

    enc.payload = _snapshot_encounter_payload(db, campaign)
    enc.map_id = campaign.active_map_id
    enc.auto_play_mode = campaign.auto_play_mode or "order"
    enc.auto_play_playlist_id = None
    if campaign.now_playing_track_id:
        track = (
            db.query(PlaylistTrack)
            .filter(PlaylistTrack.id == campaign.now_playing_track_id)
            .first()
        )
        if track:
            enc.auto_play_playlist_id = track.playlist_id

    db.commit()
    db.refresh(enc)
    return _encounter_to_dict(enc)


@router.post("/api/campaign/{campaign_id}/encounters/{encounter_id}/delete")
def delete_encounter(
    campaign_id: int,
    encounter_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Delete a saved encounter. GM-only. No broadcast — the library is
    a GM-only view, so other clients don't care."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    enc = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not enc:
        raise HTTPException(404, "Encounter not found")
    db.delete(enc)
    db.commit()
    return {"ok": True}


async def _perform_encounter_load(
    db: Session,
    campaign: Campaign,
    enc: Encounter,
    *,
    start_audio: bool,
    user_id: Optional[int],
) -> dict:
    """Two-pass strict load shared by the explicit Load endpoint and the
    session-start auto-load hook. See ``load_encounter`` for the
    semantics — this helper is the implementation; the route is a thin
    wrapper that parses the body + permission-checks. Raises
    ``HTTPException`` for caller-fixable errors so the route can let
    them propagate verbatim.
    """
    payload = enc.payload or {}
    target_map_id = enc.map_id or campaign.active_map_id
    if not target_map_id:
        raise HTTPException(400, "Encounter has no map and campaign has no active map")
    map_switched = bool(enc.map_id and enc.map_id != campaign.active_map_id)
    campaign_id = campaign.id

    # ── Pass 1: clear every token on the target map ──
    # Strict semantics (v0.73.0): only the tokens described by the
    # encounter exist after the load. Players whose characters aren't
    # in the saved bundle (no snapshot entry AND no spawn point) have
    # their tokens removed too.
    all_tokens = (
        db.query(Token)
        .filter(Token.map_id == target_map_id)
        .all()
    )
    deleted_ids = [t.id for t in all_tokens]
    for t in all_tokens:
        db.delete(t)
    db.flush()

    # ── Pass 2a: switch the active map if the encounter binds a new one ──
    if map_switched:
        campaign.active_map_id = enc.map_id
        db.flush()

    # Mark this encounter as the campaign's currently-running one so the
    # Battle drawer can keep it pinned in the UI even while collapsed.
    campaign.current_encounter_id = enc.id
    db.flush()

    # ── Pass 2b: create the new tokens from the payload ──
    # When ``use_spawn_points`` is true the encounter's spawn_points
    # dict drives player placement and the snapshot's player entries
    # are ignored. Otherwise we fall back to the snapshot's player
    # tokens. GM tokens (no ``character_id``) always come from payload.
    warnings: list[str] = []
    created_tokens: list[Token] = []
    use_spawns = bool(enc.use_spawn_points)
    spawn_map: dict = dict(enc.spawn_points or {}) if use_spawns else {}

    for tok_def in (payload.get("tokens") or []):
        char_id = tok_def.get("character_id")
        if char_id:
            # Player token. Skip the snapshot entry when spawn-points
            # mode is on — the spawn pass below covers player placement.
            if use_spawns:
                continue
            char = db.query(Character).filter(Character.id == char_id).first()
            if not char:
                warnings.append(
                    f"Player character #{char_id} no longer exists; skipping their saved token."
                )
                continue
            new_token = Token(
                map_id=target_map_id,
                character_id=char.id,
                controller_user_id=char.owner_user_id,
                label=char.name[:120],
                color=(tok_def.get("color_override") or char.color or "#cc3333")[:20],
                image_url=tok_def.get("image_url") or char.portrait_url,
                x=float(tok_def.get("x", 100)),
                y=float(tok_def.get("y", 100)),
                size=int(tok_def.get("size", 1) or 1),
                is_hidden=bool(tok_def.get("is_hidden", False)),
            )
            db.add(new_token)
            created_tokens.append(new_token)
            continue
        tmpl_id = tok_def.get("template_id")
        tmpl = None
        if tmpl_id:
            tmpl = (
                db.query(TokenTemplate)
                .filter(
                    TokenTemplate.id == tmpl_id,
                    TokenTemplate.campaign_id == campaign_id,
                )
                .first()
            )
            if not tmpl:
                warnings.append(
                    f"Token template #{tmpl_id} missing; falling back to manual token."
                )
        label = (tok_def.get("label_override") or (tmpl.name if tmpl else "Token"))[:120]
        color = (tok_def.get("color_override") or "#cc3333")[:20]
        image_url = tok_def.get("image_url") or (tmpl.image_url if tmpl else None)
        new_token = Token(
            map_id=target_map_id,
            token_template_id=tmpl.id if tmpl else None,
            label=label,
            color=color,
            image_url=image_url,
            x=float(tok_def.get("x", 100)),
            y=float(tok_def.get("y", 100)),
            size=int(tok_def.get("size", 1) or 1),
            is_hidden=bool(tok_def.get("is_hidden", False)),
        )
        db.add(new_token)
        created_tokens.append(new_token)

    # ── Pass 2c: place player tokens from spawn_points (when enabled) ──
    if use_spawns:
        gsize = 1
        target_map_obj = db.query(Map).filter(Map.id == target_map_id).first()
        if target_map_obj and target_map_obj.grid_size_px:
            gsize = max(1, int(target_map_obj.grid_size_px))
        for key, coord in spawn_map.items():
            if not isinstance(coord, dict):
                continue
            try:
                char_id = int(key)
                x = round(float(coord["x"]) / gsize) * gsize
                y = round(float(coord["y"]) / gsize) * gsize
            except (TypeError, ValueError, KeyError):
                continue
            char = (
                db.query(Character)
                .filter(Character.id == char_id, Character.campaign_id == campaign_id)
                .first()
            )
            if not char:
                warnings.append(
                    f"Spawn-point character #{char_id} no longer exists; skipping."
                )
                continue
            new_token = Token(
                map_id=target_map_id,
                character_id=char.id,
                controller_user_id=char.owner_user_id,
                label=char.name[:120],
                color=char.color or "#cc3333",
                image_url=char.portrait_url,
                x=float(x),
                y=float(y),
                size=1,
            )
            db.add(new_token)
            created_tokens.append(new_token)

    db.commit()
    for t in created_tokens:
        db.refresh(t)

    # ── Pass 3: restore battle hub state ──
    battle_state = payload.get("battle_state") or {}
    if battle_state:
        hub.set_battle(campaign_id, battle_state)

    # ── Broadcasts ──
    if map_switched:
        # Map change is a big enough scene shift that we ask clients to
        # reload; their existing canvas wasn't built to swap maps in
        # place. The reload picks up the new active_map + tokens via the
        # standard SSR path and reconnects the WS, which seeds the new
        # battle state from the hub.
        await hub.broadcast(
            campaign_id,
            {"type": "map_change", "data": {"map_id": target_map_id}},
        )
    else:
        # Same map — surgical token_delete + token_add broadcasts keep
        # every player's canvas in sync without a reload.
        for tid in deleted_ids:
            await hub.broadcast(
                campaign_id, {"type": "token_delete", "data": {"id": tid}}
            )
        for t in created_tokens:
            await hub.broadcast(
                campaign_id, {"type": "token_add", "data": _token_dict(t)}
            )
        if battle_state:
            await hub.broadcast(
                campaign_id, {"type": "battle_update", "data": battle_state}
            )

    # ── Audio behaviour on load ──
    # Three-way decision when ``start_audio`` is true:
    #   1. ``auto_play_playlist_id`` set → start that playlist (takes
    #      precedence over the stop-on-load flag).
    #   2. No playlist + ``stop_audio_on_load`` true → stop current
    #      audio so the GM gets a clean silent transition.
    #   3. No playlist + ``stop_audio_on_load`` false (default) →
    #      leave the currently-playing audio alone (continue).
    # Each branch tolerates missing/broken state with a non-fatal
    # warning rather than failing the whole load.
    if start_audio and enc.auto_play_playlist_id:
        playlist = (
            db.query(Playlist)
            .filter(
                Playlist.id == enc.auto_play_playlist_id,
                Playlist.campaign_id == campaign_id,
            )
            .first()
        )
        if not playlist:
            warnings.append("Saved playlist missing; audio skipped.")
        else:
            tracks = list(playlist.tracks)
            track: Optional[PlaylistTrack] = None
            mode = enc.auto_play_mode or "order"
            if tracks:
                if mode == "shuffle":
                    import random
                    track = random.choice(tracks)
                elif mode == "song" and enc.auto_play_track_id:
                    track = next((t for t in tracks if t.id == enc.auto_play_track_id), tracks[0])
                else:
                    track = tracks[0]
            if track:
                # Deferred import: audio_routes imports from realtime + models,
                # so importing it lazily keeps this module's load-time graph
                # free of audio-side dependencies.
                from .audio_routes import _start_track_for_campaign
                await _start_track_for_campaign(
                    db, campaign, track,
                    source="auto_start",
                    prev_reason="skipped",
                    user_id=user_id,
                )
    elif start_audio and enc.stop_audio_on_load and campaign.now_playing_track_id:
        # No playlist for this encounter AND the GM asked for silence;
        # stop whatever's currently playing. ``_stop_audio_for_campaign``
        # is idempotent so the now_playing_track_id guard is just to
        # skip the no-op call when nothing is playing.
        from .audio_routes import _stop_audio_for_campaign
        await _stop_audio_for_campaign(db, campaign, reason="skipped")

    return {
        "ok": True,
        "map_switched": map_switched,
        "tokens_created": len(created_tokens),
        "tokens_deleted": len(deleted_ids),
        "warnings": warnings,
        # v2.4.6: return the canonical post-load battle state so the GM
        # client (which is authoritative and ignores the
        # ``battle_update`` WS broadcast) can hydrate its local
        # init-tracker view to match what the server just put into the
        # hub. Without this, the GM keeps a stale localStorage battle
        # after Load — exactly the bug a v2.3.44-portrait demo user
        # hit when they'd populated the tracker pre-v2.4.3.
        "battle_state": battle_state or None,
    }


@router.post("/api/campaign/{campaign_id}/encounters/{encounter_id}/load")
async def load_encounter(
    campaign_id: int,
    encounter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Two-pass strict load. GM-only.

    Pass 1 — Delete **every** token on the **target map** (the
    encounter's bound map, or the campaign's active map if the encounter
    has no map). Strict semantics: after a load, only tokens described
    by the encounter remain. Player tokens for characters not in the
    encounter are removed.

    Pass 2 — If the encounter binds a different map, switch
    ``campaign.active_map_id`` and broadcast ``map_change`` so connected
    clients reload onto the new map. Then recreate tokens from the
    encounter:

    * **GM tokens** from the saved payload.
    * **Player tokens**:
      - When ``use_spawn_points`` is true, one token per entry in
        ``encounter.spawn_points`` (placed at the spawn coord). The
        saved snapshot's player tokens are ignored.
      - Otherwise, the saved snapshot's player tokens are used
        verbatim (positions captured at save time).

    Body (optional): ``{start_audio: bool = true}``. When true and the
    encounter has an ``auto_play_playlist_id``, audio auto-starts via the
    existing ``_start_track_for_campaign`` helper.

    Implementation lives in ``_perform_encounter_load`` so the
    session-start auto-load hook can call the same code path.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    start_audio = bool(body.get("start_audio", True))

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    enc = (
        db.query(Encounter)
        .filter(Encounter.id == encounter_id, Encounter.campaign_id == campaign_id)
        .first()
    )
    if not enc:
        raise HTTPException(404, "Encounter not found")
    return await _perform_encounter_load(
        db, campaign, enc, start_audio=start_audio, user_id=user.id,
    )


@router.patch("/api/campaign/{campaign_id}/token/{token_id}")
async def update_token(
    campaign_id: int,
    token_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    body = await request.json()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token or token.map.campaign_id != campaign_id:
        raise HTTPException(404, "Token not found")
    if "label" in body:
        token.label = str(body["label"])[:120]
    if "is_hidden" in body:
        token.is_hidden = bool(body["is_hidden"])
    if "controller_user_id" in body:
        val = body["controller_user_id"]
        token.controller_user_id = int(val) if val else None
    if "color" in body:
        token.color = str(body["color"])[:20]
    db.commit()
    await hub.broadcast(campaign_id, {"type": "token_update", "data": _token_dict(token)})
    return _token_dict(token)


@router.post("/api/campaign/{campaign_id}/token/{token_id}/image")
async def upload_token_image(
    campaign_id: int,
    token_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    import uuid
    from pathlib import Path as _Path

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token or token.map.campaign_id != campaign_id:
        raise HTTPException(404, "Token not found")
    allowed = {"image/png", "image/jpeg", "image/webp", "image/gif"}
    if image.content_type not in allowed:
        raise HTTPException(400, "Unsupported image type")
    data = await image.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image too large (>5 MB)")
    token_dir = _Path(__file__).resolve().parent.parent / "static" / "uploads" / "tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    ext = _Path(image.filename or "img.png").suffix.lower() or ".png"
    fname = f"{uuid.uuid4().hex}{ext}"
    (token_dir / fname).write_bytes(data)
    token.image_url = f"/static/uploads/tokens/{fname}"
    db.commit()
    await hub.broadcast(campaign_id, {"type": "token_update", "data": _token_dict(token)})
    return {"image_url": token.image_url}


def _token_dict(t: Token) -> dict:
    return {
        "id": t.id,
        "label": t.label,
        "color": t.color,
        "x": t.x,
        "y": t.y,
        "size": t.size,
        "character_id": t.character_id,
        "controller_user_id": t.controller_user_id,
        "image_url": t.image_url,
        "is_hidden": t.is_hidden,
        "token_template_id": t.token_template_id,
    }


# ----------- API: dice -----------

@router.post("/api/campaign/{campaign_id}/roll")
async def roll_dice(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    body = await request.json()
    expr = str(body.get("expression", "")).strip()
    visibility_str = str(body.get("visibility", "public")).lower()
    note = str(body.get("note", ""))[:200]
    skip_roll_state = bool(body.get("skip_roll_state"))
    try:
        visibility = Visibility(visibility_str)
    except ValueError:
        raise HTTPException(400, "Invalid visibility")
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    # Look up the rolling user's character so we can (a) apply roll_state
    # to single-d20 expressions and (b) attribute the roll in the log.
    # Explicit ``character_id`` in the body wins (lets a GM roll for a
    # specific char); falls back to the user's first character.
    _char = None
    explicit_char_id = body.get("character_id")
    if explicit_char_id:
        try:
            _char = (
                db.query(Character)
                .filter(Character.id == int(explicit_char_id),
                        Character.campaign_id == campaign_id)
                .first()
            )
        except (TypeError, ValueError):
            _char = None
    if _char is None:
        _char = (
            db.query(Character)
            .filter(Character.campaign_id == campaign_id, Character.owner_user_id == user.id)
            .first()
        )

    # v2.2.0: apply roll_state to single-d20 expressions before rolling.
    # Manual 2d20kh1 / 2d20kl1 are detected but left unchanged; the note
    # is annotated either way so the log distinguishes auto vs manual.
    roll_state_applied = ""
    if not skip_roll_state:
        rs = (_char.sheet or {}).get("roll_state") if _char else None
        expr, roll_state_applied = _apply_roll_state(expr, rs)
    note_suffix = _roll_state_note_suffix(roll_state_applied)
    if note_suffix:
        note = (note + note_suffix)[:200]

    try:
        result = dice_mod.roll(expr)
    except dice_mod.DiceParseError as e:
        raise HTTPException(400, str(e))
    rec = DiceRoll(
        campaign_id=campaign_id,
        user_id=user.id,
        expression=expr,
        breakdown=result.breakdown,
        total=result.total,
        visibility=visibility,
        note=note,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    _char_name   = _char.name        if _char else None
    _portrait_url = _char.portrait_url if _char else None
    _membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == user.id)
        .first()
    )
    _player_color = (
        _membership.color if _membership and _membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    _user_color = (_char.color if _char and _char.color else _player_color)
    # v2.12.4: server-side visibility filter. Previously this broadcast
    # went to every connected WS client regardless of ``visibility``;
    # ``roll_toast.js`` + the roll-log handler filtered client-side,
    # which kept the raw data accessible to anyone watching the WS in
    # devtools. The hub now accepts a recipient_filter callback that
    # consults each connection's identity (user_id + is_gm) and skips
    # the send for filtered-out recipients. ``public`` keeps the old
    # broadcast-to-all (filter is None); ``gm_only`` allows only GMs;
    # ``gm_and_roller`` allows GMs and the rolling user.
    _roller_id = user.id
    if rec.visibility == Visibility.GM_ONLY:
        _filter = lambda ident: bool(ident.get("is_gm"))
    elif rec.visibility == Visibility.GM_AND_ROLLER:
        _filter = lambda ident: bool(ident.get("is_gm")) or ident.get("user_id") == _roller_id
    else:
        _filter = None
    await hub.broadcast(
        campaign_id,
        {
            "type": "roll",
            "data": {
                "id": rec.id,
                "user_id": user.id,
                "user_name": user.display_name,
                "char_name": _char_name,
                "user_color": _user_color,
                "portrait_url": _portrait_url,
                "expression": rec.expression,
                "breakdown": rec.breakdown,
                "total": rec.total,
                "visibility": rec.visibility.value,
                "note": rec.note,
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
                "roll_state_applied": roll_state_applied or None,
            },
        },
        recipient_filter=_filter,
    )
    return {"ok": True, "total": rec.total, "breakdown": rec.breakdown,
            "roll_state_applied": roll_state_applied or None}


@router.post("/api/campaign/{campaign_id}/member_color")
async def set_member_color(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM sets a roll-log highlight color for any campaign member (including themselves)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    body = await request.json()
    target_user_id = int(body.get("user_id", 0))
    color = str(body.get("color", "")).strip()[:20] or None  # None clears the color
    if target_user_id == campaign.gm_user_id:
        campaign.gm_color = color
    else:
        membership = (
            db.query(CampaignMembership)
            .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == target_user_id)
            .first()
        )
        if not membership:
            raise HTTPException(404, "Member not found")
        membership.color = color
    db.commit()
    await hub.broadcast(
        campaign_id,
        {"type": "member_color_update", "data": {"user_id": target_user_id, "color": color}},
    )
    return {"ok": True}


@router.post("/api/campaign/{campaign_id}/character/{char_id}/color")
async def set_character_color(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM sets a roll-log color on a character. Overrides the player's assigned color."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    body = await request.json()
    color = str(body.get("color", "")).strip()[:20] or None
    char.color = color
    db.commit()
    # Broadcast so live tabletop updates immediately
    await hub.broadcast(
        campaign_id,
        {
            "type": "character_color_update",
            "data": {
                "char_id": char.id,
                "owner_user_id": char.owner_user_id,
                "color": color,
            },
        },
    )
    return {"ok": True}


_VALID_RING_STYLES = {"solid", "dashed", "double", "glow", "spiked"}


@router.post("/api/campaign/{campaign_id}/character/{char_id}/ring-style")
async def set_character_ring_style(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Player or GM sets the token ring color and style for a character."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if char.owner_user_id != user.id and not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "Not your character")
    body = await request.json()
    raw_color = str(body.get("color", "")).strip()[:20]
    if raw_color:
        char.color = raw_color
    ring_style = str(body.get("ring_style", "solid")).strip()
    if ring_style not in _VALID_RING_STYLES:
        ring_style = "solid"
    char.ring_style = ring_style
    db.commit()
    await hub.broadcast(
        campaign_id,
        {
            "type": "character_ring_update",
            "data": {
                "char_id": char.id,
                "color": char.color,
                "ring_style": ring_style,
            },
        },
    )
    return {"ok": True}


# ----------- API: roll requests -----------

def _resolve_stat_modifier(sheet: dict, template: str, stat_key: str) -> tuple[int, str]:
    """Return (modifier, display_label) by looking up *stat_key* in a D&D 5e sheet.

    stat_key forms:
      "str_save" … "cha_save"   → saving throw (adds prof if proficient)
      "str_check" … "cha_check" → raw ability modifier
      Exact skill name           → skill modifier (adds prof/expertise)
      Anything else / non-5e    → (0, "")
    """
    if not stat_key or template != "dnd5e":
        return 0, ""

    abilities = sheet.get("abilities") or {}
    saving_throws = sheet.get("saving_throws") or {}
    skills = sheet.get("skills") or {}
    prof = int(sheet.get("proficiency_bonus") or 2)

    _AB_LONG = {"str": "STR", "dex": "DEX", "con": "CON",
                "int": "INT", "wis": "WIS", "cha": "CHA"}

    def ab_mod(ab: str) -> int:
        return (int(abilities.get(ab, 10)) - 10) // 2

    # Saving throw: "str_save", "con_save", …
    for short, long in _AB_LONG.items():
        if stat_key == f"{short}_save":
            mod = ab_mod(long)
            if saving_throws.get(long, False):
                mod += prof
            label = f"{long} Save{'(prof)' if saving_throws.get(long) else ''}"
            return mod, label
        if stat_key in (f"{short}_check", f"{short}_mod"):
            return ab_mod(long), f"{long} Check"

    # Skill: exact name e.g. "Perception", "Stealth"
    skill_data = skills.get(stat_key)
    if skill_data:
        ab = skill_data.get("ability", "STR")
        mod = ab_mod(ab)
        if skill_data.get("expertise", False):
            mod += prof * 2
            suffix = " (exp)"
        elif skill_data.get("proficient", False):
            mod += prof
            suffix = " (prof)"
        else:
            suffix = ""
        return mod, f"{stat_key}{suffix}"

    return 0, ""


@router.post("/api/campaign/{campaign_id}/roll_request")
async def create_roll_request(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM posts a roll-request card to the roll log so players can respond."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    body = await request.json()
    label = str(body.get("label", "")).strip()[:200]
    if not label:
        raise HTTPException(400, "label is required")

    stat_key = str(body.get("stat_key", "") or "").strip()[:60] or None
    base_expr = str(body.get("base_expression", "1d20") or "1d20").strip()[:60] or "1d20"
    dc_raw = body.get("dc")
    dc = int(dc_raw) if dc_raw is not None and str(dc_raw).strip() else None
    visibility_str = str(body.get("visibility", "public")).lower()
    try:
        visibility = Visibility(visibility_str)
    except ValueError:
        visibility = Visibility.PUBLIC

    # Target-player filter. Empty list (default) keeps the legacy
    # broadcast-to-everyone behaviour. Non-empty list narrows the prompt to
    # specific campaign members; the validated names are echoed back in the
    # WS payload so the GM's roll-log card can show who was targeted.
    raw_targets = body.get("target_user_ids") or []
    if not isinstance(raw_targets, list):
        raw_targets = []
    target_ids: list[int] = []
    for t in raw_targets[:32]:
        try:
            target_ids.append(int(t))
        except (TypeError, ValueError):
            continue
    target_user_ids: list[int] = []
    target_user_names: list[str] = []
    if target_ids:
        member_rows = (
            db.query(User)
            .join(CampaignMembership, CampaignMembership.user_id == User.id)
            .filter(
                CampaignMembership.campaign_id == campaign_id,
                User.id.in_(target_ids),
            )
            .all()
        )
        by_id = {u.id: u for u in member_rows}
        for tid in target_ids:
            u = by_id.get(tid)
            if u and u.id not in target_user_ids:
                target_user_ids.append(u.id)
                target_user_names.append(u.display_name)

    req = RollRequest(
        campaign_id=campaign_id,
        created_by_user_id=user.id,
        label=label,
        base_expression=base_expr,
        stat_key=stat_key,
        dc=dc,
        visibility=visibility,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    await hub.broadcast(
        campaign_id,
        {
            "type": "roll_request",
            "data": {
                "id": req.id,
                "label": req.label,
                "stat_key": req.stat_key,
                "base_expression": req.base_expression,
                "dc": req.dc,
                "visibility": req.visibility.value,
                "created_by_name": user.display_name,
                "created_by_user_id": user.id,
                "target_user_ids": target_user_ids,
                "target_user_names": target_user_names,
            },
        },
    )
    return {"ok": True, "id": req.id}


@router.post("/api/campaign/{campaign_id}/roll_request/{req_id}/respond")
async def respond_roll_request(
    campaign_id: int,
    req_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Player (or GM acting as a token) clicks the Roll button in a roll-request card.

    The server resolves the stat modifier from the chosen character sheet, builds
    the final expression, rolls it, and broadcasts a standard ``roll`` WS message.
    A DC pass/fail note is appended when the request has a DC set.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    roll_req = db.query(RollRequest).filter(
        RollRequest.id == req_id,
        RollRequest.campaign_id == campaign_id,
    ).first()
    if not roll_req:
        raise HTTPException(404, "Roll request not found")

    body = await request.json()
    char_id = body.get("character_id")

    # Load character — GMs may roll for any campaign character; players only theirs
    char: Optional[Character] = None
    if char_id:
        char = db.query(Character).filter(
            Character.id == char_id,
            Character.campaign_id == campaign_id,
        ).first()
        if not char:
            raise HTTPException(404, "Character not found")
        is_gm = _user_is_gm(user, campaign, db)
        if not is_gm and char.owner_user_id != user.id:
            raise HTTPException(403, "Not your character")

    # Resolve stat modifier from sheet
    mod, stat_label = (0, "")
    if char and roll_req.stat_key:
        mod, stat_label = _resolve_stat_modifier(
            char.sheet or {}, char.template, roll_req.stat_key
        )

    # Build final expression
    base = roll_req.base_expression or "1d20"
    if mod > 0:
        final_expr = f"{base}+{mod}"
    elif mod < 0:
        final_expr = f"{base}{mod}"
    else:
        final_expr = base

    # Roll
    try:
        result = dice_mod.roll(final_expr)
    except dice_mod.DiceParseError as e:
        raise HTTPException(400, f"Bad expression '{final_expr}': {e}")

    # Build a descriptive note
    char_name = char.name if char else None
    note_parts = [f"→ {roll_req.label}"]
    if stat_label:
        note_parts.append(stat_label)
    if roll_req.dc is not None:
        outcome = "✓ Pass" if result.total >= roll_req.dc else "✗ Fail"
        note_parts.append(f"DC {roll_req.dc} — {outcome}")
    note = " | ".join(note_parts)[:200]

    rec = DiceRoll(
        campaign_id=campaign_id,
        user_id=user.id,
        expression=final_expr,
        breakdown=result.breakdown,
        total=result.total,
        visibility=roll_req.visibility,
        note=note,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    # Resolve portrait / color for broadcast
    _membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == user.id)
        .first()
    )
    _player_color = (
        _membership.color if _membership and _membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    _portrait_url = char.portrait_url if char else None
    _user_color = (char.color if char and char.color else _player_color)

    await hub.broadcast(
        campaign_id,
        {
            "type": "roll",
            "data": {
                "id": rec.id,
                "user_id": user.id,
                "user_name": user.display_name,
                "char_name": char_name,
                "user_color": _user_color,
                "portrait_url": _portrait_url,
                "expression": rec.expression,
                "breakdown": rec.breakdown,
                "total": rec.total,
                "visibility": rec.visibility.value,
                "note": rec.note,
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
            },
        },
    )

    # v2.37.0 Phase T.3d: if this roll-request response corresponds to
    # a save-or-suck spell prompted at a PC (Hold Person at Krieger,
    # etc.) and the PC FAILED the save, install the matching condition
    # buff on them via ``_install_buff`` (PC-keyed sibling of the NPC
    # path used in T.3c). Context lives in ``_save_request_context``
    # keyed by req_id; populated by /cast_spell at prompt-creation time.
    auto_buff_installed = ""
    _purge_save_request_context()
    ctx = _save_request_context.get(roll_req.id)
    if ctx and ctx.get("campaign_id") == campaign_id and roll_req.dc is not None:
        if result.total < roll_req.dc:
            cond = _SPELL_CONDITION_MAP.get(ctx.get("spell_slug") or "")
            tgt_char_id = ctx.get("target_character_id")
            if cond and tgt_char_id:
                buff = {
                    "key": cond["key"],
                    "name": cond["name"],
                    "icon": cond.get("icon", "💫"),
                    "source_char_id": int(ctx.get("caster_char_id") or 0),
                    "source_char_name": ctx.get("caster_char_name") or "",
                    "source_spell": ctx.get("spell_name") or "",
                    "duration_rounds": int(cond.get("duration_rounds", 10)),
                    "duration_max": int(cond.get("duration_rounds", 10)),
                    "concentration": bool(cond.get("concentration")),
                    "effects": list(cond.get("effects", [])),
                }
                installed = await _install_buff(
                    campaign_id, int(tgt_char_id), buff,
                )
                if installed:
                    auto_buff_installed = cond["name"]
                    _mirror_buffs_to_sheet(
                        db, int(tgt_char_id),
                        _get_buffs(campaign_id, int(tgt_char_id)),
                    )
                    # v2.38.0 Phase T.3e: install caster-side
                    # concentration so the cleanup helper can drop
                    # this PC's condition when the caster loses
                    # concentration. Mirror of the T.3c NPC path.
                    if bool(cond.get("concentration")):
                        caster_id = int(ctx.get("caster_char_id") or 0)
                        if caster_id:
                            caster_buff = {
                                "key": f"concentration-{ctx.get('spell_slug') or 'spell'}",
                                "name": f"Concentrating: {ctx.get('spell_name') or 'Spell'}",
                                "icon": "🌀",
                                "source_char_id": caster_id,
                                "source_char_name": ctx.get("caster_char_name") or "",
                                "source_spell": ctx.get("spell_name") or "",
                                "duration_rounds": int(cond.get("duration_rounds", 10)),
                                "duration_max": int(cond.get("duration_rounds", 10)),
                                "concentration": True,
                                "effects": [
                                    f"Concentrating on {ctx.get('spell_name') or 'spell'}",
                                ],
                            }
                            await _install_buff(campaign_id, caster_id, caster_buff)
        # v2.47.0 Phase T.5d: AoE PC saves apply save-for-half damage
        # and broadcast a per-target update so the cast card's pill
        # row repaints. The condition-buff path above stays scoped to
        # the existing single-target case; AoE PC saves don't install
        # buffs (the only buff-installing save spells today are non-
        # AoE save-or-suck — Hold Person, Suggestion, etc.).
        if ctx and ctx.get("is_aoe") and roll_req.dc is not None:
            _passed = result.total >= roll_req.dc
            _dmg_applied = 0
            _dmg_type = ctx.get("damage_type") or ""
            _cast_id = ctx.get("cast_id") or ""
            _combatant_id = ctx.get("combatant_id") or ""
            if ctx.get("auto_apply_damage") and ctx.get("damage_expr"):
                try:
                    _dr = dice_mod.roll(ctx["damage_expr"])
                    _dmg_rolled = max(0, int(_dr.total))
                except dice_mod.DiceParseError:
                    _dmg_rolled = 0
                if _dmg_rolled > 0:
                    proposed = _dmg_rolled if not _passed else _dmg_rolled // 2
                    if proposed > 0:
                        # Wrap the PC's character row in a combatant
                        # dict so ``_apply_damage_to_combatant`` can
                        # route through the PC HP / death-save path.
                        _pc_combatant = {
                            "char_id": int(ctx.get("target_character_id") or 0),
                            "id": _combatant_id,
                            "name": ctx.get("target_name") or "",
                        }
                        _dr_result = await _apply_damage_to_combatant(
                            db, campaign_id, _pc_combatant, proposed,
                            damage_type=_dmg_type,
                            attack_id=_cast_id,
                        )
                        _dmg_applied = int(_dr_result.get("applied") or 0)
            await hub.broadcast(campaign_id, {
                "type": "spell_cast_target_updated",
                "data": {
                    "cast_id": _cast_id,
                    "combatant_id": _combatant_id,
                    "target_name": ctx.get("target_name") or "",
                    "rolled": int(result.total),
                    "passed": _passed,
                    "damage_applied": _dmg_applied,
                    "damage_type": _dmg_type,
                },
            })
            _save_request_context.pop(roll_req.id, None)

    return {
        "ok": True,
        "total": rec.total,
        "breakdown": rec.breakdown,
        "auto_buff_installed": auto_buff_installed,
    }


# ----------- API: cast spell -----------

@router.post("/api/campaign/{campaign_id}/cast_spell")
async def cast_spell(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Cast a spell from a character's sheet.

    Decrements the matching spell slot (when ``spell_level >= 1``) and
    broadcasts a ``spell_cast`` WebSocket message that other clients render
    as an interactive card in the roll log. Cantrips (level 0) skip the
    slot check entirely.

    Returns 409 ``{"error": "no_slot", ...}`` when the slot is empty so the
    caller can show a non-blocking toast instead of a roll-log entry.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    spell_index = int(body.get("spell_index", -1))
    if char_id <= 0 or spell_index < 0:
        raise HTTPException(400, "character_id and spell_index are required")

    # v2.22.0 Phase T.1: optional target descriptors. ``target_combatant_id``
    # is the stable combatant.id from the hub battle state (preferred);
    # ``target_character_id`` + ``target_name`` are fallbacks for callers
    # that don't have a combatant id handy. Each selector is resolved
    # below into a (combatant_id, display_name) pair via the existing
    # ``_resolve_target_combatant`` helper.
    target_combatant_id_in = (body.get("target_combatant_id") or "").strip() or None
    target_character_id_in = body.get("target_character_id")
    target_character_id_in = int(target_character_id_in) if target_character_id_in else None
    target_name_in = (body.get("target_name") or "").strip() or None
    # v2.44.0 Phase T.5: AoE multi-target list. When the client's
    # sphere/circle picker places an AoE template, every token inside
    # the circle is sent as a list of combatant ids. The first id
    # drives the existing single-target resolution path (so save +
    # damage + buff + condition install all run unchanged for target
    # #0); the remaining ids are looped server-side at the end of the
    # save-resolution block, appending one entry per target to a new
    # ``auto_save_targets`` payload field. NPC-only for v1 — PC AoE
    # saves need per-target roll_request orchestration (filed for
    # T.5d follow-up).
    target_combatant_ids_in = body.get("target_combatant_ids") or []
    if not isinstance(target_combatant_ids_in, list):
        target_combatant_ids_in = []
    target_combatant_ids_in = [str(x).strip() for x in target_combatant_ids_in if str(x).strip()]
    # When the AoE list is set + the single-target field is empty,
    # promote the first AoE id into the single-target slot so the
    # existing resolution path uses it as target #0.
    if target_combatant_ids_in and not target_combatant_id_in:
        target_combatant_id_in = target_combatant_ids_in[0]

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id,
        Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)
    spells = list(sheet.get("spells") or [])
    if spell_index >= len(spells):
        raise HTTPException(404, "Spell not found")
    spell = dict(spells[spell_index] or {})
    # v2.26.0 Phase T.4: enrich the sheet's bare spell entry with the
    # canonical SRD record (resolved by ``_slug``). Demo seeds carry
    # ``{name, level, _slug, casting_time}`` only; the auto-heal /
    # auto-damage paths need the full ``actions[]`` array and
    # ``healing`` / ``damage`` fields from the SRD JSON. Sheet-side
    # overrides (homebrew, partial customization) take precedence.
    spell_slug = (spell.get("_slug") or "").strip().lower()
    if spell_slug:
        _hit = local_content.resolve(spell_slug, type="spells", campaign_id=campaign_id)
        if _hit:
            srd_rec, _ = _hit
            for k, v in srd_rec.items():
                spell.setdefault(k, v)
    spell_level = int(spell.get("level") or 0)

    # Allow upcasting via an optional slot_level override; default to spell.level
    slot_level_raw = body.get("slot_level")
    slot_level = int(slot_level_raw) if slot_level_raw is not None and str(slot_level_raw).strip() else spell_level
    if slot_level < spell_level:
        slot_level = spell_level

    # Determine which class's slots to deduct from.  Body may pass
    # ``class_slug`` explicitly; otherwise fall back to the spell's tagged
    # class, then the primary (highest-level) class on the sheet.
    body_slug = (body.get("class_slug") or "").strip().lower()
    spell_class_slug = (spell.get("class") or "").strip().lower()
    primary_slug = _class_slug(sheet.get("class") or "")
    cslug = body_slug or spell_class_slug or primary_slug

    # v2.49.75 — Phase 2C range-enforcement gate. Fires BEFORE slot
    # consumption so a blocked cast doesn't burn a slot (same contract
    # as the no_slot gate below). Skipped for AoE multi-target casts —
    # the picker UI (and the /place_aoe path) is the range gate for
    # those (see docs/plans/ruler-and-range.md Phase 2 "When NOT to
    # enforce"). user_is_gm + strict re-computed here AND below at
    # the over-budget gate; cheap idempotent lookups.
    if not target_combatant_ids_in:
        _user_is_gm_for_range = _user_is_gm(user, campaign, db)
        _strict_for_range = bool(campaign.strict_action_economy)
        _override_range = bool(body.get("override_range"))
        _range_err = _check_cast_range(
            db, campaign, char,
            spell.get("range") or "",
            spell.get("name") or "",
            target_combatant_id_in, target_character_id_in, target_name_in,
            override_range=_override_range,
            user_is_gm=_user_is_gm_for_range,
            strict=_strict_for_range,
        )
        if _range_err:
            return JSONResponse(status_code=409, content=_range_err)

    # Decrement slot when this is a leveled spell (cantrips are free)
    updated_slot = None
    if spell_level >= 1:
        all_slots = dict(sheet.get("spell_slots") or {})
        per_class = dict(all_slots.get(cslug) or {})
        slot_key = str(slot_level)
        slot = dict(per_class.get(slot_key) or {"total": 0, "used": 0})
        total = int(slot.get("total") or 0)
        used = int(slot.get("used") or 0)
        if total <= 0 or used >= total:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "no_slot",
                    "level": slot_level,
                    "class_slug": cslug,
                    "spell_name": spell.get("name", ""),
                },
            )
        slot["used"] = used + 1
        per_class[slot_key] = slot
        all_slots[cslug] = per_class
        sheet["spell_slots"] = all_slots
        char.sheet = sheet
        db.commit()
        updated_slot = {
            "class_slug": cslug,
            "level": slot_level,
            "total": total,
            "used": slot["used"],
        }

    # v2.6.1: Phase 4 over-budget gate. Compute the economy slot up-front
    # so we can decide whether this cast needs a Layer B confirm modal
    # before any state mutation. Players hitting an already-used slot get
    # 409 ``over_budget`` and the client opens the modal; on Confirm the
    # client retries with ``override: true`` and we proceed. GM clicks
    # skip the gate entirely (rules-authority bypass per the plan) but
    # still flow through the same ``over_budget`` tag in the broadcast so
    # the Layer C audit badge fires.
    # v2.8.0: when ``campaign.strict_action_economy`` is on, the
    # override flag is ignored for non-GM users — the 409 carries
    # ``strict: true`` so the modal hides its Confirm button.
    slot_for_economy = _casting_time_to_economy(spell.get("casting_time", ""))
    was_used = _is_slot_used(campaign_id, char.id, slot_for_economy)
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    override = bool(body.get("override")) and not strict
    if was_used and not user_is_gm and not override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": slot_for_economy,
            "char_name": char.name,
            "source": "spell",
            "label": spell.get("name", ""),
            "strict": strict,
        })

    # Resolve caster display info (same shape as roll broadcasts)
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    cast_id = uuid.uuid4().hex[:12]

    # v2.22.0 Phase T.1: resolve the target descriptors (any combination
    # of combatant_id / character_id / name) into a canonical pair for
    # the broadcast. ``_resolve_target_combatant`` returns
    # ``(combatant_id, display_name)``; when the target isn't currently
    # in init the combatant_id falls back to None and the broadcast
    # carries name-only. T.2 will use ``target_combatant_id`` to read
    # the target's AC; for now the chat card just shows the target
    # name in the cast line.
    target_combatant_id, target_name_resolved = await _resolve_target_combatant(
        campaign_id,
        target_character_id=target_character_id_in,
        target_name=target_name_in,
    )
    # When the caller passed an explicit combatant_id, prefer it over
    # whatever the char_id / name resolver returned (the caller knows
    # which init slot they meant — supports double-targeting the same
    # name with different tokens).
    if target_combatant_id_in:
        target_combatant_id = target_combatant_id_in

    payload = {
        "id": cast_id,
        "caster_user_id": user.id,
        "caster_user_name": user.display_name,
        "caster_user_color": caster_color,
        "caster_portrait_url": char.portrait_url,
        "caster_char_id": char.id,
        "caster_char_name": char.name,
        "spell_index": spell_index,
        "spell_name": spell.get("name", ""),
        "spell_level": spell_level,
        "slot_level": slot_level,
        "over_budget": was_used,
        "over_budget_slot": slot_for_economy if was_used else "",
        "spell_school": spell.get("school", ""),
        "spell_casting_time": spell.get("casting_time", ""),
        "spell_range": spell.get("range", ""),
        "spell_duration": spell.get("duration", ""),
        "spell_components": spell.get("components", ""),
        "spell_concentration": bool(spell.get("concentration")),
        "spell_ritual": bool(spell.get("ritual")),
        "spell_damage": spell.get("damage", ""),
        "spell_save_ability": spell.get("save_ability", ""),
        # v2.26.0 Phase T.4: heal dice may live at the top of the spell
        # record (legacy demo-seed shape) OR on ``actions[*].healing``
        # (canonical action_schema shape for SRD content). Take the
        # first non-empty source so the auto-heal path fires for both.
        "spell_healing": spell.get("healing") or next(
            (a.get("healing") for a in (spell.get("actions") or []) if a.get("healing")),
            "",
        ),
        "spell_aoe_targets": max(1, int(spell.get("aoe_targets") or 1)),
        "spell_attack_roll": bool(spell.get("attack_roll")),
        "spell_desc": spell.get("desc", "") or spell.get("description", ""),
        # Structured action descriptors — present when the spell came from the
        # file-based local_content tier with an `actions: list[Action]` array.
        # Client's renderActionButtons consumes this directly; if empty the
        # client synthesizes a single Action from the legacy fields above.
        "actions": spell.get("actions") or [],
        # v2.22.0 Phase T.1: target descriptors. ``target_combatant_id`` is
        # the stable combatant.id when the target is in init; None
        # otherwise. ``target_character_id`` carries through when the
        # target is a PC. ``target_name`` always set when any target was
        # provided. The chat card uses these to render "Lyra casts
        # Fireball at Vex"; T.2 will use combatant_id to look up AC for
        # auto-hit determination.
        "target_combatant_id": target_combatant_id or "",
        "target_character_id": target_character_id_in,
        "target_name": target_name_resolved or target_name_in or "",
    }

    # v2.48.0 Phase T.5e: caster-gated AoE placement. When the spell
    # carries an AoE area block AND no targets were supplied (neither
    # target_combatant_id nor target_combatant_ids), the cast lands in
    # "pending placement" state: the existing save/attack/damage
    # resolution blocks below all skip naturally because they're
    # gated on a target being present, so the broadcast goes out with
    # a ``pending_aoe_placement: True`` flag that tells the client to
    # render a "📍 Place AoE" button (gated to caster + GM) instead
    # of an empty pill row. The button posts to ``/place_aoe`` with
    # the swept-up target_combatant_ids; that endpoint pulls the
    # spell context from ``_pending_aoe_casts[cast_id]`` to resolve
    # saves + damage.
    _aoe_area_info = _extract_aoe_area(spell)
    _has_aoe_targets = bool(target_combatant_id or target_combatant_ids_in)
    pending_aoe_placement = bool(_aoe_area_info and not _has_aoe_targets)
    payload["pending_aoe_placement"] = pending_aoe_placement
    if _aoe_area_info:
        payload["area_shape"] = _aoe_area_info["shape"]
        payload["area_size_ft"] = _aoe_area_info["size_ft"]
        payload["area_secondary_ft"] = _aoe_area_info["secondary_ft"]
    else:
        payload["area_shape"] = ""
        payload["area_size_ft"] = 0
        payload["area_secondary_ft"] = 0
    # v2.49.78 — Phase 3A client. Surface the spell's parsed range so
    # the AoE picker can render a translucent range ring around the
    # caster's token. Self-range / unknown ranges → 0 (the client
    # skips the ring render when range_ft is 0).
    from ..content.range_parser import max_range_ft, parse_range_ft
    _parsed_range = max_range_ft(parse_range_ft(spell.get("range") or ""))
    payload["range_ft"] = int(_parsed_range) if _parsed_range else 0

    # Register heal claims so /apply_healing can validate and roll server-side
    if payload["spell_healing"]:
        _purge_heal_claims()
        _heal_claims[cast_id] = {
            "dice": payload["spell_healing"],
            "max_targets": payload["spell_aoe_targets"],
            "claimed": set(),        # user_ids who have already claimed
            "campaign_id": campaign_id,
            "expires": _time.time() + 8 * 3600,
            # v2.27.1: store the intended target so the legacy
            # /apply_healing endpoint routes the heal to the right
            # combatant — pre-T.4 it heals the calling user's first
            # owned PC, which is effectively random for a GM who
            # owns all party PCs.
            "target_combatant_id": target_combatant_id or "",
            "target_character_id": target_character_id_in,
            "target_name": target_name_resolved or target_name_in or "",
        }

    # v2.26.0 Phase T.4: auto-apply healing to the targeted combatant.
    # When (a) the spell carries a healing dice expression AND (b) the
    # caster passed a target_combatant_id (set by double-clicking a
    # token), roll the heal server-side + apply HP via
    # ``_apply_heal_to_combatant`` + capture the result for the chat
    # card. The legacy ``_heal_claims`` flow above stays in place for
    # casts WITHOUT a target (the chat-card "Heal me" button still
    # works for opt-in self-claims by allies). When auto-applied here
    # the heal_claim entry is dropped so the chat card doesn't show
    # both the per-target line AND the "claim a heal" button.
    auto_heal_applied = 0
    auto_heal_hp_before = None
    auto_heal_hp_after = None
    auto_heal_revived = False
    auto_heal_target_name = ""
    if (
        payload["spell_healing"]
        and (target_combatant_id or target_character_id_in)
    ):
        try:
            _r = dice_mod.roll(payload["spell_healing"])
            heal_rolled = max(0, int(_r.total))
            heal_breakdown = _r.breakdown
        except dice_mod.DiceParseError:
            heal_rolled = 0
            heal_breakdown = ""
        target_combatant = _lookup_combatant(campaign_id, target_combatant_id)
        # v2.27.2: when the target isn't currently in the init tracker
        # (e.g. the GM hasn't run "From Map" yet, or the targeted PC
        # was removed) but we have a target_character_id from the
        # client's double-click, synthesize a minimal combatant dict
        # so the PC heal path in ``_apply_heal_to_combatant`` still
        # fires. That path only needs ``char_id`` — it queries the
        # Character row directly. Without this fallback, casts like
        # Cure Wounds at a PC whose token isn't in init silently
        # drop into the legacy heal-claim flow.
        if not target_combatant and target_character_id_in:
            target_combatant = {
                "char_id": int(target_character_id_in),
                "id": target_combatant_id or "",
                "name": target_name_resolved or target_name_in or "",
            }
        if target_combatant and heal_rolled > 0:
            heal_result = await _apply_heal_to_combatant(
                db, campaign_id, target_combatant, heal_rolled,
                cast_id=cast_id,
            )
            auto_heal_applied = heal_result["applied"]
            auto_heal_hp_before = heal_result["hp_before"]
            auto_heal_hp_after = heal_result["hp_after"]
            auto_heal_revived = heal_result["revived"]
            auto_heal_target_name = target_combatant.get("name", "")
            # Drop the heal-claim — heal was already applied to the
            # single target. (For AoE heals like Mass Healing Word, T.5
            # will pass multiple target_combatant_ids and we'll loop;
            # the claim path stays for the existing opt-in flow.)
            _heal_claims.pop(cast_id, None)
            # Add structured heal-applied fields to the broadcast.
            payload["auto_heal_rolled"] = heal_rolled
            payload["auto_heal_breakdown"] = heal_breakdown
            payload["auto_heal_applied"] = auto_heal_applied
            payload["auto_heal_target_name"] = auto_heal_target_name
            payload["auto_heal_hp_before"] = auto_heal_hp_before
            payload["auto_heal_hp_after"] = auto_heal_hp_after
            payload["auto_heal_revived"] = auto_heal_revived

    # v2.34.0 Phase T.4b: auto-resolve spell ATTACK rolls (Fire Bolt,
    # Eldritch Blast, Inflict Wounds, Guiding Bolt, Ray of Frost,
    # Scorching Ray, Chill Touch, Vampiric Touch, etc. — every spell
    # with ``attack_roll: true`` on the action). Mirrors T.2's
    # weapon-attack hit determination: spell attack bonus = caster
    # proficiency + spellcasting mod; rolls 1d20+bonus vs target AC;
    # natural 20 = crit (doubles dice), natural 1 = miss. On hit (or
    # crit), rolls damage and applies it via the existing
    # ``_apply_damage_to_combatant`` helper (same campaign.auto_apply
    # _damage gate as weapon attacks + save-for-half). Save spells
    # are skipped here — they use the T.3 save-resolution block
    # below. The cast broadcast carries ``auto_attack_*`` fields so
    # the chat card + toast can show the verdict + damage.
    spell_attack_flag = bool(spell.get("attack_roll")) or any(
        bool(a.get("attack_roll")) for a in (spell.get("actions") or [])
    )
    auto_attack_hit = None
    auto_attack_crit = False
    auto_attack_total = 0
    auto_attack_breakdown = ""
    auto_attack_target_ac = 0
    auto_attack_target_name = ""
    auto_attack_damage_rolled = 0
    auto_attack_damage_applied = 0
    auto_attack_damage_type = ""
    auto_attack_damage_breakdown = ""
    beams: list[dict] = []
    # Save-ability detection has to happen up front so we can gate the
    # attack block — a spell with both flags wouldn't be RAW, but the
    # gate prevents accidental double-rolling.
    _spell_save_ability_check = bool(
        spell.get("save_ability") or any(
            a.get("save_ability") for a in (spell.get("actions") or [])
        )
    )
    if (
        spell_attack_flag
        and not _spell_save_ability_check
        and (target_combatant_id or target_character_id_in)
    ):
        target_combatant = _lookup_combatant(campaign_id, target_combatant_id)
        if not target_combatant and target_character_id_in:
            target_combatant = {
                "char_id": int(target_character_id_in),
                "id": target_combatant_id or "",
                "name": target_name_resolved or target_name_in or "",
            }
        if target_combatant:
            auto_attack_target_name = target_combatant.get("name", "") or target_name_resolved or ""
            # Caster's spell attack bonus.
            caster_sheet_atk = char.sheet or {}
            caster_prof_atk = int(caster_sheet_atk.get("proficiency_bonus") or 2)
            caster_spc_atk = (caster_sheet_atk.get("spellcasting_ability") or "").strip().upper()[:3]
            if caster_spc_atk not in {"STR", "DEX", "CON", "INT", "WIS", "CHA"}:
                caster_spc_atk = "WIS"
            caster_ab_atk = int(
                (caster_sheet_atk.get("abilities") or {}).get(caster_spc_atk, 10)
            )
            spell_atk_bonus = caster_prof_atk + ((caster_ab_atk - 10) // 2)
            auto_attack_target_ac = _read_target_ac(db, campaign_id, target_combatant)
            # Resolve damage dice from the action.
            _dmg_scaling = None
            for a in (spell.get("actions") or []):
                if a.get("damage"):
                    auto_attack_damage_type = a.get("damage_type") or ""
                    _dmg_base = a.get("damage") or ""
                    _dmg_scaling = a.get("damage_scaling") or None
                    break
            else:
                _dmg_base = spell.get("damage") or ""
                auto_attack_damage_type = spell.get("damage_type") or auto_attack_damage_type
            # v2.36.0 Phase T.4c: cantrip scaling — pick the highest
            # tier whose level ≤ caster's total character level. The
            # tier's damage expression overrides the base for damage
            # cantrips (Fire Bolt 1d10 → 2d10 at L5, etc.).
            _caster_level_for_scaling = int(
                (char.sheet or {}).get("level") or 1
            )
            _tier = _pick_damage_tier(_dmg_scaling, _caster_level_for_scaling)
            if _tier and _tier.get("damage"):
                _dmg_base = _tier["damage"]
            # v2.40.0 Phase T.4c-multibeam: when the scaling tier
            # carries ``extra_beams: N``, fire N+1 separate attack
            # rolls against the target (Eldritch Blast 2 beams at L5,
            # 3 at L11, 4 at L17). Each beam independently
            # hits/misses + rolls damage. Damage aggregates and
            # applies once via _apply_damage_to_combatant; per-beam
            # detail surfaces in ``auto_attack_beams`` for richer UI.
            total_beams = 1 + int((_tier or {}).get("extra_beams") or 0)
            beams: list[dict] = []
            agg_damage_rolled = 0
            agg_damage_breakdown_parts: list[str] = []
            any_hit = False
            any_crit = False
            for beam_idx in range(total_beams):
                beam = {
                    "beam": beam_idx + 1,
                    "total": 0,
                    "breakdown": "",
                    "hit": False,
                    "crit": False,
                    "damage_rolled": 0,
                    "damage_breakdown": "",
                }
                atk_expr = f"1d20{spell_atk_bonus:+d}"
                try:
                    _ar = dice_mod.roll(atk_expr)
                    beam["total"] = int(_ar.total)
                    beam["breakdown"] = _ar.breakdown
                except dice_mod.DiceParseError:
                    pass
                _nat_match = _re.search(r"\[(\d+)\]", beam["breakdown"])
                nat = int(_nat_match.group(1)) if _nat_match else (
                    beam["total"] - spell_atk_bonus
                )
                if nat == 20:
                    beam["hit"] = True
                    beam["crit"] = True
                elif nat == 1:
                    beam["hit"] = False
                else:
                    beam["hit"] = beam["total"] >= auto_attack_target_ac
                if _dmg_base and beam["hit"]:
                    roll_expr = (
                        _double_dice_for_crit(_dmg_base) if beam["crit"] else _dmg_base
                    )
                    try:
                        _dr = dice_mod.roll(roll_expr)
                        beam["damage_rolled"] = max(0, int(_dr.total))
                        beam["damage_breakdown"] = _dr.breakdown
                    except dice_mod.DiceParseError:
                        beam["damage_rolled"] = 0
                    agg_damage_rolled += beam["damage_rolled"]
                    if beam["damage_breakdown"]:
                        agg_damage_breakdown_parts.append(
                            f"beam {beam['beam']}: {beam['damage_breakdown']}"
                            if total_beams > 1 else beam["damage_breakdown"]
                        )
                if beam["hit"]:
                    any_hit = True
                if beam["crit"]:
                    any_crit = True
                beams.append(beam)
            # Aggregate fields for backward-compat. Single-beam casts
            # behave identically to pre-v2.40.0. Multi-beam casts get
            # the most-impressive beam's d20 (the highest total) as
            # the headline number; per-beam detail lives in
            # ``auto_attack_beams``.
            headline = max(beams, key=lambda b: b["total"]) if beams else {}
            auto_attack_total = int(headline.get("total") or 0)
            auto_attack_breakdown = headline.get("breakdown") or ""
            auto_attack_hit = any_hit
            auto_attack_crit = any_crit
            auto_attack_damage_rolled = agg_damage_rolled
            auto_attack_damage_breakdown = " · ".join(agg_damage_breakdown_parts)
            if (
                _dmg_base
                and any_hit
                and bool(campaign.auto_apply_damage)
                and agg_damage_rolled > 0
            ):
                dmg_result = await _apply_damage_to_combatant(
                    db, campaign_id, target_combatant,
                    agg_damage_rolled,
                    damage_type=auto_attack_damage_type,
                    attack_id=cast_id,
                )
                auto_attack_damage_applied = int(dmg_result.get("applied") or 0)
        payload["auto_attack_hit"] = auto_attack_hit
        payload["auto_attack_crit"] = auto_attack_crit
        payload["auto_attack_total"] = auto_attack_total
        payload["auto_attack_breakdown"] = auto_attack_breakdown
        payload["auto_attack_target_ac"] = auto_attack_target_ac
        payload["auto_attack_target_name"] = auto_attack_target_name
        payload["auto_attack_damage_rolled"] = auto_attack_damage_rolled
        payload["auto_attack_damage_applied"] = auto_attack_damage_applied
        payload["auto_attack_damage_type"] = auto_attack_damage_type
        payload["auto_attack_damage_breakdown"] = auto_attack_damage_breakdown
        payload["auto_attack_beams"] = beams  # v2.40.0 per-beam detail

    # v2.30.0 Phase T.3: save-spell auto-resolution.
    # When the spell carries a ``save_ability`` (top-level OR on an
    # action — same SRD-enrichment fallback the heal path uses) AND
    # a target was selected, resolve the save automatically:
    #   - PC target  → create a RollRequest scoped to the target's
    #                  owner_user_id, broadcast as a roll_request
    #                  card so the player rolls in their own UI.
    #   - NPC target → roll the save server-side from the monster's
    #                  ability scores (raw mod; no proficiency in
    #                  the demo seed) and broadcast as a ``roll``
    #                  event with a note that the chat card's
    #                  ``_appendSaveResultToSpellCard`` correlates
    #                  back to the cast.
    # The cast broadcast/response carry ``auto_save_*`` fields so
    # the chat card / toast can name the targeted creature and DC
    # without waiting for the WS round-trip.
    save_ability_raw = spell.get("save_ability") or next(
        (a.get("save_ability") for a in (spell.get("actions") or []) if a.get("save_ability")),
        "",
    )
    save_ability = (save_ability_raw or "").strip().upper()[:3]
    auto_save_target_name = ""
    auto_save_target_kind = ""  # "pc", "npc", or ""
    auto_save_prompted = False
    auto_save_prompt_id = 0
    auto_save_dc = 0
    auto_save_rolled = None
    auto_save_passed = None
    auto_save_breakdown = ""
    if save_ability in {"STR", "DEX", "CON", "INT", "WIS", "CHA"} and (
        target_combatant_id or target_character_id_in
    ):
        # Spell save DC = 8 + caster proficiency + spellcasting mod.
        caster_sheet = char.sheet or {}
        caster_prof = int(caster_sheet.get("proficiency_bonus") or 2)
        caster_spc = (caster_sheet.get("spellcasting_ability") or "").strip().upper()[:3]
        if caster_spc not in {"STR", "DEX", "CON", "INT", "WIS", "CHA"}:
            caster_spc = "WIS"  # safe fallback for non-spellcaster casts (shouldn't happen)
        caster_ab = int((caster_sheet.get("abilities") or {}).get(caster_spc, 10))
        caster_spc_mod = (caster_ab - 10) // 2
        auto_save_dc = 8 + caster_prof + caster_spc_mod

        target_combatant = _lookup_combatant(campaign_id, target_combatant_id)
        if not target_combatant and target_character_id_in:
            target_combatant = {
                "char_id": int(target_character_id_in),
                "id": target_combatant_id or "",
                "name": target_name_resolved or target_name_in or "",
            }
        if target_combatant:
            auto_save_target_name = target_combatant.get("name", "") or target_name_resolved or ""
            ab_long = {
                "STR": "STR", "DEX": "DEX", "CON": "CON",
                "INT": "INT", "WIS": "WIS", "CHA": "CHA",
            }[save_ability]
            stat_key = f"{save_ability.lower()}_save"
            note_label = f"{payload['spell_name']} — {ab_long} save"
            tgt_char_id = target_combatant.get("char_id")
            tgt_char = None
            if tgt_char_id:
                tgt_char = db.query(Character).filter(
                    Character.id == int(tgt_char_id),
                    Character.campaign_id == campaign_id,
                ).first()
            if tgt_char and tgt_char.owner_user_id:
                # ---- PC target → roll-request prompt ----
                auto_save_target_kind = "pc"
                req = RollRequest(
                    campaign_id=campaign_id,
                    created_by_user_id=user.id,
                    label=note_label,
                    base_expression="1d20",
                    stat_key=stat_key,
                    dc=auto_save_dc,
                    visibility=Visibility.PUBLIC,
                )
                db.add(req)
                db.commit()
                db.refresh(req)
                await hub.broadcast(campaign_id, {
                    "type": "roll_request",
                    "data": {
                        "id": req.id,
                        "label": req.label,
                        "stat_key": req.stat_key,
                        "base_expression": req.base_expression,
                        "dc": req.dc,
                        "visibility": req.visibility.value,
                        "created_by_name": user.display_name,
                        "created_by_user_id": user.id,
                        "target_user_ids": [tgt_char.owner_user_id],
                        "target_user_names": [tgt_char.name],
                    },
                })
                auto_save_prompted = True
                auto_save_prompt_id = req.id
                # v2.37.0 Phase T.3d: stash the cast context so the
                # roll-response handler can install the matching
                # condition buff if the PC fails. Slug + char_id +
                # DC give /roll_request/{id}/respond enough to look
                # the buff up in _SPELL_CONDITION_MAP.
                _purge_save_request_context()
                _save_request_context[req.id] = {
                    "ts": _time.time(),
                    "campaign_id": campaign_id,
                    "spell_slug": spell_slug,
                    "spell_name": payload["spell_name"],
                    "target_character_id": int(tgt_char.id),
                    "target_name": tgt_char.name,
                    "dc": int(auto_save_dc),
                    "save_ability": save_ability,
                    "caster_char_id": int(char.id),
                    "caster_char_name": char.name,
                }
            elif target_combatant.get("token_template_id"):
                # ---- NPC target → server rolls the save ----
                auto_save_target_kind = "npc"
                tmpl = db.query(TokenTemplate).filter(
                    TokenTemplate.id == int(target_combatant["token_template_id"]),
                ).first()
                if tmpl:
                    npc_sheet = _monster_template_to_sheet(tmpl, campaign_id)
                    npc_mod, _ = _resolve_stat_modifier(
                        npc_sheet, "dnd5e", stat_key,
                    )
                    expr = f"1d20{npc_mod:+d}"
                    try:
                        _r = dice_mod.roll(expr)
                        auto_save_rolled = int(_r.total)
                        auto_save_breakdown = _r.breakdown
                    except dice_mod.DiceParseError:
                        auto_save_rolled = 0
                        auto_save_breakdown = ""
                    auto_save_passed = auto_save_rolled >= auto_save_dc
                    # Broadcast as a regular roll so the toast fires
                    # AND ``_appendSaveResultToSpellCard`` correlates
                    # the result back to the cast card via note prefix.
                    await hub.broadcast(campaign_id, {
                        "type": "roll",
                        "data": {
                            "expression": expr,
                            "total": auto_save_rolled,
                            "breakdown": auto_save_breakdown,
                            "note": note_label,
                            "user_name": auto_save_target_name,
                            "char_name": auto_save_target_name,
                            "visibility": Visibility.PUBLIC.value,
                            "dc": auto_save_dc,
                        },
                    })

        # v2.31.0 Phase T.3b: auto-apply damage on save-for-half spells
        # (Fireball, Burning Hands, Sacred Flame, etc.). Full on fail,
        # half (rounded down) on success — the default save-for-half
        # rule. Gated by ``campaign.auto_apply_damage`` (same toggle as
        # weapon attacks), so the GM opts in. NPC-target only for v1
        # (PCs use the existing chat-card "Roll Damage" button + manual
        # apply). Save-or-suck spells (Hold Person — no damage on the
        # action) skip this block; the buff installer is filed as a
        # follow-up.
        damage_expr = ""
        damage_type = ""
        _save_dmg_scaling = None
        for a in (spell.get("actions") or []):
            if a.get("damage"):
                damage_expr = a.get("damage") or ""
                damage_type = a.get("damage_type") or ""
                _save_dmg_scaling = a.get("damage_scaling") or None
                break
        if not damage_expr:
            damage_expr = spell.get("damage") or ""
            damage_type = spell.get("damage_type") or damage_type
        # v2.36.0 Phase T.4c: cantrip scaling applies to save-cantrip
        # damage too (Sacred Flame 1d8 → 2d8 at L5, Poison Spray 1d12
        # → 2d12, Vicious Mockery 1d4 → 2d4). Same tier picker as the
        # attack-roll block.
        _save_caster_level = int((char.sheet or {}).get("level") or 1)
        _save_tier = _pick_damage_tier(_save_dmg_scaling, _save_caster_level)
        if _save_tier and _save_tier.get("damage"):
            damage_expr = _save_tier["damage"]
        auto_save_damage_rolled = 0
        auto_save_damage_applied = 0
        auto_save_damage_breakdown = ""
        auto_save_damage_type = damage_type
        if (
            damage_expr
            and auto_save_target_kind == "npc"
            and auto_save_passed is not None
            and target_combatant
            and bool(campaign.auto_apply_damage)
        ):
            try:
                _dr = dice_mod.roll(damage_expr)
                auto_save_damage_rolled = max(0, int(_dr.total))
                auto_save_damage_breakdown = _dr.breakdown
            except dice_mod.DiceParseError:
                auto_save_damage_rolled = 0
            if auto_save_damage_rolled > 0:
                # Save-for-half: full damage on fail, half on success.
                # Sacred Flame and similar "no effect on success" spells
                # are filed for the action schema — for now save-for-
                # half is the universal default.
                proposed = (
                    auto_save_damage_rolled if not auto_save_passed
                    else auto_save_damage_rolled // 2
                )
                if proposed > 0:
                    dmg_result = await _apply_damage_to_combatant(
                        db, campaign_id, target_combatant, proposed,
                        damage_type=damage_type,
                        attack_id=cast_id,
                    )
                    auto_save_damage_applied = int(dmg_result.get("applied") or 0)
        payload["auto_save_damage_rolled"] = auto_save_damage_rolled
        payload["auto_save_damage_applied"] = auto_save_damage_applied
        payload["auto_save_damage_breakdown"] = auto_save_damage_breakdown
        payload["auto_save_damage_type"] = auto_save_damage_type

        # v2.44.0 Phase T.5: AoE multi-target loop. The single-target
        # path above already ran for ids[0]; loop ids[1:] now, doing
        # the same NPC save-roll + save-for-half damage application
        # per extra target. Each result lands in ``auto_save_targets``
        # so the client can render one save-pill per target on the
        # spell-cast card. PC ids in the list are skipped for v1
        # (AoE-PC saves need a roll_request per target — filed).
        auto_save_targets: list[dict] = []
        # Always seed the list with target #0 (the single-target path's
        # outcome) so the client has a uniform array to iterate, even
        # for non-AoE casts. Skip when no save_ability is set or no
        # NPC outcome was resolved (e.g. PC target, or no target at all).
        if save_ability and auto_save_target_kind == "npc" and target_combatant:
            auto_save_targets.append({
                "combatant_id": target_combatant.get("id"),
                "target_name": auto_save_target_name,
                "rolled": auto_save_rolled,
                "breakdown": auto_save_breakdown,
                "passed": auto_save_passed,
                "damage_applied": auto_save_damage_applied,
                "damage_type": auto_save_damage_type,
            })
        # Extra AoE targets (skip the first; it already ran above).
        for extra_id in target_combatant_ids_in[1:]:
            extra = _lookup_combatant(campaign_id, extra_id)
            if not extra:
                continue
            extra_name = extra.get("name") or ""
            # v2.47.0 Phase T.5d: PC AoE save orchestration.
            # The combatant has a char_id whose Character row has an
            # owner_user_id (= a player owns this PC). Fire a per-PC
            # roll_request so the player can roll their save on the
            # tabletop, and stash the cast context under the request
            # id so /roll_request/{id}/respond can apply save-for-half
            # damage and broadcast a per-target update event the
            # client uses to patch the cast card's pill row.
            extra_char_id = extra.get("char_id")
            extra_pc = None
            if extra_char_id:
                extra_pc = db.query(Character).filter(
                    Character.id == int(extra_char_id),
                    Character.campaign_id == campaign_id,
                ).first()
            extra_is_pc = bool(extra_pc and extra_pc.owner_user_id)
            if extra_is_pc:
                _aoe_note = f"{payload['spell_name']} — {save_ability} save"
                _aoe_stat = f"{save_ability.lower()}_save"
                _aoe_req = RollRequest(
                    campaign_id=campaign_id,
                    created_by_user_id=user.id,
                    label=_aoe_note,
                    base_expression="1d20",
                    stat_key=_aoe_stat,
                    dc=int(auto_save_dc),
                    visibility=Visibility.PUBLIC,
                )
                db.add(_aoe_req)
                db.commit()
                db.refresh(_aoe_req)
                await hub.broadcast(campaign_id, {
                    "type": "roll_request",
                    "data": {
                        "id": _aoe_req.id,
                        "label": _aoe_req.label,
                        "stat_key": _aoe_req.stat_key,
                        "base_expression": _aoe_req.base_expression,
                        "dc": _aoe_req.dc,
                        "visibility": _aoe_req.visibility.value,
                        "created_by_name": user.display_name,
                        "created_by_user_id": user.id,
                        "target_user_ids": [extra_pc.owner_user_id],
                        "target_user_names": [extra_pc.name],
                    },
                })
                _purge_save_request_context()
                _save_request_context[_aoe_req.id] = {
                    "ts": _time.time(),
                    "campaign_id": campaign_id,
                    "spell_slug": spell_slug,
                    "spell_name": payload["spell_name"],
                    "target_character_id": int(extra_pc.id),
                    "target_name": extra_pc.name,
                    "dc": int(auto_save_dc),
                    "save_ability": save_ability,
                    "caster_char_id": int(char.id),
                    "caster_char_name": char.name,
                    # AoE-specific keys — present when this PC is one
                    # of several targets caught in the picker circle.
                    "is_aoe": True,
                    "cast_id": cast_id,
                    "combatant_id": extra.get("id"),
                    "damage_expr": damage_expr,
                    "damage_type": damage_type,
                    "auto_apply_damage": bool(campaign.auto_apply_damage),
                }
                auto_save_targets.append({
                    "combatant_id": extra.get("id"),
                    "target_name": extra_name,
                    "rolled": None,
                    "breakdown": "",
                    "passed": None,
                    "damage_applied": 0,
                    "damage_type": auto_save_damage_type,
                    "pc_skipped": True,
                    "pending_request_id": _aoe_req.id,
                })
                continue
            # NPC target: roll the save vs the same DC, then apply
            # save-for-half damage. Same shape as the single-target
            # path above but without the broadcast roll (AoE saves
            # are aggregate; broadcasting 8 save rolls for a Fireball
            # would spam the log).
            if not extra.get("token_template_id"):
                # No template to look up stats — skip.
                continue
            _tmpl = db.query(TokenTemplate).filter(
                TokenTemplate.id == int(extra["token_template_id"]),
            ).first()
            if not _tmpl:
                continue
            _npc_sheet = _monster_template_to_sheet(_tmpl, campaign_id)
            _npc_mod, _ = _resolve_stat_modifier(
                _npc_sheet, "dnd5e", f"{save_ability.lower()}_save",
            )
            _expr = f"1d20{_npc_mod:+d}"
            try:
                _r = dice_mod.roll(_expr)
                _rolled = int(_r.total)
                _bd = _r.breakdown
            except dice_mod.DiceParseError:
                _rolled = 0
                _bd = ""
            _passed = _rolled >= auto_save_dc
            # Roll damage fresh per target (each save is independent
            # in RAW; the damage roll is shared but applied per
            # target). v1 rolls once per target for simplicity —
            # matches the per-beam pattern of Eldritch Blast (v2.40.0).
            _dmg_applied = 0
            _dmg_breakdown = ""
            if damage_expr and bool(campaign.auto_apply_damage):
                try:
                    _dr = dice_mod.roll(damage_expr)
                    _dmg_rolled = max(0, int(_dr.total))
                    _dmg_breakdown = _dr.breakdown
                except dice_mod.DiceParseError:
                    _dmg_rolled = 0
                if _dmg_rolled > 0:
                    proposed = _dmg_rolled if not _passed else _dmg_rolled // 2
                    if proposed > 0:
                        _dr_result = await _apply_damage_to_combatant(
                            db, campaign_id, extra, proposed,
                            damage_type=damage_type,
                            attack_id=cast_id,
                        )
                        _dmg_applied = int(_dr_result.get("applied") or 0)
            auto_save_targets.append({
                "combatant_id": extra.get("id"),
                "target_name": extra_name,
                "rolled": _rolled,
                "breakdown": _bd,
                "damage_breakdown": _dmg_breakdown,
                "passed": _passed,
                "damage_applied": _dmg_applied,
                "damage_type": damage_type,
            })
        payload["auto_save_targets"] = auto_save_targets

        # v2.32.0 Phase T.3c: save-or-suck condition install. When the
        # spell has NO damage roll but DOES have a save_ability AND
        # the target failed the save, look up the spell's slug in
        # ``_SPELL_CONDITION_MAP`` and install the matching condition
        # buff on the target combatant. Hold Person → Paralyzed,
        # Charm Person → Charmed, Fear → Frightened, etc. NPC-only
        # for v1; PC save-or-suck is filed (the PC's owner rolls the
        # save in their UI — we'd need a roll-response hook to know
        # whether they passed and install accordingly).
        auto_save_buff_key = ""
        auto_save_buff_name = ""
        auto_save_buff_icon = ""
        auto_save_buff_duration = 0
        if (
            not damage_expr
            and auto_save_target_kind == "npc"
            and auto_save_passed is False
            and target_combatant
        ):
            cond = _SPELL_CONDITION_MAP.get(spell_slug)
            if cond:
                buff = {
                    "key": cond["key"],
                    "name": cond["name"],
                    "icon": cond.get("icon", "💫"),
                    "source_char_id": char.id,
                    "source_char_name": char.name,
                    "source_spell": payload["spell_name"],
                    "duration_rounds": int(cond.get("duration_rounds", 10)),
                    "duration_max": int(cond.get("duration_rounds", 10)),
                    "concentration": bool(cond.get("concentration")),
                    "effects": list(cond.get("effects", [])),
                }
                installed = await _install_buff_on_combatant_id(
                    campaign_id, target_combatant.get("id"), buff,
                )
                if installed:
                    auto_save_buff_key = cond["key"]
                    auto_save_buff_name = cond["name"]
                    auto_save_buff_icon = cond.get("icon", "💫")
                    auto_save_buff_duration = int(cond.get("duration_rounds", 10))
                    # v2.38.0 Phase T.3e: when the condition is RAW
                    # concentration (Hold Person, Fear, Hideous
                    # Laughter), also install a caster-side
                    # concentration buff. This makes the cleanup
                    # pipeline end-to-end: dropping the caster's
                    # concentration (manually via /end_buff, via a
                    # failed CON save on damage, or via casting a new
                    # concentration spell) calls
                    # ``_drop_paired_concentration_buffs`` which
                    # removes the condition buff from every target.
                    # The caster buff is keyed by spell slug so two
                    # save-or-suck concentration spells can't both
                    # ride the same key.
                    if bool(cond.get("concentration")):
                        caster_buff = {
                            "key": f"concentration-{spell_slug}",
                            "name": f"Concentrating: {payload['spell_name']}",
                            "icon": "🌀",
                            "source_char_id": char.id,
                            "source_char_name": char.name,
                            "source_spell": payload["spell_name"],
                            "duration_rounds": int(cond.get("duration_rounds", 10)),
                            "duration_max": int(cond.get("duration_rounds", 10)),
                            "concentration": True,
                            "effects": [f"Concentrating on {payload['spell_name']}"],
                        }
                        await _install_buff(campaign_id, char.id, caster_buff)
        payload["auto_save_buff_key"] = auto_save_buff_key
        payload["auto_save_buff_name"] = auto_save_buff_name
        payload["auto_save_buff_icon"] = auto_save_buff_icon
        payload["auto_save_buff_duration"] = auto_save_buff_duration

        payload["auto_save_ability"] = save_ability
        payload["auto_save_dc"] = auto_save_dc
        payload["auto_save_target_name"] = auto_save_target_name
        payload["auto_save_target_kind"] = auto_save_target_kind
        payload["auto_save_prompted"] = auto_save_prompted
        payload["auto_save_prompt_id"] = auto_save_prompt_id
        payload["auto_save_rolled"] = auto_save_rolled
        payload["auto_save_passed"] = auto_save_passed
        payload["auto_save_breakdown"] = auto_save_breakdown

    # v2.48.0 Phase T.5e: stash the AoE context so the placement
    # endpoint can resolve targets later. Skipped when targets were
    # already supplied (the existing AoE multi-target path ran the
    # resolution inline). The stash captures the DC + damage_expr +
    # campaign auto_apply_damage flag computed at cast time so the
    # placement preserves the "same casting" semantics — changing the
    # campaign toggle after cast but before placement won't re-roll
    # damage post-hoc.
    if pending_aoe_placement:
        _purge_pending_aoe_casts()
        # Compute the save DC from the caster sheet — same formula
        # the resolution block uses but computed here because the
        # resolution block is skipped when no targets are supplied.
        _caster_sheet = char.sheet or {}
        _caster_prof = int(_caster_sheet.get("proficiency_bonus") or 2)
        _caster_spc = (_caster_sheet.get("spellcasting_ability") or "").strip().upper()[:3]
        if _caster_spc not in {"STR", "DEX", "CON", "INT", "WIS", "CHA"}:
            _caster_spc = "WIS"
        _caster_ab = int((_caster_sheet.get("abilities") or {}).get(_caster_spc, 10))
        _caster_spc_mod = (_caster_ab - 10) // 2
        _pending_dc = 8 + _caster_prof + _caster_spc_mod
        # damage_expr + damage_type pulled from the spell same way the
        # resolution block does, but inline.
        _pending_dmg_expr = ""
        _pending_dmg_type = ""
        _pending_dmg_scaling = None
        for _a in (spell.get("actions") or []):
            if _a.get("damage"):
                _pending_dmg_expr = _a.get("damage") or ""
                _pending_dmg_type = _a.get("damage_type") or ""
                _pending_dmg_scaling = _a.get("damage_scaling") or None
                break
        if not _pending_dmg_expr:
            _pending_dmg_expr = spell.get("damage") or ""
            _pending_dmg_type = spell.get("damage_type") or _pending_dmg_type
        _pending_caster_level = int((char.sheet or {}).get("level") or 1)
        _pending_tier = _pick_damage_tier(_pending_dmg_scaling, _pending_caster_level)
        if _pending_tier and _pending_tier.get("damage"):
            _pending_dmg_expr = _pending_tier["damage"]
        _save_ability_for_stash = (spell.get("save_ability") or next(
            (a.get("save_ability") for a in (spell.get("actions") or []) if a.get("save_ability")),
            "",
        ) or "").strip().upper()[:3]
        # v2.49.0 — concentration detection. Spells with the explicit
        # ``concentration: true`` flag OR a duration starting with
        # "Up to" (Open5e convention) are concentration-tracked, so
        # /place_aoe persists the placement as a map marker.
        _dur = (spell.get("duration") or "").strip().lower()
        _is_concentration = bool(spell.get("concentration")) or _dur.startswith("up to")
        _pending_aoe_casts[cast_id] = {
            "ts": _time.time(),
            "campaign_id": campaign_id,
            "caster_user_id": user.id,
            "caster_char_id": int(char.id),
            "caster_char_name": char.name,
            "spell_slug": spell_slug,
            "spell_name": payload["spell_name"],
            "save_ability": _save_ability_for_stash,
            "dc": int(_pending_dc),
            "damage_expr": _pending_dmg_expr,
            "damage_type": _pending_dmg_type,
            "auto_apply_damage": bool(campaign.auto_apply_damage),
            "area": _aoe_area_info or {},
            "is_concentration": _is_concentration,
            # v2.49.77 — Phase 3A range-check inputs. The /place_aoe
            # gate compares the picked `center` coord to the caster's
            # token position vs the parsed spell range. Stashed at
            # cast time because by /place_aoe time we no longer have
            # the spell dict.
            "range_str": (spell.get("range") or ""),
            "strict_action_economy": bool(campaign.strict_action_economy),
        }

    await hub.broadcast(campaign_id, {"type": "spell_cast", "data": payload})
    if updated_slot is not None:
        await hub.broadcast(campaign_id, {
            "type": "spell_slot_update",
            "data": {
                "character_id": char.id,
                "class_slug": updated_slot["class_slug"],
                "level": updated_slot["level"],
                "total": updated_slot["total"],
                "used": updated_slot["used"],
            },
        })
    # v2.5.5: full-sheet → init chip sync. Slot was derived up-front
    # for the Phase 4 gate; reuse it here so the idempotence in
    # _mark_battle_economy keeps an over-budget cast from re-flipping
    # the chip (it's already used — that's why we got here).
    await _mark_battle_economy(campaign_id, char.id, slot_for_economy)
    return {
        "ok": True,
        "id": cast_id,
        "slot": updated_slot,
        "over_budget": was_used,
        # v2.22.0 Phase T.1: echo the resolved target so the rolling
        # player's toast can name them without waiting for the WS round-trip.
        "target_combatant_id": target_combatant_id or "",
        "target_character_id": target_character_id_in,
        "target_name": target_name_resolved or target_name_in or "",
        # v2.26.0 Phase T.4: echo auto-heal results for the local toast.
        "auto_heal_applied": auto_heal_applied,
        "auto_heal_target_name": auto_heal_target_name,
        "auto_heal_hp_after": auto_heal_hp_after,
        "auto_heal_revived": auto_heal_revived,
        # v2.30.0 Phase T.3: echo auto-save resolution.
        "auto_save_ability": save_ability if save_ability in {"STR", "DEX", "CON", "INT", "WIS", "CHA"} else "",
        "auto_save_dc": auto_save_dc,
        "auto_save_target_name": auto_save_target_name,
        "auto_save_target_kind": auto_save_target_kind,
        "auto_save_prompted": auto_save_prompted,
        "auto_save_prompt_id": auto_save_prompt_id,
        "auto_save_rolled": auto_save_rolled,
        "auto_save_passed": auto_save_passed,
        "auto_save_breakdown": auto_save_breakdown,
        # v2.31.0 Phase T.3b: echo damage applied on save-for-half.
        "auto_save_damage_rolled": payload.get("auto_save_damage_rolled", 0) if save_ability in {"STR", "DEX", "CON", "INT", "WIS", "CHA"} else 0,
        "auto_save_damage_applied": payload.get("auto_save_damage_applied", 0) if save_ability in {"STR", "DEX", "CON", "INT", "WIS", "CHA"} else 0,
        "auto_save_damage_type": payload.get("auto_save_damage_type", "") if save_ability in {"STR", "DEX", "CON", "INT", "WIS", "CHA"} else "",
        # v2.32.0 Phase T.3c: echo save-or-suck condition install.
        "auto_save_buff_key": payload.get("auto_save_buff_key", ""),
        "auto_save_buff_name": payload.get("auto_save_buff_name", ""),
        "auto_save_buff_icon": payload.get("auto_save_buff_icon", ""),
        "auto_save_buff_duration": payload.get("auto_save_buff_duration", 0),
        # v2.44.0 Phase T.5: per-target save outcomes for AoE casts.
        # When the cast was single-target, this is a 1-entry list
        # mirroring the headline auto_save_* fields. For AoE casts
        # (target_combatant_ids body), one entry per resolved target.
        # Always a list (possibly empty); never null.
        "auto_save_targets": payload.get("auto_save_targets", []),
        # v2.34.0 Phase T.4b: echo auto spell-attack-roll resolution.
        "auto_attack_hit": payload.get("auto_attack_hit"),
        "auto_attack_crit": payload.get("auto_attack_crit", False),
        "auto_attack_total": payload.get("auto_attack_total", 0),
        "auto_attack_breakdown": payload.get("auto_attack_breakdown", ""),
        "auto_attack_target_ac": payload.get("auto_attack_target_ac", 0),
        "auto_attack_target_name": payload.get("auto_attack_target_name", ""),
        "auto_attack_damage_rolled": payload.get("auto_attack_damage_rolled", 0),
        "auto_attack_damage_applied": payload.get("auto_attack_damage_applied", 0),
        "auto_attack_damage_type": payload.get("auto_attack_damage_type", ""),
        "auto_attack_damage_breakdown": payload.get("auto_attack_damage_breakdown", ""),
        # v2.40.0 multi-beam: per-beam detail for Eldritch Blast etc.
        "auto_attack_beams": payload.get("auto_attack_beams", []),
        # v2.48.0 Phase T.5e: caster-gated AoE placement. True when the
        # cast lands in pending-placement mode (AoE spell, no targets
        # supplied); the client renders a "📍 Place AoE" button on
        # the cast card instead of the empty pill row, and the button
        # posts to /place_aoe to resolve targets.
        "pending_aoe_placement": payload.get("pending_aoe_placement", False),
        "area_shape": payload.get("area_shape", ""),
        "area_size_ft": payload.get("area_size_ft", 0),
        "area_secondary_ft": payload.get("area_secondary_ft", 0),
    }


# ----------- API: ruler broadcast (Phase 3E — GM-led range demos) -----------

@router.post("/api/campaign/{campaign_id}/ruler_broadcast")
async def ruler_broadcast(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.49.84 Phase 3E — fan out the requester's ruler measurement
    to every connected client in the campaign.

    Body: ``{action: "show" | "hide", points?: [{x, y}, ...],
    multi_segment?: bool}``.

    Auth: any campaign member. The ruler is a transient visual cue, not
    a state mutation; sharing it is no more sensitive than chatting.

    Server side does NO ruler-state persistence — it's purely a fan-
    out path. Clients render via the broadcast; expiry / cleanup
    happens on the receiving side (default 8 s after the most recent
    update, see ``_remoteRulers`` in ``tabletop.js``).
    """
    body = await request.json()
    action = (body.get("action") or "").strip()
    if action not in ("show", "hide"):
        raise HTTPException(400, "action must be 'show' or 'hide'")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    payload: dict = {
        "user_id": user.id,
        "user_name": user.display_name,
        "action": action,
    }
    if action == "show":
        pts_raw = body.get("points") or []
        if not isinstance(pts_raw, list):
            raise HTTPException(400, "points must be a list")
        pts: list[dict] = []
        for p in pts_raw:
            if isinstance(p, dict):
                pts.append({
                    "x": float(p.get("x", 0) or 0),
                    "y": float(p.get("y", 0) or 0),
                })
        payload["points"] = pts
        payload["multi_segment"] = bool(body.get("multi_segment"))

    await hub.broadcast(campaign_id, {
        "type": "ruler_broadcast",
        "data": payload,
    })
    return {"ok": True}


# ----------- API: place AoE (Phase T.5e — caster-gated placement) -----------

@router.post("/api/campaign/{campaign_id}/place_aoe")
async def place_aoe(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Resolve a pending AoE cast's targets.

    Posted by the cast card's "📍 Place AoE" button after the caster
    or GM picks the placement on the canvas. Looks up the pending
    cast context (stashed by /cast_spell when it was AoE without
    targets), authorises the requester (must be the original caster
    OR the campaign GM), rolls per-target NPC saves + save-for-half
    damage, fires PC roll_requests via the v2.47.0 T.5d path, and
    broadcasts a ``spell_cast_aoe_resolved`` event that the client
    uses to populate the cast card's per-target pill row.
    """
    body = await request.json()
    cast_id = (body.get("cast_id") or "").strip()
    target_combatant_ids = body.get("target_combatant_ids") or []
    # v2.49.0 — center coords from the picker, used to persist the
    # placement as a map marker for concentration AoEs.
    center_body = body.get("center") or {}
    center_x = float(center_body.get("x") or 0) if isinstance(center_body, dict) else 0.0
    center_y = float(center_body.get("y") or 0) if isinstance(center_body, dict) else 0.0
    if not cast_id:
        raise HTTPException(400, "cast_id is required")
    if not isinstance(target_combatant_ids, list):
        raise HTTPException(400, "target_combatant_ids must be a list")

    _purge_pending_aoe_casts()
    ctx = _pending_aoe_casts.get(cast_id)
    if not ctx or ctx.get("campaign_id") != campaign_id:
        raise HTTPException(404, "pending AoE cast not found")

    # Auth: caster or GM only.
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "campaign not found")
    is_gm = _user_is_gm(user, campaign, db)
    if user.id != ctx.get("caster_user_id") and not is_gm:
        raise HTTPException(403, "only the caster or GM can place this AoE")

    # v2.49.77 — Phase 3A AoE range enforcement. Compares the picked
    # center coord to the caster's token position vs the parsed spell
    # range. Same three-tier override as Phase 2C: GM auto-bypass,
    # player override + not strict, otherwise enforced. Skipped when
    # the range parses to None / 0 (Self / Special / Unknown), when
    # the campaign has no active map, or when the caster has no token
    # on the active map. The cast point is the picker's chosen center
    # (Fireball at the centroid; cones / lines use the click direction
    # but the picker's commit still lands the click on the cursor —
    # the cursor IS the cast point for range purposes).
    _override_range = bool(body.get("override_range"))
    _strict_aoe = bool(ctx.get("strict_action_economy"))
    if not is_gm and not (_override_range and not _strict_aoe):
        from ..content.range_parser import max_range_ft, parse_range_ft
        _max_ft = max_range_ft(parse_range_ft(ctx.get("range_str") or ""))
        if _max_ft is not None and _max_ft > 0 and campaign.active_map_id:
            _caster_char = db.query(Character).filter(
                Character.id == int(ctx.get("caster_char_id") or 0),
            ).first()
            if _caster_char:
                _caster_token = (
                    db.query(Token)
                    .filter(
                        Token.character_id == _caster_char.id,
                        Token.map_id == campaign.active_map_id,
                    )
                    .first()
                )
                _map_row = db.query(Map).filter(Map.id == campaign.active_map_id).first()
                if _caster_token and _map_row and (center_x or center_y):
                    _distance_to_cast_point = _distance_ft_between_points(
                        int(_map_row.grid_size_px or 0),
                        (_map_row.grid_type.value if _map_row.grid_type else "square").lower(),
                        float(_caster_token.x or 0), float(_caster_token.y or 0),
                        center_x, center_y,
                    )
                    if _distance_to_cast_point > _max_ft:
                        return JSONResponse(status_code=409, content={
                            "error": "out_of_range",
                            "source_name": ctx.get("caster_char_name") or "",
                            "target_name": "(AoE cast point)",
                            "distance_ft": _distance_to_cast_point,
                            "range_ft": int(_max_ft),
                            "spell_name": ctx.get("spell_name") or "",
                        })

    save_ability = ctx.get("save_ability") or ""
    dc = int(ctx.get("dc") or 0)
    damage_expr = ctx.get("damage_expr") or ""
    damage_type = ctx.get("damage_type") or ""
    auto_apply_damage = bool(ctx.get("auto_apply_damage"))

    auto_save_targets: list[dict] = []
    # v2.48.5 — track whether we auto-added any NPCs to the battle
    # state so we can broadcast one battle_update at the end.
    auto_added_combatants = False
    for tid in target_combatant_ids:
        extra = _lookup_combatant(campaign_id, tid)
        if not extra and isinstance(tid, str) and tid.startswith("tok:"):
            # v2.48.5 — token-id fallback. The picker passed this id
            # because no combatant matched the token at picker time
            # (no active battle, or token added later). Look up the
            # Token row, synthesize a combatant dict; for NPCs, also
            # auto-add the combatant to the campaign's battle state
            # so the init tracker reflects who got swept up and HP
            # tracking works for follow-up attacks.
            try:
                token_id_int = int(tid[4:])
            except ValueError:
                continue
            token = db.query(Token).filter(Token.id == token_id_int).first()
            if not token:
                continue
            if token.character_id:
                # PC token — synthesize a combatant dict; damage
                # routes through the character sheet (no battle
                # entry required for HP tracking).
                extra = {
                    "id": tid,
                    "char_id": int(token.character_id),
                    "name": token.label or "",
                    "source_token_id": token.id,
                }
            elif token.token_template_id:
                # NPC token — auto-add to battle state with default
                # HP from the template so subsequent attacks track
                # HP, then use the new entry as ``extra``.
                _state = hub.get_battle(campaign_id) or {
                    "combatants": [], "turn_index": 0,
                    "round": 1, "active": False,
                }
                _tmpl = db.query(TokenTemplate).filter(
                    TokenTemplate.id == int(token.token_template_id),
                ).first()
                if not _tmpl:
                    continue
                _tmpl_sheet = _monster_template_to_sheet(_tmpl, campaign_id)
                _hp = (_tmpl_sheet.get("hp") or {})
                _hp_max = int(_hp.get("max") or _hp.get("current") or 10)
                new_combatant = {
                    "id": tid,
                    "name": token.label or _tmpl.name or "NPC",
                    "token_template_id": int(token.token_template_id),
                    "source_token_id": token.id,
                    "initiative": 0,
                    "hp_current": _hp_max,
                    "hp_max": _hp_max,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False,
                                "reaction": False, "movement": 0},
                }
                _state.setdefault("combatants", []).append(new_combatant)
                hub.set_battle(campaign_id, _state)
                auto_added_combatants = True
                extra = new_combatant
            else:
                continue
        if not extra:
            continue
        extra_name = extra.get("name") or ""
        extra_char_id = extra.get("char_id")
        extra_pc = None
        if extra_char_id:
            extra_pc = db.query(Character).filter(
                Character.id == int(extra_char_id),
                Character.campaign_id == campaign_id,
            ).first()
        extra_is_pc = bool(extra_pc and extra_pc.owner_user_id)

        if extra_is_pc:
            # v2.48.3 — auto-roll the PC's save + apply save-for-half
            # damage just like the NPC branch below. The v2.47.0
            # roll_request prompt path is bypassed here (still used
            # by the legacy /cast_spell-with-targets flow); the new
            # /place_aoe UX gives the caster + GM one button that
            # resolves every target in the picker, including PC
            # allies caught in the radius. Mirrors a "GM rolls
            # everyone's saves" houserule.
            pc_sheet = extra_pc.sheet or {}
            pc_mod, _ = _resolve_stat_modifier(
                pc_sheet, "dnd5e", f"{save_ability.lower()}_save",
            )
            expr = f"1d20{pc_mod:+d}"
            try:
                r = dice_mod.roll(expr)
                rolled = int(r.total)
                bd = r.breakdown
            except dice_mod.DiceParseError:
                rolled = 0
                bd = ""
            passed = rolled >= dc
            dmg_applied = 0
            dmg_breakdown = ""
            if damage_expr and auto_apply_damage:
                try:
                    dr = dice_mod.roll(damage_expr)
                    dmg_rolled = max(0, int(dr.total))
                    dmg_breakdown = dr.breakdown
                except dice_mod.DiceParseError:
                    dmg_rolled = 0
                if dmg_rolled > 0:
                    proposed = dmg_rolled if not passed else dmg_rolled // 2
                    if proposed > 0:
                        # Wrap PC character row in a combatant dict so
                        # ``_apply_damage_to_combatant`` routes through
                        # the PC HP / death-save / concentration path.
                        pc_combatant = {
                            "char_id": int(extra_pc.id),
                            "id": extra.get("id"),
                            "name": extra_pc.name,
                        }
                        dr_result = await _apply_damage_to_combatant(
                            db, campaign_id, pc_combatant, proposed,
                            damage_type=damage_type,
                            attack_id=cast_id,
                        )
                        dmg_applied = int(dr_result.get("applied") or 0)
            auto_save_targets.append({
                "combatant_id": extra.get("id"),
                "target_name": extra_name,
                "rolled": rolled,
                "breakdown": bd,
                "damage_breakdown": dmg_breakdown,
                "passed": passed,
                "damage_applied": dmg_applied,
                "damage_type": damage_type,
            })
            continue

        # NPC target — roll save server-side + apply save-for-half.
        if not extra.get("token_template_id"):
            continue
        tmpl = db.query(TokenTemplate).filter(
            TokenTemplate.id == int(extra["token_template_id"]),
        ).first()
        if not tmpl:
            continue
        npc_sheet = _monster_template_to_sheet(tmpl, campaign_id)
        npc_mod, _ = _resolve_stat_modifier(
            npc_sheet, "dnd5e", f"{save_ability.lower()}_save",
        )
        expr = f"1d20{npc_mod:+d}"
        try:
            r = dice_mod.roll(expr)
            rolled = int(r.total)
            bd = r.breakdown
        except dice_mod.DiceParseError:
            rolled = 0
            bd = ""
        passed = rolled >= dc
        dmg_applied = 0
        dmg_breakdown = ""
        if damage_expr and auto_apply_damage:
            try:
                dr = dice_mod.roll(damage_expr)
                dmg_rolled = max(0, int(dr.total))
                dmg_breakdown = dr.breakdown
            except dice_mod.DiceParseError:
                dmg_rolled = 0
            if dmg_rolled > 0:
                proposed = dmg_rolled if not passed else dmg_rolled // 2
                if proposed > 0:
                    dr_result = await _apply_damage_to_combatant(
                        db, campaign_id, extra, proposed,
                        damage_type=damage_type,
                        attack_id=cast_id,
                    )
                    dmg_applied = int(dr_result.get("applied") or 0)
        auto_save_targets.append({
            "combatant_id": extra.get("id"),
            "target_name": extra_name,
            "rolled": rolled,
            "breakdown": bd,
            "damage_breakdown": dmg_breakdown,
            "passed": passed,
            "damage_applied": dmg_applied,
            "damage_type": damage_type,
        })

    # v2.48.5 — push one battle_update so every client's init tracker
    # repaints with the resolved state: auto-added NPC combatants +
    # post-damage HP for every target. v2.48.8 — set
    # ``force_gm_sync: True`` so the GM client picks it up too. The
    # GM normally ignores battle_update (local state is authoritative
    # for drag/drop edits), but for /place_aoe the server is the
    # authority — without the flag, the GM saw damage logged in the
    # cast card but their init tracker stayed unchanged. Fires on
    # every /place_aoe (not just auto-add) so HP drops sync for
    # already-in-init NPCs too.
    _state = hub.get_battle(campaign_id) or {}
    if _state:
        await hub.broadcast(campaign_id, {
            "type": "battle_update",
            "data": _state,
            "force_gm_sync": True,
        })

    # v2.49.0 — concentration AoE persistence. For spells flagged as
    # concentration (Spirit Guardians, Hypnotic Pattern, Sleet Storm,
    # Stinking Cloud, Web, Moonbeam, etc.), persist the placement as
    # a map marker. The marker renders on the canvas with a dashed
    # translucent fill and stays put until the caster's concentration
    # ends — at which point ``_drop_paired_concentration_buffs``
    # (called from the concentration-save-failure path + manual buff
    # removal) calls ``_clear_caster_concentration_aoes`` to drop it.
    # Self-anchored shapes (self_sphere = Spirit Guardians) carry the
    # caster's char_id so the client can look up the caster's CURRENT
    # token position at render time and the marker moves with them.
    if ctx.get("is_concentration"):
        area = ctx.get("area") or {}
        shape = (area.get("shape") or "").strip()
        is_self_anchored = shape in ("self_sphere", "self_cube")
        marker = {
            "id": uuid.uuid4().hex[:12],
            "cast_id": cast_id,
            "caster_char_id": int(ctx.get("caster_char_id") or 0),
            "caster_char_name": ctx.get("caster_char_name") or "",
            "spell_name": ctx.get("spell_name") or "",
            "spell_slug": ctx.get("spell_slug") or "",
            "shape": shape,
            "size_ft": int(area.get("size_ft") or 0),
            "secondary_ft": int(area.get("secondary_ft") or 0),
            "center_x": center_x,
            "center_y": center_y,
            "is_self_anchored": is_self_anchored,
            "save_ability": save_ability,
            "dc": dc,
            # Re-trigger fields (Phase B follow-up — store now so the
            # marker is self-contained when the re-trigger handler
            # consumes them later).
            "damage_expr": damage_expr,
            "damage_type": damage_type,
            "auto_apply_damage": auto_apply_damage,
            "placed_at": _time.time(),
        }
        _concentration_aoes.setdefault(campaign_id, []).append(marker)
        await _broadcast_concentration_aoes(campaign_id)

    # Broadcast the resolved AoE so every client's cast card mutates
    # in place: pending button → per-target pill row.
    await hub.broadcast(campaign_id, {
        "type": "spell_cast_aoe_resolved",
        "data": {
            "cast_id": cast_id,
            "auto_save_targets": auto_save_targets,
            "save_ability": save_ability,
            "dc": dc,
        },
    })

    # One-shot: drop the stash so a second /place_aoe for the same
    # cast_id can't re-resolve and double-apply damage.
    _pending_aoe_casts.pop(cast_id, None)

    return {
        "ok": True,
        "cast_id": cast_id,
        "auto_save_targets": auto_save_targets,
    }


# ----------- API: use class feature (Phase 3 action-economy) -----------

@router.post("/api/campaign/{campaign_id}/use_feature")
async def use_feature(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Announce a class-feature use and mark its action-economy slot.

    Powers the "Class abilities" panel on the full character sheet
    (sheet_dnd5e.html) and any future mini-sheet equivalents. Body:
    ``{character_id, feature_key, option_key?, label?, desc?}``.

    The slot is **always** re-derived server-side from
    ``_feature_economy_slot(feature_key, option_key)`` — client claims
    are ignored to keep an attacker from minting bonus-action chips
    they shouldn't have. Returns 404 if the feature isn't in the
    curated table. ``label`` and ``desc`` are display-only and just
    get echoed into the ``feature_used`` WS broadcast for the roll
    log; they default to the feature_key/option_key if missing.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    feature_key = str(body.get("feature_key") or "").strip().lower()
    option_key_raw = body.get("option_key")
    option_key = str(option_key_raw).strip().lower() if option_key_raw else None
    if char_id <= 0 or not feature_key:
        raise HTTPException(400, "character_id and feature_key are required")

    slot = _feature_economy_slot(feature_key, option_key)
    if slot is None:
        raise HTTPException(404, f"Unknown feature: {feature_key}")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    feature_label = (body.get("label") or feature_key.replace("-", " ").title())[:160]
    if option_key:
        feature_label = f"{feature_label}: {(option_key or '').replace('-', ' ').title()}"
    # v2.43.11: fall back to the curated _FEATURE_ECONOMY desc when the
    # client request didn't include one. The cf-use button on the full
    # sheet sends ``desc: btn.dataset.desc``, but the mini-sheet, the
    # GM-tools panel, and any future caller that hits /use_feature
    # generically would broadcast a feature_used with empty feature_desc
    # — the roll-log card then renders just the feature name with no
    # explanation of what was used. The fallback covers all those
    # paths so every class-feature card carries its description.
    feature_desc = str(body.get("desc") or "")[:400]
    if not feature_desc:
        feature_desc = _feature_economy_desc(feature_key, option_key)[:400]

    # v2.6.1: Phase 4 over-budget gate. "free" features (Action Surge,
    # Divine Smite, Reckless Attack) never trigger the gate — they grant
    # rather than consume. See cast_spell for the matching pattern.
    # v2.8.0: strict-mode suppresses player overrides.
    was_used = _is_slot_used(campaign_id, char.id, slot)
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    override = bool(body.get("override")) and not strict
    if was_used and not user_is_gm and not override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": slot,
            "char_name": char.name,
            "source": "feature",
            "label": feature_label,
            "strict": strict,
        })

    # Resolve display info for the broadcast — same pattern as cast_spell.
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": feature_label,
            "feature_desc": feature_desc,
            "source": "class-feature",
            "remaining": 0,
            "max": 0,
            "over_budget": was_used,
            "over_budget_slot": slot if was_used else "",
        },
    })

    # slot == "free" means the feature doesn't consume an economy slot
    # (Action Surge / Divine Smite / Reckless Attack); the helper short-
    # circuits on anything that isn't action/bonus/reaction.
    await _mark_battle_economy(campaign_id, char.id, slot)

    return {"ok": True, "slot": slot, "feature_label": feature_label, "over_budget": was_used}


# ----------- API: use a consumable inventory item (Phase 4 polish) -----------

@router.post("/api/campaign/{campaign_id}/use_item")
async def use_item(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Use a consumable inventory item (Potion of Healing today, more
    later). Body: ``{character_id, inventory_index, override?}``.

    The item dict on the character's sheet must carry ``consumable: True``
    and a ``use_kind`` ("heal" for the only supported kind right now;
    future kinds slot into the same dispatch). Heal items roll
    ``heal_dice`` (default "2d4+2", the SRD Potion of Healing roll) and
    apply HP through ``_apply_hp_change`` so the death-save state
    machine fires correctly.

    Phase 4 + house-rule integration: when ``campaign.potions_as_bonus_action``
    is on AND ``use_kind == "heal"``, the use consumes the bonus economy
    slot. Player attempts return 409 ``over_budget`` with
    ``source: "potion"`` (the economy_messaging.js modal copy table reads
    that source for the house-rule-aware wording). GM clicks skip the
    gate; the ``over_budget`` flag still rides the broadcast for the
    Layer C audit badge regardless.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    inv_idx = int(body.get("inventory_index", -1))
    override = bool(body.get("override"))
    if char_id <= 0 or inv_idx < 0:
        raise HTTPException(400, "character_id and inventory_index are required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    inventory = list(sheet.get("inventory") or [])
    if inv_idx >= len(inventory):
        raise HTTPException(404, "Inventory item not found")
    item = dict(inventory[inv_idx] or {})
    if not item.get("consumable"):
        raise HTTPException(400, "Not a consumable item")
    use_kind = (item.get("use_kind") or "").strip().lower()
    qty = int(item.get("qty") or 0)
    if qty <= 0:
        return JSONResponse(status_code=409, content={
            "error": "out_of_stock", "label": item.get("name", "item"),
        })

    item_name = (item.get("name") or "item").strip()

    # House-rule slot derivation. Today this is "heal items eat the bonus
    # slot when potions_as_bonus_action is on." Future kinds (e.g. scroll
    # of cure wounds = action) plug in here keyed on use_kind.
    house_rule_active = bool(campaign.potions_as_bonus_action) and use_kind == "heal"
    slot = "bonus" if house_rule_active else None

    was_used = False
    if slot:
        was_used = _is_slot_used(campaign_id, char.id, slot)
        user_is_gm = _user_is_gm(user, campaign, db)
        # v2.8.0: strict-mode suppresses player overrides.
        strict = bool(campaign.strict_action_economy)
        effective_override = override and not strict
        if was_used and not user_is_gm and not effective_override:
            return JSONResponse(status_code=409, content={
                "error": "over_budget",
                "slot": slot,
                "char_name": char.name,
                "source": "potion",
                "label": item_name,
                "strict": strict,
            })

    # Decrement qty (or remove the row when it hits zero).
    new_qty = qty - 1
    if new_qty <= 0:
        inventory.pop(inv_idx)
    else:
        item["qty"] = new_qty
        inventory[inv_idx] = item
    sheet["inventory"] = inventory

    # Apply heal payload if the item is a heal kind.
    rolled = 0
    breakdown = ""
    new_hp_state = None
    heal_dice = item.get("heal_dice", "2d4+2")
    if use_kind == "heal":
        try:
            r = dice_mod.roll(heal_dice)
            rolled = r.total
            breakdown = r.breakdown
        except Exception:
            rolled = 0
            breakdown = ""
        # We just rebuilt sheet, so write it back to char before HP change
        # (which reads char.sheet inside _apply_hp_change).
        char.sheet = sheet
        hp = sheet.get("hp") or {}
        hp_cur = int(hp.get("current") or 0)
        hp_max = int(hp.get("max") or 0)
        new_cur = min(hp_max, hp_cur + rolled) if hp_max > 0 else (hp_cur + rolled)
        result = _apply_hp_change(char, new_cur)
        new_hp_state = result["hp"]
    else:
        char.sheet = sheet

    db.commit()

    # Roll log card via feature_used. The text is descriptive enough to
    # stand on its own without a dedicated item-use card type — same
    # pattern Phase 3's /use_feature uses.
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    if use_kind == "heal" and rolled > 0:
        feature_label = f"🧪 Drank {item_name}"
        feature_desc = f"Recovered {rolled} HP ({breakdown})"
    else:
        feature_label = f"🧪 Used {item_name}"
        feature_desc = (item.get("desc") or "").strip()[:400]

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": feature_label,
            "feature_desc": feature_desc,
            "source": "item-use",
            "remaining": new_qty if new_qty > 0 else 0,
            "max": qty,
            "over_budget": was_used,
            "over_budget_slot": slot if (was_used and slot) else "",
        },
    })

    # Surface the HP change to other clients so token bars + the open
    # character sheet's HP block re-render. heal_applied is the same
    # broadcast the existing /apply_healing endpoint uses, so the
    # ``_onHealApplied`` client handler renders this without changes.
    if use_kind == "heal" and new_hp_state is not None:
        await hub.broadcast(campaign_id, {
            "type": "heal_applied",
            "data": {
                "cast_id": "",
                "char_id": char.id,
                "char_name": char.name,
                "healer_name": user.display_name,
                "dice": heal_dice,
                "rolled": rolled,
                "breakdown": breakdown,
                "new_hp": new_hp_state,
                "claimed_count": 1,
                "max_targets": 1,
            },
        })

    # Mark the economy slot last so the resulting economy_update
    # broadcast lands after the roll-log entry — matches the order in
    # cast_spell / use_attack / use_feature.
    if slot:
        await _mark_battle_economy(campaign_id, char.id, slot)

    return {
        "ok": True,
        "rolled": rolled,
        "breakdown": breakdown,
        "remaining": new_qty if new_qty > 0 else 0,
        "over_budget": was_used,
        "slot": slot or "",
        "new_hp": new_hp_state,
    }


# ----------- API: campaign roster (Lay on Hands target picker, etc.) -----------

@router.get("/api/campaign/{campaign_id}/roster")
def campaign_roster(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return the campaign's character roster for the target-picker UI.

    Shape per entry: ``{id, name, color, owner_user_id, hp_current,
    hp_max, portrait_url}``. Used by the Lay on Hands picker (v2.10.0)
    and the Bardic Inspiration picker (planned). Visible to anyone
    who can view the campaign — the GM and every member see the same
    list. Doesn't expose anything beyond what's already in the
    character cards on the tabletop page.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    chars = (
        db.query(Character)
        .filter(Character.campaign_id == campaign_id)
        .order_by(Character.name)
        .all()
    )
    out = []
    for c in chars:
        hp = (c.sheet or {}).get("hp") or {}
        out.append({
            "id": c.id,
            "name": c.name,
            "color": c.color,
            "owner_user_id": c.owner_user_id,
            "hp_current": int(hp.get("current") or 0),
            "hp_max": int(hp.get("max") or 0),
            "portrait_url": c.portrait_url,
        })
    return {"characters": out}


# ----------- API: Lay on Hands (Paladin, priority #3) -----------

@router.post("/api/campaign/{campaign_id}/use_lay_on_hands")
async def use_lay_on_hands(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Spend HP from the paladin's Lay on Hands pool to heal a target.

    Body: ``{character_id, target_character_id, amount}``. The
    ``lay-on-hands`` resource on the calling character is the source
    pool (max = 5 × paladin level); ``amount`` HP is subtracted from
    the pool AND added to the target via ``_apply_hp_change`` so the
    death-save state machine wakes them from dying if applicable.

    Phase 4 over-budget gate: Lay on Hands is the Paladin's action.
    Same `was_used` / 409 / strict-mode flow as cast_spell / use_attack /
    use_feature / use_item. Override (modal Confirm) goes through
    unless `campaign.strict_action_economy` is on.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    target_id = int(body.get("target_character_id") or 0)
    amount = int(body.get("amount") or 0)
    override = bool(body.get("override"))
    if char_id <= 0 or target_id <= 0 or amount <= 0:
        raise HTTPException(400, "character_id, target_character_id, and amount > 0 are required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Paladin character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    target = db.query(Character).filter(
        Character.id == target_id, Character.campaign_id == campaign_id,
    ).first()
    if not target:
        raise HTTPException(404, "Target character not found")

    # Pool lookup. RAW: max = 5 × paladin level. We store it as a regular
    # resource entry on the sheet (`key: 'lay-on-hands'`), and the pool
    # current ticks down on use.
    sheet = dict(char.sheet or {})
    resources = list(sheet.get("resources") or [])
    pool_row = None
    pool_idx = -1
    for i, r in enumerate(resources):
        if (r.get("key") or "").lower() == "lay-on-hands":
            pool_row = dict(r)
            pool_idx = i
            break
    if pool_row is None:
        raise HTTPException(404, "No Lay on Hands resource on this sheet")
    pool_cur = int(pool_row.get("current") or 0)
    pool_max = int(pool_row.get("max") or 0)
    if amount > pool_cur:
        return JSONResponse(status_code=409, content={
            "error": "insufficient_pool",
            "available": pool_cur,
            "requested": amount,
        })

    # v2.10.0: Phase 4 over-budget gate. Lay on Hands consumes an
    # action; respect strict_action_economy if on.
    was_used = _is_slot_used(campaign_id, char.id, "action")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": "action",
            "char_name": char.name,
            "source": "lay-on-hands",
            "label": "Lay on Hands",
            "strict": strict,
        })

    # Apply the heal to the target. Read HP via _apply_hp_change so the
    # death-save state machine fires if the target was dying. RAW: Lay
    # on Hands restores up to N HP — it doesn't push above max.
    target_hp = (target.sheet or {}).get("hp") or {}
    target_cur = int(target_hp.get("current") or 0)
    target_max = int(target_hp.get("max") or 0)
    new_cur = min(target_max, target_cur + amount) if target_max > 0 else (target_cur + amount)
    actual_healed = new_cur - target_cur
    result = _apply_hp_change(target, new_cur)

    # Decrement the caster's pool by the AMOUNT the caster spent, not
    # by `actual_healed` — RAW: "expend a number of hit points up to
    # your lay on hands maximum". If the target's HP capped, the
    # paladin still spent what they declared.
    pool_row["current"] = pool_cur - amount
    resources[pool_idx] = pool_row
    sheet["resources"] = resources
    char.sheet = sheet

    db.commit()

    # Mark the caster's action slot in the realtime hub.
    await _mark_battle_economy(campaign_id, char.id, "action")

    # Resolve caster + target display info for the broadcasts.
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    # Roll-log card via feature_used.
    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": f"🙏 Lay on Hands → {target.name}",
            "feature_desc": f"Spent {amount} HP from pool ({pool_cur} → {pool_cur - amount} / {pool_max})",
            # v2.43.0: heal_amount + heal_target_name + before/after
            # surface the actual heal on the broadcast so the client
            # renders an oversized heal pill. Pool delta stays in the
            # inline feature_desc since it's caster-side accounting.
            "heal_amount": actual_healed,
            "heal_target_name": target.name,
            "heal_hp_before": target_cur,
            "heal_hp_after": result["hp"]["current"],
            "source": "lay-on-hands",
            "remaining": pool_cur - amount,
            "max": pool_max,
            "over_budget": was_used,
            "over_budget_slot": "action" if was_used else "",
        },
    })

    # HP-bar refresh for the target — same broadcast shape /apply_healing
    # and /use_item already use, so the existing _onHealApplied handler
    # picks this up unchanged.
    if actual_healed > 0:
        await hub.broadcast(campaign_id, {
            "type": "heal_applied",
            "data": {
                "cast_id": "",
                "char_id": target.id,
                "char_name": target.name,
                "healer_name": user.display_name,
                "dice": f"{amount} HP",
                "rolled": actual_healed,
                "breakdown": f"Lay on Hands ({amount})",
                "new_hp": result["hp"],
                "claimed_count": 1,
                "max_targets": 1,
            },
        })

    # Pool-update broadcast so any open resources panel re-pips. Reuses
    # the existing resource_update message that the v?.x rest endpoint
    # already broadcasts after refills.
    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id,
            "key": "lay-on-hands",
            "current": pool_cur - amount,
            "max": pool_max,
        },
    })

    return {
        "ok": True,
        "amount_spent": amount,
        "amount_healed": actual_healed,
        "pool_remaining": pool_cur - amount,
        "over_budget": was_used,
        "new_hp": result["hp"],
    }


# ----------- API: Bardic Inspiration (Bard, priority #5) -----------

def _bard_level_from_sheet(sheet: dict) -> int:
    """Read the bard level out of a sheet (single-class or multiclass).
    Used by /use_bardic_inspiration to scale the inspiration die.
    """
    if not sheet:
        return 0
    cls = (sheet.get("class") or "").strip().lower()
    if cls == "bard":
        try:
            return int(sheet.get("level") or 0)
        except (TypeError, ValueError):
            return 0
    for entry in (sheet.get("classes") or []):
        if (entry.get("class") or "").strip().lower() == "bard":
            try:
                return int(entry.get("level") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _song_of_rest_for_campaign(db: Session, campaign_id: int) -> tuple[int, str, int]:
    """v2.15.3: Song of Rest — Bard Lv 2+ in the party grants every
    ally an extra die of healing per Hit Die spent during a short
    rest. Die scales with the highest Bard level in the campaign:
    Lv 2-8 = d6, Lv 9-12 = d8, Lv 13-16 = d10, Lv 17+ = d12.

    Returns ``(die_size, bard_name, bard_level)`` where ``die_size``
    is 0 when no eligible Bard is in the campaign. Multi-bard parties
    use the highest-level Bard's die (RAW: bonus dice don't stack;
    one bard's performance is enough).
    """
    chars = db.query(Character).filter(Character.campaign_id == campaign_id).all()
    best_lv = 0
    best_name = ""
    for c in chars:
        if not c.sheet:
            continue
        lv = _bard_level_from_sheet(c.sheet)
        if lv > best_lv:
            best_lv = lv
            best_name = c.name
    if best_lv < 2:
        return 0, "", 0
    if best_lv >= 17:
        die = 12
    elif best_lv >= 13:
        die = 10
    elif best_lv >= 9:
        die = 8
    else:
        die = 6
    return die, best_name, best_lv


@router.post("/api/campaign/{campaign_id}/use_bardic_inspiration")
async def use_bardic_inspiration(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Spend a Bardic Inspiration use to grant a target an inspiration die.

    Body: ``{character_id, target_character_id, override?}``. Die size
    scales with bard level: d6 (1-4), d8 (5-9), d10 (10-14), d12 (15+).
    The recipient adds the die to one attack roll / ability check /
    save in the next 10 minutes (tracked manually until buff slot (C)
    lands). The audit trail is the ``feature_used`` roll-log entry.

    Phase 4 over-budget gate: Bardic Inspiration is a bonus action.
    Same `was_used` / 409 / strict-mode flow as cast_spell / use_attack /
    use_feature / use_lay_on_hands.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    target_id = int(body.get("target_character_id") or 0)
    override = bool(body.get("override"))
    if char_id <= 0 or target_id <= 0:
        raise HTTPException(400, "character_id and target_character_id are required")
    if char_id == target_id:
        # RAW: "you can use a bonus action on your turn to choose one
        # creature OTHER THAN YOURSELF". The client-side picker filters
        # self out; the server enforces it too as defense-in-depth.
        raise HTTPException(400, "Cannot inspire yourself")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Bard character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    target = db.query(Character).filter(
        Character.id == target_id, Character.campaign_id == campaign_id,
    ).first()
    if not target:
        raise HTTPException(404, "Target character not found")

    sheet = dict(char.sheet or {})
    resources = list(sheet.get("resources") or [])
    res_row = None
    res_idx = -1
    for i, r in enumerate(resources):
        if (r.get("key") or "").lower() == "bardic-inspiration":
            res_row = dict(r)
            res_idx = i
            break
    if res_row is None:
        raise HTTPException(404, "No Bardic Inspiration resource on this sheet")
    cur = int(res_row.get("current") or 0)
    mx = int(res_row.get("max") or 0)
    if cur <= 0:
        return JSONResponse(status_code=409, content={
            "error": "out_of_uses",
            "label": "Bardic Inspiration",
        })

    # Phase 4 over-budget gate (bonus slot — RAW: 1 bonus action).
    was_used = _is_slot_used(campaign_id, char.id, "bonus")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": "bonus",
            "char_name": char.name,
            "source": "bardic-inspiration",
            "label": "Bardic Inspiration",
            "strict": strict,
        })

    # Die scaling per PHB. Lv 1-4 d6, 5-9 d8, 10-14 d10, 15+ d12. The
    # bard's class level controls the size; a multiclassed Bard/Wizard
    # uses just the Bard half.
    bard_lv = _bard_level_from_sheet(sheet)
    if bard_lv >= 15:
        die = "d12"
    elif bard_lv >= 10:
        die = "d10"
    elif bard_lv >= 5:
        die = "d8"
    else:
        die = "d6"

    # Decrement counter.
    res_row["current"] = cur - 1
    resources[res_idx] = res_row
    sheet["resources"] = resources
    char.sheet = sheet
    db.commit()

    # Mark the bonus slot.
    await _mark_battle_economy(campaign_id, char.id, "bonus")

    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": f"✨ Bardic Inspiration → {target.name} ({die})",
            "feature_desc": (
                f"{target.name} gains a Bardic Inspiration {die} for 10 minutes. "
                f"Add it to one attack roll, ability check, or saving throw."
            ),
            "source": "bardic-inspiration",
            "remaining": cur - 1,
            "max": mx,
            "over_budget": was_used,
            "over_budget_slot": "bonus" if was_used else "",
        },
    })

    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id,
            "key": "bardic-inspiration",
            "current": cur - 1,
            "max": mx,
        },
    })

    return {
        "ok": True,
        "die": die,
        "target_id": target.id,
        "target_name": target.name,
        "remaining": cur - 1,
        "over_budget": was_used,
    }


# ----------- API: Cutting Words (Lore Bard Lv 3) -----------

@router.post("/api/campaign/{campaign_id}/use_cutting_words")
async def use_cutting_words(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Spend a Bardic Inspiration use as a Lore Bard Lv 3 Cutting Words
    reaction. The server rolls 1d{BI die} and announces the subtraction
    amount; the GM applies the reduction to whatever roll just
    triggered the reaction (no roll-time intercept infrastructure yet
    — see the plan doc's (B) infrastructure note).

    Body: ``{character_id, target_character_id?, target_name?, override?}``.
    Target resolution order (v2.15.10+): if ``target_character_id`` is
    supplied AND resolves to a Character row, use that Character's name
    in the broadcast. Else if ``target_name`` is supplied (free-form
    string from the picker for NPC tokens that don't have a Character
    row — bandits, monsters spawned via token_template), use it
    verbatim. Else announce reads "from a creature's roll" generically.
    Die scaling matches Bardic Inspiration: d6 (Lv 1-4), d8 (Lv 5-9),
    d10 (Lv 10-14), d12 (Lv 15+).

    Phase 4 over-budget gate on the reaction slot (RAW: 1 reaction).
    Mirrors the /use_bardic_inspiration pattern for resource decrement
    + chip mark + announce.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    target_id_raw = body.get("target_character_id")
    target_id = int(target_id_raw) if target_id_raw else 0
    target_name_raw = body.get("target_name")
    target_name_str = str(target_name_raw).strip()[:80] if target_name_raw else ""
    override = bool(body.get("override"))
    if char_id <= 0:
        raise HTTPException(400, "character_id is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Bard character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    target = None
    if target_id > 0:
        target = db.query(Character).filter(
            Character.id == target_id, Character.campaign_id == campaign_id,
        ).first()
        # target may be None when the triggering creature is an NPC
        # tracked only in the encounter's tokens (not in Character).
        # Caller can omit target_character_id in that case.

    sheet = dict(char.sheet or {})

    # Lore Bard Lv 3 eligibility — defense-in-depth check. The client
    # filters the Cutting Words button visibility by the same predicate.
    bard_lv = _bard_level_from_sheet(sheet)
    if bard_lv < 3:
        raise HTTPException(409, "Cutting Words requires Bard level 3+")
    is_lore = "lore" in (sheet.get("subclass") or "").strip().lower()
    if not is_lore:
        for c in sheet.get("classes") or []:
            if (c.get("class") or "").strip().lower() == "bard":
                if "lore" in (c.get("subclass") or "").strip().lower():
                    is_lore = True
                    break
    if not is_lore:
        raise HTTPException(409, "Cutting Words requires the College of Lore subclass")

    resources = list(sheet.get("resources") or [])
    res_row = None
    res_idx = -1
    for i, r in enumerate(resources):
        if (r.get("key") or "").lower() == "bardic-inspiration":
            res_row = dict(r)
            res_idx = i
            break
    if res_row is None:
        raise HTTPException(404, "No Bardic Inspiration resource on this sheet")
    cur = int(res_row.get("current") or 0)
    mx = int(res_row.get("max") or 0)
    if cur <= 0:
        return JSONResponse(status_code=409, content={
            "error": "out_of_uses",
            "label": "Bardic Inspiration (Cutting Words)",
        })

    # Phase 4 over-budget gate (reaction slot).
    was_used = _is_slot_used(campaign_id, char.id, "reaction")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": "reaction",
            "char_name": char.name,
            "source": "cutting-words",
            "label": "Cutting Words",
            "strict": strict,
        })

    # Die size — same table as Bardic Inspiration.
    if bard_lv >= 15:
        die_size = 12
    elif bard_lv >= 10:
        die_size = 10
    elif bard_lv >= 5:
        die_size = 8
    else:
        die_size = 6

    # Roll the BI die server-side. RAW: bard rolls immediately and
    # subtracts the result. Result is broadcast so the GM can apply it.
    try:
        result = dice_mod.roll(f"1d{die_size}")
        rolled = max(1, result.total)
        breakdown = result.breakdown
    except dice_mod.DiceParseError:
        rolled = 1
        breakdown = ""

    # Decrement counter.
    res_row["current"] = cur - 1
    resources[res_idx] = res_row
    sheet["resources"] = resources
    char.sheet = sheet
    db.commit()

    # Mark the reaction slot.
    await _mark_battle_economy(campaign_id, char.id, "reaction")

    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    # Resolve the display name. Character lookup wins if it returned
    # a row; otherwise the picker's free-form target_name (an NPC token
    # like "Bandit Alpha") falls through to the broadcast text.
    if target:
        display_name = target.name
    elif target_name_str:
        display_name = target_name_str
    else:
        display_name = ""

    if display_name:
        feature_name = f"🎭 Cutting Words → -{rolled} from {display_name}'s roll"
        target_phrase = display_name
    else:
        feature_name = f"🎭 Cutting Words → -{rolled} from a creature's roll"
        target_phrase = "a creature"

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": feature_name,
            "feature_desc": (
                f"Reaction. GM applies the reduction to {target_phrase}'s "
                f"triggering attack roll, ability check, or damage roll."
            ),
            # v2.35.0: dice fields so roll_toast.js fires the BI die toast.
            "dice_expression": f"1d{die_size}",
            "dice_total": rolled,
            "dice_breakdown": breakdown,
            "dice_note": f"🎭 Cutting Words → -{rolled}{(' from ' + display_name) if display_name else ''}",
            "source": "cutting-words",
            "remaining": cur - 1,
            "max": mx,
            "over_budget": was_used,
            "over_budget_slot": "reaction" if was_used else "",
        },
    })

    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id,
            "key": "bardic-inspiration",
            "current": cur - 1,
            "max": mx,
        },
    })

    return {
        "ok": True,
        "die": f"d{die_size}",
        "rolled": rolled,
        "breakdown": breakdown,
        "target_id": target.id if target else None,
        "target_name": display_name or None,
        "remaining": cur - 1,
        "over_budget": was_used,
    }


# ----------- API: Arcane Recovery (Wizard Lv 1) -----------

def _wizard_level_from_sheet(sheet: dict) -> int:
    """Wizard-level helper (mirrors `_bard_level_from_sheet`)."""
    if not sheet:
        return 0
    cls = (sheet.get("class") or "").strip().lower()
    if cls == "wizard":
        try:
            return int(sheet.get("level") or 0)
        except (TypeError, ValueError):
            return 0
    for entry in (sheet.get("classes") or []):
        if (entry.get("class") or "").strip().lower() == "wizard":
            try:
                return int(entry.get("level") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _fighter_level_from_sheet(sheet: dict) -> int:
    """Fighter-level helper (mirrors `_bard_level_from_sheet`)."""
    if not sheet:
        return 0
    cls = (sheet.get("class") or "").strip().lower()
    if cls == "fighter":
        try:
            return int(sheet.get("level") or 0)
        except (TypeError, ValueError):
            return 0
    for entry in (sheet.get("classes") or []):
        if (entry.get("class") or "").strip().lower() == "fighter":
            try:
                return int(entry.get("level") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _barbarian_level_from_sheet(sheet: dict) -> int:
    """Barbarian-level helper (mirrors `_fighter_level_from_sheet`).
    v2.19.0: added for Rage damage scaling — +2 Lv 1-8, +3 Lv 9-15, +4
    Lv 16+.
    """
    if not sheet:
        return 0
    cls = (sheet.get("class") or "").strip().lower()
    if cls == "barbarian":
        try:
            return int(sheet.get("level") or 0)
        except (TypeError, ValueError):
            return 0
    for entry in (sheet.get("classes") or []):
        if (entry.get("class") or "").strip().lower() == "barbarian":
            try:
                return int(entry.get("level") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _rage_damage_bonus(barbarian_lv: int) -> int:
    """RAW Rage damage bonus by Barbarian level. Lv 1-8 = +2, Lv 9-15 =
    +3, Lv 16+ = +4."""
    if barbarian_lv >= 16:
        return 4
    if barbarian_lv >= 9:
        return 3
    return 2


# v2.20.0 Phase B — roll-time intercepts. /attack reads attacker's
# buffs from the hub battle state at damage-roll time and folds in
# any auto-applied uplifts. Currently supported:
#
# - Rage (Barbarian self-buff). When damage_type is physical
#   (bludgeoning / piercing / slashing) AND attack is melee-or-thrown
#   STR-based (heuristic: physical damage type), add a flat
#   ``melee_str_damage_bonus`` to the damage roll AND roll the attack
#   d20 with advantage.
# - Hunter's Mark (Ranger concentration on target). When
#   target_combatant_id matches the buff's
#   ``weapon_hit_bonus_target_combatant_id``, roll +1d6 (force or
#   weapon type, per buff's stored damage_type) and stack onto damage.
# - Hex (Warlock concentration on target). Same shape as Hunter's
#   Mark but +1d6 necrotic. Stacks with weapon damage type.
# - Colossus Slayer (Ranger Hunter's Prey at Hunter Lv 3+). Once per
#   turn, when the target's current HP is below max, add +1d6 of
#   the weapon's damage type. Tracked via the
#   ``combatant.economy.colossus_slayer_used`` flag (reset at turn
#   start alongside the other action chips in the GM's nextTurn
#   handler — handled client-side by tabletop.js).
#
# Each uplift is a separate dice roll; the resulting list is returned
# as ``auto_uplifts`` on the /attack response + broadcast payload so
# the chat-card client can render them as labeled lines below the
# base damage. The aggregate ``auto_uplift_total`` is the sum across
# all auto-uplifts (used by the chat card's "Total damage" line; can
# be ignored if the client wants to display per-type breakdowns).

_PHYSICAL_DAMAGE_TYPES = {"bludgeoning", "piercing", "slashing"}


def _hunter_level_from_sheet(sheet: dict) -> int:
    """Ranger-Hunter level helper. Returns 0 for non-Hunters."""
    if not sheet:
        return 0
    primary = (sheet.get("class") or "").strip().lower()
    sub = (sheet.get("subclass") or "").strip().lower()
    if primary == "ranger" and "hunter" in sub:
        try:
            return int(sheet.get("level") or 0)
        except (TypeError, ValueError):
            return 0
    for entry in (sheet.get("classes") or []):
        if (entry.get("class") or "").strip().lower() == "ranger" \
                and "hunter" in (entry.get("subclass") or "").strip().lower():
            try:
                return int(entry.get("level") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _compute_attack_auto_uplifts(
    *,
    campaign_id: int,
    attacker_char_id: int,
    attacker_sheet: dict,
    target_combatant_id: str | None,
    attack_damage_type: str,
) -> list[dict]:
    """Compute auto-applied uplifts from attacker's buffs + class
    features at /attack time.

    Returns a list of ``{label, expression, total, breakdown,
    damage_type, source}`` dicts — each a separately-rolled uplift.
    The list is empty when no uplifts apply.

    Side effects: none. The caller is responsible for marking the
    Colossus Slayer "used this turn" flag via the action-economy
    helpers — this function reads the flag from the hub combatant but
    doesn't mutate it (the GM-side turn-advance handler resets the
    flag alongside action chips).
    """
    uplifts: list[dict] = []
    state = hub.get_battle(campaign_id)
    attacker_combatant = None
    target_combatant = None
    if state:
        for c in state.get("combatants") or []:
            if c.get("char_id") == attacker_char_id:
                attacker_combatant = c
            if target_combatant_id and c.get("id") == target_combatant_id:
                target_combatant = c

    attacker_buffs = (attacker_combatant or {}).get("buffs") or []
    damage_type_l = (attack_damage_type or "").strip().lower()
    is_physical = damage_type_l in _PHYSICAL_DAMAGE_TYPES

    # 1. Rage damage bonus (flat, applies on physical melee/thrown).
    #    The buff itself doesn't carry a die expression — it's a flat
    #    int. Roll it as a "+N" virtual roll so the breakdown reads
    #    "+2 [Rage]" uniformly with the other uplifts.
    for b in attacker_buffs:
        if not isinstance(b, dict):
            continue
        if b.get("key") != "rage":
            continue
        effects = b.get("effects") or {}
        bonus = int(effects.get("melee_str_damage_bonus") or 0)
        if bonus > 0 and is_physical:
            uplifts.append({
                "label": "Rage",
                "expression": f"+{bonus}",
                "total": bonus,
                "breakdown": f"+{bonus}",
                "damage_type": attack_damage_type or "bludgeoning",
                "source": "rage",
            })

    # 2. Hunter's Mark / Hex weapon-hit riders. Target-keyed: only
    #    fire when target_combatant_id matches the buff's stored
    #    target. Skip when target is unknown.
    if target_combatant_id:
        for b in attacker_buffs:
            if not isinstance(b, dict):
                continue
            effects = b.get("effects") or {}
            dice = (effects.get("weapon_hit_bonus_dice") or "").strip()
            tgt = effects.get("weapon_hit_bonus_target_combatant_id")
            if not dice or tgt != target_combatant_id:
                continue
            try:
                r = dice_mod.roll(dice)
                rider_type = (effects.get("weapon_hit_bonus_damage_type")
                              or attack_damage_type or "force")
                uplifts.append({
                    "label": b.get("name") or b.get("key") or "Bonus dice",
                    "expression": dice,
                    "total": r.total,
                    "breakdown": r.breakdown,
                    "damage_type": rider_type,
                    "source": b.get("key") or "buff",
                })
            except dice_mod.DiceParseError:
                pass

    # 3. Colossus Slayer (Ranger Hunter's Prey at Lv 3+).
    #    Once per turn: +1d6 vs target whose current HP < max HP. Uses
    #    the same damage type as the weapon. Tracked via
    #    ``combatant.economy.colossus_slayer_used`` flag — reset at
    #    turn start by the GM-side nextTurn handler (alongside action
    #    chips).
    hunter_lv = _hunter_level_from_sheet(attacker_sheet)
    has_cs_feature = False
    if hunter_lv >= 3:
        for cf in (attacker_sheet.get("class_features") or []):
            if (cf or {}).get("key") == "colossus-slayer":
                has_cs_feature = True
                break
    if has_cs_feature and target_combatant is not None:
        # "Below max HP" — strict less-than.
        cur = int(target_combatant.get("hp_current") or 0)
        mx = int(target_combatant.get("hp_max") or 0)
        already_used = bool(
            (attacker_combatant or {}).get("economy", {}).get("colossus_slayer_used")
        )
        if mx > 0 and cur < mx and not already_used:
            try:
                r = dice_mod.roll("1d6")
                uplifts.append({
                    "label": "Colossus Slayer",
                    "expression": "1d6",
                    "total": r.total,
                    "breakdown": r.breakdown,
                    "damage_type": attack_damage_type or "piercing",
                    "source": "colossus-slayer",
                })
            except dice_mod.DiceParseError:
                pass

    return uplifts


async def _mark_colossus_slayer_used(
    campaign_id: int, attacker_char_id: int,
) -> None:
    """Set ``combatant.economy.colossus_slayer_used = True`` on the
    attacker so subsequent attacks this turn don't re-roll Colossus
    Slayer. Reset is handled client-side by the GM's nextTurn handler.
    """
    state = hub.get_battle(campaign_id)
    if not state:
        return
    target = None
    for c in state.get("combatants") or []:
        if c.get("char_id") == attacker_char_id:
            target = c
            break
    if target is None:
        return
    economy = target.get("economy") or {}
    if not isinstance(economy, dict):
        economy = {}
        target["economy"] = economy
    economy["colossus_slayer_used"] = True
    hub.set_battle(campaign_id, state)


def _has_rage_str_advantage(
    campaign_id: int, attacker_char_id: int, damage_type: str,
) -> bool:
    """Return True if the attacker has Rage active AND the attack
    qualifies as STR-based (physical damage type). Used to apply
    advantage on the d20 attack roll.
    """
    damage_type_l = (damage_type or "").strip().lower()
    if damage_type_l not in _PHYSICAL_DAMAGE_TYPES:
        return False
    for b in _get_buffs(campaign_id, attacker_char_id):
        if (b or {}).get("key") != "rage":
            continue
        effects = (b or {}).get("effects") or {}
        adv_list = effects.get("advantage_on") or []
        if "str_attack" in adv_list:
            return True
    return False


def _resistance_halve(
    damage_amount: int, damage_type: str, target_sheet: dict,
) -> tuple[int, bool]:
    """If the target's ``_buffs_active`` has resistance to
    ``damage_type``, return (halved, True). Otherwise (damage_amount,
    False). RAW: resistance halves damage (floor).
    """
    if damage_amount <= 0 or not damage_type:
        return damage_amount, False
    damage_type_l = damage_type.strip().lower()
    for b in (target_sheet or {}).get("_buffs_active") or []:
        if not isinstance(b, dict):
            continue
        # v2.49.61: condition buffs (Paralyzed, Stunned, Unconscious-from-
        # Sleep, etc.) carry `effects` as a STRING LIST describing the
        # mechanical riders for UI display. Mechanical-effect buffs (Rage,
        # Hex, Hunter's Mark) carry `effects` as a DICT with structured
        # keys including `resistance_to`. The resistance check only
        # applies to dict-shaped effects — string-list effects don't
        # advertise damage resistance, so skip them.
        effects = b.get("effects")
        if not isinstance(effects, dict):
            continue
        resists = [str(r).strip().lower() for r in (effects.get("resistance_to") or [])]
        if damage_type_l in resists:
            return damage_amount // 2, True
    return damage_amount, False


def _resistance_halve_npc(
    damage_amount: int, damage_type: str, combatant: dict, db: Session,
) -> tuple[int, bool]:
    """NPC-side resistance halving. Mirror of ``_resistance_halve``
    for non-PC combatants. The PC path reads ``_buffs_active`` off
    the character sheet; NPCs don't have a sheet — their resistances
    live on their TokenTemplate's ``sheet.damage_resistances`` list
    (parsed by ``_split_defense`` from the SRD stat-block string at
    tabletop_routes.py:16756). Buffs installed on the NPC via the
    hub combatant's ``buffs`` list also count (Stoneskin cast on a
    bandit, Rage'd ogre, etc.) — same dict-shaped ``effects.resistance_to``
    structure as PCs.

    Pre-v2.49.109 this code path silently no-op'd (the NPC branch of
    ``_apply_damage_to_combatant`` hardcoded ``applied = damage_amount``
    with the comment "NPCs don't have resistance buffs yet"). A bandit
    with template-listed fire resistance still took full damage from a
    Fireball — the v2.49.107 damage review flagged this as the highest-
    impact in-play gameplay bug. This helper closes that gap.

    Returns ``(halved, True)`` if matched, else ``(damage_amount, False)``.
    Floor division per RAW. Immunity (sets to 0) and vulnerability
    (doubles) are NOT applied here — filed for a follow-up commit.
    """
    if damage_amount <= 0 or not damage_type:
        return damage_amount, False
    damage_type_l = damage_type.strip().lower()
    # (1) Permanent template-listed resistances.
    tmpl_id = combatant.get("token_template_id")
    if tmpl_id:
        tmpl = db.query(TokenTemplate).filter(TokenTemplate.id == tmpl_id).first()
        if tmpl:
            tmpl_sheet = tmpl.sheet or {}
            perm = [
                str(r).strip().lower()
                for r in (tmpl_sheet.get("damage_resistances") or [])
                if isinstance(r, str)
            ]
            if damage_type_l in perm:
                return damage_amount // 2, True
    # (2) Combatant-level buff resistances. Same dict-shaped
    # ``effects.resistance_to`` contract as PC ``_buffs_active`` buffs.
    for b in (combatant.get("buffs") or []):
        if not isinstance(b, dict):
            continue
        effects = b.get("effects")
        if not isinstance(effects, dict):
            continue
        resists = [str(r).strip().lower() for r in (effects.get("resistance_to") or [])]
        if damage_type_l in resists:
            return damage_amount // 2, True
    return damage_amount, False


@router.post("/api/campaign/{campaign_id}/use_arcane_recovery")
async def use_arcane_recovery(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Restore spell slots via the Wizard Lv 1 Arcane Recovery feature.

    Body: ``{character_id, slots: [{level: int, count: int}], override?}``.

    RAW: once per day during a short rest, restore spell slots whose
    combined level ≤ ⌈wizard_lv/2⌉. L6+ slots are not eligible. The
    ``slots`` array lets the caller spread the allowance across levels
    (e.g. ``[{level:1, count:2}, {level:2, count:1}]`` for 4 levels of
    allowance, sum = 1+1+2 = 4).

    Validates:
    - arcane-recovery resource is on the sheet and has at least 1 use left
    - Sum of (level × count) ≤ ⌈wizard_lv/2⌉
    - Each requested level has at least ``count`` slots currently used
    - No level >= 6 in the request (L6+ slots ineligible per RAW)

    Atomically decrements arcane-recovery + restores the slots + broadcasts
    spell_slot_update per slot level + resource_update + feature_used.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    slots_req = body.get("slots") or []
    if char_id <= 0:
        raise HTTPException(400, "character_id is required")
    if not isinstance(slots_req, list) or not slots_req:
        raise HTTPException(400, "slots is required (non-empty list)")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Wizard character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    wizard_lv = _wizard_level_from_sheet(sheet)
    if wizard_lv < 1:
        raise HTTPException(409, "Arcane Recovery requires Wizard level 1+")

    # Sum + validate the request shape. RAW allowance is ceil(wizard_lv/2).
    allowance = (wizard_lv + 1) // 2  # ceil(wizard_lv/2) via integer arithmetic
    total_levels = 0
    parsed_slots = []  # [(level, count), ...]
    for entry in slots_req:
        if not isinstance(entry, dict):
            raise HTTPException(400, "each slot entry must be an object")
        try:
            level = int(entry.get("level") or 0)
            count = int(entry.get("count") or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, "slot level and count must be integers")
        if level < 1 or level > 5:
            raise HTTPException(409, f"Arcane Recovery does not restore L{level} slots (L1-L5 only)")
        if count < 1:
            continue
        total_levels += level * count
        parsed_slots.append((level, count))

    if not parsed_slots:
        raise HTTPException(400, "slots request must restore at least 1 slot")
    if total_levels > allowance:
        return JSONResponse(status_code=409, content={
            "error": "exceeds_allowance",
            "requested": total_levels,
            "allowance": allowance,
        })

    # Verify arcane-recovery counter has uses left.
    resources = list(sheet.get("resources") or [])
    ar_idx = -1
    ar_row = None
    for i, r in enumerate(resources):
        if (r.get("key") or "").lower() == "arcane-recovery":
            ar_row = dict(r)
            ar_idx = i
            break
    if ar_row is None:
        raise HTTPException(404, "No Arcane Recovery resource on this sheet")
    ar_cur = int(ar_row.get("current") or 0)
    ar_max = int(ar_row.get("max") or 0)
    if ar_cur <= 0:
        return JSONResponse(status_code=409, content={
            "error": "out_of_uses",
            "label": "Arcane Recovery",
        })

    # Verify each requested level has enough used slots to restore.
    all_slots = dict(sheet.get("spell_slots") or {})
    # Wizard slots live under the 'wizard' class slug per the sheet schema.
    wiz_slots = dict(all_slots.get("wizard") or {})
    for level, count in parsed_slots:
        slot_key = str(level)
        slot = dict(wiz_slots.get(slot_key) or {})
        used = int(slot.get("used") or 0)
        if used < count:
            return JSONResponse(status_code=409, content={
                "error": "insufficient_used_slots",
                "level": level,
                "requested": count,
                "currently_used": used,
            })

    # Apply: decrement arcane-recovery counter, restore each slot's used.
    ar_row["current"] = ar_cur - 1
    resources[ar_idx] = ar_row
    sheet["resources"] = resources

    slot_updates = []  # for the WS broadcasts
    for level, count in parsed_slots:
        slot_key = str(level)
        slot = dict(wiz_slots.get(slot_key) or {})
        total = int(slot.get("total") or 0)
        used = int(slot.get("used") or 0)
        new_used = max(0, used - count)
        slot["used"] = new_used
        wiz_slots[slot_key] = slot
        slot_updates.append((level, total, new_used))
    all_slots["wizard"] = wiz_slots
    sheet["spell_slots"] = all_slots

    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    # Broadcasts.
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    # Per-slot spell_slot_update so any open sheet / mini-sheet re-pips.
    for level, total, new_used in slot_updates:
        try:
            await hub.broadcast(campaign_id, {
                "type": "spell_slot_update",
                "data": {
                    "character_id": char.id,
                    "class_slug": "wizard",
                    "level": level,
                    "total": total,
                    "used": new_used,
                },
            })
        except Exception:
            pass

    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id,
            "key": "arcane-recovery",
            "current": ar_cur - 1,
            "max": ar_max,
        },
    })

    # Compose a human-readable summary for the chat card.
    parts = [f"{c}× L{l}" for l, c in parsed_slots]
    summary = ", ".join(parts)
    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": f"🔮 Arcane Recovery → {summary}",
            "feature_desc": (
                f"Restored {total_levels} slot levels (allowance: {allowance}). "
                f"Arcane Recovery available again after a long rest."
            ),
            "source": "arcane-recovery",
            "remaining": ar_cur - 1,
            "max": ar_max,
            "over_budget": False,
            "over_budget_slot": "",
        },
    })

    return {
        "ok": True,
        "restored": [{"level": l, "count": c} for l, c in parsed_slots],
        "total_levels": total_levels,
        "allowance": allowance,
        "remaining": ar_cur - 1,
    }


# ----------- API: Second Wind (Fighter Lv 1) -----------

@router.post("/api/campaign/{campaign_id}/use_second_wind")
async def use_second_wind(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Spend a Second Wind use to heal 1d10 + fighter level HP.

    Body: ``{character_id, override?}``.

    RAW: Bonus action. Refreshes on a short or long rest. Heal amount
    scales linearly with fighter level (Lv 5 → 1d10+5 → 6-15 HP).
    Over-budget gate on the bonus slot per the Phase 4 (v2.6.1) pattern.

    Atomically decrements the second-wind counter, rolls the heal,
    applies HP via ``_apply_hp_change`` (so the death-save state
    machine wakes a dying fighter cleanly), marks the bonus slot,
    broadcasts feature_used + resource_update + character_death_save
    when applicable.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    override = bool(body.get("override"))
    if char_id <= 0:
        raise HTTPException(400, "character_id is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Fighter character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    fighter_lv = _fighter_level_from_sheet(sheet)
    if fighter_lv < 1:
        raise HTTPException(409, "Second Wind requires Fighter level 1+")

    # Verify second-wind counter has uses left.
    resources = list(sheet.get("resources") or [])
    sw_idx = -1
    sw_row = None
    for i, r in enumerate(resources):
        if (r.get("key") or "").lower() == "second-wind":
            sw_row = dict(r)
            sw_idx = i
            break
    if sw_row is None:
        raise HTTPException(404, "No Second Wind resource on this sheet")
    sw_cur = int(sw_row.get("current") or 0)
    sw_max = int(sw_row.get("max") or 0)
    if sw_cur <= 0:
        return JSONResponse(status_code=409, content={
            "error": "out_of_uses",
            "label": "Second Wind",
        })

    # Phase 4 over-budget gate (bonus slot).
    was_used = _is_slot_used(campaign_id, char.id, "bonus")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": "bonus",
            "char_name": char.name,
            "source": "second-wind",
            "label": "Second Wind",
            "strict": strict,
        })

    # Roll heal: 1d10 + fighter level (no CON mod per RAW).
    expr = f"1d10+{fighter_lv}"
    try:
        result = dice_mod.roll(expr)
        recovered = max(1, result.total)
        breakdown = result.breakdown
    except dice_mod.DiceParseError:
        recovered = 1
        breakdown = ""

    # Apply HP via _apply_hp_change so the death-save state machine
    # picks up a dying fighter waking up cleanly.
    hp = dict(sheet.get("hp") or {})
    hp_max = int(hp.get("max") or 0)
    hp_cur = int(hp.get("current") or 0)
    new_hp = min(hp_max, hp_cur + recovered) if hp_max > 0 else (hp_cur + recovered)

    # Decrement counter.
    sw_row["current"] = sw_cur - 1
    resources[sw_idx] = sw_row
    sheet["resources"] = resources
    char.sheet = sheet

    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    hp_result = _apply_hp_change(char, new_hp)
    db.commit()

    # Mark the bonus slot.
    await _mark_battle_economy(campaign_id, char.id, "bonus")

    # Broadcasts.
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    actual_healed = hp_result["hp"]["current"] - hp_cur

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": "💨 Second Wind",
            # v2.43.12: restore the dice-roll info inline. v2.43.0
            # dropped it to "Bonus action" when the heal pill landed,
            # but readers (esp. spectating players who can't see the
            # caster's HP delta on their own sheet) want the rolled
            # expression + raw total in the card body too. The heal
            # pill below carries the *applied* HP (capped at max);
            # this string carries what was *rolled* — they're different
            # numbers when the caster was near full HP.
            "feature_desc": f"Bonus action · rolled {expr} = {recovered}",
            # v2.35.0: dice fields so roll_toast.js fires the heal die
            # animation as a separate transient surface.
            "dice_expression": expr,
            "dice_total": recovered,
            "dice_breakdown": breakdown,
            "dice_note": "💨 Second Wind",
            # v2.43.0: heal_amount is the actual HP delta after the
            # max-HP cap (recovered may exceed it). Surfaced so the
            # client renders an oversized heal pill on the feature_used
            # card. Zero when Garrik was already at max HP.
            "heal_amount": actual_healed,
            "heal_target_name": char.name,
            "heal_hp_before": hp_cur,
            "heal_hp_after": hp_result["hp"]["current"],
            "source": "second-wind",
            "remaining": sw_cur - 1,
            "max": sw_max,
            "over_budget": was_used,
            "over_budget_slot": "bonus" if was_used else "",
        },
    })

    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id,
            "key": "second-wind",
            "current": sw_cur - 1,
            "max": sw_max,
        },
    })

    if hp_result.get("status_changed"):
        await hub.broadcast(campaign_id, {
            "type": "character_death_save",
            "data": {
                "character_id": char.id,
                "status": hp_result["death_saves"]["status"],
                "successes": int(hp_result["death_saves"]["successes"]),
                "failures": int(hp_result["death_saves"]["failures"]),
                "hp": hp_result["hp"],
                "source": "second_wind",
            },
        })

    return {
        "ok": True,
        "expression": expr,
        "rolled": recovered,
        "breakdown": breakdown,
        "actual_healed": actual_healed,
        "hp": hp_result["hp"],
        "remaining": sw_cur - 1,
        "over_budget": was_used,
    }


# ----------- API: Action Surge (Fighter Lv 2) -----------

@router.post("/api/campaign/{campaign_id}/use_action_surge")
async def use_action_surge(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Spend an Action Surge use to take one additional action this turn.

    Body: ``{character_id}``.

    RAW: "Once on your turn, you can take one additional action."
    Refreshes on a short or long rest. Costs no action / bonus /
    reaction — it GRANTS an extra action rather than consuming one
    (curated `_FEATURE_ECONOMY['action-surge'].slot = 'free'` —
    no over-budget gate).

    Mechanic: the fighter has already burned their Act chip on their
    normal action this turn. Action Surge undoes that — the helper
    `_mark_battle_economy(..., used=False)` clears the Act chip in
    the hub battle state and broadcasts ``economy_update`` so every
    client's chip strip refreshes. The fighter can now click another
    weapon / spell / feature on the same turn; that click will burn
    the Act chip again (auto-mark behavior), giving the "two actions
    this turn" feel.

    Validates: Fighter Lv 2+; action-surge counter has uses (409
    out_of_uses when depleted).
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    if char_id <= 0:
        raise HTTPException(400, "character_id is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Fighter character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    fighter_lv = _fighter_level_from_sheet(sheet)
    if fighter_lv < 2:
        raise HTTPException(409, "Action Surge requires Fighter level 2+")

    # Verify action-surge counter has uses.
    resources = list(sheet.get("resources") or [])
    as_idx = -1
    as_row = None
    for i, r in enumerate(resources):
        if (r.get("key") or "").lower() == "action-surge":
            as_row = dict(r)
            as_idx = i
            break
    if as_row is None:
        raise HTTPException(404, "No Action Surge resource on this sheet")
    as_cur = int(as_row.get("current") or 0)
    as_max = int(as_row.get("max") or 0)
    if as_cur <= 0:
        return JSONResponse(status_code=409, content={
            "error": "out_of_uses",
            "label": "Action Surge",
        })

    # Decrement counter.
    as_row["current"] = as_cur - 1
    resources[as_idx] = as_row
    sheet["resources"] = resources

    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    # Refund the action chip — Action Surge's whole point. v2.17.2's
    # _mark_battle_economy(..., used=False) handles the unmark + the
    # economy_update broadcast.
    await _mark_battle_economy(campaign_id, char.id, "action", used=False)

    # Broadcasts.
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": "⚡ Action Surge → +1 action this turn",
            "feature_desc": (
                "Action chip refunded. Take another weapon attack, "
                "cast a spell, or fire any other action — your "
                "normal Act for this turn is back."
            ),
            "source": "action-surge",
            "remaining": as_cur - 1,
            "max": as_max,
            "over_budget": False,
            "over_budget_slot": "",
        },
    })

    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id,
            "key": "action-surge",
            "current": as_cur - 1,
            "max": as_max,
        },
    })

    return {
        "ok": True,
        "remaining": as_cur - 1,
        "action_chip_refunded": True,
    }


# ----------- API: Rage (Barbarian Lv 1) -----------
#
# v2.19.0 Phase C.1: first user of the buff-slot infrastructure. Rage
# is the canonical test case for structured timed effects — damage
# bonus + advantage on STR + resistance to physical, all stamped onto
# the combatant for 10 rounds. The actual roll-time application of
# those effects waits on Phase B (the (B) roll-time intercept reads
# combatant.buffs and applies bonuses); this endpoint just installs
# the buff + decrements the Rage counter + marks the bonus chip.

@router.post("/api/campaign/{campaign_id}/use_rage")
async def use_rage(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Activate Rage — install the rage buff on the barbarian in the
    hub battle state + decrement the Rage counter + mark the bonus
    action chip.

    Body: ``{character_id, override?}``.

    RAW: Bonus action. While raging (max 1 minute / 10 rounds): +2
    damage on melee STR attacks (Lv 1-8; +3 at Lv 9-15, +4 at Lv 16+),
    advantage on STR checks and saves, resistance to bludgeoning /
    piercing / slashing. Ends early if KO'd or if turn ends without
    attacking or taking damage — v1 doesn't auto-detect the "no attack
    / no damage" branch; player ends it manually via the buff badge ×
    button (`/end_buff`).

    Validates Barbarian Lv 1+ (409 wrong_class), rage counter has uses
    (404 no resource / 409 out_of_uses). Phase 4 over-budget gate on
    the bonus slot per the v2.6.1 pattern.

    Broadcasts:
    - ``feature_used`` (rage announce + remaining counter)
    - ``resource_update`` (rage counter)
    - ``buff_update`` (rage buff appears on the barbarian's combatant)
    - ``economy_update`` (bonus chip flipped) via `_mark_battle_economy`
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    override = bool(body.get("override"))
    if char_id <= 0:
        raise HTTPException(400, "character_id is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Barbarian character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    barb_lv = _barbarian_level_from_sheet(sheet)
    if barb_lv < 1:
        raise HTTPException(409, "Rage requires Barbarian level 1+")

    # Verify rage counter has uses left.
    resources = list(sheet.get("resources") or [])
    rage_idx = -1
    rage_row = None
    for i, r in enumerate(resources):
        if (r.get("key") or "").lower() == "rage":
            rage_row = dict(r)
            rage_idx = i
            break
    if rage_row is None:
        raise HTTPException(404, "No Rage resource on this sheet")
    rage_cur = int(rage_row.get("current") or 0)
    rage_max = int(rage_row.get("max") or 0)
    if rage_cur <= 0:
        return JSONResponse(status_code=409, content={
            "error": "out_of_uses",
            "label": "Rage",
        })

    # Phase 4 over-budget gate (bonus slot).
    was_used = _is_slot_used(campaign_id, char.id, "bonus")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": "bonus",
            "char_name": char.name,
            "source": "rage",
            "label": "Rage",
            "strict": strict,
        })

    # Decrement counter.
    rage_row["current"] = rage_cur - 1
    resources[rage_idx] = rage_row
    sheet["resources"] = resources

    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    # Install the rage buff on the barbarian's combatant. ``effects`` is
    # informational — (B) Phase B roll-time intercept will read these
    # fields when applying the rage damage bonus / advantage flags /
    # resistance.
    damage_bonus = _rage_damage_bonus(barb_lv)
    buff = {
        "key": "rage",
        "name": "Rage",
        "icon": "🦬",
        "source_caster_id": None,   # filled by C.2 with combatant id
        "target_combatant_id": None,
        "duration_rounds": 10,
        "duration_max": 10,
        "concentration": False,
        "effects": {
            "melee_str_damage_bonus": damage_bonus,
            "advantage_on": ["str_check", "str_save", "str_attack"],
            "resistance_to": ["bludgeoning", "piercing", "slashing"],
        },
        "desc": (
            f"+{damage_bonus} damage on melee STR attacks, advantage on STR "
            f"checks / saves, resistance to bludgeoning / piercing / slashing. "
            f"Lasts 10 rounds or until ended early."
        ),
    }
    installed = await _install_buff(campaign_id, char.id, buff)

    # v2.19.2 Phase C.3: mirror to char.sheet["_buffs_active"] so the
    # full sheet's Active Effects panel renders Rage even when the
    # init tracker isn't open.
    _mirror_buffs_to_sheet(db, char.id, _get_buffs(campaign_id, char.id))

    # Mark the bonus slot.
    await _mark_battle_economy(campaign_id, char.id, "bonus")

    # Broadcasts.
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": f"🦬 Rage activated (+{damage_bonus} dmg, 10 rounds)",
            "feature_desc": (
                f"Bonus action. +{damage_bonus} damage on melee STR attacks, "
                f"advantage on STR checks / saves, resistance to physical "
                f"damage. Ends in 10 rounds or when turn ends without "
                f"attacking / taking damage."
            ),
            "source": "rage",
            "remaining": rage_cur - 1,
            "max": rage_max,
            "over_budget": was_used,
            "over_budget_slot": "bonus" if was_used else "",
        },
    })

    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id,
            "key": "rage",
            "current": rage_cur - 1,
            "max": rage_max,
        },
    })

    return {
        "ok": True,
        "remaining": rage_cur - 1,
        "max": rage_max,
        "damage_bonus": damage_bonus,
        "duration_rounds": 10,
        "buff_installed": installed,
    }


# ----------- API: Stunning Strike (Monk Lv5+) -----------

@router.post("/api/campaign/{campaign_id}/use_stunning_strike")
async def use_stunning_strike(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Monk class feature (Lv 5+): spend 1 ki on a hit to force the
    target to make a CON save or be Stunned until the end of the
    monk's next turn.

    Body: ``{character_id, target_combatant_id?, target_character_id?,
            target_name?}``. RAW Stunning Strike piggybacks on a melee
    weapon hit; it's a free interrupt (no action / bonus / reaction
    slot consumed) but costs 1 ki. Save DC = 8 + monk prof + monk WIS
    mod.

    Routes through the same save-or-suck pipeline as ``cast_spell``:
    NPC targets get a server-rolled save and immediate buff install
    on fail; PC targets get a ``roll_request`` prompt and the
    ``/roll_request/{id}/respond`` handler installs Stunned on fail
    via the ``_SPELL_CONDITION_MAP[stunning-strike]`` entry. The
    Stunned buff is concentration=False — exercises the v2.49.51
    incapacitation hook for non-concentration incapacitating buffs.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    target_combatant_id = (body.get("target_combatant_id") or "").strip()
    target_character_id_in = body.get("target_character_id")
    if target_character_id_in is not None:
        target_character_id_in = int(target_character_id_in)
    target_name_in = (body.get("target_name") or "").strip()

    if char_id <= 0:
        raise HTTPException(400, "character_id is required")
    if not target_combatant_id and not target_character_id_in:
        raise HTTPException(400, "target_combatant_id or target_character_id is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Monk character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})

    # Class + level validation.
    cls = (sheet.get("class") or "").lower()
    if cls != "monk":
        return JSONResponse(status_code=409, content={
            "error": "wrong_class",
            "expected": "monk",
            "got": cls or "",
        })
    level = int(sheet.get("level") or 1)
    if level < 5:
        return JSONResponse(status_code=409, content={
            "error": "level_too_low",
            "required": 5,
            "got": level,
        })

    # Ki resource lookup.
    resources = list(sheet.get("resources") or [])
    ki_row = None
    ki_idx = -1
    for i, r in enumerate(resources):
        if (r.get("key") or "").lower() == "ki":
            ki_row = dict(r)
            ki_idx = i
            break
    if ki_row is None:
        raise HTTPException(404, "No Ki resource on this sheet")
    ki_cur = int(ki_row.get("current") or 0)
    ki_max = int(ki_row.get("max") or 0)
    if ki_cur < 1:
        return JSONResponse(status_code=409, content={
            "error": "no_ki",
            "available": ki_cur,
        })

    # Resolve target.
    target_combatant = (
        _lookup_combatant(campaign_id, target_combatant_id)
        if target_combatant_id else None
    )
    if not target_combatant and target_character_id_in:
        target_combatant = {
            "char_id": target_character_id_in,
            "id": target_combatant_id or "",
            "name": target_name_in or "",
        }
    if not target_combatant:
        raise HTTPException(404, "Target combatant not found")

    # v2.49.76 — Phase 2D range-enforcement gate. Stunning Strike is
    # melee (RAW: "When you hit another creature with a melee weapon
    # attack"); 5 ft reach. Fires before ki is consumed.
    _override_range = bool(body.get("override_range"))
    _user_is_gm_for_range = _user_is_gm(user, campaign, db)
    _strict_for_range = bool(campaign.strict_action_economy)
    _range_err = _check_cast_range(
        db, campaign, char,
        "5 feet", "Stunning Strike",
        target_combatant_id, target_character_id_in, target_name_in,
        override_range=_override_range,
        user_is_gm=_user_is_gm_for_range,
        strict=_strict_for_range,
    )
    if _range_err:
        return JSONResponse(status_code=409, content=_range_err)

    # Save DC = 8 + monk prof + WIS mod.
    prof = int(sheet.get("proficiency_bonus") or 2)
    wis = int((sheet.get("abilities") or {}).get("WIS", 10))
    wis_mod = (wis - 10) // 2
    save_dc = 8 + prof + wis_mod

    # Spend the ki BEFORE rolling so it's consumed regardless of outcome.
    ki_row["current"] = ki_cur - 1
    resources[ki_idx] = ki_row
    sheet["resources"] = resources
    char.sheet = sheet
    db.commit()
    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id,
            "key": "ki",
            "current": ki_cur - 1,
            "max": ki_max,
        },
    })

    tgt_char_id = target_combatant.get("char_id")
    note_label = "Stunning Strike — CON save"
    stat_key = "con_save"
    auto_save_target_kind = ""
    auto_save_prompted = False
    auto_save_prompt_id = 0
    auto_save_rolled = None
    auto_save_passed: Optional[bool] = None
    auto_save_breakdown = ""
    auto_save_buff_installed = ""

    tgt_char = None
    if tgt_char_id:
        tgt_char = db.query(Character).filter(
            Character.id == int(tgt_char_id),
            Character.campaign_id == campaign_id,
        ).first()

    if tgt_char and tgt_char.owner_user_id:
        # PC target: roll_request flow. The /respond handler will
        # install Stunned on save fail via _SPELL_CONDITION_MAP lookup.
        auto_save_target_kind = "pc"
        req = RollRequest(
            campaign_id=campaign_id,
            created_by_user_id=user.id,
            label=note_label,
            base_expression="1d20",
            stat_key=stat_key,
            dc=save_dc,
            visibility=Visibility.PUBLIC,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        await hub.broadcast(campaign_id, {
            "type": "roll_request",
            "data": {
                "id": req.id,
                "label": req.label,
                "stat_key": req.stat_key,
                "base_expression": req.base_expression,
                "dc": req.dc,
                "visibility": req.visibility.value,
                "created_by_name": user.display_name,
                "created_by_user_id": user.id,
                "target_user_ids": [tgt_char.owner_user_id],
                "target_user_names": [tgt_char.name],
            },
        })
        auto_save_prompted = True
        auto_save_prompt_id = req.id
        _purge_save_request_context()
        _save_request_context[req.id] = {
            "ts": _time.time(),
            "campaign_id": campaign_id,
            "spell_slug": "stunning-strike",
            "spell_name": "Stunning Strike",
            "target_character_id": int(tgt_char.id),
            "target_name": tgt_char.name,
            "dc": int(save_dc),
            "save_ability": "CON",
            "caster_char_id": int(char.id),
            "caster_char_name": char.name,
        }
    elif target_combatant.get("token_template_id"):
        # NPC target: server rolls the save inline.
        auto_save_target_kind = "npc"
        tmpl = db.query(TokenTemplate).filter(
            TokenTemplate.id == int(target_combatant["token_template_id"]),
        ).first()
        if tmpl:
            npc_sheet = _monster_template_to_sheet(tmpl, campaign_id)
            npc_mod, _ = _resolve_stat_modifier(npc_sheet, "dnd5e", stat_key)
            expr = f"1d20{npc_mod:+d}"
            try:
                _r = dice_mod.roll(expr)
                auto_save_rolled = int(_r.total)
                auto_save_breakdown = _r.breakdown
            except dice_mod.DiceParseError:
                auto_save_rolled = 0
                auto_save_breakdown = ""
            auto_save_passed = auto_save_rolled >= save_dc
            await hub.broadcast(campaign_id, {
                "type": "roll",
                "data": {
                    "expression": expr,
                    "total": auto_save_rolled,
                    "breakdown": auto_save_breakdown,
                    "note": note_label,
                    "user_name": target_combatant.get("name", ""),
                    "char_name": target_combatant.get("name", ""),
                    "visibility": Visibility.PUBLIC.value,
                    "dc": save_dc,
                },
            })
            if not auto_save_passed:
                cond = _SPELL_CONDITION_MAP["stunning-strike"]
                buff = {
                    "key": cond["key"],
                    "name": cond["name"],
                    "icon": cond.get("icon", "✨"),
                    "source_char_id": char.id,
                    "source_char_name": char.name,
                    "source_spell": "Stunning Strike",
                    "duration_rounds": int(cond.get("duration_rounds", 1)),
                    "duration_max": int(cond.get("duration_rounds", 1)),
                    "concentration": bool(cond.get("concentration", False)),
                    "effects": list(cond.get("effects", [])),
                }
                installed = await _install_buff_on_combatant_id(
                    campaign_id, target_combatant.get("id"), buff,
                )
                if installed:
                    auto_save_buff_installed = cond["name"]

    return {
        "ok": True,
        "ki_remaining": ki_cur - 1,
        "save_dc": save_dc,
        "auto_save_target_kind": auto_save_target_kind,
        "auto_save_prompted": auto_save_prompted,
        "auto_save_prompt_id": auto_save_prompt_id,
        "auto_save_rolled": auto_save_rolled,
        "auto_save_passed": auto_save_passed,
        "auto_save_breakdown": auto_save_breakdown,
        "auto_save_buff_installed": auto_save_buff_installed,
    }


# ----------- API: Open Hand Technique (Monk Way of the Open Hand Lv3+) -----------

@router.post("/api/campaign/{campaign_id}/use_open_hand_technique")
async def use_open_hand_technique(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Monk subclass feature (Way of the Open Hand, Lv 3+).

    RAW: "Whenever you hit a creature with one of the attacks granted
    by your Flurry of Blows, you can impose one of the following
    effects on that target:

      - It must succeed on a Dexterity saving throw or be knocked prone.
      - It must make a Strength saving throw. If it fails, you can push
        it up to 15 feet away from you.
      - It can't take reactions until the end of your next turn."

    Body: ``{character_id, target_combatant_id?, target_character_id?,
            target_name?, mode}`` where ``mode`` is one of ``prone``,
    ``push``, ``no_reactions``.

    No additional cost — the Flurry of Blows ki already paid. RAW
    requires this to follow a Flurry hit; the endpoint trusts the
    caller (same convention as ``/use_stunning_strike``), and the UI
    is expected to surface the button only after a Flurry hit lands.

    Three flows:
      - ``no_reactions``: no save, install ``reaction-denied`` buff on
        the target inline (concentration=False, 1 turn). Mirrors the
        no-save inline-install path in ``/use_rage`` / ``/use_bardic_inspiration``.
      - ``prone``: DEX save vs DC 8 + monk prof + WIS mod. On fail
        install Prone via ``_SPELL_CONDITION_MAP['open-hand-prone']``.
        Routes through the same save-or-suck pipeline as
        ``/use_stunning_strike`` — PC target gets a roll_request,
        NPC target gets a server-rolled save inline.
      - ``push``: STR save vs the same DC. No buff to install — the
        response carries ``push_authorized`` (True on save fail, False
        on pass) so the GM UI can prompt to drag the token up to 15 ft
        away. PC target gets the roll_request and the GM observes the
        save result in the roll log; NPC target gets server-rolled
        and the response carries the verdict immediately.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    target_combatant_id = (body.get("target_combatant_id") or "").strip()
    target_character_id_in = body.get("target_character_id")
    if target_character_id_in is not None:
        target_character_id_in = int(target_character_id_in)
    target_name_in = (body.get("target_name") or "").strip()
    mode = (body.get("mode") or "").strip().lower()

    if char_id <= 0:
        raise HTTPException(400, "character_id is required")
    if mode not in ("prone", "push", "no_reactions"):
        raise HTTPException(400, "mode must be one of prone, push, no_reactions")
    if not target_combatant_id and not target_character_id_in:
        raise HTTPException(400, "target_combatant_id or target_character_id is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Monk character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})

    # Class + subclass + level validation.
    cls = (sheet.get("class") or "").lower()
    if cls != "monk":
        return JSONResponse(status_code=409, content={
            "error": "wrong_class",
            "expected": "monk",
            "got": cls or "",
        })
    subclass = (sheet.get("subclass") or "").lower()
    if "open hand" not in subclass:
        return JSONResponse(status_code=409, content={
            "error": "wrong_subclass",
            "expected": "way of the open hand",
            "got": sheet.get("subclass") or "",
        })
    level = int(sheet.get("level") or 1)
    if level < 3:
        return JSONResponse(status_code=409, content={
            "error": "level_too_low",
            "required": 3,
            "got": level,
        })

    # Resolve target.
    target_combatant = (
        _lookup_combatant(campaign_id, target_combatant_id)
        if target_combatant_id else None
    )
    if not target_combatant and target_character_id_in:
        target_combatant = {
            "char_id": target_character_id_in,
            "id": target_combatant_id or "",
            "name": target_name_in or "",
        }
    if not target_combatant:
        raise HTTPException(404, "Target combatant not found")

    # v2.49.76 — Phase 2D range-enforcement gate. Open Hand Technique
    # rides on a Flurry of Blows attack (RAW melee), so 5 ft reach.
    # Fires before any state mutation.
    _override_range_oht = bool(body.get("override_range"))
    _user_is_gm_for_range_oht = _user_is_gm(user, campaign, db)
    _strict_for_range_oht = bool(campaign.strict_action_economy)
    _range_err_oht = _check_cast_range(
        db, campaign, char,
        "5 feet", "Open Hand Technique",
        target_combatant_id, target_character_id_in, target_name_in,
        override_range=_override_range_oht,
        user_is_gm=_user_is_gm_for_range_oht,
        strict=_strict_for_range_oht,
    )
    if _range_err_oht:
        return JSONResponse(status_code=409, content=_range_err_oht)

    # ---- no_reactions: no save, install inline. ----
    if mode == "no_reactions":
        buff = {
            "key": "reaction-denied",
            "name": "No Reactions (Open Hand)",
            "icon": "🚫",
            "source_char_id": char.id,
            "source_char_name": char.name,
            "source_spell": "Open Hand Technique",
            "duration_rounds": 1,
            "duration_max": 1,
            "concentration": False,
            "effects": [
                "can't take reactions until end of monk's next turn",
            ],
        }
        installed_name = ""
        tgt_char_id = target_combatant.get("char_id")
        tgt_char = None
        if tgt_char_id:
            tgt_char = db.query(Character).filter(
                Character.id == int(tgt_char_id),
                Character.campaign_id == campaign_id,
            ).first()
        if tgt_char and tgt_char.owner_user_id:
            ok = await _install_buff(campaign_id, int(tgt_char.id), buff)
            if ok:
                installed_name = buff["name"]
                _mirror_buffs_to_sheet(
                    db, int(tgt_char.id),
                    _get_buffs(campaign_id, int(tgt_char.id)),
                )
        else:
            ok = await _install_buff_on_combatant_id(
                campaign_id, target_combatant.get("id"), buff,
            )
            if ok:
                installed_name = buff["name"]
        # Public roll-log entry so everyone sees the rider land.
        await hub.broadcast(campaign_id, {
            "type": "roll",
            "data": {
                "expression": "—",
                "total": 0,
                "breakdown": "Open Hand Technique: no reactions until end of monk's next turn",
                "note": f"🫷 {char.name} → {target_combatant.get('name') or 'target'}: No Reactions",
                "user_name": char.name,
                "char_name": char.name,
                "visibility": Visibility.PUBLIC.value,
            },
        })
        return {
            "ok": True,
            "mode": "no_reactions",
            "auto_save_target_kind": "pc" if (tgt_char and tgt_char.owner_user_id) else "npc",
            "auto_save_prompted": False,
            "buff_installed": installed_name,
        }

    # ---- prone / push: save vs DC 8 + prof + WIS mod. ----
    prof = int(sheet.get("proficiency_bonus") or 2)
    wis = int((sheet.get("abilities") or {}).get("WIS", 10))
    wis_mod = (wis - 10) // 2
    save_dc = 8 + prof + wis_mod

    if mode == "prone":
        stat_key = "dex_save"
        note_label = "Open Hand Technique — DEX save (prone)"
        spell_slug = "open-hand-prone"
        spell_name = "Open Hand Technique (Prone)"
    else:  # push
        stat_key = "str_save"
        note_label = "Open Hand Technique — STR save (push 15 ft)"
        spell_slug = "open-hand-push"  # NOT in _SPELL_CONDITION_MAP — no buff installs
        spell_name = "Open Hand Technique (Push)"

    tgt_char_id = target_combatant.get("char_id")
    auto_save_target_kind = ""
    auto_save_prompted = False
    auto_save_prompt_id = 0
    auto_save_rolled: Optional[int] = None
    auto_save_passed: Optional[bool] = None
    auto_save_breakdown = ""
    auto_save_buff_installed = ""
    push_authorized: Optional[bool] = None

    tgt_char = None
    if tgt_char_id:
        tgt_char = db.query(Character).filter(
            Character.id == int(tgt_char_id),
            Character.campaign_id == campaign_id,
        ).first()

    if tgt_char and tgt_char.owner_user_id:
        # PC target: roll_request. /respond installs the Prone buff
        # (prone mode) via _SPELL_CONDITION_MAP; push mode has no map
        # entry so /respond's install branch is a no-op and the GM
        # observes the save result in the log.
        auto_save_target_kind = "pc"
        req = RollRequest(
            campaign_id=campaign_id,
            created_by_user_id=user.id,
            label=note_label,
            base_expression="1d20",
            stat_key=stat_key,
            dc=save_dc,
            visibility=Visibility.PUBLIC,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        await hub.broadcast(campaign_id, {
            "type": "roll_request",
            "data": {
                "id": req.id,
                "label": req.label,
                "stat_key": req.stat_key,
                "base_expression": req.base_expression,
                "dc": req.dc,
                "visibility": req.visibility.value,
                "created_by_name": user.display_name,
                "created_by_user_id": user.id,
                "target_user_ids": [tgt_char.owner_user_id],
                "target_user_names": [tgt_char.name],
            },
        })
        auto_save_prompted = True
        auto_save_prompt_id = req.id
        _purge_save_request_context()
        _save_request_context[req.id] = {
            "ts": _time.time(),
            "campaign_id": campaign_id,
            "spell_slug": spell_slug,
            "spell_name": spell_name,
            "target_character_id": int(tgt_char.id),
            "target_name": tgt_char.name,
            "dc": int(save_dc),
            "save_ability": "DEX" if mode == "prone" else "STR",
            "caster_char_id": int(char.id),
            "caster_char_name": char.name,
        }
    elif target_combatant.get("token_template_id"):
        # NPC target: server rolls inline.
        auto_save_target_kind = "npc"
        tmpl = db.query(TokenTemplate).filter(
            TokenTemplate.id == int(target_combatant["token_template_id"]),
        ).first()
        if tmpl:
            npc_sheet = _monster_template_to_sheet(tmpl, campaign_id)
            npc_mod, _ = _resolve_stat_modifier(npc_sheet, "dnd5e", stat_key)
            expr = f"1d20{npc_mod:+d}"
            try:
                _r = dice_mod.roll(expr)
                auto_save_rolled = int(_r.total)
                auto_save_breakdown = _r.breakdown
            except dice_mod.DiceParseError:
                auto_save_rolled = 0
                auto_save_breakdown = ""
            auto_save_passed = auto_save_rolled >= save_dc
            await hub.broadcast(campaign_id, {
                "type": "roll",
                "data": {
                    "expression": expr,
                    "total": auto_save_rolled,
                    "breakdown": auto_save_breakdown,
                    "note": note_label,
                    "user_name": target_combatant.get("name", ""),
                    "char_name": target_combatant.get("name", ""),
                    "visibility": Visibility.PUBLIC.value,
                    "dc": save_dc,
                },
            })
            if not auto_save_passed:
                if mode == "prone":
                    cond = _SPELL_CONDITION_MAP["open-hand-prone"]
                    buff = {
                        "key": cond["key"],
                        "name": cond["name"],
                        "icon": cond.get("icon", "🫳"),
                        "source_char_id": char.id,
                        "source_char_name": char.name,
                        "source_spell": "Open Hand Technique",
                        "duration_rounds": int(cond.get("duration_rounds", 10)),
                        "duration_max": int(cond.get("duration_rounds", 10)),
                        "concentration": bool(cond.get("concentration", False)),
                        "effects": list(cond.get("effects", [])),
                    }
                    installed = await _install_buff_on_combatant_id(
                        campaign_id, target_combatant.get("id"), buff,
                    )
                    if installed:
                        auto_save_buff_installed = cond["name"]
                else:  # push
                    push_authorized = True
            else:
                if mode == "push":
                    push_authorized = False

    return {
        "ok": True,
        "mode": mode,
        "save_dc": save_dc,
        "auto_save_target_kind": auto_save_target_kind,
        "auto_save_prompted": auto_save_prompted,
        "auto_save_prompt_id": auto_save_prompt_id,
        "auto_save_rolled": auto_save_rolled,
        "auto_save_passed": auto_save_passed,
        "auto_save_breakdown": auto_save_breakdown,
        "auto_save_buff_installed": auto_save_buff_installed,
        "push_authorized": push_authorized,
    }


# ----------- API: Patient Defense (Monk Lv 2+ Ki spend-option) -----------

@router.post("/api/campaign/{campaign_id}/use_patient_defense")
async def use_patient_defense(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Monk class feature (Lv 2+): spend 1 ki point as a bonus action
    to take the Dodge action. Until the start of the monk's next turn,
    any attack roll made against the monk with an attacker the monk
    can see has disadvantage, and the monk makes DEX saves with
    advantage.

    Body: ``{character_id, override?}``. No target — self-buff.

    Validates Monk Lv 2+ (409 ``level_too_low`` / ``wrong_class``),
    ki resource has at least 1 use (409 ``no_ki``). Phase 4 over-budget
    gate on the bonus slot per the Rage pattern (v2.49.112 follows
    the Rage / Action Surge precedent for bonus-action validation).

    Broadcasts:
    - ``resource_update`` (ki counter decremented)
    - ``buff_update`` (Dodging buff installed on the monk's combatant)
    - ``feature_used`` (roll-log card with name + remaining ki)
    - ``economy_update`` (bonus chip flipped) via _mark_battle_economy
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    override = bool(body.get("override"))
    if char_id <= 0:
        raise HTTPException(400, "character_id is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Monk character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})

    # Class + level validation. Patient Defense unlocks at Monk Lv 2
    # alongside Ki itself.
    cls = (sheet.get("class") or "").lower()
    if cls != "monk":
        return JSONResponse(status_code=409, content={
            "error": "wrong_class", "expected": "monk", "got": cls or "",
        })
    level = int(sheet.get("level") or 1)
    if level < 2:
        return JSONResponse(status_code=409, content={
            "error": "level_too_low", "required": 2, "got": level,
        })

    # Ki resource lookup + spend.
    resources = list(sheet.get("resources") or [])
    ki_row = None
    ki_idx = -1
    for i, r in enumerate(resources):
        if (r.get("key") or "").lower() == "ki":
            ki_row = dict(r); ki_idx = i; break
    if ki_row is None:
        raise HTTPException(404, "No Ki resource on this sheet")
    ki_cur = int(ki_row.get("current") or 0)
    ki_max = int(ki_row.get("max") or 0)
    if ki_cur < 1:
        return JSONResponse(status_code=409, content={
            "error": "no_ki", "available": ki_cur,
        })

    # Phase 4 over-budget gate (bonus slot).
    was_used = _is_slot_used(campaign_id, char.id, "bonus")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget", "slot": "bonus",
            "char_name": char.name, "source": "patient-defense",
            "label": "Patient Defense", "strict": strict,
        })

    # Spend the ki.
    ki_row["current"] = ki_cur - 1
    resources[ki_idx] = ki_row
    sheet["resources"] = resources
    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    # Install the Dodging buff on the monk's combatant. RAW lasts
    # "until the start of your next turn" → 1 round. The (B) roll-time
    # intercept reads ``dodging`` to grant disadvantage on attacks
    # against this combatant + advantage on the combatant's DEX saves.
    buff = {
        "key": "patient-defense",
        "name": "Patient Defense (Dodging)",
        "icon": "🛡",
        "source_caster_id": None,
        "target_combatant_id": None,
        "duration_rounds": 1,
        "duration_max": 1,
        "concentration": False,
        "effects": {
            "dodging": True,
            "advantage_on": ["dex_save"],
            "incoming_attacks_have_disadvantage": True,
        },
        "desc": (
            "Attackers have disadvantage against you (if you can see them); "
            "advantage on DEX saves. Lasts until the start of your next turn."
        ),
    }
    installed = await _install_buff(campaign_id, char.id, buff)
    _mirror_buffs_to_sheet(db, char.id, _get_buffs(campaign_id, char.id))
    await _mark_battle_economy(campaign_id, char.id, "bonus")

    # Broadcasts.
    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "feature_name": "🛡 Patient Defense — Dodging",
            "feature_desc": (
                "Bonus action, 1 ki. Attackers have disadvantage; DEX saves "
                "with advantage. Lasts until start of next turn."
            ),
            "source": "patient-defense",
            "remaining": ki_cur - 1,
            "max": ki_max,
            "over_budget": was_used,
            "over_budget_slot": "bonus" if was_used else "",
        },
    })
    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id, "key": "ki",
            "current": ki_cur - 1, "max": ki_max,
        },
    })

    return {
        "ok": True,
        "remaining": ki_cur - 1,
        "max": ki_max,
        "duration_rounds": 1,
        "buff_installed": installed,
    }


# ----------- API: Step of the Wind (Monk Lv 2+ Ki spend-option) -----------

@router.post("/api/campaign/{campaign_id}/use_step_of_the_wind")
async def use_step_of_the_wind(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Monk class feature (Lv 2+): spend 1 ki point as a bonus action
    to take the Disengage OR Dash action; jump distance is doubled
    for the turn.

    Body: ``{character_id, mode: "disengage" | "dash", override?}``.
    No target — self-buff. ``mode`` defaults to "disengage" if absent.

    The two modes install differently-shaped buffs so the (B) roll-
    time intercept + the movement-tracker code path can read the
    right effect. Both share the same Ki cost + bonus-action slot.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    mode = (body.get("mode") or "disengage").strip().lower()
    override = bool(body.get("override"))
    if mode not in ("disengage", "dash"):
        raise HTTPException(400, "mode must be 'disengage' or 'dash'")
    if char_id <= 0:
        raise HTTPException(400, "character_id is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Monk character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    cls = (sheet.get("class") or "").lower()
    if cls != "monk":
        return JSONResponse(status_code=409, content={
            "error": "wrong_class", "expected": "monk", "got": cls or "",
        })
    level = int(sheet.get("level") or 1)
    if level < 2:
        return JSONResponse(status_code=409, content={
            "error": "level_too_low", "required": 2, "got": level,
        })

    # Ki resource lookup + spend.
    resources = list(sheet.get("resources") or [])
    ki_row = None
    ki_idx = -1
    for i, r in enumerate(resources):
        if (r.get("key") or "").lower() == "ki":
            ki_row = dict(r); ki_idx = i; break
    if ki_row is None:
        raise HTTPException(404, "No Ki resource on this sheet")
    ki_cur = int(ki_row.get("current") or 0)
    ki_max = int(ki_row.get("max") or 0)
    if ki_cur < 1:
        return JSONResponse(status_code=409, content={
            "error": "no_ki", "available": ki_cur,
        })

    # Phase 4 over-budget gate (bonus slot).
    was_used = _is_slot_used(campaign_id, char.id, "bonus")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget", "slot": "bonus",
            "char_name": char.name, "source": "step-of-the-wind",
            "label": "Step of the Wind", "strict": strict,
        })

    ki_row["current"] = ki_cur - 1
    resources[ki_idx] = ki_row
    sheet["resources"] = resources
    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    # Mode-specific buff. Both share the doubled-jump rider; the
    # action-equivalent (disengage vs dash) drives the (B) intercept
    # + the movement-tracker code path. Duration is "rest of turn"
    # which we encode as 1 round (auto-expires at next turn end).
    if mode == "disengage":
        buff_key = "step-of-the-wind-disengage"
        buff_name = "Step of the Wind (Disengage)"
        icon = "💨"
        effects = {
            "disengage": True,
            "jump_distance_doubled": True,
        }
        desc = (
            "Bonus action, 1 ki. Movement does not provoke opportunity "
            "attacks this turn; jump distance is doubled."
        )
    else:  # dash
        buff_key = "step-of-the-wind-dash"
        buff_name = "Step of the Wind (Dash)"
        icon = "💨"
        effects = {
            "dash": True,
            "jump_distance_doubled": True,
        }
        desc = (
            "Bonus action, 1 ki. Speed is doubled this turn; jump distance "
            "is also doubled."
        )

    buff = {
        "key": buff_key,
        "name": buff_name,
        "icon": icon,
        "source_caster_id": None,
        "target_combatant_id": None,
        "duration_rounds": 1,
        "duration_max": 1,
        "concentration": False,
        "effects": effects,
        "desc": desc,
    }
    installed = await _install_buff(campaign_id, char.id, buff)
    _mirror_buffs_to_sheet(db, char.id, _get_buffs(campaign_id, char.id))
    await _mark_battle_economy(campaign_id, char.id, "bonus")

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "feature_name": f"{icon} Step of the Wind — {mode.capitalize()}",
            "feature_desc": desc,
            "source": "step-of-the-wind",
            "remaining": ki_cur - 1,
            "max": ki_max,
            "over_budget": was_used,
            "over_budget_slot": "bonus" if was_used else "",
        },
    })
    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id, "key": "ki",
            "current": ki_cur - 1, "max": ki_max,
        },
    })

    return {
        "ok": True,
        "mode": mode,
        "remaining": ki_cur - 1,
        "max": ki_max,
        "duration_rounds": 1,
        "buff_installed": installed,
    }


# ----------- API: Flurry of Blows (Monk Lv 2+ Ki spend-option) -----------

@router.post("/api/campaign/{campaign_id}/use_flurry_of_blows")
async def use_flurry_of_blows(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Monk class feature (Lv 2+): immediately after the Attack action,
    spend 1 ki as a bonus action to grant yourself two unarmed strikes.

    Body: ``{character_id, override?}``. No target — self-buff. The
    actual unarmed-strike rolls happen via the player's regular
    weapon-attack click on their Unarmed Strike attack; this endpoint
    installs the `flurry-of-blows-active` buff that signals "you have
    two extra unarmed strikes available this turn" + decrements ki +
    marks the bonus slot.

    The buff's ``effects.unarmed_strikes_available: 2`` is informational
    for v1 — the v2.49.57 Open Hand Technique endpoint (which RAW
    requires a Flurry hit as its trigger) can read this flag in a
    future commit to gate the prone/push/no-reactions options.

    Mirrors v2.49.112's Patient Defense + Step of the Wind: same
    Phase 4 over-budget gate on the bonus slot, same broadcast set
    (feature_used + resource_update + buff_update), same one-round
    duration.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    override = bool(body.get("override"))
    if char_id <= 0:
        raise HTTPException(400, "character_id is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Monk character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    cls = (sheet.get("class") or "").lower()
    if cls != "monk":
        return JSONResponse(status_code=409, content={
            "error": "wrong_class", "expected": "monk", "got": cls or "",
        })
    level = int(sheet.get("level") or 1)
    if level < 2:
        return JSONResponse(status_code=409, content={
            "error": "level_too_low", "required": 2, "got": level,
        })

    # Ki resource lookup + spend.
    resources = list(sheet.get("resources") or [])
    ki_row = None
    ki_idx = -1
    for i, r in enumerate(resources):
        if (r.get("key") or "").lower() == "ki":
            ki_row = dict(r); ki_idx = i; break
    if ki_row is None:
        raise HTTPException(404, "No Ki resource on this sheet")
    ki_cur = int(ki_row.get("current") or 0)
    ki_max = int(ki_row.get("max") or 0)
    if ki_cur < 1:
        return JSONResponse(status_code=409, content={
            "error": "no_ki", "available": ki_cur,
        })

    # Phase 4 over-budget gate (bonus slot).
    was_used = _is_slot_used(campaign_id, char.id, "bonus")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget", "slot": "bonus",
            "char_name": char.name, "source": "flurry-of-blows",
            "label": "Flurry of Blows", "strict": strict,
        })

    ki_row["current"] = ki_cur - 1
    resources[ki_idx] = ki_row
    sheet["resources"] = resources
    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    # Install the Flurry buff. ``unarmed_strikes_available: 2`` is the
    # signal a future commit will read to (a) refund the attack chip
    # for the next two unarmed strikes, and (b) gate the v2.49.57 Open
    # Hand Technique trigger ("after Flurry hit").
    buff = {
        "key": "flurry-of-blows-active",
        "name": "Flurry of Blows",
        "icon": "🥊",
        "source_caster_id": None,
        "target_combatant_id": None,
        "duration_rounds": 1,
        "duration_max": 1,
        "concentration": False,
        "effects": {
            "unarmed_strikes_available": 2,
            "is_flurry": True,
        },
        "desc": (
            "Bonus action, 1 ki. Two unarmed strikes available this turn. "
            "Open Hand Technique (Lv 3+ Way of the Open Hand) can chain off "
            "a Flurry hit."
        ),
    }
    installed = await _install_buff(campaign_id, char.id, buff)
    _mirror_buffs_to_sheet(db, char.id, _get_buffs(campaign_id, char.id))
    await _mark_battle_economy(campaign_id, char.id, "bonus")

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "feature_name": "🥊 Flurry of Blows",
            "feature_desc": (
                "Bonus action, 1 ki. Two unarmed strikes available this turn."
            ),
            "source": "flurry-of-blows",
            "remaining": ki_cur - 1,
            "max": ki_max,
            "over_budget": was_used,
            "over_budget_slot": "bonus" if was_used else "",
        },
    })
    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id, "key": "ki",
            "current": ki_cur - 1, "max": ki_max,
        },
    })

    return {
        "ok": True,
        "remaining": ki_cur - 1,
        "max": ki_max,
        "duration_rounds": 1,
        "buff_installed": installed,
        "unarmed_strikes_available": 2,
    }


# ----------- API: End a buff manually (Phase C.1 manual removal) -----------

@router.post("/api/campaign/{campaign_id}/end_buff")
async def end_buff(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Remove a buff from a combatant by key.

    Body: ``{character_id, key}``.

    Auth: owner of the character or any GM. (Not the buff installer —
    the rage'd barbarian's player can end their own rage; the GM can
    end anyone's.)

    Returns 404 if no battle / character not in init / buff not on
    the combatant. Broadcasts ``buff_update`` with the new list.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    key = str(body.get("key") or "").strip()
    if char_id <= 0:
        raise HTTPException(400, "character_id is required")
    if not key:
        raise HTTPException(400, "key is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    # v2.49.52: snapshot the buff BEFORE removal so we can detect
    # voluntary concentration end + emit a ✋ GM log naming the
    # spell. _remove_buff itself only broadcasts buff_update; the
    # log is a separate audit entry parallel to the v2.49.50 💀
    # incapacitation log and the v2.39.0 💔 failed-save log.
    pre_remove_buff = next(
        (b for b in _get_buffs(campaign_id, char.id)
         if (b or {}).get("key") == key),
        None,
    )

    removed = await _remove_buff(campaign_id, char.id, key)
    if not removed:
        raise HTTPException(404, f"No '{key}' buff on this character")

    # v2.19.2 Phase C.3: sync sheet mirror.
    _mirror_buffs_to_sheet(db, char.id, _get_buffs(campaign_id, char.id))

    # v2.49.52: ✋ GM-only log for voluntary concentration end. Only
    # fires when the removed buff was an anchor the character owned
    # (source_char_id absent or == self). Paired conditions removed
    # via /end_buff (e.g. a player clearing their own Paralyzed) DON'T
    # get the ✋ log because that's not the caster ending concentration
    # — the source caster is still concentrating on the spell.
    if pre_remove_buff and pre_remove_buff.get("concentration"):
        src = pre_remove_buff.get("source_char_id")
        if src is None or src == char.id:
            buff_name = pre_remove_buff.get("name") or key
            await hub.broadcast(campaign_id, {
                "type": "roll",
                "data": {
                    "expression": "—",
                    "total": 0,
                    "breakdown": "Concentration ends — voluntary",
                    "note": (
                        f"✋ {char.name} ended concentration on {buff_name}"
                    ),
                    "visibility": Visibility.GM_ONLY.value,
                    "user_id": None,
                    "user_name": "GM log",
                    "char_name": char.name,
                },
            })

    return {"ok": True, "removed_key": key}


# ----------- API: GET buffs (read helper, mostly for harness tests) -----------

@router.get("/api/campaign/{campaign_id}/character/{char_id}/buffs")
def get_character_buffs(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return the character's active buff list.

    Returns both the live hub view (``buffs`` — current source of truth
    during combat, includes live duration_rounds) and the sheet mirror
    (``sheet_buffs`` — persistent snapshot, duration stripped) so callers
    can verify the C.3 mirror is in sync. Allowed to anyone who can
    view the campaign.

    v2.19.2 Phase C.3 added — primary use case is harness verification
    that /use_rage / /cast_hunters_mark / etc. update the sheet mirror.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    return {
        "character_id": char_id,
        "buffs": _get_buffs(campaign_id, char_id),
        "sheet_buffs": list((char.sheet or {}).get("_buffs_active") or []),
    }


# ----------- API: Hunter's Mark (Ranger L1) — Phase C.2 -----------
#
# v2.19.1 Phase C.2: first concentration buff. Hunter's Mark is the
# canonical "concentration on a marked target" spell — bonus action to
# cast, +1d6 weapon damage on hits against the marked creature,
# advantage on Survival/Perception checks to find it. Concentration
# breaks on damage (rolled via _maybe_concentration_save). The (B)
# Phase B roll-time intercept will read this buff's effects to add the
# +1d6 to attacks against the marked target.

async def _resolve_target_combatant(
    campaign_id: int,
    *,
    target_character_id: int | None,
    target_name: str | None,
) -> tuple[str | None, str | None]:
    """Resolve a picked target into ``(combatant_id, display_name)``.

    Returns the (stable) combatant.id string + a display name suitable
    for chat messages. Returns ``(None, target_name)`` when the target
    isn't currently in init — the buff stamps a name-only target that
    the (B) intercept matches loosely.
    """
    state = hub.get_battle(campaign_id)
    if not state:
        return None, target_name
    for c in state.get("combatants") or []:
        if target_character_id and c.get("char_id") == target_character_id:
            return c.get("id"), c.get("name") or target_name
        if target_name and c.get("name") == target_name:
            return c.get("id"), c.get("name")
    return None, target_name


@router.post("/api/campaign/{campaign_id}/cast_hunters_mark")
async def cast_hunters_mark(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Cast Hunter's Mark on a target — install the concentration buff
    + decrement a Ranger spell slot + mark the bonus chip.

    Body: ``{character_id, target_character_id?, target_name?, slot_level?, override?}``.

    RAW: Bonus action. Concentration, up to 1 hour. Mark a creature:
    +1d6 weapon damage on hits against it, advantage on Wisdom
    (Perception / Survival) checks to find it. Re-mark a new creature
    as a bonus action when the previous target drops to 0 HP.
    Upcastable: L3 = up to 8 hours; L4+ = up to 24 hours.

    Validates Ranger class (409), Hunter's Mark on the spell list (409),
    Phase 4 over-budget on bonus slot, L1+ Ranger slot available (409
    no_slot). Atomically decrements the Ranger slot + installs the
    Hunter's Mark concentration buff (drops any existing concentration
    buff on the caster — RAW one-at-a-time rule) + marks the bonus chip.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    target_character_id = body.get("target_character_id")
    target_character_id = int(target_character_id) if target_character_id else None
    target_name = (body.get("target_name") or "").strip() or None
    slot_level_raw = body.get("slot_level")
    slot_level = int(slot_level_raw) if slot_level_raw else 1
    override = bool(body.get("override"))
    if char_id <= 0:
        raise HTTPException(400, "character_id is required")
    if not target_character_id and not target_name:
        raise HTTPException(400, "target_character_id or target_name is required")
    if slot_level < 1:
        slot_level = 1

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Caster not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    primary_class = (sheet.get("class") or "").strip().lower()
    if primary_class != "ranger":
        # Multi-class lookup
        has_ranger = any(
            (entry.get("class") or "").strip().lower() == "ranger"
            for entry in (sheet.get("classes") or [])
        )
        if not has_ranger:
            raise HTTPException(409, "Hunter's Mark requires Ranger level 1+")

    # Verify Hunter's Mark is on the known spell list (defensive — the
    # client UI shouldn't surface it otherwise).
    spells = list(sheet.get("spells") or [])
    has_hm = any(
        (s.get("_slug") == "hunters-mark") or
        (str(s.get("name", "")).lower() == "hunter's mark")
        for s in spells
    )
    if not has_hm:
        raise HTTPException(409, "Hunter's Mark is not on this character's spell list")

    # Decrement a Ranger slot.
    all_slots = dict(sheet.get("spell_slots") or {})
    per_class = dict(all_slots.get("ranger") or {})
    slot_key = str(slot_level)
    slot = dict(per_class.get(slot_key) or {"total": 0, "used": 0})
    total = int(slot.get("total") or 0)
    used = int(slot.get("used") or 0)
    if total <= 0 or used >= total:
        return JSONResponse(status_code=409, content={
            "error": "no_slot",
            "level": slot_level,
            "class_slug": "ranger",
            "spell_name": "Hunter's Mark",
        })

    # Phase 4 over-budget gate (bonus slot).
    was_used = _is_slot_used(campaign_id, char.id, "bonus")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": "bonus",
            "char_name": char.name,
            "source": "hunters-mark",
            "label": "Hunter's Mark",
            "strict": strict,
        })

    # Commit slot decrement.
    slot["used"] = used + 1
    per_class[slot_key] = slot
    all_slots["ranger"] = per_class
    sheet["spell_slots"] = all_slots
    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    # Resolve the target.
    target_combatant_id, resolved_name = await _resolve_target_combatant(
        campaign_id,
        target_character_id=target_character_id,
        target_name=target_name,
    )
    display_target = resolved_name or "the target"

    # Duration scales with slot level: L1-L2 = 1 hour (600 rounds), L3-L4
    # = 8 hours (4800 rounds), L5+ = 24 hours (14400 rounds). For demo
    # purposes we cap displayed duration at 100 rounds so the chip text
    # stays compact; the buff persists until removed or concentration
    # breaks regardless.
    if slot_level >= 5:
        duration_rounds = 100  # display cap
        duration_label = "24h"
    elif slot_level >= 3:
        duration_rounds = 100
        duration_label = "8h"
    else:
        duration_rounds = 100  # display cap; RAW 1 hour = 600 rounds
        duration_label = "1h"

    # Install the concentration buff. Replaces any existing
    # concentration buff on the caster (RAW).
    buff = {
        "key": "hunters-mark",
        "name": "Hunter's Mark",
        "icon": "🎯",
        "source_caster_id": None,  # filled by client from broadcast
        "target_combatant_id": target_combatant_id,
        "target_character_id": target_character_id,
        "target_name": resolved_name or target_name,
        "duration_rounds": duration_rounds,
        "duration_max": duration_rounds,
        "duration_label": duration_label,
        "concentration": True,
        "effects": {
            "weapon_hit_bonus_dice": "1d6",
            "weapon_hit_bonus_target_combatant_id": target_combatant_id,
            "advantage_on": ["perception_to_find_target", "survival_to_find_target"],
        },
        "desc": (
            f"Concentration ({duration_label}). +1d6 weapon damage on hits "
            f"against {display_target}. Advantage on Perception / Survival "
            f"checks to find it."
        ),
    }
    await _install_buff(campaign_id, char.id, buff)
    _mirror_buffs_to_sheet(db, char.id, _get_buffs(campaign_id, char.id))

    # Mark the bonus slot.
    await _mark_battle_economy(campaign_id, char.id, "bonus")

    # Broadcasts.
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": f"🎯 Hunter's Mark → {display_target}",
            "feature_desc": (
                f"Bonus action. Concentration ({duration_label}). +1d6 weapon "
                f"damage on hits against {display_target}. L{slot_level} slot."
            ),
            "source": "hunters-mark",
            "target_character_id": target_character_id,
            "target_name": resolved_name or target_name,
            "over_budget": was_used,
            "over_budget_slot": "bonus" if was_used else "",
        },
    })

    await hub.broadcast(campaign_id, {
        "type": "spell_slot_update",
        "data": {
            "character_id": char.id,
            "class_slug": "ranger",
            "level": slot_level,
            "total": total,
            "used": used + 1,
        },
    })

    return {
        "ok": True,
        "slot_level": slot_level,
        "slot_used": used + 1,
        "slot_total": total,
        "target_combatant_id": target_combatant_id,
        "target_character_id": target_character_id,
        "target_name": resolved_name or target_name,
        "duration_rounds": duration_rounds,
        "duration_label": duration_label,
    }


# ----------- API: Hex (Warlock L1) — Phase C.2 -----------

@router.post("/api/campaign/{campaign_id}/cast_hex")
async def cast_hex(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Cast Hex on a target — install the concentration buff + decrement
    a Warlock spell slot + mark the bonus chip.

    Body: ``{character_id, target_character_id?, target_name?,
    slot_level?, ability?, override?}``.

    RAW: Bonus action. Concentration, up to 1 hour. Hex a creature:
    +1d6 necrotic damage on weapon / spell hits against it,
    disadvantage on ability checks made with the chosen ability.
    Re-hex a new creature as a bonus action when the previous target
    drops to 0 HP. Upcasts: L3 = up to 8 hours; L5+ = up to 24 hours.

    ``ability`` (one of STR/DEX/CON/INT/WIS/CHA, defaults to STR) is
    the ability the marked target has disadvantage on.

    Validates Warlock class (409), Hex on the spell list (409), Phase 4
    over-budget on bonus slot, Warlock slot available at slot_level
    (default = highest castable = L3 for Lv 5 Warlock). Concentration
    swap rule via ``_install_buff``.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    target_character_id = body.get("target_character_id")
    target_character_id = int(target_character_id) if target_character_id else None
    target_name = (body.get("target_name") or "").strip() or None
    slot_level_raw = body.get("slot_level")
    slot_level = int(slot_level_raw) if slot_level_raw else 1
    ability = (body.get("ability") or "STR").upper()
    override = bool(body.get("override"))
    if char_id <= 0:
        raise HTTPException(400, "character_id is required")
    if not target_character_id and not target_name:
        raise HTTPException(400, "target_character_id or target_name is required")
    if ability not in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
        ability = "STR"
    if slot_level < 1:
        slot_level = 1

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Caster not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    primary_class = (sheet.get("class") or "").strip().lower()
    if primary_class != "warlock":
        has_warlock = any(
            (entry.get("class") or "").strip().lower() == "warlock"
            for entry in (sheet.get("classes") or [])
        )
        if not has_warlock:
            raise HTTPException(409, "Hex requires Warlock level 1+")

    # Verify Hex is on the spell list.
    spells = list(sheet.get("spells") or [])
    has_hex = any(
        (s.get("_slug") == "hex") or
        (str(s.get("name", "")).lower() == "hex")
        for s in spells
    )
    if not has_hex:
        raise HTTPException(409, "Hex is not on this character's spell list")

    # v2.49.76 — Phase 2D range-enforcement gate. Hex's RAW range is
    # 90 feet. Fires before slot consumption (same contract as
    # cast_spell's range check).
    _override_range = bool(body.get("override_range"))
    _user_is_gm_for_range = _user_is_gm(user, campaign, db)
    _strict_for_range = bool(campaign.strict_action_economy)
    _range_err = _check_cast_range(
        db, campaign, char,
        "90 feet", "Hex",
        None, target_character_id, target_name,
        override_range=_override_range,
        user_is_gm=_user_is_gm_for_range,
        strict=_strict_for_range,
    )
    if _range_err:
        return JSONResponse(status_code=409, content=_range_err)

    # Find a usable Warlock slot. For Warlock Lv 5 the table only has
    # L3 slots; if the caller asked for L1 we upgrade to whatever's
    # actually available (Pact Magic).
    all_slots = dict(sheet.get("spell_slots") or {})
    per_class = dict(all_slots.get("warlock") or {})
    # Pick the lowest available slot at or above slot_level.
    chosen_level = None
    for k in sorted(per_class.keys(), key=lambda x: int(x)):
        try:
            lv = int(k)
        except ValueError:
            continue
        if lv < slot_level:
            continue
        s = per_class.get(k) or {}
        if int(s.get("used") or 0) < int(s.get("total") or 0):
            chosen_level = lv
            break
    if chosen_level is None:
        return JSONResponse(status_code=409, content={
            "error": "no_slot",
            "level": slot_level,
            "class_slug": "warlock",
            "spell_name": "Hex",
        })
    slot = dict(per_class.get(str(chosen_level)) or {"total": 0, "used": 0})
    total = int(slot.get("total") or 0)
    used = int(slot.get("used") or 0)
    slot_level = chosen_level  # update for downstream

    # Phase 4 over-budget gate (bonus slot).
    was_used = _is_slot_used(campaign_id, char.id, "bonus")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": "bonus",
            "char_name": char.name,
            "source": "hex",
            "label": "Hex",
            "strict": strict,
        })

    # Commit slot decrement.
    slot["used"] = used + 1
    per_class[str(slot_level)] = slot
    all_slots["warlock"] = per_class
    sheet["spell_slots"] = all_slots
    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    # Resolve target.
    target_combatant_id, resolved_name = await _resolve_target_combatant(
        campaign_id,
        target_character_id=target_character_id,
        target_name=target_name,
    )
    display_target = resolved_name or "the target"

    # Duration scales with slot level.
    if slot_level >= 5:
        duration_rounds = 100
        duration_label = "24h"
    elif slot_level >= 3:
        duration_rounds = 100
        duration_label = "8h"
    else:
        duration_rounds = 100
        duration_label = "1h"

    buff = {
        "key": "hex",
        "name": "Hex",
        "icon": "🕷️",
        "source_caster_id": None,
        "target_combatant_id": target_combatant_id,
        "target_character_id": target_character_id,
        "target_name": resolved_name or target_name,
        "duration_rounds": duration_rounds,
        "duration_max": duration_rounds,
        "duration_label": duration_label,
        "concentration": True,
        "effects": {
            "weapon_hit_bonus_dice": "1d6",
            "weapon_hit_bonus_damage_type": "necrotic",
            "weapon_hit_bonus_target_combatant_id": target_combatant_id,
            "disadvantage_on_ability_check": ability,
        },
        "desc": (
            f"Concentration ({duration_label}). +1d6 necrotic on weapon/spell "
            f"hits against {display_target}. Disadvantage on {ability} checks."
        ),
    }
    await _install_buff(campaign_id, char.id, buff)
    _mirror_buffs_to_sheet(db, char.id, _get_buffs(campaign_id, char.id))

    # Mark the bonus slot.
    await _mark_battle_economy(campaign_id, char.id, "bonus")

    # Broadcasts.
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": f"🕷️ Hex ({ability}) → {display_target}",
            "feature_desc": (
                f"Bonus action. Concentration ({duration_label}). +1d6 necrotic "
                f"on hits against {display_target}. Disadvantage on {ability} "
                f"checks. L{slot_level} slot."
            ),
            "source": "hex",
            "target_character_id": target_character_id,
            "target_name": resolved_name or target_name,
            "ability": ability,
            "over_budget": was_used,
            "over_budget_slot": "bonus" if was_used else "",
        },
    })

    await hub.broadcast(campaign_id, {
        "type": "spell_slot_update",
        "data": {
            "character_id": char.id,
            "class_slug": "warlock",
            "level": slot_level,
            "total": total,
            "used": used + 1,
        },
    })

    return {
        "ok": True,
        "slot_level": slot_level,
        "slot_used": used + 1,
        "slot_total": total,
        "target_combatant_id": target_combatant_id,
        "target_character_id": target_character_id,
        "target_name": resolved_name or target_name,
        "ability": ability,
        "duration_rounds": duration_rounds,
        "duration_label": duration_label,
    }


# ----------- API: cast Sleep (HP-pool targeting) -----------

# v2.49.64 — RAW Sleep exclusion ("Undead and creatures immune to
# being charmed aren't affected by this spell"). Inspects the
# target combatant's stat block + condition immunities. NPCs route
# through their monster template (slug → SRD JSON via local_content);
# PCs route through their character sheet. Returns ``(is_immune,
# reason)`` where reason is one of ``"undead"`` / ``"charm_immune"``
# / ``""``. Undead trumps charm-immune in reporting (most undead are
# also charm-immune; "undead" is the more specific cause).
def _is_sleep_immune(
    combatant: dict, db: Session, campaign_id: int,
) -> tuple[bool, str]:
    def _check_sheet(sheet: dict) -> tuple[bool, str]:
        race = (sheet.get("race") or "").lower()
        if "undead" in race:
            return True, "undead"
        cond_imm = sheet.get("condition_immunities") or []
        if isinstance(cond_imm, str):
            cond_imm = [p.strip() for p in cond_imm.split(",")]
        cond_imm_l = [str(c).lower() for c in cond_imm]
        if any("charm" in c for c in cond_imm_l):
            return True, "charm_immune"
        return False, ""

    # NPC: resolve via monster template's SRD-overlaid sheet.
    tmpl_id = combatant.get("token_template_id")
    if tmpl_id:
        tmpl = db.query(TokenTemplate).filter(
            TokenTemplate.id == int(tmpl_id),
        ).first()
        if tmpl:
            sheet = _monster_template_to_sheet(tmpl, campaign_id)
            immune, reason = _check_sheet(sheet)
            if immune:
                return True, reason
    # PC: check the character sheet directly.
    char_id = combatant.get("char_id")
    if char_id:
        char = db.query(Character).filter(
            Character.id == int(char_id),
        ).first()
        if char:
            immune, reason = _check_sheet(char.sheet or {})
            if immune:
                return True, reason
    return False, ""


@router.post("/api/campaign/{campaign_id}/cast_sleep")
async def cast_sleep(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Cast Sleep — roll a 5d8-per-slot HP pool and put creatures to
    sleep in ascending order of current HP until the pool is exhausted.

    Body: ``{character_id, class_slug, slot_level, target_combatant_ids,
    override?}``.

    RAW (PHB Sleep, 1st-level Enchantment): 1 action, 90 ft range,
    duration 1 minute, NO save, NO concentration. Roll 5d8 (+2d8 per
    slot level above 1st) — that's the HP pool. Affected: creatures
    within 20 ft of a chosen point, sorted ascending by current HP,
    ignoring unconscious creatures. Walk the list; each affected
    creature falls Unconscious until the spell ends, the sleeper
    takes damage, or another creature uses an action to shake them
    awake. Subtract each affected creature's HP from the pool before
    moving to the next. Undead + creatures immune to charm are
    immune.

    Implementation notes:
      - SimpleVTT doesn't enforce spatial range / radius today, so
        the caller passes the candidate set as ``target_combatant_ids``
        (the future ruler/range work can sweep this from the canvas).
      - "Immune to charm" / "undead" lookups aren't fully modelled —
        v1 skips those exclusions and lets the GM uncheck inappropriate
        targets via the picker. Filed for follow-up.
      - "Asleep until damaged" is handled by the existing damage
        pipeline: damage on an Unconscious combatant doesn't auto-
        wake them in SimpleVTT today (filed). GMs can /end_buff
        ``unconscious`` to wake a sleeper manually.
      - The Unconscious key is in ``_INCAPACITATING_BUFF_KEYS`` so
        the v2.49.51 hook fires and a PC sleeper loses their own
        concentration. Same as Hold Person etc.

    Validation: caster has the named class + Sleep on spell list +
    available slot at the requested level + Phase 4 action gate (over-
    rideable). Pool roll uses the campaign's dice path so seeded test
    runs are deterministic.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    class_slug = (body.get("class_slug") or "").strip().lower()
    slot_level_raw = body.get("slot_level")
    slot_level = int(slot_level_raw) if slot_level_raw else 1
    target_combatant_ids = body.get("target_combatant_ids") or []
    override = bool(body.get("override"))

    if char_id <= 0:
        raise HTTPException(400, "character_id is required")
    if class_slug not in ("wizard", "bard", "sorcerer", "warlock"):
        raise HTTPException(400, "class_slug must be one of wizard, bard, sorcerer, warlock")
    if slot_level < 1:
        raise HTTPException(400, "slot_level must be >= 1")
    if not isinstance(target_combatant_ids, list) or not target_combatant_ids:
        raise HTTPException(400, "target_combatant_ids must be a non-empty list")

    # v2.49.76 — Phase 2D range-enforcement: /cast_sleep is intentionally
    # SKIPPED from the range check. RAW Sleep's range is 90 ft to the
    # cast point + a 20 ft radius extending from that point; individual
    # targets in the radius can be up to 110 ft from the caster. Today
    # the endpoint receives pre-resolved targets without a cast-point
    # coordinate, so a strict server-side check would either under-enforce
    # (compare to the closest target only) or over-enforce (reject a
    # valid 110-ft target). Same convention as /cast_spell with AoE
    # multi-target lists (see Phase 2C "When NOT to enforce"). A future
    # commit could add a `cast_point: {x, y}` body field + an AoE-aware
    # range check; filed.

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Caster not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})

    # Validate class membership: primary class OR a multiclass entry.
    primary_class = (sheet.get("class") or "").strip().lower()
    if primary_class != class_slug:
        has_class = any(
            (entry.get("class") or "").strip().lower() == class_slug
            for entry in (sheet.get("classes") or [])
        )
        if not has_class:
            return JSONResponse(status_code=409, content={
                "error": "wrong_class",
                "expected": class_slug,
                "got": primary_class or "",
            })

    # Verify Sleep is on the spell list.
    spells = list(sheet.get("spells") or [])
    has_sleep = any(
        (s.get("_slug") == "sleep") or
        (str(s.get("name", "")).lower() == "sleep")
        for s in spells
    )
    if not has_sleep:
        return JSONResponse(status_code=409, content={
            "error": "spell_not_known",
            "spell": "sleep",
        })

    # Find an available slot at the requested level.
    all_slots = dict(sheet.get("spell_slots") or {})
    per_class = dict(all_slots.get(class_slug) or {})
    slot = dict(per_class.get(str(slot_level)) or {"total": 0, "used": 0})
    total = int(slot.get("total") or 0)
    used = int(slot.get("used") or 0)
    if total <= 0 or used >= total:
        return JSONResponse(status_code=409, content={
            "error": "no_slot",
            "level": slot_level,
            "class_slug": class_slug,
            "spell_name": "Sleep",
        })

    # Phase 4 over-budget gate (action slot).
    was_used = _is_slot_used(campaign_id, char.id, "action")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": "action",
            "char_name": char.name,
            "source": "sleep",
            "label": "Sleep",
            "strict": strict,
        })

    # Commit slot decrement.
    slot["used"] = used + 1
    per_class[str(slot_level)] = slot
    all_slots[class_slug] = per_class
    sheet["spell_slots"] = all_slots
    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    # Roll the HP pool: 5d8 + 2d8 per slot level above 1st.
    extra_dice = max(0, slot_level - 1) * 2
    pool_dice = 5 + extra_dice
    pool_expr = f"{pool_dice}d8"
    try:
        pool_roll = dice_mod.roll(pool_expr)
        pool_total = int(pool_roll.total)
        pool_breakdown = pool_roll.breakdown
    except dice_mod.DiceParseError:
        pool_total = 0
        pool_breakdown = pool_expr

    # Resolve targets + capture current HP. Skip already-unconscious
    # combatants (RAW: ignored when ordering). Surface RAW-immune
    # creatures (undead / charm-immune) in the `unaffected` list with
    # a `reason` so the cast card can show "X was immune".
    resolved_targets: list[dict] = []
    immune_unaffected: list[dict] = []
    for tid in target_combatant_ids:
        if not isinstance(tid, str) or not tid:
            continue
        c = _lookup_combatant(campaign_id, tid)
        if not c:
            continue
        hp_cur = int(c.get("hp_current") or 0)
        # RAW: 0 HP creatures are already unconscious / dead — skip.
        if hp_cur <= 0:
            continue
        already_unc = any(
            (b or {}).get("key") in ("unconscious", "asleep")
            for b in (c.get("buffs") or [])
        )
        if already_unc:
            continue
        # v2.49.64: RAW Sleep — "Undead and creatures immune to being
        # charmed aren't affected by this spell." Surfaced in
        # ``unaffected`` with a reason so the cast card can display
        # the exclusion to the caster rather than silently filtering.
        immune, immune_reason = _is_sleep_immune(c, db, campaign_id)
        if immune:
            immune_unaffected.append({
                "combatant_id": tid,
                "name": c.get("name") or "",
                "hp": hp_cur,
                "reason": immune_reason,
            })
            continue
        resolved_targets.append({
            "combatant_id": tid,
            "name": c.get("name") or "",
            "hp_current": hp_cur,
            "char_id": c.get("char_id"),
            "token_template_id": c.get("token_template_id"),
        })

    # Sort by ascending current HP; walk down the list.
    resolved_targets.sort(key=lambda t: t["hp_current"])

    affected: list[dict] = []
    unaffected: list[dict] = list(immune_unaffected)
    pool_remaining = pool_total
    sleep_duration_rounds = 10  # 1 min = 10 rounds at 6 s/round
    for t in resolved_targets:
        if t["hp_current"] <= pool_remaining:
            pool_remaining -= t["hp_current"]
            buff = {
                "key": "unconscious",
                "name": "Unconscious (Sleep)",
                "icon": "💤",
                "source_char_id": char.id,
                "source_char_name": char.name,
                "source_spell": "Sleep",
                "duration_rounds": sleep_duration_rounds,
                "duration_max": sleep_duration_rounds,
                "concentration": False,
                "effects": [
                    "incapacitated — no actions or reactions",
                    "drops what it's holding + falls prone",
                    "auto-fail STR / DEX saves",
                    "attacks vs target have advantage; hits within 5 ft auto-crit",
                    "wakes on damage or when shaken (action) — GM /end_buff to wake",
                ],
            }
            installed = False
            if t["char_id"]:
                installed = await _install_buff(
                    campaign_id, int(t["char_id"]), buff,
                )
                if installed:
                    _mirror_buffs_to_sheet(
                        db, int(t["char_id"]),
                        _get_buffs(campaign_id, int(t["char_id"])),
                    )
            else:
                installed = await _install_buff_on_combatant_id(
                    campaign_id, t["combatant_id"], buff,
                )
            affected.append({
                "combatant_id": t["combatant_id"],
                "name": t["name"],
                "hp": t["hp_current"],
                "installed": installed,
            })
        else:
            unaffected.append({
                "combatant_id": t["combatant_id"],
                "name": t["name"],
                "hp": t["hp_current"],
                "reason": "hp_above_pool_remaining",
                "pool_remaining": pool_remaining,
            })

    # Mark the action slot.
    await _mark_battle_economy(campaign_id, char.id, "action")

    # Public roll log + spell-slot broadcast.
    affected_summary = ", ".join(
        f"{a['name']} ({a['hp']} HP)" for a in affected
    ) or "no one"
    note = f"💤 Sleep (L{slot_level}, pool {pool_total}) → {affected_summary}"
    await hub.broadcast(campaign_id, {
        "type": "roll",
        "data": {
            "expression": pool_expr,
            "total": pool_total,
            "breakdown": (
                f"{pool_breakdown} = {pool_total} HP pool. "
                f"Affected (asc HP): {affected_summary}. "
                f"Pool remaining after sleeps: {pool_remaining}."
            ),
            "note": note,
            "user_name": char.name,
            "char_name": char.name,
            "visibility": Visibility.PUBLIC.value,
        },
    })

    await hub.broadcast(campaign_id, {
        "type": "spell_slot_update",
        "data": {
            "character_id": char.id,
            "class_slug": class_slug,
            "level": slot_level,
            "total": total,
            "used": used + 1,
        },
    })

    return {
        "ok": True,
        "slot_level": slot_level,
        "slot_used": used + 1,
        "slot_total": total,
        "class_slug": class_slug,
        "pool_expr": pool_expr,
        "pool_total": pool_total,
        "pool_breakdown": pool_breakdown,
        "pool_remaining": pool_remaining,
        "affected": affected,
        "unaffected": unaffected,
        "duration_rounds": sleep_duration_rounds,
    }


# ----------- API: shake a sleeping creature awake (RAW Sleep wake action) -----------

@router.post("/api/campaign/{campaign_id}/shake_awake")
async def shake_awake(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Use an action to shake a Sleep'd creature awake.

    Body: ``{character_id, target_combatant_id?, target_character_id?,
    target_name?, override?}``.

    RAW (PHB Sleep): "each creature affected by this spell falls
    unconscious until the spell ends, the sleeper takes damage, OR
    SOMEONE USES AN ACTION TO SHAKE OR SLAP THE SLEEPER AWAKE." This
    endpoint covers the third branch. No class restriction — RAW
    "someone" means any creature can do it. Costs 1 action.

    Validates:
      - target has a Sleep-sourced Unconscious buff (key=`unconscious`
        AND source_spell=`Sleep`). Other Unconscious sources (a
        dying-at-0-HP creature, a future Knockout feature, etc.) are
        not in scope — shaking a dying character doesn't wake them
        RAW. 409 ``not_asleep`` otherwise.
      - Phase 4 action gate. 409 ``over_budget`` when the shaker's
        action chip is already burnt + they're not the GM + ``override``
        is False (or strict_action_economy is on).

    On success:
      - Removes the Unconscious buff (PC: ``_remove_buff`` + sheet
        mirror; NPC: hub-state mutation + ``battle_update``).
      - Marks the shaker's action slot.
      - Emits a public 🤚 roll-log entry so the table sees the wake.
      - Returns ``{ok, target_name, action_used: True}``.

    No range check today — SimpleVTT doesn't enforce spatial range
    yet (see docs/plans/ruler-and-range.md). The future range-
    enforcement Phase 2 will add a 5-ft melee check here.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    target_combatant_id = (body.get("target_combatant_id") or "").strip()
    target_character_id_in = body.get("target_character_id")
    if target_character_id_in is not None:
        target_character_id_in = int(target_character_id_in)
    target_name_in = (body.get("target_name") or "").strip()
    override = bool(body.get("override"))

    if char_id <= 0:
        raise HTTPException(400, "character_id is required")
    if not target_combatant_id and not target_character_id_in:
        raise HTTPException(400, "target_combatant_id or target_character_id is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Shaker character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    # Resolve target.
    target_combatant = (
        _lookup_combatant(campaign_id, target_combatant_id)
        if target_combatant_id else None
    )
    if not target_combatant and target_character_id_in:
        # PC fallback — synthesize a combatant dict so the buff check
        # can run via the hub state (PC buffs live there, not on the
        # character sheet during combat).
        state = hub.get_battle(campaign_id) or {}
        for c in state.get("combatants") or []:
            if c.get("char_id") == target_character_id_in:
                target_combatant = c
                break
        if not target_combatant:
            target_combatant = {
                "char_id": target_character_id_in,
                "id": target_combatant_id or "",
                "name": target_name_in or "",
                "buffs": [],
            }
    if not target_combatant:
        raise HTTPException(404, "Target combatant not found")

    # Verify the target has a Sleep-sourced Unconscious buff.
    target_buffs = list(target_combatant.get("buffs") or [])
    sleep_buff_keys = [
        b.get("key") for b in target_buffs
        if (b or {}).get("key") in ("unconscious", "asleep")
        and (b or {}).get("source_spell") == "Sleep"
    ]
    if not sleep_buff_keys:
        return JSONResponse(status_code=409, content={
            "error": "not_asleep",
            "target_name": target_combatant.get("name") or "",
            "reason": "target has no Sleep-sourced Unconscious buff",
        })

    # Phase 4 over-budget gate (action slot).
    was_used = _is_slot_used(campaign_id, char.id, "action")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    effective_override = override and not strict
    if was_used and not user_is_gm and not effective_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": "action",
            "char_name": char.name,
            "source": "shake_awake",
            "label": "Shake Awake",
            "strict": strict,
        })

    # Remove the Sleep-Unconscious buff(s).
    target_char_id = target_combatant.get("char_id")
    removed_count = 0
    if target_char_id:
        # PC path.
        for key in sleep_buff_keys:
            if await _remove_buff(campaign_id, int(target_char_id), key):
                removed_count += 1
        if removed_count:
            _mirror_buffs_to_sheet(
                db, int(target_char_id),
                _get_buffs(campaign_id, int(target_char_id)),
            )
    else:
        # NPC path — mutate hub combatant buff list directly.
        state = hub.get_battle(campaign_id)
        if state:
            for c in state.get("combatants") or []:
                if c.get("id") != target_combatant.get("id"):
                    continue
                new_list = [
                    b for b in (c.get("buffs") or [])
                    if not (
                        (b or {}).get("key") in ("unconscious", "asleep")
                        and (b or {}).get("source_spell") == "Sleep"
                    )
                ]
                if len(new_list) != len(c.get("buffs") or []):
                    removed_count = len(c.get("buffs") or []) - len(new_list)
                    c["buffs"] = new_list
                    hub.set_battle(campaign_id, state)
                    await hub.broadcast(campaign_id, {
                        "type": "battle_update",
                        "data": state,
                        "force_gm_sync": True,
                    })
                break

    # Mark the action slot.
    await _mark_battle_economy(campaign_id, char.id, "action")

    # Public wake log.
    target_name = target_combatant.get("name") or "Unknown"
    await hub.broadcast(campaign_id, {
        "type": "roll",
        "data": {
            "expression": "—",
            "total": 0,
            "breakdown": (
                f"Action: shake {target_name} awake — Sleep ends "
                f"(RAW PHB Sleep)"
            ),
            "note": f"🤚 {char.name} shakes {target_name} awake",
            "user_name": char.name,
            "char_name": char.name,
            "visibility": Visibility.PUBLIC.value,
        },
    })

    return {
        "ok": True,
        "target_name": target_name,
        "action_used": True,
        "buffs_removed": removed_count,
    }


# ----------- API: get a character's current action-economy state -----------
#
# Phase 4a (v2.7.2) Layer A dimming: the full character sheet polls
# this endpoint every few seconds to learn which slots are already
# spent, so action / spell / feature buttons whose slot is used can be
# rendered with 50% opacity + cursor:not-allowed + a title="" hint
# before the player even clicks. The 409 over_budget gate on
# /use_attack, /cast_spell, /use_feature, /use_item still fires on a
# click — Layer A is purely the pre-emptive visual cue. Polling rather
# than WS to keep the sheet page free of WS infrastructure for now;
# 4-second cadence × 3-5 sheets open = trivial load.

@router.get("/api/campaign/{campaign_id}/character/{character_id}/economy")
def get_character_economy(
    campaign_id: int,
    character_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return the current action-economy state for one character.

    Shape: ``{battle_active, action, bonus, reaction, movement, speed_walk,
    potions_as_bonus_action}``. When no battle is active or the
    character isn't in init, the chip booleans are False / 0 and
    ``battle_active`` is False — the sheet treats that as "nothing is
    spent; don't dim anything." The ``potions_as_bonus_action`` flag is
    echoed so the sheet can decide whether to dim 🧪 Use on heal
    potions independently of the chip state (used only when Bns is
    already spent).
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    char = db.query(Character).filter(
        Character.id == character_id, Character.campaign_id == campaign_id,
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    state = hub.get_battle(campaign_id)
    base = {
        "battle_active": False,
        "action": False, "bonus": False, "reaction": False,
        "movement": 0.0,
        "speed_walk": 30,
        "potions_as_bonus_action": bool(campaign.potions_as_bonus_action),
    }
    if not state:
        return base
    active = bool(state.get("active"))
    base["battle_active"] = active
    if not active:
        return base
    for c in state.get("combatants") or []:
        if c.get("char_id") == character_id:
            economy = c.get("economy") or {}
            base["action"] = bool(economy.get("action"))
            base["bonus"] = bool(economy.get("bonus"))
            base["reaction"] = bool(economy.get("reaction"))
            base["movement"] = float(economy.get("movement") or 0)
            sw = c.get("speed_walk")
            if isinstance(sw, (int, float)) and sw > 0:
                base["speed_walk"] = int(sw)
            return base
    return base


# ----------- Death save state machine (v2.1.0) -----------
#
# 5e death saving throws: when a character drops to 0 HP they enter the
# "dying" state and roll a d20 each turn. 10+ = success, <10 = failure;
# 3 successes → stable, 3 failures → dead. Natural 20 regains 1 HP +
# wakes them up; natural 1 counts as two failures. Damage while at 0 HP
# auto-ticks a failure (two on a crit); damage that exceeds max HP at 0
# is instant death (massive damage rule).
#
# Every endpoint that mutates ``Character.sheet["hp"]["current"]`` MUST
# route through ``_apply_hp_change`` so the state machine stays in
# lockstep with HP. Direct ``sheet["hp"]["current"] = …`` assignments
# bypass the machine and leave the character in an inconsistent state.

# Valid death save status values. Kept as a constant so the override and
# stabilize endpoints can validate against the same set.
_DEATH_SAVE_STATUSES = ("alive", "dying", "stable", "dead")


def _apply_hp_change(
    char: Character,
    new_current: int,
    *,
    is_damage: bool = False,
    is_crit: bool = False,
    damage_amount: int = 0,
) -> dict:
    """Set ``Character.sheet["hp"]["current"]`` to ``new_current`` and run
    the death save state machine. The single source of truth for HP
    transitions in v2.1.0+.

    Args:
        char: The Character row to mutate (modified in-place).
        new_current: Target HP value after the change. Clamped at 0.
        is_damage: True if the change is a damage source. Enables the
            damage-at-0 auto-failure tick and the massive-damage rule.
            Callers that just *set* HP (manual sheet save, GM edit, /heal)
            should leave this False.
        is_crit: True for critical-hit damage. Ticks two failures instead
            of one when applied to a dying character.
        damage_amount: Raw damage value applied this event (before temp
            HP absorption). Used to evaluate the massive-damage threshold.

    Returns:
        A dict with the post-mutation state for the caller to echo back
        and broadcast:
            - hp: {current, max, temp}
            - death_saves: {status, successes, failures}
            - status_changed: bool
            - became_dying / became_dead: bool flags for the caller
              to surface in the log / toast
    """
    sheet = dict(char.sheet or {})
    hp = dict(sheet.get("hp") or {})
    ds = dict(sheet.get("death_saves") or {})

    max_hp = int(hp.get("max") or 0)
    old_current = int(hp.get("current") or 0)
    old_status = ds.get("status") or "alive"
    successes = int(ds.get("successes") or 0)
    failures = int(ds.get("failures") or 0)

    new_status = old_status
    became_dying = False
    became_dead = False

    new_current = max(0, int(new_current))

    if new_current > 0:
        # HP positive — healing or set. Wake from any non-alive state.
        # v2.1.1: this includes "dead" — healing auto-revives. The earlier
        # design ("dead stays dead, GM override required") proved confusing
        # in practice: the user healing a character is usually the GM, and
        # forcing them through a second action to clear the dead flag was
        # unhelpful. If a table wants strict revivify-spell semantics they
        # can keep the character at 0 HP and use the override to mark them
        # alive at 1 HP rather than healing them through it.
        if old_status in ("dying", "stable", "dead"):
            new_status = "alive"
            successes = 0
            failures = 0
    else:
        # new_current == 0
        if old_status == "alive":
            # Crossing into 0 HP. Massive-damage rule: if remaining
            # damage past 0 ≥ max_hp, instant death.
            if is_damage and max_hp > 0:
                remaining = max(0, damage_amount - old_current)
                if remaining >= max_hp:
                    new_status = "dead"
                    became_dead = True
                    successes = 0
                    failures = 0
                else:
                    new_status = "dying"
                    became_dying = True
                    successes = 0
                    failures = 0
            else:
                # Non-damage set to 0 (manual edit). Treat as dying with
                # zero counters; no auto-failure.
                new_status = "dying"
                became_dying = True
                successes = 0
                failures = 0
        elif old_status == "dying":
            if is_damage:
                # Per RAW: any damage at 0 HP = 1 failure (2 on crit);
                # damage_amount ≥ max_hp = instant death.
                if max_hp > 0 and damage_amount >= max_hp:
                    new_status = "dead"
                    became_dead = True
                    successes = 0
                    failures = 0
                else:
                    failures += 2 if is_crit else 1
                    if failures >= 3:
                        new_status = "dead"
                        became_dead = True
                        successes = 0
                        failures = 0
        elif old_status == "stable":
            if is_damage:
                # Damage to a stable character drops them back to dying
                # with an immediate failure tick.
                if max_hp > 0 and damage_amount >= max_hp:
                    new_status = "dead"
                    became_dead = True
                    successes = 0
                    failures = 0
                else:
                    new_status = "dying"
                    became_dying = True
                    failures = 2 if is_crit else 1
                    successes = 0
        # ``dead`` stays dead until GM override.

    hp["current"] = new_current
    hp.setdefault("max", 0)
    hp.setdefault("temp", 0)
    ds["status"] = new_status
    ds["successes"] = successes
    ds["failures"] = failures

    sheet["hp"] = hp
    sheet["death_saves"] = ds
    char.sheet = sheet

    return {
        "hp": hp,
        "death_saves": ds,
        "status_changed": new_status != old_status,
        "became_dying": became_dying,
        "became_dead": became_dead,
    }


def _set_death_save_state(
    char: Character,
    *,
    status: str | None = None,
    successes: int | None = None,
    failures: int | None = None,
) -> dict:
    """Manually patch parts of the death save state without touching HP.
    Used by the GM override + stabilize endpoints. Returns the updated
    ``death_saves`` dict for the caller to broadcast."""
    sheet = dict(char.sheet or {})
    ds = dict(sheet.get("death_saves") or {"status": "alive", "successes": 0, "failures": 0})
    if status is not None:
        ds["status"] = status
    if successes is not None:
        ds["successes"] = max(0, int(successes))
    if failures is not None:
        ds["failures"] = max(0, int(failures))
    sheet["death_saves"] = ds
    char.sheet = sheet
    return ds


async def _drop_caster_concentration(
    campaign_id: int, character_id: int, *,
    reason: str = "incapacitated",
) -> int:
    """Drop every concentration-tagged buff the character is holding.
    Reuses ``_remove_buff`` which handles the buff_update broadcast +
    ``_drop_paired_concentration_buffs`` cascade for target-side
    condition cleanup.

    v2.49.49 — used by the death-save endpoints to enforce the RAW
    "incapacitated → lose concentration" rule on paths that DON'T go
    through ``_maybe_concentration_save`` (which the v2.49.48 fix
    covered). Specifically: rolling 3 death-save failures → dead,
    or GM override to a non-alive status. The damage-event path
    already drops concentration via the v2.49.48 fix, so this
    helper is purely defensive for the rare non-damage transition
    into incapacitation.

    v2.49.50 — also emits a 💀 GM-only roll-log entry for each buff
    dropped, mirroring the v2.39.0 💔 failed-save log shape. The
    ``reason`` param flows into the log breakdown so the GM can tell
    "incapacitated (3 failed death saves)" from "incapacitated (GM
    override)" at a glance.

    v2.49.51 — filters concentration buffs by ``source_char_id``. A
    buff with ``concentration: True`` on a combatant might be (a)
    the combatant's own concentration anchor (e.g. Hex on the caster
    — source is self or absent) or (b) a paired condition sustained
    by ANOTHER caster's concentration (e.g. Paralyzed on a Hold
    Person victim — source is the enemy caster). Only (a) should
    drop when THIS character is incapacitated; (b) is the source
    caster's concern and drops when THEY lose concentration via
    ``_drop_paired_concentration_buffs``. Without this filter the
    new v2.49.51 incapacitation hook would drop the just-installed
    Paralyzed buff right back off.

    Returns the number of buffs removed.
    """
    state = hub.get_battle(campaign_id)
    if not state:
        return 0
    target = None
    for c in state.get("combatants") or []:
        if c.get("char_id") == character_id:
            target = c
            break
    if target is None:
        return 0
    caster_name = target.get("name") or "Unknown"
    # Snapshot (key, name, paired-pre-drop list) for every concentration
    # buff BEFORE calling _remove_buff — the helper mutates state in
    # place, and the paired-buff cascade fires during removal so the
    # paired list would be empty if we read it after.
    drops: list[tuple[str, str, list[dict]]] = []
    for b in target.get("buffs") or []:
        b = b or {}
        if not b.get("concentration"):
            continue
        # v2.49.51: skip paired condition buffs sustained by another
        # caster. The combatant isn't concentrating on those; their
        # source caster is.
        src = b.get("source_char_id")
        if src is not None and src != character_id:
            continue
        key = b.get("key")
        if not key:
            continue
        buff_name = b.get("name") or key
        paired_pre_drop: list[dict] = []
        for c in state.get("combatants") or []:
            for pb in c.get("buffs") or []:
                pb = pb or {}
                if (
                    pb.get("source_char_id") == character_id
                    and bool(pb.get("concentration"))
                    and pb.get("key") != key
                ):
                    paired_pre_drop.append({
                        "combatant_name": c.get("name") or "Unknown",
                        "buff_name": pb.get("name") or pb.get("key") or "Effect",
                    })
        drops.append((key, buff_name, paired_pre_drop))

    removed_count = 0
    for key, buff_name, paired in drops:
        if not await _remove_buff(campaign_id, character_id, key):
            continue
        removed_count += 1
        if paired:
            paired_summary = " · ".join(
                f"{p['buff_name']} → {p['combatant_name']}"
                for p in paired
            )
            paired_note = f" — dropped: {paired_summary}"
        else:
            paired_note = ""
        await hub.broadcast(campaign_id, {
            "type": "roll",
            "data": {
                "expression": "—",
                "total": 0,
                "breakdown": f"Concentration ends — {reason}",
                "note": (
                    f"💀 {caster_name} lost concentration on {buff_name}"
                    f"{paired_note}"
                ),
                "visibility": Visibility.GM_ONLY.value,
                "user_id": None,
                "user_name": "GM log",
                "char_name": caster_name,
            },
        })
    return removed_count


# ----------- Roll-state (advantage/disadvantage) — v2.2.0 -----------
#
# Per-character "roll state" toggled via the tri-state pill on the
# mini-sheet / full sheet. When set, the server upgrades single-d20
# expressions sent through /roll and /attack to 2d20kh1 (advantage) or
# 2d20kl1 (disadvantage) before rolling. Manual buttons that produce
# 2d20kh1 / 2d20kl1 directly bypass the auto-upgrade (the regex only
# matches single-d20). See docs/plans/advantage-disadvantage.md.

# Matches exactly a single 1d20 with optional +N/-N modifiers and
# whitespace. Rejects 1d20a / 1d20d (manual shorthand), 2d20kh1/kl1
# (manual long form), and any multi-dice expression (damage, ability
# gen, etc.). Group 1 captures the trailing modifier string.
_SINGLE_D20_RE = _re.compile(
    r'^\s*1d20((?:\s*[+-]\s*\d+)*)\s*$',
    _re.IGNORECASE,
)

# Manual adv/dis detection in the *submitted* expression (before any
# server upgrade). Matches both the long form (2d20kh1 / 2d20kl1) and
# the shorthand (1d20a / 1d20d) that dice.py expands.
_MANUAL_ADV_RE = _re.compile(r'(?i)\b(?:2d20kh1|1d20a)\b')
_MANUAL_DIS_RE = _re.compile(r'(?i)\b(?:2d20kl1|1d20d)\b')


def _apply_roll_state(
    expression: str,
    roll_state: dict | None,
) -> tuple[str, str]:
    """Upgrade a single-d20 expression to 2d20kh1 (advantage) or 2d20kl1
    (disadvantage) per the character's stored ``roll_state.value``.

    Returns ``(new_expression, applied)`` where ``applied`` is:

    - ``"auto_advantage"`` / ``"auto_disadvantage"`` — server upgraded
    - ``"manual_advantage"`` / ``"manual_disadvantage"`` — caller submitted
      a manual 2d20kh1 / 1d20a / 2d20kl1 / 1d20d expression
    - ``""`` — no upgrade and no manual flag

    Manual takes precedence over auto: if the submitted expression is
    already adv/dis, ``new_expression`` is the original and ``applied``
    reflects the manual form.
    """
    expr = expression or ""

    # 1) Detect manual adv/dis on the original expression first. If
    # the caller explicitly picked adv/dis, that wins — we don't double
    # up, and we tag the log with "manual ...".
    if _MANUAL_ADV_RE.search(expr):
        return expr, "manual_advantage"
    if _MANUAL_DIS_RE.search(expr):
        return expr, "manual_disadvantage"

    # 2) Auto upgrade only when the character has a roll_state set AND
    # the expression is a single-d20 form.
    value = None
    if isinstance(roll_state, dict):
        value = roll_state.get("value")
    if value not in ("advantage", "disadvantage"):
        return expr, ""

    m = _SINGLE_D20_RE.match(expr)
    if not m:
        return expr, ""
    modifiers = m.group(1) or ""
    if value == "advantage":
        return "2d20kh1" + modifiers, "auto_advantage"
    return "2d20kl1" + modifiers, "auto_disadvantage"


def _roll_state_note_suffix(applied: str) -> str:
    """Human-readable tag for ``applied`` from _apply_roll_state, suitable
    for appending to the roll's ``note`` field. Empty string for no-op."""
    return {
        "auto_advantage":     " (auto advantage)",
        "auto_disadvantage":  " (auto disadvantage)",
        "manual_advantage":   " (manual advantage)",
        "manual_disadvantage":" (manual disadvantage)",
    }.get(applied, "")


# ----------- API: apply healing from roll-log card -----------

@router.post("/api/campaign/{campaign_id}/apply_healing")
async def apply_healing(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Roll healing dice for a spell cast and apply the result to the calling
    user's character.  For AOE spells each user may only claim once; the
    charge counter is enforced server-side via ``_heal_claims``."""
    body = await request.json()
    cast_id = str(body.get("cast_id") or "")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    claim = _heal_claims.get(cast_id)
    if not claim or claim["campaign_id"] != campaign_id:
        # v2.26.2 fix: when v2.26.0 Phase T.4 auto-applied the heal to
        # the targeted ally, the claim was popped server-side but a
        # cached chat card might still render the legacy "🩹 Apply
        # Healing" button. Detect this by checking the damage-log for
        # a matching is_heal entry, and return a friendly 200 instead
        # of the alarming "expired" 404.
        _purge_attack_damage_log()
        log_entry = _attack_damage_log.get(cast_id)
        if log_entry and log_entry.get("is_heal") and log_entry.get("campaign_id") == campaign_id:
            return {
                "ok": True,
                "already_auto_applied": True,
                "applied": int(log_entry.get("applied") or 0),
                "message": "Heal was already auto-applied to the targeted ally — use ↶ Undo to revert.",
            }
        raise HTTPException(404, "Unknown spell cast — it may have expired")

    claimed: set = claim["claimed"]
    max_targets: int = claim["max_targets"]

    if user.id in claimed:
        raise HTTPException(409, "You have already claimed healing from this spell")
    if max_targets > 1 and len(claimed) >= max_targets:
        raise HTTPException(409, "All healing charges have been used")

    # v2.27.1: route the heal to the cast's intended target if the
    # claim carries one (stored at registration time from cast_spell's
    # target descriptors). This is the right behavior for almost every
    # caller: the GM clicking "Apply Healing" on a Tavik → Krieger
    # cast expects Krieger to be healed, not the GM's first owned PC.
    # Fall back to "first character owned by calling user" only when
    # the claim has no stored target (truly self-claim flow, like
    # Mass Healing Word AoE with no specific target).
    char = None
    stored_target_char_id = claim.get("target_character_id")
    if stored_target_char_id:
        char = db.query(Character).filter(
            Character.id == int(stored_target_char_id),
            Character.campaign_id == campaign_id,
        ).first()
    if not char:
        stored_target_combatant_id = claim.get("target_combatant_id")
        if stored_target_combatant_id:
            target_combatant = _lookup_combatant(campaign_id, stored_target_combatant_id)
            if target_combatant and target_combatant.get("char_id"):
                char = db.query(Character).filter(
                    Character.id == int(target_combatant["char_id"]),
                    Character.campaign_id == campaign_id,
                ).first()
    if not char:
        # Fallback: calling user's first owned PC in the campaign.
        char = (
            db.query(Character)
            .filter(Character.campaign_id == campaign_id, Character.owner_user_id == user.id)
            .first()
        )
    if not char:
        raise HTTPException(404, "No target character resolved for this heal claim")

    # Roll the healing dice server-side
    try:
        r = dice_mod.roll(claim["dice"])
        rolled = r.total
        breakdown = r.breakdown
    except Exception:
        rolled = 0
        breakdown = ""

    # Apply HP through the death-save state machine (heals wake the
    # character from dying/stable per v2.1.0 design).
    hp_before = char.sheet.get("hp") or {}
    hp_cur = int(hp_before.get("current") or 0)
    hp_max = int(hp_before.get("max") or 0)
    new_cur = min(hp_max, hp_cur + rolled) if hp_max > 0 else (hp_cur + rolled)
    result = _apply_hp_change(char, new_cur)
    db.commit()

    # Track claim
    claimed.add(user.id)
    claimed_count = len(claimed)

    new_hp = result["hp"]
    await hub.broadcast(campaign_id, {
        "type": "heal_applied",
        "data": {
            "cast_id": cast_id,
            "char_id": char.id,
            "char_name": char.name,
            "healer_name": user.display_name,
            "dice": claim["dice"],
            "rolled": rolled,
            "breakdown": breakdown,
            "new_hp": new_hp,
            "claimed_count": claimed_count,
            "max_targets": max_targets,
        },
    })
    if result["status_changed"]:
        await hub.broadcast(campaign_id, {
            "type": "character_death_save",
            "data": {
                "character_id": char.id,
                "status": result["death_saves"]["status"],
                "successes": int(result["death_saves"]["successes"]),
                "failures": int(result["death_saves"]["failures"]),
                "hp": new_hp,
                "source": "heal",
            },
        })
    return {"ok": True, "rolled": rolled, "breakdown": breakdown, "new_hp": new_hp,
            "claimed_count": claimed_count, "max_targets": max_targets}


# ----------- API: short / long rest -----------

@router.post("/api/campaign/{campaign_id}/character/{char_id}/rest")
async def rest_character(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Apply a short or long rest to a character.

    Body: ``{"type": "short" | "long"}``.

    Short rest: spend one hit die, roll d{HD}+CON, recover that much HP
    (capped at max), decrement hit_dice.current. Returns 409 if no hit
    dice are left.

    Long rest: HP→max, Temp HP cleared, hit_dice.current += max(1, ⌊max/2⌋)
    capped at max, every spell_slots[*].used reset to 0. Broadcasts a
    spell_slot_update WS message per slot level so any open mini-sheet or
    full sheet rerenders its pips.
    """
    body = await request.json()
    rest_type = str(body.get("type", "")).strip().lower()
    if rest_type not in ("short", "long"):
        raise HTTPException(400, "type must be 'short' or 'long'")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)
    hp = dict(sheet.get("hp") or {})
    hp_max = int(hp.get("max") or 0)
    hp_cur = int(hp.get("current") or 0)
    hd = dict(sheet.get("hit_dice") or {})
    hd_max = int(hd.get("max") if hd.get("max") is not None else (sheet.get("level") or 1))
    hd_cur = int(hd.get("current") if hd.get("current") is not None else hd_max)

    # Refill matching trackable resources. Long rest refills 'short' + 'long';
    # short rest only refills 'short'. Resources with reset='none' (manual
    # chat-only feature with a counter) are never auto-refilled.
    resources_before = list(sheet.get("resources") or [])
    refilled_resources: list[dict] = []
    new_resources: list[dict] = []
    for r in resources_before:
        if not isinstance(r, dict):
            new_resources.append(r)
            continue
        reset_kind = str(r.get("reset") or "").strip().lower()
        should_refill = (
            reset_kind == "short" and rest_type in ("short", "long")
        ) or (
            reset_kind == "long" and rest_type == "long"
        )
        if should_refill and int(r.get("max") or 0) > 0:
            updated = {**r, "current": int(r.get("max") or 0)}
            new_resources.append(updated)
            refilled_resources.append(updated)
        else:
            new_resources.append(r)
    sheet["resources"] = new_resources

    if rest_type == "long":
        long_rest_new_cur = hp_max if hp_max > 0 else hp_cur
        hp["temp"] = 0
        hd["max"] = hd_max
        hd["current"] = min(hd_max, hd_cur + max(1, hd_max // 2)) if hd_max > 0 else hd_cur
        # Reset slots across every class's nested slot map.
        slots = dict(sheet.get("spell_slots") or {})
        new_slots: dict = {}
        broadcasts: list[tuple[str, int, int]] = []  # (class_slug, level, total)
        for cslug, by_lvl in slots.items():
            if isinstance(by_lvl, dict):
                cleaned: dict = {}
                for lvl_key, slot_obj in by_lvl.items():
                    if isinstance(slot_obj, dict):
                        cleaned[lvl_key] = {**slot_obj, "used": 0}
                        try:
                            total = int(slot_obj.get("total") or 0)
                        except (TypeError, ValueError):
                            total = 0
                        if total > 0:
                            try:
                                broadcasts.append((cslug, int(lvl_key), total))
                            except (TypeError, ValueError):
                                pass
                    else:
                        cleaned[lvl_key] = slot_obj
                new_slots[cslug] = cleaned
            else:
                new_slots[cslug] = by_lvl
        sheet["spell_slots"] = new_slots
        sheet["hp"] = hp
        sheet["hit_dice"] = hd
        char.sheet = sheet
        # Long rest restores HP to max and clears any dying/stable state.
        # Route through the death-save state machine so the broadcast +
        # tracker UI stay in sync.
        hp_result = _apply_hp_change(char, long_rest_new_cur)
        db.commit()
        if hp_result["status_changed"]:
            await hub.broadcast(campaign_id, {
                "type": "character_death_save",
                "data": {
                    "character_id": char.id,
                    "status": hp_result["death_saves"]["status"],
                    "successes": int(hp_result["death_saves"]["successes"]),
                    "failures": int(hp_result["death_saves"]["failures"]),
                    "hp": hp_result["hp"],
                    "source": "long_rest",
                },
            })

        # Broadcast slot-pip updates so any open sheet / mini-sheet re-renders
        for cslug, lvl, total in broadcasts:
            try:
                await hub.broadcast(campaign_id, {
                    "type": "spell_slot_update",
                    "data": {
                        "character_id": char.id,
                        "class_slug": cslug,
                        "level": lvl,
                        "total": total,
                        "used": 0,
                    },
                })
            except Exception:
                pass

        # Broadcast resource refills for any open Class Resources panel
        for r in refilled_resources:
            try:
                await hub.broadcast(campaign_id, {
                    "type": "resource_update",
                    "data": {
                        "character_id": char.id,
                        "key": r.get("key"),
                        "current": int(r.get("current") or 0),
                        "max": int(r.get("max") or 0),
                    },
                })
            except Exception:
                pass

        return {"ok": True, "type": "long", "hp": hp_result["hp"], "hit_dice": hd, "resources": refilled_resources}

    # Short rest
    if hd_cur <= 0:
        return JSONResponse(
            status_code=409, content={"error": "no_hit_dice", "hit_dice": hd}
        )

    import re as _re
    die_str = (sheet.get("class_hit_die") or "").strip() or "d8"
    m = _re.search(r"d(\d+)", die_str, _re.IGNORECASE)
    die_size = int(m.group(1)) if m else 8

    abilities = sheet.get("abilities") or {}
    con_score = int(abilities.get("CON") or 10)
    con_mod = (con_score - 10) // 2

    # v2.15.3: Song of Rest — any Bard ≥ Lv 2 in the campaign grants
    # this rest an extra 1dN bonus (d6/d8/d10/d12 by Bard level). The
    # bonus die is folded into the same roll expression so the existing
    # ``dice_mod.roll`` call handles both terms and the breakdown reads
    # naturally ("1d8[5]+1d6[3]+2 => 10"). A Bard resting alone also
    # gets the bonus on their own HD spend (RAW: "you or any friendly
    # creatures who can hear your performance").
    sor_die, sor_bard, sor_bard_lv = _song_of_rest_for_campaign(db, campaign_id)
    sor_part = f"+1d{sor_die}" if sor_die > 0 else ""

    sign = "+" if con_mod >= 0 else ""
    con_part = f"{sign}{con_mod}" if con_mod != 0 else ""
    expr = f"1d{die_size}{sor_part}{con_part}"
    try:
        result = dice_mod.roll(expr)
        recovered = max(1, result.total)
        breakdown = result.breakdown
    except dice_mod.DiceParseError:
        recovered = 1
        breakdown = ""

    new_hp = min(hp_max, hp_cur + recovered) if hp_max > 0 else (hp_cur + recovered)
    hd["current"] = hd_cur - 1
    hd["max"] = hd_max
    sheet["hp"] = hp
    sheet["hit_dice"] = hd
    char.sheet = sheet
    # Short rest healing goes through the state machine so a dying
    # character who somehow ends up able to take a short rest (e.g. via
    # the GM rolling them stable then back up) cleanly wakes them.
    hp_result = _apply_hp_change(char, new_hp)
    db.commit()
    if hp_result["status_changed"]:
        await hub.broadcast(campaign_id, {
            "type": "character_death_save",
            "data": {
                "character_id": char.id,
                "status": hp_result["death_saves"]["status"],
                "successes": int(hp_result["death_saves"]["successes"]),
                "failures": int(hp_result["death_saves"]["failures"]),
                "hp": hp_result["hp"],
                "source": "short_rest",
            },
        })

    # Broadcast resource refills for any short-rest resources (Action Surge,
    # Channel Divinity, Ki, Superiority Dice, …) so live panels re-pip.
    for r in refilled_resources:
        try:
            await hub.broadcast(campaign_id, {
                "type": "resource_update",
                "data": {
                    "character_id": char.id,
                    "key": r.get("key"),
                    "current": int(r.get("current") or 0),
                    "max": int(r.get("max") or 0),
                },
            })
        except Exception:
            pass

    return {
        "ok": True,
        "type": "short",
        "hp": hp_result["hp"],
        "hit_dice": hd,
        "expression": expr,
        "recovered": recovered,
        "breakdown": breakdown,
        "resources": refilled_resources,
        # v2.15.3: ``song_of_rest`` is non-null when any Bard ≥ Lv 2 is
        # in the campaign. ``die`` is the d{N} that was rolled, ``bard``
        # is the highest-level Bard's name (display attribution),
        # ``bard_level`` is their level. Null when no eligible Bard
        # exists. The bonus die's individual roll is included in the
        # ``breakdown`` string ("1d8[5]+1d6[3]+2 => 10") so the client
        # can extract the exact value or just show the breakdown verbatim.
        "song_of_rest": (
            {"die": sor_die, "bard": sor_bard, "bard_level": sor_bard_lv}
            if sor_die > 0 else None
        ),
    }


# ----------- API: class / subclass resource use -----------

@router.post("/api/campaign/{campaign_id}/character/{char_id}/resource")
async def use_resource(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Spend or restore a trackable class/subclass resource.

    Body:
        {"key": "<resource key>", "delta": -1}     # spend (negative)
        {"key": "<resource key>", "delta": +1}     # restore by N
        {"key": "<resource key>", "set": N}        # set current absolute
        {"key": "<resource key>", "reset": true}   # refill to max

    Returns 409 ``{"error": "no_uses", ...}`` when a spend would go below 0
    so the caller can show a non-blocking toast instead of mutating state.

    Broadcasts a ``resource_update`` WS message so other connected clients
    (mini-sheet, popped-out roll log) can re-render the pip count.
    """
    body = await request.json()
    key = str(body.get("key") or "").strip()
    if not key:
        raise HTTPException(400, "key is required")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)
    resources = list(sheet.get("resources") or [])
    idx = next(
        (i for i, r in enumerate(resources)
         if isinstance(r, dict) and (r.get("key") or "") == key),
        None,
    )
    if idx is None:
        raise HTTPException(404, "Resource not found on this sheet")

    res = dict(resources[idx])
    mx = int(res.get("max") or 0)
    cur = int(res.get("current") or 0)

    if body.get("reset"):
        # Refill to max
        new_cur = mx
        announce = False
    elif body.get("set") is not None:
        try:
            new_cur = int(body.get("set"))
        except (TypeError, ValueError):
            raise HTTPException(400, "'set' must be an integer")
        announce = False
    else:
        try:
            delta = int(body.get("delta", -1))
        except (TypeError, ValueError):
            raise HTTPException(400, "'delta' must be an integer")
        # Chat-only features (max == 0) never have insufficient uses;
        # we just announce on negative delta and keep current at 0.
        if mx <= 0:
            new_cur = 0
            announce = delta < 0
        else:
            new_cur = cur + delta
            if new_cur < 0:
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": "no_uses",
                        "key": key,
                        "name": res.get("name", ""),
                        "current": cur,
                        "max": mx,
                    },
                )
            announce = delta < 0

    # Clamp [0, max] when max > 0
    if mx > 0:
        new_cur = max(0, min(mx, new_cur))
    else:
        new_cur = max(0, new_cur)

    res["current"] = new_cur
    resources[idx] = res
    sheet["resources"] = resources
    char.sheet = sheet
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "resource_update",
        "data": {
            "character_id": char.id,
            "key": key,
            "current": new_cur,
            "max": mx,
        },
    })

    # If the caller explicitly asks for a chat announcement (or this was a
    # chat-only feature being "used"), drop a note into the roll log so the
    # rest of the table sees that the feature fired.
    note_label = ""
    if announce and (body.get("announce") is not False):
        membership = (
            db.query(CampaignMembership)
            .filter(CampaignMembership.campaign_id == campaign_id,
                    CampaignMembership.user_id == user.id)
            .first()
        )
        player_color = (
            membership.color if membership and membership.color
            else (campaign.gm_color if user.id == campaign.gm_user_id else None)
        )
        caster_color = char.color or player_color
        note_label = res.get("name", "feature")
        await hub.broadcast(campaign_id, {
            "type": "feature_used",
            "data": {
                "character_id": char.id,
                "character_name": char.name,
                "user_color": caster_color,
                "feature_name": note_label,
                "feature_desc": res.get("desc", ""),
                "source": res.get("source", ""),
                "remaining": new_cur,
                "max": mx,
            },
        })

    return {
        "ok": True,
        "key": key,
        "current": new_cur,
        "max": mx,
        "announced": bool(note_label),
    }


# ----------- API: Wild Shape / Polymorph transform -----------

# Wild Shape CR cap by druid level (RAW). Moon Druid escalates faster.
_WS_CR_DEFAULT = [
    (2, 0.25), (4, 0.5), (8, 1.0),   # lv2: 1/4, lv4: 1/2, lv8: 1
]
_WS_CR_MOON = [
    (2, 1.0), (4, 2.0), (6, 3.0), (8, 4.0), (10, 5.0), (12, 6.0),
]

def _ws_cr_cap(druid_level: int, is_moon: bool) -> float:
    """Max CR a druid of the given level can Wild Shape into (RAW)."""
    table = _WS_CR_MOON if is_moon else _WS_CR_DEFAULT
    cap = 0.0
    for lvl, cr in table:
        if druid_level >= lvl:
            cap = cr
    return cap


def _wild_shape_economy_slot(sheet: dict, source: str) -> str:
    """Action-economy slot consumed by /transform.

    Default Druid: Wild Shape = 1 action. Circle of the Moon: bonus
    action (Lv 2 RAW feature). Polymorph the spell: 1 action regardless
    of caster class — the polymorph "🦌" button on the resources panel
    is the only path that calls /transform directly without going
    through /cast_spell, so /transform must mark the chip for it too.
    """
    if source == "polymorph":
        return "action"
    for c in sheet.get("classes") or []:
        if not isinstance(c, dict):
            continue
        if (c.get("class") or "").strip().lower() != "druid":
            continue
        if "moon" in (c.get("subclass") or "").strip().lower():
            return "bonus"
    return "action"


def _cr_to_float(cr_raw) -> float:
    """Parse '1/4' / '0' / '2' / '1/2' / '' into a float. Returns 0.0 on
    anything unparseable."""
    if cr_raw is None:
        return 0.0
    s = str(cr_raw).strip()
    if not s:
        return 0.0
    if "/" in s:
        try:
            a, b = s.split("/", 1)
            return float(a) / float(b) if float(b) else 0.0
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _fetch_open5e_creature(slug: str) -> dict:
    """Pull a creature stat block from the Open5e v2 API.

    First tries a direct slug lookup (/v2/creatures/{slug}/) which works for
    v2 keys.  If that returns 404 (e.g. a v1-style slug like ``wolf`` passed
    from a Quick Pick preset), converts the slug to a display name and retries
    via a name search so transforms always succeed regardless of slug format.
    """
    import json as _json
    import urllib.request as _urlreq
    import urllib.error as _urlerr
    import urllib.parse as _urlparse

    def _get(url: str) -> dict:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=10) as r:
            return _json.loads(r.read())

    try:
        return _get(f"{_OPEN5E_BASE}/v2/creatures/{slug}/")
    except _urlerr.HTTPError as exc:
        if exc.code != 404:
            raise HTTPException(502, f"Open5e unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")

    # Direct lookup 404'd — derive a human name from the slug and search.
    # "brown-bear" → "brown bear", "giant-constrictor-snake" → "giant constrictor snake"
    name_guess = slug.replace("-", " ")
    try:
        search_url = (
            f"{_OPEN5E_BASE}/v2/creatures/"
            f"?name__icontains={_urlparse.quote(name_guess)}&limit=10&type__key=beast"
        )
        data = _get(search_url)
        results = data.get("results", [])
        name_lower = name_guess.lower()
        match = next(
            (r for r in results if (r.get("name") or "").lower() == name_lower),
            results[0] if results else None,
        )
        if match:
            key = match.get("key") or match.get("slug") or ""
            if key:
                return _get(f"{_OPEN5E_BASE}/v2/creatures/{key}/")
    except Exception:
        pass

    raise HTTPException(404, f"Creature '{slug}' not found in Open5e")


@router.post("/api/campaign/{campaign_id}/character/{char_id}/transform")
async def transform_character(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Apply a Wild Shape / Polymorph transformation to a character.

    Body:
        {
          "slug":      "wolf",                       # required
          "source":    "wild-shape" | "polymorph",   # required
          "free_pick": false                         # bypass CR cap if True
        }

    On success: snapshots the character's current HP/AC/speed/abilities/
    attacks/skills/saves into ``sheet["prior_form"]``, replaces those
    fields with the beast's stats (Wild Shape: keeps INT/WIS/CHA;
    Polymorph: replaces all six), sets ``sheet["active_form"]``, and
    decrements the ``wild-shape`` resource if ``source == "wild-shape"``.

    Returns 409 if the character is already transformed, or if the beast's
    CR exceeds the cap for this source/level (and ``free_pick`` is false).

    TODO (filed in docs/plans/class-content-status.md under Druid Wild
    Shape — "token-disguise primitive"): swap the character's Token
    row(s) to reflect the new form (label "{name} → {beast}", image_url
    to beast portrait, size from monster["size"]). The design generalises
    to a reusable ``Token.disguise`` JSON field + ``_apply_token_disguise``
    / ``_revert_token_disguise`` helpers, so the same primitive serves
    Wild Shape AND Polymorph AND Disguise Self AND Alter Self AND True
    Polymorph (each passes its own ``source`` enum value). Storage is
    per-token (not per-sheet) so a Polymorph that targets an enemy NPC
    stores the disguise on the enemy's token without needing the enemy
    to have a Character row. See the plan doc for the full helper
    signatures, edge-case checklist (multiple tokens, summons sharing
    char_id, concentration coupling, death-revert), and the 6-step
    implementation order.
    """
    body = await request.json()
    slug = str(body.get("slug") or "").strip()
    source = str(body.get("source") or "wild-shape").strip().lower()
    free_pick = bool(body.get("free_pick"))
    override = bool(body.get("override"))
    if not slug:
        raise HTTPException(400, "slug is required")
    if source not in ("wild-shape", "polymorph"):
        raise HTTPException(400, "source must be 'wild-shape' or 'polymorph'")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)

    if sheet.get("active_form"):
        existing = sheet["active_form"]
        raise HTTPException(409, f"Already transformed into {existing.get('name', 'a form')}. Revert first.")

    # v2.14.6: Phase 4 over-budget gate. Compute the slot from the
    # sheet BEFORE the (expensive) Open5e fetch so a 409 returns
    # without burning a network round-trip. Mirrors the pattern in
    # /cast_spell + /use_feature. strict mode (v2.8.0) suppresses
    # player overrides; GM clicks always bypass.
    slot = _wild_shape_economy_slot(sheet, source)
    was_used = _is_slot_used(campaign_id, char.id, slot)
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    can_override = override and not strict
    if was_used and not user_is_gm and not can_override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": slot,
            "char_name": char.name,
            "source": source,
            "label": "Wild Shape" if source == "wild-shape" else "Polymorph",
            "strict": strict,
        })

    # Fetch beast
    monster = _fetch_open5e_creature(slug)
    creature_type = _o5e_str(monster.get("type")).strip().lower()
    creature_name = (monster.get("name") or slug).strip()
    creature_cr = _cr_to_float(_o5e_cr(monster))

    # Source-specific eligibility checks
    if not free_pick:
        if source == "wild-shape":
            if creature_type != "beast":
                raise HTTPException(409, f"Wild Shape only allows beasts (got '{creature_type or 'unknown'}'). Try 'Free pick (homebrew)' to override.")
            # Find druid level on the roster + detect Moon Druid by subclass
            classes = sheet.get("classes") or []
            druid_lv = 0
            is_moon = False
            for c in classes:
                if isinstance(c, dict) and (c.get("class") or "").strip().lower() == "druid":
                    druid_lv = max(druid_lv, int(c.get("level") or 0))
                    sub = (c.get("subclass") or "").strip().lower()
                    if "moon" in sub:
                        is_moon = True
            if druid_lv < 2:
                raise HTTPException(409, "Wild Shape requires Druid level 2+. Use 'Free pick (homebrew)' to override.")
            cap = _ws_cr_cap(druid_lv, is_moon)
            if creature_cr > cap:
                raise HTTPException(
                    409,
                    f"{creature_name} (CR {_o5e_cr(monster)}) exceeds your Wild Shape CR cap of {cap}. "
                    f"Use 'Free pick (homebrew)' to override.",
                )
        else:  # polymorph
            # Polymorph targets the *target*; for a player polymorphing
            # themselves, the cap is character_level / 4 (rounded down).
            char_level = int(sheet.get("level") or 1)
            cap = max(0.0, char_level / 4.0)
            if creature_cr > cap:
                raise HTTPException(
                    409,
                    f"{creature_name} (CR {_o5e_cr(monster)}) exceeds the Polymorph CR cap of {cap} "
                    f"(target level / 4). Use 'Free pick (homebrew)' to override.",
                )
            if creature_type != "beast":
                raise HTTPException(409, f"Polymorph only targets beasts (got '{creature_type or 'unknown'}'). Try 'Free pick (homebrew)' to override.")

    # Build the beast sheet shape (reuses the GM monster importer helper)
    form_sheet = _open5e_to_dnd5e_sheet(monster)

    # Snapshot prior_form
    prior_form = {
        "hp": dict(sheet.get("hp") or {}),
        "ac": sheet.get("ac"),
        "speed": sheet.get("speed"),
        "abilities": dict(sheet.get("abilities") or {}),
        "skills": dict(sheet.get("skills") or {}),
        "saving_throws": dict(sheet.get("saving_throws") or {}),
        "attacks": list(sheet.get("attacks") or []),
        "race": sheet.get("race"),
        "initiative_bonus": sheet.get("initiative_bonus"),
        "proficiency_bonus": sheet.get("proficiency_bonus"),
        # Defenses follow the beast for the duration of the form — RAW
        # for both Wild Shape and Polymorph (beast stats replace the
        # PC's; Wild Shape preserves the PC's INT/WIS/CHA + class
        # features but not defenses). Snapshot the PC's real-form
        # defenses so revert restores them cleanly.
        "damage_resistances":     list(sheet.get("damage_resistances") or []),
        "damage_immunities":      list(sheet.get("damage_immunities") or []),
        "damage_vulnerabilities": list(sheet.get("damage_vulnerabilities") or []),
        "condition_immunities":   list(sheet.get("condition_immunities") or []),
    }

    # Apply beast stats
    new_abilities = dict(sheet.get("abilities") or {})
    if source == "wild-shape":
        # RAW: keep INT/WIS/CHA, swap STR/DEX/CON
        for ab in ("STR", "DEX", "CON"):
            if ab in form_sheet.get("abilities", {}):
                new_abilities[ab] = form_sheet["abilities"][ab]
    else:
        # Polymorph: full replace per RAW
        new_abilities = dict(form_sheet.get("abilities") or new_abilities)

    sheet["abilities"] = new_abilities
    sheet["hp"] = form_sheet.get("hp") or sheet.get("hp")
    sheet["ac"] = form_sheet.get("ac", sheet.get("ac"))
    sheet["speed"] = form_sheet.get("speed", sheet.get("speed"))
    sheet["skills"] = form_sheet.get("skills") or sheet.get("skills")
    sheet["saving_throws"] = form_sheet.get("saving_throws") or sheet.get("saving_throws")
    sheet["attacks"] = form_sheet.get("attacks") or []
    sheet["race"] = f"{creature_name} (transformed)"
    # Replace the PC's defenses with the beast's for the duration of the
    # form. ``_open5e_to_dnd5e_sheet`` already split Open5e's free-text
    # strings into lists for us; just copy them straight in.
    sheet["damage_resistances"]     = list(form_sheet.get("damage_resistances") or [])
    sheet["damage_immunities"]      = list(form_sheet.get("damage_immunities") or [])
    sheet["damage_vulnerabilities"] = list(form_sheet.get("damage_vulnerabilities") or [])
    sheet["condition_immunities"]   = list(form_sheet.get("condition_immunities") or [])
    # Initiative bonus = DEX mod under the new abilities; keep simple
    try:
        dex = int(new_abilities.get("DEX") or 10)
        sheet["initiative_bonus"] = (dex - 10) // 2
    except (TypeError, ValueError):
        pass

    from datetime import datetime as _dt
    sheet["active_form"] = {
        "slug": slug,
        "name": creature_name,
        "source": source,
        "cr": _o5e_cr(monster),
        "creature_type": creature_type,
        "started_at": _dt.now(timezone.utc).isoformat(),
        "form_sheet": form_sheet,   # full snapshot for reference / future re-apply
    }
    sheet["prior_form"] = prior_form

    # Decrement wild-shape resource if applicable
    resource_update = None
    if source == "wild-shape":
        resources = list(sheet.get("resources") or [])
        for i, r in enumerate(resources):
            if isinstance(r, dict) and (r.get("key") or "") == "wild-shape":
                if int(r.get("max") or 0) > 0:
                    new_cur = max(0, int(r.get("current") or 0) - 1)
                    resources[i] = {**r, "current": new_cur}
                    resource_update = {"key": "wild-shape", "current": new_cur, "max": int(r.get("max") or 0)}
                break
        sheet["resources"] = resources

    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "transform_update",
        "data": {
            "character_id": char.id,
            "active_form": sheet["active_form"],
            "hp": sheet["hp"],
            "ac": sheet["ac"],
            "speed": sheet["speed"],
        },
    })
    if resource_update is not None:
        await hub.broadcast(campaign_id, {
            "type": "resource_update",
            "data": {"character_id": char.id, **resource_update},
        })

    # Announce in the roll log so the table sees the transformation
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color
    icon = "🐺" if source == "wild-shape" else "🦌"
    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": f"{icon} Transformed into {creature_name}",
            "feature_desc": f"CR {_o5e_cr(monster) or '?'} {creature_type or 'creature'}. "
                            f"Form HP {sheet['hp'].get('current')}/{sheet['hp'].get('max')}, AC {sheet['ac']}.",
            "source": "Wild Shape" if source == "wild-shape" else "Polymorph",
            "remaining": 0,
            "max": 0,
            "over_budget": was_used,
            "over_budget_slot": slot if was_used else "",
        },
    })

    # Mark the action-economy slot the transform consumed. ``slot``
    # was resolved at the top of the endpoint (Moon Druid → bonus,
    # everyone else → action; polymorph → always action) before the
    # over-budget gate. ``_mark_battle_economy`` is a no-op when the
    # campaign has no active battle or the character isn't in init.
    await _mark_battle_economy(campaign_id, char.id, slot)

    return {
        "ok": True,
        "active_form": sheet["active_form"],
        "sheet": sheet,
        "economy_slot": slot,
        "over_budget": was_used,
    }


@router.post("/api/campaign/{campaign_id}/character/{char_id}/revert")
async def revert_character(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Revert a Wild Shape / Polymorph back to the character's true form.

    Restores ``sheet["prior_form"]`` onto the live sheet and clears
    ``active_form`` / ``prior_form``.

    Tolerant of "stuck" characters: if ``active_form`` is set but
    ``prior_form`` was lost (e.g. cleared by a pre-v0.35.4 sheet save
    that didn't preserve server-managed fields), the endpoint still
    clears ``active_form`` so the player can edit their sheet back to
    normal. The response carries ``stats_restored: false`` so the UI
    can warn that stats need manual fix-up. Returns 409 only when the
    character is genuinely not transformed (no active_form either).

    RAW Wild Shape: damage that drops the form to 0 HP "overflows" to
    the character's real HP. If the caller passes
    ``{"overflow_damage": N}``, that amount is subtracted from the
    restored real-form HP (clamped to 0).
    """
    body = await request.json() if (await request.body()) else {}
    try:
        overflow = max(0, int(body.get("overflow_damage") or 0))
    except (TypeError, ValueError):
        overflow = 0

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)

    prior = sheet.get("prior_form")
    active = sheet.get("active_form") or {}

    # Neither set → genuinely not transformed.
    if not isinstance(prior, dict) and not active:
        raise HTTPException(409, "Character is not currently transformed")

    # Rescue path: active_form is set but prior_form was wiped (typically
    # by a save that didn't carry it forward). Clear active_form so the
    # player can edit out of the beast form; warn via stats_restored=False.
    stats_restored = isinstance(prior, dict)

    if stats_restored:
        # Restore prior_form fields onto the live sheet
        for key in ("hp", "ac", "speed", "abilities", "skills", "saving_throws",
                    "attacks", "race", "initiative_bonus", "proficiency_bonus",
                    "damage_resistances", "damage_immunities",
                    "damage_vulnerabilities", "condition_immunities"):
            if key in prior and prior[key] is not None:
                sheet[key] = prior[key]

        # Apply RAW Wild Shape HP overflow: any damage that dropped the
        # form below 0 carries over to the character's real HP.
        if overflow > 0 and isinstance(sheet.get("hp"), dict):
            hp = dict(sheet["hp"])
            hp["current"] = max(0, int(hp.get("current") or 0) - overflow)
            sheet["hp"] = hp

    sheet["active_form"] = None
    sheet["prior_form"] = None

    from sqlalchemy.orm.attributes import flag_modified
    char.sheet = sheet
    flag_modified(char, "sheet")
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "transform_update",
        "data": {
            "character_id": char.id,
            "active_form": None,
            "hp": sheet.get("hp"),
            "ac": sheet.get("ac"),
            "speed": sheet.get("speed"),
        },
    })

    # Announce the revert in the roll log
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id,
                CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color
    prev_name = active.get("name") or "form"
    note = f"Reverted from {prev_name}"
    if overflow > 0:
        note += f" — {overflow} overflow damage to real HP"
    if not stats_restored:
        note += " — prior stats not restored, please edit manually"
    await hub.broadcast(campaign_id, {
        "type": "feature_used",
        "data": {
            "character_id": char.id,
            "character_name": char.name,
            "user_color": caster_color,
            "feature_name": "✨ Reverted to true form",
            "feature_desc": note,
            "source": active.get("source", "transform"),
            "remaining": 0, "max": 0,
        },
    })

    return {"ok": True, "sheet": sheet, "stats_restored": stats_restored}


# ----------- API: weapon / structured attacks -----------

@router.post("/api/campaign/{campaign_id}/attack")
async def use_attack(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Resolve a structured attack from a character's sheet.

    For attack-roll based attacks: rolls 1d20 + attack_bonus AND damage at the
    same time, persists both rolls (so they appear in the roll log if anyone
    pops it out), and broadcasts a single ``weapon_attack`` WS message that
    other clients render as an attack card.

    For save-based attacks (save_dc > 0 and save_ability set): skips the d20
    attack roll and broadcasts a card with a "Prompt save" button instead.
    Damage is still pre-rolled so the GM can decide who takes it.
    """
    body = await request.json()
    char_id = int(body.get("character_id") or 0)
    attack_index = int(body.get("attack_index", -1))
    if char_id <= 0 or attack_index < 0:
        raise HTTPException(400, "character_id and attack_index are required")

    # v2.20.0 Phase B: optional target_combatant_id for buff-driven
    # uplifts that need to know the target (Hunter's Mark / Hex match,
    # Colossus Slayer below-max-HP check).
    target_combatant_id = (body.get("target_combatant_id") or "").strip() or None
    # v2.49.85 — multi-target attack list. Each entry gets its own
    # fresh attack roll + damage roll (RAW weapon attacks per-target),
    # and per-target outcomes are returned in ``auto_attack_targets``.
    # The first entry rides through the existing single-target path
    # (so the legacy ``target_combatant_id``, ``hit``, ``damage_applied``
    # fields carry the primary target's outcome for backward compat).
    # Empty / single-entry list = unchanged behavior.
    target_combatant_ids_in = body.get("target_combatant_ids") or []
    if not isinstance(target_combatant_ids_in, list):
        target_combatant_ids_in = []
    target_combatant_ids_in = [
        str(x).strip() for x in target_combatant_ids_in if str(x).strip()
    ]
    if target_combatant_ids_in and not target_combatant_id:
        target_combatant_id = target_combatant_ids_in[0]
    elif target_combatant_id and not target_combatant_ids_in:
        target_combatant_ids_in = [target_combatant_id]

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Not your character")

    sheet = dict(char.sheet or {})
    attacks = list(sheet.get("attacks") or [])
    if attack_index >= len(attacks):
        raise HTTPException(404, "Attack not found")
    attack = dict(attacks[attack_index] or {})

    name = (attack.get("name") or "Attack").strip()

    # v2.6.1: Phase 4 over-budget gate. Every weapon attack consumes the
    # action slot (bonus-action attacks are filed under feature/Class
    # abilities, not /attack). See cast_spell for the matching pattern.
    # v2.8.0: strict-mode honours the same override-suppression rule.
    was_used = _is_slot_used(campaign_id, char.id, "action")
    user_is_gm = _user_is_gm(user, campaign, db)
    strict = bool(campaign.strict_action_economy)
    override = bool(body.get("override")) and not strict
    if was_used and not user_is_gm and not override:
        return JSONResponse(status_code=409, content={
            "error": "over_budget",
            "slot": "action",
            "char_name": char.name,
            "source": "attack",
            "label": name,
            "strict": strict,
        })
    attack_bonus_raw = str(attack.get("attack_bonus") or "").strip()
    damage_expr_raw = (attack.get("damage") or "").strip()
    damage_type = (attack.get("damage_type") or "").strip()
    range_str = (attack.get("range") or "").strip()
    save_dc = int(attack.get("save_dc") or 0)
    save_ability = (attack.get("save_ability") or "").strip().upper()
    desc = (attack.get("desc") or "").strip()

    is_save = save_dc > 0 and save_ability

    # v2.49.76 — Phase 2D range-enforcement gate. The attack's
    # ``range`` field (e.g. "5 ft" / "30/120 ft") is parsed against
    # the caster's + target's token positions. Same override semantics
    # as /cast_spell: GM auto-bypass, player override + not strict,
    # otherwise enforced. Skipped when no target_combatant_id is
    # supplied (the caller didn't pick a target — the existing
    # untargeted attack flow stays unchanged for "I rolled an attack
    # for the GM to assign").
    if target_combatant_id:
        _override_range = bool(body.get("override_range"))
        _range_err = _check_cast_range(
            db, campaign, char,
            range_str, name,
            target_combatant_id, None, None,
            override_range=_override_range,
            user_is_gm=user_is_gm,
            strict=strict,
        )
        if _range_err:
            return JSONResponse(status_code=409, content=_range_err)

    # v2.20.0 Phase B: detect Rage-driven advantage on STR-based
    # attacks. RAW heuristic: physical damage type + barbarian's Rage
    # buff active = advantage on the d20 attack roll. Stacks with the
    # character's existing roll_state (advantage + advantage = still
    # advantage; advantage + disadvantage = even per RAW, which
    # ``_apply_roll_state`` already handles when both directions
    # are stamped).
    rage_advantage = _has_rage_str_advantage(campaign_id, char.id, damage_type)

    # Build the to-hit expression. Accept "+5", "5", "1d4+3" etc.
    attack_total = None
    attack_breakdown = ""
    attack_roll_state_applied = ""
    if not is_save and attack_bonus_raw:
        bonus_expr = attack_bonus_raw if attack_bonus_raw.startswith(("+", "-"))\
            or any(c.isalpha() for c in attack_bonus_raw)\
            else "+" + attack_bonus_raw
        atk_expr = "1d20" + (bonus_expr if bonus_expr.startswith(("+", "-")) else "+" + bonus_expr)
        # v2.2.0: apply character roll_state to the attack d20.
        # v2.20.0: layer Rage advantage on top by stamping "a" if it
        # isn't already there. ``_apply_roll_state`` already handles
        # the kh1 / kl1 suffix; we add ours if neither direction was
        # set by the character's roll_state.
        atk_expr, attack_roll_state_applied = _apply_roll_state(
            atk_expr, (char.sheet or {}).get("roll_state"),
        )
        if rage_advantage and "kh1" not in atk_expr and "kl1" not in atk_expr:
            atk_expr = atk_expr.replace("1d20", "2d20kh1", 1)
            attack_roll_state_applied = "advantage_rage"
        try:
            r = dice_mod.roll(atk_expr)
            attack_total = r.total
            attack_breakdown = r.breakdown
        except dice_mod.DiceParseError:
            attack_total = None
            attack_breakdown = ""
    elif not is_save:
        # No bonus given — flat d20
        atk_expr, attack_roll_state_applied = _apply_roll_state(
            "1d20", (char.sheet or {}).get("roll_state"),
        )
        if rage_advantage and "kh1" not in atk_expr and "kl1" not in atk_expr:
            atk_expr = atk_expr.replace("1d20", "2d20kh1", 1)
            attack_roll_state_applied = "advantage_rage"
        try:
            r = dice_mod.roll(atk_expr)
            attack_total = r.total
            attack_breakdown = r.breakdown
        except dice_mod.DiceParseError:
            attack_total = None
            attack_breakdown = ""

    # v2.24.0 Phase T.2: detect crit from the kept d20 value. Matches
    # both "1d20[20]" (single die) and "2d20[X,20]kh1=20" (advantage
    # whose kept high was 20). Disadvantage where the LOW kept value is
    # 20 (both dice rolled 20) is also a crit — same =20 subtotal
    # pattern. Skipped for save-DC attacks (no d20 attack roll).
    is_crit = False
    if not is_save and attack_breakdown:
        import re as _re_crit
        _crit_m = _re_crit.search(
            r"\d*d20[^d=+ ]*=(\d+)", attack_breakdown, _re_crit.IGNORECASE,
        )
        if _crit_m and int(_crit_m.group(1)) == 20:
            is_crit = True

    # Pre-roll damage if a dice expression is provided. v2.24.0 Phase
    # T.2: on a crit, double the dice (not the flat modifier) — RAW
    # "all the damage dice of a critical hit are doubled" (PHB 196).
    damage_total = None
    damage_breakdown = ""
    damage_expr_effective = damage_expr_raw
    if damage_expr_raw and is_crit:
        damage_expr_effective = _double_dice_for_crit(damage_expr_raw)
    if damage_expr_effective:
        try:
            r = dice_mod.roll(damage_expr_effective)
            damage_total = r.total
            damage_breakdown = r.breakdown
        except dice_mod.DiceParseError:
            damage_total = None
            damage_breakdown = ""

    # v2.20.0 Phase B: auto-uplifts from attacker's buffs + class
    # features. Reads the hub state for active buffs (Rage / Hunter's
    # Mark / Hex) + the sheet for class_features (Colossus Slayer).
    # Each uplift is a separately-rolled die expression; the list
    # rides on the broadcast as ``auto_uplifts`` for the chat card to
    # render. Damage type per uplift varies (Hex is necrotic, Rage
    # inherits weapon type, Colossus Slayer = weapon type) — resistance
    # at damage-application time will apply per type.
    auto_uplifts = _compute_attack_auto_uplifts(
        campaign_id=campaign_id,
        attacker_char_id=char.id,
        attacker_sheet=sheet,
        target_combatant_id=target_combatant_id,
        attack_damage_type=damage_type,
    )
    # Mark Colossus Slayer "used this turn" if it was actually
    # rolled — the helper itself reads but doesn't mutate.
    if any(u.get("source") == "colossus-slayer" for u in auto_uplifts):
        await _mark_colossus_slayer_used(campaign_id, char.id)

    # Aggregate auto-uplift damage into the base damage_total so the
    # existing "Total damage" line in chat cards remains accurate
    # without needing client changes. The structured list is still
    # exposed via ``auto_uplifts`` for clients that want per-type
    # rendering.
    auto_uplift_total = 0
    for u in auto_uplifts:
        try:
            auto_uplift_total += int(u.get("total") or 0)
        except (TypeError, ValueError):
            pass
    if auto_uplift_total > 0:
        if damage_total is not None:
            damage_total = damage_total + auto_uplift_total
        else:
            damage_total = auto_uplift_total
        # Append a one-line summary to the breakdown so chat-card
        # readers see "1d12+4=10 + Rage +2 + Hunter's Mark 1d6=4" inline.
        suffix_parts = []
        for u in auto_uplifts:
            lbl = u.get("label") or u.get("source") or "Bonus"
            bd = u.get("breakdown") or ""
            suffix_parts.append(f"{lbl} {bd}")
        if suffix_parts:
            damage_breakdown = (damage_breakdown + "  +  " + "  +  ".join(suffix_parts)).strip()

    # v2.16.0: per-attack uplifts. ``bonus_damage`` (e.g. "3d6" for Sneak
    # Attack) rolls separately and rides on the broadcast as its own
    # line. ``bonus_damage_label`` ("Sneak Attack" / "Divine Smite") is
    # the chat-card attribution. ``spend_spell_slot`` ({class_slug,
    # level}) atomically decrements a spell slot — used by Divine
    # Smite to consume a Paladin slot. Slot loss happens before the
    # roll so the player can't "back out" if they miss; matches the
    # design call from B.9's plan (RAW would prompt for smite ONLY on
    # hit, but the (B) roll-time intercept that would enable that is
    # filed for later).
    bonus_damage_expr = str(body.get("bonus_damage") or "").strip()
    bonus_damage_label = str(body.get("bonus_damage_label") or "").strip()[:80]
    spend_slot = body.get("spend_spell_slot") or None
    bonus_damage_total = None
    bonus_damage_breakdown = ""
    slot_spent_class = ""
    slot_spent_level = 0

    if isinstance(spend_slot, dict):
        cslug = str(spend_slot.get("class_slug") or "").strip().lower()
        try:
            slot_level = int(spend_slot.get("level") or 0)
        except (TypeError, ValueError):
            slot_level = 0
        if not cslug or slot_level < 1:
            raise HTTPException(400, "spend_spell_slot requires class_slug + level >= 1")
        all_slots = dict(sheet.get("spell_slots") or {})
        per_class = dict(all_slots.get(cslug) or {})
        slot_key = str(slot_level)
        slot = dict(per_class.get(slot_key) or {})
        total = int(slot.get("total") or 0)
        used = int(slot.get("used") or 0)
        if total <= 0 or used >= total:
            return JSONResponse(status_code=409, content={
                "error": "no_slot",
                "class_slug": cslug,
                "level": slot_level,
                "label": bonus_damage_label or "Slot-fueled uplift",
            })
        slot["total"] = total
        slot["used"] = used + 1
        per_class[slot_key] = slot
        all_slots[cslug] = per_class
        sheet["spell_slots"] = all_slots
        slot_spent_class = cslug
        slot_spent_level = slot_level

    if bonus_damage_expr:
        # v2.24.0 Phase T.2: crit also doubles player-picked uplift
        # dice (Sneak Attack / Divine Smite). Same _double_dice_for_crit
        # helper that's applied to the base damage above.
        bonus_expr_effective = (
            _double_dice_for_crit(bonus_damage_expr) if is_crit else bonus_damage_expr
        )
        try:
            r = dice_mod.roll(bonus_expr_effective)
            bonus_damage_total = r.total
            bonus_damage_breakdown = r.breakdown
        except dice_mod.DiceParseError:
            bonus_damage_total = None
            bonus_damage_breakdown = ""

    # Persist the slot decrement (if any). The single commit at the
    # broadcast site below would be too late — by then the response
    # could be returning and the sheet state hasn't flushed.
    if slot_spent_class:
        from sqlalchemy.orm.attributes import flag_modified
        char.sheet = sheet
        flag_modified(char, "sheet")
        db.commit()

    # v2.24.0 Phase T.2: hit determination + auto-apply damage.
    # ``hit`` is computed whenever a target is set so the chat card
    # can render a Hit/Miss badge regardless of the campaign toggle.
    # Auto-apply HP changes only fires when:
    #   - campaign.auto_apply_damage is True
    #   - target_combatant_id resolves to a combatant in hub state
    #   - the attack rolled damage_total > 0
    #   - hit is True (attack_total >= target_ac)
    # Crit always hits regardless of AC. Saves (is_save=True) skip the
    # hit determination here — they're handled by T.3's save-spell
    # path (server rolls / prompts the target's save).
    attack_id = uuid.uuid4().hex[:12]
    hit = None
    target_ac = None
    damage_applied = 0
    target_hp_before = None
    target_hp_after = None
    target_resistance_applied = False
    target_dying = False
    target_dead = False
    target_combatant = _lookup_combatant(campaign_id, target_combatant_id) if target_combatant_id else None
    if target_combatant and not is_save and attack_total is not None:
        target_ac = _read_target_ac(db, campaign_id, target_combatant)
        hit = is_crit or (attack_total >= target_ac)
        if (
            hit
            and bool(campaign.auto_apply_damage)
            and (damage_total or 0) + (bonus_damage_total or 0) > 0
        ):
            total_damage = int((damage_total or 0) + (bonus_damage_total or 0))
            apply_result = await _apply_damage_to_combatant(
                db, campaign_id, target_combatant,
                total_damage, damage_type,
                is_crit=is_crit, attack_id=attack_id,
            )
            damage_applied = apply_result["applied"]
            target_hp_before = apply_result["hp_before"]
            target_hp_after = apply_result["hp_after"]
            target_resistance_applied = apply_result["resistance_applied"]
            target_dying = apply_result["is_dying"]
            target_dead = apply_result["is_dead"]

    # v2.49.85 — multi-target loop. The PRIMARY target (target #0) was
    # just resolved above; collect its outcome here, then iterate the
    # remaining targets with FRESH attack + damage rolls per RAW (each
    # weapon attack is a separate to-hit + damage roll, not a single
    # roll spread across multiple enemies). Auto-uplifts (Hex /
    # Hunter's Mark / Colossus Slayer) intentionally apply only to the
    # primary target — those are target-bound mechanics; spreading a
    # Hexed-target's +1d6 across unrelated enemies would be RAW-wrong.
    # Filed: per-target uplift detection for multi-target attacks.
    auto_attack_targets: list[dict] = []
    if not is_save and target_combatant_ids_in:
        # Primary target entry.
        if target_combatant:
            auto_attack_targets.append({
                "combatant_id": target_combatant_id or "",
                "target_name": _lookup_combatant_name(campaign_id, target_combatant_id) if target_combatant_id else "",
                "attack_total": attack_total,
                "attack_breakdown": attack_breakdown,
                "is_crit": is_crit,
                "hit": hit,
                "target_ac": target_ac,
                "damage_total": damage_total,
                "damage_breakdown": damage_breakdown,
                "damage_applied": damage_applied,
                "damage_type": damage_type,
                "target_hp_before": target_hp_before,
                "target_hp_after": target_hp_after,
                "target_resistance_applied": target_resistance_applied,
                "target_dying": target_dying,
                "target_dead": target_dead,
            })
        # Additional targets — fresh rolls + damage application each.
        for extra_tid in target_combatant_ids_in[1:]:
            extra_combatant = _lookup_combatant(campaign_id, extra_tid)
            if not extra_combatant:
                continue
            # Fresh attack roll using the same to-hit expression as the
            # primary attack (same bonus, same roll_state, same Rage
            # advantage — those are properties of the attacker + weapon,
            # not the target).
            extra_atk_total: int | None = None
            extra_atk_breakdown = ""
            if attack_bonus_raw:
                _bonus = attack_bonus_raw if attack_bonus_raw.startswith(("+", "-"))\
                    or any(c.isalpha() for c in attack_bonus_raw)\
                    else "+" + attack_bonus_raw
                _atk_expr = "1d20" + (_bonus if _bonus.startswith(("+", "-")) else "+" + _bonus)
                _atk_expr, _ = _apply_roll_state(
                    _atk_expr, (char.sheet or {}).get("roll_state"),
                )
                if rage_advantage and "kh1" not in _atk_expr and "kl1" not in _atk_expr:
                    _atk_expr = _atk_expr.replace("1d20", "2d20kh1", 1)
                try:
                    _r = dice_mod.roll(_atk_expr)
                    extra_atk_total = _r.total
                    extra_atk_breakdown = _r.breakdown
                except dice_mod.DiceParseError:
                    extra_atk_total = None
            else:
                _atk_expr, _ = _apply_roll_state(
                    "1d20", (char.sheet or {}).get("roll_state"),
                )
                if rage_advantage and "kh1" not in _atk_expr and "kl1" not in _atk_expr:
                    _atk_expr = _atk_expr.replace("1d20", "2d20kh1", 1)
                try:
                    _r = dice_mod.roll(_atk_expr)
                    extra_atk_total = _r.total
                    extra_atk_breakdown = _r.breakdown
                except dice_mod.DiceParseError:
                    extra_atk_total = None
            # Crit detection from this attack's d20.
            extra_is_crit = False
            if extra_atk_breakdown:
                import re as _re_crit_extra
                _m = _re_crit_extra.search(
                    r"\d*d20[^d=+ ]*=(\d+)", extra_atk_breakdown, _re_crit_extra.IGNORECASE,
                )
                if _m and int(_m.group(1)) == 20:
                    extra_is_crit = True
            # Fresh damage roll (with crit-doubling if applicable).
            extra_dmg_total: int | None = None
            extra_dmg_breakdown = ""
            if damage_expr_raw:
                _dmg_expr = (
                    _double_dice_for_crit(damage_expr_raw) if extra_is_crit
                    else damage_expr_raw
                )
                try:
                    _dr = dice_mod.roll(_dmg_expr)
                    extra_dmg_total = _dr.total
                    extra_dmg_breakdown = _dr.breakdown
                except dice_mod.DiceParseError:
                    extra_dmg_total = None
            # Hit determination + auto-apply damage.
            extra_ac = _read_target_ac(db, campaign_id, extra_combatant)
            extra_hit = bool(extra_is_crit or (extra_atk_total is not None and extra_atk_total >= extra_ac))
            extra_applied = 0
            extra_hp_before = None
            extra_hp_after = None
            extra_resistance = False
            extra_dying = False
            extra_dead = False
            if (
                extra_hit
                and bool(campaign.auto_apply_damage)
                and (extra_dmg_total or 0) > 0
            ):
                _ar = await _apply_damage_to_combatant(
                    db, campaign_id, extra_combatant,
                    int(extra_dmg_total or 0), damage_type,
                    is_crit=extra_is_crit, attack_id=attack_id,
                )
                extra_applied = _ar["applied"]
                extra_hp_before = _ar["hp_before"]
                extra_hp_after = _ar["hp_after"]
                extra_resistance = _ar["resistance_applied"]
                extra_dying = _ar["is_dying"]
                extra_dead = _ar["is_dead"]
            auto_attack_targets.append({
                "combatant_id": extra_combatant.get("id") or extra_tid,
                "target_name": extra_combatant.get("name") or "",
                "attack_total": extra_atk_total,
                "attack_breakdown": extra_atk_breakdown,
                "is_crit": extra_is_crit,
                "hit": extra_hit,
                "target_ac": extra_ac,
                "damage_total": extra_dmg_total,
                "damage_breakdown": extra_dmg_breakdown,
                "damage_applied": extra_applied,
                "damage_type": damage_type,
                "target_hp_before": extra_hp_before,
                "target_hp_after": extra_hp_after,
                "target_resistance_applied": extra_resistance,
                "target_dying": extra_dying,
                "target_dead": extra_dead,
            })

    # Resolve caster display info
    membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == user.id)
        .first()
    )
    player_color = (
        membership.color if membership and membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    caster_color = char.color or player_color

    payload = {
        "id": attack_id,
        "caster_user_id": user.id,
        "caster_user_name": user.display_name,
        "caster_user_color": caster_color,
        "caster_portrait_url": char.portrait_url,
        "caster_char_id": char.id,
        "caster_char_name": char.name,
        "attack_index": attack_index,
        "attack_name": name,
        "attack_bonus": attack_bonus_raw,
        "attack_total": attack_total,
        "attack_breakdown": attack_breakdown,
        "damage_expr": damage_expr_raw,
        "damage_type": damage_type,
        "damage_total": damage_total,
        "damage_breakdown": damage_breakdown,
        # v2.16.0: per-attack uplifts. ``bonus_damage_*`` is null when no
        # uplift was applied; populated when the caller passed a
        # ``bonus_damage`` expression. Chat card renders this on its own
        # line below the base damage line so the audience can attribute
        # the extra dice to Sneak Attack / Divine Smite / etc.
        "bonus_damage_label": bonus_damage_label or "",
        "bonus_damage_expr": bonus_damage_expr or "",
        "bonus_damage_total": bonus_damage_total,
        "bonus_damage_breakdown": bonus_damage_breakdown,
        "slot_spent_class": slot_spent_class,
        "slot_spent_level": slot_spent_level,
        # v2.20.0 Phase B: auto-applied uplifts from attacker's buffs +
        # class features (Rage / Hunter's Mark / Hex / Colossus Slayer).
        # Structured per-uplift list with damage_type so future chat-card
        # work can render labeled lines + resistance can apply per type.
        # Aggregate total is already folded into damage_total above.
        "auto_uplifts": auto_uplifts,
        "auto_uplift_total": auto_uplift_total,
        "target_combatant_id": target_combatant_id or "",
        # v2.23.0 Phase T.8: resolve the target's display name from the
        # hub battle state so the chat card can render "→ NAME" without
        # the client needing a second lookup. Empty string when no
        # target was set or the target isn't in init.
        "target_name": _lookup_combatant_name(campaign_id, target_combatant_id) if target_combatant_id else "",
        # v2.24.0 Phase T.2: hit determination + auto-damage results.
        # ``hit`` is None when no target was set or it's a save spell;
        # True/False otherwise. ``target_ac`` revealed only when hit is
        # determined (so blind-AC tables can hide it on miss via a
        # future setting). ``damage_applied`` is 0 when auto-apply is
        # off OR the attack missed; >0 when HP changed. ``is_crit``
        # surfaces the crit flag for the chat card's crit badge.
        "hit": hit,
        "is_crit": is_crit,
        "target_ac": target_ac,
        "damage_applied": damage_applied,
        "target_hp_before": target_hp_before,
        "target_hp_after": target_hp_after,
        "target_resistance_applied": target_resistance_applied,
        "target_dying": target_dying,
        "target_dead": target_dead,
        # Echo whether the campaign auto-applies damage so the chat
        # card can render the Hit/Miss badge differently when the
        # GM is still in "manual apply" mode (badge becomes a hint,
        # not a confirmation of HP change).
        "auto_applied": bool(campaign.auto_apply_damage),
        "range": range_str,
        "save_dc": save_dc if is_save else 0,
        "save_ability": save_ability if is_save else "",
        "desc": desc,
        "is_save": is_save,
        "roll_state_applied": attack_roll_state_applied or None,
        "over_budget": was_used,
        "over_budget_slot": "action" if was_used else "",
        # v2.49.85 — per-target outcomes for multi-target attacks.
        # Empty list for single-target attacks (the legacy fields above
        # carry the only target's outcome). For 2+ targets, the first
        # entry mirrors the legacy fields and additional entries
        # describe each subsequent target's fresh attack + damage roll.
        "auto_attack_targets": auto_attack_targets,
    }
    await hub.broadcast(campaign_id, {"type": "weapon_attack", "data": payload})
    # v2.5.5: full-sheet → init chip sync. Weapon attacks always burn the
    # action slot; bonus-action attacks (e.g. off-hand light weapon) come
    # through a separate row whose action.economy override is followed
    # in Phase 3, not here.
    await _mark_battle_economy(campaign_id, char.id, "action")
    # Return the attack + damage totals so the sheet's .atk-strike handler can
    # fire the shared roll-toast immediately. The broadcast still drives the
    # tabletop's roll-card path; this echo gives the rolling player a popup
    # without needing a WebSocket connection on the sheet page.
    return {
        "ok": True,
        "id": attack_id,
        "attack_total": attack_total,
        "attack_breakdown": attack_breakdown,
        "damage_total": damage_total,
        "damage_breakdown": damage_breakdown,
        "bonus_damage_label": bonus_damage_label or "",
        "bonus_damage_total": bonus_damage_total,
        "bonus_damage_breakdown": bonus_damage_breakdown,
        "slot_spent_class": slot_spent_class,
        "slot_spent_level": slot_spent_level,
        "auto_uplifts": auto_uplifts,
        "auto_uplift_total": auto_uplift_total,
        "target_combatant_id": target_combatant_id or "",
        # v2.23.0 Phase T.8: echo resolved target name so the rolling
        # player's local toast can include the target without WS lag.
        "target_name": _lookup_combatant_name(campaign_id, target_combatant_id) if target_combatant_id else "",
        # v2.24.0 Phase T.2: hit + auto-damage results echoed for the
        # rolling player's local toast.
        "hit": hit,
        "is_crit": is_crit,
        "target_ac": target_ac,
        "damage_applied": damage_applied,
        "target_hp_after": target_hp_after,
        "auto_applied": bool(campaign.auto_apply_damage),
        "attack_name": name,
        "damage_type": damage_type,
        "is_save": is_save,
        "save_ability": save_ability if is_save else "",
        "save_dc": save_dc if is_save else 0,
        "roll_state_applied": attack_roll_state_applied or None,
        "over_budget": was_used,
        # v2.49.85 — echo the per-target outcomes so the rolling player's
        # local toast can render the multi-target summary without WS lag.
        "auto_attack_targets": auto_attack_targets,
    }


# ----------- API: Undo applied attack damage (v2.24.0 Phase T.2) -----------

@router.post("/api/campaign/{campaign_id}/undo_attack_damage")
async def undo_attack_damage(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Revert the HP change applied by a previous /attack auto-damage.

    Body: ``{attack_id}``.

    Looks up ``attack_id`` in the in-memory ``_attack_damage_log`` (8-hour
    TTL). Applies a healing of equal magnitude back to the target — PCs
    go through ``_apply_hp_change`` (handles dying → alive transitions
    cleanly), NPCs get the hub combatant's ``hp_current`` bumped up.
    Broadcasts ``character_hp_update`` (PC) or ``battle_update`` (NPC)
    so every client refreshes.

    Returns 404 when the attack_id is unknown / expired / never had
    auto-damage applied. Auth: any campaign viewer can call (the
    in-memory log already filters to the rolling player's recent
    attacks; cross-player undo is desirable for the GM correcting a
    misclick by a player). A future commit can tighten to caster /
    GM only if play-testing reveals abuse.
    """
    body = await request.json()
    attack_id = str(body.get("attack_id") or "").strip()
    if not attack_id:
        raise HTTPException(400, "attack_id is required")
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    _purge_attack_damage_log()
    entry = _attack_damage_log.get(attack_id)
    if not entry or entry.get("campaign_id") != campaign_id:
        raise HTTPException(404, "Damage log entry not found or expired")
    applied = int(entry.get("applied") or 0)
    if applied <= 0:
        # Nothing was actually applied (e.g. miss). Treat as no-op.
        _attack_damage_log.pop(attack_id, None)
        return {"ok": True, "no_op": True}

    target_char_id = entry.get("target_char_id")
    target_combatant_id = entry.get("target_combatant_id")
    # v2.26.0 Phase T.4: heal entries undo in reverse (damage the
    # target by the same amount). Damage entries undo by healing.
    is_heal_entry = bool(entry.get("is_heal"))
    delta_sign = -1 if is_heal_entry else +1  # +1 = restore HP (undo damage); -1 = remove HP (undo heal)

    if target_char_id:
        char = db.query(Character).filter(Character.id == target_char_id).first()
        if not char:
            raise HTTPException(404, "Target character not found")
        sheet = char.sheet or {}
        hp_cur = int((sheet.get("hp") or {}).get("current") or 0)
        hp_max = int((sheet.get("hp") or {}).get("max") or 0)
        if delta_sign > 0:
            new_hp = min(hp_max, hp_cur + applied) if hp_max > 0 else (hp_cur + applied)
        else:
            new_hp = max(0, hp_cur - applied)
        result = _apply_hp_change(char, new_hp)
        db.commit()
        await hub.broadcast(campaign_id, {
            "type": "character_hp_update",
            "data": {
                "character_id": char.id,
                "hp": result["hp"],
                "delta": delta_sign * applied,
                "source": "undo_heal" if is_heal_entry else "undo_attack",
            },
        })
        _attack_damage_log.pop(attack_id, None)
        return {"ok": True, "reverted": applied, "hp_after": result["hp"]["current"],
                "was_heal": is_heal_entry}

    if target_combatant_id:
        state = hub.get_battle(campaign_id)
        if not state:
            raise HTTPException(404, "No active battle to revert into")
        target = None
        for c in state.get("combatants") or []:
            if c.get("id") == target_combatant_id:
                target = c
                break
        if target is None:
            raise HTTPException(404, "Target combatant no longer in init")
        hp_cur = int(target.get("hp_current") or 0)
        hp_max = int(target.get("hp_max") or 0)
        if delta_sign > 0:
            new_hp = min(hp_max, hp_cur + applied) if hp_max > 0 else (hp_cur + applied)
        else:
            new_hp = max(0, hp_cur - applied)
        target["hp_current"] = new_hp
        hub.set_battle(campaign_id, state)
        # v2.49.40 — see the _apply_damage_to_combatant fix for the
        # same reasoning. NPC HP changes need force_gm_sync so the
        # GM's local battle state stays in sync; otherwise the undo
        # appears to "not work" in the GM's view until they push
        # something else.
        await hub.broadcast(campaign_id, {
            "type": "battle_update",
            "data": state,
            "force_gm_sync": True,
        })
        _attack_damage_log.pop(attack_id, None)
        return {"ok": True, "reverted": applied, "hp_after": new_hp,
                "was_heal": is_heal_entry}

    raise HTTPException(404, "Damage log entry has no target reference")


# ----------- API: Open5e item proxy (weapons / armor / magic items) -----------

@router.get("/api/open5e/items")
def open5e_items_proxy(type: str = "weapons", search: str = "", limit: int = 60):
    """Search Open5e for weapons / armor / magic items.

    Items aren't part of the local Open5e cache, so this always proxies the
    public API. Type is one of "weapons", "armor", "magicitems".
    """
    cat = (type or "weapons").strip().lower()
    if cat not in ("weapons", "armor", "magicitems"):
        raise HTTPException(400, "type must be one of weapons, armor, magicitems")
    cap = max(1, min(int(limit or 60), 200))

    import json as _json
    import urllib.parse as _urlparse
    import urllib.request as _urlreq

    qs = _urlparse.urlencode({"search": search or "", "limit": cap})
    url = f"https://api.open5e.com/v1/{cat}/?{qs}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=10) as r:
            data = _json.loads(r.read())
    except Exception as e:
        raise HTTPException(502, f"Open5e fetch failed: {e}")

    import re as _re
    raw = data.get("results") or []
    items = []
    for it in raw:
        # Open5e v1 armor stores AC in the `armor_class` field as a string
        # like "16" or "11 + Dex modifier (max 2)" or "+2" for shields.
        # Pull the leading integer (ignoring sign) out for `ac` and pass the
        # original string through for the detail panel.
        ac_string = it.get("armor_class") or it.get("ac_string") or it.get("ac_display") or ""
        ac_int = 0
        if ac_string:
            m = _re.search(r"\d+", str(ac_string))
            if m:
                ac_int = int(m.group(0))
        elif it.get("ac_base") or it.get("ac"):
            try:
                ac_int = int(it.get("ac_base") or it.get("ac") or 0)
            except (TypeError, ValueError):
                ac_int = 0

        items.append({
            "slug": it.get("slug") or it.get("key") or "",
            "name": it.get("name") or "",
            "category": it.get("category") or it.get("type") or it.get("rarity") or "",
            "damage_dice": it.get("damage_dice") or "",
            "damage_type": it.get("damage_type") or "",
            "properties": ", ".join(it.get("properties") or []) if isinstance(it.get("properties"), list) else (it.get("properties") or ""),
            "range": it.get("range") or "",
            "ac": ac_int,
            "ac_string": ac_string,
            "armor_type": it.get("category") or "",
            "stealth_disadvantage": bool(it.get("stealth_disadvantage")),
            "strength_requirement": it.get("strength") or "",
            "weight": it.get("weight") or "",
            "cost": it.get("cost") or "",
            "rarity": it.get("rarity") or "",
            "desc": it.get("desc") or it.get("description") or "",
        })
    return {"results": items}


# ----------- API: concentration tracking -----------

@router.post("/api/campaign/{campaign_id}/concentration")
async def set_concentration(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Set (or replace) the concentration effect for a character.
    Allowed by the character's owner or any GM.
    Body: {character_id, spell_name, rounds, notes}
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    body = await request.json()
    char_id = int(body.get("character_id", 0))
    spell_name = str(body.get("spell_name", "")).strip()[:120]
    if not spell_name:
        raise HTTPException(400, "spell_name is required")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")

    is_gm = _user_is_gm(user, campaign, db)
    if not is_gm and char.owner_user_id != user.id:
        raise HTTPException(403, "Not your character")

    rounds_raw = body.get("rounds")
    rounds = int(rounds_raw) if rounds_raw is not None and str(rounds_raw).strip() else None
    notes = str(body.get("notes", "") or "").strip()[:200] or None

    eff = db.query(ConcentrationEffect).filter(
        ConcentrationEffect.campaign_id == campaign_id,
        ConcentrationEffect.character_id == char_id,
    ).first()
    if eff:
        eff.spell_name = spell_name
        eff.rounds_remaining = rounds
        eff.notes = notes
    else:
        eff = ConcentrationEffect(
            campaign_id=campaign_id,
            character_id=char_id,
            spell_name=spell_name,
            rounds_remaining=rounds,
            notes=notes,
        )
        db.add(eff)
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "concentration_update",
        "data": {
            "character_id": char_id,
            "spell_name": spell_name,
            "rounds_remaining": rounds,
            "notes": notes or "",
            "ended": False,
        },
    })
    return {"ok": True}


@router.delete("/api/campaign/{campaign_id}/concentration/{char_id}")
async def end_concentration(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """End the concentration effect for a character."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")

    char = db.query(Character).filter(
        Character.id == char_id, Character.campaign_id == campaign_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")

    is_gm = _user_is_gm(user, campaign, db)
    if not is_gm and char.owner_user_id != user.id:
        raise HTTPException(403, "Not your character")

    eff = db.query(ConcentrationEffect).filter(
        ConcentrationEffect.campaign_id == campaign_id,
        ConcentrationEffect.character_id == char_id,
    ).first()
    if eff:
        db.delete(eff)
        db.commit()

    await hub.broadcast(campaign_id, {
        "type": "concentration_update",
        "data": {"character_id": char_id, "ended": True},
    })

    # v2.49.41 — also drop the caster's concentration buff(s) AND
    # any paired target-side condition buffs. Pre-fix: DELETE
    # /concentration just deleted the ConcentrationEffect row + fired
    # concentration_update with ended:True, but LEFT the concentration
    # buff (Hex / Hunter's Mark / etc.) on the caster's combatant.buffs
    # list AND left paired conditions (Paralyzed via Hold Person,
    # Frightened via Fear, …) on every target's buff list. The GM had
    # to manually × out each chip. ``_remove_buff`` already handles
    # both the broadcast of the post-removal buff list AND the
    # paired-cleanup branch (via ``_drop_paired_concentration_buffs``),
    # so we just iterate the caster's concentration-tagged buffs and
    # call it once per key. Surfaced by the encounter-sim
    # test_concentration_lifecycle (v2.49.25) which had to document
    # that the chip stays put after DELETE as a known limitation.
    state = hub.get_battle(campaign_id)
    if state:
        for c in state.get("combatants") or []:
            if c.get("char_id") == char_id:
                conc_keys = [
                    (b or {}).get("key") for b in c.get("buffs") or []
                    if (b or {}).get("concentration")
                ]
                for key in conc_keys:
                    if key:
                        await _remove_buff(campaign_id, char_id, key)
                break

    return {"ok": True}


@router.post("/api/campaign/{campaign_id}/concentration/{char_id}/tick")
async def tick_concentration(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Decrement rounds_remaining by 1 at the end of the character's turn.
    If rounds_remaining reaches 0, concentration ends automatically.
    Called by the GM's battle tracker when advancing turns.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    eff = db.query(ConcentrationEffect).filter(
        ConcentrationEffect.campaign_id == campaign_id,
        ConcentrationEffect.character_id == char_id,
    ).first()
    if not eff:
        return {"ok": True, "active": False}

    # Only decrement if rounds are being tracked
    if eff.rounds_remaining is not None:
        eff.rounds_remaining = max(0, eff.rounds_remaining - 1)
        if eff.rounds_remaining == 0:
            db.delete(eff)
            db.commit()
            await hub.broadcast(campaign_id, {
                "type": "concentration_update",
                "data": {"character_id": char_id, "ended": True, "reason": "expired"},
            })
            return {"ok": True, "active": False, "ended": True}
        db.commit()

    await hub.broadcast(campaign_id, {
        "type": "concentration_update",
        "data": {
            "character_id": char_id,
            "spell_name": eff.spell_name,
            "rounds_remaining": eff.rounds_remaining,
            "notes": eff.notes or "",
            "ended": False,
        },
    })
    return {"ok": True, "active": True, "rounds_remaining": eff.rounds_remaining}


# ----------- API: battle / initiative tracker -----------

@router.put("/api/campaign/{campaign_id}/battle")
async def update_battle(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    state = await request.json()
    hub.set_battle(campaign_id, state)
    await hub.broadcast(campaign_id, {"type": "battle_update", "data": state})

    # v2.19.2 Phase C.3: mirror each PC's buff list to their sheet so
    # the full-sheet Active Effects panel reflects auto-expire ticks
    # done client-side by the GM's nextTurn handler. PUT /battle is
    # the post-tick sync point — the GM JS decrements duration_rounds
    # locally, drops expired buffs, then pushes the whole state here.
    # The mirror helper is idempotent (no-op when sheet already matches
    # the new list), so the cost is one query + at most one write per
    # PC combatant per turn-end. NPC buffs (combatants without char_id)
    # are not mirrored — they have no sheet.
    for c in (state.get("combatants") or []):
        char_id = c.get("char_id")
        if not char_id:
            continue
        _mirror_buffs_to_sheet(db, char_id, c.get("buffs") or [])

    return {"ok": True}


# ----------- API: character portrait -----------

_PORTRAIT_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "portraits"
_PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
_MAX_PORTRAIT_BYTES = 5 * 1024 * 1024
_ALLOWED_PORTRAIT_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@router.post("/campaign/{campaign_id}/character/{char_id}/portrait")
async def upload_portrait(
    campaign_id: int,
    char_id: int,
    portrait: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Cannot edit this character")
    ext = Path(portrait.filename or "").suffix.lower() or ".png"
    if ext not in _ALLOWED_PORTRAIT_EXT:
        raise HTTPException(400, "Unsupported image format (use png/jpg/webp/gif)")
    data = await portrait.read()
    if len(data) > _MAX_PORTRAIT_BYTES:
        raise HTTPException(400, "Image exceeds 5 MB limit")
    if char.portrait_url and char.portrait_url.startswith("/static/uploads/portraits/"):
        old_path = Path(__file__).resolve().parent.parent / "static" / char.portrait_url.removeprefix("/static/")
        try:
            old_path.unlink(missing_ok=True)
        except Exception:
            pass
    fname = f"{uuid.uuid4().hex}{ext}"
    (_PORTRAIT_DIR / fname).write_bytes(data)
    char.portrait_url = f"/static/uploads/portraits/{fname}"
    db.commit()
    return {"ok": True, "portrait_url": char.portrait_url}


# ----------- API: token templates -----------

_TMPL_IMG_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "token_templates"
_TMPL_IMG_DIR.mkdir(parents=True, exist_ok=True)


def _tmpl_dict(tmpl: "TokenTemplate") -> dict:
    return {
        "id": tmpl.id,
        "name": tmpl.name,
        "image_url": tmpl.image_url,
        "tags": tmpl.tags or [],
        "template": tmpl.template,
        "sheet": tmpl.sheet or {},
    }


@router.get("/api/campaign/{campaign_id}/templates")
def list_templates(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    tmpls = db.query(TokenTemplate).filter(TokenTemplate.campaign_id == campaign_id).order_by(TokenTemplate.name).all()
    return [_tmpl_dict(t) for t in tmpls]


@router.post("/api/campaign/{campaign_id}/templates")
async def create_template(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    body = await request.json()
    tmpl = TokenTemplate(
        campaign_id=campaign_id,
        name=str(body.get("name", "Unnamed"))[:200],
        tags=body.get("tags", []),
        template=body.get("template", "generic"),
        sheet=body.get("sheet", {}),
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return _tmpl_dict(tmpl)


@router.get("/api/campaign/{campaign_id}/templates/export")
def export_templates(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpls = db.query(TokenTemplate).filter(TokenTemplate.campaign_id == campaign_id).order_by(TokenTemplate.name).all()
    return {"version": 1, "campaign": campaign.name, "templates": [_tmpl_dict(t) for t in tmpls]}


@router.post("/api/campaign/{campaign_id}/templates/import")
async def import_templates(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    body = await request.json()
    raw_list = body if isinstance(body, list) else body.get("templates", [])
    if not isinstance(raw_list, list):
        raise HTTPException(400, "Expected a list of templates")
    created = []
    for td in raw_list[:100]:
        if not isinstance(td, dict):
            continue
        tpl_type = td.get("template", "generic")
        if tpl_type not in ("generic", "dnd5e"):
            tpl_type = "generic"
        tags = td.get("tags", [])
        img = td.get("image_url")
        sheet = td.get("sheet", {})
        t = TokenTemplate(
            campaign_id=campaign_id,
            name=str(td.get("name", "Imported"))[:200],
            image_url=str(img)[:500] if isinstance(img, str) and img else None,
            tags=tags if isinstance(tags, list) else [],
            template=tpl_type,
            sheet=sheet if isinstance(sheet, dict) else {},
        )
        db.add(t)
        db.flush()
        created.append(_tmpl_dict(t))
    db.commit()
    return {"ok": True, "count": len(created), "templates": created}


@router.post("/api/campaign/{campaign_id}/templates/import-monster")
async def import_open5e_monster(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    body = await request.json()
    slug = str(body.get("slug", "")).strip()
    if not slug:
        raise HTTPException(400, "slug required")
    import json as _json
    import urllib.request as _urlreq
    try:
        req = _urlreq.Request(
            f"{_OPEN5E_BASE}/v2/creatures/{slug}/",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        with _urlreq.urlopen(req, timeout=10) as r:
            monster = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    sheet = _open5e_to_dnd5e_sheet(monster)
    tags = [t for t in [_o5e_str(monster.get("type")), _o5e_str(monster.get("size")), f"CR {_o5e_cr(monster)}"] if t]
    tmpl = TokenTemplate(
        campaign_id=campaign_id,
        name=monster.get("name", slug)[:200],
        tags=tags,
        template="dnd5e",
        sheet=sheet,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return _tmpl_dict(tmpl)


@router.get("/api/user/gm-campaigns")
def user_gm_campaigns(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    primary = db.query(Campaign).filter(Campaign.gm_user_id == user.id).all()
    co_ids = [
        m.campaign_id
        for m in db.query(CampaignMembership).filter(
            CampaignMembership.user_id == user.id,
            CampaignMembership.is_gm == True,  # noqa: E712
        ).all()
    ]
    co_gm = db.query(Campaign).filter(Campaign.id.in_(co_ids)).all() if co_ids else []
    seen = {c.id for c in primary}
    return [{"id": c.id, "name": c.name} for c in primary + [c for c in co_gm if c.id not in seen]]


def _custom_monster_lite(row: dict) -> dict:
    """Return a file-based homebrew monster record in the same lite shape the
    beast picker receives from Open5e v2 (after normalisation). v2.0.0: the
    input is now a local_content dict (not a CustomMonster row)."""
    return {
        "slug": row.get("slug"),
        "name": row.get("name"),
        "cr": row.get("challenge_rating") or "0",
        "type": row.get("type") or "",
        "size": row.get("size") or "",
        "hp": row.get("hit_points"),
        "ac": row.get("armor_class"),
        "source": "Custom",
        "is_custom": True,
    }


def _cr_to_float(raw: str) -> float:
    """Convert a CR text ("1/4", "5", "0") to a float for ``cr_max``
    filtering. Unknown forms yield 0."""
    s = (raw or "").strip()
    if "/" in s:
        try:
            a, b = s.split("/", 1)
            return float(a) / float(b)
        except (ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


@router.get("/api/open5e/monsters")
def open5e_monsters_proxy(
    search: str = "",
    limit: int = 20,
    type_filter: str = "",
    cr_max: str = "",
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Proxy for the Open5e v2 creatures endpoint.

    Query params:
        search      — text match on creature name (passed through).
        limit       — page size, capped at 50.
        type_filter — when non-empty, narrows to one creature type
                      (e.g. ``beast``). Forwarded to v2 as
                      ``type__key={type_filter}``.
        cr_max      — when non-empty, narrows to creatures of CR <= the
                      given value. Accepts ``"1/4"`` etc.; converted to
                      a decimal and passed as ``cr__lte=``.

    The v2 endpoint uses different field names than v1 (``cr`` rather
    than ``challenge_rating``, ``type`` / ``size`` as ``{key,name}``
    dicts). Output is normalized so the client can rely on the legacy
    flat-string shape regardless of upstream version.

    On a 4xx from v2 (e.g. a filter param the API doesn't accept), we
    retry once without the filter so the picker stays usable.
    """
    import json as _json
    import urllib.parse as _urlparse
    import urllib.request as _urlreq
    import urllib.error as _urlerr

    # ── Campaign-scoped homebrew monsters prepend the list ───────────────
    # Apply the same filters the client wanted upstream (type, cr_max,
    # search) so a homebrew "Awakened Boulder" only shows up when the
    # picker is in beast / Free pick mode.
    custom_rows: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        records, _ = local_content.search(
            type="monsters", campaign_id=campaign_id, q=search, limit=min(abs(limit), 50),
        )
        rows = [r for r in records if r.get("_source") == "local-homebrew"]
        if type_filter:
            tf = type_filter.strip().lower()
            rows = [r for r in rows if (r.get("type") or "").lower() == tf]
        if cr_max:
            cap = _cr_to_float(cr_max)
            rows = [r for r in rows if _cr_to_float(r.get("challenge_rating") or "0") <= cap]
        for r in rows:
            custom_rows.append(_custom_monster_lite(r))
            slug_v = r.get("slug")
            if slug_v:
                custom_slugs.add(slug_v)

    def _build_url(use_filters: bool) -> str:
        # Open5e v2 is django-filter based and silently ignores DRF's
        # ``?search=`` — name matching uses ``?name__icontains=foo``
        # instead. The v1 endpoints (still used by the spell / class
        # proxies elsewhere in this file) DO honour ``?search=``, so
        # keep that pattern there but send the v2 idiom here.
        params: dict[str, str] = {
            "limit": str(min(abs(limit), 50)),
        }
        if search:
            params["name__icontains"] = search
        if use_filters and type_filter:
            params["type__key"] = type_filter.strip().lower()
        if use_filters and cr_max:
            try:
                raw = cr_max.strip()
                cr_val = (float(raw.split("/")[0]) / float(raw.split("/")[1])) if "/" in raw else float(raw)
                params["cr__lte"] = str(cr_val)
            except (TypeError, ValueError):
                pass
        return f"{_OPEN5E_BASE}/v2/creatures/?{_urlparse.urlencode(params)}"

    def _fetch(url: str) -> dict:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            return _json.loads(r.read())

    data: dict
    try:
        data = _fetch(_build_url(use_filters=True))
    except _urlerr.HTTPError as exc:
        if 400 <= exc.code < 500:
            # Filter param the API doesn't accept (or schema drift) —
            # retry once with the plain search so the picker still works.
            try:
                data = _fetch(_build_url(use_filters=False))
            except Exception as exc2:
                # If we have homebrew, prefer returning just that over a 502.
                if custom_rows:
                    return {"count": len(custom_rows), "results": custom_rows}
                raise HTTPException(502, f"Open5e unavailable: {exc2}")
        else:
            if custom_rows:
                return {"count": len(custom_rows), "results": custom_rows}
            raise HTTPException(502, f"Open5e unavailable: {exc}")
    except Exception as exc:
        if custom_rows:
            return {"count": len(custom_rows), "results": custom_rows}
        raise HTTPException(502, f"Open5e unavailable: {exc}")

    results = []
    for m in data.get("results", []):
        slug = m.get("key", m.get("slug", ""))
        # Homebrew with the same slug shadows the Open5e entry.
        if slug in custom_slugs:
            continue
        ac = m.get("armor_class", 10)
        if isinstance(ac, list) and ac:
            ac = ac[0].get("value", 10) if isinstance(ac[0], dict) else ac[0]
        results.append({
            "slug": slug,
            "name": m.get("name", ""),
            # v2 uses ``cr`` (string); v1 used ``challenge_rating``. _o5e_cr
            # handles both.
            "cr": _o5e_cr(m),
            # ``type`` / ``size`` arrive as either plain strings (v1) or
            # ``{"key", "name"}`` dicts (v2) — coerce to a string so the
            # client's ``.toLowerCase()`` filter doesn't blow up.
            "type": _o5e_str(m.get("type")),
            "size": _o5e_str(m.get("size")),
            "hp": m.get("hit_points", 0),
            "ac": ac,
            "source": m.get("document__title", m.get("document", {}).get("title", "") if isinstance(m.get("document"), dict) else ""),
        })
    return {
        "count": len(custom_rows) + data.get("count", 0),
        "results": custom_rows + results,
    }


def _creature_lite(m: dict) -> dict:
    """Slim an Open5e creature record down to the same shape returned by
    the monsters list proxy. Used by ``/api/open5e/creature/{slug}`` so
    the picker's Favorites section can render rows that look identical
    to the search results."""
    ac = m.get("armor_class", 10)
    if isinstance(ac, list) and ac:
        ac = ac[0].get("value", 10) if isinstance(ac[0], dict) else ac[0]
    return {
        "slug": m.get("key", m.get("slug", "")),
        "name": m.get("name", ""),
        "cr": _o5e_cr(m),
        "type": _o5e_str(m.get("type")),
        "size": _o5e_str(m.get("size")),
        "hp": m.get("hit_points", 0),
        "ac": ac,
        "source": m.get("document__title", m.get("document", {}).get("title", "") if isinstance(m.get("document"), dict) else ""),
    }


def _creature_full(m: dict) -> dict:
    """Extended creature shape that adds abilities, actions, and speed
    to the lite shape. Used by the beast picker detail panel."""
    base = _creature_lite(m)
    abilities = {}
    for short, full_key in [
        ("STR", "strength"), ("DEX", "dexterity"), ("CON", "constitution"),
        ("INT", "intelligence"), ("WIS", "wisdom"), ("CHA", "charisma"),
    ]:
        val = _o5e_ability(m, short.lower(), full_key)
        abilities[short] = val if val is not None else 10
    actions = []
    for a in (m.get("actions") or []):
        if isinstance(a, dict):
            name = (a.get("name") or "").strip()
            desc = (a.get("desc") or "").strip()
            if name or desc:
                actions.append({"name": name, "desc": desc})
    speed_raw = m.get("speed", {})
    speed = {}
    if isinstance(speed_raw, dict):
        for k, v in speed_raw.items():
            if v:
                speed[k] = v
    return {**base, "abilities": abilities, "actions": actions, "speed": speed}


@router.get("/api/open5e/creature/{slug}")
def open5e_creature_detail(
    slug: str,
    campaign_id: int | None = None,
    full: bool = False,
    db: Session = Depends(get_db),
):
    """Creature lookup by slug.

    When ``full=true``, the response also includes ability scores, actions,
    and speed — used by the beast picker detail panel.

    When ``campaign_id`` is supplied, a homebrew monster with this slug
    in that campaign takes precedence over the Open5e fetch.
    Returns 404 when neither source has the slug.
    """
    slug = (slug or "").strip()
    if not slug:
        raise HTTPException(400, "slug required")
    # 1. Campaign homebrew first (v2.0.0: file-based).
    if campaign_id:
        hit = local_content.resolve(slug.lower(), type="monsters", campaign_id=campaign_id)
        if hit and hit[1] == "local-homebrew":
            return _custom_monster_lite(hit[0])
    # 2. Live Open5e v2.
    import json as _json
    import urllib.request as _urlreq
    import urllib.error as _urlerr
    try:
        req = _urlreq.Request(
            f"{_OPEN5E_BASE}/v2/creatures/{slug}/",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        with _urlreq.urlopen(req, timeout=8) as r:
            monster = _json.loads(r.read())
    except _urlerr.HTTPError as exc:
        if exc.code == 404:
            raise HTTPException(404, f"Creature '{slug}' not found")
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    return _creature_full(monster) if full else _creature_lite(monster)


@router.get("/api/open5e/update-check")
def open5e_update_check(request: Request, db: Session = Depends(get_db)):
    """Compare local Open5e data counts against the live public API.

    Only meaningful when LOCAL_OPEN5E=true. Restricted to authenticated users
    so random visitors can't trigger outbound HTTP calls.
    """
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401, "Login required")
    from ..open5e_local import check_staleness
    return check_staleness()


def _fmt_hit_die(c: dict) -> str:
    hd = c.get("hit_die") or c.get("hit_dice") or ""
    if not hd:
        return ""
    s = str(hd).strip()
    if not s or s == "0":
        return ""
    if s.startswith("1d"):
        return s[1:]   # "1d6" → "d6"
    if s.startswith("d"):
        return s
    try:
        int(s)
        return f"d{s}"
    except ValueError:
        return s


def _class_detail_response(c: dict) -> dict:
    from ..open5e_local import format_class_text
    return {
        "text": format_class_text(c),
        "hit_die": _fmt_hit_die(c),
        "armor": c.get("prof_armor", "") or "",
        "weapons": c.get("prof_weapons", "") or "",
        "tools": c.get("prof_tools", "") or "",
        "saving_throws": c.get("prof_saving_throws", "") or "",
        "skills": c.get("prof_skills", "") or "",
        "spellcasting": (c.get("spellcasting_ability", "") or "").upper(),
        "equipment": c.get("equipment", "") or "",
        "features": c.get("features_json", "") or c.get("features", "") or "",
    }


@router.get("/api/open5e/class-detail")
def open5e_class_detail(
    slug: str = "",
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, get_class
    from .. import local_features
    if not slug:
        raise HTTPException(400, "slug required")
    # 1. Local-first provider chain. DB-backed homebrew (custom_classes)
    # wins over the shipped FS overrides; both shadow Open5e fallbacks.
    scopes = [f"campaign:{campaign_id}", "global"] if campaign_id else ["global"]
    record, source = local_features.resolve_class(slug, scopes=scopes, db=db)
    if record:
        return {**_class_detail_response(record), "source": source}
    # 2. Local Open5e mirror (LOCAL_OPEN5E=true).
    if is_ready():
        c = get_class(slug)
        if c:
            local_features.record_miss("class", slug, source="open5e_mirror")
            return {**_class_detail_response(c), "source": "open5e_mirror"}
    # 3. Live Open5e fallback.
    import json as _json, urllib.request as _urlreq
    try:
        req = _urlreq.Request(f"https://api.open5e.com/v1/classes/{slug}/",
                              headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            c = _json.loads(r.read())
    except Exception as exc:
        local_features.record_miss("class", slug, source="open5e_unreachable")
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    local_features.record_miss("class", slug, source="open5e_live")
    return {**_class_detail_response(c), "source": "open5e_live"}


def _subclass_response(s: dict) -> dict:
    from ..open5e_local import format_subclass_text, parse_subclass_features
    parsed = parse_subclass_features(s)
    return {
        "text": format_subclass_text(s),
        "name": parsed["name"],
        "flavor": parsed["flavor"],
        "features": parsed["features"],
    }


@router.get("/api/open5e/subclass-detail")
def open5e_subclass_detail(
    slug: str = "",
    class_slug: str = "",
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, get_subclass, format_subclass_text
    from .. import local_features
    if not slug:
        raise HTTPException(400, "slug required")
    # Build the scope priority list.  Campaign-scoped homebrew (DB
    # provider) wins over the shipped global SRD content (FS provider).
    # Caller may omit ``campaign_id`` — then only global content is
    # considered, preserving the v0.40.1 contract.
    scopes = [f"campaign:{campaign_id}", "global"] if campaign_id else ["global"]
    # 1. Local-first provider chain.  Files already match the response
    # shape; synthesise the legacy "text" summary if absent.
    record, source = local_features.resolve_subclass(class_slug, slug, scopes=scopes, db=db)
    if record:
        features = record.get("features") or []
        return {
            "text": record.get("text") or format_subclass_text({
                "name": record.get("name", ""),
                "subclass_flavor": record.get("flavor", ""),
                "feature_items": features,
            }),
            "name": record.get("name", ""),
            "flavor": record.get("flavor", ""),
            "features": features,
            "source": source,
        }
    # 2. Local Open5e mirror.
    if is_ready():
        s = get_subclass(slug)
        if s:
            local_features.record_miss("subclass", slug, class_slug=class_slug, source="open5e_mirror")
            return {**_subclass_response(s), "source": "open5e_mirror"}
    import json as _json, urllib.request as _urlreq

    def _req(url: str) -> dict:
        r = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(r, timeout=8) as resp:
            return _json.loads(resp.read())

    # 3. Live Open5e — primary: v1/subclasses/{slug}/
    try:
        s = _req(f"https://api.open5e.com/v1/subclasses/{slug}/")
        local_features.record_miss("subclass", slug, class_slug=class_slug, source="open5e_live")
        return {**_subclass_response(s), "source": "open5e_live"}
    except Exception:
        pass

    # 4. Live Open5e — fallback: archetype inside the parent class detail
    if class_slug:
        try:
            data = _req(f"https://api.open5e.com/v1/classes/{class_slug}/")
            archetypes = data.get("archetypes") or data.get("subclasses") or []
            for a in archetypes:
                if a.get("slug") == slug or a.get("name", "").lower() == slug.replace("-", " "):
                    local_features.record_miss("subclass", slug, class_slug=class_slug, source="open5e_live")
                    return {**_subclass_response(a), "source": "open5e_live"}
        except Exception:
            pass

    local_features.record_miss("subclass", slug, class_slug=class_slug, source="open5e_unreachable")
    return {"text": "", "name": "", "flavor": "", "features": [], "source": "open5e_unreachable"}


@router.get("/api/open5e/race-detail")
def open5e_race_detail(
    slug: str = "",
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, get_race, format_race_text, parse_race_traits
    from .. import local_features
    if not slug:
        raise HTTPException(400, "slug required")

    # 1. Local-first provider chain (DB + reserved FS slot).
    scopes = [f"campaign:{campaign_id}", "global"] if campaign_id else ["global"]
    record, source = local_features.resolve_race(slug, scopes=scopes, db=db)
    if record:
        # Synthesise the legacy Open5e fields the renderers expect.
        synth: dict = {
            "name": record.get("name", ""),
            "ability_bonuses": record.get("ability_bonuses") or [],
            "size": record.get("size") or "",
            "speed": record.get("speed") or {"walk": 30},
            "age": record.get("age") or "",
            "alignment": record.get("alignment") or "",
            "languages": record.get("languages") or "",
        }
        flavor = format_race_text({**synth})  # not used — overwritten below
        # Build the structured response using the existing helpers; pass
        # the same fields ``parse_race_traits`` expects, plus a synthetic
        # ``traits`` markdown blob derived from the structured trait list
        # so the parser round-trips.
        traits_list = record.get("traits_list") or []
        traits_blob = "\n\n".join(
            f"### {t.get('name','').strip()}\n{(t.get('desc') or '').strip()}"
            for t in traits_list if isinstance(t, dict) and t.get("name")
        )
        parsed = parse_race_traits({**synth, "traits": traits_blob})
        # If parse_race_traits fell back to a single "Racial Traits" card
        # because no markdown headings were found (which won't happen with
        # our synthesised blob), prefer the structured list directly.
        return {
            "text":   format_race_text({**synth, "traits": traits_blob}),
            "name":   parsed["name"] or record.get("name", ""),
            "flavor": parsed["flavor"],
            "traits": traits_list or parsed["traits"],
            "source": source,
        }

    # 2. Local Open5e mirror.
    if is_ready():
        r_data = get_race(slug)
        if r_data:
            local_features.record_miss("race", slug, source="open5e_mirror")
            parsed = parse_race_traits(r_data)
            return {
                "text":   format_race_text(r_data),
                "name":   parsed["name"],
                "flavor": parsed["flavor"],
                "traits": parsed["traits"],
                "source": "open5e_mirror",
            }

    # 3. Live Open5e fallback.
    import json as _json, urllib.request as _urlreq
    try:
        req = _urlreq.Request(f"https://api.open5e.com/v1/races/{slug}/",
                              headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            r_data = _json.loads(r.read())
    except Exception as exc:
        local_features.record_miss("race", slug, source="open5e_unreachable")
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    local_features.record_miss("race", slug, source="open5e_live")
    parsed = parse_race_traits(r_data)
    return {
        "text":   format_race_text(r_data),
        "name":   parsed["name"],
        "flavor": parsed["flavor"],
        "traits": parsed["traits"],
        "source": "open5e_live",
    }


@router.get("/api/open5e/subclasses")
def open5e_subclasses_proxy(
    search: str = "",
    class_slug: str = "",
    limit: int = 20,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, search_subclasses, _source
    cap = min(abs(limit), 100)

    # ── Campaign-scoped homebrew (DB-backed) takes the top of the list ───────
    # and shadows any Open5e / mirror entry with the same slug.  Carries
    # ``is_custom: true`` so the picker can render an authoring affordance.
    custom_results: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        # v2.0.0: file-based subclasses. The file's `slug` is the combined
        # `<class>__<sub>` form; we split for the response shape that the
        # picker UI already consumes (it shows `slug` = the bare sub_slug
        # and filters by class_slug separately).
        records, _ = local_content.search(
            type="subclass_features", campaign_id=campaign_id, q=search, limit=cap,
        )
        for rec in records:
            if rec.get("_source") != "local-homebrew":
                continue
            combined = rec.get("slug") or ""
            cls_part, _, sub_part = combined.partition("__")
            if not sub_part:
                sub_part = combined
                cls_part = rec.get("class_slug") or ""
            if class_slug and cls_part != class_slug:
                continue
            if not sub_part:
                continue
            custom_results.append({
                "name": rec.get("name") or sub_part,
                "slug": sub_part,
                "flavor": (rec.get("subclass_flavor") or rec.get("flavor") or "")[:300],
                "source": "Custom",
                "is_custom": True,
            })
            custom_slugs.add(sub_part)

    def _dedupe(results: list[dict]) -> list[dict]:
        return [r for r in results if r.get("slug") not in custom_slugs]

    if is_ready():
        items, total = search_subclasses(q=search, class_slug=class_slug, limit=cap)
        open5e_rows = [
            {"name": s.get("name", ""), "slug": s.get("slug", ""),
             "flavor": s.get("subclass_flavor", ""), "source": _source(s)}
            for s in items
        ]
        open5e_rows = _dedupe(open5e_rows)
        return {
            "count": len(custom_results) + total - (len(items) - len(open5e_rows)),
            "results": custom_results + open5e_rows,
        }
    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq

    def _req(url: str) -> dict:
        r = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(r, timeout=8) as resp:
            return _json.loads(resp.read())

    def _q_match(name: str) -> bool:
        return not search or search.lower() in name.lower()

    # ── Primary: v1/subclasses/ ───────────────────────────────────────────────
    try:
        params: dict = {"limit": cap}
        if search:     params["search"] = search
        if class_slug: params["class_slug"] = class_slug
        data = _req(f"https://api.open5e.com/v1/subclasses/?{_urlparse.urlencode(params)}")
        results = []
        for s in data.get("results", []):
            src = s.get("document__title", "") or (
                s.get("document", {}).get("title", "") if isinstance(s.get("document"), dict) else ""
            )
            results.append({"name": s.get("name", ""), "slug": s.get("slug", ""),
                             "flavor": s.get("subclass_flavor", ""), "source": src})
        results = _dedupe(results)
        return {
            "count": len(custom_results) + data.get("count", 0),
            "results": custom_results + results,
        }
    except Exception:
        pass

    # ── Fallback: extract archetypes from the class detail endpoint ───────────
    # The v1/subclasses/ endpoint is unreliable; v1/classes/{slug}/ embeds
    # archetype data (subclasses) directly in the class object.
    if class_slug:
        try:
            data = _req(f"https://api.open5e.com/v1/classes/{class_slug}/")
            archetypes = data.get("archetypes") or data.get("subclasses") or []
            results = []
            for a in archetypes:
                name = a.get("name", "")
                if not _q_match(name):
                    continue
                results.append({
                    "name": name,
                    "slug": a.get("slug", ""),
                    "flavor": a.get("subtypes_name", "") or "",
                    "source": a.get("document__title", ""),
                })
            results = _dedupe(results)
            return {
                "count": len(custom_results) + len(results),
                "results": (custom_results + results)[:cap],
            }
        except Exception:
            pass

    # ── Both Open5e sources failed — still return any homebrew we found. ─────
    return {"count": len(custom_results), "results": custom_results}


@router.get("/api/open5e/classes")
def open5e_classes_proxy(
    search: str = "",
    limit: int = 20,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, search_classes, _source
    from .. import local_features
    cap = min(abs(limit), 30)

    # Campaign-scoped homebrew classes prepend the list and shadow any
    # Open5e/mirror entry with the same slug, mirroring the subclass behavior.
    custom_results: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        records, _ = local_content.search(
            q=search or "", type="class_features",
            campaign_id=campaign_id, limit=cap,
        )
        for rec in records:
            if rec.get("_source") != "local-homebrew":
                continue
            slug = rec.get("slug")
            custom_results.append({
                "name": rec.get("name"),
                "slug": slug,
                "hit_die": rec.get("hit_die") or 8,
                "source": "Custom",
                "is_custom": True,
            })
            custom_slugs.add(slug)

    # Shipped FS classes sit between campaign homebrew and Open5e — same
    # arrangement as races. If Open5e is unreachable the picker still
    # lists the SRD baseline; if Open5e is reachable the FS entries
    # dedupe out of its results below (detail endpoint resolves to FS
    # regardless).
    fs_results: list[dict] = []
    fs_slugs: set[str] = set()
    needle = (search or "").strip().lower()
    for entry in local_features.list_local_classes():
        slug = entry.get("slug", "")
        if slug in custom_slugs:
            continue
        name = entry.get("name") or slug
        if needle and needle not in name.lower() and needle not in slug.lower():
            continue
        fs_results.append({
            "name": name,
            "slug": slug,
            "hit_die": entry.get("hit_die") or "",
            "source": "SRD",
        })
        fs_slugs.add(slug)

    def _dedupe(results: list[dict]) -> list[dict]:
        skip = custom_slugs | fs_slugs
        return [r for r in results if r.get("slug") not in skip]

    if is_ready():
        items, total = search_classes(q=search, limit=cap)
        rows = [
            {"name": c.get("name", ""), "slug": c.get("slug", ""),
             "hit_die": c.get("hit_die", ""), "source": _source(c)}
            for c in items
        ]
        rows = _dedupe(rows)
        return {
            "count": len(custom_results) + len(fs_results) + total - (len(items) - len(rows)),
            "results": custom_results + fs_results + rows,
        }
    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    url = f"https://api.open5e.com/v1/classes/?{_urlparse.urlencode({'search': search, 'limit': cap})}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        # Open5e unreachable — fall back to homebrew + shipped FS classes.
        if custom_results or fs_results:
            return {
                "count": len(custom_results) + len(fs_results),
                "results": custom_results + fs_results,
            }
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    results = []
    for c in data.get("results", []):
        src = c.get("document__title", "") or (
            c.get("document", {}).get("title", "") if isinstance(c.get("document"), dict) else ""
        )
        results.append({"name": c.get("name", ""), "slug": c.get("slug", ""),
                         "hit_die": c.get("hit_die", ""), "source": src})
    results = _dedupe(results)
    return {
        "count": len(custom_results) + len(fs_results) + data.get("count", 0),
        "results": custom_results + fs_results + results,
    }


@router.get("/api/open5e/races")
def open5e_races_proxy(
    search: str = "",
    limit: int = 20,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    from ..open5e_local import is_ready, search_races, _source
    from .. import local_features
    cap = min(abs(limit), 30)

    # Campaign-scoped homebrew races prepend the list and shadow any
    # Open5e / mirror entry with the same slug, mirroring how classes and
    # subclasses already behave.
    custom_results: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        records, _ = local_content.search(
            type="races", campaign_id=campaign_id, q=search, limit=cap,
        )
        for rec in records:
            if rec.get("_source") != "local-homebrew":
                continue
            slug = rec.get("slug") or ""
            if not slug:
                continue
            custom_results.append({
                "name": rec.get("name") or slug,
                "slug": slug,
                "size": rec.get("size") or "",
                "source": "Custom",
                "is_custom": True,
            })
            custom_slugs.add(slug)

    # Shipped FS races sit between campaign homebrew and Open5e — so if
    # Open5e is unreachable the picker still lists the SRD baseline, and
    # if Open5e is reachable the FS entries dedupe out of its results
    # below (the detail endpoint already resolves to FS regardless).
    fs_results: list[dict] = []
    fs_slugs: set[str] = set()
    needle = (search or "").strip().lower()
    for entry in local_features.list_local_races():
        slug = entry.get("slug", "")
        if slug in custom_slugs:
            continue
        name = entry.get("name") or slug
        if needle and needle not in name.lower() and needle not in slug.lower():
            continue
        fs_results.append({
            "name": name,
            "slug": slug,
            "size": entry.get("size", ""),
            "source": "SRD",
        })
        fs_slugs.add(slug)

    def _dedupe(results: list[dict]) -> list[dict]:
        skip = custom_slugs | fs_slugs
        return [r for r in results if r.get("slug") not in skip]

    if is_ready():
        items, total = search_races(q=search, limit=cap)
        rows = [
            {"name": r.get("name", ""), "slug": r.get("slug", ""),
             "size": r.get("size", ""), "source": _source(r)}
            for r in items
        ]
        rows = _dedupe(rows)
        return {
            "count": len(custom_results) + len(fs_results) + total - (len(items) - len(rows)),
            "results": custom_results + fs_results + rows,
        }
    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    url = f"https://api.open5e.com/v1/races/?{_urlparse.urlencode({'search': search, 'limit': cap})}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        # Open5e unreachable — fall back to homebrew + shipped FS races.
        if custom_results or fs_results:
            return {
                "count": len(custom_results) + len(fs_results),
                "results": custom_results + fs_results,
            }
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    results = []
    for r in data.get("results", []):
        src = r.get("document__title", "") or (
            r.get("document", {}).get("title", "") if isinstance(r.get("document"), dict) else ""
        )
        results.append({"name": r.get("name", ""), "slug": r.get("slug", ""),
                         "size": r.get("size", ""), "source": src})
    results = _dedupe(results)
    return {
        "count": len(custom_results) + len(fs_results) + data.get("count", 0),
        "results": custom_results + fs_results + results,
    }


# ── Backgrounds proxy (with homebrew merge) ─────────────────────────────────
#
# Open5e v1 ships a ``/v1/backgrounds/`` endpoint with name, desc, the four
# proficiency strings, equipment, and feature/feature_desc. We expose two
# routes mirroring the class / subclass pattern: a list endpoint that
# searches by name and a per-slug detail endpoint, both honouring
# ``campaign_id`` to prepend / shadow with homebrew.


@router.get("/api/open5e/backgrounds")
def open5e_backgrounds_proxy(
    search: str = "",
    limit: int = 20,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    cap = min(abs(limit), 50)
    custom_results: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        records, _ = local_content.search(
            type="backgrounds", campaign_id=campaign_id, q=search, limit=cap,
        )
        for rec in records:
            if rec.get("_source") != "local-homebrew":
                continue
            slug = rec.get("slug") or ""
            if not slug:
                continue
            custom_results.append({
                "name": rec.get("name") or slug,
                "slug": slug,
                "feature": rec.get("feature_name") or "",
                "source": "Custom",
                "is_custom": True,
            })
            custom_slugs.add(slug)

    def _dedupe(results: list[dict]) -> list[dict]:
        return [r for r in results if r.get("slug") not in custom_slugs]

    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    params: dict = {"limit": cap}
    if search:
        params["search"] = search
    url = f"https://api.open5e.com/v1/backgrounds/?{_urlparse.urlencode(params)}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        # Homebrew-only when Open5e is down.
        if custom_results:
            return {"count": len(custom_results), "results": custom_results}
        raise HTTPException(502, f"Open5e unavailable: {exc}")

    results = []
    for b in data.get("results", []):
        src = b.get("document__title", "") or (
            b.get("document", {}).get("title", "") if isinstance(b.get("document"), dict) else ""
        )
        results.append({
            "name": b.get("name", ""),
            "slug": b.get("slug", ""),
            "feature": b.get("feature", ""),
            "source": src,
        })
    results = _dedupe(results)
    return {
        "count": len(custom_results) + data.get("count", 0),
        "results": custom_results + results,
    }


@router.get("/api/open5e/background/{slug}")
def open5e_background_detail(
    slug: str,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    slug = (slug or "").strip()
    if not slug:
        raise HTTPException(400, "slug required")
    from .. import local_features
    scopes = [f"campaign:{campaign_id}", "global"] if campaign_id else ["global"]
    record, source = local_features.resolve_background(slug, scopes=scopes, db=db)
    if record:
        return {**record, "source": source}
    import json as _json, urllib.request as _urlreq, urllib.error as _urlerr
    try:
        req = _urlreq.Request(
            f"https://api.open5e.com/v1/backgrounds/{slug}/",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except _urlerr.HTTPError as exc:
        if exc.code == 404:
            raise HTTPException(404, f"Background '{slug}' not found")
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    return {
        "slug": data.get("slug", slug),
        "name": data.get("name", ""),
        "desc": data.get("desc", ""),
        "skill_proficiencies": data.get("skill_proficiencies", ""),
        "tool_proficiencies": data.get("tool_proficiencies", ""),
        "languages": data.get("languages", ""),
        "equipment": data.get("equipment", ""),
        "feature": data.get("feature", ""),
        "feature_desc": data.get("feature_desc", ""),
        "source": "open5e_live",
    }


# ── Feats proxy (with homebrew merge) ───────────────────────────────────────


@router.get("/api/open5e/feats")
def open5e_feats_proxy(
    search: str = "",
    limit: int = 20,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    cap = min(abs(limit), 50)
    custom_results: list[dict] = []
    custom_slugs: set[str] = set()
    if campaign_id:
        # v2.0.0: campaign-scoped homebrew lives in the file-based content tier.
        # local_content.search returns dicts whose key set matches the Pydantic
        # Feat model, plus `_source` ("local-homebrew" for files we wrote, or
        # "local-srd" for shipped content). We only count `local-homebrew` here
        # to preserve the "Custom" badge the picker UI uses.
        records, _ = local_content.search(
            type="feats", campaign_id=campaign_id, q=search, limit=cap,
        )
        for rec in records:
            if rec.get("_source") != "local-homebrew":
                continue
            slug = rec.get("slug") or ""
            if not slug:
                continue
            custom_results.append({
                "name": rec.get("name") or slug,
                "slug": slug,
                "prerequisite": rec.get("prerequisite") or "",
                "source": "Custom",
                "is_custom": True,
            })
            custom_slugs.add(slug)

    def _dedupe(results: list[dict]) -> list[dict]:
        return [r for r in results if r.get("slug") not in custom_slugs]

    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    params: dict = {"limit": cap}
    if search:
        params["search"] = search
    url = f"https://api.open5e.com/v1/feats/?{_urlparse.urlencode(params)}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        if custom_results:
            return {"count": len(custom_results), "results": custom_results}
        raise HTTPException(502, f"Open5e unavailable: {exc}")

    results = []
    for f in data.get("results", []):
        src = f.get("document__title", "") or (
            f.get("document", {}).get("title", "") if isinstance(f.get("document"), dict) else ""
        )
        results.append({
            "name": f.get("name", ""),
            "slug": f.get("slug", ""),
            "prerequisite": f.get("prerequisite", ""),
            "source": src,
        })
    results = _dedupe(results)
    return {
        "count": len(custom_results) + data.get("count", 0),
        "results": custom_results + results,
    }


@router.get("/api/open5e/feat/{slug}")
def open5e_feat_detail(
    slug: str,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    slug = (slug or "").strip()
    if not slug:
        raise HTTPException(400, "slug required")
    from .. import local_features
    scopes = [f"campaign:{campaign_id}", "global"] if campaign_id else ["global"]
    record, source = local_features.resolve_feat(slug, scopes=scopes, db=db)
    if record:
        return {**record, "source": source}
    import json as _json, urllib.request as _urlreq, urllib.error as _urlerr
    try:
        req = _urlreq.Request(
            f"https://api.open5e.com/v1/feats/{slug}/",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except _urlerr.HTTPError as exc:
        if exc.code == 404:
            raise HTTPException(404, f"Feat '{slug}' not found")
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    return {
        "slug": data.get("slug", slug),
        "name": data.get("name", ""),
        "prerequisite": data.get("prerequisite", ""),
        "desc": data.get("desc", ""),
        "source": "open5e_live",
    }


@router.get("/api/open5e/spells")
def open5e_spells_proxy(
    search: str = "",
    limit: int = 20,
    spell_list: str = "",
    level: int = -1,
    campaign_id: int | None = None,
    db: Session = Depends(get_db),
):
    import re as _re

    def _fmt_spell(s: dict) -> dict:
        desc = s.get("desc", "")
        desc = _re.sub(r"[*_#`]+", "", desc).replace("|", ",").replace("\n", " ").strip()
        dmg_m = _re.search(r"(\d+d\d+(?:\s*[+-]\s*\d+)?)\s+(\w+)\s+damage", desc, _re.IGNORECASE)
        damage = f"{dmg_m.group(1).replace(' ', '')} {dmg_m.group(2).lower()}" if dmg_m else ""
        _save_map = {"strength": "STR", "dexterity": "DEX", "constitution": "CON",
                     "intelligence": "INT", "wisdom": "WIS", "charisma": "CHA"}
        save_m = _re.search(
            r"\b(strength|dexterity|constitution|intelligence|wisdom|charisma)\s+saving\s+throw",
            desc, _re.IGNORECASE)
        save_ability = _save_map.get(save_m.group(1).lower(), "") if save_m else ""

        # Healing detection (only on non-damage spells to avoid Vampiric Touch etc.)
        healing = ""
        aoe_targets = 1
        if not damage:
            heal_m = _re.search(
                r"(?:regain|restore|heal)s?\s+(\d+d\d+(?:\s*[+-]\s*\d+)?)\s+hit\s+points",
                desc, _re.IGNORECASE)
            if not heal_m:
                heal_m = _re.search(r"(\d+d\d+(?:\s*[+-]\s*\d+)?)\s+hit\s+points", desc, _re.IGNORECASE)
            if heal_m:
                healing = heal_m.group(1).replace(" ", "")
                aoe_m = _re.search(
                    r"up\s+to\s+(\d+)\s+(?:creatures?|targets?|willing\s+creatures?)",
                    desc, _re.IGNORECASE)
                aoe_targets = int(aoe_m.group(1)) if aoe_m else 1

        # If the input record already carries a structured `actions` array
        # (i.e. it came from the file-based local_content tier), pass it through
        # so the client renders explicit Action buttons rather than re-deriving
        # them from regex-scraped legacy fields.
        explicit_actions = s.get("actions") or []

        return {
            "slug": s.get("slug", ""),
            "name": s.get("name", ""),
            "level": s.get("level_int", s.get("spell_level", 0)),
            "school": s.get("school", ""),
            "casting_time": s.get("casting_time", ""),
            "range": s.get("range", ""),
            "duration": s.get("duration", ""),
            "components": s.get("components", ""),
            "damage": damage,
            "save_ability": save_ability,
            "healing": healing,
            "aoe_targets": aoe_targets,
            "desc": desc,
            "actions": explicit_actions,
        }

    # ── Local-content tier ──────────────────────────────────────────────────
    # Two-tier resolver: homebrew volume files (per-campaign + global) first,
    # then shipped SRD files. Only if both miss do we fall through to the
    # Open5e mirror / live API below.
    from .. import local_content as _lc
    local_results, _local_total = _lc.search(
        q=search,
        type="spells",
        campaign_id=campaign_id,
        limit=200,  # search broadly; level/spell_list filter below applies
    )
    if local_results:
        items = local_results
        if spell_list:
            sl = spell_list.lower()
            items = [s for s in items
                     if sl in [x.lower() for x in (s.get("spell_lists") or [])]]
        if level >= 0:
            items = [s for s in items
                     if (s.get("level_int") or s.get("spell_level") or 0) == level]
        if items:
            return {"count": len(items), "results": [_fmt_spell(s) for s in items[:min(abs(limit), 100)]]}
        # Local tier loaded records but none matched the class/level filter — fall
        # through to Open5e so the picker isn't artificially empty.

    from ..open5e_local import is_ready, search_spells, get_spells_by_slugs
    cap = min(abs(limit), 100)

    # ── Homebrew-class spell list ────────────────────────────────────────────
    # When the picker filters by class slug AND a campaign is supplied AND
    # that (campaign, slug) names a homebrew class, return the spells from
    # the GM's curated list rather than asking Open5e for "spells whose
    # spell_lists field contains <homebrew slug>" (which would always be
    # empty — Open5e doesn't know about the homebrew).
    if spell_list and campaign_id:
        _hb = local_content.resolve(spell_list.lower(), type="class_features", campaign_id=campaign_id)
        homebrew = _hb[0] if (_hb and _hb[1] == "local-homebrew") else None
        if homebrew:
            curated = homebrew.get("spell_list") or []
            if not curated:
                return {"count": 0, "results": []}
            # Local mirror is preferred — single in-memory lookup.  Without
            # it we'd need N parallel HTTP fetches, which is slow enough to
            # warrant requiring the mirror for homebrew lookups.
            if is_ready():
                spells = get_spells_by_slugs(curated)
            else:
                # Fall back to sequential Open5e fetches with a short
                # timeout each; tolerate individual failures.
                import json as _json, urllib.request as _urlreq
                spells = []
                for slug in curated[:cap * 2]:  # cap to a sane upper bound
                    try:
                        req = _urlreq.Request(
                            f"https://api.open5e.com/v1/spells/{slug}/",
                            headers={"User-Agent": "SimpleVTT/1.0"},
                        )
                        with _urlreq.urlopen(req, timeout=4) as r:
                            spells.append(_json.loads(r.read()))
                    except Exception:
                        continue
            # Apply search + level filters in memory.
            if search:
                q = search.lower()
                spells = [s for s in spells if q in (s.get("name") or "").lower()]
            if level >= 0:
                spells = [
                    s for s in spells
                    if (s.get("level_int") or s.get("spell_level") or 0) == level
                ]
            total = len(spells)
            return {"count": total, "results": [_fmt_spell(s) for s in spells[:cap]]}

    # Try the local mirror first when enabled. If it returns zero results
    # for a class+level filter (e.g. the sync ran before a content drop,
    # or the mirror is incomplete) fall through to the live API instead
    # of silently leaving the picker empty.
    if is_ready():
        items, total = search_spells(q=search, limit=cap, spell_list=spell_list, level=level)
        if total > 0:
            return {"count": total, "results": [_fmt_spell(s) for s in items]}
        # Local returned nothing — log + try live as a fallback.
        log.info(
            "Local Open5e spells returned 0 results (spell_list=%r, level=%r, search=%r); "
            "falling back to live API.",
            spell_list, level, search,
        )
    import json as _json, urllib.parse as _urlparse, urllib.request as _urlreq
    params: dict = {"limit": cap}
    if search:     params["search"]      = search
    if spell_list: params["spell_lists"] = spell_list.lower()  # Open5e v1 param name
    if level >= 0: params["level_int"]   = level               # Open5e v1 integer level field
    url = f"https://api.open5e.com/v1/spells/?{_urlparse.urlencode(params)}"
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with _urlreq.urlopen(req, timeout=15) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    return {"count": data.get("count", 0), "results": [_fmt_spell(s) for s in data.get("results", [])]}


@router.get("/api/open5e/conditions")
def open5e_conditions_proxy():
    """Return all D&D 5e conditions (small static list — always fetched in full)."""
    def _fmt(c: dict) -> dict:
        return {"slug": c.get("slug", ""), "name": c.get("name", ""), "desc": c.get("desc", "")}

    from ..open5e_local import is_ready, search_conditions
    if is_ready():
        items, _ = search_conditions(limit=50)
        return {"results": [_fmt(c) for c in items]}

    import json as _json, urllib.request as _urlreq
    try:
        req = _urlreq.Request(
            "https://api.open5e.com/v1/conditions/?limit=50",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        with _urlreq.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e unavailable: {exc}")
    return {"results": [_fmt(c) for c in data.get("results", [])]}


def _o5e_str(v) -> str:
    """Coerce an Open5e v1/v2 attribute to a plain string.

    v2 returns ``type`` and ``size`` (and several other taxonomy-ish
    fields) as ``{"key": "beast", "name": "Beast"}`` objects rather
    than the v1 plain-string form. Anything that calls
    ``.toLowerCase()`` / ``.strip()`` on the raw value crashes on v2
    data. This helper normalizes both shapes to a display string;
    callers downstream can ``.lower()`` / ``.strip()`` it freely.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return str(v.get("name") or v.get("key") or "")
    return str(v)


def _o5e_cr(m: dict) -> str:
    """Read the challenge rating regardless of v1/v2 shape.

    v2 (creatures endpoint) uses ``cr`` — a string like ``"1/4"`` or
    ``"5"``. v1 uses ``challenge_rating``. Returns the raw string so
    callers can decide whether to render or parse to a float.
    """
    raw = m.get("cr")
    if raw is None or raw == "":
        raw = m.get("challenge_rating")
    if raw is None:
        return "0"
    return str(raw)


def _o5e_ability(m: dict, ability_key: str, full_key: str) -> int | None:
    """Read a single ability score in a way that works for both API versions.

    - v1 puts each score at the top level: ``m["strength"] = 12``.
    - v2 nests them under ``ability_scores``: ``m["ability_scores"]["str"] = 12``.

    Returns the score as an int, or None if not present. Caller decides
    the default.
    """
    nested = m.get("ability_scores")
    if isinstance(nested, dict):
        # Try all known key formats: lowercase short ("str"), uppercase short
        # ("STR"), and full name ("strength") — different Open5e builds vary.
        for candidate in (ability_key, ability_key.upper(), full_key):
            val = nested.get(candidate)
            if val is not None:
                try:
                    return int(val)
                except (TypeError, ValueError):
                    pass
    val = m.get(full_key)
    if val is not None:
        try:
            return int(val)
        except (TypeError, ValueError):
            pass
    return None


def _o5e_save_prof(m: dict, ability_key: str, full_save_key: str) -> bool:
    """True when the creature is proficient with a given saving throw.

    v1 exposes ``strength_save = 4`` (a final bonus, presence implies
    proficiency). v2 nests them under ``saving_throws`` keyed by
    short ability name (``str``, ``dex``, …) with a numeric value when
    proficient.
    """
    nested = m.get("saving_throws")
    if isinstance(nested, dict) and nested.get(ability_key) is not None:
        return True
    return m.get(full_save_key) is not None


def _o5e_skill_prof(m: dict, snake_key: str) -> bool:
    """True when the creature is proficient with a skill.

    v1 surfaces e.g. ``perception = 5`` at the top level. v2 nests
    them under ``skill_bonuses``."""
    nested = m.get("skill_bonuses")
    if isinstance(nested, dict) and nested.get(snake_key) is not None:
        return True
    return m.get(snake_key) is not None


def _open5e_to_dnd5e_sheet(m: dict) -> dict:
    import copy
    import re
    from ..sheet_templates import DND5E_TEMPLATE

    sheet = copy.deepcopy(DND5E_TEMPLATE)

    # HP
    hp = int(m.get("hit_points") or 10)
    sheet["hp"] = {"current": hp, "max": hp, "temp": 0}

    # AC — integer or list of dicts in v2
    ac = m.get("armor_class", 10)
    if isinstance(ac, list) and ac:
        ac = ac[0].get("value", 10) if isinstance(ac[0], dict) else ac[0]
    if isinstance(ac, str):
        digs = re.search(r"\d+", ac)
        ac = int(digs.group()) if digs else 10
    sheet["ac"] = int(ac or 10)

    # Speed — dict {"walk": 30} or string
    speed_raw = m.get("speed", {})
    if isinstance(speed_raw, dict):
        walk = speed_raw.get("walk", 30)
        if isinstance(walk, str):
            digs = re.search(r"\d+", walk)
            walk = int(digs.group()) if digs else 30
        sheet["speed"] = int(walk or 30)
    elif isinstance(speed_raw, (int, float)):
        sheet["speed"] = int(speed_raw)
    else:
        digs = re.search(r"\d+", str(speed_raw))
        sheet["speed"] = int(digs.group()) if digs else 30

    # Ability scores — handle both v1 (top-level) and v2 (nested under
    # ``ability_scores``). v2 uses 3-letter keys (``str``, ``dex``, …);
    # v1 uses the full names.
    for ab, short, full in [
        ("STR", "str", "strength"),
        ("DEX", "dex", "dexterity"),
        ("CON", "con", "constitution"),
        ("INT", "int", "intelligence"),
        ("WIS", "wis", "wisdom"),
        ("CHA", "cha", "charisma"),
    ]:
        val = _o5e_ability(m, short, full)
        if val is not None:
            sheet["abilities"][ab] = val

    # CR → proficiency bonus
    cr_str = _o5e_cr(m)
    try:
        cr_val = float(cr_str.split("/")[0]) / float(cr_str.split("/")[1]) if "/" in cr_str else float(cr_str)
    except Exception:
        cr_val = 0.0
    sheet["proficiency_bonus"] = (
        2 if cr_val < 5 else 3 if cr_val < 9 else 4 if cr_val < 13 else
        5 if cr_val < 17 else 6 if cr_val < 21 else 7 if cr_val < 25 else
        8 if cr_val < 29 else 9
    )

    # Creature meta
    sheet["race"] = f"{_o5e_str(m.get('size'))} {_o5e_str(m.get('type'))}".strip()
    sheet["background"] = _o5e_str(m.get("alignment"))

    # Saving throw proficiencies — v1 has ``strength_save`` etc. at the top
    # level; v2 nests under ``saving_throws.{short}``.
    for ab, short, full in [
        ("STR", "str", "strength_save"),
        ("DEX", "dex", "dexterity_save"),
        ("CON", "con", "constitution_save"),
        ("INT", "int", "intelligence_save"),
        ("WIS", "wis", "wisdom_save"),
        ("CHA", "cha", "charisma_save"),
    ]:
        if _o5e_save_prof(m, short, full):
            sheet["saving_throws"][ab] = True

    # Skill proficiencies — v1 has ``perception`` etc. at top level; v2
    # nests under ``skill_bonuses.<snake>``.
    skill_map = {
        "acrobatics": "Acrobatics", "animal_handling": "Animal Handling", "arcana": "Arcana",
        "athletics": "Athletics", "deception": "Deception", "history": "History",
        "insight": "Insight", "intimidation": "Intimidation", "investigation": "Investigation",
        "medicine": "Medicine", "nature": "Nature", "perception": "Perception",
        "performance": "Performance", "persuasion": "Persuasion", "religion": "Religion",
        "sleight_of_hand": "Sleight of Hand", "stealth": "Stealth", "survival": "Survival",
    }
    for api_key, skill_name in skill_map.items():
        if _o5e_skill_prof(m, api_key) and skill_name in sheet["skills"]:
            sheet["skills"][skill_name]["proficient"] = True

    # Actions → attacks
    attacks = []
    for action in (m.get("actions") or []):
        desc = action.get("desc", "")
        bonus_m = re.search(r"([+-]\d+) to hit", desc)
        dmg_m = re.search(r"(\d+d\d+(?:\s*[+-]\s*\d+)?)\s+\w+\s+damage", desc)
        attacks.append({
            "name": action.get("name", ""),
            "bonus": bonus_m.group(1) if bonus_m else "",
            "damage": dmg_m.group(1).replace(" ", "") if dmg_m else "",
        })
    sheet["attacks"] = attacks

    # Special abilities → features
    features = []
    for sa in (m.get("special_abilities") or []):
        name = sa.get("name", "")
        desc = sa.get("desc", "")
        if name or desc:
            features.append(f"{name}: {desc}" if name else desc)
    sheet["features"] = "\n\n".join(features)

    # Defenses — Open5e returns these as free-text strings (e.g.
    # ``"fire, cold"`` or ``"bludgeoning, piercing, and slashing from
    # nonmagical attacks not made with silvered weapons"``). Split on
    # commas and " and " for the common simple-list cases; anything
    # more complex lands as a single custom chip the player can clean
    # up after transforming. ``normalize_dnd5e_sheet`` later dedupes
    # case-insensitively and caps the lists.
    def _split_defense(raw: object) -> list[str]:
        if not raw:
            return []
        if isinstance(raw, list):
            parts = [str(p) for p in raw]
        else:
            text = str(raw)
            # Replace " and " with comma to merge into a single split below.
            text = re.sub(r"\s+and\s+", ", ", text)
            parts = re.split(r"[,;]", text)
        return [p.strip() for p in parts if p and p.strip()]

    sheet["damage_resistances"]     = _split_defense(m.get("damage_resistances"))
    sheet["damage_immunities"]      = _split_defense(m.get("damage_immunities"))
    sheet["damage_vulnerabilities"] = _split_defense(m.get("damage_vulnerabilities"))
    sheet["condition_immunities"]   = _split_defense(m.get("condition_immunities"))

    # Notes: stat block meta (defenses are now first-class fields above,
    # so we don't dump them into Notes — leaves room for languages /
    # senses / hit dice / CR).
    parts = []
    for label, key in [
        ("Hit Dice", "hit_dice"), ("CR", "challenge_rating"),
        ("Languages", "languages"), ("Senses", "senses"),
    ]:
        if m.get(key):
            parts.append(f"{label}: {m[key]}")
    sheet["notes"] = "\n".join(parts)

    return sheet


@router.patch("/api/campaign/{campaign_id}/templates/{tmpl_id}")
async def update_template(
    campaign_id: int,
    tmpl_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpl = db.query(TokenTemplate).filter(TokenTemplate.id == tmpl_id, TokenTemplate.campaign_id == campaign_id).first()
    if not tmpl:
        raise HTTPException(404, "Template not found")
    body = await request.json()
    if "name" in body:
        tmpl.name = str(body["name"])[:200]
    if "tags" in body:
        tmpl.tags = body["tags"] if isinstance(body["tags"], list) else []
    if "template" in body and body["template"] in ("generic", "dnd5e"):
        tmpl.template = body["template"]
    if "sheet" in body and isinstance(body["sheet"], dict):
        tmpl.sheet = body["sheet"]
    db.commit()
    return _tmpl_dict(tmpl)


@router.delete("/api/campaign/{campaign_id}/templates/{tmpl_id}")
async def delete_template(
    campaign_id: int,
    tmpl_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpl = db.query(TokenTemplate).filter(TokenTemplate.id == tmpl_id, TokenTemplate.campaign_id == campaign_id).first()
    if not tmpl:
        raise HTTPException(404, "Template not found")
    if tmpl.image_url and tmpl.image_url.startswith("/static/uploads/token_templates/"):
        p = Path(__file__).resolve().parent.parent / "static" / tmpl.image_url.removeprefix("/static/")
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    db.delete(tmpl)
    db.commit()
    return {"ok": True}


@router.post("/api/campaign/{campaign_id}/templates/{tmpl_id}/image")
async def upload_template_image(
    campaign_id: int,
    tmpl_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpl = db.query(TokenTemplate).filter(TokenTemplate.id == tmpl_id, TokenTemplate.campaign_id == campaign_id).first()
    if not tmpl:
        raise HTTPException(404, "Template not found")
    ext = Path(image.filename or "").suffix.lower() or ".png"
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise HTTPException(400, "Unsupported image type")
    data = await image.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image exceeds 5 MB")
    if tmpl.image_url and tmpl.image_url.startswith("/static/uploads/token_templates/"):
        old = Path(__file__).resolve().parent.parent / "static" / tmpl.image_url.removeprefix("/static/")
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass
    fname = f"{uuid.uuid4().hex}{ext}"
    (_TMPL_IMG_DIR / fname).write_bytes(data)
    tmpl.image_url = f"/static/uploads/token_templates/{fname}"
    db.commit()
    return {"ok": True, "image_url": tmpl.image_url}


@router.get("/api/campaign/{campaign_id}/templates/{tmpl_id}/sheet", response_class=HTMLResponse)
def get_template_sheet(
    campaign_id: int,
    tmpl_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Returns sheet HTML for editing a token template's sheet data."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpl = db.query(TokenTemplate).filter(TokenTemplate.id == tmpl_id, TokenTemplate.campaign_id == campaign_id).first()
    if not tmpl:
        raise HTTPException(404, "Template not found")

    class _Char:
        pass

    char_obj = _Char()
    char_obj.id = tmpl.id
    char_obj.name = tmpl.name
    char_obj.portrait_url = tmpl.image_url
    char_obj.template = tmpl.template

    tname = "sheet_dnd5e.html" if tmpl.template == "dnd5e" else "sheet_generic.html"
    tmpl_sheet = tmpl.sheet or get_template(tmpl.template)
    if tmpl.template == "dnd5e":
        normalize_dnd5e_sheet(tmpl_sheet)
    return templates.TemplateResponse(tname, {
        "request": request,
        "char": char_obj,
        "sheet": tmpl_sheet,
        "can_edit": True,
        "campaign": campaign,
        "sheet_save_url": f"/api/campaign/{campaign_id}/templates/{tmpl_id}",
        "sheet_save_method": "PATCH",
        "portrait_upload_url": f"/api/campaign/{campaign_id}/templates/{tmpl_id}/image",
        "class_roster": class_levels_summary(tmpl_sheet) if tmpl.template == "dnd5e" else [],
        "animate_gifs": user.animate_gifs,
    })


# ----------- API: character sheets -----------

@router.get("/api/campaign/{campaign_id}/character/{char_id}", response_class=HTMLResponse)
def get_sheet(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Forbidden")
    is_gm = _user_is_gm(user, campaign, db)
    can_edit = is_gm or char.owner_user_id == user.id
    template_name = "sheet_dnd5e.html" if char.template == "dnd5e" else "sheet_generic.html"
    sheet = char.sheet or get_template(char.template)
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(sheet)
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "char": char,
            "sheet": sheet,
            "can_edit": can_edit,
            "is_gm": is_gm,
            "campaign": campaign,
            "class_roster": class_levels_summary(sheet) if char.template == "dnd5e" else [],
            "animate_gifs": user.animate_gifs,
        },
    )


@router.post("/api/campaign/{campaign_id}/character/{char_id}")
async def update_sheet(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    body = await request.json()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Forbidden")
    if "name" in body:
        char.name = str(body["name"])[:120]
    hp_result = None
    if "sheet" in body and isinstance(body["sheet"], dict):
        incoming = body["sheet"]
        existing = dict(char.sheet or {})
        # Server-managed fields that have no form inputs on the sheet. The
        # client's buildSheet() can't include them in its payload, so a
        # naive replace would strand any transformed character (active_form
        # set, prior_form lost — see bug repro in v0.35.4). Carry these
        # forward from the persisted sheet whenever the client didn't send
        # them explicitly. hp_rolls is in the same category — populated
        # exclusively through the /sheet-fields PATCH from the edit panel
        # picker. ``death_saves`` (v2.1.0) is also server-managed — the
        # full sheet POST shouldn't blow away dying/stable state.
        for k in ("active_form", "prior_form", "hp_rolls", "favorite_beasts",
                  "damage_resistances", "damage_immunities",
                  "damage_vulnerabilities", "condition_immunities",
                  "death_saves", "roll_state"):
            if k in existing and k not in incoming:
                incoming[k] = existing[k]
        # Detect HP transitions so the state machine fires on full sheet save.
        old_current = int((existing.get("hp") or {}).get("current") or 0)
        new_current = int((incoming.get("hp") or {}).get("current") or 0)
        char.sheet = incoming
        if old_current != new_current:
            hp_result = _apply_hp_change(char, new_current)
    if "template" in body and body["template"] in ("generic", "dnd5e"):
        char.template = body["template"]
    db.commit()
    await hub.broadcast(
        campaign_id,
        {"type": "character_update", "data": {"id": char.id, "name": char.name}},
    )
    if hp_result and hp_result["status_changed"]:
        await hub.broadcast(campaign_id, {
            "type": "character_death_save",
            "data": {
                "character_id": char.id,
                "status": hp_result["death_saves"]["status"],
                "successes": int(hp_result["death_saves"]["successes"]),
                "failures": int(hp_result["death_saves"]["failures"]),
                "hp": hp_result["hp"],
                "source": "full_save",
            },
        })
    return {"ok": True}


# Allowed keys for the lightweight sheet-fields patch (avoids full-sheet replace).
# subclass_features_data kept for backward-compat; the three individual keys let
# each feature be stored and queried without re-parsing the whole blob.
_SHEET_PATCH_KEYS = {
    # HP object {current, max, temp}
    "hp",
    # Subclass features (new per-feature format + legacy blob)
    "subclass_features_data",   # legacy blob (kept for backwards compat)
    "subclass_name",
    "subclass_flavor",
    "subclass_features",        # list[{name, desc, level}]
    # Race traits (same pattern)
    "race_parsed_data",         # legacy blob
    "race_flavor",
    "race_trait_items",         # list[{name, desc}]
    # Full spells list — used by the Subclass Spells / Feature Grants panels
    # to persist a player's granted-spell pick the moment they choose one,
    # so the dropdown's selection survives a refresh without an explicit Save.
    "spells",
    # Per-class subclass-variant pick (Circle of the Land → Land Type,
    # Knowledge Domain → Skill, …).  Auto-saved when the player selects
    # from the variant dropdown so the picker re-hydrates on reload.
    "subclass_choice",
    # Per-class HP gain per level — { class_slug: [int, …] }. Edited via
    # the "HP per Level" table inside the sheet edit panel.
    "hp_rolls",
    # Beast picker favorites — list of Open5e creature slugs starred by
    # the player. Toggled via the ★ button on every picker row.
    "favorite_beasts",
    # Defenses — four string lists. Edited via the chip-toggle UI in
    # the Defenses fieldset; each toggle PATCHes immediately so the
    # state persists without an explicit Save.
    "damage_resistances",
    "damage_immunities",
    "damage_vulnerabilities",
    "condition_immunities",
    # Cached background detail (signature feature etc.) so the sheet's
    # background display block survives a reload without re-fetching.
    "background_data",
    # Feats list — auto-saved on add/remove so the player's selection
    # persists across refreshes without an explicit Save.
    "feats",
}

# Keys that route into a specific entry of ``sheet["classes"]`` when the
# caller passes ``class_slug``.  These are the per-class subclass cache keys.
_CLASS_SCOPED_KEYS = {
    "subclass_features_data",
    "subclass_name",
    "subclass_flavor",
    "subclass_features",
    "subclass_choice",
}


def _apply_sheet_patch(sheet: dict, body: dict) -> dict:
    """Merge whitelisted keys onto a sheet, routing per-class fields into
    the right entry of ``sheet["classes"]`` when ``class_slug`` is supplied."""
    patch = {k: v for k, v in body.items() if k in _SHEET_PATCH_KEYS}
    if not patch:
        return sheet
    cslug = (body.get("class_slug") or "").strip().lower()
    sheet = {**(sheet or {})}
    if cslug:
        # Ensure classes[] exists, then merge per-class keys into the matching entry
        normalize_dnd5e_sheet(sheet)
        classes = list(sheet.get("classes") or [])
        target_idx = next(
            (i for i, c in enumerate(classes)
             if isinstance(c, dict) and _class_slug(c.get("class") or "") == cslug),
            None,
        )
        if target_idx is not None:
            entry = dict(classes[target_idx])
            for k, v in patch.items():
                if k in _CLASS_SCOPED_KEYS:
                    entry[k] = v
            classes[target_idx] = entry
            sheet["classes"] = classes
            # Re-mirror primary onto top-level
            normalize_dnd5e_sheet(sheet)
    # Always merge into top-level too (legacy callers / non-class-scoped keys).
    sheet.update({k: v for k, v in patch.items() if k not in _CLASS_SCOPED_KEYS or not cslug})
    return sheet


@router.patch("/api/campaign/{campaign_id}/character/{char_id}/sheet-fields")
async def patch_sheet_fields(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Merge a small set of pre-approved keys into a character's sheet JSON.

    v2.1.0: when ``hp`` is included in the patch, route through
    ``_apply_hp_change`` so the death save state machine sees the
    transition (e.g. HP dropping to 0 → dying). The optional body field
    ``hp_change_reason`` accepts ``"damage"`` to enable the auto-failure
    tick / massive-damage rule; defaults to a plain set (no damage
    semantics)."""
    body = await request.json()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Forbidden")

    # Extract HP separately so we can route it through the state machine.
    incoming_hp = body.get("hp") if isinstance(body.get("hp"), dict) else None
    body_for_patch = {k: v for k, v in body.items() if k != "hp"}
    char.sheet = _apply_sheet_patch(char.sheet, body_for_patch)

    hp_result = None
    pre_patch_current_hp = None
    if incoming_hp is not None and "current" in incoming_hp:
        # Preserve max/temp by writing them first, then routing current
        # through the state machine.
        sheet = dict(char.sheet or {})
        existing_hp = dict(sheet.get("hp") or {})
        # v2.49.42 — snapshot the pre-patch current HP so we can emit
        # a character_hp_update broadcast with the right delta below.
        pre_patch_current_hp = int(existing_hp.get("current") or 0)
        if "max" in incoming_hp:
            existing_hp["max"] = int(incoming_hp.get("max") or 0)
        if "temp" in incoming_hp:
            existing_hp["temp"] = max(0, int(incoming_hp.get("temp") or 0))
        sheet["hp"] = existing_hp
        char.sheet = sheet

        reason = str(body.get("hp_change_reason") or "set").lower()
        is_damage = reason == "damage"
        is_crit = bool(body.get("is_crit"))
        damage_amount = int(body.get("damage_amount") or 0)

        # v2.20.0 Phase B: resistance. When the caller passes a
        # damage_type AND the target has Rage (or any other buff with
        # ``resistance_to`` containing that type), halve the damage
        # before HP application. The halved value flows into
        # ``_apply_hp_change`` so the death-save state machine + the
        # massive-damage threshold both see the post-resistance number,
        # which matches RAW (resistance applies before HP is dealt).
        # incoming_hp's "current" is the player's pre-resistance new HP;
        # we recompute to keep them in sync.
        damage_type = str(body.get("damage_type") or "").strip().lower()
        resistance_applied = False
        new_hp_current = int(incoming_hp.get("current") or 0)
        if is_damage and damage_amount > 0:
            halved_damage, resistance_applied = _resistance_halve(
                damage_amount, damage_type, char.sheet or {},
            )
            if resistance_applied:
                # Recompute the new HP from the existing current HP -
                # halved damage. We can't just halve the difference
                # because the client may have applied other effects.
                existing_hp_inner = (char.sheet or {}).get("hp") or {}
                old_current = int(existing_hp_inner.get("current") or 0)
                new_hp_current = max(0, old_current - halved_damage)
                damage_amount = halved_damage

        hp_result = _apply_hp_change(
            char,
            new_hp_current,
            is_damage=is_damage,
            is_crit=is_crit,
            damage_amount=damage_amount,
        )

    db.commit()

    # v2.19.1 Phase C.2: if this was damage AND the character is
    # concentrating on a buff, roll a CON save (DC = max(10, damage//2))
    # and drop the buff on fail. Auto-rolled server-side; broadcasts
    # ``concentration_save`` so every client sees the result.
    # v2.19.2 Phase C.3: pass db so the sheet mirror updates on fail.
    if hp_result and is_damage and damage_amount > 0:
        await _maybe_concentration_save(campaign_id, char, damage_amount, db=db)

    if hp_result and hp_result["status_changed"]:
        await hub.broadcast(campaign_id, {
            "type": "character_death_save",
            "data": {
                "character_id": char.id,
                "status": hp_result["death_saves"]["status"],
                "successes": int(hp_result["death_saves"]["successes"]),
                "failures": int(hp_result["death_saves"]["failures"]),
                "hp": hp_result["hp"],
                "source": "sheet_patch",
            },
        })

    # v2.49.42 — also broadcast ``character_hp_update`` whenever HP
    # actually changed, NOT just on status-boundary crossings. Pre-fix:
    # PATCH /sheet-fields fired ``character_death_save`` only when
    # ``hp_result["status_changed"]`` (e.g. crossing into dying / stable
    # / dead), so a vanilla 35→25 HP drop within "alive" went silent —
    # non-GM observers' ``window.battle.combatants[…].hp_current`` stayed
    # at 35 until something else triggered a refresh. The character_hp_
    # update broadcast pattern (no IS_GM guard at tabletop.js:3102, fed
    # by /attack and /cast_spell paths) is the right place to plug this
    # gap — same shape, same client handler. Surfaced by the encounter-
    # sim test_alice_observes_hp_update which had to use /attack instead
    # of PATCH /sheet-fields to get an observable HP change for Alice.
    if hp_result and pre_patch_current_hp is not None:
        new_current = int(hp_result["hp"].get("current") or 0)
        if new_current != pre_patch_current_hp:
            await hub.broadcast(campaign_id, {
                "type": "character_hp_update",
                "data": {
                    "character_id": char.id,
                    "hp": hp_result["hp"],
                    "delta": new_current - pre_patch_current_hp,
                    "source": "sheet_patch",
                },
            })

    return {
        "ok": True,
        "hp": hp_result["hp"] if hp_result else None,
        "death_saves": hp_result["death_saves"] if hp_result else None,
        # v2.20.0 Phase B: signal whether resistance halved the damage
        # before applying. Useful for the player UI to surface a "🛡
        # resisted" toast.
        "resistance_applied": bool(hp_result and resistance_applied) if hp_result else False,
        "damage_amount_after_resistance": damage_amount if hp_result and is_damage else None,
    }


# ----------- API: death saving throws (v2.1.0) -----------

@router.post("/api/campaign/{campaign_id}/character/{char_id}/death-save")
async def roll_death_save(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Roll a death saving throw for a dying character.

    Per RAW: 10+ = success, <10 = failure, nat 20 wakes the character
    with 1 HP, nat 1 counts as two failures, 3 successes → stable,
    3 failures → dead. The roll lands in the campaign roll log so the
    table sees it.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Forbidden")

    ds = dict((char.sheet or {}).get("death_saves") or {})
    status = ds.get("status") or "alive"
    if status != "dying":
        raise HTTPException(409, f"Character is {status}, not dying — cannot roll a death save")

    successes = int(ds.get("successes") or 0)
    failures = int(ds.get("failures") or 0)

    # v2.49.12: route the death-save d20 through the shared seedable
    # dice RNG so encounter-sim tests can make the result deterministic.
    raw = dice_mod.get_rng().randint(1, 20)

    outcome = ""
    regained = False
    if raw == 20:
        outcome = "regain_consciousness"
        regained = True
    elif raw == 1:
        failures += 2
        outcome = "crit_fail"
    elif raw >= 10:
        successes += 1
        outcome = "success"
    else:
        failures += 1
        outcome = "fail"

    if regained:
        # Wake up: HP set to 1, status alive, counters cleared
        hp_result = _apply_hp_change(char, 1)
        new_ds = dict(char.sheet.get("death_saves") or {})
        new_hp = hp_result["hp"]
    else:
        # Threshold checks
        if failures >= 3:
            new_status = "dead"
            successes = 0
            failures = 0
        elif successes >= 3:
            new_status = "stable"
            successes = 0
            failures = 0
        else:
            new_status = "dying"
        _set_death_save_state(char, status=new_status, successes=successes, failures=failures)
        new_ds = dict(char.sheet.get("death_saves") or {})
        new_hp = dict(char.sheet.get("hp") or {})
        # v2.49.49 — when a death save flips status to "dead", drop
        # the caster's concentration. RAW "incapacitated → lose
        # concentration" applies here even though no damage was
        # dealt by the roll itself. The v2.49.48 fix covered the
        # damage-event path; this covers the death-save 3-failures
        # path. ``_drop_caster_concentration`` reuses ``_remove_buff``
        # which fires buff_update + cascades target-side cleanup.
        if new_status == "dead":
            await _drop_caster_concentration(
                campaign_id, char.id,
                reason="3 failed death saves",
            )

    # Persist roll record so the campaign log sees it
    note_label = {
        "success": f"💀 Death Save: SUCCESS ({new_ds.get('successes', 0)}/3)",
        "fail": f"💀 Death Save: FAILURE ({new_ds.get('failures', 0)}/3)",
        "crit_fail": "💀 Death Save: CRITICAL FAILURE (2 failures)",
        "regain_consciousness": "💀 Death Save: NATURAL 20 — regain consciousness!",
    }.get(outcome, "💀 Death Save")
    rec = DiceRoll(
        campaign_id=campaign_id,
        user_id=user.id,
        expression="1d20",
        breakdown=f"1d20[{raw}]={raw}  =>  {raw}",
        total=raw,
        visibility=Visibility.PUBLIC,
        note=note_label[:200],
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    # Roller / character info for the broadcast (matches /roll endpoint shape)
    _char_name = char.name
    _portrait_url = char.portrait_url
    _membership = (
        db.query(CampaignMembership)
        .filter(CampaignMembership.campaign_id == campaign_id, CampaignMembership.user_id == user.id)
        .first()
    )
    _player_color = (
        _membership.color if _membership and _membership.color
        else (campaign.gm_color if user.id == campaign.gm_user_id else None)
    )
    _user_color = (char.color if char.color else _player_color)

    await hub.broadcast(campaign_id, {
        "type": "roll",
        "data": {
            "id": rec.id,
            "user_id": user.id,
            "user_name": user.display_name,
            "char_name": _char_name,
            "user_color": _user_color,
            "portrait_url": _portrait_url,
            "expression": rec.expression,
            "breakdown": rec.breakdown,
            "total": rec.total,
            "visibility": rec.visibility.value,
            "note": rec.note,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
            "kind": "death_save",
            "death_save_outcome": outcome,
        },
    })
    await hub.broadcast(campaign_id, {
        "type": "character_death_save",
        "data": {
            "character_id": char.id,
            "status": new_ds.get("status"),
            "successes": int(new_ds.get("successes") or 0),
            "failures": int(new_ds.get("failures") or 0),
            "hp": new_hp,
            "source": "roll",
            "outcome": outcome,
            "raw": raw,
        },
    })

    return {
        "ok": True,
        "raw": raw,
        "outcome": outcome,
        "status": new_ds.get("status"),
        "successes": int(new_ds.get("successes") or 0),
        "failures": int(new_ds.get("failures") or 0),
        "hp": new_hp,
    }


@router.post("/api/campaign/{campaign_id}/character/{char_id}/death-save/override")
async def override_death_save(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM-only: manually set a character's death save status and counters.
    Used for narrative beats and misclick recovery. Body: ``{status, successes,
    failures}`` — any field omitted is left alone."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    body = await request.json()
    status_in = body.get("status")
    if status_in is not None and status_in not in _DEATH_SAVE_STATUSES:
        raise HTTPException(400, f"status must be one of {_DEATH_SAVE_STATUSES}")

    # If transitioning to "alive" from a 0-HP state, bump HP to 1 so the
    # state is internally consistent (alive at 0 HP would immediately fall
    # back to dying on the next state machine pass).
    if status_in == "alive":
        sheet = dict(char.sheet or {})
        hp = dict(sheet.get("hp") or {})
        if int(hp.get("current") or 0) <= 0:
            hp["current"] = 1
            sheet["hp"] = hp
            char.sheet = sheet

    new_ds = _set_death_save_state(
        char,
        status=status_in,
        successes=body.get("successes"),
        failures=body.get("failures"),
    )
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "character_death_save",
        "data": {
            "character_id": char.id,
            "status": new_ds.get("status"),
            "successes": int(new_ds.get("successes") or 0),
            "failures": int(new_ds.get("failures") or 0),
            "hp": dict(char.sheet.get("hp") or {}),
            "source": "gm_override",
        },
    })

    # v2.49.49 — drop the caster's concentration when GM overrides
    # the status to a non-alive state. RAW "incapacitated → lose
    # concentration" applies regardless of how the PC got there.
    # Override paths covered: dying / stable / dead. Override to
    # "alive" doesn't drop (the PC just woke up). The damage-event
    # path is already covered by v2.49.48; the death-save roll path
    # by the elif above; this is the third / final gap.
    if status_in in ("dying", "stable", "dead"):
        await _drop_caster_concentration(
            campaign_id, char.id,
            reason=f"GM override → {status_in}",
        )

    return {"ok": True, "death_saves": new_ds, "hp": char.sheet.get("hp")}


@router.post("/api/campaign/{campaign_id}/character/{char_id}/stabilize")
async def stabilize_character(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM-only: set a dying character to ``stable``. Equivalent to a
    successful DC 10 Medicine check by an ally (auto-resolution of the
    Medicine roll is deferred to a Phase 3 follow-up)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    new_ds = _set_death_save_state(char, status="stable", successes=0, failures=0)
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "character_death_save",
        "data": {
            "character_id": char.id,
            "status": "stable",
            "successes": 0,
            "failures": 0,
            "hp": dict(char.sheet.get("hp") or {}),
            "source": "stabilize",
        },
    })
    return {"ok": True, "death_saves": new_ds}


# ----------- API: roll-state toggle (v2.2.0) -----------

@router.post("/api/campaign/{campaign_id}/character/{char_id}/roll-state")
async def set_roll_state(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Set or clear a character's roll-state. Body: ``{value: "advantage"
    | "disadvantage" | null}``. While set, single-d20 expressions sent
    through /roll and /attack are auto-upgraded to 2d20kh1 / 2d20kl1
    per the v2.2.0 plan. Manual 2d20kh1 / 2d20kl1 / 1d20a / 1d20d
    submissions remain unchanged and are tagged with "(manual …)" in
    the roll log. Owner or GM only."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not (_user_is_gm(user, campaign, db) or char.owner_user_id == user.id):
        raise HTTPException(403, "Forbidden")

    body = await request.json()
    value = body.get("value")
    if value not in ("advantage", "disadvantage", None):
        raise HTTPException(400, "value must be 'advantage', 'disadvantage', or null")

    sheet = dict(char.sheet or {})
    rs = dict(sheet.get("roll_state") or {})
    rs["value"] = value
    sheet["roll_state"] = rs
    char.sheet = sheet
    db.commit()

    await hub.broadcast(campaign_id, {
        "type": "character_roll_state",
        "data": {
            "character_id": char.id,
            "value": value,
        },
    })
    return {"ok": True, "value": value}


# ----------- WebSocket -----------

@router.websocket("/ws/campaign/{campaign_id}")
async def campaign_ws(websocket: WebSocket, campaign_id: int):
    session = websocket.session  # type: ignore[attr-defined]
    user_id = session.get("user_id") if session else None
    if not user_id:
        await websocket.close(code=4401)
        return
    db = SessionLocal()
    # Audio sync: if a track is currently playing for this campaign, the
    # new client gets the audio_play payload sent privately on connect so
    # they sync to the same seek offset everyone else hears. Built here
    # while the DB session is open; sent below after hub.connect accepts
    # the socket. Targeted send (not broadcast) — broadcasting would
    # restart audio for every other client too.
    initial_audio_payload: dict | None = None
    identity: dict | None = None
    try:
        user = db.query(User).filter(User.id == user_id).first()
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not user or not campaign or not _user_can_view_campaign(db, user, campaign):
            await websocket.close(code=4403)
            return
        # v2.9.1: build the presence identity here while the DB session
        # is open. Color resolves character.color > membership.color >
        # campaign.gm_color (for the GM); display name is the User's
        # canonical display_name. GM detection uses the same helper as
        # the rest of the auth path.
        membership = (
            db.query(CampaignMembership)
            .filter(CampaignMembership.campaign_id == campaign_id,
                    CampaignMembership.user_id == user.id)
            .first()
        )
        # First character this user owns in this campaign, for color
        # preference. None for the GM (who often owns multiple).
        my_char = (
            db.query(Character)
            .filter(Character.campaign_id == campaign_id,
                    Character.owner_user_id == user.id)
            .first()
        )
        is_gm_user = _user_is_gm(user, campaign, db)
        char_color = my_char.color if my_char and my_char.color else None
        member_color = membership.color if membership and membership.color else None
        gm_color = campaign.gm_color if is_gm_user else None
        identity = {
            "user_id": user.id,
            "display_name": user.display_name,
            "color": char_color or member_color or gm_color,
            "is_gm": is_gm_user,
        }
        if campaign.now_playing_track_id:
            track = (
                db.query(PlaylistTrack)
                .filter(PlaylistTrack.id == campaign.now_playing_track_id)
                .first()
            )
            if track:
                from .audio_routes import _now_playing_payload
                initial_audio_payload = {
                    "type": "audio_play",
                    "data": _now_playing_payload(campaign, track),
                }
    finally:
        db.close()

    await hub.connect(campaign_id, websocket, identity=identity)

    if initial_audio_payload is not None:
        import json as _json
        try:
            await websocket.send_text(_json.dumps(initial_audio_payload, default=str))
        except Exception as exc:
            log.warning("audio sync send failed for campaign %s: %s", campaign_id, exc)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("ws error: %s", e)
    finally:
        await hub.disconnect(campaign_id, websocket)


# ----------- Player character roster + standalone sheet -----------

@router.get("/campaign/{campaign_id}/characters", response_class=HTMLResponse)
def player_characters(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Character roster — accessible without an active session."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    is_gm = _user_is_gm(user, campaign, db)
    if is_gm:
        characters = (
            db.query(Character)
            .filter(Character.campaign_id == campaign_id)
            .order_by(Character.name)
            .all()
        )
    else:
        characters = (
            db.query(Character)
            .filter(
                Character.campaign_id == campaign_id,
                Character.owner_user_id == user.id,
            )
            .order_by(Character.name)
            .all()
        )
    # Build owner name map for GM view
    owner_names: dict[int, str] = {}
    if is_gm:
        owner_ids = {c.owner_user_id for c in characters if c.owner_user_id}
        if owner_ids:
            for u in db.query(User).filter(User.id.in_(owner_ids)).all():
                owner_names[u.id] = u.display_name
    return templates.TemplateResponse(
        "my_characters.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "characters": characters,
            "is_gm": is_gm,
            "owner_names": owner_names,
            "system": get_system(campaign.game_system),
        },
    )


@router.get("/campaign/{campaign_id}/character/{char_id}/sheet", response_class=HTMLResponse)
def character_sheet_page(
    campaign_id: int,
    char_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Standalone full-page character sheet — no active session required."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    char = db.query(Character).filter(Character.id == char_id).first()
    if not campaign or not char or char.campaign_id != campaign_id:
        raise HTTPException(404, "Not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    is_gm = _user_is_gm(user, campaign, db)
    can_edit = is_gm or char.owner_user_id == user.id
    sheet_template = "sheet_dnd5e.html" if char.template == "dnd5e" else "sheet_generic.html"
    page_sheet = char.sheet or get_template(char.template)
    if char.template == "dnd5e":
        normalize_dnd5e_sheet(page_sheet)
    return templates.TemplateResponse(
        "character_page.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "char": char,
            "sheet": page_sheet,
            "can_edit": can_edit,
            "is_gm": is_gm,
            "sheet_template": sheet_template,
            "system": get_system(campaign.game_system),
            "class_roster": class_levels_summary(page_sheet) if char.template == "dnd5e" else [],
            "animate_gifs": user.animate_gifs,
        },
    )


# ----------- Monster sheet (v2.3.10) -----------
# Reuse sheet_dnd5e.html for monsters by projecting a TokenTemplate (stat
# block + structured actions) into the same context shape the character
# sheet expects. Gives GMs PC-parity click-to-roll for ability checks,
# saves, skills, and structured attacks without rebuilding a parallel UI.
# See docs in monster_page.html + the adapter below.


class _SyntheticMonsterChar:
    """Stand-in for a ``Character`` ORM object so ``sheet_dnd5e.html`` (and
    its wrapper ``monster_page.html``) can render a monster's stat block
    without needing a DB-backed Character row. Only the attributes the
    template actually reads need to exist — see the template scan in
    docs/plans/monster-sheet.md (when written) or grep ``char\\.`` in
    ``app/templates/sheet_dnd5e.html`` to confirm the surface.

    Intentionally NOT a SQLAlchemy model: the monster lives in
    ``TokenTemplate`` (and optionally a homebrew JSON file), not in
    ``characters``. Saving to the character API would 404, so the
    monster sheet renders with ``can_edit=False`` and the form's
    data-readonly flag suppresses save buttons.
    """

    __slots__ = (
        "id", "name", "sheet", "template", "owner_user_id", "campaign_id",
        "color", "portrait_url", "ring_style", "template_id",
    )

    def __init__(
        self,
        *,
        id,
        name: str,
        sheet: dict,
        template: str = "dnd5e",
        owner_user_id: int = 0,
        campaign_id: int = 0,
        color: Optional[str] = None,
        portrait_url: Optional[str] = None,
        ring_style: Optional[str] = None,
        template_id: Optional[int] = None,
    ) -> None:
        # ``id`` may be a numeric TokenTemplate primary key (used by the
        # 2.3.10 standalone monster sheet route) or a string like
        # ``"monster-22"`` (used by the 2.3.17 mini-sheet pool, where DOM
        # ids need to NOT collide with real Character primary keys). The
        # partial stamps it into ``id=`` / ``data-char-id=`` attributes
        # directly; downstream JS parses or branches as needed.
        self.id = id
        self.name = name
        self.sheet = sheet
        self.template = template
        self.owner_user_id = owner_user_id
        self.campaign_id = campaign_id
        self.color = color or "#888"
        self.portrait_url = portrait_url
        self.ring_style = ring_style or "solid"
        # ``template_id``: the underlying TokenTemplate primary key as an
        # int, even when ``id`` is the string form. The mini-sheet partial
        # uses this to build the ``/monster-template/{tid}/sheet`` URL
        # for the "Open full sheet" link without needing to parse the
        # ``"monster-N"`` prefix off ``id``.
        self.template_id = template_id


def _monster_dict_to_sheet(m: dict, *, base: Optional[dict] = None) -> dict:
    """Project a Monster Pydantic dict (loaded by ``local_content.resolve``
    from ``app/data/local/dnd5e/monsters/*.json`` or a homebrew JSON file)
    into the sheet dict shape ``sheet_dnd5e.html`` consumes.

    ``base`` is the TokenTemplate's existing sheet — any keys it carries
    that we don't compute here (notes, custom overrides, etc.) pass
    through unchanged. Anything we compute (HP, AC, abilities, speed,
    race header, damage lists, actions) overrides the base.
    """
    import re as _re
    out = dict(base or {})
    hp = int(m.get("hit_points") or 10)
    out["hp"] = {"current": hp, "max": hp, "temp": 0}
    out["ac"] = int(m.get("armor_class") or 10)
    speed_raw = m.get("speed") or {}
    if isinstance(speed_raw, dict):
        walk = speed_raw.get("walk") or 30
        out["speed"] = int(walk) if str(walk).isdigit() else 30
    else:
        digits = _re.search(r"\d+", str(speed_raw))
        out["speed"] = int(digits.group()) if digits else 30
    out["abilities"] = {
        "STR": int(m.get("strength") or 10),
        "DEX": int(m.get("dexterity") or 10),
        "CON": int(m.get("constitution") or 10),
        "INT": int(m.get("intelligence") or 10),
        "WIS": int(m.get("wisdom") or 10),
        "CHA": int(m.get("charisma") or 10),
    }
    size = (m.get("size") or "").strip()
    type_ = (m.get("type") or "").strip()
    header_bits = " ".join(b for b in (size, type_) if b)
    if header_bits:
        out["race"] = header_bits
    if m.get("alignment"):
        out["background"] = m.get("alignment")
    for key in ("damage_resistances", "damage_immunities",
                "damage_vulnerabilities", "condition_immunities"):
        raw = m.get(key)
        if isinstance(raw, str) and raw.strip():
            out[key] = [p.strip() for p in _re.split(r"[,;]", raw) if p.strip()]
        elif isinstance(raw, list):
            out[key] = [str(p) for p in raw]
    # Pass the structured actions through so the caller's fold step picks
    # them up. Caller handles attack-button projection.
    if m.get("actions"):
        out["actions"] = m.get("actions")
    return out


def _monster_template_to_sheet(tmpl: TokenTemplate, campaign_id: int) -> dict:
    """Project a monster TokenTemplate's stat block + structured actions
    into the dict shape that ``sheet_dnd5e.html`` consumes.

    Source resolution order:

    1. ``tmpl.sheet["monster_slug"]`` — if the template is a pointer to a
       shipped or homebrew monster (the minimal demo NPC seed shape — see
       ``app/demo_seed.py _npc_sheet``), resolve via ``local_content`` and
       overlay the full stat block. The pointer pattern keeps the
       TokenTemplate rows tiny and the stat-block authoring in one place.

    2. ``tmpl.sheet["actions"]`` (homebrew structured Action shape from the
       v2.3.8 editor) and/or ``tmpl.sheet["attacks"]`` (legacy regex-
       derived character schema from SRD imports via
       ``_open5e_to_dnd5e_sheet``). The former gets folded into the latter
       so the character template, which reads ``sheet.attacks``, sees a
       unified list. De-duped by name so a homebrew override shadows an
       SRD-imported same-name attack.

    For SRD monsters where the Action's ``attack_bonus`` is null (shipped
    files describe the to-hit only in the desc text), the projection regex-
    extracts ``+N to hit`` from the desc so the attack button rolls
    ``1d20+N`` instead of a raw 1d20.
    """
    import re as _re

    sheet = dict(tmpl.sheet or {})
    monster_slug = sheet.get("monster_slug")
    if monster_slug:
        resolved = local_content.resolve(
            str(monster_slug), type="monsters", campaign_id=campaign_id,
        )
        if resolved is not None:
            monster_dict, _src = resolved
            sheet = _monster_dict_to_sheet(monster_dict, base=sheet)

    actions = sheet.get("actions") or []
    if not actions:
        return sheet

    existing_attacks = list(sheet.get("attacks") or [])
    by_name = {
        (a.get("name") or "").strip().lower(): i
        for i, a in enumerate(existing_attacks)
        if isinstance(a, dict)
    }

    for a in actions:
        if not isinstance(a, dict):
            continue
        if not (a.get("attack_roll") or a.get("damage") or a.get("save_ability")):
            continue
        name = (a.get("name") or "Action").strip()
        save_ability_raw = (a.get("save_ability") or "").strip().upper()
        atk_bonus = a.get("attack_bonus") or ""
        # SRD fallback: shipped monsters set attack_roll=true but leave
        # attack_bonus null — the to-hit lives in the desc text. Regex it
        # out so the attack button does ``1d20+N`` instead of raw 1d20.
        if a.get("attack_roll") and not atk_bonus:
            bonus_m = _re.search(r"([+-]\d+)\s*to hit", a.get("desc") or "")
            if bonus_m:
                atk_bonus = bonus_m.group(1)
        atk_entry = {
            # v2.3.40: pass through the structured Action's ``id`` so the
            # client can key per-combatant charge state (combatant.
            # action_charges[action_id]) and ``charges_max`` so the init-
            # tracker view can render the N/M counter + disable buttons
            # when the action is spent.
            "id": a.get("id") or name.lower().replace(" ", "-"),
            "name": name,
            "atk_bonus": atk_bonus,
            "damage": a.get("damage") or "",
            "damage_type": a.get("damage_type") or "",
            "save_dc": (a.get("save_dc") or None) if a.get("save_dc") else None,
            "save_ability": save_ability_raw or None,
            "charges_max": int(a.get("charges_max") or 0),
            "description": a.get("desc") or "",
        }
        key = name.lower()
        if key in by_name:
            existing_attacks[by_name[key]] = atk_entry
        else:
            existing_attacks.append(atk_entry)
            by_name[key] = len(existing_attacks) - 1

    sheet["attacks"] = existing_attacks
    return sheet


@router.get(
    "/campaign/{campaign_id}/monster-template/{template_id}/sheet",
    response_class=HTMLResponse,
)
def monster_template_sheet_page(
    campaign_id: int,
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.3.10: full sheet view for a monster ``TokenTemplate``, reusing
    ``sheet_dnd5e.html`` so the GM gets PC-parity click-to-roll for
    ability checks, saves, skills, and structured attacks.

    GM-only because monsters are GM-visibility data in this codebase.
    Read-only — ``can_edit=False`` makes the sheet's form render with
    ``data-readonly="1"``, which the sheet JS uses to suppress save
    buttons. The form fields stay populated though, because
    ``wireDnd5eRollButtons`` reads ability/skill/save state via
    ``form.querySelector('[name="..."]').value``.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    tmpl = (
        db.query(TokenTemplate)
        .filter(TokenTemplate.id == template_id,
                TokenTemplate.campaign_id == campaign_id)
        .first()
    )
    if not tmpl:
        raise HTTPException(404, "Monster template not found")

    sheet = _monster_template_to_sheet(tmpl, campaign_id)
    if (tmpl.template or "dnd5e") == "dnd5e":
        normalize_dnd5e_sheet(sheet)
    # v2.49.3 — overlay live combatant HP onto the template's static
    # max when the GM opens the sheet for a specific instance in
    # init. Without this the sheet keeps reading the template's
    # default HP even after the bandit took 22 fire damage from a
    # Fireball. The query string ``?combatant_id=tok_xyz`` (or
    # ``?combatant_id=tok:14``) selects which instance to show; the
    # init tracker's "📋 Sheet" link sets it automatically.
    combatant_id_q = (request.query_params.get("combatant_id") or "").strip()
    if combatant_id_q:
        battle_state = hub.get_battle(campaign_id)
        if battle_state:
            for c in (battle_state.get("combatants") or []):
                if c.get("id") == combatant_id_q:
                    hp = dict(sheet.get("hp") or {})
                    hp_cur = int(c.get("hp_current") or 0)
                    hp_max_state = int(c.get("hp_max") or hp.get("max") or hp_cur)
                    hp["current"] = hp_cur
                    hp["max"] = hp_max_state
                    sheet["hp"] = hp
                    break
    sheet_template = (
        "sheet_dnd5e.html"
        if (tmpl.template or "dnd5e") == "dnd5e"
        else "sheet_generic.html"
    )
    # v2.3.42: surface the homebrew slug to the template so it can render
    # an "✏️ Edit" link in the breadcrumb that bounces the GM to the
    # campaign-settings homebrew editor (anchored to the right entry).
    # Only set when (a) the TokenTemplate points to a slug via
    # ``sheet.monster_slug`` AND (b) the resolver tags the source as
    # ``local-homebrew`` (not shipped SRD, not Open5e cache) — editing
    # SRD content through the homebrew editor would silently fork it,
    # which is what the existing "📋 Clone" button already does
    # explicitly. ``raw_sheet`` reads the original sheet because
    # ``_monster_template_to_sheet`` overlays the resolved monster onto
    # ``sheet`` and the slug pointer survives the overlay too, but
    # reading from the original keeps the intent obvious.
    edit_homebrew_slug: Optional[str] = None
    raw_sheet = tmpl.sheet or {}
    raw_slug = raw_sheet.get("monster_slug")
    if raw_slug:
        resolved = local_content.resolve(
            str(raw_slug), type="monsters", campaign_id=campaign_id,
        )
        if resolved is not None and resolved[1] == "local-homebrew":
            edit_homebrew_slug = str(raw_slug)
    synthetic = _SyntheticMonsterChar(
        id=template_id,
        name=tmpl.name or "Monster",
        sheet=sheet,
        template=tmpl.template or "dnd5e",
        owner_user_id=0,
        campaign_id=campaign_id,
        portrait_url=tmpl.image_url,
    )
    return templates.TemplateResponse(
        "monster_page.html",
        {
            "request": request,
            "user": user,
            "campaign": campaign,
            "char": synthetic,
            "sheet": sheet,
            "can_edit": False,
            "is_gm": True,
            "sheet_template": sheet_template,
            "system": get_system(campaign.game_system),
            "class_roster": [],
            "animate_gifs": user.animate_gifs,
            # v2.3.13: lets sheet_dnd5e.html hide PC-only sections
            # (spells, inventory, class/subclass/race features, class
            # resources, notes) that have no meaning for a monster.
            "is_monster_sheet": True,
            # v2.3.42: homebrew slug for the "✏️ Edit" breadcrumb link;
            # None for SRD / Open5e monsters or templates without a
            # monster_slug pointer (those use Clone-then-edit flow).
            "edit_homebrew_slug": edit_homebrew_slug,
        },
    )


# ----------- Settings: characters (GM) -----------

_SETTINGS_UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "static" / "uploads"
_MAP_DIR = _SETTINGS_UPLOAD_ROOT / "maps"
_ALLOWED_IMG = {"image/png", "image/jpeg", "image/webp", "image/gif", "video/webm", "video/mp4"}


def _make_map_thumbnail(data: bytes, content_type: str, map_dir: Path, stem: str) -> Optional[str]:
    """Return a static JPEG thumbnail URL for GIFs (frame 0) and videos (ffmpeg).
    Returns None for static images — callers fall back to image_url."""
    if content_type == "image/gif":
        try:
            import io as _io
            from PIL import Image as _PIL
            with _PIL.open(_io.BytesIO(data)) as im:
                im.seek(0)
                frame = im.convert("RGB")
                thumb_name = stem + "_thumb.jpg"
                frame.save(str(map_dir / thumb_name), "JPEG", quality=80)
                return f"/static/uploads/maps/{thumb_name}"
        except Exception:
            return None
    if content_type in ("video/mp4", "video/webm"):
        try:
            import subprocess, tempfile, os as _os
            thumb_name = stem + "_thumb.jpg"
            thumb_path = map_dir / thumb_name
            with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as tf:
                tf.write(data)
                tf_path = tf.name
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", "0.5", "-i", tf_path,
                     "-vframes", "1", "-q:v", "3", str(thumb_path)],
                    capture_output=True, timeout=30, check=True,
                )
                return f"/static/uploads/maps/{thumb_name}"
            finally:
                try:
                    _os.unlink(tf_path)
                except Exception:
                    pass
        except Exception:
            return None
    return None


@router.post("/campaign/{campaign_id}/settings/characters")
def settings_create_character(
    campaign_id: int,
    name: str = Form(...),
    owner_user_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    sys = get_system(campaign.game_system)
    char = Character(
        campaign_id=campaign_id,
        name=name.strip()[:120] or "New character",
        template=sys.sheet_template,
        sheet=get_template(sys.sheet_template),
        owner_user_id=owner_user_id or None,
    )
    db.add(char)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#characters", status_code=303)


@router.post("/campaign/{campaign_id}/settings/characters/{char_id}/assign")
def settings_assign_character(
    campaign_id: int,
    char_id: int,
    owner_user_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    char = db.query(Character).filter(Character.id == char_id, Character.campaign_id == campaign_id).first()
    if not char:
        raise HTTPException(404)
    char.owner_user_id = owner_user_id or None
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#characters", status_code=303)


@router.post("/campaign/{campaign_id}/settings/characters/{char_id}/delete")
def settings_delete_character(
    campaign_id: int,
    char_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    char = db.query(Character).filter(Character.id == char_id, Character.campaign_id == campaign_id).first()
    if not char:
        raise HTTPException(404)
    char.campaign_id = None
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#characters", status_code=303)


@router.post("/campaign/{campaign_id}/settings/characters/import")
def settings_import_character(
    campaign_id: int,
    source_char_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM imports (copies) a player's character from another campaign into this one."""
    import copy as _copy
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    source = db.query(Character).filter(Character.id == source_char_id).first()
    if not source:
        raise HTTPException(404, "Character not found")
    new_char = Character(
        campaign_id=campaign_id,
        name=source.name,
        template=source.template,
        sheet=_copy.deepcopy(source.sheet or {}),
        portrait_url=source.portrait_url,
        owner_user_id=source.owner_user_id,
    )
    db.add(new_char)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#characters", status_code=303)


# ----------- Settings: maps (GM) -----------

@router.post("/campaign/{campaign_id}/settings/maps")
async def settings_upload_map(
    campaign_id: int,
    name: str = Form(...),
    grid_type: str = Form("square"),
    grid_size_px: int = Form(70),
    width_px: int = Form(2000),
    height_px: int = Form(1500),
    tags: str = Form(""),
    folder: str = Form(""),
    # v2.4.0: per-map "show grid overlay" toggle. HTML-checkbox idiom —
    # unchecked boxes don't submit the field at all, so ``Form(False)``
    # captures "off" while the template ships the box ``checked`` by
    # default. New uploads default to overlay-on, matching legacy maps
    # whose v53 migration backfills ``show_grid = TRUE``.
    show_grid: bool = Form(False),
    image: UploadFile = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    if image and image.filename:
        if image.content_type not in _ALLOWED_IMG:
            raise HTTPException(400, "Unsupported image type")
        data = await image.read()
        if len(data) > 80 * 1024 * 1024:
            raise HTTPException(400, "Map image too large (>80 MB)")
        _MAP_DIR.mkdir(parents=True, exist_ok=True)
        ext = Path(image.filename).suffix.lower() or ".png"
        stem = uuid.uuid4().hex
        fname = f"{stem}{ext}"
        (_MAP_DIR / fname).write_bytes(data)
        image_url = f"/static/uploads/maps/{fname}"
        if image.content_type and image.content_type.startswith("image/"):
            try:
                import io as _io
                from PIL import Image as _PILImage
                with _PILImage.open(_io.BytesIO(data)) as _img:
                    width_px, height_px = _img.size
            except Exception:
                pass
        thumbnail_url = _make_map_thumbnail(data, image.content_type or "", _MAP_DIR, stem)
    try:
        gt = GridType(grid_type)
    except ValueError:
        gt = GridType.SQUARE
    m = Map(
        campaign_id=campaign_id,
        name=name.strip()[:120] or "Map",
        image_url=image_url,
        thumbnail_url=thumbnail_url,
        grid_type=gt,
        grid_size_px=max(20, min(grid_size_px, 300)),
        width_px=max(200, min(width_px, 8000)),
        height_px=max(200, min(height_px, 8000)),
        tags=_parse_tags(tags),
        folder=folder.strip()[:120],
        show_grid=show_grid,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    if not campaign.active_map_id:
        campaign.active_map_id = m.id
        db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#maps", status_code=303)


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/rename")
async def settings_rename_map(
    campaign_id: int,
    map_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Rename a map in place. GM-only. Body: ``{name: str}``. Empty /
    whitespace-only names are rejected so the table row doesn't render
    as a blank line."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    body = await request.json()
    new_name = str(body.get("name") or "").strip()[:120]
    if not new_name:
        raise HTTPException(400, "Map name cannot be empty")
    m.name = new_name
    db.commit()
    return {"ok": True, "name": m.name}


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/grid_size")
async def settings_map_grid_size(
    campaign_id: int,
    map_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    body = await request.json()
    val = max(20, min(300, int(body.get("grid_size_px", 70))))
    m.grid_size_px = val
    db.commit()
    return {"ok": True, "grid_size_px": m.grid_size_px}


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/show_grid")
async def settings_map_show_grid(
    campaign_id: int,
    map_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """v2.4.0: toggle the per-map grid-overlay flag. GM-only. Body:
    ``{show_grid: bool}``. Token snapping continues to follow
    ``grid_type`` (square / hex / none) regardless of this flag — the
    overlay is purely a visual layer for maps whose background image
    doesn't already include a grid."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    body = await request.json()
    m.show_grid = bool(body.get("show_grid", True))
    db.commit()
    return {"ok": True, "show_grid": m.show_grid}


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/tags")
async def settings_set_map_tags(
    campaign_id: int,
    map_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Replace the map's tag list. GM-only. Body accepts either a JSON
    array or a comma-separated string; same normalisation as encounter
    and playlist tags (trim, dedupe case-insensitive, 40-char cap each,
    ≤20 entries)."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    body = await request.json()
    m.tags = _parse_tags(body.get("tags"))
    db.commit()
    return {"ok": True, "tags": m.tags}


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/folder")
async def settings_set_map_folder(
    campaign_id: int,
    map_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Set the map's folder. GM-only. Body: ``{folder: str}``."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    body = await request.json()
    m.folder = (body.get("folder") or "").strip()[:120]
    db.commit()
    return {"ok": True, "folder": m.folder}


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/activate")
def settings_activate_map(
    campaign_id: int,
    map_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    campaign.active_map_id = m.id
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#maps", status_code=303)


@router.post("/campaign/{campaign_id}/settings/maps/{map_id}/delete")
def settings_delete_map(
    campaign_id: int,
    map_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    m = db.query(Map).filter(Map.id == map_id, Map.campaign_id == campaign_id).first()
    if not m:
        raise HTTPException(404)
    if campaign.active_map_id == m.id:
        campaign.active_map_id = None
    db.delete(m)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#maps", status_code=303)


# ----------- Settings: members + danger zone (admin) -----------

@router.post("/campaign/{campaign_id}/settings/members/add")
def settings_add_member(
    campaign_id: int,
    user_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404)
    existing = db.query(CampaignMembership).filter(
        CampaignMembership.campaign_id == campaign_id,
        CampaignMembership.user_id == user_id,
    ).first()
    if not existing:
        db.add(CampaignMembership(campaign_id=campaign_id, user_id=user_id))
        db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#members", status_code=303)


@router.post("/campaign/{campaign_id}/settings/members/{membership_id}/remove")
def settings_remove_member(
    campaign_id: int,
    membership_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    db.query(CampaignMembership).filter(
        CampaignMembership.id == membership_id,
        CampaignMembership.campaign_id == campaign_id,
    ).delete()
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#members", status_code=303)


@router.post("/campaign/{campaign_id}/settings/delete")
def settings_delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404)
    c.active_map_id = None
    db.commit()
    db.delete(c)
    db.commit()
    return RedirectResponse("/", status_code=303)
