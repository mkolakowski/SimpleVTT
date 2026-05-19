/* Shared roll-result popup (1.11.0).
 *
 * Lifted out of tabletop.html so character-sheet pages get the same
 * animated dice-shape popup the tabletop already uses. Renders inside
 * #roll-toast-container — auto-created on the body if missing so pages
 * that don't ship the container element still work. CSS lives in
 * app/static/style.css.
 *
 * Two entry points:
 *
 *   1. document.addEventListener('vtt:ws-message', …)  — broadcast-driven.
 *      The tabletop's WebSocket handler dispatches a CustomEvent with
 *      ``{type: 'roll', data: <roll record>}``; the listener below
 *      filters by visibility and fires the popup. This is the legacy
 *      tabletop behaviour and is unchanged.
 *
 *   2. window.showRollToast(rollData) — direct call.
 *      Use when local code already has the roll record (e.g. a sheet
 *      action button just POSTed to /api/campaign/{id}/roll and got the
 *      breakdown back) and wants to surface the popup without going
 *      through WebSocket. The shape mirrors the broadcast payload:
 *        { visibility, user_id, user_name, char_name, expression,
 *          total, breakdown, note }
 *      Any field except `expression`, `total`, `breakdown` is optional;
 *      defaults fill in for the missing ones.
 */
