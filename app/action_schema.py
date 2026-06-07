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

    ``extra_beams`` (v2.40.0) is the multi-attack counterpart for spells
    where the scaling adds entire extra attacks rather than larger dice
    per attack — Eldritch Blast is the canonical case (1 beam at L1-4,
    2 at L5-10, 3 at L11-16, 4 at L17+). When set, /cast_spell rolls
    ``1 + extra_beams`` attack rolls against the target, each
    independently hitting/missing, and aggregates damage. Crit applies
    per-beam.
    """

    level: int
    damage: str = ""
    extra_beams: int = 0


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
    # v2.49.127: slot-level upcast beam scaling. When a spell adds beams
    # per slot level above its base (Scorching Ray RAW PHB p.273: +1 ray
    # per slot above 2), the engine computes
    # ``total_beams += (slot_level - spell.level) * extra_beams_per_slot_above_base``.
    # Independent of ``damage_scaling.extra_beams`` (which is keyed on
    # character level for cantrip scaling); the two can coexist on the
    # same action if a homebrew spell wants both axes.
    extra_beams_per_slot_above_base: int = 0
    # v2.49.147: slot-level upcast target-count scaling for non-attack-
    # roll multi-target spells (Magic Missile RAW PHB p.257: 3 darts at
    # L1, +1 dart per slot above 1; future spells like Crusader's
    # Mantle if it ever picks up multi-target damage). The sheet's
    # multi-target picker uses ``aoe_targets + (slot_level - spell.level)
    # * extra_targets_per_slot_above_base`` as the required count when
    # ``attack_roll: false``. Independent of ``extra_beams_per_slot_
    # above_base`` (which drives attack-roll multi-beam math); these
    # serve symmetric purposes for the two spell archetypes.
    extra_targets_per_slot_above_base: int = 0
    # v2.110.0: slot-level upcast DICE scaling (Approach B of the
    # spell-upcasting plan). When set, the cast resolver adds
    # ``(slot_level - spell.level) ×`` this dice expression to the
    # action's damage / healing — Fireball ``damage_per_slot: "1d6"``,
    # Cure Wounds ``healing_per_slot: "1d8"``. MUST be declared here or
    # Pydantic strips it during content parse (same gotcha the
    # extra_beams_/extra_targets_per_slot_above_base comments flag).
    damage_per_slot: str = ""
    healing_per_slot: str = ""
    # v2.49.176: NPC actions can reference the shared spell catalog via
    # ``spell_slug`` (added v2.49.174). When set, the server's
    # _resolve_spell_slug_action helper merges the spell's catalog
    # entry into this action at sheet-render time (damage / type /
    # attack_roll / save_ability / range / area / etc.). Empty string
    # means "no catalog reference" — the action uses its inline data.
    # Same Pydantic-strips-unknown-fields gotcha that bit v2.49.127's
    # extra_beams_per_slot_above_base + v2.49.147's
    # extra_targets_per_slot_above_base: without this declaration the
    # field gets dropped during write_homebrew serialization, even
    # though the client + server logic reads it.
    spell_slug: str = ""
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
