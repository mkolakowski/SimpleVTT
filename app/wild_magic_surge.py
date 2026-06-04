"""Wild Magic Surge table — 50 entries from PHB p.104.

Used by the v2.99.228 `/cast_spell` post-cast hook for Wild Magic
Sorcerers (see docs/plans/wild-magic.md Phase 2). The hook rolls a
d20 after each Lv 1+ sorcerer-class cast; on a natural 1, rolls a
d100 against this table and broadcasts the resulting entry.

Each entry's `name` is a short flavor handle for the GM's chat
notification; `desc` is the RAW effect summary. The GM resolves
the actual mechanical effect — none of the entries auto-execute.

Indexed by the d100 result mapped to a table row (RAW pairs each
2-range to one entry, so we map row = (d100 - 1) // 2 → 0..49).
"""

WILD_MAGIC_SURGE_TABLE: list[dict] = [
    # 01-02
    {"slug": "recurring-surges",
     "name": "Recurring Surges",
     "desc": "Roll on this table at the start of each of your turns for the next minute, ignoring this result on subsequent rolls."},
    # 03-04
    {"slug": "see-invisible",
     "name": "See Invisible",
     "desc": "For the next minute, you can see any invisible creature if you have line of sight to it."},
    # 05-06
    {"slug": "modron-summon",
     "name": "Modron Summon",
     "desc": "A modron chosen and controlled by the DM appears in an unoccupied space within 5 ft of you, then disappears 1 minute later."},
    # 07-08
    {"slug": "fireball-self",
     "name": "Fireball — Self",
     "desc": "You cast Fireball as a 3rd-level spell centered on yourself."},
    # 09-10
    {"slug": "magic-missile-5",
     "name": "Magic Missile (5th)",
     "desc": "You cast Magic Missile as a 5th-level spell."},
    # 11-12
    {"slug": "height-change",
     "name": "Height Change",
     "desc": "Roll a d10. Your height changes by a number of inches equal to the roll. If the roll is odd you shrink; if even you grow."},
    # 13-14
    {"slug": "confusion-self",
     "name": "Confusion — Self",
     "desc": "You cast Confusion centered on yourself."},
    # 15-16
    {"slug": "regenerate-5",
     "name": "Minor Regeneration",
     "desc": "For the next minute, you regain 5 hit points at the start of each of your turns."},
    # 17-18
    {"slug": "feather-beard",
     "name": "Feather Beard",
     "desc": "You grow a long beard made of feathers that remains until you sneeze, at which point the feathers explode out from your face."},
    # 19-20
    {"slug": "grease-self",
     "name": "Grease — Self",
     "desc": "You cast Grease centered on yourself."},
    # 21-22
    {"slug": "next-save-disadv",
     "name": "Save Disadvantage Aura",
     "desc": "Creatures have disadvantage on saving throws against the next spell you cast in the next minute that involves a saving throw."},
    # 23-24
    {"slug": "blue-skin",
     "name": "Blue Skin",
     "desc": "Your skin turns a vibrant shade of blue. A Remove Curse spell can end this effect."},
    # 25-26
    {"slug": "third-eye",
     "name": "Third Eye",
     "desc": "An eye appears on your forehead for the next minute. During that time, you have advantage on Wisdom (Perception) checks that rely on sight."},
    # 27-28
    {"slug": "action-to-bonus",
     "name": "Action → Bonus",
     "desc": "For the next minute, all your spells with a casting time of 1 action have a casting time of 1 bonus action."},
    # 29-30
    {"slug": "teleport-60",
     "name": "Teleport 60",
     "desc": "You teleport up to 60 feet to an unoccupied space of your choice that you can see."},
    # 31-32
    {"slug": "astral-blink",
     "name": "Astral Blink",
     "desc": "You are transported to the Astral Plane until the end of your next turn, then return to the space you previously occupied or the nearest unoccupied space."},
    # 33-34
    {"slug": "maximize-next-spell",
     "name": "Maximize Next Damage",
     "desc": "Maximize the damage of the next damaging spell you cast within the next minute."},
    # 35-36
    {"slug": "age-shift",
     "name": "Age Shift",
     "desc": "Roll a d10. Your age changes by a number of years equal to the roll. If the roll is odd, you get younger (minimum 1 year). If even, you get older."},
    # 37-38
    {"slug": "flumph-summon",
     "name": "Flumph Summon",
     "desc": "1d6 flumphs controlled by the DM appear in unoccupied spaces within 60 ft of you and are frightened of you. They vanish after 1 minute."},
    # 39-40
    {"slug": "regain-2d10",
     "name": "Heal 2d10",
     "desc": "You regain 2d10 hit points."},
    # 41-42
    {"slug": "potted-plant",
     "name": "Potted Plant",
     "desc": "You turn into a potted plant until the start of your next turn. While a plant, you are incapacitated and have vulnerability to all damage. If you drop to 0 hp, your pot breaks and your form reverts."},
    # 43-44
    {"slug": "teleport-bonus-action",
     "name": "Blink Steps",
     "desc": "For the next minute, you can teleport up to 20 ft as a bonus action on each of your turns."},
    # 45-46
    {"slug": "levitate-self",
     "name": "Levitate — Self",
     "desc": "You cast Levitate on yourself."},
    # 47-48
    {"slug": "unicorn-companion",
     "name": "Unicorn Companion",
     "desc": "A unicorn controlled by the DM appears in a space within 5 ft of you, then disappears 1 minute later."},
    # 49-50
    {"slug": "pink-bubbles",
     "name": "Pink Bubbles",
     "desc": "You can't speak for the next minute. Whenever you try, pink bubbles float out of your mouth."},
    # 51-52
    {"slug": "spectral-shield",
     "name": "Spectral Shield",
     "desc": "A spectral shield hovers near you for the next minute, granting you a +2 bonus to AC and immunity to Magic Missile."},
    # 53-54
    {"slug": "alcohol-immune",
     "name": "Sober Streak",
     "desc": "You are immune to being intoxicated by alcohol for the next 5d6 days."},
    # 55-56
    {"slug": "hair-falls-out",
     "name": "Hair Loss",
     "desc": "Your hair falls out but grows back within 24 hours."},
    # 57-58
    {"slug": "flammable-touch",
     "name": "Flammable Touch",
     "desc": "For the next minute, any flammable object you touch that isn't being worn or carried by another creature bursts into flame."},
    # 59-60
    {"slug": "regain-slot",
     "name": "Regain Lowest Slot",
     "desc": "You regain your lowest-level expended spell slot."},
    # 61-62
    {"slug": "shouting-voice",
     "name": "Shouting Voice",
     "desc": "For the next minute, you must shout when you speak."},
    # 63-64
    {"slug": "fog-cloud-self",
     "name": "Fog Cloud — Self",
     "desc": "You cast Fog Cloud centered on yourself."},
    # 65-66
    {"slug": "lightning-burst",
     "name": "Lightning Burst",
     "desc": "Up to three creatures you choose within 30 ft of you take 4d10 lightning damage."},
    # 67-68
    {"slug": "fear-nearest",
     "name": "Fear Nearest",
     "desc": "You are frightened by the nearest creature until the end of your next turn."},
    # 69-70
    {"slug": "mass-invisibility",
     "name": "Mass Invisibility",
     "desc": "Each creature within 30 ft of you becomes invisible for the next minute. The invisibility ends on a creature when it attacks or casts a spell."},
    # 71-72
    {"slug": "damage-resistance-all",
     "name": "Total Resistance",
     "desc": "You gain resistance to all damage for the next minute."},
    # 73-74
    {"slug": "random-poisoned",
     "name": "Random Poisoned",
     "desc": "A random creature within 60 ft of you becomes poisoned for 1d4 hours."},
    # 75-76
    {"slug": "glowing-aura",
     "name": "Blinding Glow",
     "desc": "You glow with bright light in a 30-ft radius for the next minute. Any creature that ends its turn within 5 ft of you is blinded until the end of its next turn."},
    # 77-78
    {"slug": "polymorph-sheep",
     "name": "Polymorph — Self (sheep risk)",
     "desc": "You cast Polymorph on yourself. If you fail the saving throw, you turn into a sheep for the spell's duration."},
    # 79-80
    {"slug": "butterfly-aura",
     "name": "Butterfly Aura",
     "desc": "Illusory butterflies and flower petals flutter in the air within 10 ft of you for the next minute."},
    # 81-82
    {"slug": "extra-action",
     "name": "Extra Action",
     "desc": "You can take one additional action immediately."},
    # 83-84
    {"slug": "necrotic-leech",
     "name": "Necrotic Leech",
     "desc": "Each creature within 30 ft of you takes 1d10 necrotic damage. You regain hit points equal to the sum of the necrotic damage dealt."},
    # 85-86
    {"slug": "mirror-image",
     "name": "Mirror Image",
     "desc": "You cast Mirror Image."},
    # 87-88
    {"slug": "random-fly",
     "name": "Random Fly",
     "desc": "You cast Fly on a random creature within 60 ft of you."},
    # 89-90
    {"slug": "true-invisibility",
     "name": "Silent Invisibility",
     "desc": "You become invisible for the next minute. During that time, other creatures can't hear you. The invisibility ends if you attack or cast a spell."},
    # 91-92
    {"slug": "reincarnate-if-die",
     "name": "Reincarnate Insurance",
     "desc": "If you die within the next minute, you immediately come back to life as if by the Reincarnate spell."},
    # 93-94
    {"slug": "size-up",
     "name": "Size Up",
     "desc": "Your size increases by one category — from Medium to Large, for example. If there isn't room for you to increase in size, you attain the maximum possible size in the space available."},
    # 95-96
    {"slug": "piercing-vulnerability",
     "name": "Piercing Vulnerability Aura",
     "desc": "You and all creatures within 30 ft of you gain vulnerability to piercing damage for the next minute."},
    # 97-98
    {"slug": "ethereal-music",
     "name": "Ethereal Music",
     "desc": "You are surrounded by faint, ethereal music for the next minute."},
    # 99-00
    {"slug": "regain-all-sp",
     "name": "Regain All Sorcery Points",
     "desc": "You regain all expended sorcery points."},
]


def surge_entry_for_d100(d100: int) -> dict:
    """Map a d100 result (1-100) to a Wild Magic Surge entry. RAW
    pairs each 2-range, so d100 % 2 collapse into the same row.
    Returns a copy of the table entry plus the rolled d100.

    Out-of-range inputs clamp to [1, 100] for safety.
    """
    n = max(1, min(100, int(d100)))
    idx = (n - 1) // 2
    entry = dict(WILD_MAGIC_SURGE_TABLE[idx])
    entry["d100"] = n
    return entry
