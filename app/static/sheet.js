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
            const score = parseInt(inp.value) || 10;
            const mod   = Math.floor((score - 10) / 2);
            const sd = abCardView.querySelector('.ab-score-disp[data-ab="' + ab + '"]');
            const md = abCardView.querySelector('.ab-mod-disp[data-ab="' + ab + '"]');
            if (sd) sd.textContent = score;
            if (md) md.textContent = (mod >= 0 ? '+' : '') + mod;
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

// ── Open5e select dropdowns (class, subclass, race) ──
;(function () {
    const classSelect = document.getElementById('class-select');
    const subSelect   = document.getElementById('subclass-select');
    const raceSelect  = document.getElementById('race-select');
    if (!classSelect && !subSelect && !raceSelect) return;

    async function fetchList(url) {
        try {
            const r = await fetch(url);
            if (r.ok) return (await r.json()).results || [];
        } catch {}
        return [];
    }

    async function fetchDetailText(endpoint, slug) {
        if (!slug) return '';
        try {
            const r = await fetch(endpoint + '?slug=' + encodeURIComponent(slug));
            if (r.ok) return (await r.json()).text || '';
        } catch {}
        return '';
    }

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
            opt.textContent = item.name;
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
        const items = await fetchList('/api/open5e/subclasses?limit=100&class_slug=' + encodeURIComponent(slug));
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

    // Client-side fallback: parse a flat text blob into {intro, features}
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

        // Subclass name + flavor
        if (data.name) {
            const h = document.createElement('div');
            h.style.cssText = 'font-weight:700;font-size:14px;margin-bottom:4px;color:var(--fg,#e0e0e0);';
            h.textContent = data.name;
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

        // Race name heading
        if (data.name) {
            const h = document.createElement('div');
            h.style.cssText = 'font-weight:700;font-size:14px;margin-bottom:4px;color:var(--fg,#e0e0e0);';
            h.textContent = data.name;
            container.appendChild(h);
        }

        // Stat summary flavor block
        const cleanedFlavor = _cleanMd(flavor);
        if (cleanedFlavor) {
            const f = document.createElement('div');
            f.style.cssText = 'font-size:12px;color:#8a9;font-style:italic;margin-bottom:12px;line-height:1.55;border-left:2px solid #3a5a6a;padding-left:8px;';
            f.textContent = cleanedFlavor;
            container.appendChild(f);
        }

        function makeTraitCard(trait) {
            const card = document.createElement('div');
            card.style.cssText = 'margin-bottom:5px;border-radius:5px;overflow:hidden;border:1px solid #2e3250;';

            const hdr = document.createElement('div');
            hdr.style.cssText = 'display:flex;align-items:center;gap:8px;padding:7px 10px;background:#252c45;cursor:pointer;user-select:none;';

            const arrow = document.createElement('span');
            arrow.style.cssText = 'font-size:9px;color:#667;flex-shrink:0;transition:transform .15s;transform:rotate(-90deg);';
            arrow.textContent = '▼';
            hdr.appendChild(arrow);

            const nameSpan = document.createElement('span');
            nameSpan.style.cssText = 'font-size:12px;font-weight:600;color:#c8cce8;flex:1;';
            nameSpan.textContent = trait.name || 'Trait';
            hdr.appendChild(nameSpan);

            card.appendChild(hdr);

            if (trait.desc) {
                const body = document.createElement('div');
                body.style.cssText = 'display:none;padding:10px 12px;font-size:12px;line-height:1.65;color:#b0b4cc;background:#191c2b;';
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
            wrap.style.cssText = 'background:#191c2b;border-radius:4px;padding:10px 12px;border:1px solid #2a2d3a;';
            cleanedFlavor.split('\n\n').forEach(function (para) {
                para = para.trim();
                if (!para) return;
                const p = document.createElement('p');
                p.style.cssText = 'margin:0 0 8px;font-size:12px;line-height:1.65;color:#b0b4cc;';
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
        const [classes, races] = await Promise.all([
            classSelect ? fetchList('/api/open5e/classes?limit=30') : Promise.resolve([]),
            raceSelect  ? fetchList('/api/open5e/races?limit=30')   : Promise.resolve([]),
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
                        fetch('/api/open5e/race-detail?slug=' + encodeURIComponent(rSlug))
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
                    const url = '/api/open5e/subclass-detail?slug=' + encodeURIComponent(subSlug)
                        + (classSlug ? '&class_slug=' + encodeURIComponent(classSlug) : '');
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
            const r = await fetch('/api/open5e/class-detail?slug=' + encodeURIComponent(slug));
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
            const url = '/api/open5e/subclass-detail?slug=' + encodeURIComponent(subSlug)
                + (classSlug ? '&class_slug=' + encodeURIComponent(classSlug) : '');
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
                    const r = await fetch('/api/open5e/race-detail?slug=' + encodeURIComponent(slug));
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
            const url = '/api/open5e/subclass-detail?slug=' + encodeURIComponent(subSlug)
                + (classSlug ? '&class_slug=' + encodeURIComponent(classSlug) : '');
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

    const syncRaceBtn = document.getElementById('sync-race-btn');
    if (syncRaceBtn) {
        syncRaceBtn.addEventListener('click', async function () {
            const slug = selectedSlug(raceSelect) || (raceSelect && raceSelect.value.trim().toLowerCase().replace(/\s+/g, '-'));
            if (!slug) { setSyncMsg('sync-race-status', 'No race selected', '#e07070'); return; }
            syncRaceBtn.disabled = true; syncRaceBtn.textContent = '↻ Syncing…';
            try {
                const r = await fetch('/api/open5e/race-detail?slug=' + encodeURIComponent(slug));
                if (!r.ok) throw new Error('HTTP ' + r.status);
                const d = await r.json();
                const ta = document.querySelector('textarea[name="race_traits"]');
                if (ta && d.text) ta.value = d.text;
                renderRaceTraits(d);
                _saveRaceCache(d);
                setSyncMsg('sync-race-status', d.traits && d.traits.length ? '✓ Synced' : 'No traits found', d.traits && d.traits.length ? '#6cb' : '#e07070');
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

    // Lazy-loaded description cache: slug → desc string
    const descCache = {};
    let descsLoaded = false;
    async function loadDescs() {
        if (descsLoaded) return;
        descsLoaded = true; // set early to prevent parallel fetches
        try {
            const r = await fetch('/api/open5e/conditions');
            if (r.ok) {
                const data = await r.json();
                (data.results || []).forEach(c => { descCache[c.slug] = c.desc || ''; });
            }
        } catch {}
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
            await loadDescs();
            if (descBox) {
                if (openSlug === slug && descBox.style.display !== 'none') {
                    descBox.style.display = 'none';
                    openSlug = null;
                } else {
                    const desc = descCache[slug] || '';
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

// ── Spell slot auto-fill from class + level ──
;(function () {
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
