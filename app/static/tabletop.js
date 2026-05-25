/* SimpleVTT tabletop client.
 *
 * Responsibilities:
 *  - Render the active map (image + grid) on a <canvas>.
 *  - Draw tokens; allow click+drag to move tokens you own (or all if GM).
 *  - Submit moves via POST /api/campaign/.../token/.../move.
 *  - Subscribe to a per-campaign WebSocket and apply token/roll updates from
 *    other clients without round-tripping back to the server.
 *  - Submit dice rolls and append them to the local roll list.
 *
 * State is kept in a flat tokens array keyed by id. Hex math uses pointy-top
 * orientation with grid_size_px treated as the hex height.
 */
(function () {
    'use strict';

    const canvas = document.getElementById('vtt-canvas');
    if (!canvas) return;

    const mapPane = document.getElementById('map-pane');
    const ctx = canvas.getContext('2d');

    // v2.3.45: HiDPI / Retina sharpness. The HTML template sets
    // ``width="{{ map.width_px }}"`` / ``height="…"`` on the canvas;
    // those attributes also size the backing store, so on a 2× display
    // every drawn pixel was being bilinearly upscaled by the browser —
    // visibly soft on the v2.3.44 token portraits. Capture the logical
    // map size before resizing, multiply the backing store by DPR, fix
    // the CSS display size to the logical map size, and ``ctx.scale``
    // so all draw calls keep using logical (CSS) coordinates. ``MAP_W``
    // / ``MAP_H`` replace every former ``canvas.width`` / ``canvas.height``
    // reference below — those would now return the backing-store size.
    const MAP_W = canvas.width;
    const MAP_H = canvas.height;
    const DPR = Math.max(1, window.devicePixelRatio || 1);
    canvas.width = MAP_W * DPR;
    canvas.height = MAP_H * DPR;
    canvas.style.width = MAP_W + 'px';
    canvas.style.height = MAP_H + 'px';
    ctx.scale(DPR, DPR);
    // ``high`` resampling matters for the demo-token portraits which
    // are sourced ~1000 px wide and rendered at ~70 px on canvas; the
    // browser default (``low``) makes that 14× downscale look mushy.
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    const initialData = JSON.parse(document.getElementById('initial-data').textContent);
    let tokens = initialData.tokens || [];
    const characters = initialData.characters || [];
    const charById = {};
    characters.forEach(c => { charById[c.id] = c; });
    const templates = initialData.templates || [];
    // Currently-editing encounter context for spawn-point UI. When an
    // encounter row's edit form is open AND use_spawn_points is enabled
    // AND the encounter's map_id matches the active MAP_ID, the panel
    // sets these via window.vttSetSpawnContext so the canvas renders
    // the marker pass + the click-to-set landing endpoint is wired to
    // the right encounter. Cleared on edit-form close.
    let spawnContext = null;   // { encounterId, spawns: {char_id_str: {x,y}}, mapId }
    let spawnArmingCharId = null;

    const gridType = canvas.dataset.gridType || 'square';
    const gridSize = parseInt(canvas.dataset.gridSize || '70', 10);
    // v2.4.0: per-map "show grid overlay" toggle. Defaults to true when
    // the attribute is missing (e.g. on legacy pages without the new
    // template field). ``gridType`` still drives snap-to-grid token
    // placement — turning the overlay off does NOT disable snapping.
    const showGrid = canvas.dataset.showGrid !== '0';
    const bgLayer = document.getElementById('map-bg-layer');

    // ---------- Hex helpers (pointy-top) ----------
    // Hex height = gridSize. Width = sqrt(3)/2 * height.
    function hexDims() {
        const h = gridSize;
        const w = Math.sqrt(3) / 2 * h;
        return { w, h };
    }

    function snapToGrid(x, y) {
        if (gridType === 'square') {
            const gx = Math.round(x / gridSize) * gridSize;
            const gy = Math.round(y / gridSize) * gridSize;
            return [gx, gy];
        }
        if (gridType === 'hex') {
            const { w, h } = hexDims();
            const rowH = h * 0.75;          // vertical step between rows
            const row = Math.round(y / rowH);
            const offsetX = (row % 2) * (w / 2);
            const col = Math.round((x - offsetX) / w);
            return [col * w + offsetX, row * rowH];
        }
        return [x, y];
    }

    // v2.49.72: snap a canvas point to the CENTER of the grid cell it
    // falls inside (vs. snapToGrid above, which returns the top-left
    // corner for square grids). Used by the ruler picker so both
    // committed points + the live cursor preview lock onto cell centers.
    // 5e RAW measures by squares so a "22.7 ft" reading from an
    // off-center click is misleading at a TTRPG table; snapping to
    // center yields clean integer-ft results (e.g. "20 ft") on square
    // grids. See docs/plans/ruler-and-range.md Phase 1 "Snap to grid
    // center" for the rationale.
    function _snapPointToGridCenter(x, y) {
        if (gridSize <= 0) return { x, y };
        if (gridType === 'square') {
            const cx = (Math.floor(x / gridSize) + 0.5) * gridSize;
            const cy = (Math.floor(y / gridSize) + 0.5) * gridSize;
            return { x: cx, y: cy };
        }
        if (gridType === 'hex') {
            // snapToGrid already returns the hex center for any pixel
            // inside a hex (hex layout has no "corner" sense the way
            // square cells do).
            const [hx, hy] = snapToGrid(x, y);
            return { x: hx, y: hy };
        }
        return { x, y };
    }

    // ---------- Rendering ----------
    function drawSquareGrid() {
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.lineWidth = 1;
        for (let x = 0; x < MAP_W; x += gridSize) {
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, MAP_H); ctx.stroke();
        }
        for (let y = 0; y < MAP_H; y += gridSize) {
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(MAP_W, y); ctx.stroke();
        }
    }

    function drawHexGrid() {
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.lineWidth = 1;
        const { w, h } = hexDims();
        const rowH = h * 0.75;
        const cols = Math.ceil(MAP_W / w) + 1;
        const rows = Math.ceil(MAP_H / rowH) + 1;
        for (let r = 0; r < rows; r++) {
            const offsetX = (r % 2) * (w / 2);
            for (let c = 0; c < cols; c++) {
                drawHex(c * w + offsetX, r * rowH, w, h);
            }
        }
    }

    function drawHex(cx, cy, w, h) {
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
            const angle = Math.PI / 180 * (60 * i - 30);
            const px = cx + (w / 2) * Math.cos(angle);
            const py = cy + (h / 2) * Math.sin(angle);
            if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        ctx.closePath();
        ctx.stroke();
    }

    /* v2.50.0 — grid coordinate labels (LetterNumber). Thin gutter
       strip along the top + left edges of the map drawn AFTER the
       grid + tokens so labels sit on top. Columns are letters
       (A, B, …, Z, AA, AB, …); rows are 1-indexed integers. Square
       grids only — hex coordinate systems are typically axial /
       offset coordinates (q,r) that don't map onto the same
       Letter/Number convention.

       Style: theme accent color for the glyph fill + a translucent
       dark backing strip (~24 px) so the labels stay legible on
       busy / light maps. The strip pans + zooms with the map (it's
       drawn in map coords) so "G7" always points at the same
       logical cell. */
    function _colLabel(idx) {
        // 0 → A, 25 → Z, 26 → AA, 27 → AB, …
        let s = '';
        let n = idx;
        while (n >= 0) {
            s = String.fromCharCode(65 + (n % 26)) + s;
            n = Math.floor(n / 26) - 1;
        }
        return s;
    }
    function _readThemeAccent() {
        // Read --accent off :root so the labels follow whichever
        // theme the user has active (dark = purple, sepia = warm
        // orange, forest = green, …). Falls back to the v1 purple
        // if the variable isn't resolvable (e.g. CSS not loaded yet).
        try {
            const v = getComputedStyle(document.documentElement)
                .getPropertyValue('--accent').trim();
            if (v) return v;
        } catch (_) {}
        return '#a78bfa';
    }
    function drawGridCoords() {
        if (gridType !== 'square') return;
        const cols = Math.ceil(MAP_W / gridSize);
        const rows = Math.ceil(MAP_H / gridSize);
        if (cols <= 0 || rows <= 0) return;
        const accent = _readThemeAccent();
        // Strip height scales with the grid so it stays visually
        // proportional on small (35 px) and large (140 px) grids.
        const stripH = Math.max(16, Math.min(28, Math.round(gridSize * 0.32)));
        const fontSize = Math.max(10, Math.round(stripH * 0.62));

        ctx.save();
        ctx.font = `600 ${fontSize}px system-ui, -apple-system, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        // v2.51.2 — unify all four backing strips to the top + left
        // recipe (dark backing + accent text) per the user request to
        // make the new borders match the existing ones. The v2.51.0
        // parchment-tan + dark-text variant is dropped in favor of a
        // single visual treatment that frames the map cleanly. Alpha
        // also dropped from 0.55 → 0.35 so the map color reads through
        // the gutter strips more clearly — the labels stay legible
        // because they're rendered in the theme accent color, which
        // is always selected to contrast with the canvas background.
        ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
        ctx.fillRect(0, 0, MAP_W, stripH);                          // top
        ctx.fillRect(0, 0, stripH, MAP_H);                          // left
        ctx.fillRect(MAP_W - stripH, 0, stripH, MAP_H);             // right
        ctx.fillRect(0, MAP_H - stripH, MAP_W, stripH);             // bottom

        // Theme-accent border lines separating each gutter from the
        // map body. Four strokes — one along the inside edge of each
        // strip — so the player sees a complete frame.
        ctx.strokeStyle = accent;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, stripH + 0.5);
        ctx.lineTo(MAP_W, stripH + 0.5);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(stripH + 0.5, 0);
        ctx.lineTo(stripH + 0.5, MAP_H);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(0, MAP_H - stripH - 0.5);
        ctx.lineTo(MAP_W, MAP_H - stripH - 0.5);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(MAP_W - stripH - 0.5, 0);
        ctx.lineTo(MAP_W - stripH - 0.5, MAP_H);
        ctx.stroke();

        // v2.50.5 — labels centered between the gridlines, NOT
        // offset by the perpendicular strip width. The gridlines that
        // drawSquareGrid() paints sit at x = 0, gridSize, 2*gridSize,
        // … (and the same in y). Each cell is the span between two
        // consecutive gridlines; the visual center of cell ``c`` is at
        // x = c*gridSize + gridSize/2. Anchoring labels there makes
        // each letter / number line up directly with its column /
        // row's gridlines on the map. The previous implementation
        // (+ stripH offset) shifted labels right/down by the gutter
        // width, leaving them between gridlines but off-by-one from
        // the cells they were supposed to label.
        //
        // v2.51.0 — alignment tweak: round each label's anchor point
        // to integer pixel coordinates BEFORE fillText so sub-pixel
        // canvas rendering doesn't leave A and 1 a fraction of a
        // pixel out of alignment with each other. With textBaseline
        // 'middle' the canvas uses font metrics to position the
        // glyph; the integer rounding stabilizes that across glyphs
        // with different visual heights (the cap-height of "A" vs.
        // the digit-height of "1").
        //
        // Edge case: when ``gridSize / 2 < stripH`` (very small grids),
        // the first column / row label would fall inside the
        // perpendicular gutter strip and be hidden behind its dark
        // backing. Skip drawing in that case so the user doesn't see
        // a half-clipped glyph in the corner.
        const stripHalf = Math.round(stripH / 2);
        // Top labels (accent color) — column letters.
        ctx.fillStyle = accent;
        for (let c = 0; c < cols; c++) {
            const x = Math.round(c * gridSize + gridSize / 2);
            if (x > MAP_W - stripH) break;            // clips into right gutter
            if (x < stripH) continue;                 // clips into left gutter
            ctx.fillText(_colLabel(c), x, stripHalf);
        }
        // Left labels (accent color) — row numbers.
        for (let r = 0; r < rows; r++) {
            const y = Math.round(r * gridSize + gridSize / 2);
            if (y > MAP_H - stripH) break;            // clips into bottom gutter
            if (y < stripH) continue;                 // clips into top gutter
            ctx.fillText(String(r + 1), stripHalf, y);
        }

        // v2.51.2 — right + bottom border lettering uses the SAME
        // accent color as the top + left labels (was dark text in
        // v2.51.0; unified per user request to keep the visual
        // treatment consistent across all four sides). `ctx.fillStyle`
        // is still set to `accent` from the top-label pass above, so
        // no re-set needed — the loop just reuses it.
        const rightX = MAP_W - stripHalf;
        const bottomY = MAP_H - stripHalf;
        // Right labels — row numbers, mirroring the left strip.
        for (let r = 0; r < rows; r++) {
            const y = Math.round(r * gridSize + gridSize / 2);
            if (y > MAP_H - stripH) break;
            if (y < stripH) continue;
            ctx.fillText(String(r + 1), rightX, y);
        }
        // Bottom labels — column letters, mirroring the top strip.
        for (let c = 0; c < cols; c++) {
            const x = Math.round(c * gridSize + gridSize / 2);
            if (x > MAP_W - stripH) break;
            if (x < stripH) continue;
            ctx.fillText(_colLabel(c), x, bottomY);
        }
        ctx.restore();
    }

    const _tokenImgCache = {};

    function _loadTokenImage(url) {
        if (_tokenImgCache[url]) return _tokenImgCache[url];
        const img = new Image();
        img.onload = render;
        img.src = url;
        _tokenImgCache[url] = img;
        return img;
    }

    // GIF token overlay — browsers won't advance GIF frames for off-screen or
    // canvas-drawn images. Instead we place real <img> elements in a div that
    // shares the canvas's pan/zoom transform; CSS border-radius clips them to
    // circles. The canvas still draws the colour-ring border on top.
    const _gifOverlay = document.getElementById('gif-token-overlay');
    const _gifImgMap  = {};   // token.id → <img>

    function _updateGifOverlay() {
        if (!_gifOverlay) return;
        const keep = new Set();
        tokens.forEach(t => {
            if (!ME.animateGifs || !t.image_url || !t.image_url.toLowerCase().includes('.gif')) return;
            if (t.is_hidden && !ME.isGm) return;
            keep.add(t.id);
            const cx = t.x + gridSize / 2;
            const cy = t.y + gridSize / 2;
            const r  = (gridSize * t.size) / 2 - 4;
            if (!_gifImgMap[t.id]) {
                const img = document.createElement('img');
                img.style.cssText = 'position:absolute;border-radius:50%;object-fit:cover;pointer-events:none;';
                _gifOverlay.appendChild(img);
                _gifImgMap[t.id] = img;
            }
            const img = _gifImgMap[t.id];
            if (img.src !== t.image_url) img.src = t.image_url;
            img.style.left    = (cx - r) + 'px';
            img.style.top     = (cy - r) + 'px';
            img.style.width   = (r * 2)  + 'px';
            img.style.height  = (r * 2)  + 'px';
            img.style.opacity = t.is_hidden ? '0.4' : '1';
        });
        Object.keys(_gifImgMap).forEach(id => {
            if (!keep.has(parseInt(id))) {
                _gifImgMap[id].remove();
                delete _gifImgMap[id];
            }
        });
    }

    // v2.21.0 Phase T.0: targeting state. Players double-click tokens on
    // the board to designate them as the target of their next attack /
    // spell / heal / check. Shift+double-click adds to a multi-target
    // selection (Magic Missile-style). Right-click (or touch long-press)
    // opens the target's character sheet — the gesture migrated off
    // double-click to make room. Escape clears.
    //
    // State lives client-side only. ``window._targetingState`` is the
    // public surface that the sheet's .atk-strike / .sp-cast / .cf-use
    // handlers will read in T.1 to attach target_combatant_id /
    // target_character_id / target_name to the POST body. T.2-T.4 then
    // teach the endpoints to compute hit / damage / heal application.
    const _targeting = {
        tokenIds: new Set(),  // canonical = token.id (numeric)

        setTarget(tokenId) {
            this.tokenIds.clear();
            this.tokenIds.add(tokenId);
            this._publish();
        },
        addTarget(tokenId) {  // Shift+dblclick — multi-target accumulation
            this.tokenIds.add(tokenId);
            this._publish();
        },
        toggleTarget(tokenId) {
            if (this.tokenIds.has(tokenId)) this.tokenIds.delete(tokenId);
            else this.tokenIds.add(tokenId);
            this._publish();
        },
        clear() {
            if (!this.tokenIds.size) return;
            this.tokenIds.clear();
            this._publish();
        },
        isTargeted(tokenId) { return this.tokenIds.has(tokenId); },

        // Resolve current target tokens to richer descriptors for the
        // sheet handlers. Each descriptor carries every selector the
        // server-side ``_resolve_target_combatant`` helper accepts so
        // the handler can pick whichever is set.
        getTargets() {
            const out = [];
            const battle = (window.battle && window.battle.combatants) || [];
            for (const tid of this.tokenIds) {
                const tok = tokens.find(t => t.id === tid);
                if (!tok) continue;
                let combatant = null;
                for (const c of battle) {
                    if (c.source_token_id != null && c.source_token_id === tid) { combatant = c; break; }
                    if (tok.character_id && c.char_id === tok.character_id) { combatant = c; break; }
                    if (tok.token_template_id
                            && c.token_template_id === tok.token_template_id
                            && c.name === tok.label) { combatant = c; break; }
                }
                out.push({
                    token_id: tid,
                    character_id: tok.character_id || null,
                    token_template_id: tok.token_template_id || null,
                    combatant_id: combatant ? combatant.id : null,
                    name: tok.label || (combatant && combatant.name) || 'Token',
                    color: tok.color || null,
                });
            }
            return out;
        },

        _publish() {
            try { render(); } catch (_) {}
            _updateTargetingChip();
            // v2.38.0 Phase T.9: refresh the token-tracker rows so
            // their 🎯 buttons reflect the current target state
            // (active = crimson, idle = neutral). Cheap because
            // renderTokenTracker is idempotent.
            try { renderTokenTracker(); } catch (_) {}
            // v2.22.0 Phase T.1: mirror the current targets into
            // localStorage so the full character sheet (which runs in
            // a separate page/iframe with its own ``window`` object)
            // can pick up the target before submitting an action. Key
            // namespaced by campaign so two campaigns open in different
            // tabs don't cross-contaminate. JSON.stringify the list so
            // the receiver can read structured ``{token_id, char_id,
            // combatant_id, name}`` descriptors without re-resolving.
            try {
                const targets = this.getTargets();
                const key = `simplevtt:targeting:${CAMPAIGN_ID}`;
                if (targets.length) {
                    localStorage.setItem(key, JSON.stringify(targets));
                } else {
                    localStorage.removeItem(key);
                }
            } catch (_) { /* localStorage may be disabled in private mode */ }
            try { document.dispatchEvent(new CustomEvent('vtt:targeting-change', { detail: this.getTargets() })); } catch (_) {}
        },
    };
    window._targetingState = _targeting;

    // v2.49.0 — persistent AoE markers for concentration spells.
    // Server populates this list via ``concentration_aoe_update``
    // broadcasts on /place_aoe for concentration AoEs, and clears
    // it when the caster's concentration ends. The canvas render
    // loop iterates this list and draws each marker on top of the
    // tokens with a translucent teal fill + dashed border to
    // distinguish from the bright-orange picker preview.
    let _concentrationAoes = [];

    // v2.44.1 Phase T.5b → v2.45.0 Phase T.6: AoE placement picker.
    // The sheet's ``.sp-cast`` handler calls ``window._openAoePicker(
    // {shape, size_ft, name, char_id})`` for spells whose action
    // carries a non-empty ``area`` block. The picker activates a
    // placement mode on the canvas: shape-specific mouse-follow
    // preview, click-to-place, Escape / right-click to cancel. On
    // placement, computes the set of token ids inside the shape and
    // resolves the returned Promise with ``{target_combatant_ids,
    // center}`` so the cast handler can submit the AoE multi-target
    // body the T.5a endpoint accepts.
    //
    // Standard D&D 5e: 1 grid square = 5 ft, so ``px_per_ft = gridSize
    // / 5``. Supported shapes:
    //   - ``sphere`` (T.5b): origin = cursor, radius = size_ft.
    //   - ``cone``   (T.6):  origin = caster's token center, axis =
    //                       direction(origin → cursor), length =
    //                       size_ft. PHB cone: width at distance d
    //                       equals d, i.e. half-angle = arctan(0.5)
    //                       ≈ 26.57°. Modelled as an isoceles triangle
    //                       from origin to the two far corners at
    //                       (axis * L + perp * L/2) and (axis * L -
    //                       perp * L/2), matching the printed cone
    //                       template; cleaner than a circular sector
    //                       for grid play.
    // v2.49.169: shared caster-token helpers. The picker modules
    // independently resolved "is this token the caster's token?" via
    // ``casterCharId`` lookups (PC-only). NPC casters (v2.49.163+)
    // need the parallel ``casterCombatantId`` path. Extracting these
    // two helpers means both _targetPicker and _aoePicker (and any
    // future picker) get NPC support uniformly. Same three-tier
    // resolution the picker.commit / _resolveOrigin paths already use.
    function _isCasterToken(token, casterCharId, casterCombatantId) {
        if (!token) return false;
        if (casterCharId && token.character_id === casterCharId) return true;
        if (casterCombatantId) {
            const battle = (window.battle && window.battle.combatants) || [];
            const comb = battle.find(c => c.id === casterCombatantId);
            if (comb) {
                if (comb.source_token_id != null && token.id === comb.source_token_id) {
                    return true;
                }
                if (comb.token_template_id != null
                        && token.token_template_id === comb.token_template_id
                        && token.label === comb.name) {
                    return true;
                }
            }
        }
        return false;
    }
    function _resolveCasterTokenPos(casterCharId, casterCombatantId) {
        if (casterCharId) {
            for (const t of tokens) {
                if (t.character_id === casterCharId) {
                    return { x: t.x + gridSize / 2, y: t.y + gridSize / 2 };
                }
            }
        }
        if (casterCombatantId) {
            const battle = (window.battle && window.battle.combatants) || [];
            const comb = battle.find(c => c.id === casterCombatantId);
            if (comb) {
                for (const t of tokens) {
                    if (_isCasterToken(t, 0, casterCombatantId)) {
                        return { x: t.x + gridSize / 2, y: t.y + gridSize / 2 };
                    }
                }
            }
        }
        return null;
    }

    const _aoePicker = {
        active: false,
        shape: '',
        size_ft: 0,
        secondary_ft: 0,
        spellName: '',
        casterCharId: 0,      // for self_sphere: filter caster out of target list
        casterCombatantId: '', // v2.49.169 — NPC casters (matches _targetPicker contract)
        range_ft: 0,          // v2.49.78 Phase 3A — spell range; 0 = skip ring + dim
        origin: null,         // { x, y } canvas coords — non-null for cone/line/self-sphere
        cursor: null,         // { x, y } canvas coords
        _resolve: null,       // promise resolver — null when inactive

        start(opts) {
            // Cancel any in-flight picker so back-to-back AoE casts
            // don't leak state.
            if (this.active) this.cancel();
            this.active = true;
            this.shape = String(opts.shape || 'sphere');
            this.size_ft = Number(opts.size_ft) || 0;
            this.secondary_ft = Number(opts.secondary_ft) || 0;
            this.spellName = String(opts.name || 'Spell');
            this.casterCharId = parseInt(opts.char_id, 10) || 0;
            // v2.49.169: NPC caster support — same combatant_id three-
            // tier lookup _targetPicker has used since v2.49.163.
            this.casterCombatantId = String(opts.combatant_id || opts.casterCombatantId || '');
            // v2.49.146: accept either range_ft (number) or range_str
            // ("120 feet" / "Self (15-ft radius)"), mirroring the
            // v2.49.143 _targetPicker contract. Callers from the sheet
            // typically have the raw string from _fetchSpellDetail;
            // callers from the post-cast Place AoE button have the
            // parsed int from the server's pending_aoe response.
            this.range_ft = Number(opts.range_ft) || 0;
            if (!this.range_ft && opts.range_str) {
                const _parsed = _parseRangeFtJS(opts.range_str);
                if (_parsed && _parsed > 0) this.range_ft = _parsed;
            }
            this.cursor = null;
            // Shapes that need an origin = caster's token resolve it
            // up-front. If we can't find a token for the casting
            // character (off-map / token not placed), bail with a
            // null resolve so the cast handler can surface an error.
            this.origin = null;
            if (this.shape === 'cone' || this.shape === 'line'
                    || this.shape === 'self_sphere' || this.shape === 'self_cube') {
                // v2.49.169: use the shared resolver so NPC casters
                // (combatant_id path) can also drive self-anchored
                // shapes — same logic _targetPicker uses for the ruler.
                this.origin = _resolveCasterTokenPos(this.casterCharId, this.casterCombatantId);
                if (!this.origin) {
                    this._cleanup();
                    return Promise.resolve(null);
                }
            }
            document.body.classList.add('aoe-picker-active');
            _showAoePickerHint(this.spellName, this.size_ft, this.shape, this.secondary_ft);
            try { render(); } catch (_) {}
            return new Promise((resolve) => { this._resolve = resolve; });
        },

        cancel() {
            if (!this.active) return;
            const resolve = this._resolve;
            this._cleanup();
            if (resolve) resolve(null);
        },

        commit(canvasX, canvasY) {
            if (!this.active) return;
            const resolve = this._resolve;
            const target_combatant_ids = [];
            const battle = (window.battle && window.battle.combatants) || [];
            const _resolveCombatant = (t) => {
                for (const c of battle) {
                    if (c.source_token_id != null && c.source_token_id === t.id) return c;
                    if (t.character_id && c.char_id === t.character_id) return c;
                    if (t.token_template_id
                            && c.token_template_id === t.token_template_id
                            && c.name === t.label) return c;
                }
                return null;
            };
            for (const t of tokens) {
                if (t.is_hidden && !ME.isGm) continue;
                // Self-anchored shapes never target the caster
                // themselves — Spirit Guardians, Antimagic Field,
                // Thunderwave etc. affect creatures "originating from"
                // or "around" the caster, which by RAW convention
                // excludes the caster. v2.49.169: NPC casters honored
                // via the shared _isCasterToken helper.
                if ((this.shape === 'self_sphere' || this.shape === 'self_cube')
                        && _isCasterToken(t, this.casterCharId, this.casterCombatantId)) {
                    continue;
                }
                if (!this._tokenInShape(t, canvasX, canvasY)) continue;
                const combatant = _resolveCombatant(t);
                if (combatant && combatant.id) {
                    target_combatant_ids.push(combatant.id);
                } else {
                    // v2.48.5 — no matching combatant (no active
                    // battle yet, or token added after init started).
                    // Pass the token id with a ``tok:`` prefix; the
                    // server's /place_aoe handler resolves it from
                    // the Token table and auto-adds an init entry so
                    // damage tracking works going forward.
                    target_combatant_ids.push(`tok:${t.id}`);
                }
            }
            this._cleanup();
            if (resolve) resolve({
                target_combatant_ids,
                center: { x: canvasX, y: canvasY },
            });
        },

        /** Shape-aware hit-test. ``(canvasX, canvasY)`` is the click
         *  position (cursor at commit time). */
        _tokenInShape(t, canvasX, canvasY) {
            const tcx = t.x + gridSize / 2;
            const tcy = t.y + gridSize / 2;
            const len_px = this._sizePx();
            if (this.shape === 'sphere') {
                return Math.hypot(tcx - canvasX, tcy - canvasY) <= len_px;
            }
            if (this.shape === 'cone' && this.origin) {
                const ox = this.origin.x, oy = this.origin.y;
                // Axis = direction from origin to cursor (unit vector).
                const adx = canvasX - ox, ady = canvasY - oy;
                const amag = Math.hypot(adx, ady);
                if (amag < 1) return false; // degenerate aim
                const ax = adx / amag, ay = ady / amag;
                // Token relative to origin, projected onto axis (par)
                // and perpendicular to axis (perp).
                const rx = tcx - ox, ry = tcy - oy;
                const par = rx * ax + ry * ay;
                const perp = Math.abs(rx * (-ay) + ry * ax);
                // PHB cone triangle: in-cone iff 0 ≤ par ≤ length and
                // perp ≤ par / 2 (half-width = half the axial distance).
                return par >= 0 && par <= len_px && perp <= par / 2;
            }
            if (this.shape === 'line' && this.origin) {
                // PHB line: rectangle from origin along aim axis with
                // fixed width = secondary_ft. In-line iff axial
                // component ∈ [0, length] and perpendicular ≤ width/2.
                const ox = this.origin.x, oy = this.origin.y;
                const adx = canvasX - ox, ady = canvasY - oy;
                const amag = Math.hypot(adx, ady);
                if (amag < 1) return false;
                const ax = adx / amag, ay = ady / amag;
                const rx = tcx - ox, ry = tcy - oy;
                const par = rx * ax + ry * ay;
                const perp = Math.abs(rx * (-ay) + ry * ax);
                const halfW = (this.secondary_ft / 5) * gridSize / 2;
                return par >= 0 && par <= len_px && perp <= halfW;
            }
            if (this.shape === 'cube') {
                // PHB cube ("within range"): axis-aligned square edge
                // = size_ft, centered on the cursor. In-cube iff
                // |tcx - cx| ≤ edge/2 AND |tcy - cy| ≤ edge/2.
                const half = len_px / 2;
                return Math.abs(tcx - canvasX) <= half
                    && Math.abs(tcy - canvasY) <= half;
            }
            if (this.shape === 'self_sphere' && this.origin) {
                // Self-centered emanation (Spirit Guardians, Antimagic
                // Field). Cursor doesn't move the center; the click
                // only serves as a confirmation. Caster IS in the
                // area but is filtered out below in the commit so the
                // PC doesn't roll a save against their own spell.
                return Math.hypot(tcx - this.origin.x, tcy - this.origin.y) <= len_px;
            }
            if (this.shape === 'self_cube' && this.origin) {
                // Self-anchored cube (Thunderwave): extends from the
                // caster's square in the cursor direction with edge =
                // size_ft. Math is identical to ``line`` but with
                // width = length (square cross-section). Half-width =
                // edge / 2.
                const ox = this.origin.x, oy = this.origin.y;
                const adx = canvasX - ox, ady = canvasY - oy;
                const amag = Math.hypot(adx, ady);
                if (amag < 1) return false;
                const ax = adx / amag, ay = ady / amag;
                const rx = tcx - ox, ry = tcy - oy;
                const par = rx * ax + ry * ay;
                const perp = Math.abs(rx * (-ay) + ry * ax);
                const halfW = len_px / 2;
                return par >= 0 && par <= len_px && perp <= halfW;
            }
            return false;
        },

        /** Resolve a {x, y} canvas-space origin for the caster's token.
         *  PC casters resolve by ``character_id``; NPC casters resolve
         *  by combatant_id → source_token_id / token_template_id+name.
         *  Kept as a thin wrapper for back-compat with existing callers
         *  that pass an integer char_id; the shared
         *  ``_resolveCasterTokenPos`` does the real work. */
        _resolveOrigin(charId) {
            return _resolveCasterTokenPos(parseInt(charId, 10) || 0, '');
        },

        _sizePx() {
            // 1 grid square = 5 ft by D&D 5e convention. The map
            // config doesn't carry a feet-per-square override today.
            return (this.size_ft / 5) * gridSize;
        },
        // Back-compat alias — earlier T.5b code used _radiusPx().
        _radiusPx() { return this._sizePx(); },

        _cleanup() {
            this.active = false;
            this.shape = '';
            this.size_ft = 0;
            this.secondary_ft = 0;
            this.spellName = '';
            this.casterCharId = 0;
            this.casterCombatantId = '';
            this.range_ft = 0;
            this.origin = null;
            this.cursor = null;
            this._resolve = null;
            document.body.classList.remove('aoe-picker-active');
            _hideAoePickerHint();
            try { render(); } catch (_) {}
        },
    };

    /** Convenience: feature-detected entry point that the sheet's
     *  cast handler calls. Always returns a Promise — never throws. */
    window._openAoePicker = function (opts) {
        if (!opts || !opts.size_ft) return Promise.resolve(null);
        return _aoePicker.start(opts);
    };

    // ──────────────────────────────────────────────────────────────────
    // v2.49.135 — Multi-target token picker (canvas-based crosshair).
    //
    // Pre-cast picker for multi-beam spells (Magic Missile, Scorching
    // Ray, Eldritch Blast at L5+). Modeled on _aoePicker but instead
    // of placing a shape, the player clicks each target token (allowing
    // stacking — clicking the same token N times puts N beams on it,
    // RAW PHB). Right-click decrements a token's count. Enter commits
    // (auto-commits when count === required). Esc cancels.
    //
    // Returns a Promise<Array<combatant_id>> where duplicates are
    // allowed for stacking (the server's existing target_combatant_ids
    // loop iterates per id, naturally resolving "3 beams on 1 bandit"
    // by passing the bandit's id three times).
    // ──────────────────────────────────────────────────────────────────
    const _targetPicker = {
        active: false,
        required: 0,
        spellName: '',
        casterCharId: 0,
        casterCombatantId: '', // v2.49.163 — NPC casters; resolved via window.battle.combatants
        casterPos: null,    // v2.49.138 — {x, y} canvas-space center of caster's token
        cursor: null,       // v2.49.138 — {x, y} snapped to grid-cell center; drives ruler endpoint
        cursorRaw: null,    // v2.49.140 — {x, y} raw cursor; drives hover-token preview ring
        rangeFt: 0,         // v2.49.143 — spell/attack range in feet; 0 = no range gating
        _justClosedAt: 0,   // v2.49.154 — ms timestamp of last cleanup; dblclick guard window
        picks: null,        // Map<token.id, count>
        _resolve: null,

        start(opts) {
            if (this.active) this.cancel();
            this.active = true;
            this.required = Math.max(1, parseInt(opts && opts.required, 10) || 1);
            this.spellName = String((opts && opts.spellName) || 'Spell');
            this.casterCharId = parseInt(opts && opts.casterCharId, 10) || 0;
            this.casterCombatantId = String((opts && opts.casterCombatantId) || '');
            // v2.49.138: resolve the caster's token center for the
            // ruler line. Mirrors _aoePicker._resolveOrigin (private —
            // re-walked here so the picker stays self-contained).
            // v2.49.163: PC casters resolve via character_id; NPC
            // casters resolve via combatant_id → window.battle, then
            // via the three-tier token lookup (source_token_id →
            // token_template_id+name).
            // v2.49.169: refactored to use the shared
            // _resolveCasterTokenPos helper. The old inline three-tier
            // resolution (PC by character_id, then NPC by combatant_id
            // → source_token_id / token_template_id+name) now lives in
            // one place so _aoePicker can use it too.
            this.casterPos = _resolveCasterTokenPos(
                this.casterCharId, this.casterCombatantId,
            );
            this.cursor = null;
            this.cursorRaw = null;
            // v2.49.143 — accept either a pre-parsed rangeFt OR a raw
            // range_str ("120 feet", "60 ft", "Self (15-ft radius)") so
            // callers can pass whichever is convenient. Self-cast (0)
            // and "Special" / null disable range gating.
            this.rangeFt = parseInt(opts && opts.rangeFt, 10) || 0;
            if (!this.rangeFt && opts && opts.rangeStr) {
                const _parsed = _parseRangeFtJS(opts.rangeStr);
                if (_parsed && _parsed > 0) this.rangeFt = _parsed;
            }
            this.picks = new Map();
            document.body.classList.add('target-picker-active');
            _showTargetPickerHint(this.spellName, 0, this.required);
            try { render(); } catch (_) {}
            return new Promise((resolve) => { this._resolve = resolve; });
        },

        cancel() {
            if (!this.active) return;
            const resolve = this._resolve;
            this._cleanup();
            if (resolve) resolve(null);
        },

        commit() {
            if (!this.active) return;
            const resolve = this._resolve;
            // Build the combatant-id list, repeating each entry per
            // the pick count. The server iterates this list per beam,
            // so [bandit, bandit, bandit] = 3 beams on the same bandit.
            const battle = (window.battle && window.battle.combatants) || [];
            const ids = [];
            for (const [tokenId, count] of this.picks) {
                const tok = tokens.find(t => t.id === tokenId);
                if (!tok) continue;
                let combatant = null;
                for (const c of battle) {
                    if (c.source_token_id != null && c.source_token_id === tok.id) { combatant = c; break; }
                    if (tok.character_id && c.char_id === tok.character_id) { combatant = c; break; }
                    if (tok.token_template_id
                            && c.token_template_id === tok.token_template_id
                            && c.name === tok.label) { combatant = c; break; }
                }
                const id = combatant && combatant.id ? combatant.id : `tok:${tok.id}`;
                for (let n = 0; n < count; n++) ids.push(id);
            }
            this._cleanup();
            if (resolve) resolve(ids);
        },

        addPick(canvasX, canvasY) {
            if (!this.active) return false;
            // Find the topmost token under the cursor.
            for (let i = tokens.length - 1; i >= 0; i--) {
                const t = tokens[i];
                if (t.is_hidden && !ME.isGm) continue;
                if (!pointInToken(canvasX, canvasY, t)) continue;
                const cur = this.picks.get(t.id) || 0;
                if (this._totalPicked() >= this.required) return false;
                this.picks.set(t.id, cur + 1);
                _showTargetPickerHint(this.spellName, this._totalPicked(), this.required);
                try { render(); } catch (_) {}
                // Auto-commit when the required count is met — players
                // can also press Enter early for under-quota commits.
                if (this._totalPicked() >= this.required) this.commit();
                return true;
            }
            return false;
        },

        removePick(canvasX, canvasY) {
            if (!this.active) return false;
            for (let i = tokens.length - 1; i >= 0; i--) {
                const t = tokens[i];
                if (!pointInToken(canvasX, canvasY, t)) continue;
                const cur = this.picks.get(t.id) || 0;
                if (cur <= 0) return false;
                if (cur <= 1) this.picks.delete(t.id);
                else this.picks.set(t.id, cur - 1);
                _showTargetPickerHint(this.spellName, this._totalPicked(), this.required);
                try { render(); } catch (_) {}
                return true;
            }
            return false;
        },

        _totalPicked() {
            let n = 0;
            for (const v of this.picks.values()) n += v;
            return n;
        },

        _cleanup() {
            this.active = false;
            this.required = 0;
            this.spellName = '';
            this.casterCharId = 0;
            this.casterCombatantId = '';
            this.casterPos = null;
            this.cursor = null;
            this.cursorRaw = null;
            this.rangeFt = 0;
            this.picks = null;
            this._resolve = null;
            // v2.49.154: stamp the close time so the dblclick handler
            // can guard a short window (single-target picker auto-
            // commits on the first click; the second click of a
            // dbl-click lands AFTER cleanup, so checking `active`
            // alone misses it). 500 ms covers the typical browser
            // dblclick threshold (Safari/Chrome ~300, plus headroom).
            this._justClosedAt = Date.now();
            document.body.classList.remove('target-picker-active');
            _hideTargetPickerHint();
            try { render(); } catch (_) {}
        },
    };

    function _showTargetPickerHint(spellName, picked, required) {
        _hideTargetPickerHint();
        const el = document.createElement('div');
        el.id = 'target-picker-hint';
        el.innerHTML =
            `<strong>🎯 ${spellName}</strong> · ` +
            `<span class="muted">pick ${picked} / ${required} target${required === 1 ? '' : 's'} · ` +
            `click target · right-click to undo · Enter to commit · Esc to cancel</span>`;
        Object.assign(el.style, {
            position: 'absolute',
            top: '10px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 200,
            padding: '6px 12px',
            borderRadius: '14px',
            border: '1.5px solid var(--accent)',
            background: 'color-mix(in srgb, var(--accent) 18%, var(--bg))',
            color: 'var(--accent)',
            fontSize: '12px',
            fontWeight: '600',
            boxShadow: '0 4px 14px rgba(0,0,0,0.35)',
            pointerEvents: 'none',
        });
        const host = document.getElementById('map-pane') || document.body;
        host.appendChild(el);
    }
    function _hideTargetPickerHint() {
        const el = document.getElementById('target-picker-hint');
        if (el) el.remove();
    }

    /** Convenience entry point for the sheet's cast handler. Returns a
     *  Promise<Array<combatant_id>> with duplicates allowed for stacking,
     *  or null when cancelled. */
    window.vttOpenMultiTargetPicker = function (opts) {
        if (!opts || !opts.required || opts.required < 1) return Promise.resolve(null);
        return _targetPicker.start(opts);
    };

    // ──────────────────────────────────────────────────────────────────
    // v2.49.71 — Ruler tool (Phase 1 of docs/plans/ruler-and-range.md)
    //
    // Mirrors _aoePicker's "suspend map control, prompt for clicks,
    // resume" pattern but for distance measurement. Local-only — no
    // WS broadcast (broadcast mode is Phase 3). The committed measurement
    // freezes on-screen for 3 s then auto-clears.
    //
    // Distance math matches the server's token_move formula: Chebyshev
    // (square grids) or Euclidean (hex grids), 5 ft per cell. Same
    // numbers a player sees in the movement breadcrumb.
    //
    // The picker is mutually exclusive with _aoePicker and with
    // token-drag / pan / spawn-arming — see the mousedown / mousemove
    // / contextmenu hooks below for the gating.
    // ──────────────────────────────────────────────────────────────────
    const _rulerPicker = {
        active: false,
        points: [],            // canvas-space {x, y} points; 2 in single-segment, 2+ in multi-segment
        cursor: null,          // {x, y} canvas-space mouse position
        multiSegment: false,   // v2.49.83 Phase 3D — Shift+R toggles
        broadcasting: false,   // v2.49.84 Phase 3E — Shift-click toggles broadcast
        _clearTimer: null,     // setTimeout handle for the 3 s ghost

        start(opts) {
            if (this.active) return false;
            // Mutex with the AoE picker — only one tool mode at a time.
            if (_aoePicker.active) _aoePicker.cancel();
            this.active = true;
            this.points = [];
            this.cursor = null;
            this.multiSegment = !!(opts && opts.multiSegment);
            this.broadcasting = !!(opts && opts.broadcasting);
            if (this._clearTimer) {
                clearTimeout(this._clearTimer);
                this._clearTimer = null;
            }
            document.body.classList.add('ruler-picker-active');
            _showRulerHint(0, this.multiSegment);
            _setRulerButtonState(true, this.broadcasting);
            try { render(); } catch (_) {}
            return true;
        },

        cancel() {
            if (!this.active) return;
            this._cleanup(/*keepGhost=*/false);
        },

        addPoint(x, y) {
            if (!this.active) return;
            this.points.push({ x, y });
            // v2.49.84 Phase 3E — broadcast each waypoint so remote
            // clients see the line draw in real time.
            if (this.broadcasting) _postRulerBroadcast('show', this.points, this.multiSegment);
            // v2.49.83 Phase 3D — multi-segment mode keeps accumulating
            // waypoints. Each click bumps the hint to "Click next
            // waypoint — Enter to commit." Enter calls commit(); Esc
            // calls cancel(). The render-pass per-segment chip layout
            // handles N points naturally.
            if (this.multiSegment) {
                _showRulerHint(this.points.length, true);
                try { render(); } catch (_) {}
                return;
            }
            // Single-segment (default): after the first click, prompt
            // for the second; after the second, auto-commit.
            if (this.points.length === 1) {
                _showRulerHint(1, false);
                try { render(); } catch (_) {}
                return;
            }
            // Second click — commit. Show the measurement in the hint
            // banner briefly, then auto-clear after 3 s.
            const a = this.points[0], b = this.points[1];
            const distance_ft = _computeRulerDistanceFt(a, b);
            _showRulerResult(distance_ft);
            // Move out of "active" so the next click doesn't re-add a
            // point; keep the points array so render() draws the ghost.
            this.active = false;
            document.body.classList.remove('ruler-picker-active');
            _setRulerButtonState(false, false);
            try { render(); } catch (_) {}
            // v2.49.84 — schedule the broadcast cleanup along with the
            // local ghost-clear so remote clients keep the line for the
            // same 3 s window.
            const wasBroadcasting = this.broadcasting;
            this._clearTimer = setTimeout(() => {
                this.points = [];
                this.cursor = null;
                this.broadcasting = false;
                this._clearTimer = null;
                _hideRulerHint();
                if (wasBroadcasting) _postRulerBroadcast('hide');
                try { render(); } catch (_) {}
            }, 3000);
        },

        // v2.49.83 Phase 3D — commit a multi-segment ruler. Called
        // on Enter while in multi-segment mode with at least 2 points.
        // Sums the per-segment distances + flips to the "ghost" state
        // (active=false but points kept) for the 3 s freeze.
        commitMulti() {
            if (!this.active || !this.multiSegment) return;
            if (this.points.length < 2) return;
            let total_ft = 0;
            for (let i = 0; i < this.points.length - 1; i++) {
                total_ft += _computeRulerDistanceFt(
                    this.points[i], this.points[i + 1],
                );
            }
            total_ft = Math.round(total_ft * 10) / 10;
            _showRulerResult(total_ft);
            this.active = false;
            document.body.classList.remove('ruler-picker-active');
            _setRulerButtonState(false, false);
            try { render(); } catch (_) {}
            const wasBroadcasting = this.broadcasting;
            this._clearTimer = setTimeout(() => {
                this.points = [];
                this.cursor = null;
                this.multiSegment = false;
                this.broadcasting = false;
                this._clearTimer = null;
                _hideRulerHint();
                if (wasBroadcasting) _postRulerBroadcast('hide');
                try { render(); } catch (_) {}
            }, 3000);
        },

        _cleanup(keepGhost) {
            const wasBroadcasting = this.broadcasting;
            this.active = false;
            if (!keepGhost) this.points = [];
            this.cursor = null;
            this.multiSegment = false;
            this.broadcasting = false;
            if (this._clearTimer) {
                clearTimeout(this._clearTimer);
                this._clearTimer = null;
            }
            document.body.classList.remove('ruler-picker-active');
            _hideRulerHint();
            _setRulerButtonState(false, false);
            // v2.49.84 Phase 3E — tell remote clients to drop the ghost.
            if (wasBroadcasting) _postRulerBroadcast('hide');
            try { render(); } catch (_) {}
        },
    };

    // Distance helper — mirrors the server's _distance_ft_between_tokens
    // (tabletop_routes.py:~1640). Chebyshev on square grids (the "5-5-5"
    // 5e diagonals rule), Euclidean on hex. 5 ft per cell. Result rounded
    // to nearest 0.1 ft to match the movement breadcrumb's chip text.
    function _computeRulerDistanceFt(a, b) {
        if (!a || !b || gridSize <= 0) return 0;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        let cells;
        if (gridType === 'square') {
            cells = Math.max(Math.abs(dx), Math.abs(dy)) / gridSize;
        } else {
            cells = Math.hypot(dx, dy) / gridSize;
        }
        return Math.round(cells * 5 * 10) / 10;
    }

    // v2.49.82 — Phase 3C client-side range parser. Mirrors the server's
    // app/content/range_parser.py::parse_range_ft for the cast-button
    // hover preview path. Returns:
    //   - null for "Special" / "Unlimited" / "Sight" / unparseable
    //   - 0   for "Self" / "Self (X-foot radius)" (caller skips the ring)
    //   - 5   for "Touch"
    //   - int for "N feet" / "N ft" / "N mile(s)" (× 5280)
    //   - long band int for thrown weapons ("20/60 feet" → 60)
    //
    // The receiver is the cross-window postMessage handler from the
    // sheet's spell-button hover events. Parsing on the tabletop side
    // means the sheet only sends raw strings — no client/server
    // version-sync risk.
    function _parseRangeFtJS(rangeStr) {
        if (!rangeStr) return null;
        const s = String(rangeStr).trim();
        if (!s) return null;
        const lower = s.toLowerCase();
        if (lower === 'special' || lower === 'unlimited' || lower === 'sight') return null;
        if (lower === 'self') return 0;
        if (lower === 'touch') return 5;
        if (/^\s*self\s*\(/i.test(s)) return 0;
        let m = s.match(/^\s*(\d+)\s*\/\s*(\d+)\s*(?:ft|foot|feet)\.?\s*$/i);
        if (m) return parseInt(m[2], 10);
        m = s.match(/^\s*(\d+)\s*(?:ft|foot|feet)\.?\s*$/i);
        if (m) return parseInt(m[1], 10);
        m = s.match(/^\s*(\d+)\s*miles?\.?\s*$/i);
        if (m) return parseInt(m[1], 10) * 5280;
        return null;
    }
    // v2.49.170: SRD monster actions bury range / reach in the desc
    // sentence ("Melee Weapon Attack: +3 to hit, reach 5 ft., one
    // target. ...") rather than carrying a structured ``range`` field.
    // Demo-seed monsters (app/demo_seed.py) DO have an explicit range
    // field, but SRD imports don't. Without a structured range the
    // picker has ``rangeStr === ""`` → ``rangeFt === 0`` → no green
    // availability rings, no ruler chip, no out-of-range warning, no
    // server-side range enforcement. This helper regex-extracts the
    // range from a free-text desc so SRD monsters get picker parity
    // with both demo-seed monsters and PCs.
    //
    // Returns a string like "5 ft" / "80/320 ft" that _parseRangeFtJS
    // can consume, or null if no range pattern matches.
    //
    // Priority order (matches RAW phrasing in SRD action blocks):
    //   1. "range N/M ft" — thrown / ranged weapons (long range)
    //   2. "range N ft" — pure ranged
    //   3. "reach N ft" — melee
    function _parseRangeFromMonsterDesc(desc) {
        if (!desc) return null;
        const s = String(desc);
        let m = s.match(/range\s+(\d+)\s*\/\s*(\d+)\s*(?:ft|foot|feet)\.?/i);
        if (m) return `${m[1]}/${m[2]} ft`;
        m = s.match(/range\s+(\d+)\s*(?:ft|foot|feet)\.?/i);
        if (m) return `${m[1]} ft`;
        m = s.match(/reach\s+(\d+)\s*(?:ft|foot|feet)\.?/i);
        if (m) return `${m[1]} ft`;
        return null;
    }
    window._parseRangeFromMonsterDesc = _parseRangeFromMonsterDesc;

    // v2.49.82 — Phase 3C cast-button hover ring. Renders a translucent
    // ring around the caster's token at the spell's range while the
    // player hovers a spell-cast button in the character sheet (BEFORE
    // they click Cast). Same green-translucent style as the Phase 3A
    // AoE picker ring. State driven by postMessage from the sheet's
    // .sp-cast mouseenter / mouseleave handlers (see Phase 3C client
    // wiring in app/templates/sheet_dnd5e.html). Suppressed when the
    // AoE picker / ruler picker / a drag is active — the more
    // prominent tool wins.
    const _castHoverRing = {
        active: false,
        casterPos: null,
        range_ft: 0,
        spellName: '',

        show(opts) {
            if (_aoePicker.active || _rulerPicker.active || dragging) return;
            const rangeFt = _parseRangeFtJS(opts.range_str);
            if (!rangeFt || rangeFt <= 0) return;
            const charId = parseInt(opts.char_id, 10);
            if (!charId) return;
            const casterPos = _aoePicker._resolveOrigin(charId);
            if (!casterPos) return;
            this.active = true;
            this.casterPos = casterPos;
            this.range_ft = rangeFt;
            this.spellName = String(opts.spell_name || '');
            try { render(); } catch (_) {}
        },

        hide() {
            if (!this.active) return;
            this.active = false;
            this.casterPos = null;
            this.range_ft = 0;
            this.spellName = '';
            try { render(); } catch (_) {}
        },
    };

    // Listen for cross-window postMessages from the sheet drawer's
    // iframe. The sheet posts `{type: 'vtt:cast_range_hover', action:
    // 'show'|'hide', ...}` on .sp-cast mouseenter / mouseleave.
    // Origin-matched against window.location.origin so a malicious
    // page in another tab can't spoof the picker.
    window.addEventListener('message', (ev) => {
        if (!ev || !ev.data) return;
        if (ev.origin && ev.origin !== window.location.origin) return;
        const d = ev.data;
        if (!d || d.type !== 'vtt:cast_range_hover') return;
        if (d.action === 'show') {
            _castHoverRing.show({
                char_id: d.char_id,
                range_str: d.range_str,
                spell_name: d.spell_name,
            });
        } else if (d.action === 'hide') {
            _castHoverRing.hide();
        }
    });

    // v2.49.83 Phase 3D — shared chip-drawing helper. Used for both
    // per-segment chips (midpoint of each line) AND the total chip at
    // the cursor in multi-segment mode. Centered at (x, y) with the
    // ruler's accent green border + dark fill.
    function _drawRulerChip(c, label, x, y) {
        const metrics = c.measureText(label);
        const padX = 8;
        const chipW = metrics.width + padX * 2;
        const chipH = 18;
        c.fillStyle = 'rgba(20, 24, 28, 0.92)';
        c.strokeStyle = '#4ade80';
        c.lineWidth = 1.5;
        if (c.roundRect) {
            c.beginPath();
            c.roundRect(x - chipW / 2, y - chipH / 2, chipW, chipH, 6);
            c.fill();
            c.stroke();
        } else {
            c.fillRect(x - chipW / 2, y - chipH / 2, chipW, chipH);
            c.strokeRect(x - chipW / 2, y - chipH / 2, chipW, chipH);
        }
        c.fillStyle = '#4ade80';
        c.fillText(label, x, y);
    }

    function _showRulerHint(pointsClicked, multiSegment) {
        _hideRulerHint();
        const el = document.createElement('div');
        el.id = 'ruler-picker-hint';
        el.className = 'ruler-picker-hint';
        let msg;
        if (multiSegment) {
            // v2.49.83 Phase 3D — multi-segment hint text rotates by
            // points clicked. Enter commits; Esc cancels at any point.
            msg = pointsClicked === 0
                ? '📏 Click waypoints — Enter to commit, Esc to cancel'
                : `📏 Click next waypoint (${pointsClicked} placed) — Enter to commit, Esc to cancel`;
        } else {
            msg = pointsClicked === 0
                ? '📏 Click two points — Esc to cancel'
                : '📏 Click second point — Esc to cancel';
        }
        el.textContent = msg;
        const host = document.getElementById('map-pane') || document.body;
        host.appendChild(el);
    }
    function _showRulerResult(distance_ft) {
        _hideRulerHint();
        const el = document.createElement('div');
        el.id = 'ruler-picker-hint';
        el.className = 'ruler-picker-hint';
        el.textContent = `📏 ${distance_ft} ft`;
        const host = document.getElementById('map-pane') || document.body;
        host.appendChild(el);
    }
    function _hideRulerHint() {
        const el = document.getElementById('ruler-picker-hint');
        if (el) el.remove();
    }

    function _setRulerButtonState(active, broadcasting) {
        const btn = document.getElementById('ruler-btn');
        if (!btn) return;
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        if (broadcasting) {
            btn.setAttribute('data-broadcasting', 'true');
            btn.setAttribute('title', 'Measure distance on the map (R) — Broadcasting 📡');
        } else {
            btn.removeAttribute('data-broadcasting');
            btn.setAttribute('title', 'Measure distance on the map (R) · Shift = multi-segment · Shift-click = broadcast');
        }
    }

    // v2.49.84 Phase 3E — broadcast helpers + remote-rulers map.
    //
    // POST to /api/campaign/{cid}/ruler_broadcast on each addPoint /
    // commit / cancel when the local picker is in broadcasting mode.
    // The server fan-outs a ``ruler_broadcast`` WS message to all
    // other campaign clients. The fire-and-forget pattern matches
    // the existing token-move broadcast cadence.
    function _postRulerBroadcast(action, points, multiSegment) {
        if (typeof CAMPAIGN_ID === 'undefined') return;
        const body = { action };
        if (action === 'show') {
            body.points = (points || []).map(p => ({ x: p.x, y: p.y }));
            body.multi_segment = !!multiSegment;
        }
        try {
            fetch(`/api/campaign/${CAMPAIGN_ID}/ruler_broadcast`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            }).catch(() => { /* fire-and-forget */ });
        } catch (_) { /* network / CSP — silent */ }
    }

    // Remote rulers map keyed by broadcaster user_id. Each entry:
    // { points: [{x,y}, ...], multi_segment: bool, user_name: str,
    //   expires_at: ms }. Render pass walks the map; entries past
    //   expires_at are skipped + lazily removed.
    const _remoteRulers = new Map();

    function _onRulerBroadcast(d) {
        if (!d || typeof d.user_id !== 'number') return;
        // Drop our own echoes — local render is already up to date.
        if (typeof ME !== 'undefined' && ME && d.user_id === ME.id) return;
        if (d.action === 'hide') {
            _remoteRulers.delete(d.user_id);
            try { render(); } catch (_) {}
            return;
        }
        // action === 'show'.
        const pts = Array.isArray(d.points) ? d.points : [];
        if (!pts.length) {
            _remoteRulers.delete(d.user_id);
            try { render(); } catch (_) {}
            return;
        }
        _remoteRulers.set(d.user_id, {
            points: pts.map(p => ({ x: Number(p.x) || 0, y: Number(p.y) || 0 })),
            multi_segment: !!d.multi_segment,
            user_name: d.user_name || 'Player',
            // Auto-drop 8 s after the last update (covers the
            // broadcaster's 3 s freeze + network jitter + dropped
            // hides from disconnected clients).
            expires_at: Date.now() + 8000,
        });
        try { render(); } catch (_) {}
    }

    // Toolbar-button click + R hotkey wiring. The button toggles the
    // picker — clicking again while active cancels.
    (function _wireRulerControls() {
        const btn = document.getElementById('ruler-btn');
        if (btn && !btn.hasAttribute('disabled')) {
            btn.addEventListener('click', (ev) => {
                if (_rulerPicker.active) {
                    _rulerPicker.cancel();
                    return;
                }
                // v2.49.83 / v2.49.84 — Shift toggles BOTH multi-segment
                // AND broadcast mode (GM-led demos typically use both
                // together to walk the table through a measurement).
                // Two flags are independent in the API, but the
                // toolbar binds them together for one-click ergonomics.
                // The hotkey path is the same: R = single + local;
                // Shift+R = multi + broadcast.
                _rulerPicker.start({
                    multiSegment: !!ev.shiftKey,
                    broadcasting: !!ev.shiftKey,
                });
            });
        }
        // R hotkey — only when no input has focus + no other modal /
        // picker is consuming the keystroke. Esc handling already lives
        // in the existing global keydown handler below; we extend it.
        // v2.49.83 Phase 3D — Shift+R starts the multi-segment variant.
        // Enter inside multi-segment commits.
        document.addEventListener('keydown', (ev) => {
            // Skip if the user is typing in an input / textarea / contenteditable.
            const ae = document.activeElement;
            if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA'
                    || ae.isContentEditable)) return;
            // Enter commits a multi-segment ruler.
            if ((ev.key === 'Enter' || ev.key === 'NumpadEnter')
                    && _rulerPicker.active && _rulerPicker.multiSegment) {
                if (_rulerPicker.points.length >= 2) {
                    ev.preventDefault();
                    _rulerPicker.commitMulti();
                }
                return;
            }
            if (ev.key !== 'r' && ev.key !== 'R') return;
            if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
            if (_aoePicker.active) return;
            const ruleButton = document.getElementById('ruler-btn');
            if (ruleButton && ruleButton.hasAttribute('disabled')) return;
            ev.preventDefault();
            if (_rulerPicker.active) _rulerPicker.cancel();
            else _rulerPicker.start({
                multiSegment: !!ev.shiftKey,
                broadcasting: !!ev.shiftKey,
            });
        });
    })();

    // Floating hint chip for the AoE placement mode. Mirrors the
    // existing targeting chip's positioning but uses the damage tint
    // so the user knows they're in a different mode. Label text varies
    // by shape so the GM sees whether they're placing a sphere (click
    // anywhere) vs aiming a cone (cursor = direction from caster).
    function _showAoePickerHint(spellName, sizeFt, shape, secondaryFt) {
        _hideAoePickerHint();
        const el = document.createElement('div');
        el.id = 'aoe-picker-hint';
        let shapeLabel;
        let verb;
        if (shape === 'cone') {
            shapeLabel = 'cone';
            verb = 'aim with cursor · click to fire';
        } else if (shape === 'line') {
            shapeLabel = `× ${secondaryFt || 5} ft line`;
            verb = 'aim with cursor · click to fire';
        } else if (shape === 'cube') {
            shapeLabel = 'cube';
            verb = 'click to place';
        } else if (shape === 'self_sphere') {
            shapeLabel = 'emanation';
            verb = 'click to confirm';
        } else if (shape === 'self_cube') {
            shapeLabel = 'cube from you';
            verb = 'aim with cursor · click to fire';
        } else {
            shapeLabel = 'sphere';
            verb = 'click to place';
        }
        el.innerHTML =
            `<strong>💥 ${spellName}</strong> · ${sizeFt} ft ${shapeLabel} · ` +
            `<span class="muted">${verb} · Esc to cancel</span>`;
        Object.assign(el.style, {
            position: 'absolute',
            top: '10px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 200,
            padding: '6px 12px',
            borderRadius: '14px',
            border: '1.5px solid var(--c-damage)',
            background: 'color-mix(in srgb, var(--c-damage) 18%, var(--bg))',
            color: 'var(--c-damage)',
            fontSize: '12px',
            fontWeight: '600',
            boxShadow: '0 4px 14px rgba(0,0,0,0.35)',
            pointerEvents: 'none',
        });
        const host = document.getElementById('map-pane') || document.body;
        host.appendChild(el);
    }
    function _hideAoePickerHint() {
        const el = document.getElementById('aoe-picker-hint');
        if (el) el.remove();
    }

    // Floating chip rendered in #map-pane. Auto-removes when no
    // targets are selected; auto-rebuilds when at least one is.
    function _updateTargetingChip() {
        let el = document.getElementById('targeting-chip');
        const targets = _targeting.getTargets();
        if (!targets.length) {
            if (el) el.remove();
            return;
        }
        if (!el) {
            el = document.createElement('div');
            el.id = 'targeting-chip';
            el.className = 'targeting-chip';
            (mapPane || document.body).appendChild(el);
        }
        const names = targets
            .map(t => (t.name || '').replace(/[<&>]/g, s => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[s])))
            .join(', ');
        el.innerHTML = `<span class="t-icon">🎯</span>
            <span class="t-label">Targeting</span>
            <span class="t-name" title="${names}">${names}</span>
            <button type="button" class="t-clear" title="Clear (Esc)">×</button>`;
        el.querySelector('.t-clear').addEventListener('click', () => _targeting.clear());
    }

    // One-time onboarding hint the first time targeting fires so
    // long-time demo users learn the new gestures.
    function _maybeShowTargetingHint() {
        try {
            if (localStorage.getItem('vtt:targeting-hint-shown')) return;
            localStorage.setItem('vtt:targeting-hint-shown', '1');
        } catch (_) { return; }
        if (typeof window.showToast === 'function') {
            window.showToast(
                '🎯 Target set. Right-click (or long-press on touch) opens the character sheet.',
                'info',
                6000,
            );
        }
    }

    function _drawRing(cx, cy, r, color, style) {
        ctx.save();
        ctx.strokeStyle = color || '#000';
        switch (style) {
            case 'dashed':
                ctx.setLineDash([5, 3]);
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.stroke();
                ctx.setLineDash([]);
                break;
            case 'double':
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.arc(cx, cy, r + 3, 0, Math.PI * 2);
                ctx.stroke();
                ctx.beginPath();
                ctx.arc(cx, cy, r - 2, 0, Math.PI * 2);
                ctx.stroke();
                break;
            case 'glow':
                ctx.shadowBlur = 8;
                ctx.shadowColor = color || '#000';
                ctx.lineWidth = 2.5;
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.stroke();
                ctx.shadowBlur = 0;
                break;
            case 'spiked': {
                const spikes = 8, outerR = r + 5, innerR = r;
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                for (let i = 0; i < spikes * 2; i++) {
                    const angle = (i * Math.PI) / spikes - Math.PI / 2;
                    const rad = i % 2 === 0 ? outerR : innerR;
                    const x = cx + rad * Math.cos(angle);
                    const y = cy + rad * Math.sin(angle);
                    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
                }
                ctx.closePath();
                ctx.stroke();
                break;
            }
            default: // solid
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.stroke();
        }
        ctx.restore();
    }

    function _drawCircleToken(t, cx, cy, r) {
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fillStyle = t.color || '#cc3333';
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = '#000';
        ctx.stroke();
        ctx.fillStyle = '#fff';
        ctx.font = '12px system-ui';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText((t.label || '').slice(0, 12), cx, cy);
    }

    function drawToken(t) {
        if (t.is_hidden && !ME.isGm) return;
        const cx = t.x + gridSize / 2;
        const cy = t.y + gridSize / 2;
        const r = (gridSize * t.size) / 2 - 4;
        ctx.save();
        if (t.is_hidden) ctx.globalAlpha = 0.4;
        const isGif = ME.animateGifs && t.image_url && t.image_url.toLowerCase().includes('.gif');
        const _char = charById[t.character_id] || {};
        const _ringColor = _char.color || t.color || '#000';
        const _ringStyle = _char.ring_style || 'solid';
        if (isGif) {
            // GIF: the overlay <img> renders the image; just draw the colour ring here.
            _drawRing(cx, cy, r, _ringColor, _ringStyle);
        } else if (t.image_url) {
            const img = _loadTokenImage(t.image_url);
            if (img.complete && img.naturalWidth > 0) {
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.clip();
                ctx.drawImage(img, cx - r, cy - r, r * 2, r * 2);
                _drawRing(cx, cy, r, _ringColor, _ringStyle);
            } else {
                _drawCircleToken(t, cx, cy, r);
            }
        } else {
            _drawCircleToken(t, cx, cy, r);
        }
        ctx.restore();
    }

    function drawSpawnMarkers() {
        // GM-only encounter-prep markers. Only drawn while an encounter
        // edit form is open AND its bound map matches the active map.
        // A dashed ring tinted with each character's color so they
        // don't look like real tokens.
        if (!ME.isGm) return;
        if (!spawnContext || !spawnContext.spawns) return;
        if (spawnContext.mapId != null && spawnContext.mapId !== MAP_ID) return;
        const spawns = spawnContext.spawns;
        if (!Object.keys(spawns).length) return;
        const r = Math.max(14, gridSize / 3);
        Object.keys(spawns).forEach(key => {
            const spawn = spawns[key];
            if (!spawn || typeof spawn.x !== 'number' || typeof spawn.y !== 'number') return;
            const ch = characters.find(c => String(c.id) === key);
            const cx = spawn.x + gridSize / 2;
            const cy = spawn.y + gridSize / 2;
            const tint = (ch && ch.color) || '#d4a84a';
            ctx.save();
            ctx.globalAlpha = 0.85;
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(20,20,28,0.55)';
            ctx.fill();
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.lineWidth = 3;
            ctx.strokeStyle = tint;
            ctx.setLineDash([5, 4]);
            ctx.stroke();
            ctx.setLineDash([]);
            const initial = ch && ch.name ? ch.name.slice(0, 1).toUpperCase() : '📍';
            ctx.fillStyle = tint;
            ctx.font = 'bold ' + Math.round(r * 0.95) + 'px sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(initial, cx, cy + 1);
            ctx.restore();
        });
    }

    // v2.49.81 — Phase 3B hover rangefinder. Tracks the canvas-space
    // cursor whenever no tool mode (AoE picker, ruler picker) is
    // active so the render-pass can draw a distance line from the
    // currently-targeted token to the cursor. Set to null when the
    // cursor leaves the canvas; cleared when a tool mode activates.
    //
    // v2.49.92 — MUST be declared BEFORE render() is defined (let
    // hoisting doesn't apply to declarations BELOW the function body
    // that closes over them). render() runs at IIFE startup
    // (`render()` call further down) and reads ``_hoverCursor`` —
    // putting the `let` declaration after that read trips the
    // temporal-dead-zone "Cannot access '_hoverCursor' before
    // initialization" ReferenceError and aborts the entire IIFE,
    // which silently leaves the mousedown / mouseup / mousemove
    // listeners + every ``window.vtt*`` global UNATTACHED. The
    // user-reported pan/drag breakage from v2.49.81 onward was this
    // bug; the new tests in tests/harness_ui/test_tabletop_canvas.py
    // catch it.
    // v2.49.134: removed the _hoverCursor declaration — its only
    // consumer was the v2.49.81 Phase 3B hover-rangefinder render
    // block, which was removed in this commit. The TDZ-safety
    // comment that the original declaration carried (Read full
    // context at v2.49.92 git history if needed) doesn't apply
    // because there's no consumer left.

    // v2.49.133: init-tracker → canvas hover linking. When the user
    // hovers an .init-row / .init-entry in the side drawer (desktop
    // only — see the @media (hover: hover) gate in tabletop.html),
    // the bound listener calls window.vttHighlightCombatant(c) to set
    // _initHoverTokenId. render() draws an accent-coloured glow ring
    // around the matching token so the GM can identify which canvas
    // token a row corresponds to without trial-and-error clicking.
    let _initHoverTokenId = null;
    window.vttHighlightCombatant = function (combatant) {
        if (!combatant) {
            if (_initHoverTokenId !== null) {
                _initHoverTokenId = null;
                try { render(); } catch (_) {}
            }
            return;
        }
        let foundId = null;
        for (const t of tokens) {
            if (combatant.source_token_id != null && combatant.source_token_id === t.id) {
                foundId = t.id; break;
            }
            if (combatant.char_id && t.character_id === combatant.char_id) {
                foundId = t.id; break;
            }
            if (combatant.token_template_id
                    && t.token_template_id === combatant.token_template_id
                    && combatant.name === t.label) {
                foundId = t.id; break;
            }
        }
        if (foundId !== _initHoverTokenId) {
            _initHoverTokenId = foundId;
            try { render(); } catch (_) {}
        }
    };

    function render() {
        ctx.clearRect(0, 0, MAP_W, MAP_H);
        if (showGrid) {
            if (gridType === 'square') drawSquareGrid();
            else if (gridType === 'hex') drawHexGrid();
        }
        tokens.forEach(drawToken);
        // v2.49.4 — skull overlay for any token whose linked
        // combatant is at 0 HP. Iterates window.battle.combatants for
        // matching entries (PCs via char_id, NPCs via source_token_id
        // or template+label). Drawn after drawToken so the skull sits
        // on top of the portrait, but before targeting rings + AoE
        // markers so it doesn't compete with the active-target
        // outline. Hidden tokens skipped for non-GMs. Skull is
        // drawn over a dim-down overlay so a dead bandit reads as
        // "still on the map but not a threat" instead of vanishing
        // entirely (the GM may want to keep the body visible for
        // narrative reasons).
        const battleC = (window.battle && window.battle.combatants) || [];
        tokens.forEach(t => {
            if (t.is_hidden && !ME.isGm) return;
            let combatant = null;
            for (const c of battleC) {
                if (c.source_token_id != null && c.source_token_id === t.id) { combatant = c; break; }
                if (t.character_id && c.char_id === t.character_id) { combatant = c; break; }
                if (t.token_template_id
                        && c.token_template_id === t.token_template_id
                        && c.name === t.label) { combatant = c; break; }
            }
            if (!combatant) return;
            const hpCur = Number(combatant.hp_current);
            const hpMax = Number(combatant.hp_max);
            if (!(hpMax > 0 && hpCur <= 0)) return;
            const cx = t.x + gridSize / 2;
            const cy = t.y + gridSize / 2;
            const r = (gridSize * t.size) / 2;
            ctx.save();
            // Dim the token portrait so the skull reads as the
            // primary visual signal.
            ctx.fillStyle = 'rgba(0,0,0,0.55)';
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.fill();
            // Skull emoji on top — sized to fill ~60% of the token.
            ctx.font = `bold ${Math.round(r * 1.2)}px system-ui, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = '#fff';
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 3;
            ctx.strokeText('💀', cx, cy);
            ctx.fillText('💀', cx, cy);
            ctx.restore();
        });
        drawSpawnMarkers();
        drawMovementBreadcrumb();
        // v2.49.133: init-tracker hover-link glow ring. Set by
        // window.vttHighlightCombatant when the user mouses over a
        // row in the init drawer (desktop only). Drawn before the
        // crimson targeting ring so a tracker-hovered token that is
        // ALSO a target gets the crimson on top (priority: explicit
        // target > tracker hover). Hidden tokens skipped for non-GM
        // so the glow doesn't leak hidden NPC positions.
        if (_initHoverTokenId !== null) {
            const t = tokens.find(tk => tk.id === _initHoverTokenId);
            if (t && !(t.is_hidden && !ME.isGm)) {
                const cx = t.x + gridSize / 2;
                const cy = t.y + gridSize / 2;
                const r = (gridSize * t.size) / 2;
                ctx.save();
                ctx.lineWidth = 3;
                ctx.strokeStyle = '#a78bfa';      // accent purple (matches theme accent default)
                ctx.shadowColor = '#a78bfa';
                ctx.shadowBlur = 14;
                ctx.beginPath();
                ctx.arc(cx, cy, r + 5, 0, Math.PI * 2);
                ctx.stroke();
                ctx.restore();
            }
        }
        // v2.21.0 Phase T.0: targeting rings drawn on top of tokens so
        // the crimson outer ring stays visible even when a portrait
        // jpg fills the token face. Skip hidden tokens for non-GM.
        tokens.forEach(t => {
            if (!_targeting.isTargeted(t.id)) return;
            if (t.is_hidden && !ME.isGm) return;
            const cx = t.x + gridSize / 2;
            const cy = t.y + gridSize / 2;
            const r = (gridSize * t.size) / 2 - 4;
            ctx.save();
            ctx.lineWidth = 3;
            ctx.strokeStyle = '#dc2626';
            ctx.shadowColor = '#dc2626';
            ctx.shadowBlur = 10;
            ctx.beginPath();
            ctx.arc(cx, cy, r + 4, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
        });
        // v2.49.143: target picker range-gate ring. When the spell /
        // attack has a known range, draw a translucent green ring
        // around the caster at the range radius so out-of-range
        // candidate targets are obvious before the click. Suppressed
        // for rangeFt === 0 (self-cast, "Special", unknown ranges).
        let _tpOutOfRange = false;  // shared with the ruler + hover ring rendering below
        // v2.49.161: per-token availability rings (was per-cell rects
        // in v2.49.160, was a single range circle in v2.49.143). Each
        // in-range token gets a bold green circle around it; the one
        // currently under the cursor turns red (matching the picked
        // ring colour) so the player sees "click here will pick this"
        // without having to read the ruler. Out-of-range tokens get
        // nothing — the empty space tells the player they're not in
        // reach. Picked tokens are skipped here because the picked-
        // ring loop (~80 lines below) draws its own brighter ring on
        // top, so we don't want to double-stroke.
        let _hoveredPickableId = null;
        if (_targetPicker.active && _targetPicker.cursorRaw) {
            for (let i = tokens.length - 1; i >= 0; i--) {
                const t = tokens[i];
                if (t.is_hidden && !ME.isGm) continue;
                if (pointInToken(_targetPicker.cursorRaw.x, _targetPicker.cursorRaw.y, t)) {
                    _hoveredPickableId = t.id;
                    break;
                }
            }
        }
        let _hoveredOutOfRange = false;
        if (_targetPicker.active && _targetPicker.casterPos && _targetPicker.rangeFt > 0) {
            ctx.save();
            ctx.lineCap = 'round';
            ctx.setLineDash([]);
            for (const t of tokens) {
                if (t.is_hidden && !ME.isGm) continue;
                // Skip the caster's own token — single-target spells
                // can't target self, and showing the caster as a
                // valid target clutters the visual. v2.49.169: NPC
                // casters honored via the shared _isCasterToken helper
                // (the pre-v2.49.169 check only fired for casterCharId,
                // letting NPCs ring their own token green).
                if (_isCasterToken(t, _targetPicker.casterCharId, _targetPicker.casterCombatantId)) continue;
                const tcx = t.x + gridSize / 2;
                const tcy = t.y + gridSize / 2;
                const dist_ft = _computeRulerDistanceFt(
                    _targetPicker.casterPos, { x: tcx, y: tcy },
                );
                if (dist_ft > _targetPicker.rangeFt) continue;
                // Skip already-picked tokens — the picked-ring loop
                // below renders a brighter crimson ring on top.
                if (_targetPicker.picks && _targetPicker.picks.has(t.id)) continue;
                const r = (gridSize * (t.size || 1)) / 2;
                const isHovered = (t.id === _hoveredPickableId);
                ctx.save();
                if (isHovered) {
                    // Hovered in-range token → bold crimson ring with
                    // a halo. Same visual language as the picked ring
                    // so the player sees "click now to add this one."
                    ctx.strokeStyle = 'rgba(220, 38, 38, 0.4)';
                    ctx.lineWidth = 5;
                    ctx.beginPath();
                    ctx.arc(tcx, tcy, r + 3, 0, Math.PI * 2);
                    ctx.stroke();
                    ctx.strokeStyle = '#dc2626';
                    ctx.lineWidth = 3.5;
                    ctx.shadowColor = '#dc2626';
                    ctx.shadowBlur = 14;
                } else {
                    // Available in-range token → bold accent-green
                    // ring with a soft halo.
                    ctx.strokeStyle = 'rgba(74, 222, 128, 0.35)';
                    ctx.lineWidth = 5;
                    ctx.beginPath();
                    ctx.arc(tcx, tcy, r + 3, 0, Math.PI * 2);
                    ctx.stroke();
                    ctx.strokeStyle = '#4ade80';
                    ctx.lineWidth = 3;
                    ctx.shadowColor = 'rgba(74, 222, 128, 0.85)';
                    ctx.shadowBlur = 10;
                }
                ctx.beginPath();
                ctx.arc(tcx, tcy, r + 2, 0, Math.PI * 2);
                ctx.stroke();
                ctx.restore();
            }
            ctx.restore();
            // Compute out-of-range against the SNAPPED cursor so the
            // chip + ruler still warn when the cursor strays into a
            // non-target cell beyond range. Same Chebyshev math.
            if (_targetPicker.cursor) {
                const _dist = _computeRulerDistanceFt(
                    _targetPicker.casterPos, _targetPicker.cursor,
                );
                if (_dist > _targetPicker.rangeFt) _tpOutOfRange = true;
            }
            // If the hovered token is out-of-range, flag for the
            // separate amber-dashed hover preview below.
            if (_hoveredPickableId) {
                const _ht = tokens.find(tk => tk.id === _hoveredPickableId);
                if (_ht) {
                    const _hcx = _ht.x + gridSize / 2;
                    const _hcy = _ht.y + gridSize / 2;
                    const _hdist = _computeRulerDistanceFt(
                        _targetPicker.casterPos, { x: _hcx, y: _hcy },
                    );
                    if (_hdist > _targetPicker.rangeFt) _hoveredOutOfRange = true;
                }
            }
        }
        // v2.49.140 / v2.49.161: hover preview retained ONLY for the
        // out-of-range case. In-range hover is handled inline above by
        // the availability-ring loop (red ring when hovered). Here we
        // only fire when the cursor sits on an out-of-range token, so
        // the player sees "this token is reachable visually but out of
        // spell range." Also fires when the picker has no rangeFt set
        // (Special / unknown) — in that case there's no green-ring
        // loop, so this is the only hover indicator.
        if (_targetPicker.active && _hoveredPickableId
            && (_hoveredOutOfRange || !_targetPicker.rangeFt)) {
            const t = tokens.find(tk => tk.id === _hoveredPickableId);
            if (t) {
                const cx = t.x + gridSize / 2;
                const cy = t.y + gridSize / 2;
                const r = (gridSize * t.size) / 2;
                ctx.save();
                ctx.lineWidth = 2;
                if (_hoveredOutOfRange) {
                    ctx.strokeStyle = 'rgba(245, 158, 11, 0.85)';
                    ctx.setLineDash([4, 3]);
                } else {
                    ctx.strokeStyle = 'rgba(220, 38, 38, 0.55)';
                    ctx.setLineDash([]);
                }
                ctx.beginPath();
                ctx.arc(cx, cy, r + 4, 0, Math.PI * 2);
                ctx.stroke();
                ctx.restore();
            }
        }
        // v2.49.135: multi-target picker — draw a red ring + an "×N"
        // badge on every token that has at least one pick. Drawn on
        // top of the targeting ring (`_targeting` state) so a picked-
        // during-cast token visibly stands out from any pre-existing
        // selection. v2.49.138: ring color shifted from accent purple
        // → red (#dc2626, same crimson the existing `_targeting`
        // ring uses) so "this is a target you've selected" reads as
        // the same visual language across the two systems.
        if (_targetPicker.active && _targetPicker.picks && _targetPicker.picks.size) {
            for (const [tokenId, count] of _targetPicker.picks) {
                const t = tokens.find(tk => tk.id === tokenId);
                if (!t) continue;
                if (t.is_hidden && !ME.isGm) continue;
                const cx = t.x + gridSize / 2;
                const cy = t.y + gridSize / 2;
                const r = (gridSize * t.size) / 2;
                ctx.save();
                // v2.49.158: tighter + bolder ring matching the new
                // active-turn init card border style. Outer halo +
                // tight inner ring instead of the v2.49.140 single
                // r+6 offset. Draws in two passes: a softer wider
                // outer halo first, then a sharp 2px inner ring on
                // top, so the visual reads as "thick crimson border
                // with glow" rather than "fat fuzzy ring."
                ctx.lineWidth = 4;
                ctx.strokeStyle = 'rgba(220, 38, 38, 0.35)';
                ctx.beginPath();
                ctx.arc(cx, cy, r + 3, 0, Math.PI * 2);
                ctx.stroke();
                ctx.lineWidth = 2.5;
                ctx.strokeStyle = '#dc2626';
                ctx.shadowColor = '#dc2626';
                ctx.shadowBlur = 14;
                ctx.beginPath();
                ctx.arc(cx, cy, r + 1, 0, Math.PI * 2);
                ctx.stroke();
                ctx.restore();
                // "×N" badge in the upper-right of the token (only when
                // the same token is picked more than once — single picks
                // are obvious from the ring alone).
                if (count > 1) {
                    ctx.save();
                    const badgeR = Math.max(11, Math.round(gridSize * 0.22));
                    const bx = cx + r * 0.72;
                    const by = cy - r * 0.72;
                    ctx.fillStyle = '#dc2626';
                    ctx.strokeStyle = '#fff';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.arc(bx, by, badgeR, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.stroke();
                    ctx.font = `bold ${Math.round(badgeR * 1.1)}px system-ui, sans-serif`;
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillStyle = '#fff';
                    ctx.fillText(`×${count}`, bx, by + 1);
                    ctx.restore();
                }
            }
        }
        // v2.49.138: ruler line from the caster's token center to the
        // crosshair cursor (snapped to the grid-cell center the mouse
        // is hovering). Mirrors the ruler tool's distance chip + line
        // so the player sees the spell/attack range in feet as they
        // hover candidate targets. Suppressed when the picker isn't
        // active OR the caster's token isn't on the map.
        // v2.49.143: line + chip switch to amber when out of range.
        // Distance chip carries an "X / Y" form so the player sees
        // both the cursor distance and the spell's max range.
        // v2.49.161: suppress entirely for melee (range ≤ 5 ft).
        // The chip would always read "5 ft / 5 ft" and the line just
        // adds visual noise to a one-cell decision. The green/red
        // per-token availability rings (above) already tell the
        // player which adjacent token is the target.
        const _suppressRuler = (
            _targetPicker.rangeFt > 0 && _targetPicker.rangeFt <= 5
        );
        if (_targetPicker.active && _targetPicker.casterPos && _targetPicker.cursor && !_suppressRuler) {
            const fromX = _targetPicker.casterPos.x;
            const fromY = _targetPicker.casterPos.y;
            const toX = _targetPicker.cursor.x;
            const toY = _targetPicker.cursor.y;
            // Only render once the cursor has moved off the caster's
            // own square — a zero-length line is visual noise.
            if (Math.hypot(toX - fromX, toY - fromY) > 8) {
                const _outOfRange = _tpOutOfRange;
                ctx.save();
                // v2.49.144: HD ruler polish — round line caps + 2px
                // baseline width so the dashed pattern renders as
                // crisp pills instead of fuzzy chevrons. Endpoint
                // pixel-snap (Math.round) eliminates sub-pixel blur
                // from non-integer grid-snap coordinates.
                ctx.lineCap = 'round';
                if (_outOfRange) {
                    ctx.strokeStyle = 'rgba(245, 158, 11, 0.95)';
                    ctx.lineWidth = 2;
                    ctx.setLineDash([4, 3]);
                } else {
                    ctx.strokeStyle = 'rgba(220, 38, 38, 0.85)';
                    ctx.lineWidth = 2;
                    ctx.setLineDash([6, 4]);
                }
                ctx.beginPath();
                ctx.moveTo(Math.round(fromX), Math.round(fromY));
                ctx.lineTo(Math.round(toX), Math.round(toY));
                ctx.stroke();
                ctx.restore();
                const distance_ft = _computeRulerDistanceFt(
                    { x: fromX, y: fromY }, { x: toX, y: toY },
                );
                const label = (_targetPicker.rangeFt > 0)
                    ? (_outOfRange
                        ? `⚠ ${distance_ft} ft / ${_targetPicker.rangeFt} ft`
                        : `${distance_ft} ft / ${_targetPicker.rangeFt} ft`)
                    : `${distance_ft} ft`;
                ctx.save();
                ctx.font = '11px sans-serif';
                ctx.textAlign = 'left';
                ctx.textBaseline = 'middle';
                const metrics = ctx.measureText(label);
                const padX = 6, chipH = 16;
                const chipW = metrics.width + padX * 2;
                const chipX = toX + 12;
                const chipY = toY + 12;
                ctx.fillStyle = 'rgba(20, 24, 28, 0.88)';
                ctx.strokeStyle = _outOfRange
                    ? 'rgba(245, 158, 11, 0.85)'
                    : 'rgba(220, 38, 38, 0.6)';
                ctx.lineWidth = 1;
                if (ctx.roundRect) {
                    ctx.beginPath();
                    ctx.roundRect(chipX, chipY, chipW, chipH, 4);
                    ctx.fill();
                    ctx.stroke();
                } else {
                    ctx.fillRect(chipX, chipY, chipW, chipH);
                    ctx.strokeRect(chipX, chipY, chipW, chipH);
                }
                ctx.fillStyle = _outOfRange ? '#fbbf24' : '#fff';
                ctx.fillText(label, chipX + padX, chipY + chipH / 2);
                ctx.restore();
            }
        }
        // v2.49.0 — persistent concentration AoE markers. Drawn after
        // tokens + targeting rings but before the picker preview, so
        // a fresh placement's preview circle is still visible on top.
        // Teal/cyan palette + dashed border distinguishes from the
        // flame-orange picker preview ("currently placing") and the
        // crimson targeting rings ("currently selected").
        if (_concentrationAoes.length) {
            for (const m of _concentrationAoes) {
                const lenPx = (m.size_ft / 5) * gridSize;
                let cx, cy;
                if (m.is_self_anchored && m.caster_char_id) {
                    const t = tokens.find(t => t.character_id === m.caster_char_id);
                    if (!t) continue;
                    cx = t.x + gridSize / 2;
                    cy = t.y + gridSize / 2;
                } else {
                    cx = m.center_x;
                    cy = m.center_y;
                }
                ctx.save();
                ctx.fillStyle = 'rgba(94,234,212,0.13)';   // teal — concentration aura
                ctx.strokeStyle = '#5eead4';
                ctx.lineWidth = 2;
                ctx.setLineDash([6, 4]);
                if (m.shape === 'sphere' || m.shape === 'self_sphere') {
                    ctx.beginPath();
                    ctx.arc(cx, cy, lenPx, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.stroke();
                } else if (m.shape === 'cube') {
                    const half = lenPx / 2;
                    ctx.beginPath();
                    ctx.rect(cx - half, cy - half, lenPx, lenPx);
                    ctx.fill();
                    ctx.stroke();
                }
                // Floating label so the GM knows which spell.
                if (m.spell_name) {
                    ctx.setLineDash([]);
                    ctx.font = 'bold 11px system-ui, sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    const label = `🌀 ${m.spell_name}`;
                    const metrics = ctx.measureText(label);
                    const padX = 5;
                    const w = metrics.width + padX * 2;
                    const h = 16;
                    const ly = cy - lenPx - 12;
                    ctx.fillStyle = 'rgba(15,23,42,0.85)';
                    ctx.beginPath();
                    if (ctx.roundRect) ctx.roundRect(cx - w/2, ly - h/2, w, h, 4);
                    else ctx.rect(cx - w/2, ly - h/2, w, h);
                    ctx.fill();
                    ctx.fillStyle = '#5eead4';
                    ctx.fillText(label, cx, ly);
                }
                ctx.restore();
            }
        }

        // T.5b → T.6: AoE picker preview. Drawn last so it sits on
        // top of tokens and targeting rings. Translucent flame-orange
        // fill + dashed crimson stroke so it reads as "damage zone".
        // Tokens whose centers fall inside get a faint highlight ring
        // so the GM sees which combatants the click will sweep up.
        if (_aoePicker.active && _aoePicker.cursor) {
            const cx = _aoePicker.cursor.x;
            const cy = _aoePicker.cursor.y;
            const len = _aoePicker._sizePx();
            // v2.49.78 — Phase 3A range ring. Render a translucent
            // green ring around the caster's token at the spell's
            // range AND detect when the cursor (= cast point for
            // sphere / cube; cursor-tip for cone / line) is outside
            // the ring → dim the AoE preview to red-on-grey so the
            // player gets pre-commit feedback that the placement
            // would 409 server-side.
            let _aoe_caster_pos = _aoePicker.origin;
            if (!_aoe_caster_pos && _aoePicker.casterCharId) {
                _aoe_caster_pos = _aoePicker._resolveOrigin(_aoePicker.casterCharId);
            }
            let _aoe_out_of_range = false;
            if (_aoePicker.range_ft > 0 && _aoe_caster_pos) {
                const _dist_ft = _computeRulerDistanceFt(_aoe_caster_pos, { x: cx, y: cy });
                _aoe_out_of_range = _dist_ft > _aoePicker.range_ft;
            }
            // Range ring — drawn BEFORE the AoE preview so the AoE
            // shape stays clearly on top. Skipped for Self spells
            // (range_ft == 0).
            if (_aoePicker.range_ft > 0 && _aoe_caster_pos) {
                const _ring_radius_px = (_aoePicker.range_ft / 5) * gridSize;
                ctx.save();
                ctx.fillStyle = 'rgba(74, 222, 128, 0.06)';
                ctx.strokeStyle = '#4ade80';
                ctx.lineWidth = 2;        // v2.49.144 HD polish
                ctx.lineCap = 'round';    // v2.49.144 HD polish
                ctx.setLineDash([6, 4]);
                ctx.beginPath();
                ctx.arc(_aoe_caster_pos.x, _aoe_caster_pos.y,
                        _ring_radius_px, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
                ctx.restore();
            }
            // v2.49.150: caster→cursor ruler line for sphere / cube
            // placements (Fireball, Hypnotic Pattern, etc.) so the
            // player sees the distance to the AoE center. Cone / line
            // / self_* shapes already convey direction via their
            // shape outline — adding a separate ruler line there
            // would be visual noise. Color shifts to amber when out
            // of range (matches the AoE preview's dimmed state +
            // the v2.49.143 target-picker out-of-range warning).
            if (_aoe_caster_pos
                    && (_aoePicker.shape === 'sphere' || _aoePicker.shape === 'cube')
                    && Math.hypot(cx - _aoe_caster_pos.x, cy - _aoe_caster_pos.y) > 8) {
                ctx.save();
                ctx.lineCap = 'round';
                ctx.lineWidth = 2;
                if (_aoe_out_of_range) {
                    ctx.strokeStyle = 'rgba(245, 158, 11, 0.95)';
                    ctx.setLineDash([4, 3]);
                } else {
                    ctx.strokeStyle = 'rgba(220, 38, 38, 0.85)';
                    ctx.setLineDash([6, 4]);
                }
                ctx.beginPath();
                ctx.moveTo(Math.round(_aoe_caster_pos.x), Math.round(_aoe_caster_pos.y));
                ctx.lineTo(Math.round(cx), Math.round(cy));
                ctx.stroke();
                ctx.restore();
                // Distance chip — same shape as the v2.49.143 target
                // picker's chip so the visual language is consistent
                // across pickers.
                const _aoeDistFt = _computeRulerDistanceFt(
                    _aoe_caster_pos, { x: cx, y: cy },
                );
                const _aoeLabel = (_aoePicker.range_ft > 0)
                    ? (_aoe_out_of_range
                        ? `⚠ ${_aoeDistFt} ft / ${_aoePicker.range_ft} ft`
                        : `${_aoeDistFt} ft / ${_aoePicker.range_ft} ft`)
                    : `${_aoeDistFt} ft`;
                ctx.save();
                ctx.font = '11px sans-serif';
                ctx.textAlign = 'left';
                ctx.textBaseline = 'middle';
                const _metrics = ctx.measureText(_aoeLabel);
                const _padX = 6, _chipH = 16;
                const _chipW = _metrics.width + _padX * 2;
                const _chipX = cx + 12;
                const _chipY = cy + 12;
                ctx.fillStyle = 'rgba(20, 24, 28, 0.88)';
                ctx.strokeStyle = _aoe_out_of_range
                    ? 'rgba(245, 158, 11, 0.85)'
                    : 'rgba(220, 38, 38, 0.6)';
                ctx.lineWidth = 1;
                if (ctx.roundRect) {
                    ctx.beginPath();
                    ctx.roundRect(_chipX, _chipY, _chipW, _chipH, 4);
                    ctx.fill();
                    ctx.stroke();
                } else {
                    ctx.fillRect(_chipX, _chipY, _chipW, _chipH);
                    ctx.strokeRect(_chipX, _chipY, _chipW, _chipH);
                }
                ctx.fillStyle = _aoe_out_of_range ? '#fbbf24' : '#fff';
                ctx.fillText(_aoeLabel, _chipX + _padX, _chipY + _chipH / 2);
                ctx.restore();
            }
            ctx.save();
            if (_aoe_out_of_range) {
                // Dimmed preview — desaturated, lower-alpha, signals
                // "this placement will be rejected." Players still see
                // WHERE the AoE would land if they overrode.
                ctx.fillStyle = 'rgba(120, 120, 120, 0.12)';
                ctx.strokeStyle = '#888';
                ctx.globalAlpha = 0.65;
            } else {
                ctx.fillStyle = 'rgba(220,38,38,0.18)';
                ctx.strokeStyle = '#dc2626';
            }
            ctx.lineWidth = 2.5;
            ctx.setLineDash([8, 6]);
            if (_aoePicker.shape === 'sphere') {
                ctx.beginPath();
                ctx.arc(cx, cy, len, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            } else if (_aoePicker.shape === 'cone' && _aoePicker.origin) {
                // Axis = origin → cursor (unit), perp = axis rotated 90°.
                // Far corners at origin + axis*L ± perp*(L/2) — PHB
                // cone template, width-at-distance d = d.
                const ox = _aoePicker.origin.x, oy = _aoePicker.origin.y;
                const adx = cx - ox, ady = cy - oy;
                const amag = Math.hypot(adx, ady) || 1;
                const ax = adx / amag, ay = ady / amag;
                const px = -ay, py = ax;
                const tipX  = ox + ax * len;
                const tipY  = oy + ay * len;
                const halfW = len / 2;
                const leftX  = tipX + px * halfW, leftY  = tipY + py * halfW;
                const rightX = tipX - px * halfW, rightY = tipY - py * halfW;
                ctx.beginPath();
                ctx.moveTo(ox, oy);
                ctx.lineTo(leftX,  leftY);
                ctx.lineTo(rightX, rightY);
                ctx.closePath();
                ctx.fill();
                ctx.stroke();
                // Small dot at origin so the caster's token has a
                // visible "this is where the cone starts" marker.
                ctx.setLineDash([]);
                ctx.beginPath();
                ctx.arc(ox, oy, 4, 0, Math.PI * 2);
                ctx.fillStyle = '#dc2626';
                ctx.fill();
            } else if (_aoePicker.shape === 'cube') {
                // Axis-aligned square centered on cursor. No rotation
                // — 5e cubes don't tilt relative to the grid.
                const half = len / 2;
                ctx.beginPath();
                ctx.rect(cx - half, cy - half, len, len);
                ctx.fill();
                ctx.stroke();
            } else if (_aoePicker.shape === 'self_sphere' && _aoePicker.origin) {
                // Emanation: filled circle anchored at the caster's
                // token center, ignoring cursor position. Cursor only
                // serves as the click-to-confirm gesture.
                const ox = _aoePicker.origin.x, oy = _aoePicker.origin.y;
                ctx.beginPath();
                ctx.arc(ox, oy, len, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.beginPath();
                ctx.arc(ox, oy, 4, 0, Math.PI * 2);
                ctx.fillStyle = '#dc2626';
                ctx.fill();
            } else if (_aoePicker.shape === 'line' && _aoePicker.origin) {
                // Rectangle from origin along aim axis: length × width.
                // Four corners at origin ± perp*(W/2) and origin +
                // axis*L ± perp*(W/2).
                const ox = _aoePicker.origin.x, oy = _aoePicker.origin.y;
                const adx = cx - ox, ady = cy - oy;
                const amag = Math.hypot(adx, ady) || 1;
                const ax = adx / amag, ay = ady / amag;
                const px = -ay, py = ax;
                const halfW = (_aoePicker.secondary_ft / 5) * gridSize / 2;
                const farX = ox + ax * len, farY = oy + ay * len;
                ctx.beginPath();
                ctx.moveTo(ox  + px * halfW, oy  + py * halfW);
                ctx.lineTo(farX + px * halfW, farY + py * halfW);
                ctx.lineTo(farX - px * halfW, farY - py * halfW);
                ctx.lineTo(ox  - px * halfW, oy  - py * halfW);
                ctx.closePath();
                ctx.fill();
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.beginPath();
                ctx.arc(ox, oy, 4, 0, Math.PI * 2);
                ctx.fillStyle = '#dc2626';
                ctx.fill();
            } else if (_aoePicker.shape === 'self_cube' && _aoePicker.origin) {
                // Same rectangle as line, but width = length (square
                // cross-section). Thunderwave-style: one face of the
                // cube touches the caster's square; the cube extends
                // in the cursor direction.
                const ox = _aoePicker.origin.x, oy = _aoePicker.origin.y;
                const adx = cx - ox, ady = cy - oy;
                const amag = Math.hypot(adx, ady) || 1;
                const ax = adx / amag, ay = ady / amag;
                const px = -ay, py = ax;
                const halfW = len / 2;
                const farX = ox + ax * len, farY = oy + ay * len;
                ctx.beginPath();
                ctx.moveTo(ox  + px * halfW, oy  + py * halfW);
                ctx.lineTo(farX + px * halfW, farY + py * halfW);
                ctx.lineTo(farX - px * halfW, farY - py * halfW);
                ctx.lineTo(ox  - px * halfW, oy  - py * halfW);
                ctx.closePath();
                ctx.fill();
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.beginPath();
                ctx.arc(ox, oy, 4, 0, Math.PI * 2);
                ctx.fillStyle = '#dc2626';
                ctx.fill();
            }
            ctx.restore();
            // Highlight tokens inside the shape using the same hit-test
            // logic as commit().
            tokens.forEach(t => {
                if (t.is_hidden && !ME.isGm) return;
                if (!_aoePicker._tokenInShape(t, cx, cy)) return;
                const tcx = t.x + gridSize / 2;
                const tcy = t.y + gridSize / 2;
                const tr = (gridSize * t.size) / 2 - 4;
                ctx.save();
                ctx.lineWidth = 2.5;
                ctx.strokeStyle = '#fbbf24';
                ctx.shadowColor = '#fbbf24';
                ctx.shadowBlur = 8;
                ctx.beginPath();
                ctx.arc(tcx, tcy, tr + 6, 0, Math.PI * 2);
                ctx.stroke();
                ctx.restore();
            });
        }

        // v2.49.71 — Ruler tool overlay (Phase 1 of docs/plans/ruler-and-range.md).
        // Drawn last so it sits on top of every other canvas overlay.
        // Renders when EITHER (a) the picker is active and has at least
        // one committed point (the cursor or the second committed point
        // is the line's other end) OR (b) the picker just committed and
        // the 3 s freeze-ghost is still up (`points.length === 2` after
        // active flipped false).
        if (_rulerPicker.points.length >= 1) {
            // v2.49.83 Phase 3D — generalised render. Build an
            // "effective path" array including each committed point
            // PLUS the live cursor (if still in active mode AND the
            // cursor is set). Then draw circles, segments, and chips
            // by walking the path. Works the same for single-segment
            // (2 points, possibly with cursor as point #2) and
            // multi-segment (N committed points + cursor).
            const pts = _rulerPicker.points.slice();
            // Append cursor only while the picker is ACTIVELY collecting
            // points (not during the 3 s freeze). In multi-segment mode
            // the cursor tracks the "next segment" preview; in single-
            // segment mode it stands in for point #2 before commit.
            const showingCursor = _rulerPicker.active && _rulerPicker.cursor
                && (_rulerPicker.points.length < (_rulerPicker.multiSegment ? 1000 : 2));
            const tailIsCursor = showingCursor && pts.length >= 1;
            if (tailIsCursor) pts.push(_rulerPicker.cursor);
            ctx.save();
            // Segment lines.
            // v2.49.144: HD polish — round caps + round joins so
            // multi-segment paths read as smooth strokes instead of
            // pixel-sharp corners. Endpoints pixel-snap for crisp
            // dash rendering. Pre-existing 2px width kept (already HD).
            ctx.strokeStyle = '#4ade80';
            ctx.lineWidth = 2;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.setLineDash([8, 5]);
            for (let i = 0; i < pts.length - 1; i++) {
                ctx.beginPath();
                ctx.moveTo(Math.round(pts[i].x), Math.round(pts[i].y));
                ctx.lineTo(Math.round(pts[i + 1].x), Math.round(pts[i + 1].y));
                ctx.stroke();
            }
            ctx.setLineDash([]);
            // Per-point circles. Committed points = filled; the tail
            // (cursor preview, if any) = open ring.
            for (let i = 0; i < pts.length; i++) {
                const isCursorTail = tailIsCursor && i === pts.length - 1;
                ctx.beginPath();
                ctx.arc(pts[i].x, pts[i].y, 5, 0, Math.PI * 2);
                if (isCursorTail) {
                    ctx.lineWidth = 2;
                    ctx.stroke();
                } else {
                    ctx.fillStyle = '#4ade80';
                    ctx.fill();
                }
            }
            // Per-segment midpoint chips. Each chip shows the segment's
            // length. For single-segment that's the only chip; for
            // multi-segment the cursor also gets a "total" chip below.
            ctx.font = '12px sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            let totalFt = 0;
            for (let i = 0; i < pts.length - 1; i++) {
                const a = pts[i], b = pts[i + 1];
                const segFt = _computeRulerDistanceFt(a, b);
                totalFt += segFt;
                const midX = (a.x + b.x) / 2;
                const midY = (a.y + b.y) / 2;
                const label = `${segFt} ft`;
                _drawRulerChip(ctx, label, midX, midY);
            }
            totalFt = Math.round(totalFt * 10) / 10;
            // Total chip at the cursor end (multi-segment only and
            // only when there are 3+ effective points — for single-
            // segment the midpoint chip IS the total).
            if (_rulerPicker.multiSegment && pts.length >= 3) {
                const tail = pts[pts.length - 1];
                _drawRulerChip(
                    ctx,
                    `Σ ${totalFt} ft`,
                    tail.x + 24, tail.y - 16,
                );
            }
            ctx.restore();
        }

        // v2.49.82 — Phase 3C cast-button hover ring. Drawn just
        // before the hover rangefinder so the ring sits as
        // "background context" under the rangefinder's line if both
        // happen to be visible. Suppressed by the same mutex set as
        // Phase 3B (drag / picker active).
        if (
            _castHoverRing.active &&
            _castHoverRing.casterPos &&
            _castHoverRing.range_ft > 0 &&
            !_aoePicker.active &&
            !_rulerPicker.active &&
            !dragging
        ) {
            const _radius_px = (_castHoverRing.range_ft / 5) * gridSize;
            ctx.save();
            // v2.49.144: HD polish — 1.5px → 2px + lineCap round so
            // the dashed ring matches the target picker's range ring.
            ctx.fillStyle = 'rgba(74, 222, 128, 0.06)';
            ctx.strokeStyle = '#4ade80';
            ctx.lineWidth = 2;
            ctx.lineCap = 'round';
            ctx.setLineDash([6, 4]);
            ctx.beginPath();
            ctx.arc(
                _castHoverRing.casterPos.x, _castHoverRing.casterPos.y,
                _radius_px, 0, Math.PI * 2,
            );
            ctx.fill();
            ctx.stroke();
            ctx.restore();
        }

        // v2.49.134: removed the v2.49.81 Phase 3B hover-rangefinder
        // block (thin distance line + "X ft" chip drawn from a
        // dbl-click-selected target to the cursor). User feedback —
        // it read as a phantom ruler appearing on token select. The
        // explicit ruler tool (toolbar button) still provides on-
        // demand measurements when needed; cast-button hover rings
        // (v2.49.82) still preview spell range. Just the auto-on-
        // target-set distance line + chip is gone.

        // v2.49.84 Phase 3E — remote ruler broadcasts. Render each
        // foreign measurement as a semi-transparent green overlay with
        // the broadcaster's name on the chip. Drawn AFTER local
        // overlays so a local active ruler sits on top of any remote
        // ghost. Drops expired entries (broadcaster commits froze for
        // 3 s + we keep showing for ~5 s after; expires_at is set to
        // 8 s past the most recent update).
        if (_remoteRulers.size) {
            const _now = Date.now();
            for (const [user_id, entry] of _remoteRulers) {
                if (entry.expires_at <= _now) {
                    _remoteRulers.delete(user_id);
                    continue;
                }
                if (!entry.points || entry.points.length < 1) continue;
                const pts = entry.points;
                ctx.save();
                // v2.49.144: HD polish matching the local ruler tool.
                ctx.globalAlpha = 0.6;
                ctx.strokeStyle = '#4ade80';
                ctx.lineWidth = 2;
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';
                ctx.setLineDash([8, 5]);
                for (let i = 0; i < pts.length - 1; i++) {
                    ctx.beginPath();
                    ctx.moveTo(Math.round(pts[i].x), Math.round(pts[i].y));
                    ctx.lineTo(Math.round(pts[i + 1].x), Math.round(pts[i + 1].y));
                    ctx.stroke();
                }
                ctx.setLineDash([]);
                ctx.fillStyle = '#4ade80';
                for (const p of pts) {
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
                    ctx.fill();
                }
                // Single chip at midpoint with total distance + name.
                if (pts.length >= 2) {
                    let totalFt = 0;
                    for (let i = 0; i < pts.length - 1; i++) {
                        totalFt += _computeRulerDistanceFt(pts[i], pts[i + 1]);
                    }
                    totalFt = Math.round(totalFt * 10) / 10;
                    const mid = pts[Math.floor(pts.length / 2)];
                    ctx.font = '12px sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    _drawRulerChip(ctx, `${totalFt} ft (${entry.user_name})`, mid.x, mid.y - 14);
                }
                ctx.restore();
            }
        }

        // v2.50.0 — grid coordinate labels drawn LAST so the gutter
        // sits on top of every other rendered element. Tokens sliding
        // along the map edge will pass under the strip, which is
        // intentional — the labels need to stay visible to fulfill
        // their "establish a fixed naming system" role.
        if (showGrid) drawGridCoords();

        _updateGifOverlay();
    }

    /* v2.8.1: movement breadcrumb. Drawn on top of tokens so the line
     * stays visible when a token sits on a waypoint. Reads
     * window._movementBreadcrumb populated by the battle IIFE in
     * tabletop.html — that file owns the source of truth for "who is
     * active" and their movement history; we just draw what it tells
     * us. Empty / missing breadcrumb is a no-op so the canvas still
     * renders fine before init starts. Each segment is colored green
     * (within speed_walk) or red (over the cap); v2.8.2 — a single
     * cumulative-distance label is drawn at the midpoint of the LAST
     * segment only, instead of one per segment, to reduce visual
     * clutter on multi-drag turns. */
    function drawMovementBreadcrumb() {
        const bc = window._movementBreadcrumb;
        if (!bc || !Array.isArray(bc.path) || bc.path.length < 2) return;
        const path = bc.path;
        // v2.8.3: effective cap = walking speed + Dash-granted extras.
        // Dash adds speed_walk on each use; the chip strip in the init
        // tracker still shows N/speed_walk (base) since that's the
        // standard reference, but the breadcrumb colors against the
        // post-Dash effective cap so a Dashed player sees green up to
        // their actual budget.
        const speedCap = (Number(bc.speed_walk) || 30) + (Number(bc.dash_bonus_ft) || 0);
        const half = gridSize / 2;

        // First pass: stroke every segment + arrowhead, tracking the
        // cumulative distance so the color tracks each segment's
        // end-of-segment total. The final cumulative survives into
        // the label-draw step below.
        let cumulative = 0;
        let lastSegment = null;
        let lastColor = '#4cd964';
        ctx.save();
        for (let i = 1; i < path.length; i++) {
            const a = path[i - 1];
            const b = path[i];
            const ax = a.x + half;
            const ay = a.y + half;
            const bx = b.x + half;
            const by = b.y + half;
            const dist = Number(b.distance_ft) || 0;
            cumulative += dist;
            const overCap = cumulative > speedCap + 0.001;
            const color = overCap ? '#ff6060' : '#4cd964';
            const glow = overCap ? 'rgba(255,96,96,0.6)' : 'rgba(76,217,100,0.55)';
            lastSegment = { ax, ay, bx, by };
            lastColor = color;

            // Line — wide stroke with a soft glow for visibility on busy maps.
            ctx.strokeStyle = glow;
            ctx.lineWidth = 8;
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(ax, ay);
            ctx.lineTo(bx, by);
            ctx.stroke();
            ctx.strokeStyle = color;
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(ax, ay);
            ctx.lineTo(bx, by);
            ctx.stroke();

            // Arrow head at the segment endpoint.
            const dx = bx - ax;
            const dy = by - ay;
            const len = Math.sqrt(dx * dx + dy * dy);
            if (len > 0) {
                const angle = Math.atan2(dy, dx);
                const ah = Math.min(14, len * 0.45);
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.moveTo(bx, by);
                ctx.lineTo(bx - ah * Math.cos(angle - Math.PI / 7),
                           by - ah * Math.sin(angle - Math.PI / 7));
                ctx.lineTo(bx - ah * Math.cos(angle + Math.PI / 7),
                           by - ah * Math.sin(angle + Math.PI / 7));
                ctx.closePath();
                ctx.fill();
            }
        }
        ctx.restore();

        // Second pass: one label at the midpoint of the LAST segment
        // showing the total cumulative distance. Pill background +
        // colored border to keep it readable on busy maps.
        if (lastSegment) {
            const mx = (lastSegment.ax + lastSegment.bx) / 2;
            const my = (lastSegment.ay + lastSegment.by) / 2;
            const label = `${Math.round(cumulative * 10) / 10} ft`;
            ctx.save();
            ctx.font = 'bold 13px system-ui, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            const padX = 6;
            const metrics = ctx.measureText(label);
            const w = metrics.width + padX * 2;
            const h = 18;
            ctx.fillStyle = 'rgba(20,20,28,0.85)';
            ctx.strokeStyle = lastColor;
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            const rx = mx - w / 2, ry = my - h / 2;
            ctx.roundRect ? ctx.roundRect(rx, ry, w, h, 4) : ctx.rect(rx, ry, w, h);
            ctx.fill();
            ctx.stroke();
            ctx.fillStyle = lastColor;
            ctx.fillText(label, mx, my);
            ctx.restore();
        }
    }

    /* v2.8.1: exposed so the battle IIFE in tabletop.html can trigger a
     * redraw after it updates window._movementBreadcrumb (e.g. at turn
     * transitions when the active combatant's path resets, or right
     * after a token_move arrives and the path grows). Idempotent and
     * cheap — calling it on every battle state change is fine. */
    window._renderCanvas = render;

    render();

    // ---------- Pan & zoom ----------
    let scale = 1;
    let panX = 0;
    let panY = 0;
    const MIN_SCALE = 0.15;
    const MAX_SCALE = 5;
    canvas.style.transformOrigin = '0 0';

    // GM-only view persistence. Key per (campaign, map) so each map
    // remembers its own pan/zoom; saves are debounced to avoid spamming
    // localStorage during a pinch or drag. Players are excluded —
    // they get the auto-center on first controlled token from v0.77.0,
    // and persisting on top of that creates a confusing jump on
    // session start.
    const VIEW_KEY = (ME && ME.isGm && typeof MAP_ID !== 'undefined' && MAP_ID)
        ? `simplevtt_gm_view_${CAMPAIGN_ID}_${MAP_ID}`
        : null;
    let _saveViewTimer = null;
    function scheduleSaveView() {
        if (!VIEW_KEY) return;
        clearTimeout(_saveViewTimer);
        _saveViewTimer = setTimeout(() => {
            try {
                localStorage.setItem(VIEW_KEY, JSON.stringify({
                    panX: panX, panY: panY, scale: scale,
                }));
            } catch (e) { /* quota / disabled — silently skip */ }
        }, 250);
    }

    function clampPan() {
        const paneRect = mapPane.getBoundingClientRect();
        if (!paneRect || paneRect.width <= 0 || paneRect.height <= 0) return;
        const margin = gridSize * scale;
        panX = Math.max(margin - MAP_W * scale, Math.min(paneRect.width  - margin, panX));
        panY = Math.max(margin - MAP_H * scale, Math.min(paneRect.height - margin, panY));
    }

    function applyTransform() {
        clampPan();
        const t = `translate(${panX}px, ${panY}px) scale(${scale})`;
        canvas.style.transform = t;
        if (bgLayer) { bgLayer.style.transform = t; }
        if (_gifOverlay) { _gifOverlay.style.transform = t; _gifOverlay.style.transformOrigin = '0 0'; }
        scheduleSaveView();
    }

    // Restore previously-saved view (GM only). Clamps scale into the
    // existing zoom bounds in case MIN_SCALE / MAX_SCALE moved since
    // the save. Pan is clamped by clampPan() inside applyTransform().
    if (VIEW_KEY) {
        try {
            const raw = localStorage.getItem(VIEW_KEY);
            if (raw) {
                const saved = JSON.parse(raw);
                if (saved
                    && Number.isFinite(saved.panX)
                    && Number.isFinite(saved.panY)
                    && Number.isFinite(saved.scale)) {
                    panX = saved.panX;
                    panY = saved.panY;
                    scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, saved.scale));
                    applyTransform();
                }
            }
        } catch (e) { /* corrupt JSON — ignore + overwrite on next move */ }
    }

    // ---------- Auto-center on the player's first controlled token ----------
    // Called after initial render (session start + page reloads on map
    // switch) and after every token_add WS message (same-map encounter
    // loads). Player-only — GMs control many tokens and would find the
    // auto-pan disruptive.

    function centerOnToken(token) {
        // No-op if the pane hasn't been laid out yet — the caller can
        // retry. Token world-coord center accounts for the gridSize
        // offset render uses, so the token visually lands at the center
        // of the viewport, not its top-left corner.
        if (!token) return false;
        const paneRect = mapPane.getBoundingClientRect();
        if (paneRect.width <= 0 || paneRect.height <= 0) return false;
        const tx = token.x + gridSize / 2;
        const ty = token.y + gridSize / 2;
        panX = paneRect.width / 2 - tx * scale;
        panY = paneRect.height / 2 - ty * scale;
        applyTransform();
        return true;
    }

    function findMyFirstControlledToken() {
        // First token in array order where the current user controls
        // the character, either via controller_user_id or via being the
        // owner of the linked character.
        if (!ME || ME.id == null) return null;
        for (const t of tokens) {
            if (t.controller_user_id != null && t.controller_user_id === ME.id) return t;
            if (t.character_id) {
                const c = characters.find(c => c.id === t.character_id);
                if (c && c.owner_user_id === ME.id) return t;
            }
        }
        return null;
    }

    function centerOnFirstControlledToken() {
        if (ME && ME.isGm) return;
        const t = findMyFirstControlledToken();
        if (t) centerOnToken(t);
    }

    // Initial autocenter — runs after the synchronous render() at
    // module init, so the map is drawn before we move the viewport.
    // setTimeout(0) lets the browser finish initial layout so
    // mapPane has a real width/height to center against.
    setTimeout(centerOnFirstControlledToken, 0);

    // Per-user zoom-speed multiplier. 1.0 = default. Applied to both
    // wheel (1.12 per notch base) and pinch (with extra baseline
    // dampening so iPad gestures aren't twitchy). Clamped on the
    // server but defended here against bad globals too.
    function _zoomSpeed() {
        const s = (ME && ME.zoomSpeed) || 1.0;
        return Math.max(0.3, Math.min(1.5, Number.isFinite(s) ? s : 1.0));
    }

    mapPane.addEventListener('wheel', (ev) => {
        ev.preventDefault();
        const rect = mapPane.getBoundingClientRect();
        const mouseX = ev.clientX - rect.left;
        const mouseY = ev.clientY - rect.top;
        // Per-notch factor scales with zoom_speed exponentially so 1.0
        // preserves the pre-v0.81 feel; <1 is gentler, >1 snappier.
        const baseFactor = Math.pow(1.12, _zoomSpeed());
        const factor = ev.deltaY < 0 ? baseFactor : 1 / baseFactor;
        const newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * factor));
        panX = mouseX - (mouseX - panX) * (newScale / scale);
        panY = mouseY - (mouseY - panY) * (newScale / scale);
        scale = newScale;
        applyTransform();
    }, { passive: false });

    // v2.21.0 Phase T.0: right-click opens the character or monster
    // sheet. Was a bare preventDefault — double-click used to open the
    // sheet, but T.0 took that gesture for targeting.
    //
    // v2.21.1 fix-up:
    // - Also listens on ``mapPane`` (the parent of canvas) so the
    //   contextmenu fires even if some overlay sits between canvas
    //   and the cursor.
    // - Also handles NPC tokens (``token_template_id``) — opens the
    //   monster sheet via the existing v2.3.15 drawer link pattern.
    //   Originally only PC sheets were wired up.
    // - Falls back to a synthetic anchor click for the actual
    //   navigation so the GM's iframe-drawer interceptor (the
    //   ``a.character-sheet-link`` / ``a.monster-sheet-link``
    //   delegated handler in tabletop.html) catches it. That works
    //   around popup blockers AND gives the GM the in-pane drawer
    //   view they're used to from the init-tracker 📋 Sheet button.
    function _openSheetForToken(token) {
        if (!token) return false;
        if (token.is_hidden && !ME.isGm) return false;
        let url, cls, name;
        if (token.character_id) {
            url = `/campaign/${CAMPAIGN_ID}/character/${token.character_id}/sheet`;
            cls = 'character-sheet-link';
            name = token.label || '';
        } else if (token.token_template_id) {
            url = `/campaign/${CAMPAIGN_ID}/monster-template/${token.token_template_id}/sheet`;
            cls = 'monster-sheet-link';
            name = token.label || '';
        } else {
            return false;
        }
        // v2.49.6 — match the init tracker's "📋 Sheet" button: when
        // this token has a live combatant in init, append
        // ``?combatant_id=...`` so the server's v2.49.3 HP overlay
        // fires and the sheet shows the current HP (not the
        // template max). Same 3-way lookup the skull pass + AoE
        // picker use: source_token_id, character_id, or
        // template+label. Skipped when no battle is active or no
        // combatant matches — sheet falls back to the v2.49.3
        // default (template max for monsters; character sheet read
        // for PCs) without breaking anything.
        const battleC = (window.battle && window.battle.combatants) || [];
        let combatantId = null;
        for (const c of battleC) {
            if (c.source_token_id != null && c.source_token_id === token.id) { combatantId = c.id; break; }
            if (token.character_id && c.char_id === token.character_id) { combatantId = c.id; break; }
            if (token.token_template_id
                    && c.token_template_id === token.token_template_id
                    && c.name === token.label) { combatantId = c.id; break; }
        }
        if (combatantId) {
            url += (url.includes('?') ? '&' : '?')
                + 'combatant_id=' + encodeURIComponent(combatantId);
        }
        // Synthetic anchor click — the document-level interceptor in
        // tabletop.html picks it up and opens in the iframe drawer for
        // GMs; for non-GMs the anchor's target="_blank" falls through
        // to a new tab (the interceptor is GM-only).
        const a = document.createElement('a');
        a.href = url;
        a.target = '_blank';
        a.rel = 'noopener';
        a.className = cls;
        if (cls === 'character-sheet-link') a.dataset.characterName = name;
        else a.dataset.monsterName = name;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        a.remove();
        return true;
    }
    // v2.21.2: debounce flag to prevent double-fire when both
    // ``contextmenu`` and ``pointerdown`` fire for the same gesture
    // (iPad Pro Magic Keyboard trackpad dispatches both).
    let _lastSheetOpenAt = 0;
    function _handleRightClick(ev) {
        ev.preventDefault();
        // T.5b: right-click during AoE placement cancels the picker
        // instead of opening a sheet; the mousedown handler also
        // suppresses the would-be pan-start.
        if (_aoePicker.active) {
            _aoePicker.cancel();
            return;
        }
        // v2.49.71: right-click in ruler mode cancels the measurement.
        if (_rulerPicker.active) {
            _rulerPicker.cancel();
            return;
        }
        // v2.49.135: right-click in target-picker mode decrements the
        // count on the token under the cursor (the "undo last pick"
        // gesture per the picker hint). Falls through to sheet-open
        // only when the click is on empty space (no token under the
        // cursor) — that way a misclick on a non-token area cancels
        // the picker via the Escape key path.
        if (_targetPicker.active) {
            const [x, y] = clientToCanvas(ev);
            const consumed = _targetPicker.removePick(x, y);
            if (!consumed) {
                // Right-click on empty canvas = cancel the picker.
                _targetPicker.cancel();
            }
            return;
        }
        if (Date.now() - _lastSheetOpenAt < 300) return;
        const [x, y] = clientToCanvas(ev);
        for (let i = tokens.length - 1; i >= 0; i--) {
            const t = tokens[i];
            if (!pointInToken(x, y, t)) continue;
            if (_openSheetForToken(t)) {
                _lastSheetOpenAt = Date.now();
                return;
            }
        }
    }
    canvas.addEventListener('contextmenu', _handleRightClick);
    // Defense-in-depth: also listen on mapPane in case overlays sit
    // between the cursor and the canvas at right-click time.
    mapPane.addEventListener('contextmenu', _handleRightClick);

    // v2.21.2 / v2.47.2 fix: iPad Pro Magic Keyboard trackpad fires
    // ``pointerdown`` with ``button === 2`` and ``pointerType ==
    // 'mouse'`` for two-finger tap / Control+click, but iOS Safari
    // sometimes suppresses the subsequent ``contextmenu`` event
    // (intercepted by the system text-selection long-press menu), so
    // this pointerdown path was added to cover the trackpad gesture.
    //
    // v2.47.2 — gate on ``navigator.maxTouchPoints > 0`` so this
    // handler only fires on touch-capable devices (iPad). On desktop
    // mice, ``_handleRightClick`` calls ``preventDefault()`` which
    // per the W3C Pointer Events spec suppresses the subsequent
    // ``mousedown`` — and that mousedown is what starts pan. So on
    // desktop, let the contextmenu handler do the work (it fires
    // after mouseup, so pan completes first) and skip pointerdown
    // entirely.
    function _handleRightClickPointer(ev) {
        if (ev.button !== 2) return;            // only right button
        if (ev.pointerType === 'touch') return; // touchscreen tap, not trackpad
        if (!navigator.maxTouchPoints) return;  // desktop mouse — contextmenu handles it
        _handleRightClick(ev);
    }
    canvas.addEventListener('pointerdown', _handleRightClickPointer);
    mapPane.addEventListener('pointerdown', _handleRightClickPointer);

    // ---------- Drag handling ----------
    let dragging = null;     // { token, offsetX, offsetY }
    let panning = null;      // { startX, startY }

    function pointInToken(x, y, t) {
        const cx = t.x + gridSize / 2, cy = t.y + gridSize / 2;
        const r = (gridSize * t.size) / 2 - 4;
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r;
    }

    function canMove(t) {
        if (ME.isGm) return true;
        if (t.is_hidden) return false;
        if (t.controller_user_id != null && t.controller_user_id === ME.id) return true;
        if (!t.character_id) return false;
        const c = characters.find(c => c.id === t.character_id);
        return c && c.owner_user_id === ME.id;
    }

    function clientToCanvas(ev) {
        const rect = canvas.getBoundingClientRect();
        return [
            (ev.clientX - rect.left) / scale,
            (ev.clientY - rect.top) / scale,
        ];
    }

    // World-space coordinate at the center of what the GM is currently
    // looking at (the map-pane viewport, accounting for pan + zoom).
    // Used by token-add flows so new tokens land where the GM is looking
    // instead of the (often offscreen) geometric center of the map.
    function viewportCenterWorld() {
        const paneRect = mapPane.getBoundingClientRect();
        const canvasRect = canvas.getBoundingClientRect();
        const screenCx = paneRect.left + paneRect.width / 2;
        const screenCy = paneRect.top + paneRect.height / 2;
        return {
            x: (screenCx - canvasRect.left) / scale,
            y: (screenCy - canvasRect.top) / scale,
        };
    }
    window.vttViewportCenterWorld = viewportCenterWorld;

    canvas.addEventListener('mousedown', (ev) => {
        // v2.49.71: ruler tool intercepts left-click mousedown so the
        // click-to-set-point gesture doesn't start a token drag or pan.
        // Mutually exclusive with the AoE picker per _rulerPicker.start().
        // v2.49.72: snap the click to the center of the grid cell under
        // the cursor so distances are clean multiples of 5 ft.
        if (_rulerPicker.active && ev.button === 0) {
            const [wx, wy] = clientToCanvas(ev);
            const snapped = _snapPointToGridCenter(wx, wy);
            _rulerPicker.addPoint(snapped.x, snapped.y);
            ev.preventDefault();
            return;
        }
        // T.5b: AoE picker intercepts left-click mousedown so the
        // commit-on-click gesture doesn't start a token drag. Right-
        // click is deliberately NOT intercepted here — it falls
        // through to the existing pan-start path. The contextmenu
        // handler below cancels the picker on right-click release,
        // so a stuck-active picker can never block panning.
        if (_aoePicker.active && ev.button === 0) {
            const [wx, wy] = clientToCanvas(ev);
            _aoePicker.commit(wx, wy);
            ev.preventDefault();
            return;
        }
        // v2.49.135: target picker intercepts left-click so the
        // click-to-pick gesture doesn't start a token drag. Right-
        // click is handled by _handleRightClick above (decrements or
        // cancels). The picker stays open until the required count
        // is reached (auto-commit), Enter is pressed, or Esc cancels.
        if (_targetPicker.active && ev.button === 0) {
            const [wx, wy] = clientToCanvas(ev);
            _targetPicker.addPick(wx, wy);
            ev.preventDefault();
            return;
        }
        // Click-to-set spawn: when armed (GM picked "Set" on a character
        // row in an encounter's spawn-points editor), eat the next
        // left-click on the canvas as the spawn coordinate for that
        // character. Snap to grid. Right-click still pans.
        if (spawnArmingCharId != null && spawnContext && spawnContext.encounterId && ev.button === 0) {
            const [wx, wy] = clientToCanvas(ev);
            const snappedX = Math.floor(wx / gridSize) * gridSize;
            const snappedY = Math.floor(wy / gridSize) * gridSize;
            const charId = spawnArmingCharId;
            const encId = spawnContext.encounterId;
            // Locally apply the new spawn so the marker shows up
            // immediately; the inline panel will re-fetch on the
            // server response to stay authoritative.
            spawnContext.spawns[String(charId)] = { x: snappedX, y: snappedY };
            render();
            window.vttCancelSpawnArming();
            ev.preventDefault();
            fetch(`/api/campaign/${CAMPAIGN_ID}/encounters/${encId}/spawn`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ character_id: charId, x: snappedX, y: snappedY }),
            }).then(r => {
                if (!r.ok) {
                    r.text().then(t => alert('Failed to set spawn: ' + t));
                    return;
                }
                if (window.vttSpawnPlacedCallback) {
                    window.vttSpawnPlacedCallback(encId, charId, snappedX, snappedY);
                }
            });
            return;
        }
        if (ev.button === 2) {
            panning = { startX: ev.clientX - panX, startY: ev.clientY - panY };
            canvas.style.cursor = 'move';
            ev.preventDefault();
            return;
        }
        const [x, y] = clientToCanvas(ev);
        for (let i = tokens.length - 1; i >= 0; i--) {
            const t = tokens[i];
            if (pointInToken(x, y, t) && canMove(t)) {
                // v2.8.3: remember pre-drag position so the overrun
                // modal's Cancel can snap the token back without a
                // server roundtrip.
                dragging = { token: t, offsetX: x - t.x, offsetY: y - t.y, origX: t.x, origY: t.y };
                canvas.style.cursor = 'grabbing';
                return;
            }
        }
    });

    // Encounter spawn-points helpers used by the encounter panel
    // controller (inline in tabletop.html). Set the context when the
    // edit form opens; clear it when the form closes. Arming + the
    // click-to-set landing flow are gated by the context being set.
    window.vttGetCharacters = function () { return characters; };
    // Lookup a token on the active map by character id (or null). Used
    // by the spawn-points editor so clicking Set on a character who's
    // already placed copies that token's position instead of requiring
    // a second click on the map.
    window.vttFindTokenForCharacter = function (charId) {
        const cid = parseInt(charId, 10);
        if (!cid) return null;
        return tokens.find(t => t.character_id === cid) || null;
    };
    window.vttSetSpawnContext = function (ctx) {
        // ctx: null | {encounterId, mapId, spawns: {char_id_str: {x,y}}}
        spawnContext = ctx ? {
            encounterId: ctx.encounterId,
            mapId: ctx.mapId != null ? ctx.mapId : null,
            spawns: ctx.spawns || {},
        } : null;
        if (!spawnContext && spawnArmingCharId != null) {
            window.vttCancelSpawnArming();
        }
        render();
    };
    window.vttArmSpawn = function (charId) {
        if (!spawnContext) {
            // Caller forgot to set the context first — no-op to avoid
            // arming with nowhere to send the click.
            return;
        }
        spawnArmingCharId = parseInt(charId, 10) || null;
        document.body.classList.toggle('spawn-arming', spawnArmingCharId != null);
        const banner = document.getElementById('spawn-arm-banner');
        const nameEl = document.getElementById('spawn-arm-name');
        if (banner) banner.style.display = spawnArmingCharId ? '' : 'none';
        if (nameEl && spawnArmingCharId) {
            const ch = characters.find(c => c.id === spawnArmingCharId);
            nameEl.textContent = ch ? ch.name : 'player';
        }
    };
    window.vttCancelSpawnArming = function () {
        spawnArmingCharId = null;
        document.body.classList.remove('spawn-arming');
        const banner = document.getElementById('spawn-arm-banner');
        if (banner) banner.style.display = 'none';
    };
    document.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape' && _aoePicker.active) {
            _aoePicker.cancel();
            return;
        }
        // v2.49.71: Esc cancels an active ruler measurement too.
        if (ev.key === 'Escape' && _rulerPicker.active) {
            _rulerPicker.cancel();
            return;
        }
        // v2.49.135: Esc cancels an active target-picker; Enter
        // commits the picks so far (under-quota commits allowed).
        if (_targetPicker.active) {
            if (ev.key === 'Escape') {
                _targetPicker.cancel();
                return;
            }
            if (ev.key === 'Enter' || ev.key === 'NumpadEnter') {
                if (_targetPicker._totalPicked() > 0) _targetPicker.commit();
                else _targetPicker.cancel();
                return;
            }
        }
        if (ev.key === 'Escape' && spawnArmingCharId != null) {
            window.vttCancelSpawnArming();
        }
    });

    canvas.addEventListener('mousemove', (ev) => {
        // v2.49.71: when the ruler picker is live AND we have one
        // committed point, follow the cursor for the live-distance
        // preview to the would-be second point. Same render-loop
        // re-entry pattern as the AoE picker below.
        // v2.49.72: snap the cursor preview to the grid-cell center so
        // the live distance label matches what the committing click
        // would actually produce.
        // v2.49.83 Phase 3D: multi-segment mode tracks the cursor for
        // the live "next segment" preview at ANY waypoint count (not
        // just === 1).
        if (_rulerPicker.active && _rulerPicker.points.length >= 1
                && (_rulerPicker.points.length === 1 || _rulerPicker.multiSegment)) {
            const [wx, wy] = clientToCanvas(ev);
            _rulerPicker.cursor = _snapPointToGridCenter(wx, wy);
            render();
            return;
        }
        // T.5b: when the AoE picker is live, follow the cursor with
        // a preview circle by stashing the canvas-space pointer pos
        // and re-rendering. Re-enters the same render() path as the
        // rest of the canvas so the preview lives in the same draw
        // stack as targeting rings.
        if (_aoePicker.active) {
            const [wx, wy] = clientToCanvas(ev);
            _aoePicker.cursor = { x: wx, y: wy };
            render();
            return;
        }
        if (panning) {
            panX = ev.clientX - panning.startX;
            panY = ev.clientY - panning.startY;
            applyTransform();
            return;
        }
        if (!dragging) {
            // v2.49.134: the v2.49.81 Phase 3B hover-rangefinder pump
            // (set _hoverCursor + render on every mousemove while a
            // single target was selected) was removed alongside the
            // renderer block that consumed it — see the matching
            // comment in render() above. No mousemove work needed
            // when not dragging.
            // v2.49.138: target picker — when active, track the cursor
            // for two consumers: the caster→cursor ruler line (snapped
            // to the grid-cell center via _snapPointToGridCenter) and
            // the hover-token preview ring (raw cursor for hit-testing
            // against tokens via pointInToken). Both stored on the
            // picker; render() reads them per-pass.
            if (_targetPicker.active) {
                const [wx, wy] = clientToCanvas(ev);
                _targetPicker.cursor = _snapPointToGridCenter(wx, wy);
                _targetPicker.cursorRaw = { x: wx, y: wy };
                render();
            }
            return;
        }
        const [x, y] = clientToCanvas(ev);
        dragging.token.x = x - dragging.offsetX;
        dragging.token.y = y - dragging.offsetY;
        render();
    });

    canvas.addEventListener('mouseup', (ev) => {
        if (ev.button === 2) {
            panning = null;
            canvas.style.cursor = 'grab';
            return;
        }
        if (!dragging) return;
        const [sx, sy] = snapToGrid(dragging.token.x, dragging.token.y);
        dragging.token.x = sx;
        dragging.token.y = sy;
        const tok = dragging.token;
        const origX = dragging.origX;
        const origY = dragging.origY;
        dragging = null;
        canvas.style.cursor = 'grab';
        render();
        _commitTokenMove(tok, origX, origY, sx, sy);
    });

    /* v2.8.3: pre-commit gate for token drags. Computes the distance the
     * proposed move would add, looks up whether the dragger owns the
     * active combatant, and — if the move would push them past their
     * effective walking cap — shows the movement-overrun modal before
     * POSTing /move. Cancel snaps the token back to (origX, origY);
     * Move-anyway POSTs as-is; Take Dash marks the action chip + adds
     * speed_walk to dash_bonus_ft (via the battle-IIFE-exported
     * window._dashCombatant) before POSTing.
     *
     * GM bypass: GMs skip the modal. They're the rules authority, can
     * teleport tokens, etc. — gating would be friction.
     *
     * Non-active / off-turn drags: also skip the modal. The breadcrumb
     * only tracks active-combatant moves; gating off-turn drags would
     * be confusing.
     */
    function _commitTokenMove(token, origX, origY, sx, sy) {
        const tokenId = token.id;
        const postMove = () => {
            fetch(`/api/campaign/${CAMPAIGN_ID}/token/${tokenId}/move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ x: sx, y: sy }),
            });
        };
        const snapBack = () => {
            token.x = origX;
            token.y = origY;
            render();
        };

        // No gate when the dragger is GM, when window helpers aren't
        // loaded, when the modal helper isn't available, or when init
        // isn't actively running.
        const me = (typeof ME !== 'undefined' && ME) || {};
        if (me.isGm || typeof window._getActiveCombatant !== 'function'
                || typeof window.showMovementOverrunModal !== 'function') {
            postMove();
            return;
        }
        const active = window._getActiveCombatant();
        if (!active) { postMove(); return; }

        // Match this token to the active combatant. Source-token-id is
        // the unambiguous v2.6.2 path; fall back to char_id when an
        // older combatant pre-dates that field.
        const activeMatches = (
            (active.source_token_id != null && active.source_token_id === tokenId)
            || (active.char_id != null && active.char_id === token.character_id)
        );
        if (!activeMatches) { postMove(); return; }

        // Distance math mirrors the server-side derivation in /move:
        // Chebyshev for square grids, Euclidean otherwise. 5 ft per
        // grid cell.
        const dx = sx - origX;
        const dy = sy - origY;
        let distance = 0;
        if (gridSize > 0) {
            const cells = (gridType === 'square')
                ? Math.max(Math.abs(dx), Math.abs(dy)) / gridSize
                : Math.sqrt(dx * dx + dy * dy) / gridSize;
            distance = Math.round(cells * 5 * 10) / 10;
        }
        if (distance <= 0) { postMove(); return; }

        const econ = active.economy || {};
        const currentUsed = Number(econ.movement) || 0;
        const dashBonus = Number(econ.dash_bonus_ft) || 0;
        const speedWalk = Number(active.speed_walk) || 30;
        const effectiveCap = speedWalk + dashBonus;
        const projected = currentUsed + distance;
        if (projected <= effectiveCap + 0.001) { postMove(); return; }

        // Over the cap — show the modal.
        window.showMovementOverrunModal({
            characterName: active.name,
            currentUsed,
            distanceFt: distance,
            speedCap: speedWalk,
            dashed: dashBonus > 0,
            onCancel: snapBack,
            onMove: postMove,
            onDash: () => {
                if (typeof window._dashCombatant === 'function') {
                    window._dashCombatant(active);
                }
                postMove();
            },
        });
    }

    // Release pan/drag if mouse button is lifted outside the canvas
    document.addEventListener('mouseup', (ev) => {
        if (ev.button === 2 && panning) {
            panning = null;
            canvas.style.cursor = 'grab';
        }
    });

    // v2.21.0 Phase T.0: double-click now targets instead of opening
    // the sheet (right-click took over the sheet gesture). Shift held
    // = additive multi-target (Magic Missile, Eldritch Blast picking
    // 2 beams at Lv 5+, etc.). Hidden tokens skipped for non-GM.
    canvas.addEventListener('dblclick', (ev) => {
        // v2.49.153: while the target picker is active, swallow
        // dblclick so it doesn't bleed into the persistent _targeting
        // state. The browser dispatches both mousedown→mousedown
        // (which feed picker stacking via addPick) AND a dblclick
        // for any double-click gesture; without this guard, stacking
        // on a token by dbl-clicking would ALSO set the token as the
        // persistent target — and the first picker id would resolve
        // against that persistent target after the cast, leading to
        // "I picked the bandit but Tavik took damage."
        // v2.49.154: ALSO swallow if the picker just closed within
        // the last 500 ms. Single-target picker auto-commits on the
        // first click, so the second click of a dblclick lands when
        // ``active`` is already false — without this window check
        // the dblclick fires anyway and persistently targets the
        // token the player just picked.
        if (_targetPicker.active
                || (Date.now() - _targetPicker._justClosedAt < 500)) {
            ev.preventDefault();
            return;
        }
        const [x, y] = clientToCanvas(ev);
        for (let i = tokens.length - 1; i >= 0; i--) {
            const t = tokens[i];
            if (!pointInToken(x, y, t)) continue;
            if (t.is_hidden && !ME.isGm) continue;
            if (ev.shiftKey) _targeting.addTarget(t.id);
            else _targeting.setTarget(t.id);
            _maybeShowTargetingHint();
            return;
        }
    });

    // v2.21.0 Phase T.0: Escape clears the target list. Bound on
    // document so the chip × isn't the only way out. ``keydown``
    // captures during typing inside inputs (e.g. roll-expr field) but
    // pickers / inputs swallow Escape before it bubbles, so the chip
    // clear here only fires when no editor is focused.
    document.addEventListener('keydown', (ev) => {
        if (ev.key !== 'Escape') return;
        if (!_targeting.tokenIds.size) return;
        const a = document.activeElement;
        if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.isContentEditable)) {
            return;  // let inputs see their own Escape
        }
        _targeting.clear();
    });

    // ---------- Touch controls (iPad / tablet) ----------
    // One finger: drag token if started on a movable one, else pan.
    // Two fingers: pinch zoom around the gesture's center, with pan
    // adjusted so the world coord under the center stays put. A clean
    // single-finger tap (small movement, short duration) is treated
    // like a mouse click — fires spawn-arm if armed; pairs of taps
    // close together open the character sheet (double-tap = dblclick).
    // touch-action:none on #map-pane (CSS) suppresses the browser's
    // default scroll/zoom so these gestures own the pane.
    {
        let touchPan = null;
        let touchPinch = null;
        let touchDrag = null;
        let tapStart = null;
        let lastTap = { time: 0, x: 0, y: 0 };

        function touchDist(t1, t2) {
            return Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
        }
        function clientToCanvasXY(cx, cy) {
            const r = canvas.getBoundingClientRect();
            return [(cx - r.left) / scale, (cy - r.top) / scale];
        }

        mapPane.addEventListener('touchstart', (ev) => {
            if (ev.touches.length === 1) {
                const t = ev.touches[0];
                tapStart = { time: Date.now(), x: t.clientX, y: t.clientY };
                // v2.21.0 Phase T.0 fix-up (v2.21.1): the long-press →
                // openSheet timer was removed. iOS Safari blocks
                // ``window.open`` from async setTimeout callbacks (not
                // a user-initiated gesture by the time the timer fires)
                // AND the iOS native long-press menu on image elements
                // competes for the same gesture, so the long-press
                // implementation was unreliable in two distinct ways.
                // For now, sheet-open on touch falls back to the init
                // tracker's "📋 Sheet" button. A future commit can
                // introduce a two-finger tap or a long-press-on-empty-
                // map → "tap a token" mode that side-steps both issues.

                // Spawn click-to-set: a tap while armed consumes the touch.
                if (spawnArmingCharId != null && spawnContext && spawnContext.encounterId) {
                    const [wx, wy] = clientToCanvasXY(t.clientX, t.clientY);
                    const snappedX = Math.floor(wx / gridSize) * gridSize;
                    const snappedY = Math.floor(wy / gridSize) * gridSize;
                    const charId = spawnArmingCharId;
                    const encId = spawnContext.encounterId;
                    spawnContext.spawns[String(charId)] = { x: snappedX, y: snappedY };
                    render();
                    window.vttCancelSpawnArming();
                    ev.preventDefault();
                    fetch(`/api/campaign/${CAMPAIGN_ID}/encounters/${encId}/spawn`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ character_id: charId, x: snappedX, y: snappedY }),
                    }).then(r => {
                        if (!r.ok) { r.text().then(s => alert('Failed to set spawn: ' + s)); return; }
                        if (window.vttSpawnPlacedCallback) {
                            window.vttSpawnPlacedCallback(encId, charId, snappedX, snappedY);
                        }
                    });
                    tapStart = null;
                    return;
                }

                const [wx, wy] = clientToCanvasXY(t.clientX, t.clientY);
                for (let i = tokens.length - 1; i >= 0; i--) {
                    const tok = tokens[i];
                    if (pointInToken(wx, wy, tok) && canMove(tok)) {
                        // v2.8.3: remember pre-drag position for snap-back
                        // when the overrun modal's Cancel fires.
                        touchDrag = { token: tok, offsetX: wx - tok.x, offsetY: wy - tok.y, origX: tok.x, origY: tok.y };
                        ev.preventDefault();
                        return;
                    }
                }
                touchPan = {
                    startPanX: panX, startPanY: panY,
                    startTouchX: t.clientX, startTouchY: t.clientY,
                };
                ev.preventDefault();
                return;
            }
            if (ev.touches.length === 2) {
                // Drop any single-finger state — pinch wins.
                touchDrag = null;
                touchPan = null;
                tapStart = null;
                const [t1, t2] = ev.touches;
                const paneRect = mapPane.getBoundingClientRect();
                const midX = (t1.clientX + t2.clientX) / 2;
                const midY = (t1.clientY + t2.clientY) / 2;
                touchPinch = {
                    startDist: touchDist(t1, t2),
                    startScale: scale,
                    startPanX: panX,
                    startPanY: panY,
                    centerX: midX - paneRect.left,
                    centerY: midY - paneRect.top,
                };
                ev.preventDefault();
            }
        }, { passive: false });

        mapPane.addEventListener('touchmove', (ev) => {
            if (touchPinch && ev.touches.length >= 2) {
                const [t1, t2] = ev.touches;
                const newDist = touchDist(t1, t2);
                if (touchPinch.startDist > 0) {
                    // Pinch exponent: raw `newDist/startDist` is too
                    // twitchy on iPad. Multiply by a 0.6 baseline
                    // dampener × the user's zoom_speed multiplier so a
                    // default 1.0 setting feels comfortable and the
                    // slider tunes from there. Effective exponent
                    // range at default: 0.6 × {0.3..1.5} = {0.18..0.9}.
                    const exp = 0.6 * _zoomSpeed();
                    const ratio = Math.pow(newDist / touchPinch.startDist, exp);
                    const newScale = Math.max(
                        MIN_SCALE,
                        Math.min(MAX_SCALE, touchPinch.startScale * ratio)
                    );
                    // Anchor the gesture's center: same math the wheel
                    // handler uses, with the touch midpoint as the
                    // fixed screen point.
                    const cx = touchPinch.centerX;
                    const cy = touchPinch.centerY;
                    const factor = newScale / touchPinch.startScale;
                    panX = cx - (cx - touchPinch.startPanX) * factor;
                    panY = cy - (cy - touchPinch.startPanY) * factor;
                    scale = newScale;
                    applyTransform();
                }
                ev.preventDefault();
                return;
            }
            if (touchDrag && ev.touches.length === 1) {
                const t = ev.touches[0];
                const [wx, wy] = clientToCanvasXY(t.clientX, t.clientY);
                touchDrag.token.x = wx - touchDrag.offsetX;
                touchDrag.token.y = wy - touchDrag.offsetY;
                render();
                ev.preventDefault();
                return;
            }
            if (touchPan && ev.touches.length === 1) {
                const t = ev.touches[0];
                panX = touchPan.startPanX + (t.clientX - touchPan.startTouchX);
                panY = touchPan.startPanY + (t.clientY - touchPan.startTouchY);
                applyTransform();
                ev.preventDefault();
            }
        }, { passive: false });

        function endTouches(ev) {
            // Finalize token drag when the last finger lifts.
            if (touchDrag && ev.touches.length === 0) {
                const [sx, sy] = snapToGrid(touchDrag.token.x, touchDrag.token.y);
                touchDrag.token.x = sx;
                touchDrag.token.y = sy;
                const tok = touchDrag.token;
                const origX = touchDrag.origX;
                const origY = touchDrag.origY;
                touchDrag = null;
                render();
                tapStart = null;
                // v2.8.3: route through the shared pre-commit gate so
                // iPad / touch drags get the same overrun modal flow as
                // mouse drags. The helper handles snap-back on Cancel.
                _commitTokenMove(tok, origX, origY, sx, sy);
            }
            if (touchPan && ev.touches.length === 0) {
                touchPan = null;
            }
            // Pinch ending — if one finger remains, transition into pan
            // so the user can keep moving the map.
            if (touchPinch && ev.touches.length < 2) {
                touchPinch = null;
                if (ev.touches.length === 1) {
                    const t = ev.touches[0];
                    touchPan = {
                        startPanX: panX, startPanY: panY,
                        startTouchX: t.clientX, startTouchY: t.clientY,
                    };
                }
            }
            // Tap / double-tap detection: only fires when the lift moved
            // very little since touchstart (i.e., not a pan or drag).
            // v2.21.0 Phase T.0: double-tap now targets (was openSheet).
            // Sheet-open on touch falls back to the init-tracker
            // "📋 Sheet" button — see the touchstart comment for the
            // long-press attempt that was reverted in v2.21.1.
            if (tapStart && ev.changedTouches.length === 1 && ev.touches.length === 0) {
                const ct = ev.changedTouches[0];
                const moved = Math.hypot(ct.clientX - tapStart.x, ct.clientY - tapStart.y);
                const dt = Date.now() - tapStart.time;
                if (moved < 12 && dt < 350) {
                    const now = Date.now();
                    const dx = ct.clientX - lastTap.x;
                    const dy = ct.clientY - lastTap.y;
                    if (now - lastTap.time < 400 && Math.hypot(dx, dy) < 30) {
                        // Double-tap → target.
                        const [wx, wy] = clientToCanvasXY(ct.clientX, ct.clientY);
                        for (let i = tokens.length - 1; i >= 0; i--) {
                            const tok = tokens[i];
                            if (!pointInToken(wx, wy, tok)) continue;
                            if (tok.is_hidden && !ME.isGm) continue;
                            _targeting.setTarget(tok.id);
                            _maybeShowTargetingHint();
                            break;
                        }
                        lastTap = { time: 0, x: 0, y: 0 };
                    } else {
                        lastTap = { time: now, x: ct.clientX, y: ct.clientY };
                    }
                }
                tapStart = null;
            }
        }
        mapPane.addEventListener('touchend', endTouches);
        mapPane.addEventListener('touchcancel', endTouches);
    }

    // ---------- WebSocket ----------
    const wsProto = location.protocol === 'https:' ? 'wss://' : 'ws://';
    let ws;
    function connectWs() {
        ws = new WebSocket(`${wsProto}${location.host}/ws/campaign/${CAMPAIGN_ID}`);
        ws.onmessage = (ev) => {
            const msg = JSON.parse(ev.data);
            // Forward every message as a CustomEvent so other modules
            // (like audio.js) can react without re-opening the socket.
            try { document.dispatchEvent(new CustomEvent('vtt:ws-message', { detail: msg })); } catch (_) {}
            // When the GM ends the session, non-GM clients are bounced back
            // to the lobby (which will show the "Waiting" state). The GM's
            // tab stays put — they can immediately re-Start without losing
            // their setup view.
            if (msg.type === 'session_ended' && !ME.isGm) {
                location.href = '/';
                return;
            }
            // Encounter load swapped the active map under us. The canvas
            // wasn't built to swap maps mid-session (grid math, bg image,
            // dims all change), so the simplest correct path is a hard
            // reload — SSR rebuilds the page against the new active map
            // and the WS reconnects to seed battle state from the hub.
            if (msg.type === 'map_change') {
                location.reload();
                return;
            }
            if (msg.type === 'token_move') {
                const t = tokens.find(t => t.id === msg.data.id);
                if (t) { t.x = msg.data.x; t.y = msg.data.y; render(); }
            } else if (msg.type === 'token_add') {
                tokens.push(msg.data);
                renderTokenTracker();
                refreshPlaceButtons();
                render();
                // Encounter load cascades token_add per token — center
                // on the player's first controlled token as soon as
                // it appears. Idempotent for non-controlled tokens;
                // GM check inside the helper keeps this a player-only
                // behavior.
                centerOnFirstControlledToken();
            } else if (msg.type === 'token_delete') {
                tokens = tokens.filter(t => t.id !== msg.data.id);
                renderTokenTracker();
                refreshPlaceButtons();
                render();
            } else if (msg.type === 'token_update') {
                const t = tokens.find(t => t.id === msg.data.id);
                if (t) { Object.assign(t, msg.data); renderTokenTracker(); refreshPlaceButtons(); render(); }
            } else if (msg.type === 'roll') {
                appendRoll(msg.data);
                _focusRollLogIfLocal(msg.data && msg.data.user_id);
            } else if (msg.type === 'member_color_update') {
                const { user_id, color } = msg.data;
                if (color) USER_COLORS[user_id] = color;
                else delete USER_COLORS[user_id];
                // Only apply if there's no character-level color overriding it
                // (character_color_update handles that separately)
                document.querySelectorAll(`.roll-card-user[data-uid="${user_id}"]`).forEach(el => {
                    if (!el.dataset.charColor) el.style.color = color || '';
                });
            } else if (msg.type === 'character_color_update') {
                const { owner_user_id, color } = msg.data;
                if (owner_user_id == null) return;
                // Character color overrides player color; update all cards for this user
                document.querySelectorAll(`.roll-card-user[data-uid="${owner_user_id}"]`).forEach(el => {
                    const effective = color || USER_COLORS[owner_user_id] || '';
                    el.style.color = effective;
                    if (color) el.dataset.charColor = color;
                    else delete el.dataset.charColor;
                });
            } else if (msg.type === 'character_ring_update') {
                const { char_id, color, ring_style } = msg.data;
                const ch = charById[char_id];
                if (ch) {
                    if (color    !== undefined) ch.color      = color;
                    if (ring_style !== undefined) ch.ring_style = ring_style;
                }
                render();
            } else if (msg.type === 'roll_request') {
                appendRollRequest(msg.data);
                // Focus the roll log when the prompt is addressed AT
                // the local user — they're the one being asked to
                // roll, so seeing the prompt land helps them act.
                const tgt = msg.data && msg.data.target_user_ids;
                if (Array.isArray(tgt) && tgt.includes(ME.id)) {
                    _focusRollLogIfLocal(ME.id);
                }
            } else if (msg.type === 'spell_cast') {
                appendSpellCast(msg.data);
                _focusRollLogIfLocal(msg.data && msg.data.caster_user_id);
            } else if (msg.type === 'weapon_attack') {
                appendWeaponAttack(msg.data);
                _focusRollLogIfLocal(msg.data && msg.data.caster_user_id);
            } else if (msg.type === 'spell_slot_update') {
                // Forwarded as a CustomEvent above; the open mini-sheet listens
                // for it to update its pip row in place.
            } else if (msg.type === 'heal_applied') {
                _onHealApplied(msg.data);
            } else if (msg.type === 'spell_cast_target_updated') {
                _onSpellCastTargetUpdated(msg.data);
            } else if (msg.type === 'spell_cast_aoe_resolved') {
                _onSpellCastAoeResolved(msg.data);
            } else if (msg.type === 'concentration_aoe_update') {
                _concentrationAoes = (msg.data && Array.isArray(msg.data.markers))
                    ? msg.data.markers : [];
                try { render(); } catch (_) {}
            } else if (msg.type === 'feature_used') {
                _appendFeatureUsed(msg.data);
                _focusRollLogIfLocal(msg.data && msg.data.user_id);
            } else if (msg.type === 'presence_update') {
                _renderPresence(msg.data);
            } else if (msg.type === 'character_hp_update') {
                _onCharacterHpUpdate(msg.data);
            } else if (msg.type === 'character_death_save') {
                _onCharacterDeathSave(msg.data);
            } else if (msg.type === 'character_roll_state') {
                _onCharacterRollState(msg.data);
            } else if (msg.type === 'ruler_broadcast') {
                // v2.49.84 Phase 3E — remote ruler broadcasts. Drop
                // our own broadcasts since we already render them
                // locally; only foreign rulers populate _remoteRulers.
                _onRulerBroadcast(msg.data);
            }
        };
        ws.onclose = () => setTimeout(connectWs, 2000);
    }
    connectWs();

    function _appendSaveResultToSpellCard(r) {
        // If this roll's note is a response to one of our spell-cast save
        // prompts, append a "<roller>: <total> ✓/✗" line to that card.
        if (!r || !r.note) return;
        const ul = document.getElementById('roll-list');
        if (!ul) return;
        for (const li of ul.querySelectorAll('li[data-cast-id]')) {
            const meta = li._spellCast;
            if (!meta || !meta._saveLabel) continue;
            const prefix = `→ ${meta._saveLabel}`;
            if (!r.note.startsWith(prefix)) continue;
            const results = li.querySelector('.spell-cast-results');
            if (!results) continue;
            // v2.49.211 / v2.49.212: respect server-sent no_char_attribution
            // for monster rolls + prefer actor_name (the monster's display
            // name) — see matching note in the roll-log render at line ~3832.
            const dispName = r.char_name
                || (r.no_char_attribution
                    ? (r.actor_name || r.user_name || 'Player')
                    : (USER_CHAR_NAMES[r.user_id] || r.user_name || 'Player'));
            const passed = /✓ Pass/.test(r.note);
            const failed = /✗ Fail/.test(r.note);
            const outcome = passed ? '<span class="spell-cast-pass">✓ Save</span>'
                          : failed ? '<span class="spell-cast-fail">✗ Failed save</span>'
                          : '';
            const row = document.createElement('div');
            row.className = 'spell-cast-result-row';
            row.innerHTML = `<strong>${escapeHTML(dispName)}</strong>: ${r.total} &nbsp; ${outcome}`;
            results.appendChild(row);
            return;
        }
    }

    function _scrollRollLogToBottom() {
        const ul = document.getElementById('roll-list');
        if (!ul) return;
        const body = ul.closest('.drawer-body');
        if (body) body.scrollTop = body.scrollHeight;
    }

    // v2.28.0: roll-log persistence. Snapshot WS-only chat-card events
    // (spell_cast / weapon_attack / feature_used) to localStorage keyed
    // by campaign id so they survive page refreshes. On page load we
    // replay the saved entries through the same append fns so the
    // cards rebuild identically, with all buttons (Undo / Apply
    // Healing / Save prompts) freshly wired. Plain ``roll`` records
    // are NOT persisted here — the server-side render in
    // ``tabletop.html`` (Jinja ``{% for r in rolls %}``) already
    // surfaces the persistent roll history, so localStorage replay
    // would double-render them. Same for ``roll_request`` which is
    // stored in the RollRequest table. Capped at 100 most-recent
    // WS-only entries to bound storage; older entries roll off
    // FIFO-style. ``window._clearRollLog()`` flushes the buffer
    // (intended for a future GM "Clear log" button — callable from
    // the console today).
    const _ROLL_LOG_KEY = `simplevtt:rolllog:${CAMPAIGN_ID}`;
    const _ROLL_LOG_MAX = 100;
    let _rollLogHydrating = false;
    function _persistRollEntry(type, data) {
        if (_rollLogHydrating) return;
        try {
            const raw = localStorage.getItem(_ROLL_LOG_KEY);
            const entries = raw ? JSON.parse(raw) : [];
            if (!Array.isArray(entries)) return;
            entries.push({ type, data, ts: Date.now() });
            if (entries.length > _ROLL_LOG_MAX) {
                entries.splice(0, entries.length - _ROLL_LOG_MAX);
            }
            localStorage.setItem(_ROLL_LOG_KEY, JSON.stringify(entries));
        } catch (_) { /* private-mode localStorage etc. */ }
    }
    function _hydrateRollLog() {
        let entries;
        try {
            const raw = localStorage.getItem(_ROLL_LOG_KEY);
            if (!raw) return;
            entries = JSON.parse(raw);
        } catch (_) { return; }
        if (!Array.isArray(entries) || !entries.length) return;
        _rollLogHydrating = true;
        try {
            for (const e of entries) {
                try {
                    if (e.type === 'spell_cast')         appendSpellCast(e.data);
                    else if (e.type === 'weapon_attack') appendWeaponAttack(e.data);
                    else if (e.type === 'feature_used')  _appendFeatureUsed(e.data);
                    else if (e.type === 'heal_applied')  _onHealApplied(e.data);
                    else if (e.type === 'spell_cast_target_updated') _onSpellCastTargetUpdated(e.data);
                    else if (e.type === 'spell_cast_aoe_resolved') _onSpellCastAoeResolved(e.data);
                } catch (err) {
                    console.warn('[rolllog] hydrate skipped', e.type, err);
                }
            }
        } finally {
            _rollLogHydrating = false;
        }
    }
    // v2.48.6 — click any per-target AoE pill to toggle its
    // breakdown detail. Delegated on document so it survives card
    // re-renders (initial paint, /place_aoe resolution mutation,
    // localStorage replay on refresh). Detail is a sibling <span>
    // inside the pill button that starts ``display: none``.
    document.addEventListener('click', (ev) => {
        const pill = ev.target.closest && ev.target.closest('.per-target-pill');
        if (!pill) return;
        const detail = pill.querySelector('.pt-detail');
        if (!detail) return;
        const expanded = pill.dataset.expanded === '1';
        pill.dataset.expanded = expanded ? '0' : '1';
        detail.style.display = expanded ? 'none' : 'inline';
        // Bump pill font size when expanded so the math is readable.
        pill.style.fontSize = expanded ? '' : '13px';
    });

    window._clearRollLog = function () {
        try { localStorage.removeItem(_ROLL_LOG_KEY); } catch (_) {}
        const ul = document.getElementById('roll-list');
        if (ul) ul.innerHTML = '';
    };

    // v2.48.2 — auto-focus the roll log drawer when a broadcast that
    // ADDS an entry was triggered by the local user (their /roll, their
    // cast, their feature_used, or a roll_request addressed AT them).
    // Skipped during localStorage replay (we don't want to fight the
    // user's last-drawer preference on page load) and on broadcasts
    // from other users (their actions shouldn't yank this user's view
    // off whatever drawer they were already using). The roll log was
    // designed to be a sidebar — the user wants to see the result of
    // their click without manually switching tabs every time.
    function _focusRollLogIfLocal(actorUserId) {
        if (_rollLogHydrating) return;
        if (actorUserId == null) return;
        if (actorUserId !== ME.id) return;
        if (typeof window._openDrawerPanel === 'function') {
            try { window._openDrawerPanel('roll-log-drawer'); } catch (_) {}
        }
    }

    function appendRoll(r) {
        // Re-apply visibility filter on the client (server already does this
        // for non-broadcast targets but every client receives the same payload).
        if (!ME.isGm) {
            if (r.visibility === 'gm_only') return;
            if (r.visibility === 'gm_and_roller' && r.user_id !== ME.id) return;
        }
        _appendSaveResultToSpellCard(r);
        const visClass  = r.visibility === 'gm_only'      ? 'vis-gm-only'
                        : r.visibility === 'gm_and_roller' ? 'vis-gm-roller'
                        : '';
        const badgeText = r.visibility === 'gm_only'      ? 'GM only'
                        : r.visibility === 'gm_and_roller' ? 'GM + you'
                        : '';
        const now = new Date();
        const h = now.getHours(), m = now.getMinutes();
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12  = (h % 12) || 12;
        const hhmm = h12.toString().padStart(2,'0') + ':' + m.toString().padStart(2,'0') + ' ' + ampm;

        // Portrait and color — prefer values from the broadcast, fall back to local maps
        const portrait  = r.portrait_url || USER_PORTRAITS[r.user_id] || '';
        const color     = r.user_color   || USER_COLORS[r.user_id]   || '';
        // v2.49.211 / v2.49.212: monster rolls (skip_roll_state=true + no
        // character_id) come back from the server with
        // no_char_attribution=true; respect that by skipping the
        // USER_CHAR_NAMES fallback so the roll log doesn't surface the
        // GM's first owned PC ("Brother Tavik Stonebrow" in the demo) as
        // the rolled-by name. v2.49.212 also threads an `actor_name`
        // through the broadcast — the monster's name as it appeared on
        // the clicked mini-sheet ("Cult Acolyte") — so the rolled-by
        // slot surfaces THAT instead of the GM's user name. For PC rolls
        // both flags are absent / false and the original fallback chain
        // is preserved.
        const dispName  = r.char_name
            || (r.no_char_attribution
                ? (r.actor_name || r.user_name)
                : (USER_CHAR_NAMES[r.user_id] || r.user_name));
        const avatarInner = portrait
            ? `<img src="${escapeHTML(portrait)}" alt="">`
            : '🎲';

        const ul = document.getElementById('roll-list');
        const li = document.createElement('li');
        li.innerHTML = `
            <div class="roll-card ${visClass}">
                <div class="roll-card-total-col">
                    <span class="roll-card-total">${r.total}</span>
                </div>
                <div class="roll-card-right">
                    <div class="roll-card-header">
                        <div class="roll-card-avatar">${avatarInner}</div>
                        <span class="roll-card-user" data-uid="${r.user_id}"${color ? ` style="color:${escapeHTML(color)}"` : ''}>${escapeHTML(dispName)}</span>
                        ${badgeText ? `<span class="roll-card-badge">${badgeText}</span>` : ''}
                        <span class="roll-card-time">${hhmm}</span>
                    </div>
                    <div class="roll-card-body">
                        ${r.note ? `<div class="roll-card-note">${escapeHTML(r.note)}</div>` : ''}
                        <div class="result-pills">
                            <span class="result-pill">🎲 ${r.breakdown ? formatBreakdown(r.breakdown) : escapeHTML(r.expression || '')}</span>
                        </div>
                    </div>
                </div>
            </div>`;
        ul.appendChild(li);
        _scrollRollLogToBottom();
        // ``roll`` not persisted to localStorage — server pre-renders
        // rolls history via Jinja, so replay would double-render.
    }

    function appendRollRequest(req) {
        const ul = document.getElementById('roll-list');
        if (!ul) return;

        const now = new Date();
        const h = now.getHours(), m = now.getMinutes();
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12 = (h % 12) || 12;
        const timeStr = h12.toString().padStart(2, '0') + ':' + m.toString().padStart(2, '0') + ' ' + ampm;

        // Per-player targeting (added in 1.7.1). When the GM ticks specific
        // player checkboxes on the roll-request panel, the WS payload carries
        // `target_user_ids` so we render the Roll button only for those
        // players. An empty list (the default) keeps the legacy broadcast
        // behaviour — everyone sees the Roll button. The GM always sees the
        // Roll button regardless of targeting because they may be rolling for
        // an NPC token they control.
        const targetIds = Array.isArray(req.target_user_ids) ? req.target_user_ids : [];
        const targetNames = Array.isArray(req.target_user_names) ? req.target_user_names : [];
        const isTargeted = targetIds.length === 0 || targetIds.includes(ME.id) || ME.isGm;
        const targetLine = targetIds.length
            ? `<div class="roll-req-target" style="font-size:11px;color:var(--fg-mute);margin-top:2px;">
                   To: ${targetNames.map(n => escapeHTML(n)).join(', ')}
               </div>`
            : '';

        // Characters this user can roll as (GM sees all; players see only theirs)
        const myChars = ME.isGm
            ? characters.filter(c => c.owner_user_id != null)
            : characters.filter(c => c.owner_user_id === ME.id);

        let charSelectHtml = '';
        if (myChars.length > 1) {
            charSelectHtml = `<select class="roll-req-select">${
                myChars.map(c => `<option value="${c.id}">${escapeHTML(c.name)}</option>`).join('')
            }</select>`;
        } else if (myChars.length === 1) {
            charSelectHtml = `<input type="hidden" class="roll-req-select" value="${myChars[0].id}">
                <span class="roll-req-char-label">${escapeHTML(myChars[0].name)}</span>`;
        }

        const dcBadge = req.dc
            ? `<span class="roll-req-dc">DC ${req.dc}</span>`
            : '';

        const statLabel = req.stat_key
            ? req.stat_key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
            : '';
        const exprHint = statLabel
            ? `<div class="roll-req-expr">${escapeHTML(req.base_expression)} + ${statLabel}</div>`
            : `<div class="roll-req-expr">${escapeHTML(req.base_expression)}</div>`;

        const rollBtnHtml = isTargeted
            ? `<button class="roll-req-btn" type="button">🎲 Roll</button>`
            : `<span class="roll-req-not-targeted" style="font-size:11px;color:var(--fg-mute);font-style:italic;">Not your roll</span>`;

        const li = document.createElement('li');
        li.dataset.reqId = req.id;
        li.innerHTML = `
            <div class="roll-req-card">
                <div class="roll-req-header">
                    <span class="roll-req-icon">📋</span>
                    <span class="roll-req-creator">${escapeHTML(req.created_by_name)}</span>
                    <span class="roll-req-time">${timeStr}</span>
                </div>
                <div class="roll-req-body">
                    <div class="roll-req-label">${escapeHTML(req.label)}</div>
                    ${dcBadge}
                    ${exprHint}
                    ${targetLine}
                    <div class="roll-req-actions">
                        ${isTargeted ? charSelectHtml : ''}
                        ${rollBtnHtml}
                        <span class="roll-req-status"></span>
                    </div>
                </div>
            </div>`;

        const rollBtn = li.querySelector('.roll-req-btn');
        if (rollBtn) rollBtn.addEventListener('click', async () => {
            const sel = li.querySelector('.roll-req-select');
            const charId = sel ? (parseInt(sel.value) || null) : null;
            rollBtn.disabled = true;
            rollBtn.textContent = '…';
            const statusEl = li.querySelector('.roll-req-status');
            try {
                const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/roll_request/${req.id}/respond`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ character_id: charId }),
                });
                if (!resp.ok) throw new Error(await resp.text());
                rollBtn.textContent = '✓ Rolled';
                if (statusEl) statusEl.textContent = 'Result in log';
            } catch (e) {
                rollBtn.disabled = false;
                rollBtn.textContent = '🎲 Roll';
                if (statusEl) statusEl.textContent = '✗ Error';
                console.error(e);
            }
        });

        ul.appendChild(li);
        _scrollRollLogToBottom();
        // ``roll_request`` not persisted to localStorage — server
        // stores it in the RollRequest table (same reason as ``roll``).
    }

    // ---------- Toast (transient overlay notification) ----------
    function showToast(msg, kind) {
        let stack = document.getElementById('vtt-toast-stack');
        if (!stack) {
            stack = document.createElement('div');
            stack.id = 'vtt-toast-stack';
            document.body.appendChild(stack);
        }
        const t = document.createElement('div');
        t.className = 'vtt-toast' + (kind ? ' vtt-toast-' + kind : '');
        t.textContent = msg;
        stack.appendChild(t);
        // Force reflow so the fade-in transition runs
        // eslint-disable-next-line no-unused-expressions
        t.offsetHeight;
        t.classList.add('vtt-toast-show');
        setTimeout(() => {
            t.classList.remove('vtt-toast-show');
            setTimeout(() => t.remove(), 260);
        }, 3200);
    }
    window.showToast = showToast;

    // ---------- Spell-cast card ----------
    function _diceExprFromDamage(dmgStr) {
        const m = /(\d+d\d+(?:\s*[+-]\s*\d+)?)/.exec(dmgStr || '');
        return m ? m[1].replace(/\s+/g, '') : '';
    }

    // ---------- Action button renderer ----------
    // The shared helper lives in static/action_buttons.js (loaded before this
    // file by tabletop.html so window.renderActionButtons is available here
    // and on the character sheet). We just reference the global below.
    const renderActionButtons = window.renderActionButtons;

    // Build a synthetic single-Action from the legacy regex-derived WebSocket
    // payload fields so existing cast_spell broadcasts keep rendering buttons
    // even before the server emits `actions[]` natively for every spell.
    function _synthesizeCastAction(d) {
        return {
            id: 'cast',
            name: d.spell_name || 'Cast',
            damage: _diceExprFromDamage(d.spell_damage || ''),
            damage_type: '',
            save_ability: d.spell_save_ability || '',
            healing: (d.spell_healing || '').trim(),
            aoe_targets: d.spell_aoe_targets || 1,
            attack_roll: !!d.spell_attack_roll,
        };
    }

    // v2.23.0 Phase T.8: render a "→ NAME" target tag on chat cards.
    // Pulled directly from the broadcast's ``target_name`` field, which
    // every targeting-aware endpoint sets (/attack, /cast_spell,
    // /cast_hunters_mark, /cast_hex, /use_lay_on_hands, /use_bardic_
    // inspiration, /use_cutting_words). Empty string when no target
    // was set — caller renders nothing in that case.
    function _targetTagHtml(d) {
        const name = (d && (d.target_name || d.target_character_name)) || '';
        if (!name) return '';
        return `<span class="target-tag" title="Targeted: ${escapeHTML(name)}">→ ${escapeHTML(name)}</span>`;
    }

    // v2.26.0 Phase T.4: auto-heal line for spell_cast cards. Renders
    // "✚ Healed NAME for N HP (HP_BEFORE → HP_AFTER)" when /cast_spell
    // auto-applied a heal to the targeted combatant. Includes an
    // ↶ Undo button (reuses /undo_attack_damage which detects heal
    // entries via the is_heal flag and reverses by damaging the same
    // amount). Empty when no auto-heal happened.
    // v2.43.0: oversized pill row for spell-cast auto-effect outcomes.
    // Replaces the v2.42.0 ▼ Result collapsible + the v2.42.0 simple-
    // mode small chip row. One pill per consequence; no drop-down,
    // no toggle — always rendered the same way. The pills are big
    // enough to read across the table and carry their own colors via
    // the chip-* modifier classes (heal / hit / miss / crit / damage /
    // buff / prompt / undo). Returns '' when the cast produced no
    // auto-effects so utility-only spells (Mage Armor, Misty Step)
    // render without an empty pill row.
    // v2.48.7 — every cast-card pill that has roll math is now click-
    // to-expand. Builds a ``<button class="result-pill chip-X
    // per-target-pill">`` so the existing v2.48.6 delegated click
    // handler toggles the detail span. When ``detail`` is empty the
    // pill renders as a non-expandable ``<span>`` (no click target).
    function _buildPill(cls, headerHtml, detailText) {
        if (detailText) {
            return (
                `<button type="button" class="result-pill ${cls} per-target-pill" data-expanded="0"`
                + ` title="Click for roll math">`
                + `<span class="pt-header">${headerHtml}</span>`
                + `<span class="pt-detail" style="display:none;font-size:11px;color:var(--fg-mute);margin-left:8px;border-left:1px solid currentColor;padding-left:8px;opacity:.85;">${escapeHTML(detailText)}</span>`
                + `</button>`
            );
        }
        return `<span class="result-pill ${cls}">${headerHtml}</span>`;
    }

    function _spellResultPillsHtml(d) {
        if (!d) return '';
        const pills = [];
        // v2.48.0 Phase T.5e: pending AoE placement. Render a "📍
        // Place AoE" button instead of any other pills — the cast
        // hasn't resolved targets yet. The button is enabled only
        // for the caster or the GM; everyone else sees a disabled
        // "Waiting for placement" pill so they know the cast is
        // still pending. The actual click handler is wired in
        // appendSpellCast below (so it can call _openAoePicker and
        // POST /place_aoe).
        // v2.48.0 — pending AoE placement. v2.48.4 — also fires for
        // "legacy" AoE cards (cast in localStorage before the v2.48.0
        // flow shipped, so the broadcast lacked the pending flag) so
        // those cards aren't stuck with an empty pill row. The click
        // handler surfaces a toast if /place_aoe can't find the stash
        // (the server doesn't know about pre-v2.48.0 casts) so the GM
        // can clear the log.
        const _hasResolvedTargets = Array.isArray(d.auto_save_targets) && d.auto_save_targets.length > 0;
        const _isAoeCard = Boolean(d.area_shape) && Number(d.area_size_ft) > 0;
        // ``pending_aoe_placement === false`` (server-set after the
        // /place_aoe broadcast resolves) means the cast WAS placed —
        // even if it caught 0 targets. ``undefined`` means we don't
        // know (legacy data); treat that AS pending so the GM can
        // still place.
        const _wasPlaced = d.pending_aoe_placement === false;
        const _isPending = d.pending_aoe_placement === true
            || (d.pending_aoe_placement === undefined && _isAoeCard && !_hasResolvedTargets);
        if (_isPending) {
            const isCaster = typeof ME !== 'undefined' && ME && ME.id === d.caster_user_id;
            const canPlace = isCaster || (ME && ME.isGm);
            if (canPlace) {
                const label = `📍 Place ${escapeHTML(d.area_shape || 'AoE')}`;
                pills.push(
                    `<button type="button" class="result-pill chip-prompt spell-cast-place-aoe" data-cast-id="${escapeHTML(d.id || '')}" title="Open the placement picker on the canvas">${label}</button>`
                );
            } else {
                pills.push(
                    `<span class="result-pill chip-prompt">⏳ Awaiting placement…</span>`
                );
            }
            return pills.length ? `<div class="result-pills">${pills.join('')}</div>` : '';
        }
        // AoE that was placed but caught no targets in the area —
        // show an explicit "no targets" pill so the card isn't empty.
        if (_isAoeCard && _wasPlaced && !_hasResolvedTargets) {
            return `<div class="result-pills"><span class="result-pill chip-miss">💨 No targets in area</span></div>`;
        }
        // Heal — click to expand shows the rolled dice breakdown.
        if (d.auto_heal_applied > 0) {
            const tgt = d.auto_heal_target_name || d.target_name || '';
            const before = d.auto_heal_hp_before;
            const after = d.auto_heal_hp_after;
            const hpDelta = (before != null && after != null)
                ? ` (${before} → ${after})` : '';
            const header = `✚ ${escapeHTML(tgt)} +${d.auto_heal_applied} HP${hpDelta}`;
            const detail = d.auto_heal_breakdown ? `Heal: ${d.auto_heal_breakdown}` : '';
            pills.push(_buildPill('chip-heal', header, detail));
            if (d.auto_heal_revived) {
                pills.push('<span class="result-pill chip-buff">💚 revived</span>');
            }
        }
        // Attack — click for attack-roll breakdown; damage pill click
        // for damage-roll breakdown.
        if (d.auto_attack_hit != null) {
            const verdict = d.auto_attack_crit ? '💥 CRIT' : d.auto_attack_hit ? '✅ HIT' : '❌ MISS';
            const cls = d.auto_attack_crit ? 'chip-crit' : d.auto_attack_hit ? 'chip-hit' : 'chip-miss';
            const tgt = d.auto_attack_target_name || d.target_name || '';
            const ac = d.auto_attack_target_ac != null ? `/${d.auto_attack_target_ac}` : '';
            const header = `🎯 ${escapeHTML(tgt)} 🎲 ${d.auto_attack_total}${ac} ${verdict}`;
            const detail = d.auto_attack_breakdown ? `Attack: ${d.auto_attack_breakdown}` : '';
            pills.push(_buildPill(cls, header, detail));
            if (d.auto_attack_damage_applied > 0) {
                const type = d.auto_attack_damage_type ? ` ${escapeHTML(d.auto_attack_damage_type)}` : '';
                const dmgHeader = `🎲 ${d.auto_attack_damage_applied}${type}`;
                const dmgDetail = d.auto_attack_damage_breakdown ? `Damage: ${d.auto_attack_damage_breakdown}` : '';
                pills.push(_buildPill('chip-damage', dmgHeader, dmgDetail));
            }
        }
        // Save: multi-target AoE (T.5c) takes precedence over the
        // single-target headline pills. When the server sent a list
        // of per-target outcomes (Fireball at 3 bandits, Burning Hands
        // at 4 mooks, etc.), render one pill per target instead of
        // collapsing to the headline view — the GM needs to see who
        // saved, who failed, and how much damage each took.
        // v2.48.1 — gate on ``length > 0`` instead of ``> 1``. The new
        // T.5e pending-then-place flow always uses ``auto_save_targets``
        // even for a single-target placement (the headline auto_save_*
        // fields were never populated because resolution was deferred).
        // The 1-target case in this branch renders the same pill the
        // multi-target case would — without it, single-target Fireball
        // placements have an empty pill row.
        const saveTargets = Array.isArray(d.auto_save_targets) ? d.auto_save_targets : [];
        const multiSave = saveTargets.length > 0;
        if (multiSave) {
            const dc = d.auto_save_dc;
            const ability = d.auto_save_ability || '';
            let totalDmg = 0;
            let dmgType = '';
            for (const t of saveTargets) {
                if (t.pc_skipped) {
                    pills.push(
                        `<span class="result-pill chip-prompt">📋 ${escapeHTML(t.target_name || '')} ${escapeHTML(ability)} save · DC ${dc} pending</span>`
                    );
                    continue;
                }
                if (t.rolled == null) continue;
                const cls = t.passed ? 'chip-hit' : 'chip-miss';
                const v = t.passed ? '✅' : '❌';
                const type = t.damage_type ? ` ${escapeHTML(t.damage_type)}` : '';
                const tag = t.passed ? ' (½)' : '';
                // v2.48.6 — pill format:
                //   📋 NAME 🎲 ROLL/DC ✅/❌ · DMG TYPE
                // Dice emoji moved between name and roll; minus
                // sign removed from damage. Click toggles a
                // detail row showing the save + damage breakdowns
                // (1d20[15]+2=17 / 8d6[3,5,…]=28). Wrapped in a
                // container div so the detail can append below the
                // header without breaking the flex row layout.
                const dmg = (t.damage_applied || 0) > 0
                    ? ` · ${t.damage_applied}${type}${tag}`
                    : '';
                const header = `📋 ${escapeHTML(t.target_name || '')} 🎲 ${t.rolled}/${dc} ${v}${dmg}`;
                const saveBreak = t.breakdown ? `Save: ${escapeHTML(t.breakdown)}` : '';
                const dmgBreak = t.damage_breakdown ? `Damage: ${escapeHTML(t.damage_breakdown)}${type}` : '';
                const detailLines = [saveBreak, dmgBreak].filter(Boolean).join(' · ');
                pills.push(
                    `<button type="button" class="result-pill ${cls} per-target-pill" data-expanded="0"`
                    + ` title="Click for roll math">`
                    + `<span class="pt-header">${header}</span>`
                    + (detailLines
                        ? `<span class="pt-detail" style="display:none;font-size:11px;color:var(--fg-mute);margin-left:8px;border-left:1px solid currentColor;padding-left:8px;opacity:.85;">${detailLines}</span>`
                        : '')
                    + `</button>`
                );
                totalDmg += (t.damage_applied || 0);
                if (!dmgType && t.damage_type) dmgType = t.damage_type;
            }
            if (totalDmg > 0) {
                const typeBit = dmgType ? ` ${escapeHTML(dmgType)}` : '';
                pills.push(`<span class="result-pill chip-damage">Σ ${totalDmg}${typeBit}</span>`);
            }
        } else {
            // Single-target headline view — v2.48.7: click to expand
            // shows the save roll breakdown + damage roll breakdown.
            if (d.auto_save_target_kind === 'pc' && d.auto_save_prompted) {
                pills.push(
                    `<span class="result-pill chip-prompt">📋 ${escapeHTML(d.auto_save_target_name || '')} ${escapeHTML(d.auto_save_ability || '')} save · DC ${d.auto_save_dc}</span>`
                );
            }
            if (d.auto_save_target_kind === 'npc' && d.auto_save_rolled != null) {
                const cls = d.auto_save_passed ? 'chip-hit' : 'chip-miss';
                const v = d.auto_save_passed ? '✅ saved' : '❌ failed';
                const header = `📋 ${escapeHTML(d.auto_save_target_name || '')} 🎲 ${d.auto_save_rolled}/${d.auto_save_dc} ${v}`;
                const detail = d.auto_save_breakdown ? `Save: ${d.auto_save_breakdown}` : '';
                pills.push(_buildPill(cls, header, detail));
            }
            if (d.auto_save_damage_applied > 0) {
                const type = d.auto_save_damage_type ? ` ${escapeHTML(d.auto_save_damage_type)}` : '';
                const tag = d.auto_save_passed ? ' (half)' : '';
                const dmgHeader = `🎲 ${d.auto_save_damage_applied}${type}${tag}`;
                const dmgDetail = d.auto_save_damage_breakdown ? `Damage: ${d.auto_save_damage_breakdown}` : '';
                pills.push(_buildPill('chip-damage', dmgHeader, dmgDetail));
            }
        }
        if (d.auto_save_buff_name) {
            const dur = d.auto_save_buff_duration;
            const durLabel = dur === 1 ? '1 round' : `${dur} rounds`;
            pills.push(
                `<span class="result-pill chip-buff">${escapeHTML(d.auto_save_buff_icon || '💫')} ${escapeHTML(d.auto_save_buff_name)} · ${durLabel}</span>`
            );
        }
        // v2.49.156: auto-hit per-target damage pills (Magic Missile).
        // The server's auto_hit_targets list (v2.49.155) carries one
        // entry per dart with {target_name, rolled, breakdown,
        // damage_applied, damage_type}. Each renders as a clickable
        // pill with the same expandable-detail pattern as save pills.
        // Σ aggregate pill appended when 2+ darts landed.
        const hitTargets = Array.isArray(d.auto_hit_targets) ? d.auto_hit_targets : [];
        let _hitTotal = 0;
        let _hitDmgType = '';
        if (hitTargets.length) {
            for (const t of hitTargets) {
                const type = t.damage_type ? ` ${escapeHTML(t.damage_type)}` : '';
                const amt = (t.damage_applied != null && t.damage_applied > 0)
                    ? t.damage_applied
                    : (t.rolled || 0);
                const header = `🎯 ${escapeHTML(t.target_name || '')} 🎲 ${amt}${type}`;
                const detail = t.breakdown ? `Damage: ${escapeHTML(t.breakdown)}` : '';
                pills.push(_buildPill('chip-damage', header, detail));
                _hitTotal += (t.damage_applied || 0);
                if (!_hitDmgType && t.damage_type) _hitDmgType = t.damage_type;
            }
            if (hitTargets.length > 1 && _hitTotal > 0) {
                const typeBit = _hitDmgType ? ` ${escapeHTML(_hitDmgType)}` : '';
                pills.push(`<span class="result-pill chip-damage">Σ ${_hitTotal}${typeBit}</span>`);
            }
        }
        // Undo pill (when anything was actually applied). For multi-
        // target AoE, "applied" sums across per-target damage so the
        // button shows when at least one bandit took damage.
        const multiTargetDmg = saveTargets.reduce(
            (acc, t) => acc + (t && t.damage_applied ? t.damage_applied : 0), 0);
        const anyApplied = (
            (d.auto_heal_applied || 0) > 0
            || (d.auto_attack_damage_applied || 0) > 0
            || (d.auto_save_damage_applied || 0) > 0
            || multiTargetDmg > 0
            || _hitTotal > 0
        );
        if (anyApplied) {
            pills.push(
                `<button type="button" class="result-pill chip-undo weapon-atk-undo" data-attack-id="${escapeHTML(d.id || '')}" title="Revert this cast's HP changes">↶ Undo</button>`
            );
        }
        return pills.length ? `<div class="result-pills">${pills.join('')}</div>` : '';
    }

    function appendSpellCast(d) {
        const ul = document.getElementById('roll-list');
        if (!ul) return;
        const now = new Date();
        const h = now.getHours(), m = now.getMinutes();
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12 = (h % 12) || 12;
        const timeStr = h12.toString().padStart(2, '0') + ':' + m.toString().padStart(2, '0') + ' ' + ampm;

        const portrait = d.caster_portrait_url || USER_PORTRAITS[d.caster_user_id] || '';
        const color = d.caster_user_color || USER_COLORS[d.caster_user_id] || '';
        const dispName = d.caster_char_name || USER_CHAR_NAMES[d.caster_user_id] || d.caster_user_name;
        const avatarInner = portrait ? `<img src="${escapeHTML(portrait)}" alt="">` : '🪄';

        const slotLabel = d.spell_level === 0
            ? 'Cantrip'
            : `Lv ${d.slot_level}${d.slot_level > d.spell_level ? ' (upcast)' : ''} slot`;

        // Action buttons come from `d.actions` (new shape) or are synthesized
        // from the legacy regex-derived fields for backward compatibility.
        const _baseActions = (d.actions && d.actions.length) ? d.actions : [_synthesizeCastAction(d)];
        // v2.26.1: strip the legacy "🩹 Apply Healing" button when the
        // server already auto-applied the heal (the heal_claim has been
        // dropped server-side, so clicking would 404). v2.42.3: extend
        // the same idea to auto-attack damage + auto-save outcomes —
        // when the server resolved the spell's attack or save path, the
        // manual "🎲 Roll damage" / "📋 Prompt SAVE" buttons are
        // redundant (the chat card's ▼ Result block already shows the
        // outcome + Undo). Magic Missile-style spells that have no
        // auto-resolution path keep their manual buttons because
        // auto_attack_hit / auto_save_target_kind stay null for them.
        const _autoHeal   = d.auto_heal_applied > 0;
        const _autoAttack = d.auto_attack_hit != null;
        const _autoSave   = d.auto_save_target_kind != null;
        // v2.49.159: auto-hit spells (Magic Missile) now apply per-
        // dart damage server-side and emit auto_hit_targets pills —
        // the legacy "🎲 Roll damage" button is redundant. Strip
        // damage actions when at least one dart landed.
        const _autoHit    = Array.isArray(d.auto_hit_targets) && d.auto_hit_targets.length > 0;
        // v2.48.3 — AoE spells strip ALL legacy action buttons (Roll
        // Damage / Prompt SAVE / etc.). The v2.48.0 pending → place
        // flow renders a Place button when pending and per-target
        // pills once resolved; the legacy buttons would duplicate
        // those outcomes and confuse the GM ("did I already roll the
        // saves or do I still need to click Prompt?"). Detection
        // mirrors the server-side ``pending_aoe_placement`` rule —
        // the spell has a populated AoE area block.
        const _isAoeSpell = Boolean(d.area_shape) && Number(d.area_size_ft) > 0;
        const actions = _baseActions.map(a => {
            let out = a;
            if (_autoHeal && out.healing) out = {...out, healing: ''};
            if (_autoAttack && (out.damage || (out.damage_scaling && out.damage_scaling.length))) {
                out = {...out, damage: '', damage_scaling: []};
            }
            if (_autoSave || _isAoeSpell) {
                if (out.save_ability) out = {...out, save_ability: ''};
                if (out.damage || (out.damage_scaling && out.damage_scaling.length)) {
                    out = {...out, damage: '', damage_scaling: []};
                }
            }
            // v2.49.159: auto-hit spells strip damage actions too.
            if (_autoHit && (out.damage || (out.damage_scaling && out.damage_scaling.length))) {
                out = {...out, damage: '', damage_scaling: []};
            }
            return out;
        });
        // Keep `damageExpr` available for downstream code paths that already
        // expect the single-string variable (openDamagePicker call below).
        const _firstDamageAction = actions.find(a => a.damage || (a.damage_scaling && a.damage_scaling.length)) || {};
        const damageExpr = _diceExprFromDamage(_firstDamageAction.damage || '');

        const metaBits = [];
        if (d.spell_school)        metaBits.push(escapeHTML(d.spell_school));
        if (d.spell_casting_time)  metaBits.push(escapeHTML(d.spell_casting_time));
        if (d.spell_range)         metaBits.push(escapeHTML(d.spell_range));
        if (d.spell_concentration) metaBits.push('<span style="color:var(--accent)">Concentration</span>');
        if (d.spell_ritual)        metaBits.push('<span style="color:var(--accent)">Ritual</span>');

        // v2.43.0: target tag relocated from the body's name row up
        // into the header (next to the slot chip). Inline the spell
        // school / casting time / range / concentration / ritual
        // bits with the spell name in a single row so the cast scans
        // top-to-bottom: who → what → outcome (pills) → buttons.
        const targetTagHtml = _targetTagHtml(d);
        const li = document.createElement('li');
        li.dataset.castId = d.id;
        li.innerHTML = `
            <div class="spell-cast-card">
                <div class="roll-card-header">
                    <div class="roll-card-avatar">${avatarInner}</div>
                    <span class="roll-card-user" data-uid="${d.caster_user_id}"${color ? ` style="color:${escapeHTML(color)}"` : ''}>${escapeHTML(dispName)}</span>
                    ${targetTagHtml}
                    <span class="spell-cast-slot">${escapeHTML(slotLabel)}</span>
                    <span class="roll-card-time">${timeStr}</span>
                </div>
                <div class="spell-cast-body">
                    <div class="spell-cast-name-row">
                        <span class="spell-cast-name">🪄 ${escapeHTML(d.spell_name || 'Spell')}</span>
                        ${metaBits.length ? `<span class="spell-cast-meta-inline">· ${metaBits.join(' · ')}</span>` : ''}
                    </div>
                    ${d.spell_desc ? `<details class="roll-card-details"><summary>▾ details</summary><div class="spell-cast-desc">${escapeHTML(d.spell_desc)}</div></details>` : ''}
                    ${_spellResultPillsHtml(d)}
                    <div class="spell-cast-actions"></div>
                    ${_overBudgetBadge(d)}
                    <div class="spell-cast-results"></div>
                </div>
            </div>`;
        ul.appendChild(li);
        _scrollRollLogToBottom();

        // Populate the actions slot via the shared renderer. Each handler maps
        // to the existing per-button helper so behavior is unchanged.
        const actionsSlot = li.querySelector('.spell-cast-actions');
        actionsSlot.appendChild(renderActionButtons(actions, {
            characterLevel: d.character_level || 1,
            handlers: {
                save:   (_action, btn) => promptSpellSave(d, li, btn),
                damage: (_action, dmgExpr, btn) => _castDamageClick(d, dmgExpr, li, btn),
                heal:   (_action, btn) => _applyHealing(d, li, btn),
                // attack and toggle handlers are wired through where consumers
                // need them — the spell-cast card itself only uses save/damage/heal.
            },
        }));

        // v2.26.0 Phase T.4: wire the auto-heal undo button if the
        // server applied a heal to the targeted combatant. Same
        // endpoint as attack-damage undo (server detects the heal
        // entry's is_heal flag and reverses by damaging the same
        // amount).
        // v2.31.0 Phase T.3b: also wires save-for-half damage undo
        // buttons. querySelectorAll iterates every ``.weapon-atk-undo``
        // on the card; heal cards only have one, save-spell cards may
        // have one (damage applied), and a future spell that combines
        // both (some homebrew?) would wire both with the same handler.
        li.querySelectorAll('.weapon-atk-undo').forEach((undoBtn) => {
            undoBtn.addEventListener('click', async () => {
                undoBtn.disabled = true;
                try {
                    const r = await fetch(`/api/campaign/${CAMPAIGN_ID}/undo_attack_damage`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ attack_id: d.id }),
                    });
                    if (!r.ok) {
                        let body; try { body = await r.json(); } catch { body = null; }
                        (window.showToast || function(m){ alert(m); })(
                            `Undo failed: ${body ? JSON.stringify(body) : r.status}`, 'error');
                        undoBtn.disabled = false;
                        return;
                    }
                    const data = await r.json().catch(() => ({}));
                    undoBtn.textContent = `↶ Reverted ${data.reverted || ''}`;
                    undoBtn.classList.add('undone');
                } catch (e) {
                    console.warn('undo_attack_damage failed:', e);
                    undoBtn.disabled = false;
                }
            });
        });

        // v2.48.0 Phase T.5e: wire the Place AoE button when the cast
        // is in pending-placement mode. Click opens the canvas picker
        // (caster + GM only) and POSTs /place_aoe with the swept-up
        // target_combatant_ids; the server resolves saves + damage
        // and broadcasts ``spell_cast_aoe_resolved`` which the handler
        // below applies to the card in place.
        li.querySelectorAll('.spell-cast-place-aoe').forEach((placeBtn) => {
            placeBtn.addEventListener('click', async () => {
                if (placeBtn.disabled) return;
                placeBtn.disabled = true;
                try {
                    const opts = {
                        shape: d.area_shape || 'sphere',
                        size_ft: d.area_size_ft || 0,
                        secondary_ft: d.area_secondary_ft || 0,
                        name: d.spell_name || 'Spell',
                        char_id: d.caster_char_id,
                        // v2.49.78 — Phase 3A range ring. The server's
                        // /cast_spell pending-placement response now
                        // carries `range_ft`; pass it through so the
                        // picker can render the translucent range ring
                        // around the caster + dim the AoE preview when
                        // the cursor strays outside.
                        range_ft: d.range_ft || 0,
                    };
                    const placed = (typeof _openAoePicker === 'function')
                        ? await _openAoePicker(opts)
                        : (typeof window._openAoePicker === 'function')
                            ? await window._openAoePicker(opts)
                            : null;
                    if (placed === null) {
                        placeBtn.disabled = false;
                        return;
                    }
                    const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/place_aoe`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            cast_id: d.id,
                            target_combatant_ids: placed.target_combatant_ids || [],
                            // v2.49.0 — pass the placement center so
                            // the server can persist concentration-
                            // based AoEs as map markers (Spirit
                            // Guardians, Hypnotic Pattern, etc.).
                            center: placed.center || null,
                        }),
                    });
                    if (!resp.ok) {
                        let body; try { body = await resp.json(); } catch { body = null; }
                        // 404 = stale cast (the server's pending-AoE
                        // stash doesn't have a matching cast_id, most
                        // likely because the cast pre-dates v2.48.0
                        // or the 8-hour TTL elapsed). Surface a
                        // helpful message + invite the user to clear
                        // the log.
                        if (resp.status === 404) {
                            (window.showToast || function(m){ alert(m); })(
                                'This cast is stale — server can no longer place it. Click 🗑 Clear in the roll log to remove old entries.',
                                'error');
                        } else {
                            (window.showToast || function(m){ alert(m); })(
                                `Place AoE failed: ${body ? JSON.stringify(body) : resp.status}`,
                                'error');
                        }
                        placeBtn.disabled = false;
                        return;
                    }
                    // Success — the server's spell_cast_aoe_resolved
                    // broadcast lands shortly and the handler below
                    // mutates the card. Leave the button disabled in
                    // the meantime so a fast second click can't double-
                    // resolve.
                } catch (e) {
                    console.warn('place_aoe failed:', e);
                    placeBtn.disabled = false;
                }
            });
        });

        // Stash the cast metadata on the element so the roll listener can
        // correlate save responses back to this card (matches by note prefix).
        // v2.49.219: seed _saveLabel from the server's auto_save_label when
        // present so NPC casts (where the server auto-prompts the save via
        // a RollRequest without the user clicking "Prompt SAVE") get the
        // pill correlation just like PC casts do. Falls back to null —
        // PC casts that haven't clicked "Prompt SAVE" yet keep the existing
        // behavior of setting _saveLabel on click.
        li._spellCast = { ...d, _saveLabel: d.auto_save_label || null };
        // v2.49.162: damage toast for auto-hit spells (Magic Missile et al).
        // Auto-heal already toasts via the manual Apply Healing click path
        // (line ~4466) and auto-attack / auto-save damage shows in pills,
        // but auto-hit had no surfaced confirmation that damage actually
        // applied — the user only saw pills inside the chat-card body.
        // Gated on !_rollLogHydrating so localStorage replay on page
        // refresh doesn't fire a stale toast for every prior cast.
        if (!_rollLogHydrating) {
            const _hitTargets = Array.isArray(d.auto_hit_targets) ? d.auto_hit_targets : [];
            if (_hitTargets.length) {
                let _total = 0;
                let _dtype = '';
                for (const t of _hitTargets) {
                    _total += (t.damage_applied || 0);
                    if (!_dtype && t.damage_type) _dtype = t.damage_type;
                }
                if (_total > 0) {
                    const _typeBit = _dtype ? ` ${_dtype}` : '';
                    const _names = _hitTargets
                        .map(t => t.target_name)
                        .filter(Boolean);
                    const _targetsLabel = _names.length === 1
                        ? _names[0]
                        : `${_hitTargets.length} targets`;
                    const _spellLabel = d.spell_name || 'Spell';
                    showToast(
                        `🎯 ${_spellLabel}: ${_total}${_typeBit} dmg → ${_targetsLabel}`,
                        'info',
                    );
                }
            }
        }
        _persistRollEntry('spell_cast', d);
    }

    async function _applyHealing(d, li, btn) {
        if (btn.disabled) return;
        btn.disabled = true;
        try {
            const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/apply_healing`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cast_id: d.id }),
            });
            const body = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                const msg = body.detail || body.error || 'Healing failed';
                showToast(msg, 'error');
                btn.disabled = false;
                return;
            }
            if (body.already_auto_applied) {
                showToast(body.message || `🩹 Heal was already auto-applied to the target.`, 'info');
                // Hide the now-stale heal button so the user doesn't keep clicking.
                btn.style.display = 'none';
                return;
            }
            showToast(`🩹 +${body.rolled} HP applied to your character!`, 'info');
            // UI update arrives via the heal_applied broadcast — no need to patch DOM here
        } catch (e) {
            showToast('Healing failed: ' + e.message, 'error');
            btn.disabled = false;
        }
    }

    function _onHealApplied(d) {
        const ul = document.getElementById('roll-list');
        if (ul) {
            const li = ul.querySelector(`li[data-cast-id="${d.cast_id}"]`);
            if (li) {
                // Update charge tracker
                const tracker = li.querySelector('.heal-charge-tracker');
                if (tracker) {
                    tracker.dataset.claimed = d.claimed_count;
                    tracker.textContent = `(${d.claimed_count}/${d.max_targets})`;
                }
                // Append result row
                const results = li.querySelector('.spell-cast-results');
                if (results) {
                    const row = document.createElement('div');
                    row.className = 'spell-cast-result-row heal-result-row';
                    row.innerHTML = `🩹 <strong>${escapeHTML(d.char_name)}</strong> +${d.rolled} HP`;
                    results.appendChild(row);
                }
                // Disable button once all AOE charges are consumed
                const healBtn = li.querySelector('.spell-cast-heal-btn');
                if (healBtn && d.max_targets > 1 && d.claimed_count >= d.max_targets) {
                    healBtn.disabled = true;
                }
            }
        }
        // Update the player-drawer mini-sheet HP if visible
        if (typeof window._updateMiniHpDisplay === 'function') {
            window._updateMiniHpDisplay(d.char_id, d.new_hp);
        }
        // v2.49.47 — also sync window.battle.combatants HP + refresh
        // the init tracker. Same bug class as v2.49.45 / v2.49.46:
        // the broadcast carries new_hp but the handler doesn't push
        // it into the combatants list or trigger renderBattle, so
        // the init-tracker mini-header-sub "HP X / Y" stays at the
        // pre-heal value. Skip if char_id or new_hp is absent.
        if (d.char_id != null && d.new_hp) {
            const battle = window.battle && Array.isArray(window.battle.combatants)
                ? window.battle.combatants : null;
            if (battle) {
                for (const c of battle) {
                    if (c.char_id === d.char_id) {
                        if (typeof d.new_hp.current === 'number') c.hp_current = d.new_hp.current;
                        if (typeof d.new_hp.max === 'number') c.hp_max = d.new_hp.max;
                    }
                }
            }
            if (typeof window._renderBattle === 'function') {
                try { window._renderBattle(); } catch (_) {}
            }
        }
        // v2.29.1: persist heal_applied to the roll-log buffer so the
        // "🩹 Krieger Stonefist +N HP" result row survives a refresh.
        // The row is rendered by mutating the existing spell-cast card,
        // so on replay we need the heal_applied entry to fire AFTER the
        // matching spell_cast. Entries are stored in chronological
        // order in localStorage so the replay loop hits them in the
        // right sequence naturally.
        _persistRollEntry('heal_applied', d);
    }

    // v2.47.0 Phase T.5d: a PC AoE save just resolved. Find the
    // matching cast card in the roll log, mutate the relevant
    // auto_save_targets entry (the PC pill goes from "pending" →
    // "rolled / passed / damage_applied"), and re-render the pill
    // row from the stashed cast data. The Σ aggregate pill in the
    // v2.46.3 multi-target renderer picks up the new damage value
    // automatically since it sums across the array.
    function _onSpellCastTargetUpdated(d) {
        if (!d || !d.cast_id) return;
        const ul = document.getElementById('roll-list');
        if (!ul) return;
        const li = ul.querySelector(`li[data-cast-id="${d.cast_id}"]`);
        if (!li || !li._spellCast) return;
        const cast = li._spellCast;
        const targets = Array.isArray(cast.auto_save_targets) ? cast.auto_save_targets : [];
        const entry = targets.find(t => t && t.combatant_id === d.combatant_id);
        if (!entry) return;
        entry.rolled = d.rolled;
        entry.passed = d.passed;
        entry.damage_applied = d.damage_applied || 0;
        entry.damage_type = d.damage_type || entry.damage_type;
        delete entry.pc_skipped;
        delete entry.pending_request_id;
        // Re-render the entire pill row in place. ``_spellResultPillsHtml``
        // returns a fresh ``<div class="result-pills">…</div>`` block so
        // we look up the existing one by class and replace its outerHTML.
        const body = li.querySelector('.spell-cast-body');
        if (!body) return;
        const newHtml = _spellResultPillsHtml(cast);
        const existing = body.querySelector('.result-pills');
        if (existing) {
            if (newHtml) {
                const tmp = document.createElement('div');
                tmp.innerHTML = newHtml;
                existing.replaceWith(tmp.firstElementChild);
            } else {
                existing.remove();
            }
        } else if (newHtml) {
            const tmp = document.createElement('div');
            tmp.innerHTML = newHtml;
            // Insert above .spell-cast-actions per the original layout.
            const actions = body.querySelector('.spell-cast-actions');
            if (actions) actions.before(tmp.firstElementChild);
            else body.appendChild(tmp.firstElementChild);
        }
        _persistRollEntry('spell_cast_target_updated', d);
    }

    // v2.48.0 Phase T.5e: the caster (or GM) placed a pending AoE
    // cast and the server resolved every target. Pull the populated
    // auto_save_targets list onto the cast card's stashed metadata,
    // clear the pending flag (so the Place button is replaced by
    // the per-target pill row), backfill auto_save_dc and ability
    // so the per-target pill renderer's labels work, and re-render
    // the .result-pills block in place.
    function _onSpellCastAoeResolved(d) {
        if (!d || !d.cast_id) return;
        const ul = document.getElementById('roll-list');
        if (!ul) return;
        const li = ul.querySelector(`li[data-cast-id="${d.cast_id}"]`);
        if (!li || !li._spellCast) return;
        const cast = li._spellCast;
        cast.auto_save_targets = Array.isArray(d.auto_save_targets) ? d.auto_save_targets : [];
        cast.pending_aoe_placement = false;
        if (d.dc != null) cast.auto_save_dc = d.dc;
        if (d.save_ability) cast.auto_save_ability = d.save_ability;
        const body = li.querySelector('.spell-cast-body');
        if (!body) return;
        const newHtml = _spellResultPillsHtml(cast);
        const existing = body.querySelector('.result-pills');
        if (existing) {
            if (newHtml) {
                const tmp = document.createElement('div');
                tmp.innerHTML = newHtml;
                existing.replaceWith(tmp.firstElementChild);
            } else {
                existing.remove();
            }
        } else if (newHtml) {
            const tmp = document.createElement('div');
            tmp.innerHTML = newHtml;
            const actions = body.querySelector('.spell-cast-actions');
            if (actions) actions.before(tmp.firstElementChild);
            else body.appendChild(tmp.firstElementChild);
        }
        _persistRollEntry('spell_cast_aoe_resolved', d);
    }

    // ---------- Death save broadcast handler (v2.1.0) ----------
    // v2.49.4 — sync PC HP from the server-authoritative broadcast.
    // ``_apply_hp_change`` mutates ``Character.sheet.hp`` server-side
    // and emits ``character_hp_update``; clients need the handler to
    // keep ``window.battle.combatants`` + the in-memory ``characters``
    // array in step (their hp_current was stale otherwise). Triggers
    // a canvas re-render so the v2.49.4 skull overlay fires on the
    // moment a PC drops to 0 HP, and refreshes the mini-sheet HP bar
    // if one's visible.
    function _onCharacterHpUpdate(d) {
        if (!d || !d.character_id || !d.hp) return;
        const ch = charById[d.character_id];
        if (ch) {
            ch.hp_current = d.hp.current;
            ch.hp_max     = d.hp.max;
        }
        const battle = window.battle && Array.isArray(window.battle.combatants)
            ? window.battle.combatants : null;
        if (battle) {
            for (const c of battle) {
                if (c.char_id === d.character_id) {
                    c.hp_current = d.hp.current;
                    c.hp_max     = d.hp.max;
                }
            }
        }
        try { render(); } catch (_) {}
        // v2.49.45 — also trigger the init-tracker re-render. The
        // PC-damage path broadcasts character_hp_update (not
        // battle_update which already calls renderBattle), so without
        // this the mini-header-sub "HP X / Y" text stays at the
        // pre-damage value. window._renderBattle is exposed by the
        // tabletop.html IIFE for exactly this case.
        if (typeof window._renderBattle === 'function') {
            try { window._renderBattle(); } catch (_) {}
        }
        if (typeof window._updateMiniHpDisplay === 'function') {
            try { window._updateMiniHpDisplay(d.character_id, d.hp); } catch (_) {}
        }
        // v2.49.5 — push the new HP into the iframe drawer sheet
        // (sheet_dnd5e.html exposes ``window.updateSheetHp`` for
        // exactly this case). Without this the open sheet keeps
        // showing the HP from when the page first rendered.
        const iframe = document.getElementById('monster-sheet-drawer-iframe');
        if (iframe && iframe.contentWindow) {
            try {
                const fn = iframe.contentWindow.updateSheetHp;
                if (typeof fn === 'function') fn(d.character_id, d.hp);
            } catch (_) { /* cross-origin or unloaded — skip */ }
        }
    }

    function _onCharacterDeathSave(d) {
        if (!d || !d.character_id) return;
        // Update every tracker on the page for this character
        const successes = Math.max(0, parseInt(d.successes ?? 0, 10) || 0);
        const failures = Math.max(0, parseInt(d.failures ?? 0, 10) || 0);
        const status = d.status || 'alive';
        document.querySelectorAll(
            `.death-saves-tracker[data-character-id="${d.character_id}"]`
        ).forEach(el => {
            el.dataset.status = status;
            el.dataset.successes = String(successes);
            el.dataset.failures = String(failures);
            // v2.1.1: tracker is permanently visible (no display toggle).
            const badge = el.querySelector('.death-saves-status');
            if (badge) {
                badge.textContent = status.toUpperCase();
                badge.className = `death-saves-status death-saves-status-${status}`;
            }
            el.querySelectorAll('.death-saves-pip-success').forEach((p, i) =>
                p.classList.toggle('death-saves-pip-on', i < successes));
            el.querySelectorAll('.death-saves-pip-failure').forEach((p, i) =>
                p.classList.toggle('death-saves-pip-on', i < failures));
            const actions = el.querySelector('.death-saves-actions');
            if (actions) actions.style.display = (status === 'dying') ? '' : 'none';
        });
        // v2.49.46 — sync HP into window.battle.combatants + trigger
        // a renderBattle pass so the init tracker's mini-header-sub
        // "HP X / Y" text reflects the new HP. Pre-fix: the GM-only
        // /death-save/override endpoint at status="alive" bumps a
        // dying PC's HP from 0 → 1; the broadcast carried the new
        // hp dict but the init tracker showed "HP 0 / N" until
        // something else triggered renderBattle. Same bug class as
        // v2.49.45 (character_hp_update handler) — the broadcast
        // carries the data, the handler skips the init-tracker
        // refresh. Skip when d.hp is absent (some death-save events
        // don't include HP, e.g. rolling a success that doesn't
        // change HP).
        if (d.hp) {
            const battle = window.battle && Array.isArray(window.battle.combatants)
                ? window.battle.combatants : null;
            if (battle) {
                for (const c of battle) {
                    if (c.char_id === d.character_id) {
                        if (typeof d.hp.current === 'number') c.hp_current = d.hp.current;
                        if (typeof d.hp.max === 'number') c.hp_max = d.hp.max;
                    }
                }
            }
            if (typeof window._renderBattle === 'function') {
                try { window._renderBattle(); } catch (_) {}
            }
        }
        // Sync HP display in the player-drawer mini-sheet (when present)
        if (d.hp && typeof window._updateMiniHpDisplay === 'function') {
            window._updateMiniHpDisplay(d.character_id, d.hp);
        }
    }

    // ---------- Death save button delegation (v2.1.0) ----------
    document.addEventListener('click', async (ev) => {
        const rollBtn = ev.target.closest('[data-action="roll-death-save"]');
        const stabBtn = ev.target.closest('[data-action="stabilize"]');
        if (!rollBtn && !stabBtn) return;
        const btn = rollBtn || stabBtn;
        const cid = btn.dataset.campaignId;
        const charId = btn.dataset.characterId;
        if (!cid || !charId) return;
        const url = rollBtn
            ? `/api/campaign/${cid}/character/${charId}/death-save`
            : `/api/campaign/${cid}/character/${charId}/stabilize`;
        if (stabBtn && !confirm('Stabilize this character? They will remain unconscious at 0 HP until healed.')) return;
        btn.disabled = true;
        try {
            const resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                showToast(err.detail || 'Death save action failed', 'error');
                return;
            }
            // Server broadcasts character_death_save → _onCharacterDeathSave
            // updates the tracker UI. Nothing to do here.
        } catch (e) {
            showToast('Action error: ' + (e.message || e), 'error');
        } finally {
            btn.disabled = false;
        }
    });

    // ---------- Roll-state broadcast handler (v2.2.0) ----------
    function _onCharacterRollState(d) {
        if (!d || !d.character_id) return;
        const value = d.value || '';
        document.querySelectorAll(
            `.roll-state-pill[data-character-id="${d.character_id}"]`
        ).forEach(pill => {
            pill.dataset.value = value;
            pill.querySelectorAll('.roll-state-btn').forEach(btn => {
                const matches = (btn.dataset.value || '') === value;
                btn.classList.toggle('roll-state-btn-on', matches);
            });
        });
    }

    // ---------- Roll-state pill click delegation (v2.2.0) ----------
    document.addEventListener('click', async (ev) => {
        const btn = ev.target.closest('[data-action="set-roll-state"]');
        if (!btn) return;
        const cid = btn.dataset.campaignId;
        const charId = btn.dataset.characterId;
        if (!cid || !charId) return;
        const value = btn.dataset.value || null;  // empty string → null
        btn.disabled = true;
        try {
            const resp = await fetch(
                `/api/campaign/${cid}/character/${charId}/roll-state`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ value: value || null }),
                }
            );
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                showToast(err.detail || 'Failed to set roll state', 'error');
                return;
            }
            // Optimistic local update — the WS broadcast will also call
            // _onCharacterRollState shortly, but updating now avoids the
            // brief flicker.
            _onCharacterRollState({ character_id: charId, value: value || '' });
        } catch (e) {
            showToast('Roll-state error: ' + (e.message || e), 'error');
        } finally {
            btn.disabled = false;
        }
    });

    // ---------- Class-feature use card ----------
    // Compact roll-log card announcing that a character used a class /
    // subclass feature (Rage, Channel Divinity, Action Surge, …). Posted
    // by the backend when ``POST /resource`` is called with a negative
    // delta. The card has no roll — it's purely an announcement so the
    // rest of the table sees who fired what.
    /* v2.9.1: presence pills. The hub broadcasts ``presence_update``
     * on every connect/disconnect with the deduped list of connected
     * users. We render one transparent pill per user in the
     * #presence-bubbles container anchored at the map pane's lower-
     * left. The pill's left border carries the user's color (character
     * color → membership color → gm_color); a small dot indicates
     * green for player, amber for GM. Display-only — clicks pass
     * through to the canvas via pointer-events:none on the container
     * (individual pills re-enable to surface a hover title with the
     * user_id). */
    function _renderPresence(data) {
        const container = document.getElementById('presence-bubbles');
        if (!container) return;
        const users = (data && Array.isArray(data.users)) ? data.users : [];
        // v2.9.2: empty roster shouldn't happen (the receiving client
        // is always in the list since they're connected), but defend
        // against a stale broadcast by keeping the server-rendered
        // pill in place rather than wiping it. Same for any case where
        // ``users`` doesn't include the current user — keep the SSR
        // fallback visible so the corner is never blank.
        if (!users.length) return;
        // Stable sort: GMs first (so they always render in the same
        // relative position), then alphabetical display name. The
        // server doesn't guarantee an order so we do it client-side.
        users.sort((a, b) => {
            if (!!a.is_gm !== !!b.is_gm) return a.is_gm ? -1 : 1;
            return String(a.display_name || '').localeCompare(String(b.display_name || ''));
        });
        const html = users.map(u => {
            const name = String(u.display_name || 'Player')
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
            const color = u.color || (u.is_gm ? '#ffa54a' : '#6cb4ff');
            const titleBits = [u.display_name || 'Player'];
            if (u.is_gm) titleBits.push('Game Master');
            const title = titleBits.join(' — ').replace(/"/g, '&quot;');
            return (
                `<span class="presence-pill${u.is_gm ? ' is-gm' : ''}" ` +
                `style="border-left-color:${color};" title="${title}">` +
                `<span class="presence-dot"></span>${name}</span>`
            );
        }).join('');
        container.innerHTML = html;
        container.style.display = '';
    }

    /* v2.6.1: Phase 4 Layer C — audit badge HTML for over-budget rolls.
     * Returned as a small inline element appended to the roll-card body
     * for weapon_attack / spell_cast / feature_used cards when the
     * server flags ``over_budget: true``. Visible to every participant
     * (GM + all players); the GM uses it as the audit trail without
     * needing a separate WS push.
     */
    function _overBudgetBadge(d) {
        if (!d || !d.over_budget) return '';
        const slot = d.over_budget_slot || '';
        const slotPhrase = slot === 'bonus' ? 'bonus action'
                         : slot === 'reaction' ? 'reaction'
                         : 'action';
        return `<div class="over-budget-badge" style="margin-top:6px;padding:4px 8px;border-radius:4px;background:rgba(255,165,74,0.12);border:1px solid rgba(255,165,74,0.4);color:#ffa54a;font-size:11px;font-weight:600;display:inline-flex;align-items:center;gap:4px;">⚠ Manual override — 2nd ${slotPhrase} this turn</div>`;
    }

    // v2.42.3: source slug → human-readable tag for the feature-used
    // card header. Mirrors how spell-cast cards show "Cantrip" / "Lv 1
    // slot" — gives features parity so the roll log scans uniformly.
    // Unknown sources fall through to "Feature" (safe default).
    function _featureSourceLabel(src) {
        if (!src) return 'Feature';
        const map = {
            'class-feature':    'Class Feature',
            'second-wind':      'Class Feature',
            'action-surge':     'Class Feature',
            'rage':             'Class Feature',
            'cunning-action':   'Class Feature',
            'lay-on-hands':     'Class Feature',
            'channel-divinity': 'Class Feature',
            'bardic-inspiration': 'Class Feature',
            'cutting-words':    'Class Feature',
            'arcane-recovery':  'Class Feature',
            'wild-shape':       'Class Feature',
            'ki':               'Class Feature',
            'racial':           'Racial Trait',
            'race':             'Racial Trait',
            'item-use':         'Item',
            'feat':             'Feat',
        };
        return map[src] || 'Feature';
    }

    function _appendFeatureUsed(d) {
        const ul = document.getElementById('roll-list');
        if (!ul) return;
        const now = new Date();
        const h = now.getHours(), m = now.getMinutes();
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12  = (h % 12) || 12;
        const hhmm = h12.toString().padStart(2,'0') + ':' + m.toString().padStart(2,'0') + ' ' + ampm;
        const color = d.user_color || '';
        const name  = d.character_name || 'Player';
        const feat  = d.feature_name || 'feature';
        const tagLabel = _featureSourceLabel(d.source);
        // v2.49.2 — charges/remaining now render as a chip-buff pill
        // in the .result-pills row alongside heal/damage/dice pills.
        // The old inline ``feature-used-counter`` span next to the
        // feature name is gone. When remaining hits 0, the pill
        // turns red (chip-miss) so the GM sees "Garrik just spent
        // his last Second Wind use" at a glance.
        const remaining = '';
        // v2.43.0: feature_desc is now an inline tail next to the
        // feature name (it was a collapsible ▾ details block in
        // v2.41.0). Most descs are short ("Bonus action", "Spent
        // 5 HP from pool"); long ones wrap to the next line.
        const descInline = d.feature_desc
            ? `<span class="feature-used-desc">· ${escapeHTML(d.feature_desc)}</span>`
            : '';
        // v2.43.0: oversized heal pill when the feature actually
        // healed someone. Server adds ``heal_amount`` / ``heal_target_name``
        // / ``heal_hp_before`` / ``heal_hp_after`` on broadcasts where
        // a heal landed (Second Wind, Lay on Hands). Mirrors the
        // spell-cast result-pill row so the eye finds the outcome
        // in the same place across card types.
        // v2.48.8 — Second Wind / Lay on Hands / any feature_used
        // heal now uses the shared ``_buildPill`` so click-to-expand
        // shows the heal dice breakdown (1d10+5[8+5]=13 etc.).
        // v2.49.1 — gate on ``dice_total > 0 || heal_amount > 0`` so
        // the pill renders even when the caster was already at full
        // HP (heal_amount caps at 0 in that case but the dice still
        // rolled; the rendered pill shows the rolled value + a
        // "(at max)" indicator). Server still computes heal_amount
        // as the applied delta — pill just reads dice_total for
        // header display.
        // v2.49.2 — every feature_used card now gets a unified pill
        // row (heal + dice + charges + future buff/damage pills).
        // The row replaces the v2.49.1 single heal pill block + the
        // inline charges counter. Each pill independently clickable
        // via _buildPill where roll math is available.
        const featurePills = [];
        const hasHealEvent = (d.heal_amount && d.heal_amount > 0)
            || (d.dice_total && d.dice_total > 0 && (d.heal_target_name || (d.dice_note || '').includes('Heal') || (d.source || '').match(/wind|hands|heal/i)));
        if (hasHealEvent) {
            const tgt = d.heal_target_name || name;
            const before = d.heal_hp_before;
            const after = d.heal_hp_after;
            const applied = d.heal_amount || 0;
            const rolled = d.dice_total || applied;
            let headerTail;
            if (applied > 0 && before != null && after != null) {
                headerTail = `+${applied} HP (${before} → ${after})`;
            } else if (applied === 0 && rolled > 0) {
                headerTail = `+0 HP (at max — rolled ${rolled})`;
            } else {
                headerTail = `+${applied} HP`;
            }
            const header = `✚ ${escapeHTML(tgt)} ${headerTail}`;
            const detail = d.dice_breakdown
                ? `Heal: ${d.dice_breakdown}`
                : (d.heal_breakdown ? `Heal: ${d.heal_breakdown}` : '');
            featurePills.push(_buildPill('chip-heal', header, detail));
        }
        // Generic dice-roll pill — features that rolled dice without
        // auto-applying a heal (Bardic Inspiration's d-die isn't a
        // roll yet, but Arcane Recovery + Healing Hands racial +
        // anything else broadcasting ``dice_total`` lands here).
        // Suppressed when hasHealEvent is true to avoid double-
        // rendering the same dice as both a heal pill and a die pill.
        if (!hasHealEvent && d.dice_total && d.dice_total > 0) {
            const diceHeader = d.dice_expression
                ? `🎲 ${escapeHTML(d.dice_expression)} → ${d.dice_total}`
                : `🎲 ${d.dice_total}`;
            const diceDetail = d.dice_breakdown ? `Roll: ${d.dice_breakdown}` : '';
            featurePills.push(_buildPill('chip-prompt', diceHeader, diceDetail));
        }
        // Charges pill — every feature with remaining/max. The pill's
        // ``chip-buff`` color signals "this resource is still
        // available"; switches to ``chip-miss`` when remaining hits
        // 0 so the GM sees the depleted state at a glance.
        if (d.max && d.max > 0) {
            const rem = Number(d.remaining || 0);
            const mx  = Number(d.max);
            const isLast = rem === 0;
            const cls = isLast ? 'chip-miss' : 'chip-buff';
            const icon = isLast ? '⚪' : '🔋';
            featurePills.push(`<span class="result-pill ${cls}">${icon} ${rem}/${mx} uses left</span>`);
        }
        const healPill = featurePills.length
            ? `<div class="result-pills">${featurePills.join('')}</div>`
            : '';
        const targetTagHtml = _targetTagHtml(d);
        const li = document.createElement('li');
        li.innerHTML = `
            <div class="roll-card feature-used-card">
                <div class="roll-card-header">
                    <div class="roll-card-avatar">✨</div>
                    <span class="roll-card-user" data-uid="${d.character_id || ''}"${color ? ` style="color:${escapeHTML(color)}"` : ''}>${escapeHTML(name)}</span>
                    ${targetTagHtml}
                    <span class="spell-cast-slot">${escapeHTML(tagLabel)}</span>
                    <span class="roll-card-time">${hhmm}</span>
                </div>
                <div class="roll-card-body" style="padding:6px 10px 8px;">
                    <div class="feature-used-name-row">
                        <strong class="feature-used-name">${escapeHTML(feat)}</strong>
                        ${descInline}
                        ${remaining}
                    </div>
                    ${healPill}
                    ${_overBudgetBadge(d)}
                </div>
            </div>`;
        ul.appendChild(li);
        _scrollRollLogToBottom();
        _persistRollEntry('feature_used', d);
    }

    // ---------- Weapon-attack card ----------
    function appendWeaponAttack(d) {
        const ul = document.getElementById('roll-list');
        if (!ul) return;
        const now = new Date();
        const h = now.getHours(), m = now.getMinutes();
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12 = (h % 12) || 12;
        const timeStr = h12.toString().padStart(2, '0') + ':' + m.toString().padStart(2, '0') + ' ' + ampm;

        const portrait = d.caster_portrait_url || USER_PORTRAITS[d.caster_user_id] || '';
        const color = d.caster_user_color || USER_COLORS[d.caster_user_id] || '';
        const dispName = d.caster_char_name || USER_CHAR_NAMES[d.caster_user_id] || d.caster_user_name;
        const avatarInner = portrait ? `<img src="${escapeHTML(portrait)}" alt="">` : '🗡';

        const metaBits = [];
        if (d.range)       metaBits.push(escapeHTML(d.range));
        if (d.damage_type) metaBits.push(escapeHTML(d.damage_type));

        // v2.43.1: weapon-attack outcome row uses the same oversized
        // pill pattern as spell-cast. Each line of the v2.24.0 inline
        // "weapon-atk-line" layout maps to one pill (attack-roll
        // verdict + AC, damage applied + HP delta + resist marker,
        // bonus damage attribution, ↶ Undo, save prompt). The
        // per-pill dice breakdown moves to ▾ details below the pill
        // row so the card scans top-to-bottom: who → what → outcome.
        const pills = [];
        if (!d.is_save && d.attack_total != null) {
            const cls = d.is_crit ? 'chip-crit' : (d.hit === false ? 'chip-miss' : 'chip-hit');
            const verdict = d.is_crit ? '💥 CRIT' : (d.hit === false ? '❌ MISS' : (d.hit === true ? '✅ HIT' : ''));
            const ac = d.target_ac != null ? `/${d.target_ac}` : '';
            const verdictTail = verdict ? ` ${verdict}` : '';
            // v2.48.7 — click to expand shows the attack roll breakdown.
            const header = `🎯 🎲 ${d.attack_total}${ac}${verdictTail}`;
            const detail = d.attack_breakdown ? `Attack: ${d.attack_breakdown}` : '';
            pills.push(_buildPill(cls, header, detail));
        }
        if (d.damage_total != null) {
            const type = d.damage_type ? ` ${escapeHTML(d.damage_type)}` : '';
            const applied = (d.damage_applied || 0) > 0 && d.target_hp_after != null
                ? ` (${d.target_hp_before != null ? d.target_hp_before + ' → ' : ''}${d.target_hp_after} HP)`
                : '';
            const resist = d.target_resistance_applied ? ' 🛡' : '';
            const status = d.target_dead ? ' 💀' : (d.target_dying ? ' 💤' : '');
            const header = `💥 ${d.damage_total}${type}${applied}${resist}${status}`;
            const detail = d.damage_breakdown ? `Damage: ${d.damage_breakdown}` : '';
            pills.push(_buildPill('chip-damage', header, detail));
        }
        if (d.bonus_damage_total != null && d.bonus_damage_total > 0) {
            const bonusLabel = d.bonus_damage_label || 'Bonus';
            pills.push(`<span class="result-pill chip-buff">✨ ${escapeHTML(bonusLabel)} +${d.bonus_damage_total}</span>`);
        }
        if ((d.damage_applied || 0) > 0) {
            pills.push(`<button type="button" class="result-pill chip-undo weapon-atk-undo" data-attack-id="${escapeHTML(d.id || '')}" title="Revert this damage application">↶ Undo</button>`);
        }
        if (d.is_save) {
            pills.push(`<button type="button" class="result-pill chip-prompt weapon-atk-save-btn" title="Prompt all players for a ${escapeHTML(d.save_ability)} save">📋 Prompt ${escapeHTML(d.save_ability)} save · DC ${escapeHTML(String(d.save_dc || ''))}</button>`);
        }
        const pillsHtml = pills.length ? `<div class="result-pills">${pills.join('')}</div>` : '';

        // Detailed dice breakdowns (attack roll d20 + base damage +
        // bonus damage) move into ▾ details so the card stays clean.
        // The pills above carry the totals; the breakdown is audit.
        const detailRows = [];
        if (!d.is_save && d.attack_total != null) {
            detailRows.push(`<div class="roll-card-breakdown">🎯 ${formatBreakdown(d.attack_breakdown || '')}</div>`);
        }
        if (d.damage_total != null && d.damage_breakdown) {
            detailRows.push(`<div class="roll-card-breakdown">💥 ${formatBreakdown(d.damage_breakdown)}</div>`);
        }
        if (d.bonus_damage_total != null && d.bonus_damage_total > 0 && d.bonus_damage_breakdown) {
            detailRows.push(`<div class="roll-card-breakdown">✨ ${formatBreakdown(d.bonus_damage_breakdown)}</div>`);
        }
        if (d.desc) detailRows.push(`<div class="spell-cast-desc">${escapeHTML(d.desc)}</div>`);
        const detailsHtml = detailRows.length
            ? `<details class="roll-card-details"><summary>▾ details</summary>${detailRows.join('')}</details>`
            : '';

        const targetTagHtml = _targetTagHtml(d);
        const li = document.createElement('li');
        li.dataset.attackId = d.id;
        li.innerHTML = `
            <div class="spell-cast-card weapon-atk-card">
                <div class="roll-card-header">
                    <div class="roll-card-avatar">${avatarInner}</div>
                    <span class="roll-card-user" data-uid="${d.caster_user_id}"${color ? ` style="color:${escapeHTML(color)}"` : ''}>${escapeHTML(dispName)}</span>
                    ${targetTagHtml}
                    <span class="spell-cast-slot">⚔ Attack</span>
                    <span class="roll-card-time">${timeStr}</span>
                </div>
                <div class="spell-cast-body">
                    <div class="spell-cast-name-row">
                        <span class="spell-cast-name">🗡 ${escapeHTML(d.attack_name || 'Attack')}</span>
                        ${metaBits.length ? `<span class="spell-cast-meta-inline">· ${metaBits.join(' · ')}</span>` : ''}
                    </div>
                    ${pillsHtml}
                    ${detailsHtml}
                    ${_overBudgetBadge(d)}
                    <div class="spell-cast-results"></div>
                </div>
            </div>`;
        ul.appendChild(li);
        _scrollRollLogToBottom();

        const saveBtn = li.querySelector('.weapon-atk-save-btn');
        if (saveBtn) saveBtn.addEventListener('click', () => promptAttackSave(d, li, saveBtn));

        // v2.24.0 Phase T.2: wire the ↶ Undo button. POSTs the attack
        // id back; server reverts HP via the in-memory damage log.
        const undoBtn = li.querySelector('.weapon-atk-undo');
        if (undoBtn) {
            undoBtn.addEventListener('click', async () => {
                undoBtn.disabled = true;
                try {
                    const r = await fetch(`/api/campaign/${CAMPAIGN_ID}/undo_attack_damage`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ attack_id: d.id }),
                    });
                    if (!r.ok) {
                        let body; try { body = await r.json(); } catch { body = null; }
                        (window.showToast || function(m){ alert(m); })(
                            `Undo failed: ${body ? JSON.stringify(body) : r.status}`, 'error');
                        undoBtn.disabled = false;
                        return;
                    }
                    const data = await r.json().catch(() => ({}));
                    undoBtn.textContent = `↶ Reverted ${data.reverted || ''}`;
                    undoBtn.classList.add('undone');
                } catch (e) {
                    console.warn('undo_attack_damage failed:', e);
                    undoBtn.disabled = false;
                }
            });
        }

        // Stash the attack metadata on the element so the roll listener can
        // correlate save responses back to this card (matches by note prefix).
        li._spellCast = {
            // Reuse the spell-cast save-correlation field name so the existing
            // roll listener appends pass/fail rows here without modification.
            _saveLabel: null,
            spell_save_ability: d.save_ability,
            spell_name: d.attack_name,
        };
        _persistRollEntry('weapon_attack', d);
    }

    async function promptAttackSave(d, li, btn) {
        const dc = parseInt(d.save_dc, 10);
        if (!Number.isFinite(dc)) { showToast('No DC set on attack.', 'error'); return; }
        const label = `${d.attack_name} — ${d.save_ability} save`;
        btn.disabled = true;
        try {
            const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/roll_request`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    label,
                    base_expression: '1d20',
                    stat_key: `${d.save_ability.toLowerCase()}_save`,
                    dc,
                    visibility: 'public',
                }),
            });
            if (!resp.ok) throw new Error(await resp.text());
            if (li._spellCast) li._spellCast._saveLabel = label;
            btn.textContent = `📋 Save prompt sent (DC ${dc})`;
        } catch (e) {
            btn.disabled = false;
            showToast('Could not post save prompt.', 'error');
            console.error(e);
        }
    }

    async function promptSpellSave(d, li, btn) {
        const dcStr = window.prompt(
            `${d.spell_save_ability} save DC for "${d.spell_name}"?`,
            '13'
        );
        if (dcStr === null) return;
        const dc = parseInt(dcStr, 10);
        if (!Number.isFinite(dc)) { showToast('Enter a numeric DC.', 'error'); return; }
        const label = `${d.spell_name} — ${d.spell_save_ability} save`;
        btn.disabled = true;
        try {
            const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/roll_request`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    label,
                    base_expression: '1d20',
                    stat_key: `${d.spell_save_ability.toLowerCase()}_save`,
                    dc,
                    visibility: 'public',
                }),
            });
            if (!resp.ok) throw new Error(await resp.text());
            // Remember the label so we can match incoming roll notes back to this card
            if (li._spellCast) li._spellCast._saveLabel = label;
            btn.textContent = `📋 Save prompt sent (DC ${dc})`;
        } catch (e) {
            btn.disabled = false;
            showToast('Could not post save prompt.', 'error');
            console.error(e);
        }
    }

    function _myCharsForCast(d) {
        // GM may roll as any token; players only as their own characters/tokens
        if (ME.isGm) {
            const tokenChars = tokens
                .filter(t => t.character_id)
                .map(t => characters.find(c => c.id === t.character_id))
                .filter(Boolean);
            // De-duplicate while preserving order
            const seen = new Set();
            const uniq = [];
            for (const c of tokenChars) {
                if (!seen.has(c.id)) { seen.add(c.id); uniq.push(c); }
            }
            // Always include the caster's own character at the top
            const caster = characters.find(c => c.id === d.caster_char_id);
            if (caster && !seen.has(caster.id)) uniq.unshift(caster);
            return uniq.length ? uniq : characters.filter(c => c.owner_user_id != null);
        }
        return characters.filter(c => c.owner_user_id === ME.id);
    }

    // v2.42.2: spell-cast damage button handler. The damage of a spell is
    // attributed to the caster by definition (Fire Bolt by Thalindra → roll
    // is "Fire Bolt damage as Thalindra") — no picker needed even for GMs
    // who own multiple tokens. Falls through to ``openDamagePicker`` only
    // when the caster char isn't in the local ``characters`` array (legacy
    // safety net; shouldn't trigger in normal play).
    async function _castDamageClick(d, damageExpr, li, btn) {
        if (btn && btn.disabled) return;
        const caster = d.caster_char_id
            ? characters.find(c => c.id === d.caster_char_id)
            : null;
        if (!caster) {
            // No identified caster — fall back to the legacy picker.
            return openDamagePicker(d, damageExpr, li);
        }
        if (btn) btn.disabled = true;
        try {
            const ok = await rollSpellDamage(d, damageExpr, caster, li);
            // Hide the button after a successful roll so the card visibly
            // commits to the result. The roll itself lands as a new entry
            // in the log via the WS broadcast. On failure, re-enable so the
            // user can retry.
            if (ok && btn) btn.style.display = 'none';
            else if (!ok && btn) btn.disabled = false;
        } catch (e) {
            console.warn('spell damage roll failed:', e);
            if (btn) btn.disabled = false;
        }
    }

    function openDamagePicker(d, damageExpr, li) {
        const choices = _myCharsForCast(d);
        if (!choices.length) {
            showToast('No tokens available to roll damage as.', 'error');
            return;
        }
        // If the user only has one option, skip the picker and roll immediately
        if (choices.length === 1) {
            return rollSpellDamage(d, damageExpr, choices[0], li);
        }
        const overlay = document.createElement('div');
        overlay.className = 'token-picker-overlay';
        overlay.innerHTML = `
            <div class="token-picker">
                <div class="token-picker-title">Roll ${escapeHTML(d.spell_name)} damage as…</div>
                <div class="token-picker-list">${
                    choices.map(c => `<button type="button" class="token-picker-item" data-cid="${c.id}">${escapeHTML(c.name)}</button>`).join('')
                }</div>
                <div class="token-picker-foot">
                    <button type="button" class="token-picker-cancel">Cancel</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        overlay.addEventListener('click', (ev) => {
            if (ev.target === overlay) overlay.remove();
        });
        overlay.querySelector('.token-picker-cancel').addEventListener('click', () => overlay.remove());
        overlay.querySelectorAll('.token-picker-item').forEach(b => {
            b.addEventListener('click', () => {
                const cid = parseInt(b.dataset.cid, 10);
                const c = choices.find(c => c.id === cid);
                overlay.remove();
                if (c) rollSpellDamage(d, damageExpr, c, li);
            });
        });
    }

    async function rollSpellDamage(d, damageExpr, asChar, _li) {
        const note = `${d.spell_name} damage (as ${asChar.name})`;
        // The /roll endpoint uses the caller's user_id, but we override the
        // displayed character via the note. The portrait/color in the broadcast
        // come from the user's first character, so the note carries the chosen
        // token's name explicitly so other players can tell which token rolled.
        const visibility = (document.getElementById('roll-vis')?.value) || 'public';
        const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/roll`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ expression: damageExpr, visibility, note }),
        });
        if (!resp.ok) {
            showToast('Damage roll failed: ' + await resp.text(), 'error');
            return false;
        }
        return true;
    }

    function formatBreakdown(s) {
        // HTML-escape the string, then bold individual die values inside [...]
        return escapeHTML(s).replace(/\[([^\]]*)\]/g, (_, inner) => {
            const bolded = inner.replace(/(\d+)/g, '<strong>$1</strong>');
            return `[${bolded}]`;
        });
    }

    function escapeHTML(s) {
        return String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
    }

    // ---------- Dice form ----------
    document.getElementById('roll-expr-clear-btn')?.addEventListener('click', () => {
        const exprInput = document.getElementById('roll-expr');
        exprInput.value = '';
        exprInput.focus();
    });

    document.getElementById('roll-form').addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const expr = document.getElementById('roll-expr').value.trim();
        const vis = document.getElementById('roll-vis').value;
        if (!expr) return;
        const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/roll`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ expression: expr, visibility: vis }),
        });
        if (!resp.ok) {
            const txt = await resp.text();
            alert('Roll failed: ' + txt);
        }
        // The result will arrive via the WS broadcast.
    });

    document.querySelectorAll('.quick-die').forEach(btn => {
        btn.addEventListener('click', () => {
            const exprEl = document.getElementById('roll-expr');
            const current = exprEl.value.trim();
            const newExpr = btn.dataset.expr;

            if (!current) {
                exprEl.value = newExpr;
                return;
            }

            // Try to merge with an existing term of the same type (e.g. 1d20d + 1d20d → 2d20d)
            const diceRe = /^(\d+)(d\d+\w*)$/i;
            const newMatch = newExpr.match(diceRe);
            if (newMatch) {
                const newType = newMatch[2];
                const newCount = parseInt(newMatch[1]);
                const terms = current.split('+').map(t => t.trim());
                let merged = false;
                const newTerms = terms.map(term => {
                    const m = term.match(diceRe);
                    if (!merged && m && m[2] === newType) {
                        merged = true;
                        return (parseInt(m[1]) + newCount) + newType;
                    }
                    return term;
                });
                exprEl.value = merged ? newTerms.join('+') : current + '+' + newExpr;
            } else {
                exprEl.value = current + '+' + newExpr;
            }
        });
    });

    // Player-tab dice form handlers removed in 2.1.6 alongside the
    // #player-dice-panel HTML block. The roll-log Dice Roller card
    // (#roll-form) is the single dice UI on the tabletop.

    // ---------- GM: add token button ----------
    const addBtn = document.getElementById('add-token-btn');
    if (addBtn) {
        addBtn.addEventListener('click', () => {
            const modal = document.getElementById('add-token-modal');
            // Populate template grid
            const grid = document.getElementById('atm-template-grid');
            const noTmpl = document.getElementById('atm-no-templates');
            const settingsLink = document.getElementById('atm-settings-link');
            if (settingsLink) settingsLink.href = `/campaign/${CAMPAIGN_ID}/settings#tmpl`;
            grid.innerHTML = '';
            if (!templates.length) {
                noTmpl.style.display = '';
                grid.style.display = 'none';
            } else {
                noTmpl.style.display = 'none';
                grid.style.display = '';
                templates.forEach(tmpl => {
                    const card = document.createElement('div');
                    card.style.cssText = 'background:#20232a;border:1px solid #2e3140;border-radius:6px;overflow:hidden;cursor:pointer;transition:border-color 0.15s;';
                    card.addEventListener('mouseenter', () => { card.style.borderColor = '#6cb'; });
                    card.addEventListener('mouseleave', () => { card.style.borderColor = '#2e3140'; });
                    if (tmpl.image_url) {
                        const img = document.createElement('img');
                        img.src = tmpl.image_url;
                        img.style.cssText = 'width:100%;height:90px;object-fit:cover;display:block;';
                        card.appendChild(img);
                    } else {
                        const ph = document.createElement('div');
                        ph.style.cssText = 'width:100%;height:90px;display:flex;align-items:center;justify-content:center;background:#1e2030;font-size:28px;font-weight:700;color:#556;';
                        ph.textContent = tmpl.name.slice(0,1).toUpperCase();
                        card.appendChild(ph);
                    }
                    const info = document.createElement('div');
                    info.style.cssText = 'padding:7px 8px;';
                    const nameEl = document.createElement('div');
                    nameEl.style.cssText = 'font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
                    nameEl.textContent = tmpl.name;
                    info.appendChild(nameEl);
                    if (tmpl.tags && tmpl.tags.length) {
                        const tags = document.createElement('div');
                        tags.style.cssText = 'font-size:10px;color:#6cb;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px;';
                        tags.textContent = tmpl.tags.join(', ');
                        info.appendChild(tags);
                    }
                    card.appendChild(info);
                    card.addEventListener('click', async () => {
                        modal.style.display = 'none';
                        const center = viewportCenterWorld();
                        const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/tokens`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                token_template_id: tmpl.id,
                                x: center.x, y: center.y,
                            }),
                        });
                        if (!resp.ok) alert('Failed to place token');
                    });
                    grid.appendChild(card);
                });
            }

            // ── Populate Players grid (campaign characters) ──
            // Multi-select: click cards to toggle selection, then use
            // "Place Selected" to place all at once. Placed tokens can
            // be removed by clicking their card directly (bypasses multi-select).
            const playerGrid = document.getElementById('atm-player-grid');
            const noChars = document.getElementById('atm-no-characters');
            const placeSelBtn = document.getElementById('atm-place-selected-btn');
            const selCountEl = document.getElementById('atm-selected-count');
            const selectedIds = new Set();

            function syncPlaceBtn() {
                const n = selectedIds.size;
                if (placeSelBtn) {
                    placeSelBtn.style.display = n > 0 ? '' : 'none';
                    if (selCountEl) selCountEl.textContent = n;
                }
            }

            if (playerGrid) {
                playerGrid.innerHTML = '';
                selectedIds.clear();
                syncPlaceBtn();
                if (!characters.length) {
                    noChars.style.display = '';
                    playerGrid.style.display = 'none';
                } else {
                    noChars.style.display = 'none';
                    playerGrid.style.display = 'grid';
                    characters.forEach(ch => {
                        const placed = charTokenOnMap(ch.id);
                        const card = document.createElement('div');
                        card.dataset.charId = ch.id;
                        card.style.cssText =
                            'background:#20232a;border:2px solid #2e3140;border-radius:6px;' +
                            'overflow:hidden;cursor:pointer;transition:border-color 0.15s,box-shadow 0.15s;' +
                            'position:relative;' + (placed ? 'opacity:0.78;' : '');

                        function applySelStyle() {
                            const sel = selectedIds.has(ch.id);
                            card.style.borderColor = sel ? '#6cb' : (placed ? '#3a6a50' : '#2e3140');
                            card.style.boxShadow = sel ? '0 0 0 1px #6cb' : 'none';
                        }

                        const portrait = ch.portrait_url || (ch.owner_user_id ? USER_PORTRAITS[ch.owner_user_id] : null);
                        if (portrait) {
                            const img = document.createElement('img');
                            img.src = portrait;
                            img.style.cssText = 'width:100%;height:90px;object-fit:cover;display:block;';
                            card.appendChild(img);
                        } else {
                            const ph = document.createElement('div');
                            const tint = ch.color || (ch.owner_user_id ? USER_COLORS[ch.owner_user_id] : null) || '#3a3f55';
                            ph.style.cssText =
                                'width:100%;height:90px;display:flex;align-items:center;justify-content:center;' +
                                'background:' + tint + ';font-size:28px;font-weight:700;color:#fff;' +
                                'text-shadow:0 1px 2px rgba(0,0,0,0.5);';
                            ph.textContent = ch.name.slice(0, 1).toUpperCase();
                            card.appendChild(ph);
                        }
                        if (placed) {
                            const badge = document.createElement('span');
                            badge.textContent = 'On map';
                            badge.style.cssText =
                                'position:absolute;top:5px;right:5px;font-size:9px;font-weight:700;' +
                                'background:rgba(34,68,55,0.92);color:#7c9;border:1px solid #3a6a50;' +
                                'border-radius:3px;padding:1px 5px;letter-spacing:.04em;';
                            card.appendChild(badge);
                        }
                        const info = document.createElement('div');
                        info.style.cssText = 'padding:6px 8px;';
                        const nameEl = document.createElement('div');
                        nameEl.style.cssText = 'font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
                        nameEl.textContent = ch.name;
                        info.appendChild(nameEl);
                        const ownerName = ch.owner_user_id ? USER_CHAR_NAMES[ch.owner_user_id] : null;
                        if (ownerName && ownerName !== ch.name) {
                            const ownerEl = document.createElement('div');
                            ownerEl.style.cssText = 'font-size:10px;color:var(--fg-mute);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px;';
                            ownerEl.textContent = ownerName;
                            info.appendChild(ownerEl);
                        }
                        card.appendChild(info);
                        card.addEventListener('click', async () => {
                            if (card.dataset.busy === '1') return;
                            // Already on map → remove immediately (no multi-select for removals)
                            if (charTokenOnMap(ch.id)) {
                                card.dataset.busy = '1';
                                try {
                                    const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/character/${ch.id}/token`, {
                                        method: 'DELETE',
                                        headers: { 'Content-Type': 'application/json' },
                                    });
                                    if (!resp.ok) alert('Failed: ' + await resp.text());
                                } finally {
                                    delete card.dataset.busy;
                                }
                                return;
                            }
                            // Not on map → toggle selection
                            if (selectedIds.has(ch.id)) {
                                selectedIds.delete(ch.id);
                            } else {
                                selectedIds.add(ch.id);
                            }
                            applySelStyle();
                            syncPlaceBtn();
                        });
                        applySelStyle();
                        playerGrid.appendChild(card);
                    });
                }
            }

            if (placeSelBtn) {
                placeSelBtn.onclick = async () => {
                    if (!selectedIds.size || placeSelBtn.dataset.busy === '1') return;
                    placeSelBtn.dataset.busy = '1';
                    placeSelBtn.disabled = true;
                    const center = viewportCenterWorld();
                    const ids = Array.from(selectedIds);
                    try {
                        for (const id of ids) {
                            const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/character/${id}/place-token`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify(center),
                            });
                            if (!resp.ok) { alert('Failed: ' + await resp.text()); break; }
                        }
                    } finally {
                        delete placeSelBtn.dataset.busy;
                        placeSelBtn.disabled = false;
                    }
                    modal.style.display = 'none';
                };
            }

            // Tab switching
            modal.querySelectorAll('.atm-tab-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    modal.querySelectorAll('.atm-tab-btn').forEach(b => {
                        b.style.background = '#2a2d36'; b.style.color = '#bbb'; b.style.borderColor = '#444';
                    });
                    btn.style.background = '#1a3328'; btn.style.color = '#6cb'; btn.style.borderColor = '#3a6a50';
                    modal.querySelectorAll('[id^="atm-tab-"]').forEach(t => t.style.display = 'none');
                    const tab = document.getElementById(btn.dataset.tab);
                    if (tab) tab.style.display = '';
                });
            });
            // Reset to library tab
            modal.querySelectorAll('.atm-tab-btn').forEach(b => {
                b.style.background = '#2a2d36'; b.style.color = '#bbb'; b.style.borderColor = '#444';
            });
            modal.querySelectorAll('[id^="atm-tab-"]').forEach(t => t.style.display = 'none');
            const libBtn = modal.querySelector('[data-tab="atm-tab-library"]');
            const libTab = document.getElementById('atm-tab-library');
            if (libBtn) { libBtn.style.background = '#1a3328'; libBtn.style.color = '#6cb'; libBtn.style.borderColor = '#3a6a50'; }
            if (libTab) libTab.style.display = '';
            modal.style.display = 'flex';
        });

        // Blank token placement
        const blankPlaceBtn = document.getElementById('atm-blank-place');
        if (blankPlaceBtn) {
            blankPlaceBtn.addEventListener('click', async () => {
                const label = document.getElementById('atm-blank-label').value.trim() || 'Token';
                const color = document.getElementById('atm-blank-color').value || '#cc3333';
                document.getElementById('add-token-modal').style.display = 'none';
                const center = viewportCenterWorld();
                const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/tokens`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ label, color, x: center.x, y: center.y }),
                });
                if (!resp.ok) alert('Failed to add token');
            });
        }

        // Open5e search tab
        (function() {
            const searchInput = document.getElementById('atm-o5e-search');
            const statusEl   = document.getElementById('atm-o5e-status');
            const resultsEl  = document.getElementById('atm-o5e-results');
            if (!searchInput) return;

            let o5eTimer = null;

            function renderResults(creatures) {
                resultsEl.innerHTML = '';
                if (!creatures.length) {
                    statusEl.textContent = 'No results.';
                    return;
                }
                statusEl.textContent = `${creatures.length} result${creatures.length === 1 ? '' : 's'}`;
                creatures.forEach(c => {
                    const row = document.createElement('div');
                    row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:6px 10px;background:var(--bg-3,#1a1d24);border-radius:4px;gap:8px;';
                    const info = document.createElement('div');
                    const cr   = c.cr != null ? `CR ${c.cr}` : '';
                    const type = [c.size, c.type, cr].filter(Boolean).join(' · ');
                    info.innerHTML = `<div style="font-size:12px;font-weight:600;">${c.name}</div><div style="font-size:10px;color:var(--fg-mute);">${type}</div>`;
                    const btn = document.createElement('button');
                    btn.textContent = 'Import & Place';
                    btn.style.cssText = 'font-size:11px;white-space:nowrap;flex-shrink:0;';
                    btn.addEventListener('click', async () => {
                        btn.disabled = true;
                        btn.textContent = 'Importing…';
                        try {
                            const imp = await fetch(`/api/campaign/${CAMPAIGN_ID}/templates/import-monster`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ slug: c.slug }),
                            });
                            if (!imp.ok) throw new Error(await imp.text());
                            const tmpl = await imp.json();
                            document.getElementById('add-token-modal').style.display = 'none';
                            const center = viewportCenterWorld();
                            const place = await fetch(`/api/campaign/${CAMPAIGN_ID}/tokens`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ template_id: tmpl.id, x: center.x, y: center.y }),
                            });
                            if (!place.ok) alert('Template imported but token placement failed.');
                        } catch (err) {
                            btn.disabled = false;
                            btn.textContent = 'Import & Place';
                            alert(`Import failed: ${err.message}`);
                        }
                    });
                    row.appendChild(info);
                    row.appendChild(btn);
                    resultsEl.appendChild(row);
                });
            }

            async function doSearch(q) {
                if (!q) { statusEl.textContent = ''; resultsEl.innerHTML = ''; return; }
                statusEl.textContent = 'Searching…';
                resultsEl.innerHTML = '';
                try {
                    const r = await fetch(`/api/open5e/monsters?search=${encodeURIComponent(q)}&limit=25`);
                    if (!r.ok) throw new Error(r.statusText);
                    const data = await r.json();
                    renderResults(data.results || data);
                } catch (e) {
                    statusEl.textContent = `Error: ${e.message}`;
                }
            }

            searchInput.addEventListener('input', () => {
                clearTimeout(o5eTimer);
                o5eTimer = setTimeout(() => doSearch(searchInput.value.trim()), 350);
            });

            // Clear search when tab is opened.
            // v2.25.2 fix: ``modal`` was a closure-scope variable inside
            // the addBtn click handler and isn't visible here (this IIFE
            // runs at script init, before any click). Re-resolve via
            // document.querySelectorAll scoped to the modal id.
            document.querySelectorAll('#add-token-modal .atm-tab-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    if (btn.dataset.tab === 'atm-tab-open5e') {
                        searchInput.value = '';
                        statusEl.textContent = '';
                        resultsEl.innerHTML = '';
                        setTimeout(() => searchInput.focus(), 50);
                    }
                });
            });
        })();

        // Close modal on backdrop click
        document.getElementById('add-token-modal').addEventListener('click', (ev) => {
            if (ev.target === ev.currentTarget) ev.currentTarget.style.display = 'none';
        });
    }

    // ---------- GM: token tracker ----------

    // buildMiniSheetEl() removed in 2.1.4 along with the 📋 token-tracker
    // expand. The Jinja-rendered Characters-panel mini-sheet is now the
    // single mini-sheet UI on the tabletop.

    async function patchToken(id, updates) {
        return fetch(`/api/campaign/${CAMPAIGN_ID}/token/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates),
        });
    }

    function renderTokenTracker() {
        const list = document.getElementById('token-tracker-list');
        if (!list) return;
        list.innerHTML = '';
        if (!tokens.length) {
            list.innerHTML = '<p class="muted" style="font-size:11px;margin:4px 0;">No tokens on this map.</p>';
            return;
        }
        // Split into player- vs GM-controlled tokens. The signal is
        // ``controller_user_id``: set by place_character_token when the
        // GM places a player's character token; remains null for NPCs
        // / monsters / blank tokens the GM creates from the Add Token
        // modal. The two sections render with their own headers so the
        // GM can scan players first during combat.
        const playerTokens = tokens.filter(t => t.controller_user_id != null);
        const npcTokens    = tokens.filter(t => t.controller_user_id == null);

        function _appendSectionHeader(label, count) {
            const h = document.createElement('div');
            h.className = 'tt-section-header';
            h.style.cssText = 'font-size:9px;font-weight:700;color:var(--fg-mute);text-transform:uppercase;letter-spacing:.06em;padding:8px 0 4px;margin-top:4px;border-bottom:1px solid var(--border);';
            h.innerHTML = `${label} <span style="color:var(--fg);font-weight:400;font-size:10px;letter-spacing:0;">(${count})</span>`;
            list.appendChild(h);
        }
        function _renderToken(t) {
            const row = document.createElement('div');
            row.className = 'tt-row';
            row.dataset.id = t.id;
            const memberOpts = (typeof MEMBERS !== 'undefined' ? MEMBERS : [])
                .map(m => `<option value="${m.id}"${t.controller_user_id === m.id ? ' selected' : ''}>${escapeHTML(m.name)}</option>`)
                .join('');
            let portraitUrl = t.image_url || null;
            if (!portraitUrl && t.character_id) {
                const ch = characters.find(c => c.id === t.character_id);
                portraitUrl = ch?.portrait_url || null;
            }
            const avatarHtml = portraitUrl
                ? `<img class="tt-portrait" src="${escapeHTML(portraitUrl)}" alt="">`
                : `<span class="tt-swatch" style="background:${escapeHTML(t.color || '#cc3333')}"></span>`;
            // v2.25.0: 📋 Sheet button — opens the character sheet
            // (PC) or monster sheet (NPC) via the existing
            // ``a.character-sheet-link`` / ``a.monster-sheet-link``
            // interceptor in tabletop.html. Skipped for tokens with
            // neither character_id nor token_template_id (rare blank
            // tokens the GM created from the Add Token modal).
            const sheetBtnHtml = (t.character_id || t.token_template_id)
                ? `<a class="tt-btn tt-sheet ${t.character_id ? 'character-sheet-link' : 'monster-sheet-link'}"
                       href="/campaign/${CAMPAIGN_ID}/${t.character_id ? 'character/' + t.character_id : 'monster-template/' + t.token_template_id}/sheet"
                       target="_blank" rel="noopener"
                       data-${t.character_id ? 'character' : 'monster'}-name="${escapeHTML(t.label || '')}"
                       title="Open ${t.character_id ? 'character' : 'monster'} sheet">📋</a>`
                : '';
            // v2.38.0 Phase T.9: 🎯 Target button — tap to set this
            // token as the current target. The same effect a desktop
            // user gets from double-clicking the token on the canvas,
            // but available from the (tap-friendly) Token Tracker
            // panel on mobile. Highlights when the token is already
            // the active target so the GM can see at a glance who's
            // marked.
            const isTargeted = _targeting && _targeting.isTargeted(t.id);
            const targetBtnHtml = `<button class="tt-btn tt-target${isTargeted ? ' tt-target-on' : ''}" title="${isTargeted ? 'Clear target' : 'Set as target'}" data-token-id="${t.id}">🎯</button>`;
            row.innerHTML = `
                ${avatarHtml}
                <span class="tt-name" contenteditable="true" spellcheck="false">${escapeHTML(t.label)}</span>
                <button class="tt-btn tt-vis" title="${t.is_hidden ? 'Show token' : 'Hide token'}">${t.is_hidden ? '🚫' : '👁'}</button>
                ${targetBtnHtml}
                ${sheetBtnHtml}
                <label class="tt-btn tt-art-label" title="Upload art">
                    🖼<input class="tt-art-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif" style="display:none">
                </label>
                <select class="tt-ctrl">
                    <option value="">GM</option>
                    ${memberOpts}
                </select>
                <button class="tt-btn tt-del" title="Delete token">🗑</button>`;
            // v2.38.0 Phase T.9: wire the target button — tap toggles.
            const targetBtn = row.querySelector('.tt-target');
            if (targetBtn) {
                targetBtn.addEventListener('click', (ev) => {
                    ev.stopPropagation();
                    if (_targeting.isTargeted(t.id)) {
                        _targeting.clear();
                    } else {
                        _targeting.setTarget(t.id);
                    }
                });
            }
            list.appendChild(row);

            const nameEl = row.querySelector('.tt-name');
            nameEl.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); nameEl.blur(); } });
            nameEl.addEventListener('blur', () => {
                const label = nameEl.textContent.trim().slice(0, 120);
                if (label !== t.label) patchToken(t.id, { label });
            });

            row.querySelector('.tt-vis').addEventListener('click', () => {
                patchToken(t.id, { is_hidden: !t.is_hidden });
            });

            row.querySelector('.tt-art-input').addEventListener('change', async (e) => {
                const file = e.target.files[0];
                if (!file) return;
                const fd = new FormData();
                fd.append('image', file);
                const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/token/${t.id}/image`, { method: 'POST', body: fd });
                if (!resp.ok) alert('Image upload failed');
            });

            row.querySelector('.tt-ctrl').addEventListener('change', (e) => {
                const val = e.target.value;
                patchToken(t.id, { controller_user_id: val ? parseInt(val, 10) : null });
            });

            row.querySelector('.tt-del').addEventListener('click', () => {
                if (!confirm(`Delete "${t.label}"?`)) return;
                fetch(`/api/campaign/${CAMPAIGN_ID}/tokens/${t.id}`, { method: 'DELETE' });
            });

            // 📋 mini-sheet expand removed in 2.1.4 — the Characters panel
            // mini-sheet is now the single mini-sheet UI on the tabletop.
        }   // end _renderToken

        if (playerTokens.length) {
            _appendSectionHeader('👤 Players', playerTokens.length);
            playerTokens.forEach(_renderToken);
        }
        if (npcTokens.length) {
            _appendSectionHeader('⚙ GM / NPCs', npcTokens.length);
            npcTokens.forEach(_renderToken);
        }
    }

    renderTokenTracker();

    // ---------- Player: place/remove character token buttons ----------
    function charTokenOnMap(charId) {
        return tokens.find(t => t.character_id === charId) || null;
    }

    function canPlaceChar(charId) {
        // GM-only as of v0.63.0. Players no longer add or remove their
        // own tokens — the GM does it for them from the Token Management
        // panel in the Battle drawer. The local check matches the
        // server-side gate in place_character_token / remove_character_token;
        // even if the player tried to bypass the UI, the API returns 403.
        return !!ME.isGm;
    }

    function refreshPlaceButtons() {
        document.querySelectorAll('.char-row[data-char-id]').forEach(row => {
            const charId = parseInt(row.dataset.charId, 10);
            if (!canPlaceChar(charId)) return;
            let btn = row.querySelector('.char-place-btn');
            if (!btn) {
                btn = document.createElement('button');
                btn.className = 'char-expand-btn char-place-btn';
                btn.style.marginRight = '2px';
                const expandBtn = row.querySelector('.char-expand-btn:not(.char-place-btn)');
                row.insertBefore(btn, expandBtn);
                btn.addEventListener('click', async () => {
                    const existing = charTokenOnMap(charId);
                    const url = existing
                        ? `/api/campaign/${CAMPAIGN_ID}/character/${charId}/token`
                        : `/api/campaign/${CAMPAIGN_ID}/character/${charId}/place-token`;
                    btn.disabled = true;
                    try {
                        // For place (POST): send viewport-center world coords so
                        // the new token lands where the GM is looking. For
                        // remove (DELETE): no body needed.
                        const init = {
                            method: existing ? 'DELETE' : 'POST',
                            headers: { 'Content-Type': 'application/json' },
                        };
                        if (!existing) init.body = JSON.stringify(viewportCenterWorld());
                        const resp = await fetch(url, init);
                        if (!resp.ok) alert('Failed: ' + await resp.text());
                    } finally { btn.disabled = false; }
                });
            }
            const existing = charTokenOnMap(charId);
            btn.textContent = existing ? '⊖' : '⊕';
            btn.title = existing ? 'Remove token from map' : 'Place token on map';
        });
    }

    refreshPlaceButtons();

    // ---------- Sheet opener ----------
    // The full D&D 5e sheet is now always opened in a separate browser tab
    // pointed at the standalone /sheet route. The previous in-page modal
    // path (DOMParser + script-stripping + manual sheet.js re-injection)
    // was retired in v0.35.3 because every inline <script> block inside
    // sheet_dnd5e.html (Wild Shape buttons, Class Resources panel, rest
    // handlers, …) was being stripped during injection — leaving those
    // features silently broken in the modal context. A new tab gets the
    // full standalone page with every inline script intact.
    window.renderTokenTracker = renderTokenTracker;

    window.openSheet = function (charId) {
        if (!charId) return;
        window.open(
            `/campaign/${CAMPAIGN_ID}/character/${charId}/sheet`,
            '_blank',
            'noopener'
        );
    };

    // v2.28.0: rehydrate the roll log from localStorage so chat-card
    // history survives page refreshes. Runs once after the append fns
    // are defined; the ``_rollLogHydrating`` guard inside
    // ``_persistRollEntry`` prevents the replay from re-saving each
    // entry. Each card rebuilds through its original append fn so
    // all click handlers (Undo / Apply Healing / Save) re-wire.
    _hydrateRollLog();
})();
