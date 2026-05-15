"""One-shot migration helpers for schema v52 (APP_VERSION 2.0.0).

What this does
--------------
Exports every row in the six ``custom_*`` tables to per-slug JSON files in
the homebrew Docker volume, then DROPs the tables. After this runs once on
a given database, the ``custom_classes`` / ``custom_subclasses`` /
``custom_races`` / ``custom_feats`` / ``custom_monsters`` /
``custom_backgrounds`` tables no longer exist.

Why a separate module
---------------------
- Keeps ``database.py`` focused on the inline-migration framework itself.
- Lets the ``_dump_custom_*`` helpers be unit-tested without booting the app.
- Uses raw SQL (``conn.execute(text("SELECT * FROM …"))``) rather than
  SQLAlchemy ORM queries so the migration keeps working after the matching
  model classes are removed from ``app/models.py``.

Idempotency / safety
--------------------
- The runner is a no-op when the legacy tables are already gone.
- Exports run inside a single SQL transaction; the ``DROP TABLE`` statements
  only execute after every row has been written to a homebrew JSON file. If
  a write raises, the transaction rolls back and the tables stay intact.
  Partial files written before the failure are harmless and overwritten on
  the next run (writes are deterministic).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .local_content import features_to_markdown, write_homebrew

log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _scope_for(row: Any) -> str:
    """Build the homebrew scope label from a row's ``campaign_id`` column.
    Campaign-scoped rows go to ``campaign-<N>``; rows with NULL campaign_id
    (none today; reserved) go to ``global``."""
    cid = getattr(row, "campaign_id", None)
    return f"campaign-{int(cid)}" if cid else "global"


def _maybe_json(value: Any) -> Any:
    """SQLite returns JSON columns as Python strings (varies by driver), while
    Postgres returns parsed dicts/lists. Coerce strings to JSON; pass anything
    else through."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


# ── Per-table dumpers ─────────────────────────────────────────────────────────
def _dump_custom_class(row: Any) -> dict:
    """``CustomClass`` row → ``ClassFeature`` JSON dict.

    The structured ``features`` JSON list flattens to a markdown blob to
    match the shipped class_features schema (where ``features: str``).
    """
    return {
        "slug": row.class_slug,
        "name": row.name,
        "hit_die": row.hit_die or 8,
        "prof_armor": row.prof_armor or "",
        "prof_weapons": row.prof_weapons or "",
        "prof_tools": row.prof_tools or "",
        "prof_saving_throws": row.prof_saving_throws or "",
        "prof_skills": row.prof_skills or "",
        "spellcasting_ability": row.spellcasting_ability or "",
        "equipment": row.equipment or "",
        "features": features_to_markdown(_maybe_json(row.features) or []),
        "multiclass_prereq_abilities": _maybe_json(row.multiclass_prereq_abilities) or {},
        "multiclass_prereq_mode": row.multiclass_prereq_mode or "all",
        "multiclass_proficiencies": row.multiclass_proficiencies or "",
        "spell_list": _maybe_json(row.spell_list) or [],
        "resources": _maybe_json(row.resources) or [],
        "actions": [],
        "system": row.system or "dnd5e",
        "scope": _scope_for(row),
        "source": "homebrew",
        "owner": row.created_by_user_id,
        "_attribution": "Migrated from CustomClass DB row at v2.0.0 (file-based content framework).",
    }


def _dump_custom_subclass(row: Any) -> dict:
    """``CustomSubclass`` row → ``SubclassFeature`` JSON dict.

    Filename slug combines the parent class and subclass slugs the same way
    the shipped files do (``<class>__<sub>``) so the resolver finds them
    under the same lookup convention."""
    raw_features = _maybe_json(row.features) or []
    combined_slug = f"{row.class_slug}__{row.sub_slug}"
    return {
        "slug": combined_slug,
        "name": row.name,
        "class_slug": row.class_slug,
        "subclass_flavor": row.flavor or "",
        # Keep structured features so the existing parser path still works.
        # The schema accepts ``Any`` here precisely so both list-of-dict and
        # markdown-blob shapes load cleanly.
        "features": raw_features,
        "actions": [],
        "system": row.system or "dnd5e",
        "scope": _scope_for(row),
        "source": "homebrew",
        "owner": row.created_by_user_id,
        "_attribution": "Migrated from CustomSubclass DB row at v2.0.0.",
    }


