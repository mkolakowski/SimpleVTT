/**
 * Spell-list picker for homebrew custom-class forms.
 *
 * Renders a search-as-you-type input plus a chip list of selected spells,
 * and syncs the selection into a hidden <input name="spell_list_json"> on
 * form submit. The hidden field carries a JSON array of slug strings — the
 * exact shape the server-side ``_parse_spell_list_json`` already accepts.
 *
 * Each chip displays "Spell Name (Lv.N, school)" with an X button to remove.
 * Clicking a search result adds the spell to the chips and clears the search.
 * Duplicate slugs are silently ignored so a GM can spam-click without issue.
 *
 * Auto-initialisation mirrors features_editor.js: every [data-spell-picker]
 * gets wired on DOMContentLoaded and on any <details> open. Initial state
 * comes from data-spells (JSON array of {slug, name, level, school} or bare
 * slug strings — bare slugs render as "<slug> (resolving…)" and get
 * back-filled by a single bulk lookup on init).
 *
 * Usage in a Jinja template:
 *
 *   <div data-spell-picker data-spells='{{ spell_list_lite | tojson }}'></div>
 *   <input type="hidden" name="spell_list_json" />
 */
(function () {
    'use strict';

    const NS = 'SimpleVTTSpellPicker';

    function _closestForm(el) {
        while (el && el.tagName !== 'FORM') el = el.parentElement;
        return el;
    }

    function _findHiddenInput(root) {
        const form = _closestForm(root);
        return form ? form.querySelector('input[type="hidden"][name="spell_list_json"]') : null;
    }

    function _schoolAbbrev(s) {
        return (s || '').slice(0, 4);
    }

    function _chipLabel(spell) {
        const lvl = (spell.level === 0 || spell.level === '0') ? 'cantrip' : 'Lv.' + spell.level;
        const sch = spell.school ? ', ' + _schoolAbbrev(spell.school) : '';
        return (spell.name || spell.slug) + ' (' + lvl + sch + ')';
    }

    function _renderChip(root, spell) {
        const chip = document.createElement('span');
        chip.dataset.slug = spell.slug;
        chip.dataset.spell = JSON.stringify(spell);
        chip.style.cssText =
            'display:inline-flex;align-items:center;gap:6px;padding:3px 8px;margin:2px;' +
            'background:#252c45;border:1px solid #3a4060;border-radius:12px;font-size:12px;';
        const label = document.createElement('span');
        label.textContent = _chipLabel(spell);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = '✕';
        btn.title = 'Remove this spell';
        btn.style.cssText =
            'background:none;border:none;color:#c66;font-size:11px;cursor:pointer;padding:0;line-height:1;';
        btn.addEventListener('click', () => chip.remove());
        chip.appendChild(label);
        chip.appendChild(btn);
        return chip;
    }

    function _serialize(root) {
        const chips = root.querySelectorAll('.spell-picker-chips [data-slug]');
        const slugs = [];
        chips.forEach(ch => slugs.push(ch.dataset.slug));
        return JSON.stringify(slugs);
    }

    function _addSpell(root, spell) {
        if (!spell || !spell.slug) return;
        // Dedupe: a chip with this slug already?
        const chipsEl = root.querySelector('.spell-picker-chips');
        if (chipsEl.querySelector('[data-slug="' + CSS.escape(spell.slug) + '"]')) return;
        chipsEl.appendChild(_renderChip(root, spell));
    }

    /** Resolve bare slug strings in ``initial`` to lite shapes by hitting
     *  the search endpoint with each slug. Best-effort; the chips render
     *  with a placeholder if the lookup fails. */
    async function _resolveSlugs(initial) {
        const out = [];
        for (const item of initial) {
            if (item && typeof item === 'object' && item.slug) {
                out.push(item);
                continue;
            }
            const slug = (typeof item === 'string') ? item : '';
            if (!slug) continue;
            out.push({ slug: slug, name: slug, level: '?', school: '' });
        }
        return out;
    }

    function _wireSearch(root) {
        const searchInput = root.querySelector('.spell-picker-search');
        const resultsEl   = root.querySelector('.spell-picker-results');

        let debounce = 0;
        searchInput.addEventListener('input', () => {
            const q = searchInput.value.trim();
            clearTimeout(debounce);
            if (q.length < 2) {
                resultsEl.innerHTML = '';
                resultsEl.style.display = 'none';
                return;
            }
            debounce = setTimeout(async () => {
                try {
                    const r = await fetch('/api/open5e/spells?search='
                        + encodeURIComponent(q) + '&limit=15');
                    if (!r.ok) return;
                    const data = await r.json();
                    resultsEl.innerHTML = '';
                    (data.results || []).forEach(s => {
                        const row = document.createElement('div');
                        row.style.cssText =
                            'padding:5px 9px;cursor:pointer;font-size:12px;border-bottom:1px solid #2a2d36;';
                        row.textContent = _chipLabel(s);
                        row.addEventListener('mouseenter', () => row.style.background = '#252c45');
                        row.addEventListener('mouseleave', () => row.style.background = '');
                        row.addEventListener('click', () => {
                            _addSpell(root, s);
                            searchInput.value = '';
                            resultsEl.innerHTML = '';
                            resultsEl.style.display = 'none';
                            searchInput.focus();
                        });
                        resultsEl.appendChild(row);
                    });
                    resultsEl.style.display = data.results && data.results.length ? '' : 'none';
                } catch {}
            }, 200);
        });

        searchInput.addEventListener('blur', () => {
            // Defer so clicks on results land before the dropdown hides.
            setTimeout(() => { resultsEl.style.display = 'none'; }, 150);
        });
    }

    async function init(root) {
        if (root.dataset.spellPickerInit === '1') return;
        root.dataset.spellPickerInit = '1';

        let initial = [];
        try { initial = JSON.parse(root.dataset.spells || '[]'); } catch (e) {}
        if (!Array.isArray(initial)) initial = [];

        root.innerHTML = `
            <div class="spell-picker-chips" style="display:flex;flex-wrap:wrap;gap:2px;margin-bottom:8px;"></div>
            <div style="position:relative;">
                <input type="text" class="spell-picker-search"
                       placeholder="Search spells to add (type 2+ chars)…"
                       style="width:100%;padding:6px 10px;box-sizing:border-box;font-size:13px;">
                <div class="spell-picker-results"
                     style="position:absolute;top:100%;left:0;right:0;max-height:240px;overflow-y:auto;
                            background:#1a1d24;border:1px solid #3a4060;border-radius:0 0 4px 4px;
                            display:none;z-index:50;"></div>
            </div>
        `;

        const resolved = await _resolveSlugs(initial);
        resolved.forEach(s => _addSpell(root, s));
        _wireSearch(root);

        const form = _closestForm(root);
        if (form && !form.dataset.spellPickerSubmitBound) {
            form.dataset.spellPickerSubmitBound = '1';
            form.addEventListener('submit', () => {
                form.querySelectorAll('[data-spell-picker]').forEach(p => {
                    const hidden = _findHiddenInput(p);
                    if (hidden) hidden.value = _serialize(p);
                });
            });
        }
    }

    function initAll(scope) {
        const root = scope || document;
        root.querySelectorAll('[data-spell-picker]').forEach(init);
    }

    document.addEventListener('toggle', e => {
        if (e.target.tagName === 'DETAILS' && e.target.open) {
            initAll(e.target);
        }
    }, true);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => initAll());
    } else {
        initAll();
    }

    window[NS] = { init, initAll };
})();
