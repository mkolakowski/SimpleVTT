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
            let v;
            if (el.type === 'checkbox') v = el.checked;
            else if (el.type === 'number') v = el.value === '' ? 0 : Number(el.value);
            else v = el.value;

            if (n === 'inventory') {
                v = String(v).split('\n').map(s => s.trim()).filter(Boolean);
            } else if (n === 'attacks' && template === 'dnd5e') {
                v = String(v).split('\n').map(s => s.trim()).filter(Boolean).map(line => {
                    const [name, bonus, damage] = line.split('|').map(s => (s||'').trim());
                    return { name: name || '', bonus: bonus || '', damage: damage || '' };
                });
            } else if (n === 'spells' && template === 'dnd5e') {
                v = String(v).split('\n').map(s => s.trim()).filter(Boolean).map(line => {
                    const [name, level, description] = line.split('|').map(s => (s||'').trim());
                    return { name: name || '', level: level || '', description: description || '' };
                });
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
        const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/character/${charId}`, {
            method: 'POST',
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

    function wireDnd5eRollButtons(form) {
        form.querySelectorAll('.roll-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                let expr = '';
                let note = '';
                const prof = Number(readField(form, 'proficiency_bonus') || 2);

                if (btn.dataset.rollAbility) {
                    const ab = btn.dataset.rollAbility;
                    const mod = abilityModifier(readField(form, `abilities.${ab}`));
                    expr = `1d20${formatBonus(mod)}`;
                    note = `${ab} check`;
                } else if (btn.dataset.rollSave) {
                    const ab = btn.dataset.rollSave;
                    const mod = abilityModifier(readField(form, `abilities.${ab}`));
                    const isProf = !!readField(form, `saving_throws.${ab}`);
                    const total = mod + (isProf ? prof : 0);
                    expr = `1d20${formatBonus(total)}`;
                    note = `${ab} save${isProf ? ' (prof)' : ''}`;
                } else if (btn.dataset.rollSkill) {
                    const skill = btn.dataset.rollSkill;
                    const ab = btn.dataset.skillAbility;
                    const mod = abilityModifier(readField(form, `abilities.${ab}`));
                    const isProf = !!readField(form, `skills.${skill}.proficient`);
                    const isExp  = !!readField(form, `skills.${skill}.expertise`);
                    let bonus = 0;
                    if (isExp) bonus = prof * 2;
                    else if (isProf) bonus = prof;
                    expr = `1d20${formatBonus(mod + bonus)}`;
                    note = `${skill}${isExp ? ' (expertise)' : isProf ? ' (prof)' : ''}`;
                }

                if (!expr) return;
                if (typeof CAMPAIGN_ID === 'undefined') return;
                const visEl = document.getElementById('roll-vis');
                const visibility = visEl ? visEl.value : 'public';
                const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/roll`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ expression: expr, visibility, note }),
                });
                if (!resp.ok) {
                    const txt = await resp.text();
                    alert('Roll failed: ' + txt);
                }
                // Result will appear in the roll log via the WebSocket broadcast.
            });
        });
    }
})();