def _dump_custom_race(row: Any) -> dict:
    """``CustomRace`` row → ``Race`` JSON dict."""
    return {
        "slug": row.race_slug,
        "name": row.name,
        "ability_bonuses": _maybe_json(row.ability_bonuses) or [],
        "size": row.size or "Medium",
        "speed": row.speed if row.speed is not None else 30,
        "age": row.age or "",
        "alignment": row.alignment or "",
        "languages": row.languages or "",
        "traits": _maybe_json(row.traits) or [],
        "actions": [],
        "system": row.system or "dnd5e",
        "scope": _scope_for(row),
        "source": "homebrew",
        "owner": row.created_by_user_id,
        "_attribution": "Migrated from CustomRace DB row at v2.0.0.",
    }


def _dump_custom_feat(row: Any) -> dict:
    """``CustomFeat`` row → ``Feat`` JSON dict."""
    return {
        "slug": row.feat_slug,
        "name": row.name,
        "prerequisite": row.prerequisite or "",
        "desc": row.desc or "",
        "actions": [],
        "system": row.system or "dnd5e",
        "scope": _scope_for(row),
        "source": "homebrew",
        "owner": row.created_by_user_id,
        "_attribution": "Migrated from CustomFeat DB row at v2.0.0.",
    }


def _slugify(name: str) -> str:
    """Action ids inside the monster's unified ``actions`` list need stable
    keys derived from the action name (Open5e's structured action entries
    don't have explicit ids)."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "unnamed"


def _dump_custom_monster(row: Any) -> dict:
    """``CustomMonster`` row → ``Monster`` JSON dict.

    Coalesces the four legacy action-list columns (``actions``, ``reactions``,
    ``special_abilities``, ``legendary_actions``) into a single
    ``actions: list[Action]`` array with the appropriate ``category``."""
    unified: list[dict] = []
    for legacy_attr, category in (
        ("actions", "action"),
        ("reactions", "reaction"),
        ("special_abilities", "special_ability"),
        ("legendary_actions", "legendary_action"),
    ):
        entries = _maybe_json(getattr(row, legacy_attr, None)) or []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = (entry.get("name") or "").strip()
            unified.append({
                "id": entry.get("id") or _slugify(name) or f"unnamed-{category}",
                "name": name,
                "desc": entry.get("desc") or "",
                "min_level": entry.get("level") or 1,
                "category": category,
            })

    speed = _maybe_json(row.speed) or {}
    if not isinstance(speed, dict):
        speed = {"walk": speed}

    return {
        "slug": row.monster_slug,
        "name": row.name,
        "size": row.size or "Medium",
        "type": row.type or "humanoid",
        "alignment": row.alignment or "unaligned",
        "armor_class": row.armor_class or 10,
        "armor_desc": row.armor_desc or "",
        "hit_points": row.hit_points or 1,
        "hit_dice": row.hit_dice or "",
        "speed": speed,
        "strength": row.strength or 10,
        "dexterity": row.dexterity or 10,
        "constitution": row.constitution or 10,
        "intelligence": row.intelligence or 10,
        "wisdom": row.wisdom or 10,
        "charisma": row.charisma or 10,
        "damage_vulnerabilities": row.damage_vulnerabilities or "",
        "damage_resistances": row.damage_resistances or "",
        "damage_immunities": row.damage_immunities or "",
        "condition_immunities": row.condition_immunities or "",
        "senses": row.senses or "",
        "languages": row.languages or "",
        "challenge_rating": row.challenge_rating or "0",
        "actions": unified,
        "system": row.system or "dnd5e",
        "scope": _scope_for(row),
        "source": "homebrew",
        "owner": row.created_by_user_id,
        "_attribution": "Migrated from CustomMonster DB row at v2.0.0. Legacy "
        "actions/reactions/special_abilities/legendary_actions columns "
        "coalesced into a single 'actions' array with 'category' labels.",
    }


def _dump_custom_background(row: Any) -> dict:
    """``CustomBackground`` row → ``Background`` JSON dict."""
    return {
        "slug": row.background_slug,
        "name": row.name,
        "skill_proficiencies": row.skill_proficiencies or "",
        "tool_proficiencies": row.tool_proficiencies or "",
        "languages": row.languages or "",
        "equipment": row.equipment or "",
        "feature_name": row.feature_name or "",
        "feature_desc": row.feature_desc or "",
        "suggested_characteristics": "",
        "actions": [],
        "system": row.system or "dnd5e",
        "scope": _scope_for(row),
        "source": "homebrew",
        "owner": row.created_by_user_id,
        "_attribution": "Migrated from CustomBackground DB row at v2.0.0.",
    }


# ── Runner ────────────────────────────────────────────────────────────────────
# Table → (content_type_dir, dumper_fn) so the runner can loop over them.
_EXPORT_MAP: list[tuple[str, str, Any]] = [
    ("custom_classes",      "class_features",    _dump_custom_class),
    ("custom_subclasses",   "subclass_features", _dump_custom_subclass),
    ("custom_races",        "races",             _dump_custom_race),
    ("custom_feats",        "feats",             _dump_custom_feat),
    ("custom_monsters",     "monsters",          _dump_custom_monster),
    ("custom_backgrounds",  "backgrounds",       _dump_custom_background),
]


def run_v52_migration(engine: Engine) -> dict[str, int]:
    """Export then drop. Returns a per-table count for the boot log."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    present = [t for (t, _, _) in _EXPORT_MAP if t in table_names]
    if not present:
        log.info("v52 migration: no Custom* tables present; nothing to do.")
        return {}

    # Pre-flight count so the boot log shows what the migration intends to do.
    pre_counts: dict[str, int] = {}
    with engine.connect() as conn:
        for table_name, _, _ in _EXPORT_MAP:
            if table_name in table_names:
                pre_counts[table_name] = conn.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                ).scalar() or 0
    total_rows = sum(pre_counts.values())
    log.info("v52 migration: %d Custom* rows to export across %d table(s)",
             total_rows, len(pre_counts))

    # Export all rows, then DROP the tables, inside one transaction.
    written_counts: dict[str, int] = {}
    with engine.begin() as conn:
        for table_name, type_dir, dumper in _EXPORT_MAP:
            if table_name not in table_names:
                continue
            rows = conn.execute(text(f"SELECT * FROM {table_name}")).fetchall()
            for row in rows:
                record = dumper(row)
                write_homebrew(
                    record,
                    system=record.get("system") or "dnd5e",
                    type=type_dir,
                    scope=record.get("scope") or "global",
                )
            written_counts[table_name] = len(rows)
            log.info("v52 migration: exported %d rows from %s",
                     len(rows), table_name)

        # Only drop after every export wrote successfully (any exception above
        # rolls the transaction back and leaves the tables intact).
        for table_name, _, _ in _EXPORT_MAP:
            if table_name in table_names:
                conn.execute(text(f"DROP TABLE {table_name}"))
                log.info("v52 migration: dropped %s", table_name)

    if sum(written_counts.values()) != total_rows:
        log.error("v52 migration: pre-flight expected %d rows, wrote %d. "
                  "Manual review of the homebrew volume is recommended.",
                  total_rows, sum(written_counts.values()))
    return written_counts
