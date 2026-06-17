"""Single source of truth for the per-condition impact descriptions
that drive the mini-sheet abilities-header warning pill.

Prior to v2.157.4, the same map was duplicated in two places:
  - ``app/templates/_mini_sheet_card.html`` as the Jinja
    ``_cond_impact_map`` literal (consumed by the server-side render
    of the v2.157.1 PC warning pill).
  - ``app/templates/tabletop.html`` as the JS ``_COND_IMPACT_MAP``
    const (consumed by the v2.157.2 NPC + v2.157.3 PC live-update
    JS hydration paths).

Both maps must agree exactly — the user-facing tooltip text is
identical and the keys gate the same condition-buff names. Keeping
two copies in lockstep by convention is fragile. v2.157.4 moves the
authoritative map here and:
  - exposes it as a Jinja global (``CONDITION_IMPACTS``) via
    ``app/templates.py``;
  - renders it as a ``window._COND_IMPACT_MAP`` JSON blob from
    ``tabletop.html`` so the runtime JS reads the same dict.

Adding a new condition is now a single edit to the dict below.

The keys are the canonical buff-key strings used everywhere else in
the codebase (lower-case, hyphen-free for the standard RAW
conditions — Paralyzed / Stunned / etc. — matches the keys the
server-side helpers ``_attacker_has_condition_disadvantage`` /
``_target_has_condition_advantage`` / ``_npc_save_condition_disadvantage``
/ ``_saver_auto_fails_strdex_save`` / ``_roll_condition_disadvantage``
read).

The values are RAW PHB Appendix A summaries kept compact enough to
fit in a multi-line tooltip without wrapping awkwardly. Each entry
covers the impact the v2.152.0–v2.157.0 server-side automation
actually enforces (so the player/GM sees what the server will do, not
the full RAW condition rider list).
"""
from __future__ import annotations


CONDITION_IMPACTS: "dict[str, str]" = {
    "poisoned":      "disadvantage on attacks + ability checks",
    "frightened":    "disadvantage on attacks + ability checks",
    "restrained":    "disadvantage on attacks; attacks against have advantage; disadvantage on DEX saves",
    "blinded":       "disadvantage on attacks; attacks against have advantage",
    "prone":         "disadvantage on attacks (own); melee attacks against have advantage",
    "paralyzed":     "incapacitated · auto-fail STR + DEX saves · attacks against have advantage · melee = auto-crit",
    "stunned":       "incapacitated · auto-fail STR + DEX saves · attacks against have advantage",
    "unconscious":   "incapacitated, prone · auto-fail STR + DEX saves · attacks against have advantage · melee = auto-crit",
    "petrified":     "auto-fail STR + DEX saves · resistance to all damage",
    "invisible":     "advantage on own attack rolls; attacks against have disadvantage",
    # v2.401.0 — surfaces the post-v2.385.0–v2.391.0 enforcement sweep
    # (Incapacitated action gate, Grappled clause 1, Charmed clause 1)
    # in the same warning-pill UI the d20-adv/dis conditions already use.
    "charmed":       "cannot attack charmer or target charmer with harmful spells",
    "grappled":      "speed reduced to 0",
    "incapacitated": "cannot take actions, bonus actions, or reactions",
}