(function () {
    'use strict';

    function _ensureContainer() {
        let container = document.getElementById('roll-toast-container');
        if (container) return container;
        container = document.createElement('div');
        container.id = 'roll-toast-container';
        document.body.appendChild(container);
        return container;
    }

    /* SVG inner markup for each die face.
       d4 is INVERTED (flat top, point bottom) — visually distinct from d20
       (point top, flat bottom). No inner lines on d8 — the horizontal line
       would cross the number. */
    const DIE_SHAPES = {
        4:   `<polygon points="7,8 93,8 50,92" fill="none" stroke="currentColor" stroke-width="8" stroke-linejoin="round"/>`,
        6:   `<rect x="10" y="10" width="80" height="80" rx="12" fill="none" stroke="currentColor" stroke-width="8"/>`,
        8:   `<polygon points="50,8 92,50 50,92 8,50" fill="none" stroke="currentColor" stroke-width="8" stroke-linejoin="round"/>`,
        10:  `<polygon points="50,6 88,36 74,90 26,90 12,36" fill="none" stroke="currentColor" stroke-width="8" stroke-linejoin="round"/>`,
        12:  `<polygon points="50,8 88,33 76,77 24,77 12,33" fill="none" stroke="currentColor" stroke-width="8" stroke-linejoin="round"/>`,
        20:  `<polygon points="50,7 93,28.5 93,71.5 50,93 7,71.5 7,28.5" fill="none" stroke="currentColor" stroke-width="8" stroke-linejoin="round"/><polygon points="50,7 93,71.5 7,71.5" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" opacity="0.45"/><polygon points="93,28.5 50,93 7,28.5" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" opacity="0.45"/>`,
        100: `<circle cx="50" cy="50" r="43" fill="none" stroke="currentColor" stroke-width="8"/><circle cx="50" cy="50" r="28" fill="none" stroke="currentColor" stroke-width="3" opacity="0.35"/>`,
    };

    function _makeDie(sides, size) {
        const NS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('class', 'rt-die');
        svg.setAttribute('width', size);
        svg.setAttribute('height', size);
        svg.setAttribute('viewBox', '0 0 100 100');
        svg.setAttribute('aria-hidden', 'true');
        svg.innerHTML = DIE_SHAPES[sides] || DIE_SHAPES[6];

        const t = document.createElementNS(NS, 'text');
        t.setAttribute('x', '50');
        /* d4 is inverted (flat top, point bottom) — centroid in upper third.
           d20 is upright (point top, flat bottom) — centroid in lower third. */
        t.setAttribute('y', sides === 4 ? '38' : '54');
        t.setAttribute('text-anchor', 'middle');
        t.setAttribute('dominant-baseline', 'middle');
        t.setAttribute('fill', 'currentColor');
        t.setAttribute('font-size', sides >= 100 ? '26' : sides >= 20 ? '34' : '40');
        t.setAttribute('font-weight', '800');
        svg.appendChild(t);
        return { svg, t };
    }

    /* Parse individual die values out of the breakdown string.
       Format: "2d6[3,5]=8 +1d4[2]=2  =>  10" → [3, 5, 2] */
    function _parseDieVals(breakdown) {
        const out = [];
        const re = /\[([^\]]+)\]/g;
        let m;
        while ((m = re.exec(String(breakdown))) !== null) {
            m[1].split(',').forEach(v => { const n = parseInt(v); if (!isNaN(n)) out.push(n); });
        }
        return out;
    }

    /* Detect an advantage/disadvantage pair in the roll (2.2.1).
       Looks at both the expression (2dNkh1 / 2dNkl1 long form or 1dNa /
       1dNd shorthand) and the breakdown's bracketed pair to identify the
       two-die group and which die was "kept". Returns:
         { sides, isAdv, v1, v2, keptIdx }
       or ``null`` if no adv/dis pair is present. ``keptIdx`` is the
       index into ``[v1, v2]`` of the die that resolved to the total
       (max for advantage, min for disadvantage). Used by ``showRollToast``
       to render both dice with the kept one highlighted. */
    function _detectAdvDis(expression, breakdown) {
        const exprStr = String(expression || '');
        const brkStr = String(breakdown || '');
        let isAdv;
        let sides;
        // Long form: 2dN(kh1|kl1) in the submitted expression
        let m = /(?:^|[+\s-])2d(\d+)(kh1|kl1)\b/i.exec(exprStr);
        if (m) {
            sides = parseInt(m[1]);
            isAdv = m[2].toLowerCase() === 'kh1';
        } else {
            // Shorthand: dN(a|d) or 1dN(a|d). Dice.py expands both to a
            // pair internally and emits ]kh1/]kl1 in the breakdown.
            m = /(?:^|[+\s-])\d*d(\d+)([ad])\b/i.exec(exprStr);
            if (m) {
                sides = parseInt(m[1]);
                isAdv = m[2].toLowerCase() === 'a';
            } else {
                // v2.2.5: the server may have upgraded a single-d20 expression
                // to 2d20kh1 / 2d20kl1 server-side without echoing the new
                // expression back (e.g. the sheet's /roll callers pass the
                // original ``1d20+stat``). Fall back to scanning the breakdown
                // alone for the kept/dropped marker that dice.py always emits.
                // Pattern: ``NdM<mod>[v1,v2]khK`` / ``...klK`` where K=1.
                // ``<mod>`` is optional and may be ``kh1`` / ``kl1`` (long form)
                // or ``a`` / ``d`` (shorthand) — dice.py emits the original
                // expression's mod token before the result bracket.
                const brBlind = /(\d+)d(\d+)(?:kh1|kl1|a|d)?\[(\d+),(\d+)\](kh1|kl1)/i.exec(brkStr);
                if (!brBlind) return null;
                sides = parseInt(brBlind[2]);
                isAdv = brBlind[5].toLowerCase() === 'kh1';
                const v1 = parseInt(brBlind[3]);
                const v2 = parseInt(brBlind[4]);
                const keptIdx = isAdv ? (v1 >= v2 ? 0 : 1) : (v1 <= v2 ? 0 : 1);
                return { sides, isAdv, v1, v2, keptIdx };
            }
        }
        const brRe = isAdv
            ? /\[(\d+),(\d+)\]kh1/i
            : /\[(\d+),(\d+)\]kl1/i;
        const bm = brRe.exec(brkStr);
        if (!bm) return null;
        const v1 = parseInt(bm[1]);
        const v2 = parseInt(bm[2]);
        const keptIdx = isAdv ? (v1 >= v2 ? 0 : 1) : (v1 <= v2 ? 0 : 1);
        return { sides, isAdv, v1, v2, keptIdx };
    }

    function _dismiss(toast) {
        if (toast.dataset.gone) return;
        toast.dataset.gone = '1';
        clearTimeout(toast._timer);
        toast.classList.add('rt-out');
        setTimeout(() => toast.remove(), 370);
    }

    function _meId() {
        return (typeof window !== 'undefined' && window.ME && window.ME.id) || null;
    }

    function showRollToast(r) {
        if (!r || !r.expression) return;
        const container = _ensureContainer();
        const myId = _meId();

        const toast = document.createElement('div');
        toast.className = 'roll-toast rt-animating';
        toast.title = 'Click to dismiss';

        const lbl = document.createElement('div');
        lbl.className = 'rt-label';
        const roller = r.char_name || r.user_name || 'You';
        lbl.textContent = (r.user_id != null && myId != null && r.user_id === myId)
            ? '🎲 ' + (r.note || r.expression)
            : (r.user_id == null
                ? '🎲 ' + (r.note || r.expression)
                : '🎲 ' + roller + ' — ' + (r.note || r.expression));

        /* Build one die element per die in the expression (max 6).
           Count is optional — "d20" treated as "1d20". */
        const MAX_DICE = 6;
        const sides = [];
        for (const m of String(r.expression).matchAll(/(\d*)d(\d+)/gi)) {
            const cnt = parseInt(m[1]) || 1;
            for (let i = 0; i < cnt && sides.length < MAX_DICE; i++) sides.push(parseInt(m[2]));
        }
        if (!sides.length) sides.push(6);

        /* v2.2.1: detect advantage/disadvantage and ensure both dice are
           rendered. The shorthand form (1d20a / 1d20d) only generates a
           single die from the expression-parsing loop above; push a
           second die of the same sides so the toast shows both. */
        const advDis = _detectAdvDis(r.expression, r.breakdown);
        if (advDis && sides.length === 1 && sides[0] === advDis.sides) {
            sides.push(advDis.sides);
        }

        const n    = sides.length;
        const sz   = n === 1 ? 82 : n <= 3 ? 60 : n <= 5 ? 46 : 38;
        const dies = sides.map(s => _makeDie(s, sz));

        const diceRow = document.createElement('div');
        diceRow.className = 'rt-dice';
        dies.forEach(d => diceRow.appendChild(d.svg));

        /* v2.27.0: bonus chip. Show the raw die value(s) on the die face
           and render the flat-bonus modifier as a separate "+N" chip
           beside the dice (e.g. 1d20+5 rolling a 12 → die shows "12",
           chip shows "+5"). Bonus is derived from total - sum(kept die
           values) so it works for plain rolls, multi-die rolls, AND
           advantage/disadvantage (where only the kept die counts). The
           chip is created up-front but its text is set at landing time
           — during the spin we don't know the final value yet. */
        const bonusChip = document.createElement('span');
        bonusChip.className = 'rt-bonus';
        bonusChip.style.visibility = 'hidden';
        diceRow.appendChild(bonusChip);

        /* Sum line shown below the dice for multi-die rolls */
        const sumEl = n > 1
            ? Object.assign(document.createElement('div'), { className: 'rt-sum' })
            : null;

        toast.append(lbl, diceRow);
        if (sumEl) toast.appendChild(sumEl);
        toast.addEventListener('click', () => _dismiss(toast));
        container.appendChild(toast);

        /* Ease-out animation: each die independently cycles 1–sides */
        const delays = [50, 55, 60, 75, 100, 150, 220, 320, 430];
        let di = 0;
        function tick() {
            if (di < delays.length) {
                dies.forEach((d, i) => { d.t.textContent = Math.floor(Math.random() * sides[i]) + 1; });
                setTimeout(tick, delays[di++]);
            } else {
                toast.classList.remove('rt-animating');
                /* v2.27.0: die face always shows the RAW rolled value;
                   the bonus modifier is rendered as a separate chip
                   beside the dice. Single-die rolls used to show the
                   total on the face — that conflated die + modifier. */
                const vals = _parseDieVals(r.breakdown);
                if (n === 1) {
                    const rawDie = vals[0] != null ? vals[0] : r.total;
                    dies[0].t.textContent = rawDie;
                    dies[0].svg.classList.add('rt-die-landed');
                } else {
                    /* Multi-die: show per-die results parsed from breakdown */
                    dies.forEach((d, i) => { d.t.textContent = vals[i] != null ? vals[i] : '?'; });
                    sumEl.textContent = '= ' + r.total;
                    sumEl.classList.add('rt-landed');
                }
                /* Compute the bonus modifier and reveal the chip if non-zero.
                   For advantage/disadvantage only the kept die counts toward
                   the total — every other die value sums in. */
                let dieSum;
                if (advDis && advDis.v1 != null && advDis.v2 != null) {
                    dieSum = (advDis.keptIdx === 0 ? advDis.v1 : advDis.v2);
                } else {
                    dieSum = vals.reduce((s, v) => s + (typeof v === 'number' ? v : 0), 0);
                }
                const bonus = (typeof r.total === 'number') ? (r.total - dieSum) : 0;
                if (bonus !== 0 && dieSum !== 0) {
                    bonusChip.textContent = (bonus > 0 ? '+' : '') + bonus;
                    bonusChip.style.visibility = 'visible';
                    bonusChip.classList.add('rt-landed');
                }
                /* v2.2.1: highlight kept vs discarded for advantage/disadvantage
                   pairs. Both dice show their rolled value (handled by the
                   multi-die branch above); the classes tint the kept die green
                   (adv) or red (dis) and dim the discarded one. */
                if (advDis && dies.length >= 2) {
                    // Force the values in case the expression parser had n=1
                    // (shorthand form) and _parseDieVals only returned one pair.
                    dies[0].t.textContent = advDis.v1;
                    dies[1].t.textContent = advDis.v2;
                    const keptKindClass = advDis.isAdv ? 'rt-die-kept-adv' : 'rt-die-kept-dis';
                    dies.forEach((d, i) => {
                        if (i === advDis.keptIdx) {
                            d.svg.classList.add('rt-die-kept', keptKindClass);
                        } else if (i <= 1) {
                            d.svg.classList.add('rt-die-discarded');
                        }
                    });
                }

                const bkd = document.createElement('div');
                bkd.className = 'rt-breakdown';
                bkd.textContent = r.breakdown;

                const hint = document.createElement('div');
                hint.className = 'rt-dismiss';
                hint.textContent = 'click to dismiss';

                toast.append(bkd, hint);
                toast._timer = setTimeout(() => _dismiss(toast), 10000);
            }
        }
        tick();
    }
    window.showRollToast = showRollToast;

    /* Legacy tabletop behaviour: the WS handler in tabletop.js dispatches a
       `vtt:ws-message` CustomEvent on every incoming message; we filter to
       the roll-bearing types and fire the popup with the visibility checks
       the tabletop has always done. Sheets don't have a WS connection so
       this listener is a no-op there — they call window.showRollToast
       directly off the response body.

       v2.7.3 — `weapon_attack` joins the listener. /attack pre-rolls both
       the d20-to-hit and the damage dice and broadcasts them in a single
       payload; we fire two toasts (attack + damage), mirroring the
       sheet-side direct-call path in `.atk-strike`. Without this, attacks
       triggered from the mini-sheet's Actions tab or any other surface
       that posts to /attack (monster strikes, future hotkeys) would land
       in the roll log without surfacing a toast — the user reported this
       hitting the GM's Warhammer click on Tavik's mini-sheet. */
    document.addEventListener('vtt:ws-message', (ev) => {
        const msg = ev.detail;
        if (!msg) return;
        const r = msg.data;
        if (!r) return;

        if (msg.type === 'roll') {
            const isGm = !!(window.ME && window.ME.isGm);
            const myId = _meId();
            if (r.visibility === 'gm_only' && !isGm) return;
            if (r.visibility === 'gm_and_roller' && !isGm && r.user_id !== myId) return;
            showRollToast(r);
            return;
        }

        if (msg.type === 'weapon_attack') {
            // Attack rolls are always public (the /attack endpoint doesn't
            // carry a visibility field) so no filter is needed. Skip the
            // d20 toast for save-DC attacks — those don't pre-roll an
            // attack die, jumping straight to the damage line, same as
            // the .atk-strike handler in sheet_dnd5e.html does.
            const nm = r.attack_name || 'Attack';
            const tgt = r.target_name || '';
            // v2.33.0: richer attack toast. Includes "→ TARGET",
            // "vs AC N", and a HIT/MISS/CRIT verdict — pulled from
            // the T.2 hit-determination payload. Falls back gracefully
            // when no target was set (attack without target = no
            // verdict, just the dice toast like pre-T.2).
            if (!r.is_save && r.attack_breakdown) {
                let verdict = '';
                if (r.is_crit) verdict = ' · 💥 CRIT';
                else if (r.hit === true) verdict = ' · ✅ HIT';
                else if (r.hit === false) verdict = ' · ❌ MISS';
                const acBit = (r.target_ac != null && r.hit != null)
                    ? ` vs AC ${r.target_ac}` : '';
                const tgtBit = tgt ? ` → ${tgt}` : '';
                showRollToast({
                    expression: '1d20',
                    total: r.attack_total,
                    breakdown: r.attack_breakdown,
                    note: `🎯 ${nm}${tgtBit}${acBit}${verdict}`,
                    user_id: r.caster_user_id,
                    user_name: r.caster_user_name,
                    char_name: r.caster_char_name,
                });
            }
            // v2.33.1: delay the damage toast until the attack-roll
            // dice finish animating. The spin schedule in
            // ``showRollToast`` adds up to ~1460 ms; 1600 ms gives a
            // small breath between the d20 landing and the damage
            // dice starting to roll. The delay is skipped on save-DC
            // attacks (no attack-roll toast to wait for).
            if (r.damage_breakdown) {
                const exprMatch = String(r.damage_breakdown).match(/(\d+d\d+(?:[+-]\d+)?)/);
                const typeBit = r.damage_type ? ` ${r.damage_type}` : '';
                const tgtBit = tgt ? ` → ${tgt}` : '';
                // Build a richer note describing what the damage roll
                // means in context. When auto_apply is on and the hit
                // landed we surface HP_BEFORE → HP_AFTER so the user
                // sees the consequence in one glance.
                let suffix = '';
                if (r.damage_applied > 0 && r.target_hp_after != null) {
                    suffix = ` · −${r.damage_applied} HP · ${r.target_hp_before ?? '?'} → ${r.target_hp_after} HP`;
                    if (r.target_resistance_applied) suffix += ' (resist)';
                    if (r.target_dead) suffix += ' · ☠ dead';
                    else if (r.target_dying) suffix += ' · 🩸 dying';
                } else if (r.hit === false) {
                    suffix = ' · would-be damage';
                }
                const dmgNote = `🎲 ${nm}${tgtBit}${typeBit ? ' — ' + typeBit.trim() : ''}${suffix}`;
                const fire = () => showRollToast({
                    expression: exprMatch ? exprMatch[1] : '1d6',
                    total: r.damage_total,
                    breakdown: r.damage_breakdown,
                    note: dmgNote,
                    user_id: r.caster_user_id,
                    user_name: r.caster_user_name,
                    char_name: r.caster_char_name,
                });
                if (!r.is_save && r.attack_breakdown) {
                    setTimeout(fire, 1600);
                } else {
                    fire();
                }
            }
            return;
        }

        if (msg.type === 'spell_cast') {
            // v2.27.1: dice toast for the healing roll when T.4 auto-
            // applied the heal to the targeted ally. Casts WITHOUT a
            // target still register a heal_claim and surface the
            // chat-card "Apply Healing" button — the heal_applied
            // broadcast (below) fires the toast for that path. This
            // branch only fires when the server pre-rolled + applied
            // the heal, so the broadcast carries auto_heal_breakdown.
            // v2.34.0 Phase T.4b: dice toasts for the auto-rolled
            // spell ATTACK roll + damage. Mirrors the weapon_attack
            // sequencing: attack d20 first, damage 1600 ms later. Pre-
            // T.4b broadcasts without ``auto_attack_*`` fields skip
            // this branch (auto_attack_hit is null).
            if (r.auto_attack_hit != null && r.auto_attack_breakdown) {
                const nm = r.spell_name || 'Spell';
                const tgt = r.auto_attack_target_name || r.target_name || '';
                let verdict = '';
                if (r.auto_attack_crit) verdict = ' · 💥 CRIT';
                else if (r.auto_attack_hit) verdict = ' · ✅ HIT';
                else verdict = ' · ❌ MISS';
                const acBit = r.auto_attack_target_ac
                    ? ` vs AC ${r.auto_attack_target_ac}` : '';
                const tgtBit = tgt ? ` → ${tgt}` : '';
                showRollToast({
                    expression: '1d20',
                    total: r.auto_attack_total,
                    breakdown: r.auto_attack_breakdown,
                    note: `🎯 ${nm}${tgtBit}${acBit}${verdict}`,
                    user_id: r.caster_user_id,
                    user_name: r.caster_user_name,
                    char_name: r.caster_char_name,
                });
                // Damage toast follows after the d20 settles.
                if (r.auto_attack_damage_breakdown) {
                    const dmgApplied = r.auto_attack_damage_applied || 0;
                    const dmgType = r.auto_attack_damage_type
                        ? ' — ' + r.auto_attack_damage_type : '';
                    let suffix = '';
                    if (dmgApplied > 0) {
                        suffix = ` · −${dmgApplied} HP`;
                    } else if (!r.auto_attack_hit) {
                        suffix = ' · no damage (miss)';
                    }
                    const exprMatch = String(r.auto_attack_damage_breakdown)
                        .match(/(\d+d\d+(?:[+-]\d+)?)/);
                    setTimeout(() => showRollToast({
                        expression: exprMatch ? exprMatch[1] : '1d6',
                        total: r.auto_attack_damage_rolled,
                        breakdown: r.auto_attack_damage_breakdown,
                        note: `🎲 ${nm}${tgtBit}${dmgType}${suffix}`,
                        user_id: r.caster_user_id,
                        user_name: r.caster_user_name,
                        char_name: r.caster_char_name,
                    }), 1600);
                }
            }
            // v2.35.0: save-for-half damage toast (Fireball, Burning
            // Hands, Sacred Flame, etc.). Server rolled damage when the
            // NPC saved/failed; auto_save_damage_breakdown carries the
            // breakdown. Fires after the save-roll toast (which lands
            // via the inline ``roll`` broadcast in T.3) so the user
            // reads save → damage in sequence.
            if (r.auto_save_damage_rolled && r.auto_save_damage_breakdown) {
                const exprMatch = String(r.auto_save_damage_breakdown).match(/(\d+d\d+(?:[+-]\d+)?)/);
                const tgt = r.auto_save_target_name || r.target_name || '';
                const typeBit = r.auto_save_damage_type
                    ? ' — ' + r.auto_save_damage_type : '';
                const applied = r.auto_save_damage_applied || 0;
                const passed = r.auto_save_passed;
                const suffix = applied > 0
                    ? ` · −${applied} HP${passed ? ' (half on save)' : ' (full)'}`
                    : '';
                showRollToast({
                    expression: exprMatch ? exprMatch[1] : '1d6',
                    total: r.auto_save_damage_rolled,
                    breakdown: r.auto_save_damage_breakdown,
                    note: `🎲 ${r.spell_name || 'Spell'}${tgt ? ' → ' + tgt : ''}${typeBit}${suffix}`,
                    user_id: r.caster_user_id,
                    user_name: r.caster_user_name,
                    char_name: r.caster_char_name,
                });
            }

            if (r.auto_heal_applied && r.auto_heal_breakdown) {
                const exprMatch = String(r.auto_heal_breakdown).match(/(\d+d\d+(?:[+-]\d+)?)/);
                const tgt = r.auto_heal_target_name || r.target_name || '';
                // v2.33.0: include HP delta + revived tag so the toast
                // explains exactly what happened. "✚ Healing Word →
                // Krieger · +4 HP · 50 → 54 HP" or, if a dying ally
                // came back, "… · 💚 revived".
                let suffix = ` · +${r.auto_heal_applied} HP`;
                if (r.auto_heal_hp_before != null && r.auto_heal_hp_after != null) {
                    suffix += ` · ${r.auto_heal_hp_before} → ${r.auto_heal_hp_after} HP`;
                }
                if (r.auto_heal_revived) suffix += ' · 💚 revived';
                showRollToast({
                    expression: exprMatch ? exprMatch[1] : (r.spell_healing || '1d4'),
                    total: r.auto_heal_rolled || r.auto_heal_applied,
                    breakdown: r.auto_heal_breakdown,
                    note: `✚ ${r.spell_name || 'Heal'}${tgt ? ' → ' + tgt : ''}${suffix}`,
                    user_id: r.caster_user_id,
                    user_name: r.caster_user_name,
                    char_name: r.caster_char_name,
                });
            }
            return;
        }

        if (msg.type === 'feature_used') {
            // v2.35.0: dice toast for feature_used broadcasts that
            // carry ``dice_*`` fields. Used by /use_second_wind
            // (1d10+lv heal) and /use_cutting_words (1dN BI die) so
            // the dice animation appears like other rolls instead of
            // being inlined in the feature-card description. Other
            // feature uses (Rage, Action Surge, Lay on Hands) carry
            // no dice and skip this branch.
            if (r.dice_expression && r.dice_breakdown) {
                showRollToast({
                    expression: r.dice_expression,
                    total: r.dice_total,
                    breakdown: r.dice_breakdown,
                    note: r.dice_note || r.feature_name || 'Feature',
                    user_name: r.character_name || '',
                });
            }
            return;
        }

        if (msg.type === 'heal_applied') {
            // v2.27.1: dice toast for the legacy heal-claim flow
            // (Apply Healing button). The /apply_healing endpoint
            // rolls server-side and broadcasts heal_applied with
            // {dice, rolled, breakdown, char_name}.
            if (r.breakdown && r.rolled != null) {
                const exprMatch = String(r.breakdown).match(/(\d+d\d+(?:[+-]\d+)?)/);
                showRollToast({
                    expression: exprMatch ? exprMatch[1] : (r.dice || '1d4'),
                    total: r.rolled,
                    breakdown: r.breakdown,
                    note: '✚ Heal → ' + (r.char_name || ''),
                    user_name: r.healer_name || '',
                });
            }
            return;
        }
    });
})();
