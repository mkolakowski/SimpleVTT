"""Shared declarative action descriptor for every content type.

Every content record — spell, item, feat, monster, background, condition,
class feature, subclass feature, race — carries ``actions: list[Action]``.
The frontend's ``renderActionButtons(actions, ctx)`` helper inspects which
fields are populated on each ``Action`` and emits the matching button:

* ``damage`` (+ ``damage_type``)        → 🎲 Roll damage
* ``damage_scaling``                    → 🎲 Roll scaled-by-level damage
* ``attack_roll``                       → 🎯 Attack roll
* ``save_ability``                      → 📋 Prompt save
* ``healing`` (+ ``aoe_targets``)       → 🩹 Apply healing
* ``active_toggle`` + ``resource_key``  → ⚡ Activate / deactivate
* ``reroll_trigger``                    → ↩ Reroll (e.g. Lucky)
* ``transform_picker``                  → 🐺 Transform (reserved; Wildshape stays on its bespoke path)
* ``upcast`` / ``area``                 → slot-picker scaling preview / future AOE template

The presence-gates-button pattern keeps the descriptor open: adding a new
button category is one new field on this model plus one branch in the
JS helper. No content type needs to know about every field.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ActionScalingTier(BaseModel):
    """One entry in ``Action.damage_scaling`` (e.g. Sneak Attack 1d6 → 10d6).

    The renderer picks the highest tier whose ``level`` is ≤ the character's
    level. Earlier tiers stop applying once a later one takes effect.
    """

    level: int
    damage: str = ""


class AreaShape(BaseModel):
    """Spell/effect area declaration. Schema-only in v2.0.0 — the map ruler / AOE
    template UI that consumes ``shape`` + ``size_ft`` is a follow-up PR."""

    shape: str = ""
    size_ft: int = 0
    secondary_ft: int = 0


class UpcastEntry(BaseModel):
    """One slot-level bump for a spell. The renderer previews the cumulative
    effect of casting at ``slot_level``: base + sum of all entries with
    ``slot_level`` ≤ chosen slot."""

    slot_level: int
    damage: str = ""
    healing: str = ""
    extra_targets: int = 0


class Action(BaseModel):
    """Single declarative button / automation bound to a content record."""

    id: str
    name: str
    desc: str = ""
    min_level: int = 1
    category: str = "action"
    resource_key: str = ""
    cost: int = 1
    active_toggle: bool = False
    damage: str = ""
    damage_type: str = ""
    damage_scaling: list[ActionScalingTier] = Field(default_factory=list)
    attack_roll: bool = False
    # To-hit string ("+5", "-1") used when ``attack_roll`` is true. Stored as
    # a string (not int) for parity with the character-sheet attack schema
    # and so the existing server-side ``1d20 + attack_bonus`` expression
    # builder in ``tabletop_routes._resolve_attack`` round-trips unchanged.
    # Empty means "no bonus" (raw 1d20).
    attack_bonus: str = ""
    save_ability: str = ""
    # DC for the save when ``save_ability`` is set. 0 means "DC not declared"
    # — the prompt-save flow still works (the GM enters DC at prompt time).
    save_dc: int = 0
    # v2.3.40: charges_max > 0 marks the action as limited-use (e.g.
    # "Recharge 5-6", "1/day", "3/short rest"). The init-tracker
    # monster card renders an N/M counter beside the action name and
    # decrements on click; a ↻ recharge button resets to max. 0 means
    # unlimited use (the existing default — every action without an
    # explicit cap stays usable indefinitely). Per-combatant state
    # lives on ``combatant.action_charges[action.id]`` in localStorage,
    # not on the Action itself — same Action instance can be shared
    # across multiple combatants with separate counts.
    charges_max: int = 0
    healing: str = ""
    aoe_targets: int = 1
    reroll_trigger: str = ""
    transform_picker: str = ""
    upcast: list[UpcastEntry] = Field(default_factory=list)
    area: AreaShape = Field(default_factory=AreaShape)
