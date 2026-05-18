/* dnd5e_feature_economy.js — canonical per-feature action-cost table.
 *
 * Phase 3 of the action-economy tracker (see docs/plans/class-content-status.md
 * section E). Maps class / subclass features to the economy slot they
 * consume. Lookup is keyed by a stable feature slug, plus an optional
 * sub-option slug (e.g. Cunning Action's three modes, Channel Divinity's
 * per-domain options).
 *
 * Consumed by:
 *   • app/templates/sheet_dnd5e.html — the Class abilities panel reads
 *     this table to decide which chip to flip when a feature button is
 *     clicked, and what description to show in the roll-log entry.
 *   • app/routes/tabletop_routes.py — a small Python mirror of this
 *     table powers the /api/campaign/{id}/use_feature endpoint so the
 *     server can derive the slot without trusting the client.
 *
 * Slots: "action" / "bonus" / "reaction" / "free". The "free" slot
 * means the feature does NOT consume any economy slot (e.g. Action
 * Surge grants an extra action, doesn't consume one). The chip code
 * treats "free" as a no-op.
 *
 * Keys: lowercase kebab-case feature slug. When a feature has sub-
 * options (Cunning Action: dash / disengage / hide; Channel Divinity:
 * turn-undead / preserve-life) the table nests `options` keyed by
 * option slug. Each option can override the slot if needed (most
 * inherit the parent feature's slot).
 *
 * Adding a new entry: append to the right class block alphabetically.
 * Mirror it in app/routes/tabletop_routes.py's _FEATURE_ECONOMY dict
 * so the server-side validator agrees.
 */

