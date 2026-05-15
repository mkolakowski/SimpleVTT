"""Per-content-type Pydantic models. One file per type would have meant nine
near-identical 20-line modules, so they're consolidated here.

Every model carries the same provenance trailer (``system``, ``scope``,
``source``, ``owner``, ``attribution`` aliased to ``_attribution``) and an
``actions: list[Action]`` array that drives the shared button renderer.

Legacy fields on existing on-disk JSON files (class_features / subclass_features
/ races) are typed liberally (``Any`` / loose unions) so the new schema is a
superset of the current content shape and revalidating existing files at boot
doesn't introduce regressions.
"""
from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from .action_schema import Action


# ── Shared provenance mixin ──────────────────────────────────────────────────
class _ProvenanceMixin(BaseModel):
    """Trailer fields every content record carries.

    ``_attribution`` is exposed via alias so Pydantic v2 accepts the
    underscore-prefixed key from the shipped SRD JSON files.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    system: str = "dnd5e"
    scope: str = "global"
    source: str = "srd"
    owner: Optional[int] = None
    attribution: str = Field(default="", alias="_attribution")


# ── Race / racial traits ─────────────────────────────────────────────────────
class Trait(BaseModel):
    """Legacy descriptive trait card retained for backward compatibility with
    existing ``app/data/local/dnd5e/races/<slug>.json`` files. New mechanically
    active traits should live in ``actions: list[Action]`` instead."""

    name: str
    desc: str = ""
    level: Optional[int] = None


class Race(_ProvenanceMixin):
    slug: str
    name: str
    ability_bonuses: list[dict] = Field(default_factory=list)
    size: str = "Medium"
    speed: Union[int, dict] = 30
    age: str = ""
    alignment: str = ""
    languages: str = ""
    traits: list[Trait] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)


# ── Class / class features ───────────────────────────────────────────────────
class ClassFeature(_ProvenanceMixin):
    slug: str
    name: str
    hit_die: int = 8
    prof_armor: str = ""
    prof_weapons: str = ""
    prof_tools: str = ""
    prof_saving_throws: str = ""
    prof_skills: str = ""
    spellcasting_ability: str = ""
    equipment: str = ""
    features: str = ""
    multiclass_prereq_abilities: dict = Field(default_factory=dict)
    multiclass_prereq_mode: str = "all"
    multiclass_proficiencies: str = ""
    spell_list: list[str] = Field(default_factory=list)
    resources: list[dict] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)


# ── Subclass / subclass features ─────────────────────────────────────────────
class SubclassFeature(_ProvenanceMixin):
    slug: str
    name: str
    class_slug: str = ""
    subclass_flavor: str = ""
    features: Any = ""
    actions: list[Action] = Field(default_factory=list)


# ── Spells ───────────────────────────────────────────────────────────────────
class Spell(_ProvenanceMixin):
    slug: str
    name: str
    level_int: int
    school: str = ""
    spell_lists: list[str] = Field(default_factory=list)
    casting_time: str = ""
    range: str = ""
    duration: str = ""
    components: str = ""
    desc: str = ""
    higher_level: str = ""
    ritual: bool = False
    concentration: bool = False
    actions: list[Action] = Field(default_factory=list)


# ── Items ────────────────────────────────────────────────────────────────────
class Item(_ProvenanceMixin):
    slug: str
    name: str
    type: str = "gear"
    rarity: str = "common"
    attunement: bool = False
    weight: str = ""
    cost: str = ""
    desc: str = ""
    properties: dict = Field(default_factory=dict)
    actions: list[Action] = Field(default_factory=list)


# ── Feats ────────────────────────────────────────────────────────────────────
class Feat(_ProvenanceMixin):
    slug: str
    name: str
    prerequisite: str = ""
    desc: str = ""
    actions: list[Action] = Field(default_factory=list)


# ── Backgrounds ──────────────────────────────────────────────────────────────
class Background(_ProvenanceMixin):
    slug: str
    name: str
    skill_proficiencies: str = ""
    tool_proficiencies: str = ""
    languages: str = ""
    equipment: str = ""
    feature_name: str = ""
    feature_desc: str = ""
    suggested_characteristics: str = ""
    actions: list[Action] = Field(default_factory=list)


# ── Monsters ─────────────────────────────────────────────────────────────────
class Monster(_ProvenanceMixin):
    slug: str
    name: str
    size: str = "Medium"
    type: str = "humanoid"
    alignment: str = "unaligned"
    armor_class: int = 10
    armor_desc: str = ""
    hit_points: int = 1
    hit_dice: str = ""
    speed: dict = Field(default_factory=dict)
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    damage_vulnerabilities: str = ""
    damage_resistances: str = ""
    damage_immunities: str = ""
    condition_immunities: str = ""
    senses: str = ""
    languages: str = ""
    challenge_rating: str = "0"
    actions: list[Action] = Field(default_factory=list)


# ── Conditions ───────────────────────────────────────────────────────────────
class Condition(_ProvenanceMixin):
    slug: str
    name: str
    desc: str = ""
    actions: list[Action] = Field(default_factory=list)


# ── Type registry for the local_content resolver ────────────────────────────
# Keys are the directory names under ``app/data/local/<system>/`` and
# ``app/data/homebrew/<system>/<scope>/``.
TYPE_REGISTRY: dict[str, type[BaseModel]] = {
    "races": Race,
    "class_features": ClassFeature,
    "subclass_features": SubclassFeature,
    "spells": Spell,
    "items": Item,
    "feats": Feat,
    "backgrounds": Background,
    "monsters": Monster,
    "conditions": Condition,
}
