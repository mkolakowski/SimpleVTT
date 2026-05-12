/* Beast Picker — shared module for Wild Shape / Polymorph beast selection.
 *
 * Surfaces a modal overlay (see app/templates/_beast_picker_modal.html)
 * that searches Open5e creatures, filters by type=Beast + CR cap, and
 * POSTs the chosen beast to the backend transform endpoint.
 *
 * Used from:
 *   - The standalone D&D 5e sheet (sheet_dnd5e.html — Wild Shape /
 *     Polymorph buttons in the Class Resources fieldset)
 *   - The tabletop mini-sheet (tabletop.html — Wild Shape / Polymorph
 *     mini buttons in the player drawer)
 *
 * API:
 *   window.BeastPicker.open({
 *       campaignId:         123,
 *       characterId:        456,
 *       source:             'wild-shape' | 'polymorph',
 *       druidLevel:         5,             // 0 if not a druid
 *       isMoonDruid:        false,
 *       characterLevel:     5,             // total class levels (caps Polymorph)
 *       onSuccess:          () => location.reload(),   // optional, default = reload
 *       favorites:          [                          // optional
 *           {slug:'wolf', name:'Wolf', cr:'1/4', type:'Beast',
 *            size:'Medium', hp:11, ac:13, source:'SRD'},
 *           // legacy v0.38.0 bare slug strings also accepted; they
 *           // get backfilled on first open and re-persisted.
 *       ],
 *       onFavoritesChange:  (newList) => {},           // optional, called after persist
 *   });
 *
 * Favorites carry their full lite stat block so the "★ Favorites"
 * section renders WITHOUT any Open5e call when every entry is cached.
 * Bare-slug entries (legacy) trigger a single backfill fetch on open,
 * after which the resolved data is persisted via /sheet-fields so
 * subsequent opens are cache-hits even if Open5e is unreachable.
 * The ★ button on each row toggles favorite state — the picker
 * PATCHes the new list back and calls onFavoritesChange if supplied
 * so the caller can refresh any cached copy.
 *
 * The overlay is a singleton — only one instance per page. Both
 * sheet_dnd5e.html and tabletop.html `{% include %}` the modal partial
 * exactly once.
 */
