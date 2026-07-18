/* Character sheet form binder.
 *
 * The sheet templates use dotted names like "abilities.STR" or
 * "skills.Athletics.proficient". This script reads the form, builds the
 * nested object, and PUTs it to the campaign character endpoint.
 *
 * For systems with rollable_sheet=true (e.g., D&D 5e), this also wires up
 * the per-row 🎲 buttons: clicking one reads the form's current state
 * (so unsaved edits to ability scores or proficiencies are reflected),
 * computes the right roll expression, and POSTs it to /api/.../roll.
 */
(function () {
    const form = document.getElementById('sheet-form');
    if (!form) return;
    if (form.dataset.bound === '1') return;   // prevent double-binding when re-injected
    form.dataset.bound = '1';
    const readonly = form.dataset.readonly === '1';
    const charId = form.dataset.charId;
    const template = form.dataset.template;
    const status = document.getElementById('sheet-status');

    // Roll buttons work even on read-only sheets so non-owner GMs can roll
    // for an NPC, etc. They are wired up before the readonly early-return.
    if (template === 'dnd5e') wireDnd5eRollButtons(form);

    if (readonly) return;

    // ── Abilities edit/done toggle ──────────────────────────────────────────
    (function () {
        const abEditBtn  = document.getElementById('ab-edit-btn');
        const abDoneBtn  = document.getElementById('ab-done-btn');
        const abCardView = document.getElementById('ab-card-view');
        const abEditView = document.getElementById('ab-edit-view');
        if (!abEditBtn || !abDoneBtn || !abCardView || !abEditView) return;

        function updateCardFromInput(inp) {
            const ab    = inp.dataset.ab;
            const base  = parseInt(inp.value) || 10;
            const sd = abCardView.querySelector('.ab-score-disp[data-ab="' + ab + '"]');
            const md = abCardView.querySelector('.ab-mod-disp[data-ab="' + ab + '"]');
            // v2.214.0 — ability-score override Phase 2a: when an equipped
            // item sets this ability (data-override holds the set value), the
            // card shows the EFFECTIVE score = max(base, override) per RAW
            // max(base, set). Display-only — roll-building still reads the raw
            // form input, and /roll appends the override delta server-side.
            const override = parseInt(sd && sd.dataset.override, 10);
            const boosted  = !isNaN(override) && override > base;
            const score = boosted ? override : base;
            const mod   = Math.floor((score - 10) / 2);
            if (sd) {
                sd.textContent = score;
                sd.style.color = boosted ? 'var(--s-accent)' : 'var(--s-fg)';
            }
            if (md) md.textContent = (mod >= 0 ? '+' : '') + mod;
            const badge = abCardView.querySelector('.ab-boost-badge[data-ab="' + ab + '"]');
            if (badge) badge.style.display = boosted ? '' : 'none';
        }

        abEditBtn.addEventListener('click', function () {
            abCardView.style.display = 'none';
            abEditView.style.display = 'flex';
            abEditBtn.style.display  = 'none';
            abDoneBtn.style.display  = '';
        });

        abDoneBtn.addEventListener('click', function () {
            abEditView.querySelectorAll('input[data-ab]').forEach(updateCardFromInput);
            abEditView.style.display = 'none';
            abCardView.style.display = 'flex';
            abDoneBtn.style.display  = 'none';
            abEditBtn.style.display  = '';
            if (window._updateSaveCards)  window._updateSaveCards();
            if (window._updateSkillCards) window._updateSkillCards();
        });

        abEditView.querySelectorAll('input[data-ab]').forEach(function (inp) {
            inp.addEventListener('input', function () {
                updateCardFromInput(inp);
                if (window._updateSaveCards)  window._updateSaveCards();
                if (window._updateSkillCards) window._updateSkillCards();
            });
        });
    })();

    // ── Saving throws card view / edit toggle ──────────────────────────────
    (function () {
        const stCardView = document.getElementById('st-card-view');
        const stEditView = document.getElementById('st-edit-view');
        const stEditBtn  = document.getElementById('st-edit-btn');
        const stDoneBtn  = document.getElementById('st-done-btn');
        if (!stCardView) return;

        function updateSaveCards() {
            const prof = Number(form.querySelector('[name="proficiency_bonus"]')?.value || 2);
            stCardView.querySelectorAll('.st-roll-card[data-ab]').forEach(function (card) {
                const ab    = card.dataset.ab;
                const score = Number(form.querySelector('[name="abilities.' + ab + '"]')?.value || 10);
                const abMod = Math.floor((score - 10) / 2);
                const profEl  = form.querySelector('[name="saving_throws.' + ab + '"]');
                const isProf  = profEl ? profEl.checked : false;
                const total   = abMod + (isProf ? prof : 0);
                const modDisp = card.querySelector('.st-mod-disp');
                const dot     = card.querySelector('.st-prof-dot');
                if (modDisp) modDisp.textContent = (total >= 0 ? '+' : '') + total;
                if (dot)     dot.style.background = isProf ? '#6ab' : 'transparent';
            });
        }

        window._updateSaveCards = updateSaveCards;
        updateSaveCards();

        if (!stEditBtn || !stDoneBtn || !stEditView) return;

        stEditBtn.addEventListener('click', function () {
            stCardView.style.display = 'none';
            stEditView.style.display = 'flex';
            stEditBtn.style.display  = 'none';
            stDoneBtn.style.display  = '';
        });

        stDoneBtn.addEventListener('click', function () {
            updateSaveCards();
            stEditView.style.display = 'none';
            stCardView.style.display = 'flex';
            stDoneBtn.style.display  = 'none';
            stEditBtn.style.display  = '';
        });

        stEditView.querySelectorAll('input[data-ab]').forEach(function (inp) {
            inp.addEventListener('change', updateSaveCards);
        });
    })();

    // ── Skills card view / edit toggle ────────────────────────────────────
    (function () {
        const skCardView = document.getElementById('sk-card-view');
        const skEditView = document.getElementById('sk-edit-view');
        const skEditBtn  = document.getElementById('sk-edit-btn');
        const skDoneBtn  = document.getElementById('sk-done-btn');
        if (!skCardView) return;

        function updateSkillCards() {
            const prof = Number(form.querySelector('[name="proficiency_bonus"]')?.value || 2);
            skCardView.querySelectorAll('.sk-roll-card[data-skill]').forEach(function (card) {
                const skill = card.dataset.skill;
                const ab    = card.dataset.skillAbility;
                const score = Number(form.querySelector('[name="abilities.' + ab + '"]')?.value || 10);
                const abMod = Math.floor((score - 10) / 2);
                const profEl = form.querySelector('[name="skills.' + skill + '.proficient"]');
                const expEl  = form.querySelector('[name="skills.' + skill + '.expertise"]');
                const isProf = profEl ? profEl.checked : false;
                const isExp  = expEl  ? expEl.checked  : false;
                const bonus  = isExp ? prof * 2 : (isProf ? prof : 0);
                const total  = abMod + bonus;
                const modDisp = card.querySelector('.sk-mod-disp');
                const dot     = card.querySelector('.sk-prof-dot');
                if (modDisp) modDisp.textContent = (total >= 0 ? '+' : '') + total;
                if (dot) {
                    if (isExp)       { dot.style.background = '#e8a'; dot.style.borderColor = '#e8a'; }
                    else if (isProf) { dot.style.background = '#6ab'; dot.style.borderColor = '#3e5a70'; }
                    else             { dot.style.background = 'transparent'; dot.style.borderColor = '#3e5a70'; }
                }
            });
        }

        window._updateSkillCards = updateSkillCards;
        updateSkillCards();

        if (!skEditBtn || !skDoneBtn || !skEditView) return;

        skEditBtn.addEventListener('click', function () {
            skCardView.style.display = 'none';
            skEditView.style.display = 'block';
            skEditBtn.style.display  = 'none';
            skDoneBtn.style.display  = '';
        });

        skDoneBtn.addEventListener('click', function () {
            updateSkillCards();
            skEditView.style.display = 'none';
            skCardView.style.display = 'grid';
            skDoneBtn.style.display  = 'none';
            skEditBtn.style.display  = '';
        });

        skEditView.querySelectorAll('input[data-skill]').forEach(function (inp) {
            inp.addEventListener('change', updateSkillCards);
        });
    })();

    // ── Character header edit/done toggle ─────────────────────────────
    (function () {
        const editBtn   = document.getElementById('char-edit-btn');
        const doneBtn   = document.getElementById('char-done-btn');
        const editPanel = document.getElementById('char-edit-panel');
        if (!editBtn || !doneBtn || !editPanel) return;

        function updateHeaderDisplays() {
            const el = function (id) { return document.getElementById(id); };

            // Character name
            const nameInp = el('char-name-input');
            if (nameInp) {
                const nd = el('char-name-disp');
                if (nd) nd.textContent = nameInp.value || '—';
            }

            // Identity tags: class, subclass, race, level
            const classVal    = (form.querySelector('[name="class"]')    || {}).value || '';
            const subclassVal = (form.querySelector('[name="subclass"]') || {}).value || '';
            const raceVal     = (form.querySelector('[name="race"]')     || {}).value || '';
            const levelVal    = (form.querySelector('[name="level"]')    || {}).value || '1';

            const tc = el('tag-class');    if (tc) tc.textContent = classVal || '—';
            const ts = el('tag-subclass'); if (ts) ts.textContent = subclassVal;
            const ss = el('sep-sub');
            if (ss) ss.style.display = subclassVal ? '' : 'none';
            if (ts) ts.style.display = subclassVal ? '' : 'none';
            const tr = el('tag-race');     if (tr) tr.textContent = raceVal;
            const sr = el('sep-race');
            if (sr) sr.style.display = raceVal ? '' : 'none';
            if (tr) tr.style.display = raceVal ? '' : 'none';
            const tl = el('tag-level');    if (tl) tl.textContent = 'Level ' + levelVal;

            // HP max display
            const hpMaxInp  = el('hp-max-input');
            const hpMaxDisp = el('hp-max-disp');
            if (hpMaxInp && hpMaxDisp) hpMaxDisp.textContent = hpMaxInp.value || '0';

            // Speed chip
            const speedInp  = el('speed-edit-input');
            const speedDisp = el('speed-disp');
            if (speedInp && speedDisp) speedDisp.textContent = speedInp.value || '0';

            // Initiative chip
            const initInp  = el('init-edit-input');
            const initDisp = el('init-disp');
            if (initInp && initDisp) {
                const v = parseInt(initInp.value) || 0;
                initDisp.textContent = (v >= 0 ? '+' : '') + v;
            }

            // Proficiency chip + cascade to save/skill cards
            const profInp  = el('prof-edit-input');
            const profDisp = el('prof-disp');
            if (profInp && profDisp) {
                const v = parseInt(profInp.value) || 2;
                profDisp.textContent = (v >= 0 ? '+' : '') + v;
            }

            if (window._updateSaveCards)  window._updateSaveCards();
            if (window._updateSkillCards) window._updateSkillCards();
        }

        editBtn.addEventListener('click', function () {
            editPanel.style.display = 'block';
            editBtn.style.display   = 'none';
        });

        doneBtn.addEventListener('click', function () {
            updateHeaderDisplays();
            editPanel.style.display = 'none';
            editBtn.style.display   = '';
        });

        // Live preview while the panel is open
        editPanel.querySelectorAll('input, select').forEach(function (inp) {
            inp.addEventListener('input',  updateHeaderDisplays);
            inp.addEventListener('change', updateHeaderDisplays);
        });
    })();

    function setNested(obj, path, value) {
        const parts = path.split('.');
        let o = obj;
        for (let i = 0; i < parts.length - 1; i++) {
            if (!o[parts[i]] || typeof o[parts[i]] !== 'object') o[parts[i]] = {};
            o = o[parts[i]];
        }
        o[parts[parts.length - 1]] = value;
    }

    function buildSheet() {
        const sheet = {};
        let name = '';
        const inputs = form.querySelectorAll('input[name], textarea[name], select[name]');
        inputs.forEach((el) => {
            const n = el.name;
            if (n === 'name') {
                name = el.value;
                return;
            }
            // Multiclass roster — JSON array stored in a hidden textarea.
            // We deserialise it into ``sheet.classes`` and DO NOT keep the raw
            // ``classes_json`` key in the saved sheet.
            if (n === 'classes_json' && template === 'dnd5e') {
                const raw = (el.value || '').trim();
                let arr = [];
                if (raw) { try { arr = JSON.parse(raw); } catch { arr = []; } }
                if (!Array.isArray(arr)) arr = [];
                sheet.classes = arr;
                return;
            }
            // Class-resources list — same pattern as classes_json.
            if (n === 'resources_json' && template === 'dnd5e') {
                const raw = (el.value || '').trim();
                let arr = [];
                if (raw) { try { arr = JSON.parse(raw); } catch { arr = []; } }
                if (!Array.isArray(arr)) arr = [];
                sheet.resources = arr;
                return;
            }
            let v;
            if (el.type === 'checkbox') v = el.checked;
            else if (el.type === 'number') v = el.value === '' ? 0 : Number(el.value);
            else v = el.value;

            if (n === 'inventory') {
                const raw = String(v).trim();
                if (raw.startsWith('[')) {
                    try { v = JSON.parse(raw); } catch { v = []; }
                } else {
                    // Legacy newline format — preserve as plain-name items
                    v = raw.split('\n').map(s => s.trim()).filter(Boolean);
                }
            } else if (n === 'attacks' && template === 'dnd5e') {
                const raw = String(v).trim();
                if (raw.startsWith('[')) {
                    try { v = JSON.parse(raw); } catch { v = []; }
                } else {
                    // Legacy pipe-delimited format: "Name | bonus | damage"
                    v = raw.split('\n').map(s => s.trim()).filter(Boolean).map(line => {
                        const [name, bonus, damage] = line.split('|').map(s => (s||'').trim());
                        return { name: name || '', attack_bonus: bonus || '', damage: damage || '' };
                    });
                }
            } else if (n === 'spells' && template === 'dnd5e') {
                const raw = String(v).trim();
                if (raw.startsWith('[')) {
                    try { v = JSON.parse(raw); } catch { v = []; }
                } else {
                    // Legacy pipe-delimited format
                    v = raw.split('\n').map(s => s.trim()).filter(Boolean).map(line => {
                        const [name, level, description] = line.split('|').map(s => (s||'').trim());
                        return { name: name || '', level: level || '', description: description || '' };
                    });
                }
            } else if (n === 'conditions' && template === 'dnd5e') {
                const raw = String(v).trim();
                try { v = raw ? JSON.parse(raw) : []; } catch { v = []; }
            } else if ((n === 'damage_resistances' || n === 'damage_immunities'
                     || n === 'damage_vulnerabilities' || n === 'condition_immunities')
                     && template === 'dnd5e') {
                // Same shape as ``conditions``: hidden input carries a
                // JSON-encoded array kept in sync by the Defenses chip
                // toggle. Empty or unparseable values fall back to [].
                const raw = String(v).trim();
                try { v = raw ? JSON.parse(raw) : []; } catch { v = []; }
                if (!Array.isArray(v)) v = [];
            }
            setNested(sheet, n, v);
        });

        // Generic template: collect dynamic stat-rows
        if (template === 'generic') {
            const stats = {};
            form.querySelectorAll('.stat-row').forEach(row => {
                const k = row.querySelector('.stat-k').value.trim();
                const v = row.querySelector('.stat-v').value;
                if (k) stats[k] = v;
            });
            sheet.stats = stats;
        }

        return { name, sheet };
    }

    form.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const payload = buildSheet();
        payload.template = template;
        if (status) status.textContent = 'Saving…';
        const saveUrl = form.dataset.saveUrl || `/api/campaign/${CAMPAIGN_ID}/character/${charId}`;
        const saveMethod = form.dataset.saveMethod || 'POST';
        const resp = await fetch(saveUrl, {
            method: saveMethod,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (resp.ok) {
            if (status) status.textContent = 'Saved.';
            setTimeout(() => { if (status) status.textContent = ''; }, 1500);
        } else {
            if (status) status.textContent = 'Save failed.';
        }
    });

    window.addStatRow = function () {
        const wrap = document.getElementById('stat-rows');
        if (!wrap) return;
        const div = document.createElement('div');
        div.className = 'stat-row';
        div.innerHTML = '<input class="stat-k" placeholder="key"><input class="stat-v" placeholder="value">';
        wrap.appendChild(div);
    };

    // ----------------- D&D 5e roll buttons -----------------

    function abilityModifier(score) {
        return Math.floor((Number(score || 10) - 10) / 2);
    }

    function readField(form, name) {
        const el = form.querySelector(`[name="${CSS.escape(name)}"]`);
        if (!el) return null;
        if (el.type === 'checkbox') return el.checked;
        return el.value;
    }

    function formatBonus(n) {
        if (n === 0) return '';
        return n > 0 ? `+${n}` : `${n}`;
    }

    /* v2.15.2: Jack of All Trades — Bard Lv 2 feature. Adds floor(PB/2)
     * to ability checks the character is NOT proficient in (raw STR/DEX/
     * etc. check OR a skill where ``skills.X.proficient`` is false). Does
     * NOT apply to saving throws (different category RAW) or to proficient
     * skills (PB is already there). Mirror of the Jinja ``has_jack`` block
     * in sheet_dnd5e.html so live-edits to class/level via the form pick
     * up the change immediately. ``window._mcRoster()`` reads the
     * multi-class roster from #classes-data; falls back to the
     * single-class form fields for sheets without multi-class wiring.
     */
    function _hasJackOfAllTrades(form) {
        const roster = (typeof window._mcRoster === 'function') ? window._mcRoster() : null;
        if (Array.isArray(roster) && roster.length) {
            for (const c of roster) {
                if ((c.class || '').trim().toLowerCase() === 'bard'
                    && (parseInt(c.level, 10) || 0) >= 2) return true;
            }
            return false;
        }
        const singleClass = (readField(form, 'class') || '').trim().toLowerCase();
        const singleLevel = parseInt(readField(form, 'level'), 10) || 0;
        return singleClass === 'bard' && singleLevel >= 2;
    }

    /**
     * v2.49.237 — Champion Fighter Lv 7+ Remarkable Athlete. RAW
     * (PHB p.72): "Starting at 7th level, you can add half your
     * proficiency bonus (round up) to any Strength, Dexterity, or
     * Constitution check you make that doesn't already use your
     * proficiency bonus."
     *
     * Differs from Jack of All Trades in three ways:
     *   - STR / DEX / CON only (Jack is any ability).
     *   - Round up (Jack rounds down).
     *   - Lv 7+ Champion Fighter (Jack is Lv 2+ Bard).
     *
     * Returns true when the live class/level + subclass tags match.
     * Multiclass support: walks ``_mcRoster`` for a Fighter entry with
     * level≥7 + subclass containing "champion"; falls back to single-
     * class form fields when no roster is present. Mirrors the multi-
     * class shape of ``_hasJackOfAllTrades``.
     */
    function _hasRemarkableAthlete(form) {
        const roster = (typeof window._mcRoster === 'function') ? window._mcRoster() : null;
        if (Array.isArray(roster) && roster.length) {
            for (const c of roster) {
                if ((c.class || '').trim().toLowerCase() !== 'fighter') continue;
                if ((parseInt(c.level, 10) || 0) < 7) continue;
                if ((c.subclass || '').trim().toLowerCase().includes('champion')) return true;
            }
            return false;
        }
        const singleClass = (readField(form, 'class') || '').trim().toLowerCase();
        const singleLevel = parseInt(readField(form, 'level'), 10) || 0;
        const singleSub = (readField(form, 'subclass') || '').trim().toLowerCase();
        return singleClass === 'fighter' && singleLevel >= 7 && singleSub.includes('champion');
    }

    function wireDnd5eRollButtons(form) {
        form.querySelectorAll('.roll-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                let expr = '';
                let note = '';
                const prof = Number(readField(form, 'proficiency_bonus') || 2);
                const jack = _hasJackOfAllTrades(form) ? Math.floor(prof / 2) : 0;
                // v2.49.237: Champion Fighter Lv 7+ Remarkable Athlete.
                // STR / DEX / CON ability checks (and non-proficient
                // skill checks on those abilities) get +ceil(PB/2). Note:
                // this STACKS with Jack of All Trades on a Bard/Champion
                // multiclass — RAW unclear, but additive is the kinder
                // reading and matches similar partial-PB stackers.
                const remarkable = _hasRemarkableAthlete(form) ? Math.ceil(prof / 2) : 0;
                const _isRmkAthAbility = (ab) => remarkable > 0
                    && ['STR', 'DEX', 'CON'].includes((ab || '').toUpperCase());

                // v2.99.30 — stat_key field for /roll provenance.
                // Hooks like the v2.99.28 Rage STR-check advantage
                // read this field server-side to identify the roll
                // type. Schema: "<ability>_check" for raw ability,
                // "<ability>_save" for saves, "<SkillName>" for
                // skills (matches the /roll_request convention).
                // `statAbility` is the underlying ability slug (e.g.
                // "STR" for Athletics) — used by hooks that fire on
                // ability-based skill checks (Rage covers all STR
                // checks including STR-based skills).
                let statKey = '';
                let statAbility = '';
                if (btn.dataset.rollAbility) {
                    const ab = btn.dataset.rollAbility;
                    const mod = abilityModifier(readField(form, `abilities.${ab}`));
                    // Jack applies to raw ability checks too (RAW: "any
                    // ability check that doesn't already include PB").
                    const rmk = _isRmkAthAbility(ab) ? remarkable : 0;
                    const total = mod + jack + rmk;
                    expr = `1d20${formatBonus(total)}`;
                    const tags = [];
                    if (jack > 0) tags.push('Jack +' + jack);
                    if (rmk > 0)  tags.push('Rmk Ath +' + rmk);
                    note = `${ab} check${tags.length ? ' (' + tags.join(', ') + ')' : ''}`;
                    statKey = `${ab.toLowerCase()}_check`;
                    statAbility = (ab || '').toUpperCase();
                } else if (btn.dataset.rollSave) {
                    const ab = btn.dataset.rollSave;
                    const mod = abilityModifier(readField(form, `abilities.${ab}`));
                    const isProf = !!readField(form, `saving_throws.${ab}`);
                    const total = mod + (isProf ? prof : 0);
                    expr = `1d20${formatBonus(total)}`;
                    note = `${ab} save${isProf ? ' (prof)' : ''}`;
                    statKey = `${ab.toLowerCase()}_save`;
                    statAbility = (ab || '').toUpperCase();
                } else if (btn.dataset.rollSkill) {
                    const skill = btn.dataset.rollSkill;
                    const ab = btn.dataset.skillAbility;
                    const mod = abilityModifier(readField(form, `abilities.${ab}`));
                    const isProf = !!readField(form, `skills.${skill}.proficient`);
                    const isExp  = !!readField(form, `skills.${skill}.expertise`);
                    let bonus = 0;
                    let jackApplied = 0;
                    let rmkApplied = 0;
                    if (isExp) bonus = prof * 2;
                    else if (isProf) bonus = prof;
                    else if (_isRmkAthAbility(ab)) {
                        // Remarkable Athlete beats Jack on STR/DEX/CON
                        // because it's ceiling (larger when PB is odd).
                        bonus = remarkable;
                        rmkApplied = remarkable;
                    }
                    else if (jack > 0) { bonus = jack; jackApplied = jack; }
                    expr = `1d20${formatBonus(mod + bonus)}`;
                    const skillTags = [];
                    if (isExp) skillTags.push('expertise');
                    else if (isProf) skillTags.push('prof');
                    else if (rmkApplied > 0) skillTags.push('Rmk Ath +' + rmkApplied);
                    else if (jackApplied > 0) skillTags.push('Jack +' + jackApplied);
                    note = `${skill}${skillTags.length ? ' (' + skillTags.join(', ') + ')' : ''}`;
                    statKey = skill;
                    statAbility = (ab || '').toUpperCase();
                }

                if (!expr) return;
                if (typeof CAMPAIGN_ID === 'undefined') return;
                const visEl = document.getElementById('roll-vis');
                const visibility = visEl ? visEl.value : 'public';
                // v2.2.6: include character_id so the server applies *this*
                // character's roll_state, not the user's first-character
                // fallback (which mis-resolves when the user has multiple
                // characters in the campaign — e.g. a test character with
                // a stale roll_state still set).
                const charId = (form && form.dataset && form.dataset.charId)
                    ? parseInt(form.dataset.charId, 10)
                    : (typeof CHAR_ID !== 'undefined' ? CHAR_ID : null);
                const body = { expression: expr, visibility, note };
                // v2.99.30 — stat_key for /roll provenance. Drives
                // server-side hooks like Rage STR-check advantage.
                if (statKey) body.stat_key = statKey;
                if (statAbility) body.stat_ability = statAbility;
                // v2.99.7 — monster sheets are not backed by a Character
                // row; sending the template id as character_id would
                // make the server's roll_state fallback land on an
                // unrelated PC owned by the GM. Pass actor_name +
                // skip_roll_state to opt into the v2.49.211/212
                // "no character attribution" path so the roll log
                // attributes to the monster name instead.
                if (window.IS_MONSTER_SHEET) {
                    body.skip_roll_state = true;
                    if (window.MONSTER_NAME) body.actor_name = window.MONSTER_NAME;
                } else if (charId) {
                    body.character_id = charId;
                }
                const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/roll`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!resp.ok) {
                    const txt = await resp.text();
                    alert('Roll failed: ' + txt);
                    return;
                }
                // Fire the shared rich roll-toast (animated dice + breakdown) so
                // the player sees their save/check/skill result right on the
                // sheet. The sheet no longer keeps a WS connection so the
                // broadcast path doesn't fire here — direct invocation only.
                try {
                    const j = await resp.json();
                    if (typeof window.showRollToast === 'function') {
                        window.showRollToast({
                            expression: expr,
                            total: j.total,
                            breakdown: j.breakdown,
                            note: note,
                            visibility: visibility,
                            user_id: (window.ME && window.ME.id) || null,
                            user_name: (window.ME && window.ME.displayName) || '',
                            char_name: '',
                        });
                    }
                } catch (e) { /* roll succeeded server-side; popup is non-fatal */ }
            });
        });
    }
})();

// ── Open5e select dropdowns (class, subclass, race) ──
;(function () {
    // Multiclass mode: if the multiclass JSON textarea is present, the
    // class+subclass dropdowns are now rendered per-row by the multiclass
    // module further down. We still want this IIFE to run for race init,
    // so we conditionally null out the class/subclass references.
    const _MC = !!document.getElementById('classes-data');
    const classSelect = _MC ? null : document.getElementById('class-select');
    const subSelect   = _MC ? null : document.getElementById('subclass-select');
    const raceSelect  = document.getElementById('race-select');
    if (!classSelect && !subSelect && !raceSelect) return;

    async function fetchList(url) {
        try {
            const r = await fetch(url);
            if (r.ok) return (await r.json()).results || [];
        } catch {}
        return [];
    }

    const _LSC_TTL = 86400000; // 24 hours
    async function fetchListCached(url, cacheKey) {
        try {
            const raw = localStorage.getItem(cacheKey);
            if (raw) {
                const { ts, data } = JSON.parse(raw);
                if (Date.now() - ts < _LSC_TTL && data.length) return data;
            }
        } catch {}
        const items = await fetchList(url);
        if (items.length) {
            try { localStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), data: items })); } catch {}
        }
        return items;
    }

    async function fetchDetailText(endpoint, slug) {
        if (!slug) return '';
        try {
            const r = await fetch(endpoint + '?slug=' + encodeURIComponent(slug));
            if (r.ok) return (await r.json()).text || '';
        } catch {}
        return '';
    }

    // Returns null (no badge) or {label, title, css} describing how a
    // content-source string should render. ``kind`` is the noun used in the
    // tooltip ("subclasses" / "races") so the user knows where to go to
    // manage that flavor of content. Three buckets:
    //   - "local-custom"  → orange "Custom" — campaign homebrew (DB).
    //   - "local-srd"     → green  "SRD"    — shipped FS files.
    //   - "open5e_mirror" / "open5e_live" → blue "Open5e" — external API.
    // Anything else returns null so unrecognised sources stay quiet.
    function _sourceBadgeSpec(source, kind) {
        if (source === 'local-custom') {
            return {
                label: 'Custom',
                title: 'Campaign-authored homebrew. Manage via campaign settings → Custom ' + (kind || 'content') + '.',
                css: 'color:#d4a84a;background:#3a2f15;border:1px solid #6e5828;',
            };
        }
        if (source === 'local-srd') {
            return {
                label: 'SRD',
                title: 'Shipped locally as part of the D&D 5e SRD baseline — no Open5e call needed.',
                css: 'color:#7fb069;background:#1f2d1a;border:1px solid #3d5e30;',
            };
        }
        if (source === 'open5e_mirror' || source === 'open5e_live') {
            return {
                label: 'Open5e',
                title: 'Loaded from the Open5e ' + (source === 'open5e_mirror' ? 'mirror' : 'live API') + '.',
                css: 'color:#7aa7d4;background:#1a2433;border:1px solid #2f4a6e;',
            };
        }
        return null;
    }

    function _appendSourceBadge(headerEl, source, kind) {
        const spec = _sourceBadgeSpec(source, kind);
        if (!spec) return;
        const badge = document.createElement('span');
        badge.textContent = spec.label;
        badge.title = spec.title;
        badge.style.cssText = 'font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border-radius:3px;padding:1px 6px;' + spec.css;
        headerEl.appendChild(badge);
        // Exposed globally so the multi-class IIFE further down the file can
        // reuse it without redeclaring (pre-existing _renderSubclassBlock call
        // at the heading-badge insertion was throwing ReferenceError because
        // closure-scoped names don't cross IIFE boundaries).
    }
    window._appendSourceBadge = _appendSourceBadge;

    function populateSelect(sel, items, currentName) {
        sel.innerHTML = '';
        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = '— none —';
        sel.appendChild(blank);
        let matched = false;
        items.forEach(function (item) {
            const opt = document.createElement('option');
            opt.value = item.name;
            // Append the source as a suffix so the user can see at a glance
            // which entry is local SRD / Custom / Open5e — and pick the one
            // they want when multiple sources expose the same name. Search
            // endpoints set: "Custom" for DB homebrew, "SRD" for shipped
            // FS files, and an Open5e document title (e.g. "5e Core Rules")
            // otherwise. Empty/missing source renders as the bare name.
            const src = (item.source || '').trim();
            opt.textContent = src ? (item.name + ' · ' + src) : item.name;
            opt.dataset.slug = item.slug || '';
            sel.appendChild(opt);
            if (item.name === currentName) { opt.selected = true; matched = true; }
        });
        if (!matched && currentName) {
            const opt = document.createElement('option');
            opt.value = currentName;
            opt.textContent = currentName;
            opt.selected = true;
            sel.insertBefore(opt, blank.nextSibling);
        }
    }

    async function loadSubclasses(className) {
        if (!subSelect) return;
        subSelect.innerHTML = '<option value="">— loading… —</option>';
        if (!className) {
            subSelect.innerHTML = '<option value="">— select class first —</option>';
            return;
        }
        const slug = className.trim().toLowerCase().replace(/\s+/g, '-');
        // Campaign-scoped homebrew is merged into the list server-side; the
        // cache key embeds the campaign id so one campaign's homebrew doesn't
        // bleed into another via localStorage.
        const cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
        const url = '/api/open5e/subclasses?limit=100&class_slug=' + encodeURIComponent(slug)
            + (cid ? '&campaign_id=' + cid : '');
        const items = await fetchListCached(url, 'simplevtt_subclasses_' + slug + '_c' + (cid || 'none'));
        const current = subSelect.dataset.current || '';
        populateSelect(subSelect, items, current);
        subSelect.dataset.current = '';
    }

    function updateFeatureDisplay(taName, displayId, emptyId) {
        const ta = document.querySelector('textarea[name="' + taName + '"]');
        const div = document.getElementById(displayId);
        if (!div) return;
        const text = ta ? ta.value.trim() : '';
        div.textContent = text;
        div.style.display = text ? '' : 'none';
        const emp = emptyId && document.getElementById(emptyId);
        if (emp) emp.style.display = text ? 'none' : '';
    }

    function _cleanMd(text) {
        if (!text) return '';
        return text
            .replace(/\r\n/g, '\n').replace(/\r/g, '\n')
            .replace(/\*{3}([^*]+)\*{3}/g, '$1')
            .replace(/\*{2}([^*]+)\*{2}/g, '$1')
            .replace(/_{2}([^_]+)_{2}/g, '$1')
            .replace(/\*([^*\n]+)\*/g, '$1')
            .replace(/_([^_\n]+)_/g, '$1')
            .replace(/^#{1,6}\s+/gm, '')
            .replace(/^[*\-]\s+/gm, '• ')
            .replace(/\n{3,}/g, '\n\n')
            .trim();
    }

    function _extractLevelHint(text) {
        const m = text.match(/\b(\d+)(?:st|nd|rd|th)[- ]level/i)
                || text.match(/(?:at|reach)[^.\n]{0,30}?(\d+)(?:st|nd|rd|th)/i);
        return m ? parseInt(m[1], 10) : null;
    }

    // Client-side fallback: parse a flat text blob into {intro, features}.
    // Exposed on window so the spellcasting framework can re-use it to scan
    // class_features blobs for cantrip-granting features.
    window._parseFeaturesFromText = _parseFeaturesFromText;
    function _parseFeaturesFromText(text) {
        if (!text) return { intro: '', features: [] };
        text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

        function buildFeatures(parts) {
            const out = [];
            for (let i = 1; i < parts.length - 1; i += 2) {
                const name = parts[i].trim().replace(/\.$/, '');
                const desc = (parts[i + 1] || '').trim();
                out.push({ name, desc, level: _extractLevelHint(desc) });
            }
            return out;
        }

        // Strategy 0: split on markdown headings (Open5e uses ##### = 5 hashes)
        const headingRe = /\n#{2,6}\s+([^\n]+)\n/g;
        const hparts = ('\n' + text).split(headingRe);
        if (hparts.length >= 3) {
            return { intro: hparts[0].trim(), features: buildFeatures(hparts) };
        }

        // Strategy 1: split on **Name** or ***Name*** bold headers
        const boldRe = /\n\*{2,3}([^*\n]+?)\*{2,3}\.?\s*\n/g;
        const bparts = ('\n' + text).split(boldRe);
        if (bparts.length >= 3) {
            return { intro: bparts[0].trim(), features: buildFeatures(bparts) };
        }

        // Strategy 2: paragraph split — short title-like first line = feature name
        const paras = text.split(/\n{2,}/).map(p => p.trim()).filter(Boolean);
        if (paras.length >= 3) {
            const features = [], introParts = [];
            for (const para of paras) {
                const nl = para.indexOf('\n');
                const first = nl === -1 ? para : para.slice(0, nl).trim();
                const rest  = nl === -1 ? '' : para.slice(nl + 1).trim();
                if (rest && first.length <= 60 && !/\.$/.test(first)
                        && /^[A-Z][A-Za-z ,'\-]+$/.test(first)) {
                    features.push({ name: first, desc: rest, level: _extractLevelHint(rest) });
                } else {
                    if (!features.length) introParts.push(para);
                }
            }
            if (features.length) return { intro: introParts.join('\n\n'), features };
        }

        return { intro: text, features: [] };
    }

    function renderSubclassFeatures(data) {
        const container = document.getElementById('sf-display');
        const emptyEl   = document.getElementById('sf-empty');
        if (!container) return;
        container.innerHTML = '';

        if (!data) {
            container.style.display = 'none';
            if (emptyEl) emptyEl.style.display = '';
            return;
        }

        const charLevel = parseInt(
            (document.querySelector('input[name="level"]') || {}).value, 10
        ) || 20;

        // Client-side fallback: if backend returned no features, try to parse flavor
        let flavor   = data.flavor || '';
        let features = (data.features || []).slice();
        if (!features.length && flavor) {
            const parsed = _parseFeaturesFromText(flavor);
            if (parsed.features.length) {
                flavor   = parsed.intro;
                features = parsed.features;
            }
        }

        const allFeatures = features;
        const visible = allFeatures.filter(f => f.level == null || f.level <= charLevel);
        const locked  = allFeatures.filter(f => f.level != null && f.level > charLevel);

        const hasContent = flavor || visible.length || locked.length;
        if (!hasContent) {
            container.style.display = 'none';
            if (emptyEl) emptyEl.style.display = '';
            return;
        }
        container.style.display = '';
        if (emptyEl) emptyEl.style.display = 'none';

        // Subclass name + source badge. ``data.source`` is set by the
        // resolver/route: "local-custom" (campaign homebrew DB),
        // "local-srd" (shipped FS file), or "open5e_mirror"/"open5e_live"
        // for content fetched from Open5e. _appendSourceBadge no-ops for
        // unrecognised values.
        if (data.name) {
            const h = document.createElement('div');
            h.style.cssText = 'font-weight:700;font-size:14px;margin-bottom:4px;color:var(--fg,#e0e0e0);display:flex;align-items:center;gap:8px;';
            const nameSpan = document.createElement('span');
            nameSpan.textContent = data.name;
            h.appendChild(nameSpan);
            _appendSourceBadge(h, data.source, 'subclasses');
            container.appendChild(h);
        }
        const cleanedFlavor = _cleanMd(flavor);
        if (cleanedFlavor) {
            const f = document.createElement('div');
            f.style.cssText = 'font-size:12px;color:#8a9;font-style:italic;margin-bottom:12px;line-height:1.55;border-left:2px solid #3a6a50;padding-left:8px;';
            f.textContent = cleanedFlavor;
            container.appendChild(f);
        }

        function makeCard(feat, dimmed) {
            const card = document.createElement('div');
            card.style.cssText = 'margin-bottom:5px;border-radius:5px;overflow:hidden;border:1px solid ' + (dimmed ? '#252530' : '#2e3250') + ';opacity:' + (dimmed ? '0.45' : '1') + ';';

            const hdr = document.createElement('div');
            hdr.style.cssText = 'display:flex;align-items:center;gap:8px;padding:7px 10px;background:' + (dimmed ? '#1c1e2a' : '#252c45') + ';cursor:pointer;user-select:none;';

            const arrow = document.createElement('span');
            arrow.style.cssText = 'font-size:9px;color:#667;flex-shrink:0;transition:transform .15s;transform:rotate(-90deg);';
            arrow.textContent = '▼';
            hdr.appendChild(arrow);

            const nameSpan = document.createElement('span');
            nameSpan.style.cssText = 'font-size:12px;font-weight:600;color:' + (dimmed ? '#667' : '#c8cce8') + ';flex:1;';
            nameSpan.textContent = feat.name || 'Feature';
            hdr.appendChild(nameSpan);

            if (feat.level != null) {
                const badge = document.createElement('span');
                badge.style.cssText = 'font-size:10px;padding:1px 7px;border-radius:10px;white-space:nowrap;flex-shrink:0;' +
                    (dimmed ? 'background:#1e1e28;color:#445;' : 'background:#1c3040;color:#6ab;');
                badge.textContent = 'Lvl ' + feat.level;
                hdr.appendChild(badge);
            }

            card.appendChild(hdr);

            if (feat.desc) {
                const body = document.createElement('div');
                body.style.cssText = 'display:none;padding:10px 12px;font-size:12px;line-height:1.65;color:#b0b4cc;background:#191c2b;';
                // Render cleaned paragraphs
                _cleanMd(feat.desc).split('\n\n').forEach(function (para) {
                    para = para.trim();
                    if (!para) return;
                    const p = document.createElement('p');
                    p.style.cssText = 'margin:0 0 8px;';
                    // Handle bullet lines within a paragraph
                    if (para.includes('\n')) {
                        para.split('\n').forEach(function (line, i) {
                            if (i > 0) p.appendChild(document.createElement('br'));
                            p.appendChild(document.createTextNode(line));
                        });
                    } else {
                        p.textContent = para;
                    }
                    body.appendChild(p);
                });
                card.appendChild(body);

                hdr.addEventListener('click', function () {
                    const open = body.style.display !== 'none';
                    body.style.display = open ? 'none' : '';
                    arrow.style.transform = open ? 'rotate(-90deg)' : 'rotate(0deg)';
                });
            }

            return card;
        }

        if (visible.length || locked.length) {
            visible.forEach(f => container.appendChild(makeCard(f, false)));
            if (locked.length) {
                const lockedWrap = document.createElement('div');
                lockedWrap.style.cssText = 'margin-top:6px;';
                const lockedLabel = document.createElement('div');
                lockedLabel.style.cssText = 'font-size:10px;color:#445;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;padding-left:2px;';
                lockedLabel.textContent = 'Future features';
                lockedWrap.appendChild(lockedLabel);
                locked.forEach(f => lockedWrap.appendChild(makeCard(f, true)));
                container.appendChild(lockedWrap);
            }
        } else if (cleanedFlavor) {
            // Last resort: couldn't parse features — render the blob as readable paragraphs
            const wrap = document.createElement('div');
            wrap.style.cssText = 'background:#191c2b;border-radius:4px;padding:10px 12px;border:1px solid #2a2d3a;';
            cleanedFlavor.split('\n\n').forEach(function (para) {
                para = para.trim();
                if (!para) return;
                const p = document.createElement('p');
                p.style.cssText = 'margin:0 0 8px;font-size:12px;line-height:1.65;color:#b0b4cc;';
                p.textContent = para;
                wrap.appendChild(p);
            });
            // Remove the italic flavor block we already added and replace with this
            const flavEl = container.querySelector('div[style*="italic"]');
            if (flavEl) { container.removeChild(flavEl); container.appendChild(wrap); }
            else { container.appendChild(wrap); }
        }
    }

    // Mirrors renderSubclassFeatures() but for racial traits.
    // Uses data.traits (not data.features) and skips level filtering.
    function renderRaceTraits(data) {
        const container = document.getElementById('rt-display');
        const emptyEl   = document.getElementById('rt-empty');
        if (!container) return;
        container.innerHTML = '';

        if (!data) {
            container.style.display = 'none';
            if (emptyEl) emptyEl.style.display = '';
            return;
        }

        // Client-side fallback: if backend returned no traits, try parsing flavor/text
        let flavor = data.flavor || '';
        let traits  = (data.traits  || []).slice();
        if (!traits.length && flavor) {
            const parsed = _parseFeaturesFromText(flavor);
            if (parsed.features.length) {
                flavor = parsed.intro;
                traits  = parsed.features;
            }
        }

        const hasContent = flavor || traits.length;
        if (!hasContent) {
            container.style.display = 'none';
            if (emptyEl) emptyEl.style.display = '';
            return;
        }
        container.style.display = '';
        if (emptyEl) emptyEl.style.display = 'none';

        // Race name heading + source badge — same conventions as the
        // subclass renderer above. ``data.source`` is "local-custom",
        // "local-srd", or one of the open5e_* labels.
        if (data.name) {
            const h = document.createElement('div');
            h.style.cssText = 'font-weight:700;font-size:14px;margin-bottom:4px;color:var(--fg);display:flex;align-items:center;gap:8px;';
            const nameSpan = document.createElement('span');
            nameSpan.textContent = data.name;
            h.appendChild(nameSpan);
            _appendSourceBadge(h, data.source, 'races');
            container.appendChild(h);
        }

        // Stat summary flavor block
        const cleanedFlavor = _cleanMd(flavor);
        if (cleanedFlavor) {
            const f = document.createElement('div');
            f.style.cssText = 'font-size:12px;color:var(--fg-mute);font-style:italic;margin-bottom:12px;line-height:1.55;border-left:2px solid var(--accent-border,var(--accent));padding-left:8px;';
            f.textContent = cleanedFlavor;
            container.appendChild(f);
        }

        function makeTraitCard(trait) {
            const card = document.createElement('div');
            card.style.cssText = 'margin-bottom:5px;border-radius:5px;overflow:hidden;border:1px solid var(--border);';

            const hdr = document.createElement('div');
            hdr.style.cssText = 'display:flex;align-items:center;gap:8px;padding:7px 10px;background:var(--bg-2);cursor:pointer;user-select:none;';

            const arrow = document.createElement('span');
            arrow.style.cssText = 'font-size:9px;color:var(--fg-mute);flex-shrink:0;transition:transform .15s;transform:rotate(-90deg);';
            arrow.textContent = '▼';
            hdr.appendChild(arrow);

            const nameSpan = document.createElement('span');
            nameSpan.style.cssText = 'font-size:12px;font-weight:600;color:var(--fg);flex:1;';
            nameSpan.textContent = trait.name || 'Trait';
            hdr.appendChild(nameSpan);

            card.appendChild(hdr);

            if (trait.desc) {
                const body = document.createElement('div');
                body.style.cssText = 'display:none;padding:10px 12px;font-size:12px;line-height:1.65;color:var(--fg-mute);background:var(--bg);border-top:1px solid var(--border);';
                _cleanMd(trait.desc).split('\n\n').forEach(function (para) {
                    para = para.trim();
                    if (!para) return;
                    const p = document.createElement('p');
                    p.style.cssText = 'margin:0 0 8px;';
                    if (para.includes('\n')) {
                        para.split('\n').forEach(function (line, i) {
                            if (i > 0) p.appendChild(document.createElement('br'));
                            p.appendChild(document.createTextNode(line));
                        });
                    } else {
                        p.textContent = para;
                    }
                    body.appendChild(p);
                });
                card.appendChild(body);
                hdr.addEventListener('click', function () {
                    const open = body.style.display !== 'none';
                    body.style.display = open ? 'none' : '';
                    arrow.style.transform = open ? 'rotate(-90deg)' : 'rotate(0deg)';
                });
            }
            return card;
        }

        if (traits.length) {
            traits.forEach(t => container.appendChild(makeTraitCard(t)));
        } else if (cleanedFlavor) {
            // No traits parsed — render the blob as paragraphs
            const wrap = document.createElement('div');
            wrap.style.cssText = 'background:var(--bg);border-radius:4px;padding:10px 12px;border:1px solid var(--border);';
            cleanedFlavor.split('\n\n').forEach(function (para) {
                para = para.trim();
                if (!para) return;
                const p = document.createElement('p');
                p.style.cssText = 'margin:0 0 8px;font-size:12px;line-height:1.65;color:var(--fg-mute);';
                p.textContent = para;
                wrap.appendChild(p);
            });
            const flavEl = container.querySelector('div[style*="italic"]');
            if (flavEl) { container.removeChild(flavEl); container.appendChild(wrap); }
            else { container.appendChild(wrap); }
        }
    }

    function setSyncMsg(elemId, msg, color) {
        const el = document.getElementById(elemId);
        if (!el) return;
        el.textContent = msg;
        el.style.color = color || '';
        if (msg) { clearTimeout(el._t); el._t = setTimeout(() => { el.textContent = ''; }, 4000); }
    }

    async function applyDetail(textareaName, endpoint, slug, displayId, emptyId) {
        if (!slug) return;
        const ta = document.querySelector('textarea[name="' + textareaName + '"]');
        if (!ta || ta.value.trim()) return;
        const text = await fetchDetailText(endpoint, slug);
        if (text) { ta.value = text; updateFeatureDisplay(textareaName, displayId, emptyId); }
    }

    function selectedSlug(sel) {
        const opt = sel && sel.options[sel.selectedIndex];
        return opt ? (opt.dataset.slug || '') : '';
    }

    function lockSelect(sel) {
        if (!sel || !sel.value) return;
        const wrap = sel.parentElement;
        const existing = wrap.querySelector('.sel-lock-row');
        if (existing) existing.remove();
        const row = document.createElement('span');
        row.className = 'sel-lock-row';
        row.style.cssText = 'display:inline-flex;align-items:center;gap:6px;';
        const label = document.createElement('span');
        label.className = 'sel-lock-label';
        label.textContent = sel.value;
        label.style.cssText = 'font-size:13px;color:var(--fg,#e0e0e0);';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = 'Change';
        btn.style.cssText = 'font-size:10px;padding:2px 7px;opacity:0.7;';
        btn.addEventListener('click', () => unlockSelect(sel));
        row.appendChild(label);
        row.appendChild(btn);
        wrap.insertBefore(row, sel);
        sel.style.display = 'none';
    }

    function unlockSelect(sel) {
        const wrap = sel.parentElement;
        const row = wrap.querySelector('.sel-lock-row');
        if (row) row.remove();
        sel.style.display = '';
        sel.focus();
    }

    async function init() {
        const _cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
        const _classesUrl = '/api/open5e/classes?limit=30' + (_cid ? '&campaign_id=' + _cid : '');
        const _classesKey = 'simplevtt_classes_list_c' + (_cid || 'none');
        const _racesUrl   = '/api/open5e/races?limit=30'   + (_cid ? '&campaign_id=' + _cid : '');
        const _racesKey   = 'simplevtt_races_list_c'   + (_cid || 'none');
        const [classes, races] = await Promise.all([
            classSelect ? fetchListCached(_classesUrl, _classesKey) : Promise.resolve([]),
            raceSelect  ? fetchListCached(_racesUrl,   _racesKey)   : Promise.resolve([]),
        ]);
        if (classSelect) {
            populateSelect(classSelect, classes, classSelect.dataset.current || '');
            if (classSelect.value) {
                await loadSubclasses(classSelect.value);
                lockSelect(classSelect);
                // Auto-fill proficiency fields if hit_die is missing (e.g. older characters)
                const sheetForm = document.getElementById('sheet-form');
                const hitDieEl = sheetForm && sheetForm.querySelector('[name="class_hit_die"]');
                if (hitDieEl && !hitDieEl.value.trim()) {
                    await applyClassDetail(selectedSlug(classSelect));
                }
            }
        }
        if (raceSelect) {
            populateSelect(raceSelect, races, raceSelect.dataset.current || '');
            if (raceSelect.value) {
                lockSelect(raceSelect);
                // Use DB-cached traits if available, otherwise fetch from Open5e
                if (window._savedRaceData && (window._savedRaceData.traits || []).length) {
                    renderRaceTraits(window._savedRaceData);
                } else if (raceSelect.value) {
                    const rSlug = selectedSlug(raceSelect) || raceSelect.value.trim().toLowerCase().replace(/\s+/g, '-');
                    if (rSlug) {
                        const _cid2 = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
                        const _rUrl = '/api/open5e/race-detail?slug=' + encodeURIComponent(rSlug)
                            + (_cid2 ? '&campaign_id=' + _cid2 : '');
                        fetch(_rUrl)
                            .then(r => r.ok ? r.json() : null)
                            .then(d => { if (d) { renderRaceTraits(d); _saveRaceCache(d); } })
                            .catch(() => {});
                    }
                }
            }
        }
        if (subSelect && subSelect.value) {
            lockSelect(subSelect);
            // Use DB-cached features if available, otherwise fetch from Open5e
            if (window._savedSubclassData && window._savedSubclassData.features) {
                renderSubclassFeatures(window._savedSubclassData);
            } else {
                const subSlug = selectedSlug(subSelect);
                if (subSlug) {
                    const classSlug = classSelect
                        ? (selectedSlug(classSelect) || classSelect.value.trim().toLowerCase().replace(/\s+/g, '-'))
                        : '';
                    const cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
                    const url = '/api/open5e/subclass-detail?slug=' + encodeURIComponent(subSlug)
                        + (classSlug ? '&class_slug=' + encodeURIComponent(classSlug) : '')
                        + (cid ? '&campaign_id=' + cid : '');
                    fetch(url).then(r => r.ok ? r.json() : null).then(d => {
                        if (d) { renderSubclassFeatures(d); _saveSubclassCache(d); }
                    }).catch(() => {});
                }
            }
        }
        if (typeof window._syncSpellSlots === 'function') window._syncSpellSlots();
    }

    function setSyncStatus(msg, color) {
        const el = document.getElementById('sync-class-status');
        if (!el) return;
        el.textContent = msg;
        el.style.color = color || '';
        if (msg) {
            clearTimeout(el._t);
            el._t = setTimeout(() => { el.textContent = ''; }, 4000);
        }
    }

    async function applyClassDetail(slug, force) {
        if (!slug) {
            setSyncStatus('No class selected', '#e07070');
            return;
        }
        const sheetForm = document.getElementById('sheet-form');
        if (!sheetForm) return;
        const btn = document.getElementById('sync-class-btn');
        if (btn) { btn.disabled = true; btn.textContent = '↻ Syncing…'; }
        setSyncStatus('');
        try {
            const cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
            const r = await fetch('/api/open5e/class-detail?slug=' + encodeURIComponent(slug)
                + (cid ? '&campaign_id=' + cid : ''));
            if (!r.ok) {
                setSyncStatus('Lookup failed (' + r.status + ')', '#e07070');
                return;
            }
            const d = await r.json();
            const map = {
                'class_hit_die': d.hit_die,
                'class_armor': d.armor,
                'class_weapons': d.weapons,
                'class_tools': d.tools,
                'class_saving_throws': d.saving_throws,
                'class_skills': d.skills,
                'class_spellcasting': d.spellcasting,
                'class_equipment': d.equipment,
                'class_features': d.features || d.text || '',
            };
            let filled = 0;
            for (const [name, val] of Object.entries(map)) {
                const el = sheetForm.querySelector(`[name="${CSS.escape(name)}"]`);
                if (el && (force || !el.value.trim())) { el.value = val || ''; filled++; }
            }
            updateFeatureDisplay('class_features', 'cf-display', 'cf-empty');
            setSyncStatus(filled > 0 ? '✓ Synced' : '✓ Already up to date', '#6cb');
        } catch (err) {
            setSyncStatus('Error: ' + err.message, '#e07070');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '↻ Sync'; }
        }
    }

    const syncBtn = document.getElementById('sync-class-btn');
    if (syncBtn) {
        syncBtn.addEventListener('click', async function () {
            const slug = selectedSlug(classSelect) || (classSelect && classSelect.value.trim().toLowerCase().replace(/\s+/g, '-'));
            await applyClassDetail(slug, true);
        });
    }

    if (classSelect) {
        classSelect.addEventListener('change', async function () {
            const sheetForm = document.getElementById('sheet-form');
            if (subSelect) {
                subSelect.dataset.current = '';
                unlockSelect(subSelect);
            }
            const sfTa = document.querySelector('textarea[name="subclass_features"]');
            if (sfTa) sfTa.value = '';
            renderSubclassFeatures(null);
            _saveSubclassCache(null);
            await loadSubclasses(classSelect.value);
            // Clear all class proficiency fields before re-populating
            ['class_hit_die','class_armor','class_weapons','class_tools',
             'class_saving_throws','class_skills','class_spellcasting',
             'class_equipment','class_features'].forEach(name => {
                const el = sheetForm && sheetForm.querySelector(`[name="${CSS.escape(name)}"]`);
                if (el) el.value = '';
            });
            await applyClassDetail(selectedSlug(classSelect));
            if (classSelect.value) lockSelect(classSelect);
        });
    }

    if (subSelect) {
        subSelect.addEventListener('change', async function () {
            const ta = document.querySelector('textarea[name="subclass_features"]');
            if (ta) ta.value = '';
            renderSubclassFeatures(null);
            const subSlug = selectedSlug(subSelect);
            if (!subSlug) return;
            const classSlug = classSelect
                ? (selectedSlug(classSelect) || classSelect.value.trim().toLowerCase().replace(/\s+/g, '-'))
                : '';
            const cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
            const url = '/api/open5e/subclass-detail?slug=' + encodeURIComponent(subSlug)
                + (classSlug ? '&class_slug=' + encodeURIComponent(classSlug) : '')
                + (cid ? '&campaign_id=' + cid : '');
            try {
                const r = await fetch(url);
                if (r.ok) {
                    const d = await r.json();
                    if (ta && d.text) ta.value = d.text;
                    renderSubclassFeatures(d);
                    _saveSubclassCache(d);
                }
            } catch {}
            if (subSelect.value) lockSelect(subSelect);
        });
    }

    if (raceSelect) {
        raceSelect.addEventListener('change', async function () {
            const rtTa = document.querySelector('textarea[name="race_traits"]');
            if (rtTa) rtTa.value = '';
            renderRaceTraits(null);
            _saveRaceCache(null);
            const slug = selectedSlug(raceSelect);
            if (slug) {
                try {
                    const _cidR = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
                    const r = await fetch('/api/open5e/race-detail?slug=' + encodeURIComponent(slug)
                        + (_cidR ? '&campaign_id=' + _cidR : ''));
                    if (r.ok) {
                        const d = await r.json();
                        if (rtTa && d.text) rtTa.value = d.text;
                        renderRaceTraits(d);
                        _saveRaceCache(d);
                    }
                } catch {}
            }
            if (raceSelect.value) lockSelect(raceSelect);
        });
    }

    const syncSubBtn = document.getElementById('sync-subclass-btn');
    if (syncSubBtn) {
        syncSubBtn.addEventListener('click', async function () {
            const subSlug = selectedSlug(subSelect);
            if (!subSlug) { setSyncMsg('sync-subclass-status', 'No subclass selected', '#e07070'); return; }
            syncSubBtn.disabled = true; syncSubBtn.textContent = '↻ Syncing…';
            const classSlug = classSelect
                ? (selectedSlug(classSelect) || classSelect.value.trim().toLowerCase().replace(/\s+/g, '-'))
                : '';
            const cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
            const url = '/api/open5e/subclass-detail?slug=' + encodeURIComponent(subSlug)
                + (classSlug ? '&class_slug=' + encodeURIComponent(classSlug) : '')
                + (cid ? '&campaign_id=' + cid : '');
            try {
                const r = await fetch(url);
                if (!r.ok) { setSyncMsg('sync-subclass-status', 'Lookup failed (' + r.status + ')', '#e07070'); return; }
                const d = await r.json();
                const ta = document.querySelector('textarea[name="subclass_features"]');
                if (ta && d.text) ta.value = d.text;
                renderSubclassFeatures(d);
                _saveSubclassCache(d);
                setSyncMsg('sync-subclass-status', d.features && d.features.length ? '✓ Synced' : 'No features found', d.features && d.features.length ? '#6cb' : '#e07070');
            } catch (err) {
                setSyncMsg('sync-subclass-status', 'Error: ' + err.message, '#e07070');
            } finally {
                syncSubBtn.disabled = false; syncSubBtn.textContent = '↻ Sync';
            }
        });
    }

    // Build a list of slug candidates from the race select. Legacy characters
    // store display strings like "Halfling (Lightfoot)" rather than the
    // canonical `lightfoot-halfling` slug used by the shipped file. We try the
    // option's explicit data-slug first (set when the option came from the
    // file-based picker), then the naive slugification of the visible text,
    // then a transposed "X (Y)" -> "<y> <x>" form so the parens variant maps
    // back to the canonical slug instead of 502-ing through Open5e.
    function _raceSlugCandidates(sel) {
        const out = [];
        const explicit = selectedSlug(sel);
        if (explicit) out.push(explicit);
        const txt = (sel && sel.value || '').trim();
        if (!txt) return out;
        const naive = txt.toLowerCase()
            .replace(/[^a-z0-9 -]/g, ' ')
            .replace(/\s+/g, '-')
            .replace(/-+/g, '-')
            .replace(/^-|-$/g, '');
        if (naive && out.indexOf(naive) === -1) out.push(naive);
        const m = txt.match(/^(.+?)\s*\((.+?)\)\s*$/);
        if (m) {
            const transposed = (m[2] + ' ' + m[1]).toLowerCase()
                .replace(/[^a-z0-9 -]/g, ' ')
                .replace(/\s+/g, '-')
                .replace(/-+/g, '-')
                .replace(/^-|-$/g, '');
            if (transposed && out.indexOf(transposed) === -1) out.push(transposed);
        }
        return out;
    }

    const syncRaceBtn = document.getElementById('sync-race-btn');
    if (syncRaceBtn) {
        syncRaceBtn.addEventListener('click', async function () {
            const candidates = _raceSlugCandidates(raceSelect);
            if (!candidates.length) { setSyncMsg('sync-race-status', 'No race selected', '#e07070'); return; }
            syncRaceBtn.disabled = true; syncRaceBtn.textContent = '↻ Syncing…';
            const _cidS = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
            let lastError = null;
            try {
                for (const slug of candidates) {
                    try {
                        const r = await fetch('/api/open5e/race-detail?slug=' + encodeURIComponent(slug)
                            + (_cidS ? '&campaign_id=' + _cidS : ''));
                        if (!r.ok) { lastError = new Error('HTTP ' + r.status); continue; }
                        const d = await r.json();
                        const ta = document.querySelector('textarea[name="race_traits"]');
                        if (ta && d.text) ta.value = d.text;
                        renderRaceTraits(d);
                        _saveRaceCache(d);
                        setSyncMsg('sync-race-status', d.traits && d.traits.length ? '✓ Synced' : 'No traits found', d.traits && d.traits.length ? '#6cb' : '#e07070');
                        return;
                    } catch (err) { lastError = err; }
                }
                throw lastError || new Error('Race not found');
            } catch (err) {
                setSyncMsg('sync-race-status', 'Error: ' + err.message, '#e07070');
            } finally {
                syncRaceBtn.disabled = false; syncRaceBtn.textContent = '↻ Sync';
            }
        });
    }

    // Persist structured subclass data to the character's sheet in the DB.
    // Stores each feature individually (subclass_features list) plus the name
    // and flavour as separate top-level keys so they can be queried without
    // re-parsing the whole blob.  Also keeps the legacy subclass_features_data
    // blob so old code / existing records stay compatible.
    // Fire-and-forget — UI doesn't depend on the response.
    function _saveSubclassCache(data) {
        if (typeof CHAR_ID === 'undefined' || !data) return;
        const url = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID)
            ? '/api/campaign/' + CAMPAIGN_ID + '/character/' + CHAR_ID + '/sheet-fields'
            : '/api/character/' + CHAR_ID + '/sheet-fields';
        fetch(url, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                subclass_features_data: data,                  // legacy blob
                subclass_name:     data.name     || '',        // e.g. "Way of the Open Hand"
                subclass_flavor:   data.flavor   || '',        // intro paragraph
                subclass_features: data.features || [],        // [{name,desc,level}, …]
            }),
        }).catch(() => {});
    }

    // Persist structured race data to the character's sheet in the DB.
    function _saveRaceCache(data) {
        if (typeof CHAR_ID === 'undefined' || !data) return;
        const url = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID)
            ? '/api/campaign/' + CAMPAIGN_ID + '/character/' + CHAR_ID + '/sheet-fields'
            : '/api/character/' + CHAR_ID + '/sheet-fields';
        fetch(url, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                race_parsed_data: data,
                race_flavor:      data.flavor  || '',
                race_trait_items: data.traits  || [],
            }),
        }).catch(() => {});
    }

    init();
})();

// ── Condition chips ──
;(function () {
    const form     = document.getElementById('sheet-form');
    const chipsDiv = document.getElementById('condition-chips');
    const condInput = document.getElementById('conditions-input');
    const descBox  = document.getElementById('cond-desc-popover');
    if (!chipsDiv || !condInput) return;

    const readonly = form && form.dataset.readonly === '1';

    // Initialise active set from stored JSON
    let active = new Set();
    try { active = new Set(JSON.parse(condInput.value || '[]')); } catch {}

    // Lazy per-condition description cache: slug → desc string.
    // v2.1026.0 (SRD Reference Phase 3): source the popover text from the
    // offline SRD reference tier (GET /api/reference/entry) — shipped SRD
    // content, never the network — instead of the old /api/open5e/conditions
    // proxy which could fall back to api.open5e.com. Fetch only the clicked
    // condition and cache it.
    const descCache = {};
    async function fetchDesc(slug) {
        if (slug in descCache) return descCache[slug];
        let desc = '';
        try {
            const r = await fetch('/api/reference/entry?type=conditions&slug='
                                  + encodeURIComponent(slug));
            if (r.ok) desc = (await r.json()).desc || '';
        } catch {}
        descCache[slug] = desc;
        return desc;
    }

    function syncInput() {
        condInput.value = JSON.stringify([...active]);
    }

    function styleChip(btn, isActive) {
        btn.style.background   = isActive ? '#4a1520' : '#1c2235';
        btn.style.borderColor  = isActive ? '#c05070' : '#2e3550';
        btn.style.color        = isActive ? '#f0a0b8' : '#7a8ab0';
        btn.style.fontWeight   = isActive ? '700'     : '500';
    }

    // Apply initial styles from sheet data
    chipsDiv.querySelectorAll('.cond-chip').forEach(btn => {
        styleChip(btn, active.has(btn.dataset.slug));
    });

    let openSlug = null;

    chipsDiv.querySelectorAll('.cond-chip').forEach(btn => {
        btn.addEventListener('click', async () => {
            const slug = btn.dataset.slug;

            // Toggle active state (edit mode only)
            if (!readonly) {
                if (active.has(slug)) active.delete(slug);
                else active.add(slug);
                styleChip(btn, active.has(slug));
                syncInput();
            }

            // Toggle description popover
            if (descBox) {
                if (openSlug === slug && descBox.style.display !== 'none') {
                    descBox.style.display = 'none';
                    openSlug = null;
                } else {
                    const desc = await fetchDesc(slug);
                    descBox.innerHTML = desc
                        ? `<strong style="color:#dde2f0;">${btn.textContent.trim()}</strong><br><br>${desc}`
                        : '<em style="color:#7a8ab0;">No description available.</em>';
                    descBox.style.display = 'block';
                    openSlug = slug;
                }
            }
        });
    });
})();

// ── Multiclass editor + per-class subclass features + class-prof table ─────
//
//  Source of truth: <textarea name="classes_json" id="classes-data">.
//  Hidden mirrors:  #class-select / #subclass-select / #level-input reflect
//                   the *primary* (highest-level) class so older code that
//                   still reads [name="class"]/[name="level"]/[name="subclass"]
//                   keeps working.
//
;(function () {
    const dataEl = document.getElementById('classes-data');
    if (!dataEl) return;
    const sheetForm = document.getElementById('sheet-form');
    const isReadonly = !!sheetForm && sheetForm.dataset.readonly === '1';

    const listEl       = document.getElementById('mc-class-list');
    const totalEl      = document.getElementById('mc-total-lv');
    const addBtn       = document.getElementById('mc-add-class-btn');
    const sfContainer  = document.getElementById('sf-multiclass-list');
    const sfEmptyMsg   = document.getElementById('sf-empty');
    const profTable    = document.getElementById('class-prof-table');
    const slotsParking = document.getElementById('spell-slots-ui');

    const MAX_TOTAL_LEVEL = 20;

    function _slug(name) {
        return (name || '').toString().trim().toLowerCase().replace(/\s+/g, '-');
    }

    function _esc(s) {
        return String(s ?? '')
            .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    // ── Shared helper: render content-record actions into a slot (1.9.0) ──
    // Fetches /api/content/<type>/<slug> and, on success, mounts the record's
    // ``actions: list[Action]`` array into ``slot`` via window.renderActionButtons.
    // The damage handler posts to /api/campaign/{id}/roll so the roll shows up
    // in the log with a note naming the action source. Other handlers (save /
    // heal / attack / toggle) are wired through to reasonable defaults: damage
    // and attack roll to the dice endpoint, healing handled like damage with a
    // self-target stub, toggle / save surface a toast so the player knows the
    // hook fired even though no automation is wired yet. ``actionLabelPrefix``
    // is prepended to the roll-log note so a generic "Sneak Attack" reads as
    // "Rogue · Sneak Attack" once it's coming from the class panel.
    async function _populateContentActions(slot, contentType, slug, opts) {
        if (!slot || !slug || typeof window.renderActionButtons !== 'function') return;
        opts = opts || {};
        const characterLevel = opts.characterLevel || 1;
        const labelPrefix = opts.actionLabelPrefix || '';
        const cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
        const url = '/api/content/' + encodeURIComponent(contentType) + '/' + encodeURIComponent(slug)
            + (cid ? '?campaign_id=' + cid : '');
        let data;
        try {
            const r = await fetch(url, { credentials: 'same-origin' });
            if (!r.ok) return;
            data = await r.json();
        } catch (e) {
            return;
        }
        const actions = (data && data.record && data.record.actions) || [];
        if (!actions.length) return;

        function _noteFor(action) {
            const parts = [];
            if (labelPrefix) parts.push(labelPrefix);
            if (action && action.name) parts.push(action.name);
            return parts.join(' · ');
        }
        const toast = (typeof window.showToast === 'function') ? window.showToast : ((m) => console.log(m));
        async function _postRoll(expression, action) {
            if (!cid || !expression) {
                toast('No active campaign for roll.', 'error');
                return;
            }
            const note = _noteFor(action);
            try {
                const r = await fetch('/api/campaign/' + cid + '/roll', {
                    method: 'POST', credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        expression: expression,
                        visibility: 'public',
                        note: note,
                    }),
                });
                if (!r.ok) {
                    toast('Roll failed: HTTP ' + r.status, 'error');
                    return;
                }
                const j = await r.json();
                // Pop the rich tabletop roll-toast (animated dice + breakdown).
                // The page-wide module lives in /static/roll_toast.js.
                if (typeof window.showRollToast === 'function') {
                    window.showRollToast({
                        expression: expression,
                        total: j.total,
                        breakdown: j.breakdown,
                        note: note,
                        visibility: 'public',
                        user_id: (window.ME && window.ME.id) || null,
                        user_name: (window.ME && window.ME.displayName) || '',
                        char_name: '',
                    });
                } else {
                    // Fallback to the plain text toast if roll_toast.js isn't loaded.
                    const head = '🎲 ' + (note ? note + ' — ' : '') + expression;
                    const body = j.breakdown ? ' = ' + j.breakdown : '';
                    const tail = (j.total != null) ? ' → ' + j.total : '';
                    toast(head + body + tail, 'success');
                }
            } catch (e) {
                toast('Roll error: ' + (e && e.message || e), 'error');
            }
        }

        const frag = window.renderActionButtons(actions, {
            characterLevel: characterLevel,
            handlers: {
                damage: (action, damageExpr) => _postRoll(damageExpr, action),
                attack: (action) => _postRoll('1d20', action),  // bare attack roll; modifier added at roll time
                heal:   (action) => _postRoll(action.healing, action),
                save:   (action) => toast('Save prompt for ' + (action.name || 'action') + ' — wire targeting from the roll-request panel.'),
                toggle: (action) => toast((action.active_toggle ? 'Toggle ' : 'Use ') + (action.name || 'action') + ' — resource tracking coming soon.'),
            },
        });
        slot.appendChild(frag);
    }
    window._populateContentActions = _populateContentActions;

    function _readRoster() {
        try {
            const arr = JSON.parse(dataEl.value || '[]');
            return Array.isArray(arr) ? arr : [];
        } catch { return []; }
    }

    function _writeRoster(arr) {
        dataEl.value = JSON.stringify(arr || []);
        _refreshMirrors();
        _refreshTotalLevel();
        // Tabletop / mini-sheet listeners can react to roster changes
        document.dispatchEvent(new CustomEvent('vtt:mc-changed', { detail: arr }));
    }

    function _primary(arr) {
        if (!arr || !arr.length) return null;
        return arr.slice().sort((a, b) => (b.level || 0) - (a.level || 0))[0];
    }

    function _refreshTotalLevel() {
        const arr = _readRoster();
        const total = arr.reduce((acc, c) => acc + (parseInt(c.level, 10) || 0), 0);
        if (totalEl) {
            totalEl.textContent = total;
            totalEl.style.color = total > MAX_TOTAL_LEVEL ? 'var(--s-danger,#e07070)' : 'var(--s-fg)';
        }
    }

    function _refreshMirrors() {
        const arr = _readRoster();
        const p = _primary(arr) || {};
        const setHidden = (id, val) => {
            const el = document.getElementById(id);
            if (el) {
                el.value = val == null ? '' : String(val);
                if ('dataset' in el && el.dataset && id !== 'level-input') el.dataset.current = el.value;
            }
        };
        setHidden('class-select', p.class || '');
        setHidden('subclass-select', p.subclass || '');
        const total = arr.reduce((a, c) => a + (parseInt(c.level, 10) || 0), 0);
        setHidden('level-input', Math.max(1, Math.min(MAX_TOTAL_LEVEL, total || 1)));

        // Mirror primary class proficiency fields into the hidden inputs that
        // legacy code (item browser, etc.) reads.
        ['class_hit_die','class_armor','class_weapons','class_tools',
         'class_saving_throws','class_skills','class_spellcasting',
         'class_equipment','class_features'].forEach(k => {
            const el = sheetForm && sheetForm.querySelector(`input[type="hidden"][name="${k}"]`);
            if (el) el.value = (p && p[k]) ? p[k] : '';
        });
    }

    // ── Open5e list cache (shared across rows) ──
    const _LSC_TTL = 86400000; // 24h
    async function _fetchListCached(url, key) {
        try {
            const raw = localStorage.getItem(key);
            if (raw) {
                const { ts, data } = JSON.parse(raw);
                if (Date.now() - ts < _LSC_TTL && data && data.length) return data;
            }
        } catch {}
        try {
            const r = await fetch(url);
            if (r.ok) {
                const items = (await r.json()).results || [];
                if (items.length) {
                    try { localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data: items })); } catch {}
                }
                return items;
            }
        } catch {}
        return [];
    }

    let _classesPromise = null;
    function _classList() {
        if (!_classesPromise) {
            const cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
            _classesPromise = _fetchListCached(
                '/api/open5e/classes?limit=30' + (cid ? '&campaign_id=' + cid : ''),
                'simplevtt_classes_list_c' + (cid || 'none'),
            );
        }
        return _classesPromise;
    }
    async function _subclassList(classSlug) {
        if (!classSlug) return [];
        const cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
        return _fetchListCached(
            '/api/open5e/subclasses?limit=100&class_slug=' + encodeURIComponent(classSlug)
                + (cid ? '&campaign_id=' + cid : ''),
            'simplevtt_subclasses_' + classSlug + '_c' + (cid || 'none'),
        );
    }

    function _populateSelect(sel, items, currentName) {
        sel.innerHTML = '';
        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = '— none —';
        sel.appendChild(blank);
        let matched = false;
        items.forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.name;
            opt.textContent = item.name;
            opt.dataset.slug = item.slug || '';
            sel.appendChild(opt);
            if (item.name === currentName) { opt.selected = true; matched = true; }
        });
        if (!matched && currentName) {
            const opt = document.createElement('option');
            opt.value = currentName;
            opt.textContent = currentName;
            opt.dataset.slug = _slug(currentName);
            opt.selected = true;
            sel.insertBefore(opt, blank.nextSibling);
        }
    }

    // ── Class-detail (proficiencies) auto-fill for one row ──
    async function _fillClassDetail(entry, force) {
        const slug = _slug(entry.class || '');
        if (!slug) return entry;
        try {
            const cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
            const r = await fetch('/api/open5e/class-detail?slug=' + encodeURIComponent(slug)
                + (cid ? '&campaign_id=' + cid : ''));
            if (!r.ok) return entry;
            const d = await r.json();
            const map = {
                'class_hit_die': d.hit_die,
                'class_armor': d.armor,
                'class_weapons': d.weapons,
                'class_tools': d.tools,
                'class_saving_throws': d.saving_throws,
                'class_skills': d.skills,
                'class_spellcasting': d.spellcasting,
                'class_equipment': d.equipment,
                'class_features': d.features || d.text || '',
            };
            for (const [k, v] of Object.entries(map)) {
                if (force || !(entry[k] && String(entry[k]).trim())) entry[k] = v || '';
            }
        } catch {}
        return entry;
    }

    // ── Subclass-detail auto-fill for one row ──
    async function _fillSubclassDetail(entry) {
        const cslug = _slug(entry.class || '');
        const sslug = entry._subclass_slug || _slug(entry.subclass || '');
        if (!sslug) {
            entry.subclass_features = [];
            entry.subclass_name = entry.subclass || '';
            entry.subclass_flavor = '';
            return entry;
        }
        const cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
        const url = '/api/open5e/subclass-detail?slug=' + encodeURIComponent(sslug)
            + (cslug ? '&class_slug=' + encodeURIComponent(cslug) : '')
            + (cid ? '&campaign_id=' + cid : '');
        try {
            const r = await fetch(url);
            if (!r.ok) return entry;
            const d = await r.json();
            entry.subclass_features = d.features || [];
            entry.subclass_name = d.name || entry.subclass || '';
            entry.subclass_flavor = d.flavor || '';
            entry.subclass_features_data = d;
        } catch {}
        return entry;
    }

    // Persist a single class entry's subclass cache to the DB (fire-and-forget)
    function _saveSubclassCacheRow(entry) {
        if (typeof CHAR_ID === 'undefined') return;
        const url = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID)
            ? '/api/campaign/' + CAMPAIGN_ID + '/character/' + CHAR_ID + '/sheet-fields'
            : '/api/character/' + CHAR_ID + '/sheet-fields';
        fetch(url, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                class_slug: _slug(entry.class || ''),
                subclass_features_data: entry.subclass_features_data || null,
                subclass_name:     entry.subclass_name     || '',
                subclass_flavor:   entry.subclass_flavor   || '',
                subclass_features: entry.subclass_features || [],
            }),
        }).catch(() => {});
    }

    // ── Subclass features renderer (per class block) ──
    // Mirrors the legacy renderSubclassFeatures() in this file, but draws
    // into a target container and prefixes with "<Class> - <Subclass>".
    function _cleanMd(text) {
        if (!text) return '';
        return String(text)
            .replace(/\r\n/g, '\n').replace(/\r/g, '\n')
            .replace(/\*{3}([^*]+)\*{3}/g, '$1')
            .replace(/\*{2}([^*]+)\*{2}/g, '$1')
            .replace(/_{2}([^_]+)_{2}/g, '$1')
            .replace(/\*([^*\n]+)\*/g, '$1')
            .replace(/_([^_\n]+)_/g, '$1')
            .replace(/^#{1,6}\s+/gm, '')
            .replace(/^[*\-]\s+/gm, '• ')
            .replace(/\n{3,}/g, '\n\n').trim();
    }

    // Strip markdown-style tables (lines with two or more pipes, plus the
    // `---|---` separator rows) so we don't render Open5e's verbatim PHB
    // spell tables next to our interactive picker. Header lines like
    // "Druid Level | Circle Spells" also disappear because they're table
    // rows themselves.
    function _stripTables(text) {
        if (!text) return '';
        return String(text)
            .replace(/\r\n/g, '\n').replace(/\r/g, '\n')
            .split('\n')
            .filter(line => {
                if ((line.match(/\|/g) || []).length >= 2) return false;
                if (/^[\s\-:|]+$/.test(line) && line.includes('-')) return false;
                return true;
            })
            .join('\n')
            .replace(/\n{3,}/g, '\n\n')
            .trim();
    }

    // Open5e sometimes returns the same subclass feature multiple times
    // (e.g. "Circle Spells" as both a descriptive entry AND a separate per-
    // level spell table). Merge any same-named features into one card so the
    // player doesn't see duplicate "Circle Spells" headings.
    function _dedupeFeatures(features) {
        const order = [];
        const byName = new Map();
        features.forEach(f => {
            if (!f || typeof f !== 'object') return;
            const name = (f.name || '').trim();
            const key = name.toLowerCase();
            if (!key) { order.push(f); return; }
            if (byName.has(key)) {
                const existing = byName.get(key);
                const fdesc = (f.desc || '').trim();
                if (fdesc && (existing.desc || '').indexOf(fdesc) === -1) {
                    existing.desc = ((existing.desc || '') + '\n\n' + fdesc).trim();
                }
                // Keep the EARLIEST unlock level — that's when the player first
                // gets access to anything mentioned by this feature.
                if (f.level != null && (existing.level == null || f.level < existing.level)) {
                    existing.level = f.level;
                }
            } else {
                const copy = { name: name, desc: (f.desc || ''), level: f.level };
                byName.set(key, copy);
                order.push(copy);
            }
        });
        return order;
    }

    function _renderSubclassBlock(target, entry) {
        target.innerHTML = '';

        const className = entry.class || '';
        const subName   = entry.subclass_name || entry.subclass || '';
        const rawFlavor = entry.subclass_flavor || '';
        const lvl       = parseInt(entry.level, 10) || 0;

        // Look the subclass up in the curated picker table — used both for
        // deciding which features carry a picker AND for synthesizing
        // feature cards offline (when Open5e hasn't been hit yet or is
        // unreachable). The cards themselves come from Open5e for prose
        // when available, but the pickers are always renderable from the
        // curated data alone.
        const subclassData = (typeof window._lookupSubclassData === 'function')
            ? window._lookupSubclassData(entry)
            : null;

        // ── Synthesize missing curated picker cards ────────────────────
        // For any curated feature (main subclass-spells feature like "Circle
        // Spells" / "Domain Spells", or a bonusFeature like "Bonus Cantrip"
        // / "Acolyte of Nature") that Open5e didn't return, push a synthetic
        // feature into the list with no description. The dedupe + visible /
        // locked split below treats it like any other feature, and the
        // existing inline-picker logic gives it the matching picker as its
        // body. When Open5e later returns the real feature, the dedupe
        // merges them so the prose appears alongside the same picker.
        let rawFeatures = (entry.subclass_features || []).slice();
        if (subclassData) {
            const existingNames = new Set();
            rawFeatures.forEach(f => {
                if (f && f.name) existingNames.add(f.name.toLowerCase());
            });
            // Main subclass-spells feature (Circle Spells / Domain Spells / …)
            if (subclassData.feature && !existingNames.has(subclassData.feature.toLowerCase())) {
                const grants = [];
                if (Array.isArray(subclassData.grants)) grants.push(...subclassData.grants);
                if (subclassData.variants) Object.values(subclassData.variants).forEach(arr => {
                    if (Array.isArray(arr)) grants.push(...arr);
                });
                let minLvl = null;
                grants.forEach(g => {
                    if (g && g.classLvl && (minLvl == null || g.classLvl < minLvl)) minLvl = g.classLvl;
                });
                rawFeatures.push({
                    name: subclassData.feature,
                    desc: '',
                    level: minLvl,
                });
                existingNames.add(subclassData.feature.toLowerCase());
            }
            // bonusFeatures (Bonus Cantrip / Acolyte of Nature / …)
            if (Array.isArray(subclassData.bonusFeatures)) {
                subclassData.bonusFeatures.forEach(bf => {
                    if (bf && bf.feature && !existingNames.has(bf.feature.toLowerCase())) {
                        rawFeatures.push({
                            name: bf.feature,
                            desc: '',
                            level: bf.classLvl || null,
                        });
                        existingNames.add(bf.feature.toLowerCase());
                    }
                });
            }
        }
        const features = _dedupeFeatures(rawFeatures);

        // Pre-compute the lookups the visible-features loop will use below
        // so we can also reference them in the visible/locked split.
        const subclassMainFeature = (subclassData && subclassData.feature)
            ? subclassData.feature.toLowerCase()
            : null;
        const bonusFeaturesByName = new Map();
        if (subclassData && Array.isArray(subclassData.bonusFeatures)) {
            subclassData.bonusFeatures.forEach(bf => {
                if (bf && bf.feature) bonusFeaturesByName.set(bf.feature.toLowerCase(), bf);
            });
        }
        function _isPickerFeature(f) {
            if (!f || !f.name) return false;
            const lc = f.name.toLowerCase();
            return (subclassMainFeature && lc === subclassMainFeature)
                || bonusFeaturesByName.has(lc);
        }

        // Heading: "<Class> - <Subclass>" + source badge if the cached
        // detail blob carries one.
        const heading = document.createElement('div');
        heading.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:4px;';
        const lbl = document.createElement('span');
        lbl.style.cssText = 'font-size:11px;font-weight:700;letter-spacing:.05em;color:var(--muted,#888);text-transform:uppercase;';
        lbl.textContent = className + (subName ? ' - ' + subName : ' - (no subclass)');
        heading.appendChild(lbl);
        const subSource = entry.subclass_features_data && entry.subclass_features_data.source;
        // `_appendSourceBadge` is defined in a different IIFE (closure-scoped);
        // reach for the globally-exposed `window._appendSourceBadge` so this
        // call doesn't throw and break the rest of the class-block render.
        if (subSource && typeof window._appendSourceBadge === 'function') {
            window._appendSourceBadge(heading, subSource, 'subclasses');
        }
        if (!isReadonly) {
            const sync = document.createElement('button');
            sync.type = 'button';
            sync.className = 'mc-sync-sub-btn';
            sync.dataset.cslug = _slug(className);
            sync.style.cssText = 'font-size:11px;padding:2px 8px;';
            sync.textContent = '↻ Sync';
            sync.title = 'Re-fetch subclass features from Open5e';
            heading.appendChild(sync);
        }
        target.appendChild(heading);

        // ── File-based class actions slot (1.9.0) ──
        // Renders the Action descriptors declared on the class's local-content
        // record (e.g. Rogue's Sneak Attack damage_scaling, Barbarian's Rage
        // toggle). The slot is populated asynchronously from
        // /api/content/class_features/<slug>; if the record has no actions, or
        // local content isn't available, the slot stays empty and nothing
        // breaks downstream.
        const classActionsSlot = document.createElement('div');
        classActionsSlot.className = 'class-actions-slot';
        classActionsSlot.style.cssText = 'margin-bottom:10px;';
        target.appendChild(classActionsSlot);
        _populateContentActions(classActionsSlot, 'class_features', _slug(className), {
            characterLevel: lvl,
            actionLabelPrefix: className,
        });

        // If the subclass is set but its features haven't been cached yet,
        // show a quiet hint but DON'T return early — we still want the
        // Subclass Spells panel (Circle / Domain / Oath spells) to render
        // immediately, since it's driven by the curated table keyed off the
        // subclass slug and doesn't need the features blob.
        if (!features.length && !rawFlavor) {
            const p = document.createElement('p');
            p.className = 'muted';
            p.style.cssText = 'font-size:12px;margin:4px 0 0;';
            p.textContent = subName
                ? 'Fetching subclass features from Open5e…'
                : 'Pick a subclass on this class to see its features.';
            target.appendChild(p);
        }

        // When we have a curated picker for this subclass, strip out
        // markdown-style tables from the flavor before rendering — Open5e
        // stuffs the verbatim PHB spell tables into the subclass blurb and
        // we don't want them next to our interactive picker.
        const flavor = subclassData ? _stripTables(rawFlavor) : rawFlavor;
        const cleanedFlavor = _cleanMd(flavor);
        if (cleanedFlavor) {
            const f = document.createElement('div');
            f.style.cssText = 'font-size:12px;color:var(--fg-mute);font-style:italic;margin-bottom:10px;line-height:1.55;border-left:2px solid var(--accent-border,var(--accent));padding-left:8px;';
            f.textContent = cleanedFlavor;
            target.appendChild(f);
        }

        // Curated-picker features (Circle Spells, Bonus Cantrip, …) always
        // render in the visible list — even when their unlock level is
        // above the player's current class level — so the picker is always
        // reachable. The "Class Lv N" label inside the picker still tells
        // the player when each row unlocks.
        const visible = features.filter(f => f.level == null || f.level <= lvl || _isPickerFeature(f));
        const locked  = features.filter(f => f.level != null && f.level >  lvl && !_isPickerFeature(f));

        // ``customBody`` replaces the description body with whatever element
        // the caller supplies — used to put the Subclass Spells picker
        // inside the "Circle Spells" / "Domain Spells" / "Oath Spells" card
        // so the verbatim PHB tables don't show up next to the interactive
        // picker. ``startsOpen`` opens the body without a click; useful when
        // the body IS the interactive control. ``bodyAppend`` is an extra
        // element tacked onto the bottom of the body (after the description
        // or customBody) — used to slot a Feature Grants picker into a
        // "Bonus Cantrip" card right under its description text.
        function makeCard(feat, dimmed, customBody, startsOpen, bodyAppend) {
            const card = document.createElement('div');
            card.style.cssText = 'margin-bottom:5px;border-radius:5px;overflow:hidden;border:1px solid var(--border);opacity:' + (dimmed ? '0.5' : '1') + ';';
            const hdr = document.createElement('div');
            hdr.style.cssText = 'display:flex;align-items:center;gap:8px;padding:7px 10px;background:' + (dimmed ? 'var(--bg)' : 'var(--bg-2)') + ';cursor:pointer;user-select:none;';
            const arrow = document.createElement('span');
            arrow.style.cssText = 'font-size:9px;color:var(--fg-mute);flex-shrink:0;transition:transform .15s;transform:' + (startsOpen ? 'rotate(0deg)' : 'rotate(-90deg)') + ';';
            arrow.textContent = '▼';
            hdr.appendChild(arrow);
            const nameSpan = document.createElement('span');
            nameSpan.style.cssText = 'font-size:12px;font-weight:600;color:' + (dimmed ? 'var(--fg-mute)' : 'var(--fg)') + ';flex:1;';
            nameSpan.textContent = feat.name || 'Feature';
            hdr.appendChild(nameSpan);
            if (feat.level != null) {
                const badge = document.createElement('span');
                badge.style.cssText = 'font-size:10px;padding:1px 7px;border-radius:10px;white-space:nowrap;flex-shrink:0;border:1px solid var(--accent-border,var(--border));' +
                    (dimmed ? 'background:transparent;color:var(--fg-mute);' : 'background:var(--accent-bg2);color:var(--accent);');
                badge.textContent = 'Lvl ' + feat.level;
                hdr.appendChild(badge);
            }
            card.appendChild(hdr);
            let body = null;
            if (customBody) {
                body = document.createElement('div');
                body.style.cssText = 'display:' + (startsOpen ? '' : 'none') + ';padding:10px 12px;background:var(--bg);border-top:1px solid var(--border);';
                body.appendChild(customBody);
                card.appendChild(body);
            } else if (feat.desc) {
                body = document.createElement('div');
                body.style.cssText = 'display:' + (startsOpen ? '' : 'none') + ';padding:10px 12px;font-size:12px;line-height:1.65;color:var(--fg-mute);background:var(--bg);border-top:1px solid var(--border);';
                _cleanMd(feat.desc).split('\n\n').forEach(para => {
                    para = para.trim(); if (!para) return;
                    const p = document.createElement('p');
                    p.style.cssText = 'margin:0 0 8px;';
                    if (para.includes('\n')) {
                        para.split('\n').forEach((line, i) => {
                            if (i > 0) p.appendChild(document.createElement('br'));
                            p.appendChild(document.createTextNode(line));
                        });
                    } else { p.textContent = para; }
                    body.appendChild(p);
                });
                card.appendChild(body);
            }
            if (bodyAppend) {
                if (!body) {
                    body = document.createElement('div');
                    body.style.cssText = 'display:' + (startsOpen ? '' : 'none') + ';padding:10px 12px;background:var(--bg);border-top:1px solid var(--border);';
                    card.appendChild(body);
                } else if (body.firstChild) {
                    // Thin divider between description text and the picker.
                    const sep = document.createElement('div');
                    sep.style.cssText = 'margin:8px 0 6px;border-top:1px dashed var(--border);';
                    body.appendChild(sep);
                }
                body.appendChild(bodyAppend);
            }
            if (body) {
                hdr.addEventListener('click', () => {
                    const open = body.style.display !== 'none';
                    body.style.display = open ? 'none' : '';
                    arrow.style.transform = open ? 'rotate(-90deg)' : 'rotate(0deg)';
                });
            }
            return card;
        }

        // ── Render visible feature cards. Each card may have an interactive
        //    panel inlined directly under it — the main Subclass Spells panel
        //    sits under the matching "Circle Spells" / "Domain Spells" /
        //    "Oath Spells" card; individual cantrip grants ("Bonus Cantrip",
        //    "Acolyte of Nature") sit under their own feature cards. The
        //    inlined name is tracked so the fallback panels at the bottom
        //    don't render anything twice. ──
        // (``subclassData``, ``subclassMainFeature``, and ``bonusFeaturesByName``
        //  were all set up at the top of this function so the visible/locked
        //  split could also reference them.)
        const inlinedSubclassPanel = { done: false };
        const inlinedGrantNames = new Set();
        const cslug = _slug(entry.class || '');

        visible.forEach(f => {
            const fNameLc = (f.name || '').toLowerCase();

            // The main subclass-spells panel ("Circle Spells", "Domain Spells", …)
            // — REPLACE the verbatim PHB tables in the card body with the
            // interactive picker. Card starts expanded so the picker is
            // visible without a click.
            if (fNameLc && !inlinedSubclassPanel.done
                && subclassMainFeature && fNameLc === subclassMainFeature
                && typeof window._renderSubclassSpellPanel === 'function') {
                const pickerBody = document.createElement('div');
                window._renderSubclassSpellPanel(pickerBody, entry, { inline: true });
                target.appendChild(makeCard(f, false, pickerBody, true));
                inlinedSubclassPanel.done = true;
                return;
            }

            if (!fNameLc) {
                target.appendChild(makeCard(f, false));
                return;
            }

            // A curated bonusFeatures entry matching this card — render the
            // card with its description AND the Feature Grants picker inside
            // the body (the card opens expanded so the picker is visible).
            if (bonusFeaturesByName.has(fNameLc)
                && typeof window._renderFeatureGrantsPanel === 'function') {
                const pickerExtra = document.createElement('div');
                window._renderFeatureGrantsPanel(pickerExtra, entry, {
                    inline: true,
                    onlyFeature: f.name,
                });
                target.appendChild(makeCard(f, false, null, true, pickerExtra));
                inlinedGrantNames.add(fNameLc);
                return;
            }

            // Otherwise let the parser have a look at this card's description.
            if (typeof window._parseCantripGrant === 'function'
                && typeof window._renderFeatureGrantsPanel === 'function') {
                const g = window._parseCantripGrant(f.name || '', f.desc || '', cslug);
                if (g) {
                    const pickerExtra = document.createElement('div');
                    window._renderFeatureGrantsPanel(pickerExtra, entry, {
                        inline: true,
                        onlyFeature: f.name,
                    });
                    target.appendChild(makeCard(f, false, null, true, pickerExtra));
                    inlinedGrantNames.add(fNameLc);
                    return;
                }
            }

            // No grant — render the normal description card.
            target.appendChild(makeCard(f, false));
        });

        if (locked.length) {
            const lockedWrap = document.createElement('div');
            lockedWrap.style.cssText = 'margin-top:6px;';
            const lockedLabel = document.createElement('div');
            lockedLabel.style.cssText = 'font-size:10px;color:var(--fg-mute);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;padding-left:2px;';
            lockedLabel.textContent = 'Future features';
            lockedWrap.appendChild(lockedLabel);
            locked.forEach(f => lockedWrap.appendChild(makeCard(f, true)));
            target.appendChild(lockedWrap);
        }

        // ── Fallback: grants that couldn't be matched to a visible feature
        //    card (e.g. subclass set but features not yet synced). Render
        //    them at the bottom inside the usual panel wrapper. Anything
        //    already inlined above is filtered out. ──
        if (!inlinedSubclassPanel.done && subclassData
            && typeof window._renderSubclassSpellPanel === 'function') {
            const fallback = document.createElement('div');
            target.appendChild(fallback);
            window._renderSubclassSpellPanel(fallback, entry);
        }
        if (typeof window._renderFeatureGrantsPanel === 'function') {
            const fallback = document.createElement('div');
            target.appendChild(fallback);
            window._renderFeatureGrantsPanel(fallback, entry, {
                excludeFeatures: inlinedGrantNames,
            });
            // Strip the element if the panel rendered nothing
            if (!fallback.children.length) fallback.remove();
        }
    }

    function _renderAllSubclassBlocks() {
        if (!sfContainer) return;
        const arr = _readRoster();
        // Clear any previous blocks but keep #sf-empty for the no-classes state
        sfContainer.querySelectorAll('.sf-class-block').forEach(b => b.remove());
        if (sfEmptyMsg) sfEmptyMsg.style.display = arr.length ? 'none' : '';
        // One block per class entry
        arr.forEach((entry) => {
            const block = document.createElement('div');
            block.className = 'sf-class-block';
            block.dataset.cslug = _slug(entry.class || '');
            sfContainer.appendChild(block);
            _renderSubclassBlock(block, entry);
        });
    }

    // ── Multiclass prereq check ──
    // Non-blocking warning: if the character's ability scores don't meet
    // the target class's multiclass minimums (as defined either in the
    // shipped class JSON or in a campaign-scoped homebrew row), surface
    // the reasons in a banner appended below the class row.  Skipped on
    // standalone (no CHAR_ID) and read-only sheet views.
    async function _checkAndRenderMulticlassPrereq(idx, className, classSel) {
        if (typeof CHAR_ID === 'undefined' || !CHAR_ID) return;
        // Find the row in the DOM so we can attach the banner.
        const row = classSel.closest('.mc-row');
        if (!row) return;
        // Always clear the previous banner first.
        const old = row.querySelector('.mc-prereq-warning');
        if (old) old.remove();
        const slug = _slug(className || '');
        if (!slug) return;
        try {
            const r = await fetch('/api/character/' + CHAR_ID + '/multiclass-check?target_class=' + encodeURIComponent(slug));
            if (!r.ok) return;
            const check = await r.json();
            if (check.ok || !(check.reasons && check.reasons.length)) return;
            const warn = document.createElement('div');
            warn.className = 'mc-prereq-warning';
            warn.style.cssText =
                'grid-column:1 / -1;padding:6px 10px;background:#3a2f15;' +
                'border:1px solid #6e5828;border-radius:4px;color:#e0c478;' +
                'font-size:11px;line-height:1.4;margin-top:2px;';
            const label = document.createElement('strong');
            label.style.cssText = 'color:#f0d088;margin-right:6px;';
            label.textContent = '⚠ Multiclass:';
            warn.appendChild(label);
            warn.appendChild(document.createTextNode(check.reasons.join(' • ')));
            row.appendChild(warn);
        } catch {}
    }

    // ── Multiclass list editor ──
    function _row(entry, idx, classOptions) {
        const row = document.createElement('div');
        row.className = 'mc-row';
        row.dataset.mcIdx = idx;
        row.style.cssText = 'display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) 70px auto;gap:6px;align-items:center;';

        const classWrap = document.createElement('div');
        classWrap.style.cssText = 'display:flex;flex-direction:column;gap:2px;';
        const classLabel = document.createElement('span');
        classLabel.style.cssText = 'font-size:9px;color:var(--s-mute);font-weight:700;text-transform:uppercase;letter-spacing:.06em;';
        classLabel.textContent = idx === 0 ? 'Class' : 'Class ' + (idx + 1);
        classWrap.appendChild(classLabel);
        const classSel = document.createElement('select');
        classSel.className = 'mc-class-select';
        classSel.dataset.mcIdx = idx;
        classSel.style.cssText = 'font-size:12px;';
        if (isReadonly) classSel.disabled = true;
        _populateSelect(classSel, classOptions, entry.class || '');
        classWrap.appendChild(classSel);
        row.appendChild(classWrap);

        const subWrap = document.createElement('div');
        subWrap.style.cssText = 'display:flex;flex-direction:column;gap:2px;';
        const subLabel = document.createElement('span');
        subLabel.style.cssText = 'font-size:9px;color:var(--s-mute);font-weight:700;text-transform:uppercase;letter-spacing:.06em;';
        subLabel.textContent = 'Subclass';
        subWrap.appendChild(subLabel);
        const subSel = document.createElement('select');
        subSel.className = 'mc-subclass-select';
        subSel.dataset.mcIdx = idx;
        subSel.style.cssText = 'font-size:12px;';
        if (isReadonly) subSel.disabled = true;
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = entry.class ? '— loading… —' : '— pick a class —';
        subSel.appendChild(placeholder);
        subWrap.appendChild(subSel);
        row.appendChild(subWrap);

        const lvlWrap = document.createElement('div');
        lvlWrap.style.cssText = 'display:flex;flex-direction:column;gap:2px;';
        const lvlLabel = document.createElement('span');
        lvlLabel.style.cssText = 'font-size:9px;color:var(--s-mute);font-weight:700;text-transform:uppercase;letter-spacing:.06em;';
        lvlLabel.textContent = 'Level';
        lvlWrap.appendChild(lvlLabel);
        const lvlInp = document.createElement('input');
        lvlInp.type = 'number';
        lvlInp.className = 'mc-level-input';
        lvlInp.dataset.mcIdx = idx;
        lvlInp.min = '1';
        lvlInp.max = '20';
        lvlInp.value = entry.level || 1;
        lvlInp.style.cssText = 'font-size:12px;text-align:center;';
        if (isReadonly) lvlInp.readOnly = true;
        lvlWrap.appendChild(lvlInp);
        row.appendChild(lvlWrap);

        const rmBtn = document.createElement('button');
        rmBtn.type = 'button';
        rmBtn.className = 'mc-remove-btn';
        rmBtn.dataset.mcIdx = idx;
        rmBtn.textContent = '×';
        rmBtn.title = 'Remove this class';
        rmBtn.style.cssText = 'background:transparent;border:1px solid var(--s-border);color:var(--s-danger);width:28px;height:28px;border-radius:4px;cursor:pointer;font-size:14px;line-height:1;align-self:flex-end;';
        if (isReadonly) rmBtn.style.display = 'none';
        row.appendChild(rmBtn);

        return row;
    }

    async function _renderEditor() {
        if (!listEl) { _refreshTotalLevel(); _refreshMirrors(); _renderAllSubclassBlocks(); _refreshProfTable(); return; }
        const arr = _readRoster();
        listEl.innerHTML = '';
        const classOptions = await _classList();
        arr.forEach((entry, idx) => listEl.appendChild(_row(entry, idx, classOptions)));
        _refreshTotalLevel();

        // Wire each row's class select
        listEl.querySelectorAll('.mc-class-select').forEach(async (sel) => {
            const idx = parseInt(sel.dataset.mcIdx, 10);
            const entry = (_readRoster()[idx] || {});
            const subSel = listEl.querySelector(`.mc-subclass-select[data-mc-idx="${idx}"]`);
            // populate subclass options for this entry's class
            if (subSel) {
                if (entry.class) {
                    const items = await _subclassList(_slug(entry.class));
                    _populateSelect(subSel, items, entry.subclass || '');
                } else {
                    subSel.innerHTML = '<option value="">— pick a class first —</option>';
                }
            }
            sel.addEventListener('change', async () => {
                const arr2 = _readRoster();
                const e = arr2[idx] || {};
                e.class = sel.value;
                e.subclass = '';
                e.subclass_features = [];
                e.subclass_name = '';
                e.subclass_flavor = '';
                // Clear cached proficiencies so the new class's data fills in
                ['class_hit_die','class_armor','class_weapons','class_tools',
                 'class_saving_throws','class_skills','class_spellcasting',
                 'class_equipment','class_features'].forEach(k => { delete e[k]; });
                arr2[idx] = e;
                await _fillClassDetail(e, true);
                _writeRoster(arr2);
                // Repopulate subclass dropdown for the new class
                if (subSel) {
                    if (e.class) {
                        const items = await _subclassList(_slug(e.class));
                        _populateSelect(subSel, items, '');
                    } else {
                        subSel.innerHTML = '<option value="">— pick a class first —</option>';
                    }
                }
                _renderAllSubclassBlocks();
                _refreshProfTable(true);
                _refreshSpellSlots(false);
                // Multiclass prereq check — non-blocking warning if the
                // character doesn't meet ability minimums for this class.
                _checkAndRenderMulticlassPrereq(idx, e.class, sel);
            });
        });

        // Wire each row's subclass select
        listEl.querySelectorAll('.mc-subclass-select').forEach(sel => {
            const idx = parseInt(sel.dataset.mcIdx, 10);
            sel.addEventListener('change', async () => {
                const arr2 = _readRoster();
                const e = arr2[idx] || {};
                e.subclass = sel.value;
                const opt = sel.options[sel.selectedIndex];
                e._subclass_slug = (opt && opt.dataset && opt.dataset.slug) || _slug(sel.value);
                arr2[idx] = e;
                await _fillSubclassDetail(e);
                _writeRoster(arr2);
                _renderAllSubclassBlocks();
                _saveSubclassCacheRow(e);
            });
        });

        // Level inputs
        listEl.querySelectorAll('.mc-level-input').forEach(inp => {
            const idx = parseInt(inp.dataset.mcIdx, 10);
            const apply = () => {
                let v = parseInt(inp.value, 10);
                if (isNaN(v) || v < 1) v = 1;
                if (v > 20) v = 20;
                const arr2 = _readRoster();
                const otherTotal = arr2.reduce((acc, c, i) => i === idx ? acc : acc + (parseInt(c.level, 10) || 0), 0);
                const max = MAX_TOTAL_LEVEL - otherTotal;
                if (v > max) {
                    v = Math.max(1, max);
                    if (window.showToast) window.showToast(`Total level capped at ${MAX_TOTAL_LEVEL}.`, 'warning');
                }
                inp.value = v;
                if (arr2[idx]) {
                    arr2[idx].level = v;
                    _writeRoster(arr2);
                    _renderAllSubclassBlocks();
                    _refreshProfTable();
                    _refreshSpellSlots(false);
                }
            };
            inp.addEventListener('change', apply);
            inp.addEventListener('input', apply);
        });

        // Remove buttons
        listEl.querySelectorAll('.mc-remove-btn').forEach(btn => {
            const idx = parseInt(btn.dataset.mcIdx, 10);
            btn.addEventListener('click', () => {
                const arr2 = _readRoster();
                if (arr2.length <= 1) {
                    if (window.showToast) window.showToast('Need at least one class.', 'warning');
                    return;
                }
                const removed = arr2.splice(idx, 1)[0];
                // Drop the removed class's spell slots so they don't linger
                const removedSlug = _slug(removed && removed.class);
                if (removedSlug && slotsParking) {
                    slotsParking.querySelectorAll(`.ss-row[data-cslug="${CSS.escape(removedSlug)}"]`).forEach(r => r.remove());
                }
                _writeRoster(arr2);
                _renderEditor();
                _renderAllSubclassBlocks();
                _refreshProfTable(true);
                _refreshSpellSlots(false);
            });
        });

        // Subclass-features ↻ Sync buttons (delegate)
        if (sfContainer && !sfContainer._mcSyncBound) {
            sfContainer._mcSyncBound = true;
            sfContainer.addEventListener('click', async (ev) => {
                const btn = ev.target.closest('.mc-sync-sub-btn');
                if (!btn) return;
                const cslug = btn.dataset.cslug;
                const arr2 = _readRoster();
                const idx = arr2.findIndex(c => _slug(c.class) === cslug);
                if (idx < 0) return;
                btn.disabled = true; btn.textContent = '↻ Syncing…';
                try {
                    await _fillSubclassDetail(arr2[idx]);
                    _writeRoster(arr2);
                    _renderAllSubclassBlocks();
                    _saveSubclassCacheRow(arr2[idx]);
                } finally {
                    btn.disabled = false; btn.textContent = '↻ Sync';
                }
            });
        }

        _refreshMirrors();
        _renderAllSubclassBlocks();
        _refreshProfTable();
        _refreshSpellSlots(true);
        // Auto-fetch any missing subclass/class details so the Subclass Spells
        // and Feature Grants panels populate without the player having to
        // click the ↻ Sync button on each class.
        _autoSyncMissingDetails();
    }

    // Background fetch for entries whose subclass features or class features
    // haven't been cached yet. Each entry is tried at most once per session
    // (tracked by a stable key) so we never thrash Open5e.
    const _autoSyncedKeys = new Set();
    async function _autoSyncMissingDetails() {
        const arr = _readRoster();
        if (!arr.length) return;
        let changed = false;
        for (const entry of arr) {
            const key = (entry.class || '') + '|' + (entry.subclass || '');
            if (_autoSyncedKeys.has(key)) continue;
            const needsSub = (entry.subclass || '') && !((entry.subclass_features || []).length) && !(entry.subclass_flavor || '').trim();
            const needsCls = (entry.class || '')    && !((entry.class_features || '') + '').trim();
            if (!needsSub && !needsCls) continue;
            _autoSyncedKeys.add(key);
            try {
                if (needsSub) await _fillSubclassDetail(entry);
                if (needsCls) await _fillClassDetail(entry, false);
                changed = true;
            } catch {}
        }
        if (changed) {
            _writeRoster(arr);
            _renderAllSubclassBlocks();
            _refreshProfTable();
            // Persist subclass cache (per-class PATCH) so refresh sticks.
            arr.forEach(e => {
                if (e.subclass && (e.subclass_features || []).length) _saveSubclassCacheRow(e);
            });
        }
    }

    // ── Class proficiency table sync ──
    function _refreshProfTable(rebuildOnRosterChange) {
        if (!profTable) return;
        const arr = _readRoster();
        if (rebuildOnRosterChange) {
            // Rebuild header + body to match the current roster
            const nClasses = arr.length;
            const colgroup = profTable.querySelector('colgroup');
            if (colgroup) {
                colgroup.innerHTML = '<col style="width:130px;">' + Array(nClasses).fill('<col>').join('');
            }
            const thead = profTable.querySelector('thead');
            if (thead) {
                const ths = arr.map((c, i) =>
                    `<th class="cprof-class-th" data-mc-idx="${i}" style="text-align:left;font-size:11px;font-weight:700;color:var(--s-fg);padding:6px 8px;border-bottom:1px solid var(--s-border);white-space:nowrap;">
                        ${_esc(c.class || '—')} <span style="color:var(--s-accent);">Lv ${parseInt(c.level,10)||1}</span>
                    </th>`).join('');
                thead.innerHTML = `<tr>
                    <th style="text-align:left;font-size:10px;font-weight:700;color:var(--s-mute);text-transform:uppercase;letter-spacing:.06em;padding:6px 8px;border-bottom:1px solid var(--s-border);">&nbsp;</th>
                    ${ths}
                </tr>`;
            }
            const tbody = profTable.querySelector('tbody');
            if (tbody) {
                const rows = [
                    ['Hit Die',       'class_hit_die'],
                    ['Armor',         'class_armor'],
                    ['Weapons',       'class_weapons'],
                    ['Tools',         'class_tools'],
                    ['Saving Throws', 'class_saving_throws'],
                    ['Skills',        'class_skills'],
                    ['Spellcasting',  'class_spellcasting'],
                    ['Starting Eq.',  'class_equipment'],
                ];
                tbody.innerHTML = rows.map(([label, key]) =>
                    `<tr><th style="text-align:left;font-size:11px;font-weight:700;color:var(--s-mute);text-transform:uppercase;letter-spacing:.04em;padding:5px 8px;border-bottom:1px solid var(--s-border);white-space:nowrap;vertical-align:top;">${_esc(label)}</th>` +
                    arr.map((c, i) =>
                        `<td class="cprof-cell" data-mc-idx="${i}" data-cprof-key="${key}" style="padding:4px 8px;border-bottom:1px solid var(--s-border);vertical-align:top;">${
                            isReadonly
                                ? `<span style="font-size:12px;color:var(--fg,#e0e0e0);white-space:pre-wrap;">${_esc(c[key] || '—')}</span>`
                                : `<input type="text" class="cprof-input" data-mc-idx="${i}" data-cprof-key="${key}" value="${_esc(c[key] || '')}" style="width:100%;font-size:12px;" placeholder="—">`
                        }</td>`
                    ).join('') + '</tr>'
                ).join('');
            }
        } else {
            // Light update: just refresh header levels + cell values to reflect current roster
            profTable.querySelectorAll('.cprof-class-th').forEach((th) => {
                const i = parseInt(th.dataset.mcIdx, 10);
                const c = arr[i];
                if (c) th.innerHTML = `${_esc(c.class || '—')} <span style="color:var(--s-accent);">Lv ${parseInt(c.level,10)||1}</span>`;
            });
            profTable.querySelectorAll('.cprof-input').forEach((inp) => {
                const i = parseInt(inp.dataset.mcIdx, 10);
                const k = inp.dataset.cprofKey;
                const c = arr[i];
                if (c && document.activeElement !== inp) inp.value = c[k] || '';
            });
        }

        // Wire input listeners (delegated)
        if (!profTable._cprofBound) {
            profTable._cprofBound = true;
            profTable.addEventListener('input', (ev) => {
                const inp = ev.target.closest('.cprof-input');
                if (!inp) return;
                const idx = parseInt(inp.dataset.mcIdx, 10);
                const key = inp.dataset.cprofKey;
                const arr2 = _readRoster();
                if (arr2[idx]) {
                    arr2[idx][key] = inp.value;
                    _writeRoster(arr2);
                }
            });
        }

        // Wire ↻ Sync (re-fetch all classes' details)
        const syncBtn = document.getElementById('sync-class-btn');
        if (syncBtn && !syncBtn._mcBound) {
            syncBtn._mcBound = true;
            syncBtn.addEventListener('click', async () => {
                const arr2 = _readRoster();
                syncBtn.disabled = true;
                syncBtn.textContent = '↻ Syncing…';
                const status = document.getElementById('sync-class-status');
                if (status) status.textContent = '';
                try {
                    for (const e of arr2) await _fillClassDetail(e, true);
                    _writeRoster(arr2);
                    _refreshProfTable(true);
                    if (status) { status.textContent = '✓ Synced'; status.style.color = '#6cb'; }
                } catch (err) {
                    if (status) { status.textContent = 'Error: ' + err.message; status.style.color = '#e07070'; }
                } finally {
                    syncBtn.disabled = false; syncBtn.textContent = '↻ Sync';
                    if (status) setTimeout(() => { status.textContent = ''; }, 4000);
                }
            });
        }
    }

    // ── Per-class spell slot management ──
    // Spell slots live in #spell-slots-ui as .ss-row elements, each tagged
    // with data-cslug + data-lvl. Adding a new class creates 9 fresh rows
    // (all level 1-9 empty). Removing a class removes its rows.
    function _ensureSlotRowsForClass(cslug, classLabel) {
        if (!slotsParking || !cslug) return;
        for (let lvl = 1; lvl <= 9; lvl++) {
            let row = slotsParking.querySelector(`.ss-row[data-cslug="${CSS.escape(cslug)}"][data-lvl="${lvl}"]`);
            if (row) {
                row.dataset.classLabel = classLabel || cslug;
                continue;
            }
            row = document.createElement('div');
            row.className = 'ss-row';
            row.dataset.cslug = cslug;
            row.dataset.classLabel = classLabel || cslug;
            row.dataset.lvl = String(lvl);
            row.dataset.total = '0';
            row.dataset.used = '0';
            row.style.cssText = 'display:none;align-items:center;gap:8px;';
            row.innerHTML =
                `<span style="font-size:11px;font-weight:600;width:38px;flex-shrink:0;color:var(--s-mute);letter-spacing:.03em;">Lv ${lvl}</span>` +
                `<div class="ss-pips" style="display:flex;gap:5px;flex-wrap:wrap;flex:1;"></div>` +
                `<input type="hidden" name="spell_slots.${cslug}.${lvl}.total" class="ss-total-input" value="0">` +
                `<input type="hidden" name="spell_slots.${cslug}.${lvl}.used"  class="ss-used-input"  value="0">`;
            slotsParking.appendChild(row);
        }
    }

    function _refreshSpellSlots(autoFillIfZero) {
        if (!slotsParking) return;
        const arr = _readRoster();
        // Make sure every active class has its 9 rows present
        const liveSlugs = new Set();
        arr.forEach(e => {
            const slug = _slug(e.class);
            if (!slug) return;
            liveSlugs.add(slug);
            _ensureSlotRowsForClass(slug, e.class);
            // Also tag the row's mc-idx so we can find it later
            slotsParking.querySelectorAll(`.ss-row[data-cslug="${CSS.escape(slug)}"]`).forEach(r => {
                r.dataset.classLabel = e.class || slug;
            });
        });
        // Remove rows for classes no longer present
        slotsParking.querySelectorAll('.ss-row').forEach(r => {
            const s = r.dataset.cslug;
            if (s && !liveSlugs.has(s)) r.remove();
        });
        // Optionally auto-fill slot tables (preserves existing non-zero values)
        if (autoFillIfZero && typeof window._mcAutoFillSlots === 'function') {
            window._mcAutoFillSlots(false);
        }
        // Re-render the spell list groups to pick up new slot rows
        if (typeof window._mcRenderSpells === 'function') window._mcRenderSpells();
    }

    // ── WebSocket: spell_slot_update — update the right (class, level) row ──
    document.addEventListener('vtt:ws-message', function (ev) {
        const msg = ev.detail;
        if (!msg || msg.type !== 'spell_slot_update') return;
        const d = msg.data || {};
        const myCharId = (sheetForm && parseInt(sheetForm.dataset.charId, 10)) || null;
        if (myCharId == null || d.character_id !== myCharId) return;
        const cslug = (d.class_slug || '').toLowerCase();
        const row = cslug
            ? slotsParking && slotsParking.querySelector(`.ss-row[data-cslug="${CSS.escape(cslug)}"][data-lvl="${d.level}"]`)
            : null;
        if (!row) return;
        row.dataset.total = d.total;
        row.dataset.used  = d.used;
        if (window._ssSyncInputs) window._ssSyncInputs(row);
        if (window._ssRenderPips) window._ssRenderPips(row);
    });

    // ── Add Class ──
    if (addBtn) {
        addBtn.addEventListener('click', async () => {
            const arr = _readRoster();
            const total = arr.reduce((a, c) => a + (parseInt(c.level, 10) || 0), 0);
            if (total >= MAX_TOTAL_LEVEL) {
                if (window.showToast) window.showToast(`Total level already at ${MAX_TOTAL_LEVEL}.`, 'warning');
                return;
            }
            arr.push({ class: '', subclass: '', level: 1 });
            _writeRoster(arr);
            await _renderEditor();
        });
    }

    // ── Expose helpers to other modules in the page ──
    window._mcRoster      = _readRoster;
    window._mcWriteRoster = _writeRoster;
    window._mcPrimary     = () => _primary(_readRoster());
    window._mcClassSlug   = _slug;
    // The subclass picker helpers (_lookupSubclassData, _renderSubclassSpellPanel,
    // _renderFeatureGrantsPanel) are defined in an inline <script> block inside
    // sheet_dnd5e.html that loads AFTER this file. When localStorage has the
    // Open5e class/subclass lists cached, our initial _renderEditor() flow
    // resolves its awaits on the microtask queue and runs _renderAllSubclassBlocks
    // BEFORE the browser parses that inline block — at which point those window.*
    // helpers are still undefined and the per-feature inline pickers never render.
    // Exposing the renderer here lets the helper-defining block trigger one
    // re-render once it finishes setting up.
    window._mcRenderSubclassBlocks = _renderAllSubclassBlocks;

    // Initial render
    _renderEditor();
})();

// ── Spell slot auto-fill from class + level ──
;(function () {
    // In multiclass mode the per-class autofill lives in the spellcasting
    // framework script inside sheet_dnd5e.html, so this legacy single-class
    // helper becomes a no-op.
    if (document.getElementById('classes-data')) {
        window._syncSpellSlots = function () {};
        return;
    }
    // Rows indexed by characterLevel - 1 (index 0 = level 1).
    // Each row: [slots_l1, slots_l2, ..., slots_l9]
    const _FULL = [
        [2,0,0,0,0,0,0,0,0],
        [3,0,0,0,0,0,0,0,0],
        [4,2,0,0,0,0,0,0,0],
        [4,3,0,0,0,0,0,0,0],
        [4,3,2,0,0,0,0,0,0],
        [4,3,3,0,0,0,0,0,0],
        [4,3,3,1,0,0,0,0,0],
        [4,3,3,2,0,0,0,0,0],
        [4,3,3,3,1,0,0,0,0],
        [4,3,3,3,2,0,0,0,0],
        [4,3,3,3,2,1,0,0,0],
        [4,3,3,3,2,1,0,0,0],
        [4,3,3,3,2,1,1,0,0],
        [4,3,3,3,2,1,1,0,0],
        [4,3,3,3,2,1,1,1,0],
        [4,3,3,3,2,1,1,1,0],
        [4,3,3,3,2,1,1,1,1],
        [4,3,3,3,3,1,1,1,1],
        [4,3,3,3,3,2,1,1,1],
        [4,3,3,3,3,2,2,1,1],
    ];

    // Half-casters (Paladin, Ranger) — no slots until level 2
    const _HALF = [
        [0,0,0,0,0,0,0,0,0],
        [2,0,0,0,0,0,0,0,0],
        [3,0,0,0,0,0,0,0,0],
        [3,0,0,0,0,0,0,0,0],
        [4,2,0,0,0,0,0,0,0],
        [4,2,0,0,0,0,0,0,0],
        [4,3,0,0,0,0,0,0,0],
        [4,3,0,0,0,0,0,0,0],
        [4,3,2,0,0,0,0,0,0],
        [4,3,2,0,0,0,0,0,0],
        [4,3,3,0,0,0,0,0,0],
        [4,3,3,0,0,0,0,0,0],
        [4,3,3,1,0,0,0,0,0],
        [4,3,3,1,0,0,0,0,0],
        [4,3,3,2,0,0,0,0,0],
        [4,3,3,2,0,0,0,0,0],
        [4,3,3,3,1,0,0,0,0],
        [4,3,3,3,1,0,0,0,0],
        [4,3,3,3,2,0,0,0,0],
        [4,3,3,3,2,0,0,0,0],
    ];

    // Warlock pact magic — all slots at one level, number of slots varies
    // Row: [slots, slot_level] — converted to the 9-element array in getSpellSlots
    const _WARLOCK_RAW = [
        [1,1],[2,1],[2,2],[2,2],[2,3],[2,3],[2,4],[2,4],[2,5],[2,5],
        [3,5],[3,5],[3,5],[3,5],[3,5],[3,5],[4,5],[4,5],[4,5],[4,5],
    ];

    const _NONE = Array(20).fill([0,0,0,0,0,0,0,0,0]);

    // Map lowercase class names → their table
    const _CLASS_TABLE = {
        'bard': _FULL, 'cleric': _FULL, 'druid': _FULL,
        'sorcerer': _FULL, 'wizard': _FULL,
        'paladin': _HALF, 'ranger': _HALF,
        'warlock': 'warlock',
        'artificer': _HALF,
        'barbarian': _NONE, 'fighter': _NONE, 'monk': _NONE,
        'rogue': _NONE, 'blood hunter': _NONE,
    };

    function getSpellSlots(className, level) {
        const lvl = Math.max(1, Math.min(20, parseInt(level) || 1));
        const key = (className || '').toLowerCase().trim();
        const table = _CLASS_TABLE[key];
        const result = {};
        if (!table) {
            for (let i = 1; i <= 9; i++) result[i] = 0;
            return result;
        }
        if (table === 'warlock') {
            const [slots, slotLvl] = _WARLOCK_RAW[lvl - 1];
            for (let i = 1; i <= 9; i++) result[i] = (i === slotLvl) ? slots : 0;
            return result;
        }
        const row = table[lvl - 1];
        for (let i = 1; i <= 9; i++) result[i] = row[i - 1] || 0;
        return result;
    }

    function _renderPipsFallback(row) {
        const total = parseInt(row.dataset.total) || 0;
        const used  = parseInt(row.dataset.used)  || 0;
        const pipsDiv = row.querySelector('.ss-pips');
        if (!pipsDiv) return;
        pipsDiv.innerHTML = '';
        row.style.display = total === 0 ? 'none' : 'flex';
        const totalLabel = row.querySelector('.ss-total-label');
        if (totalLabel) totalLabel.textContent = total;
        for (let i = 0; i < total; i++) {
            const pip = document.createElement('span');
            pip.style.cssText = [
                'width:18px','height:18px','border-radius:50%',
                'border:2px solid #7b8cde','display:inline-block',
                i < used ? 'background:#7b8cde' : 'background:transparent',
            ].join(';');
            pipsDiv.appendChild(pip);
        }
    }

    function applySpellSlots(slots) {
        const renderRow = typeof window._ssRenderPips === 'function'
            ? window._ssRenderPips
            : _renderPipsFallback;
        for (let lvl = 1; lvl <= 9; lvl++) {
            const total = slots[lvl] || 0;
            const row = document.querySelector(`.ss-row[data-lvl="${lvl}"]`);
            if (!row) continue;
            const current = parseInt(row.dataset.total) || 0;
            if (current === total) continue;
            row.dataset.total = total;
            const used = parseInt(row.dataset.used) || 0;
            if (used > total) row.dataset.used = total;
            const totalInput = row.querySelector('.ss-total-input');
            const usedInput  = row.querySelector('.ss-used-input');
            if (totalInput) totalInput.value = total;
            if (usedInput)  usedInput.value  = parseInt(row.dataset.used) || 0;
            renderRow(row);
        }
        // Show/hide the "no slots" hint
        const anyVisible = Array.from(document.querySelectorAll('.ss-row'))
            .some(r => parseInt(r.dataset.total) > 0);
        const emptyMsg = document.getElementById('ss-empty-msg');
        if (emptyMsg) emptyMsg.style.display = anyVisible ? 'none' : '';
    }

    function syncSpellSlots(force) {
        const classEl = document.getElementById('class-select')
                     || document.querySelector('[name="class"]');
        const levelEl = document.querySelector('[name="level"]');
        if (!classEl || !levelEl) return;
        const className = classEl.value || '';
        const level = levelEl.value || 1;
        if (!className) return;
        // Only auto-fill when all totals are zero, unless triggered by a user interaction
        if (!force && !allTotalsZero()) return;
        applySpellSlots(getSpellSlots(className, level));
    }

    function allTotalsZero() {
        const rows = document.querySelectorAll('.ss-row');
        if (!rows.length) return false;
        return Array.from(rows).every(r => (parseInt(r.dataset.total) || 0) === 0);
    }

    // Expose globally so the Open5e init() can trigger after class select is populated
    window._syncSpellSlots = syncSpellSlots;

    // Wire up change events
    const classEl = document.getElementById('class-select');
    const levelEl = document.querySelector('[name="level"]');
    if (classEl) classEl.addEventListener('change', () => syncSpellSlots(true));
    if (levelEl) levelEl.addEventListener('change', () => syncSpellSlots(true));
    if (levelEl) levelEl.addEventListener('input',  () => syncSpellSlots(true));
})();