window._FEATURE_ECONOMY = {
    /* ── Rogue ───────────────────────────────────────────────────── */
    'cunning-action': {
        slot: 'bonus',
        class: 'rogue',
        unlock_level: 2,
        label: 'Cunning Action',
        desc: 'Take Dash, Disengage, or Hide as a bonus action.',
        options: {
            'dash': { label: 'Dash', desc: 'Move up to your speed again this turn.' },
            'disengage': { label: 'Disengage', desc: "Your movement doesn't provoke opportunity attacks this turn." },
            'hide': { label: 'Hide', desc: 'Make a Dexterity (Stealth) check to hide.' },
        },
    },
    'stroke-of-luck': {
        slot: 'free',
        class: 'rogue',
        unlock_level: 20,
        label: 'Stroke of Luck',
        desc: 'Once per short or long rest: turn a missed attack into a hit, OR turn a failed ability check into a 20.',
        // v2.16.2: curated table entry only. No demo Rogue PC at Lv 20
        // (Pip is Lv 5). The full UX needs (B) roll-time intercept to
        // prompt the player AFTER a miss/failure — "want to use Stroke
        // of Luck?" — and rewrite the d20 result. slot:'free' because
        // the reroll/upgrade is a once-per-rest resource use, not an
        // action/bonus/reaction.
    },

    /* ── Fighter ─────────────────────────────────────────────────── */
    'second-wind': {
        slot: 'bonus',
        class: 'fighter',
        unlock_level: 1,
        label: 'Second Wind',
        desc: 'Regain 1d10 + your fighter level HP. Recharges on a short or long rest.',
    },
    'action-surge': {
        slot: 'free',
        class: 'fighter',
        unlock_level: 2,
        label: 'Action Surge',
        desc: 'Take one additional action on this turn. Recharges on a short or long rest.',
        // Action Surge GRANTS an extra action — doesn't consume one. The
        // chip code treats slot:"free" as a no-op so clicking the button
        // doesn't flip any chip (the player will then click their actual
        // second action which marks Act for the round; the previously-
        // used Act stays burnt). Phase 4's GM shift+click chip-clear is
        // the proper way to model "I just got a second action."
    },
    'indomitable': {
        slot: 'free',
        class: 'fighter',
        unlock_level: 9,
        label: 'Indomitable',
        desc: 'Reroll a failed saving throw. Must use the new roll. 1/short rest at Lv 9, 2/short rest at Lv 13, 3/short rest at Lv 17.',
        // v2.16.2: curated table entry only. No demo Fighter PC at Lv
        // 9+ yet; future Phase A.4 (demo Fighter) would land the
        // resource counter, the resource ⚡ Use special-case for the
        // save-reroll prompt (depends on (B) roll-time intercept for
        // the actual "let me reroll that save I just failed" UX),
        // and the harness happy-path test. slot:'free' because the
        // reroll itself doesn't consume an action / bonus / reaction
        // — it just costs a use of the resource.
    },

    /* ── Cleric ──────────────────────────────────────────────────── */
    'channel-divinity': {
        slot: 'action',
        class: 'cleric',  // parent class for the top-level entry; per-option ``class`` tags below allow Paladin CD options to live in the same key
        unlock_level: 2,
        label: 'Channel Divinity',
        desc: 'Channel divine energy to fuel a class- and subclass-specific effect.',
        // v2.9.0 added per-option ``subclass`` tags so the picker
        // could filter by cleric domain. v2.14.3 adds a ``class``
        // tag too so the same channel-divinity resource key can
        // hold Paladin options alongside Cleric ones — Caelan
        // (Oath of Devotion) sees Sacred Weapon + Turn the Unholy;
        // Tavik (Life Domain) sees Turn Undead + Preserve Life.
        // The picker in sheet_dnd5e.html filters: keep option if
        // option.class matches the character's class AND
        // option.subclass matches their subclass (with "any" as
        // wildcard on either field).
        options: {
            // ── Cleric options ────────────────────────────────
            'turn-undead': { label: 'Turn Undead', desc: 'Each undead within 30 ft makes a Wisdom save or flees for 1 minute.', class: 'cleric', subclass: 'any' },
            'preserve-life': { label: 'Preserve Life', desc: 'Distribute 5 × cleric level HP among creatures within 30 ft, none raised above half max HP.', class: 'cleric', subclass: 'life' },
            'radiance-of-the-dawn': { label: 'Radiance of the Dawn', desc: 'Dispel magical darkness, deal 2d10 + cleric level radiant damage on a failed Con save (each enemy within 30 ft).', class: 'cleric', subclass: 'light' },
            'guided-strike': { label: 'Guided Strike', desc: '+10 bonus to one attack roll, declared after seeing the d20.', class: 'cleric', subclass: 'war' },
            // ── Paladin options (v2.14.3) ─────────────────────
            'sacred-weapon': { label: 'Sacred Weapon', desc: 'Imbue a weapon you hold with positive energy for 1 minute: +CHA mod to attack rolls, deals magical damage, emits 20 ft bright light.', class: 'paladin', subclass: 'devotion' },
            'turn-the-unholy': { label: 'Turn the Unholy', desc: 'Each fiend or undead within 30 ft that can see/hear you must succeed on a Wisdom save or be turned for 1 minute.', class: 'paladin', subclass: 'devotion' },
        },
    },

    /* ── Paladin ─────────────────────────────────────────────────── */
    'lay-on-hands': {
        slot: 'action',
        class: 'paladin',
        unlock_level: 1,
        label: 'Lay on Hands',
        desc: 'Spend from your pool (5 × paladin level) to heal a touched creature or cure poison/disease.',
    },
    'divine-smite': {
        slot: 'free',
        class: 'paladin',
        unlock_level: 2,
        label: 'Divine Smite',
        desc: 'After hitting with a melee weapon attack, expend a spell slot for +2d8 radiant (+1d8 per slot level above 1st; +1d8 vs undead/fiends).',
        // "Free" because Divine Smite augments an attack you already made
        // — the attack itself consumed action; the smite doesn't add a
        // second economy cost.
    },
    'divine-sense': {
        slot: 'action',
        class: 'paladin',
        unlock_level: 1,
        label: 'Divine Sense',
        desc: 'Detect celestial / fiend / undead within 60 ft until end of next turn. 1 + CHA mod uses per long rest.',
    },
    'cleansing-touch': {
        slot: 'action',
        class: 'paladin',
        unlock_level: 14,
        label: 'Cleansing Touch',
        desc: 'End one spell on yourself or one willing creature you touch. CHA mod uses per long rest.',
        // v2.15.6: curated entry only — no demo PC has Cleansing Touch
        // (Lv 14 Paladin feature; Caelan is Lv 5). Server-side accepts
        // the key so a future Lv 14+ fixture can fire it. The target-
        // picker UI (RAW: "yourself or one willing creature you touch")
        // is filed for that future commit; today /use_feature with this
        // key announces the use generically without a target.
    },

    /* ── Bard ────────────────────────────────────────────────────── */
    'bardic-inspiration': {
        slot: 'bonus',
        class: 'bard',
        unlock_level: 1,
        label: 'Bardic Inspiration',
        desc: 'Pick one creature within 60 ft (other than yourself). They gain a bonus die to add to one ability check, attack roll, or save in the next 10 minutes.',
    },
    'cutting-words': {
        slot: 'reaction',
        class: 'bard',
        subclass: 'lore',
        unlock_level: 3,
        label: 'Cutting Words',
        desc: 'Reaction (Lore Lv 3): spend 1 Bardic Inspiration use to subtract a Bardic Inspiration die roll from an enemy attack roll, ability check, or damage roll within 60 ft.',
        // v2.15.7: dedicated /use_cutting_words endpoint rolls the BI
        // die server-side + decrements BI + marks the reaction slot
        // + announces. UI-side a class_features button on Lyra's sheet
        // routes to that endpoint (mirror of /use_bardic_inspiration).
        // No roll-time intercept yet — GM applies the subtraction
        // manually to whatever roll just triggered the reaction.
    },

    /* ── Monk ────────────────────────────────────────────────────── */
    'flurry-of-blows': {
        slot: 'bonus',
        class: 'monk',
        unlock_level: 2,
        label: 'Flurry of Blows',
        desc: 'Immediately after taking the Attack action, spend 1 ki to make two unarmed strikes as a bonus action.',
    },
    'patient-defense': {
        slot: 'bonus',
        class: 'monk',
        unlock_level: 2,
        label: 'Patient Defense',
        desc: 'Spend 1 ki to take the Dodge action as a bonus action.',
    },
    'step-of-the-wind': {
        slot: 'bonus',
        class: 'monk',
        unlock_level: 2,
        label: 'Step of the Wind',
        desc: 'Spend 1 ki to take the Disengage or Dash action as a bonus action; your jump distance doubles for the turn.',
    },

    /* ── Druid ───────────────────────────────────────────────────── */
    'wild-shape': {
        slot: 'action',
        class: 'druid',
        unlock_level: 2,
        label: 'Wild Shape',
        desc: 'Transform into a beast you have seen before.',
        // v2.14.5: Wild Shape is routed through the BeastPicker →
        // /transform endpoint, not /use_feature. /transform computes
        // the slot server-side via _wild_shape_economy_slot (Moon
        // Druid → bonus; default → action) and returns it on the
        // response as ``economy_slot`` for the chip to flip. So the
        // 'action' literal on this entry is the fallback for
        // non-Moon flows and the dead-code path if anything ever
        // looks up Wild Shape via /use_feature.
    },

    /* ── Barbarian ───────────────────────────────────────────────── */
    'rage': {
        slot: 'bonus',
        class: 'barbarian',
        unlock_level: 1,
        label: 'Rage',
        desc: '+damage on STR melee attacks, advantage on STR checks/saves, resistance to bludgeoning/piercing/slashing.',
    },
    'reckless-attack': {
        slot: 'free',
        class: 'barbarian',
        unlock_level: 2,
        label: 'Reckless Attack',
        desc: 'On your first attack this turn, gain advantage on melee STR attacks but attacks against you have advantage until your next turn.',
        // Modifies your existing attack action; doesn't consume a new slot.
    },

    /* ── Wizard ──────────────────────────────────────────────────── */
    'arcane-recovery': {
        slot: 'free',
        class: 'wizard',
        unlock_level: 1,
        label: 'Arcane Recovery',
        desc: 'Once per day during a short rest, regain spell slots whose combined level ≤ ⌈wizard_lv/2⌉. L6+ slots are not eligible.',
        // v2.16.1: out-of-combat feature ("once per day during a short
        // rest") so slot:'free' — no chip flip, no action-economy cost.
        // Resource ⚡ Use opens a slot-restore modal; /use_arcane_recovery
        // validates the allowance + decrements counter + restores slots
        // atomically.
    },

    /* ── Sorcerer ────────────────────────────────────────────────── */
    'font-of-magic': {
        slot: 'free',
        class: 'sorcerer',
        unlock_level: 2,
        label: 'Font of Magic',
        desc: 'Convert spell slots to sorcery points (and vice versa) as a bonus action. Costs: SP → slot at 2/3/5/6/7 SP per L1/L2/L3/L4/L5 slot; slot → SP at the slot level (e.g. L3 slot → 3 SP).',
        // v2.16.2: curated table entry only. No demo Sorcerer PC. The
        // full feature ships when Phase A.4+ adds a Sorcerer fixture
        // — that commit lands the sorcery-points resource counter,
        // the slot-conversion picker (a sibling to Arcane Recovery's
        // restore-modal but with conversion costs), and a dedicated
        // /use_font_of_magic endpoint. slot:'free' because the
        // conversion itself is a bonus action (mechanically) but
        // the action-economy chip is per-class-feature; the chip
        // flip would happen via /use_feature's slot resolution.
        // Future v2 can promote this to slot:'bonus' once a Sorcerer
        // demo exists to verify the chip-marking.
    },
    'quickened-spell': {
        slot: 'bonus',
        class: 'sorcerer',
        unlock_level: 3,
        label: 'Quickened Spell',
        desc: 'Spend 2 sorcery points to change the casting time of a 1-action spell to 1 bonus action this turn.',
        // Note: this metamagic effectively swaps action → bonus for the
        // spell it modifies, not adds an extra cost. UI should let the
        // player flip the cast slot manually; we tag it bonus here
        // because clicking the Quickened button itself is the slot
        // selector for the spell that follows.
    },
};

/* Lookup helper. Returns the merged feature + option entry or null
 * when the key isn't recognised. The `slot` on the returned object is
 * the option's slot if specified, else the parent feature's slot.
 *
 * Example:
 *   getFeatureEconomy('cunning-action', 'disengage')
 *   → { slot: 'bonus', label: 'Disengage', desc: '...', parent_label: 'Cunning Action' }
 *
 *   getFeatureEconomy('second-wind')
 *   → { slot: 'bonus', label: 'Second Wind', desc: '...' }
 */
window.getFeatureEconomy = function (featureKey, optionKey) {
    const fkey = String(featureKey || '').toLowerCase();
    const feat = window._FEATURE_ECONOMY[fkey];
    if (!feat) return null;
    if (!optionKey) {
        return {
            slot: feat.slot,
            label: feat.label,
            desc: feat.desc,
            class: feat.class,
            unlock_level: feat.unlock_level,
        };
    }
    const okey = String(optionKey).toLowerCase();
    const opt = (feat.options || {})[okey];
    if (!opt) return null;
    return {
        slot: opt.slot || feat.slot,
        label: opt.label,
        desc: opt.desc,
        parent_label: feat.label,
        class: feat.class,
        unlock_level: feat.unlock_level,
    };
};