;(function () {
    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({
            '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
        }[c]));
    }
    function _crStr(cr) {
        if (cr <= 0) return '0';
        if (cr < 1) return cr === 0.125 ? '1/8' : cr === 0.25 ? '1/4' : cr === 0.5 ? '1/2' : String(cr);
        return String(cr);
    }
    function _parseCr(raw) {
        if (raw == null) return 0;
        const s = String(raw).trim();
        if (!s) return 0;
        if (s.includes('/')) {
            const [a, b] = s.split('/');
            return (parseFloat(b) > 0) ? parseFloat(a) / parseFloat(b) : 0;
        }
        return parseFloat(s) || 0;
    }
    function _wsCrCap(lv, moon) {
        const table = moon
            ? [[2,1],[4,2],[6,3],[8,4],[10,5],[12,6]]
            : [[2,0.25],[4,0.5],[8,1]];
        let cap = 0;
        for (const [reqLv, cr] of table) if (lv >= reqLv) cap = cr;
        return cap;
    }
    function _toast(msg, kind) {
        if (typeof window._toast === 'function') return window._toast(msg, kind);
        if (typeof window.showToast === 'function') return window.showToast(msg, kind);
        console.log('[BeastPicker]', msg);
    }

    // Lazy DOM lookups so the picker can be invoked before any inline
    // <script>s run (e.g. from sheet.js inside a stripped-script modal).
    function $(id) { return document.getElementById(id); }

    let _state = null;   // { opts, cap, results, selected }

    function _close() {
        const overlay = $('beast-picker-overlay');
        if (overlay) overlay.style.display = 'none';
        _state = null;
    }

    // Defensive coercion: Open5e v2 occasionally returns ``type``/``size``
    // as ``{key, name}`` dicts instead of strings (the server normalizes
    // these, but belt-and-braces here keeps the picker working if a
    // proxy mid-stream slips a raw v2 response through).
    function _str(v) {
        if (v == null) return '';
        if (typeof v === 'string') return v;
        if (typeof v === 'object') return String(v.name || v.key || '');
        return String(v);
    }

    function _rowHtml(r, isFavorite) {
        // Single row used by both the Favorites section at the top and
        // the live search results below it. The ★ button toggles
        // favorite state; ev.stopPropagation in the click handler keeps
        // it from also selecting the row.
        const starColor = isFavorite ? '#f7c948' : 'var(--s-mute)';
        const starGlyph = isFavorite ? '★' : '☆';
        const starTitle = isFavorite ? 'Unfavorite' : 'Favorite';
        // Campaign-authored homebrew rows carry ``is_custom: true`` from the
        // server. Render a tiny gold pill so GMs can tell at a glance which
        // entries came from their settings page vs. Open5e.
        const customBadge = r.is_custom
            ? `<span title="Campaign-authored homebrew" style="font-size:9px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:#d4a84a;background:#3a2f15;border:1px solid #6e5828;border-radius:3px;padding:0 4px;margin-left:5px;vertical-align:1px;">Custom</span>`
            : '';
        return `
            <div class="bp-row" data-slug="${_esc(r.slug)}"
                 style="padding:7px 14px;cursor:pointer;border-bottom:1px solid var(--s-border);display:flex;align-items:flex-start;gap:8px;">
                <button type="button" class="bp-fav" data-slug="${_esc(r.slug)}"
                        title="${starTitle}"
                        style="background:none;border:none;font-size:16px;color:${starColor};cursor:pointer;padding:0 2px;line-height:1;flex-shrink:0;margin-top:1px;">${starGlyph}</button>
                <div style="flex:1;min-width:0;">
                    <div style="font-size:12px;font-weight:700;color:var(--s-fg);">${_esc(r.name)}${customBadge}</div>
                    <div style="font-size:10px;color:var(--s-mute);">CR ${_esc(r.cr || '0')} · ${_esc(_str(r.size))} ${_esc(_str(r.type))}</div>
                </div>
            </div>
        `;
    }

    function _sectionHeader(label) {
        return `<div style="padding:5px 14px;font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--s-mute);background:var(--s-input);border-bottom:1px solid var(--s-border);text-transform:uppercase;">${_esc(label)}</div>`;
    }

    function _renderList() {
        const listPanel = $('bp-list-panel');
        if (!listPanel || !_state) return;
        const free = $('bp-free-pick').checked;
        const all = _state.results || [];
        const favSet = _state.favorites || new Set();
        // Client-side name filter as a safety net — the server already
        // forwards ``name__icontains`` to Open5e v2, but if the upstream
        // API ever drops or renames that filter we still want the picker
        // to narrow results to what the user typed. Also handy when Free
        // pick is on (we want the search term to still narrow the type-
        // unfiltered list).
        const qLower = String(_state.lastQuery || '').toLowerCase();
        const filtered = all.filter(r => {
            if (qLower && !String(r.name || '').toLowerCase().includes(qLower)) return false;
            if (free) return true;
            if (_str(r.type).toLowerCase() !== 'beast') return false;
            if (_parseCr(r.cr) > _state.cap) return false;
            return true;
        });

        // Favorites that also match the current search term — keeps the
        // top section relevant when the user has many favorites and is
        // typing to narrow.
        const favResults = (_state.favoriteResults || []).filter(r => {
            if (!qLower) return true;
            return String(r.name || '').toLowerCase().includes(qLower);
        });

        // Always surface a count so users understand whether the API is
        // returning data (and how aggressively the type/CR filter is
        // chopping). The total reported by the API can be far larger
        // than what we fetched; show the page size honestly.
        const statusEl = $('bp-status');
        if (statusEl) {
            const total = _state.totalCount || all.length;
            const shown = filtered.length;
            const favCount = favResults.length;
            const favPart = favCount ? `★ ${favCount} favorite${favCount === 1 ? '' : 's'} · ` : '';
            statusEl.textContent = free
                ? `${favPart}${shown} of ${all.length} on this page (${total} total) — free pick`
                : `${favPart}${shown} of ${all.length} on this page match the beast / CR filter`;
        }

        const sections = [];
        if (favResults.length) {
            sections.push(_sectionHeader('★ Favorites'));
            sections.push(favResults.map(r => _rowHtml(r, true)).join(''));
        }
        if (filtered.length) {
            if (favResults.length) sections.push(_sectionHeader(qLower ? 'Other matches' : 'All beasts'));
            sections.push(filtered.map(r => _rowHtml(r, favSet.has(r.slug))).join(''));
        }
        if (!sections.length) {
            const hint = free
                ? 'API returned an empty page — try a different search term.'
                : `No beasts within your CR cap on this page. Try a search term, or enable Free pick to bypass the filter.`;
            listPanel.innerHTML = `<div style="padding:14px;color:var(--s-mute);font-size:12px;">${hint}</div>`;
            return;
        }
        listPanel.innerHTML = sections.join('');
    }

    function _findInState(slug) {
        // Selection can come from either the Favorites section or the
        // live search results, so look in both lists.
        const inResults = (_state?.results || []).find(r => r.slug === slug);
        if (inResults) return inResults;
        return (_state?.favoriteResults || []).find(r => r.slug === slug);
    }

    function _renderDetail(slug) {
        const detail = $('bp-detail-panel');
        if (!detail || !_state) return;
        const m = _findInState(slug);
        if (!m) return;
        _state.selected = m;
        $('bp-confirm-btn').disabled = false;
        const free = $('bp-free-pick').checked;
        const typeOk = _str(m.type).toLowerCase() === 'beast';
        const crOk   = _parseCr(m.cr) <= _state.cap;
        let warn = '';
        if (!free) {
            if (!typeOk) warn = `<div style="padding:8px 10px;margin-top:6px;background:var(--s-err-bg);border:1px solid var(--s-danger);color:var(--s-err-fg);border-radius:5px;font-size:11px;">⚠ Not a beast — enable Free pick to override.</div>`;
            else if (!crOk) warn = `<div style="padding:8px 10px;margin-top:6px;background:var(--s-err-bg);border:1px solid var(--s-danger);color:var(--s-err-fg);border-radius:5px;font-size:11px;">⚠ CR ${m.cr} exceeds your cap of ${_crStr(_state.cap)} — enable Free pick to override.</div>`;
        }
        const isPoly = _state.opts.source === 'polymorph';
        detail.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;">
                <h3 style="margin:0;font-size:18px;color:var(--s-fg);">${_esc(m.name)}</h3>
                <span style="font-size:12px;color:var(--s-mute);">CR ${_esc(m.cr || '0')}</span>
            </div>
            <div style="font-size:11px;color:var(--s-mute);margin-top:2px;">${_esc(_str(m.size))} ${_esc(_str(m.type))}</div>
            <div style="display:flex;gap:14px;margin-top:10px;flex-wrap:wrap;font-size:12px;color:var(--s-fg);">
                <span><strong>HP</strong> ${_esc(m.hp ?? '?')}</span>
                <span><strong>AC</strong> ${_esc(m.ac ?? '?')}</span>
            </div>
            ${warn}
            <p style="font-size:11px;color:var(--s-mute);margin-top:10px;line-height:1.45;">
                On Transform, the server fetches the full stat block from Open5e and replaces your HP, AC, speed,
                ${isPoly ? '<strong>all ability scores</strong>' : 'STR / DEX / CON (keeps your INT / WIS / CHA)'},
                skills, saves, and attacks with the beast's. Your class features, spells, and inventory are preserved.
                Click <strong>Revert</strong> on the active-form banner to switch back.
            </p>
        `;
    }

    async function _runSearch() {
        if (!_state) return;
        const q = ($('bp-search').value || '').trim();
        _state.lastQuery = q;   // remembered so _renderList can name-filter locally
        const listPanel = $('bp-list-panel');
        listPanel.innerHTML = '<div style="padding:14px;color:var(--s-mute);font-size:12px;">Searching…</div>';

        // Push the type + CR filter to the server when Free pick is off,
        // so v2 returns a page of relevant matches instead of 50 random
        // creatures most of which would fail our client-side filter.
        const free = $('bp-free-pick')?.checked;
        const params = new URLSearchParams();
        params.set('search', q);
        params.set('limit', '50');
        if (!free) {
            params.set('type_filter', 'beast');
            if (_state.cap && _state.cap > 0) {
                params.set('cr_max', _crStr(_state.cap));
            }
        }

        try {
            // Thread campaign id through so homebrew monsters merge into
            // the response (server-side dedupes any slug collision).
            if (_state.opts && _state.opts.campaignId) {
                params.set('campaign_id', _state.opts.campaignId);
            }
            const resp = await fetch(`/api/open5e/monsters?${params.toString()}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            _state.results = data.results || [];
            _state.totalCount = data.count || 0;
            _renderList();
        } catch (e) {
            listPanel.innerHTML = `<div style="padding:14px;color:var(--s-danger);font-size:12px;">Error: ${e.message}</div>`;
            const statusEl = $('bp-status');
            if (statusEl) statusEl.textContent = '';
        }
    }

    async function _confirm() {
        if (!_state || !_state.selected) return;
        const { opts, selected } = _state;
        $('bp-confirm-btn').disabled = true;
        $('bp-status').textContent = 'Transforming…';
        try {
            const resp = await fetch(`/api/campaign/${opts.campaignId}/character/${opts.characterId}/transform`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    slug: selected.slug,
                    source: opts.source,
                    free_pick: $('bp-free-pick').checked,
                }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: 'Transform failed' }));
                throw new Error(err.detail || err.error || `HTTP ${resp.status}`);
            }
            // Default behaviour: reload the page so all stats re-render.
            // Callers can override via onSuccess (e.g. mini-sheet partial refresh).
            if (typeof opts.onSuccess === 'function') {
                opts.onSuccess();
            } else {
                window.location.reload();
            }
            _close();
        } catch (e) {
            $('bp-status').textContent = '';
            _toast('Transform failed: ' + e.message, 'error');
            $('bp-confirm-btn').disabled = false;
        }
    }

    // True when a favorite entry has enough fields cached locally that
    // the picker can render its row without an Open5e call.
    function _favHasCache(fav) {
        return !!(fav && fav.slug && fav.name && fav.cr != null);
    }

    async function _persistFavorites() {
        if (!_state) return;
        const url = _state.opts.campaignId
            ? `/api/campaign/${_state.opts.campaignId}/character/${_state.opts.characterId}/sheet-fields`
            : `/api/character/${_state.opts.characterId}/sheet-fields`;
        const payload = _state.favoritesArray.map(fav => ({ ...fav }));
        try {
            await fetch(url, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ favorite_beasts: payload }),
            });
        } catch { /* keep local state; next open will repopulate from server */ }
        if (typeof _state.opts.onFavoritesChange === 'function') {
            try { _state.opts.onFavoritesChange(payload); }
            catch { /* swallow listener errors */ }
        }
    }

    async function _toggleFavorite(slug) {
        if (!slug || !_state) return;
        const isFav = _state.favorites.has(slug);
        if (isFav) {
            // Remove from the slug-set, the order-preserving array, AND
            // the render cache so the ★ Favorites section refreshes.
            _state.favorites.delete(slug);
            _state.favoritesArray = _state.favoritesArray.filter(f => f.slug !== slug);
            _state.favoriteResults = (_state.favoriteResults || []).filter(r => r.slug !== slug);
            _renderList();
            await _persistFavorites();
            return;
        }
        // Add. Snapshot the lite shape from whichever source already has
        // it: the row the user just starred (in the current search
        // results), or the matching detail panel data. Falling back to
        // a fetch is a last resort — every starred creature SHOULD be
        // cached so we never re-fetch on subsequent opens.
        const fromResults = (_state.results || []).find(r => r.slug === slug);
        let liteShape = fromResults
            ? { slug: fromResults.slug, name: fromResults.name, cr: fromResults.cr,
                type: fromResults.type, size: fromResults.size,
                hp: fromResults.hp, ac: fromResults.ac, source: fromResults.source }
            : { slug };

        _state.favorites.add(slug);
        _state.favoritesArray = [..._state.favoritesArray, liteShape];
        if (_favHasCache(liteShape)) {
            _state.favoriteResults = [...(_state.favoriteResults || []), liteShape];
            _renderList();
        } else {
            // Don't have cache yet (e.g. user starred while Free pick was
            // on and the row's data was minimal). Render immediately for
            // visual feedback, then try to backfill.
            _renderList();
            try {
                const _cid = (_state.opts && _state.opts.campaignId) ? _state.opts.campaignId : '';
                const _cQ = _cid ? `?campaign_id=${_cid}` : '';
                const resp = await fetch(`/api/open5e/creature/${encodeURIComponent(slug)}${_cQ}`);
                if (resp.ok) {
                    const lite = await resp.json();
                    // Replace the placeholder entry in the saved array
                    // and the render cache with the fully-cached version.
                    _state.favoritesArray = _state.favoritesArray.map(f =>
                        f.slug === slug ? { ...f, ...lite } : f);
                    _state.favoriteResults = [...(_state.favoriteResults || []), lite];
                    _renderList();
                }
            } catch { /* offline — slug is recorded; render shows just the slug name */ }
        }
        await _persistFavorites();
    }

    async function _fetchFavorites() {
        if (!_state) return;
        const favs = _state.favoritesArray || [];
        // First pass: anything with a complete cache renders immediately
        // from local data — zero Open5e calls for the common case.
        _state.favoriteResults = favs.filter(_favHasCache).map(f => ({ ...f }));
        _renderList();

        // Second pass: backfill any cache-misses (legacy slug-only
        // entries from before v0.39.0). Each missing entry triggers one
        // /api/open5e/creature/{slug} call. Failures (Open5e down,
        // creature removed upstream) are tolerated — those entries just
        // render with their slug as the label.
        const misses = favs.filter(f => !_favHasCache(f));
        if (!misses.length) return;
        const _cid = (_state.opts && _state.opts.campaignId) ? _state.opts.campaignId : '';
        const _cQ = _cid ? `?campaign_id=${_cid}` : '';
        const fetched = await Promise.all(misses.map(f =>
            fetch(`/api/open5e/creature/${encodeURIComponent(f.slug)}${_cQ}`)
                .then(r => r.ok ? r.json() : null)
                .catch(() => null)
        ));
        let anyBackfilled = false;
        misses.forEach((f, idx) => {
            const lite = fetched[idx];
            if (!lite) return;
            // Merge fetched data into the slugs entry inside favoritesArray
            _state.favoritesArray = _state.favoritesArray.map(orig =>
                orig.slug === f.slug ? { ...orig, ...lite } : orig);
            anyBackfilled = true;
        });
        if (anyBackfilled) {
            _state.favoriteResults = _state.favoritesArray
                .filter(_favHasCache)
                .map(f => ({ ...f }));
            _renderList();
            // Persist so the next open is cache-hit even if Open5e is
            // unavailable later.
            await _persistFavorites();
        } else {
            // No backfill possible but still render any slug-only rows
            // so the user sees their favorites (with slug as label).
            _state.favoriteResults = _state.favoritesArray.map(f => ({
                slug: f.slug,
                name: f.name || f.slug,
                cr: f.cr ?? '?',
                type: f.type || '',
                size: f.size || '',
                hp: f.hp, ac: f.ac, source: f.source,
            }));
            _renderList();
        }
    }

    function _bindOnce() {
        const overlay = $('beast-picker-overlay');
        if (!overlay || overlay._bpBound) return;
        overlay._bpBound = true;

        overlay.addEventListener('click', (ev) => {
            // ★ Favorite toggle — must intercept before the row-select
            // handler so a star click doesn't also pick the beast.
            const favBtn = ev.target.closest('.bp-fav');
            if (favBtn) {
                ev.stopPropagation();
                _toggleFavorite(favBtn.dataset.slug);
                return;
            }
            const row = ev.target.closest('.bp-row');
            if (row) {
                overlay.querySelectorAll('.bp-row').forEach(r => r.style.background = '');
                row.style.background = 'var(--accent-bg2, rgba(99,102,241,.12))';
                _renderDetail(row.dataset.slug);
            }
        });
        $('bp-close-btn')?.addEventListener('click', _close);
        $('bp-search-btn')?.addEventListener('click', _runSearch);
        $('bp-search')?.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') { ev.preventDefault(); _runSearch(); }
        });
        $('bp-free-pick')?.addEventListener('change', () => {
            // Re-query the server when the filter mode changes — with
            // Free pick OFF we want only beasts within the CR cap, and
            // when it's ON we want everything (Open5e ignores the
            // ``type__key`` / ``cr__lte`` params we drop). Re-rendering
            // the existing local list wouldn't broaden the set since the
            // server already trimmed it.
            _runSearch();
            if (_state?.selected) _renderDetail(_state.selected.slug);
        });
        $('bp-confirm-btn')?.addEventListener('click', _confirm);

        // Dismiss on backdrop click
        overlay.addEventListener('click', (ev) => {
            if (ev.target === overlay) _close();
        });
    }

    window.BeastPicker = {
        open(opts) {
            opts = opts || {};
            if (!opts.campaignId || !opts.characterId) {
                console.warn('BeastPicker.open: campaignId + characterId required');
                return;
            }
            const overlay = $('beast-picker-overlay');
            if (!overlay) {
                console.warn('BeastPicker: modal partial not present on this page');
                return;
            }
            _bindOnce();

            const source = opts.source === 'polymorph' ? 'polymorph' : 'wild-shape';
            const druidLv = parseInt(opts.druidLevel, 10) || 0;
            const isMoon = !!opts.isMoonDruid;
            const charLv = parseInt(opts.characterLevel, 10) || 1;
            const cap = source === 'wild-shape'
                ? _wsCrCap(druidLv, isMoon)
                : Math.max(0, charLv / 4);

            // Coerce favorites: caller can pass an array of slug strings
            // (legacy v0.38.0 shape) or objects ``{slug, name, cr, …}``
            // (v0.39.0+). Both normalize to objects so the rest of the
            // picker only deals with one shape. Entries without a usable
            // slug are dropped silently.
            const favArr = Array.isArray(opts.favorites)
                ? opts.favorites.map(f => {
                    if (typeof f === 'string') {
                        const s = f.trim();
                        return s ? { slug: s } : null;
                    }
                    if (f && typeof f === 'object' && typeof f.slug === 'string' && f.slug.trim()) {
                        return { ...f, slug: f.slug.trim() };
                    }
                    return null;
                }).filter(Boolean)
                : [];
            _state = {
                opts: { ...opts, source },
                cap,
                results: [],
                selected: null,
                lastQuery: '',
                favorites: new Set(favArr.map(f => f.slug)),
                favoritesArray: favArr,
                favoriteResults: [],
            };

            const titleEl = $('bp-title');
            if (titleEl) titleEl.textContent = source === 'polymorph'
                ? '🦌 Choose a Beast (Polymorph)'
                : '🐺 Choose a Beast (Wild Shape)';
            const capEl = $('bp-cap-text');
            if (capEl) {
                if (source === 'wild-shape') {
                    capEl.innerHTML = druidLv >= 2
                        ? `Druid Lv ${druidLv}${isMoon ? ' (Moon)' : ''} — max CR <strong>${_crStr(cap)}</strong>. Type must be Beast.`
                        : `Druid level 2+ required. Enable <strong>Free pick</strong> to override.`;
                } else {
                    capEl.innerHTML = `Polymorph: target CR ≤ <strong>${_crStr(cap)}</strong> (your level ${charLv} ÷ 4). Type must be Beast.`;
                }
            }

            $('bp-search').value = '';
            // Placeholder shown briefly until the auto-search below resolves.
            $('bp-list-panel').innerHTML = '<div style="padding:14px;color:var(--s-mute);font-size:12px;">Loading beasts…</div>';
            $('bp-detail-panel').innerHTML = '<p style="color:var(--s-mute);font-size:13px;">Select a beast to see its stats.</p>';
            $('bp-free-pick').checked = false;
            $('bp-confirm-btn').disabled = true;
            $('bp-status').textContent = '';

            overlay.style.display = '';
            setTimeout(() => $('bp-search').focus(), 50);

            // Auto-populate the list with the first page of results so the
            // player can scroll immediately without typing — mirrors the
            // Spell Browser UX. An empty search returns the API's default
            // ordering; the type/CR cap filter narrows it to beasts the
            // character can actually transform into. Favorites are
            // fetched in parallel so the ★ section appears as soon as
            // possible — independent of the search response.
            _runSearch();
            _fetchFavorites();
        },
        close: _close,
    };
})();
