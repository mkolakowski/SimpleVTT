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
    //
    // v2.88.0 — canvas is now sized to (MAP_W + 2*stripH) × (MAP_H +
    // 2*stripH) so the grid coordinate gutter can render OUTSIDE the
    // map image. ``stripH`` is the gutter width in CSS pixels, set
    // server-side via the data-strip-h attribute and matched to the
    // same formula tabletop.js used internally pre-v2.88.0
    // (max(16, min(28, round(gridSize*0.32)))). The canvas is also
    // positioned at top:-stripH;left:-stripH inside the
    // #map-transform wrapper so that after ctx.translate(stripH,
    // stripH) the canvas's logical (0, 0) coincides with the
    // bg-layer image's (0, 0) — map-coord drawing keeps the same
    // coordinate space as before this version.
    const stripH = parseInt(canvas.dataset.stripH || '0', 10);
    const MAP_W = canvas.width - 2 * stripH;
    const MAP_H = canvas.height - 2 * stripH;
    const DPR = Math.max(1, window.devicePixelRatio || 1);
    // v2.714.0 — supersample-on-zoom. The backing-store resolution is a
    // ``renderScale`` multiple of the logical map size (the CSS display size
    // stays the logical map size, so the pan/zoom transform math is
    // unchanged). At rest renderScale = DPR (the v2.3.45 behaviour); when a
    // player zooms in, `scheduleRenderScaleUpdate` raises it toward
    // DPR×zoom (capped for memory) and re-rasters once on zoom-settle, so
    // the ~1000 px token sources are drawn at MANY more physical pixels
    // instead of the CSS transform bitmap-upscaling a fixed-res canvas.
    let renderScale = DPR;
    // Bounds: never exceed a single-dimension cap (older Safari/iOS choke
    // past ~4096) nor a total-area cap (~16.7M px on iOS), and never
    // supersample past DPR×4. Floors at DPR so an already-huge map that
    // exceeds the cap at DPR keeps its existing behaviour (never worse).
    const MAX_CANVAS_DIM = 4096;
    const MAX_CANVAS_AREA = 16e6;
    const RS_MAX = DPR * 4;
    function fittedRenderScale(targetRS) {
        const w = MAP_W + 2 * stripH;
        const h = MAP_H + 2 * stripH;
        const capByDim = MAX_CANVAS_DIM / Math.max(w, h);
        const capByArea = Math.sqrt(MAX_CANVAS_AREA / Math.max(1, w * h));
        const rs = Math.min(targetRS, RS_MAX, capByDim, capByArea);
        return Math.max(DPR, rs);
    }
    function applyRenderScale(rs) {
        renderScale = rs;
        canvas.width = Math.round((MAP_W + 2 * stripH) * rs);
        canvas.height = Math.round((MAP_H + 2 * stripH) * rs);
        canvas.style.width = (MAP_W + 2 * stripH) + 'px';
        canvas.style.height = (MAP_H + 2 * stripH) + 'px';
        // Resizing the backing store resets the 2D context — re-establish
        // the rs scale + the stripH origin shift + high-quality resampling.
        // Shift the drawing origin so logical (0, 0) is at canvas-physical
        // (stripH, stripH); the gutter strips paint at logical (-stripH..0)
        // which lands in the outer halo.
        ctx.setTransform(rs, 0, 0, rs, 0, 0);
        ctx.translate(stripH, stripH);
        // ``high`` resampling matters for the demo-token portraits which
        // are sourced ~1000 px wide and rendered at ~70 px on canvas; the
        // browser default (``low``) makes that downscale look mushy.
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
    }
    applyRenderScale(DPR);

    const initialData = JSON.parse(document.getElementById('initial-data').textContent);
    let tokens = initialData.tokens || [];
    // v2.710.0 — Phase 5 of vision-and-light: client dynamic lighting state.
    // The map ambient ("bright"/"dim"/"dark") + spell light/darkness/fog
    // emitters drive a canvas overlay (`drawLighting`). Bootstrapped from a
    // GET /tokens fetch on init (which carries both) and kept live by the
    // map_ambient_light / light_emitter_add / light_emitter_remove WS events.
    let mapAmbientLight = initialData.ambient_light || 'bright';
    let lightEmitters = initialData.light_emitters || [];
    // The server-rendered initial-data predates the vision fields, so pull
    // the active map's ambient + placed emitters once on load. Deferred
    // (async) so it runs after the sync init defines render() + CAMPAIGN_ID.
    (async () => {
        try {
            const r = await fetch(`/api/campaign/${CAMPAIGN_ID}/tokens`);
            if (!r.ok) return;
            const d = await r.json();
            if (d.ambient_light) mapAmbientLight = d.ambient_light;
            if (Array.isArray(d.light_emitters)) lightEmitters = d.light_emitters;
            try { render(); } catch (_) {}
        } catch (_) { /* lighting is best-effort presentation */ }
    })();
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

        // v2.88.0 — gutter strips + frame are back, but now drawn in
        // the OUTER halo (canvas-logical coords -stripH..0 and
        // MAP_W..MAP_W+stripH) instead of the inner edge of the map
        // (canvas coords 0..stripH). The canvas was expanded by 2*stripH
        // server-side and ctx.translate(stripH, stripH) shifts logical
        // (0, 0) to canvas-physical (stripH, stripH); drawing at
        // negative logical coords lands in the outer halo around the
        // bg image — so the labels and frame sit entirely OUTSIDE the
        // map bounds (per GM request, v2.87.3 → v2.88.0).
        ctx.fillStyle = 'rgba(0, 0, 0, 0.55)';
        // Top + bottom gutters (full width, stripH tall) at y = -stripH
        // and y = MAP_H. Both extend left/right by stripH so the four
        // corners are filled exactly once.
        ctx.fillRect(-stripH, -stripH, MAP_W + 2 * stripH, stripH);
        ctx.fillRect(-stripH, MAP_H, MAP_W + 2 * stripH, stripH);
        // Left + right gutters (MAP_H tall, stripH wide), between the
        // top and bottom strips so corners don't double-fill.
        ctx.fillRect(-stripH, 0, stripH, MAP_H);
        ctx.fillRect(MAP_W, 0, stripH, MAP_H);

        // Theme-accent border lines at the INNER edge of the gutter,
        // i.e., along the boundary between the gutter and the map
        // image. Frames the map cleanly without painting any pixels
        // inside the map itself.
        ctx.strokeStyle = accent;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, -0.5);
        ctx.lineTo(MAP_W, -0.5);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(-0.5, 0);
        ctx.lineTo(-0.5, MAP_H);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(0, MAP_H + 0.5);
        ctx.lineTo(MAP_W, MAP_H + 0.5);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(MAP_W + 0.5, 0);
        ctx.lineTo(MAP_W + 0.5, MAP_H);
        ctx.stroke();

        // v2.88.0 — labels render IN THE GUTTER (outside the map
        // bounds). Top labels at y = -stripH/2 (in the negative-y
        // gutter), left labels at x = -stripH/2 (in the negative-x
        // gutter), right labels at x = MAP_W + stripH/2, bottom
        // labels at y = MAP_H + stripH/2. Column-x and row-y still
        // align with the map's gridlines (c*gridSize + gridSize/2) so
        // each letter / number lines up with its cell column/row.
        //
        // The previous (v2.51.x) bounds-clipping skipped labels that
        // would land inside the PERPENDICULAR gutter — that doesn't
        // apply now (gutters live outside the map area), so all
        // labels render unconditionally.
        const topY = -Math.round(stripH / 2);
        const leftX = -Math.round(stripH / 2);
        const rightX = MAP_W + Math.round(stripH / 2);
        const bottomY = MAP_H + Math.round(stripH / 2);
        ctx.fillStyle = accent;
        // Top + bottom labels — column letters.
        for (let c = 0; c < cols; c++) {
            const x = Math.round(c * gridSize + gridSize / 2);
            ctx.fillText(_colLabel(c), x, topY);
            ctx.fillText(_colLabel(c), x, bottomY);
        }
        // Left + right labels — row numbers.
        for (let r = 0; r < rows; r++) {
            const y = Math.round(r * gridSize + gridSize / 2);
            ctx.fillText(String(r + 1), leftX, y);
            ctx.fillText(String(r + 1), rightX, y);
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

    // v2.64.0 — F2 fog-of-war: returns true when the current user
    // should NOT see this token. GMs always see everything; non-GM
    // users are hidden from when:
    //   - the legacy `is_hidden` boolean is set (hidden from all
    //     non-GM users), OR
    //   - their user_id appears in `hidden_from_user_ids` (the
    //     per-user list added in v2.64.0).
    // Used in render loops + hit-testing + GIF overlay to skip
    // tokens that the viewer shouldn't perceive.
    function _isTokenHiddenFromMe(t) {
        if (!t || (ME && ME.isGm)) return false;
        if (t.is_hidden) return true;
        const hf = t.hidden_from_user_ids;
        if (Array.isArray(hf) && ME && typeof ME.id === 'number' && hf.includes(ME.id)) {
            return true;
        }
        return false;
    }

    function _updateGifOverlay() {
        if (!_gifOverlay) return;
        const keep = new Set();
        tokens.forEach(t => {
            if (!ME.animateGifs || !t.image_url || !t.image_url.toLowerCase().includes('.gif')) return;
            if (_isTokenHiddenFromMe(t)) return;
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

    // v2.111.0 — transient instantaneous-AoE pulses (Fireball flash).
    // Each entry is the aoe_pulse broadcast data + a ``start`` ts; the
    // render loop fades them out and _tickAoePulses prunes expired ones.
    let _aoePulses = [];
    let _aoePulseRaf = null;
    function _tickAoePulses() {
        const now = (window.performance && performance.now)
            ? performance.now() : Date.now();
        _aoePulses = _aoePulses.filter(p => (now - p.start) < 2200);
        render();
        _aoePulseRaf = _aoePulses.length
            ? requestAnimationFrame(_tickAoePulses) : null;
    }
    function _addAoePulse(d) {
        if (!d || !d.shape) return;
        const now = (window.performance && performance.now)
            ? performance.now() : Date.now();
        _aoePulses.push(Object.assign({}, d, { start: now }));
        if (!_aoePulseRaf) _aoePulseRaf = requestAnimationFrame(_tickAoePulses);
    }

    // v2.112.0 — GM-only "Move AoE" controls. A movable concentration
    // AoE (Moonbeam / Web / Sleet Storm — anything not self-anchored)
    // gets a small floating button that re-opens the AoE picker; on
    // commit the new center is POSTed to /move_aoe, which re-broadcasts
    // the marker. Self-anchored shapes (Spirit Guardians) are omitted —
    // they track the caster's token automatically. v1 is GM-only; the
    // /move_aoe endpoint also permits the caster, so a player-facing
    // trigger is a clean follow-up. (Player self-move filed.)
    function _renderAoeMoveControls() {
        let host = document.getElementById('aoe-move-controls');
        const movable = (ME && ME.isGm)
            ? _concentrationAoes.filter(m => m && !m.is_self_anchored)
            : [];
        if (!movable.length) { if (host) host.remove(); return; }
        if (!host) {
            host = document.createElement('div');
            host.id = 'aoe-move-controls';
            host.setAttribute('style', [
                'position:fixed', 'left:12px', 'bottom:64px',
                'z-index:2147483000', 'display:flex',
                'flex-direction:column', 'gap:6px', 'max-width:220px',
            ].join(';'));
            document.body.appendChild(host);
        }
        host.innerHTML = '';
        for (const m of movable) {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = `↔ Move ${m.spell_name || 'AoE'}`;
            // Compact floating control (dense GM tool) — 32px min per the
            // CLAUDE.md compact-panel exception.
            b.setAttribute('style', [
                'min-height:32px', 'padding:4px 10px', 'border-radius:6px',
                'cursor:pointer', 'font-size:12px', 'font-weight:600',
                'border:1px solid #5eead4', 'background:rgba(94,234,212,0.15)',
                'color:#5eead4', 'text-align:left',
            ].join(';'));
            b.addEventListener('click', async () => {
                if (typeof window._openAoePicker !== 'function') return;
                const placed = await window._openAoePicker({
                    shape: m.shape, size_ft: m.size_ft,
                    secondary_ft: m.secondary_ft || 0,
                    name: m.spell_name || 'AoE',
                    char_id: m.caster_char_id || null,
                });
                if (!placed || !placed.center) return;  // cancelled
                try {
                    await fetch(`/api/campaign/${CAMPAIGN_ID}/move_aoe`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            marker_id: m.id,
                            center_x: placed.center.x,
                            center_y: placed.center.y,
                        }),
                    });
                } catch (_) { /* WS reconciles on the broadcast */ }
            });
            host.appendChild(b);
        }
    }

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
                if (_isTokenHiddenFromMe(t)) continue;
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
                if (_isTokenHiddenFromMe(t)) continue;
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
        if (_isTokenHiddenFromMe(t)) return;
        const cx = t.x + gridSize / 2;
        const cy = t.y + gridSize / 2;
        const r = (gridSize * t.size) / 2 - 4;
        ctx.save();
        // v2.64.0: GM dim-render for tokens hidden from anyone —
        // legacy `is_hidden` OR the new per-user `hidden_from_user_ids`
        // list. 40% alpha indicates "GM sees this; some players
        // don't." Other clients have already skipped this token via
        // _isTokenHiddenFromMe.
        if (t.is_hidden || (Array.isArray(t.hidden_from_user_ids) && t.hidden_from_user_ids.length > 0)) {
            ctx.globalAlpha = 0.4;
        }
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
            if (_isTokenHiddenFromMe(t)) return;
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
            if (t && !(_isTokenHiddenFromMe(t))) {
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
            if (_isTokenHiddenFromMe(t)) return;
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
                if (_isTokenHiddenFromMe(t)) continue;
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
                if (_isTokenHiddenFromMe(t)) continue;
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
                if (_isTokenHiddenFromMe(t)) continue;
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

        // v2.111.0 — instantaneous AoE pulse. A non-concentration AoE
        // (Fireball / Burning Hands / Shatter) flashes a warm shape
        // that expands slightly + fades over ~2.2 s so the table sees
        // where it landed. Shapes reuse the picker/marker geometry;
        // cone/line anchor at the caster's token (carried on the
        // pulse) toward the placement point. The fade is driven by
        // _tickAoePulses (rAF) which re-renders + prunes expired ones.
        if (_aoePulses.length) {
            const _PULSE_MS = 2200;
            const _pnow = (window.performance && performance.now)
                ? performance.now() : Date.now();
            for (const p of _aoePulses) {
                const frac = Math.max(0, Math.min(1, (_pnow - p.start) / _PULSE_MS));
                const lenPx = (p.size_ft / 5) * gridSize * (1 + 0.12 * frac);
                let ox = p.center_x, oy = p.center_y;
                if ((p.shape === 'cone' || p.shape === 'line') && p.caster_char_id) {
                    const t = tokens.find(t => t.character_id === p.caster_char_id);
                    if (t) { ox = t.x + gridSize / 2; oy = t.y + gridSize / 2; }
                }
                ctx.save();
                ctx.globalAlpha = 1 - frac;
                ctx.fillStyle = 'rgba(251,146,60,0.30)';   // warm flash
                ctx.strokeStyle = '#fb923c';
                ctx.lineWidth = 2;
                ctx.beginPath();
                if (p.shape === 'cube' || p.shape === 'self_cube') {
                    const half = lenPx / 2;
                    ctx.rect(p.center_x - half, p.center_y - half, lenPx, lenPx);
                } else if (p.shape === 'cone') {
                    const adx = p.center_x - ox, ady = p.center_y - oy;
                    const amag = Math.hypot(adx, ady) || 1;
                    const ax = adx / amag, ay = ady / amag, px = -ay, py = ax;
                    const tipX = ox + ax * lenPx, tipY = oy + ay * lenPx, halfW = lenPx / 2;
                    ctx.moveTo(ox, oy);
                    ctx.lineTo(tipX + px * halfW, tipY + py * halfW);
                    ctx.lineTo(tipX - px * halfW, tipY - py * halfW);
                    ctx.closePath();
                } else if (p.shape === 'line') {
                    const adx = p.center_x - ox, ady = p.center_y - oy;
                    const amag = Math.hypot(adx, ady) || 1;
                    const ax = adx / amag, ay = ady / amag, px = -ay, py = ax;
                    const halfW = ((p.secondary_ft || 5) / 5) * gridSize / 2;
                    const fx = ox + ax * lenPx, fy = oy + ay * lenPx;
                    ctx.moveTo(ox + px * halfW, oy + py * halfW);
                    ctx.lineTo(fx + px * halfW, fy + py * halfW);
                    ctx.lineTo(fx - px * halfW, fy - py * halfW);
                    ctx.lineTo(ox - px * halfW, oy - py * halfW);
                    ctx.closePath();
                } else {  // sphere / self_sphere / fallback
                    ctx.arc(p.center_x, p.center_y, lenPx, 0, Math.PI * 2);
                }
                ctx.fill();
                ctx.stroke();
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
                if (_isTokenHiddenFromMe(t)) return;
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

        // v2.710.0 — Phase 5 of vision-and-light: dynamic lighting overlay.
        // Drawn after tokens/markers (so darkness dims them) but before the
        // gutter labels (which must stay readable as UI chrome).
        drawLighting();

        // v2.50.0 — grid coordinate labels drawn LAST so the gutter
        // sits on top of every other rendered element. Tokens sliding
        // along the map edge will pass under the strip, which is
        // intentional — the labels need to stay visible to fulfill
        // their "establish a fixed naming system" role.
        if (showGrid) drawGridCoords();

        _updateGifOverlay();
    }

    // v2.710.0 — Phase 5 of vision-and-light: render the lighting model
    // (map ambient + token light sources + spell darkness/daylight/fog
    // emitters) as a composited overlay. Mirrors the server resolver's
    // `_illumination_at_point` precedence visually: an ambient dim/dark
    // veil punched through by bright/dim light radii (token sources +
    // Daylight), then magical-darkness + fog emitters painted on top.
    // Built on an offscreen canvas so the destination-out "punch" erases
    // only the veil, never the map/tokens beneath. Bright maps with no
    // emitters are a no-op (status quo). Presentation only — the server
    // is already authoritative for every sight verdict (Phases 1–4).
    let _lightCanvas = null;
    function drawLighting() {
        const dark = mapAmbientLight === 'dark';
        const dim = mapAmbientLight === 'dim';
        const darknessEm = lightEmitters.filter(e => e && e.kind === 'darkness');
        const fogEm = lightEmitters.filter(e => e && e.kind === 'fog');
        if (!dark && !dim && !darknessEm.length && !fogEm.length) return;
        const pxPerFt = gridSize / 5;   // 70px = 5ft grid → ft→px
        if (!_lightCanvas) _lightCanvas = document.createElement('canvas');
        if (_lightCanvas.width !== MAP_W) _lightCanvas.width = MAP_W;
        if (_lightCanvas.height !== MAP_H) _lightCanvas.height = MAP_H;
        const lc = _lightCanvas.getContext('2d');
        lc.clearRect(0, 0, MAP_W, MAP_H);
        // 1. Ambient veil.
        const veil = dark ? 0.8 : (dim ? 0.42 : 0);
        if (veil > 0) {
            lc.fillStyle = `rgba(3,6,18,${veil})`;
            lc.fillRect(0, 0, MAP_W, MAP_H);
        }
        // 2. Punch light holes (token sources + Daylight emitters): full clear
        //    out to the bright radius, fading to partial at the dim radius.
        lc.globalCompositeOperation = 'destination-out';
        function punch(cx, cy, brightFt, dimFt) {
            const outerPx = Math.max(brightFt, dimFt) * pxPerFt;
            if (outerPx <= 0) return;
            const innerPx = Math.min(brightFt * pxPerFt, outerPx);
            const g = lc.createRadialGradient(cx, cy, Math.max(1, innerPx), cx, cy, outerPx);
            g.addColorStop(0, 'rgba(0,0,0,1)');      // bright → fully clear
            g.addColorStop(1, 'rgba(0,0,0,0.35)');   // dim edge → partial
            lc.fillStyle = g;
            lc.beginPath();
            lc.arc(cx, cy, outerPx, 0, Math.PI * 2);
            lc.fill();
        }
        tokens.forEach(t => {
            if (_isTokenHiddenFromMe(t)) return;
            const b = Number(t.light_bright_ft || 0);
            const d = Number(t.light_dim_ft || 0);
            if (b <= 0 && d <= 0) return;
            punch(t.x + gridSize / 2, t.y + gridSize / 2, b, d);
        });
        lightEmitters.forEach(e => {
            if (!e || e.kind !== 'daylight') return;
            const r = Number(e.radius_ft || 0);
            punch(Number(e.x || 0), Number(e.y || 0), r, r);
        });
        // 3. Magical darkness + fog painted on top (override any light below).
        lc.globalCompositeOperation = 'source-over';
        darknessEm.forEach(e => {
            const r = Number(e.radius_ft || 0) * pxPerFt;
            if (r <= 0) return;
            lc.fillStyle = 'rgba(1,2,9,0.92)';
            lc.beginPath();
            lc.arc(Number(e.x || 0), Number(e.y || 0), r, 0, Math.PI * 2);
            lc.fill();
        });
        fogEm.forEach(e => {
            const r = Number(e.radius_ft || 0) * pxPerFt;
            if (r <= 0) return;
            lc.fillStyle = 'rgba(201,206,216,0.72)';
            lc.beginPath();
            lc.arc(Number(e.x || 0), Number(e.y || 0), r, 0, Math.PI * 2);
            lc.fill();
        });
        ctx.drawImage(_lightCanvas, 0, 0);
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
        /* v2.99.98 — honor speed-reduction effects in the red/green
         * threshold. v2.99.446 — Phase 6.1: prefer the breadcrumb's
         * precomputed `effective_speed_walk` ((base + Σ bonus) × mult −
         * Σ reduction) so Haste / Longstrider raise the cap too; fall
         * back to the old base − reduction math for a stale bc. */
        const _effWalk = (typeof bc.effective_speed_walk === 'number')
            ? bc.effective_speed_walk
            : Math.max(
                0,
                (Number(bc.speed_walk) || 30)
                    - (Number(bc.speed_reduction_ft) || 0),
            );
        const speedCap = Math.max(0, _effWalk + (Number(bc.dash_bonus_ft) || 0));
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

    // v2.88.0 — pan/zoom transform now targets the single
    // #map-transform wrapper instead of bg-layer / canvas /
    // gif-overlay individually. The wrapper's children (with their
    // various top/left positions, including canvas at -stripH/-stripH)
    // scale uniformly because the wrapper provides one shared
    // transform context. Before this, each child had the same
    // transform applied separately but CSS scale with
    // transform-origin: 0 0 doesn't account for the child's box
    // top/left, so different top/left values diverged at scale ≠ 1.
    // v2.714.0 — supersample-on-zoom driver. Zooming changes `scale`, which
    // changes the target backing-store resolution. Re-rastering on every
    // wheel notch / pinch frame would be janky, so the CSS transform handles
    // the live (bitmap-scaled) zoom and this debounced pass re-rasters ONCE
    // after the zoom settles — only when the target moves >5% from the
    // current renderScale, so panning (same scale) never triggers a re-raster.
    let _renderScaleTimer = null;
    function scheduleRenderScaleUpdate() {
        clearTimeout(_renderScaleTimer);
        _renderScaleTimer = setTimeout(() => {
            const target = fittedRenderScale(DPR * Math.max(1, scale));
            if (Math.abs(target - renderScale) / renderScale > 0.05) {
                applyRenderScale(target);
                try { render(); } catch (_) {}
            }
        }, 180);
    }

    const mapTransform = document.getElementById('map-transform');
    function applyTransform() {
        clampPan();
        const t = `translate(${panX}px, ${panY}px) scale(${scale})`;
        if (mapTransform) {
            mapTransform.style.transform = t;
        } else {
            // Fallback path for legacy pages / tests that may not have
            // the wrapper element — preserves the pre-v2.88.0 behaviour
            // of applying the transform per-child. Harmless on pages
            // that DO have the wrapper because mapTransform is checked
            // first.
            canvas.style.transform = t;
            if (bgLayer) { bgLayer.style.transform = t; }
            if (_gifOverlay) {
                _gifOverlay.style.transform = t;
                _gifOverlay.style.transformOrigin = '0 0';
            }
        }
        scheduleSaveView();
        scheduleRenderScaleUpdate();
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
        // Base ownership gate — must be the dragger's PC or a token
        // they're an explicit controller of.
        const ownsByController = (
            t.controller_user_id != null && t.controller_user_id === ME.id
        );
        let ownsByChar = false;
        if (!ownsByController) {
            if (!t.character_id) return false;
            const c = characters.find(c => c.id === t.character_id);
            ownsByChar = !!(c && c.owner_user_id === ME.id);
            if (!ownsByChar) return false;
        }
        // v2.99.79 — initiative-turn gate. When a battle is ACTIVE
        // (init started), non-GMs may only drag the token of the
        // CURRENT active combatant. Off-turn drags are rejected at
        // the canvas layer so players can't reposition their PC
        // (or any token they own) while it's not their turn. GM
        // already bypassed up top. Battle inactive → fall through
        // to the legacy ownership-only gate so out-of-combat
        // exploration / shuffling still works freely.
        const b = window.battle;
        if (b && b.active && Array.isArray(b.combatants)
                && b.combatants.length
                && Number.isFinite(b.turn_index)) {
            const active = b.combatants[b.turn_index % b.combatants.length];
            if (active) {
                const activeMatchesThisToken = (
                    (active.source_token_id != null
                     && active.source_token_id === t.id)
                    || (active.char_id != null
                        && active.char_id === t.character_id)
                );
                if (!activeMatchesThisToken) return false;
            }
        }
        return true;
    }

    function clientToCanvas(ev) {
        // v2.88.0 — canvas is now expanded by stripH on every side and
        // positioned at top:-stripH;left:-stripH inside the wrapper, so
        // ``rect`` corresponds to the OUTER (expanded) canvas. Logical
        // (0, 0) in map coords is at canvas-local (stripH, stripH) due
        // to ctx.translate(stripH, stripH). Subtract stripH after the
        // scale divide to get map coords. Pre-v2.88.0 stripH was 0,
        // so this is a no-op for legacy paths.
        const rect = canvas.getBoundingClientRect();
        return [
            (ev.clientX - rect.left) / scale - stripH,
            (ev.clientY - rect.top) / scale - stripH,
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
        // v2.88.0 — same stripH subtraction as clientToCanvas.
        return {
            x: (screenCx - canvasRect.left) / scale - stripH,
            y: (screenCy - canvasRect.top) / scale - stripH,
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
        // v2.583.0: left-drag on empty map area pans the map. The loop
        // above returns early when the click lands on a movable token
        // (token drag), so falling through here means empty space —
        // start a pan. This is the reliable cross-device pan gesture:
        // right-button drag (the ``ev.button === 2`` path above) is
        // intercepted by the native context menu on macOS Safari and on
        // some trackpads, which swallows the follow-up mousemove/mouseup
        // and leaves the map "stuck" (zoom still works because the wheel
        // listener is a separate path). Left-drag works everywhere and
        // doesn't depend on the fragile right-click/contextmenu coupling.
        // Only the left button starts a pan here; other buttons fall
        // through untouched.
        if (ev.button === 0) {
            panning = { startX: ev.clientX - panX, startY: ev.clientY - panY };
            canvas.style.cursor = 'move';
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
        // v2.583.0: clear an active pan regardless of which button
        // started it (left-drag-on-empty or right-drag). Must come
        // before the token-drop logic so a pan release never falls into
        // the drag-commit path.
        if (panning) {
            panning = null;
            canvas.style.cursor = 'grab';
            return;
        }
        if (ev.button === 2) return;
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

    /* v2.99.69 — pre-move Dash modal. Shown BEFORE the v2.99.55 OA
     * modal when the planned move both PROVOKES an OA and exceeds the
     * combatant's remaining movement (the v2.100.1 gate is
     * `_projectedOverrun && !action`). Dash extends movement but
     * doesn't prevent the OA (RAW: Disengage prevents OA — not
     * surfaced yet; filed for follow-up). Buttons (v2.100.2): Take
     * Dash / Cancel move only — there is no "Skip Dash" path because
     * the move is over-cap and can't be made without Dashing, so
     * declining == Cancel == no move == no OA. Take Dash chains to the
     * OA modal automatically; Cancel snaps the token back. */
    function _showPreMoveDashModal({
        tokenLabel, triggers, distanceFt, onChoice, onCancel,
    }) {
        const backdrop = document.createElement('div');
        backdrop.setAttribute('style', [
            'position:fixed', 'inset:0',
            'background:rgba(0,0,0,0.45)',
            'z-index:2147483600',
            'display:flex', 'align-items:center', 'justify-content:center',
            'padding:16px',
            'animation:reactionPopIn 180ms ease-out',
        ].join(';'));
        backdrop.setAttribute('role', 'dialog');
        backdrop.setAttribute('aria-label', 'Dash before opportunity attack');

        const card = document.createElement('div');
        card.setAttribute('style', [
            'background:#1f2433',
            'background:color-mix(in srgb, var(--bg, #1f2433) 88%, transparent)',
            'backdrop-filter:blur(8px)',
            '-webkit-backdrop-filter:blur(8px)',
            'border:1px solid var(--border, rgba(255,255,255,0.18))',
            'border-left:4px solid #66bb6a',
            'border-radius:10px',
            'padding:18px 20px',
            'color:var(--fg, #fff)',
            'font-size:13px',
            'max-width:440px', 'width:100%',
            'box-shadow:0 10px 36px rgba(0,0,0,0.55), 0 0 0 1px rgba(102,187,106,0.18)',
        ].join(';'));

        const header = document.createElement('div');
        header.style.cssText = 'font-size:14px; font-weight:600; margin-bottom:6px;';
        header.textContent = '🏃 Take the Dash action?';
        card.appendChild(header);

        const summary = document.createElement('p');
        summary.style.cssText = 'margin:0 0 10px 0; font-size:12px; opacity:0.85; line-height:1.4;';
        const distTxt = distanceFt > 0 ? ' (~' + distanceFt + ' ft)' : '';
        const provokers = (triggers || [])
            .map(t => escapeHTML(t.watcher_name || 'a hostile'))  // v2.599.5 — escape: injected via innerHTML below
            .filter((v, i, a) => a.indexOf(v) === i)
            .join(', ');
        // v2.100.2 — this modal only appears when the move is BEYOND
        // the combatant's remaining movement (the Dash gate is
        // `_projectedOverrun && !action`). So the move literally can't
        // be made without Dashing — copy + buttons reflect that: Take
        // Dash to extend movement and make the move (the OA fires), or
        // Cancel (no move, no OA). There is no "skip Dash but move
        // anyway" path because there isn't the movement for it.
        summary.innerHTML = (
            'This move' + distTxt + ' is farther than the combatant can '
            + 'travel without Dashing, and it will provoke an Opportunity '
            + 'Attack from <strong>' + (provokers || 'a hostile') + '</strong>. '
            + 'Take Dash to extend your movement and make the move — the OA '
            + 'will fire. Otherwise cancel.'
        );
        card.appendChild(summary);

        const btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex; gap:8px; justify-content:flex-end; margin-top:6px; flex-wrap:wrap;';

        function _btn(label, style, onClick) {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            b.setAttribute('style', [
                'min-height:44px', 'padding:6px 14px',
                'border-radius:6px', 'cursor:pointer', 'font-size:13px',
                'border:1px solid var(--border, rgba(255,255,255,0.22))',
            ].join(';') + ';' + style);
            b.addEventListener('click', (ev) => {
                ev.preventDefault();
                document.removeEventListener('keydown', _onKey);
                backdrop.remove();
                onClick();
            });
            return b;
        }
        btnRow.appendChild(_btn(
            '✋ Cancel move',
            'background:rgba(255,255,255,0.04); color:var(--fg);',
            onCancel,
        ));
        // v2.100.2 — removed the "Skip Dash" button. It used to route
        // to the OA Continue/Stop modal and then commit an over-cap
        // move WITHOUT the Dash that made it legal — so declining Dash
        // still surfaced an OA prompt for a move the combatant had no
        // movement to make. Now the only way forward is Take Dash;
        // not Dashing == Cancel == no move == no OA.
        btnRow.appendChild(_btn(
            '🏃 Take Dash',
            'background:#66bb6a; color:#1f2433; font-weight:600; border-color:#43a047;',
            () => onChoice(true),
        ));
        card.appendChild(btnRow);

        backdrop.addEventListener('click', (ev) => {
            if (ev.target === backdrop) {
                document.removeEventListener('keydown', _onKey);
                backdrop.remove();
                onCancel();
            }
        });
        function _onKey(ev) {
            if (ev.key === 'Escape') {
                ev.preventDefault();
                document.removeEventListener('keydown', _onKey);
                backdrop.remove();
                onCancel();
            }
        }
        document.addEventListener('keydown', _onKey);

        backdrop.appendChild(card);
        document.body.appendChild(backdrop);
    }

    /* v2.99.55 — plan-movement-oa-flow Phase 4 pre-move modal. Built
     * inline rather than via the showMovementOverrunModal helper
     * because the trigger semantics are different (movement-overrun
     * is per-active-combatant + speed-cap-aware; OA is geometry-only
     * + per-watcher). Glass-card styling matches v2.99.49's
     * reaction-prompt popup so the table sees a consistent visual
     * language for "your action provoked something." z-index above
     * the canvas + the GM panels (2147483600 matches reaction
     * popup).
     */
    function _showPreMoveOaModal({
        tokenLabel, triggers, distanceFt, onContinue, onStop,
    }) {
        // Backdrop blocks canvas interaction while the modal is open.
        const backdrop = document.createElement('div');
        backdrop.setAttribute('style', [
            'position:fixed', 'inset:0',
            'background:rgba(0,0,0,0.45)',
            'z-index:2147483600',
            'display:flex', 'align-items:center', 'justify-content:center',
            'padding:16px',
            'animation:reactionPopIn 180ms ease-out',
        ].join(';'));
        backdrop.setAttribute('role', 'dialog');
        backdrop.setAttribute('aria-label', 'Opportunity attack provoked');

        const card = document.createElement('div');
        card.setAttribute('style', [
            'background:#1f2433',
            'background:color-mix(in srgb, var(--bg, #1f2433) 88%, transparent)',
            'backdrop-filter:blur(8px)',
            '-webkit-backdrop-filter:blur(8px)',
            'border:1px solid var(--border, rgba(255,255,255,0.18))',
            'border-left:4px solid #ffb74d',
            'border-radius:10px',
            'padding:18px 20px',
            'color:var(--fg, #fff)',
            'font-size:13px',
            'max-width:420px', 'width:100%',
            'box-shadow:0 10px 36px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,183,77,0.18)',
        ].join(';'));

        // Header.
        const header = document.createElement('div');
        header.style.cssText = 'font-size:14px; font-weight:600; margin-bottom:6px;';
        header.textContent = '⚠ Opportunity Attack provoked';
        card.appendChild(header);

        // Summary line.
        const summary = document.createElement('p');
        summary.style.cssText = 'margin:0 0 10px 0; font-size:12px; opacity:0.85; line-height:1.4;';
        const distTxt = distanceFt > 0 ? ' (~' + distanceFt + ' ft)' : '';
        summary.textContent = (
            'Continuing this move' + distTxt + ' will provoke an '
            + 'Opportunity Attack from:'
        );
        card.appendChild(summary);

        // Trigger list.
        const list = document.createElement('ul');
        list.style.cssText = 'margin:0 0 14px 0; padding-left:18px; font-size:12px;';
        (triggers || []).forEach(t => {
            const li = document.createElement('li');
            const reach = Number(t.watcher_reach_ft) || 5;
            const reachTxt = (reach % 1 === 0) ? reach.toFixed(0) : reach.toFixed(1);
            const kind = (t.trigger_type === 'enter')
                ? 'enters ' + reachTxt + ' ft polearm reach'
                : 'exits ' + reachTxt + ' ft reach';
            li.textContent = (t.watcher_name || 'Watcher') + ' — ' + kind;
            li.style.marginBottom = '3px';
            list.appendChild(li);
        });
        card.appendChild(list);

        // Buttons. Stop = primary (red-tinted) since the safer
        // default is to NOT walk into a swing. Continue = secondary.
        const btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex; gap:8px; justify-content:flex-end; margin-top:6px;';

        function _btn(label, style, onClick) {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            b.setAttribute('style', [
                'min-height:44px', 'padding:6px 14px',
                'border-radius:6px', 'cursor:pointer', 'font-size:13px',
                'border:1px solid var(--border, rgba(255,255,255,0.22))',
            ].join(';') + ';' + style);
            b.addEventListener('click', (ev) => {
                ev.preventDefault();
                backdrop.remove();
                onClick();
            });
            return b;
        }
        btnRow.appendChild(_btn(
            '✋ Stop — don\'t provoke',
            'background:rgba(255,255,255,0.04); color:var(--fg);',
            onStop,
        ));
        btnRow.appendChild(_btn(
            '⚔ Continue anyway',
            'background:#ffb74d; color:#1f2433; font-weight:600; border-color:#e09a2a;',
            onContinue,
        ));
        card.appendChild(btnRow);

        // Click outside the card → treat as Stop (safer default).
        backdrop.addEventListener('click', (ev) => {
            if (ev.target === backdrop) {
                backdrop.remove();
                onStop();
            }
        });
        // Escape key → Stop too.
        function _onKey(ev) {
            if (ev.key === 'Escape') {
                ev.preventDefault();
                document.removeEventListener('keydown', _onKey);
                backdrop.remove();
                onStop();
            }
        }
        document.addEventListener('keydown', _onKey);

        backdrop.appendChild(card);
        document.body.appendChild(backdrop);
    }

    /* v2.100.0 — GM over-range advisory modal. Mirrors the OA
     * pre-move modal shape (glass card, amber accent) but warns the
     * GM that a single drag moves a token further than its base
     * walking speed. Advisory only: "Move anyway" commits, "Cancel"
     * snaps the token back. Shown only to the GM, only during an
     * active battle, and only for tokens that are NOT the active
     * combatant (the active combatant's per-turn movement budget is
     * handled by showMovementOverrunModal, which respects Dash +
     * cumulative economy.movement). This fills the off-turn /
     * NPC-side reposition gap where no movement prompt fired. */
    /* v2.102.0 — movement-lock modal. Two variants:
     *   • GM (isGm:true) — advisory "movement is locked — move
     *     anyway?" with Cancel / Move anyway. The GM is the arbiter;
     *     the server lets their drag through, so onMove continues the
     *     normal move flow and onCancel snaps the token back.
     *   • Player (isGm:false) — informational "movement is locked"
     *     notice with a single Dismiss button (the token is already
     *     snapped back by the caller). Phase 3 adds a "Request to
     *     move" action here.
     * Mirrors the _showGmOverRangeModal glass-card recipe so the two
     * movement prompts read as a family. */
    function _showMovementLockedModal({
        isGm, tokenId, tokenLabel, onMove, onCancel,
    }) {
        const backdrop = document.createElement('div');
        backdrop.setAttribute('style', [
            'position:fixed', 'inset:0',
            'background:rgba(0,0,0,0.45)',
            'z-index:2147483600',
            'display:flex', 'align-items:center', 'justify-content:center',
            'padding:16px',
            'animation:reactionPopIn 180ms ease-out',
        ].join(';'));
        backdrop.setAttribute('role', 'dialog');
        backdrop.setAttribute('aria-label', 'Movement is locked');

        const card = document.createElement('div');
        card.setAttribute('style', [
            'background:#1f2433',
            'background:color-mix(in srgb, var(--bg, #1f2433) 88%, transparent)',
            'backdrop-filter:blur(8px)',
            '-webkit-backdrop-filter:blur(8px)',
            'border:1px solid var(--border, rgba(255,255,255,0.18))',
            'border-left:4px solid #ff8a80',
            'border-radius:10px',
            'padding:18px 20px',
            'color:var(--fg, #fff)',
            'font-size:13px',
            'max-width:420px', 'width:100%',
            'box-shadow:0 10px 36px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,138,128,0.18)',
        ].join(';'));

        const header = document.createElement('div');
        header.style.cssText = 'font-size:14px; font-weight:600; margin-bottom:6px;';
        header.textContent = '🔒 Movement locked';
        card.appendChild(header);

        const summary = document.createElement('p');
        summary.style.cssText = 'margin:0 0 14px 0; font-size:12px; opacity:0.85; line-height:1.4;';
        summary.textContent = isGm
            ? ((tokenLabel || 'This token') + ' — movement is locked for '
               + 'players. Move it anyway? (You’re the GM; players '
               + 'are still blocked.)')
            : ('The GM has locked token movement. You can’t move '
               + (tokenLabel || 'your token') + ' right now — ask the GM '
               + 'to unlock movement.');
        card.appendChild(summary);

        const btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex; gap:8px; justify-content:flex-end; margin-top:6px;';

        function _btn(label, style, onClick) {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            b.setAttribute('style', [
                'min-height:44px', 'padding:6px 14px',
                'border-radius:6px', 'cursor:pointer', 'font-size:13px',
                'border:1px solid var(--border, rgba(255,255,255,0.22))',
            ].join(';') + ';' + style);
            b.addEventListener('click', (ev) => {
                ev.preventDefault();
                backdrop.remove();
                if (onClick) onClick();
            });
            return b;
        }

        let _closeAction;  // run on backdrop-click / Escape
        if (isGm) {
            btnRow.appendChild(_btn(
                '✋ Cancel',
                'background:rgba(255,255,255,0.04); color:var(--fg);',
                onCancel,
            ));
            btnRow.appendChild(_btn(
                '➡ Move anyway',
                'background:#ff8a80; color:#1f2433; font-weight:600; border-color:#e0625a;',
                onMove,
            ));
            _closeAction = onCancel;
        } else {
            btnRow.appendChild(_btn(
                'Dismiss',
                'background:rgba(255,255,255,0.04); color:var(--fg);',
                null,
            ));
            // v2.104.0 — ask the GM to unlock this one token.
            btnRow.appendChild(_btn(
                '🙋 Request to move',
                'background:#6cb4ff; color:#1f2433; font-weight:600; border-color:#3f8fdc;',
                () => _requestMovement(tokenId, tokenLabel),
            ));
            _closeAction = null;
        }
        card.appendChild(btnRow);

        backdrop.addEventListener('click', (ev) => {
            if (ev.target === backdrop) {
                backdrop.remove();
                if (_closeAction) _closeAction();
            }
        });
        function _onKey(ev) {
            if (ev.key === 'Escape') {
                ev.preventDefault();
                document.removeEventListener('keydown', _onKey);
                backdrop.remove();
                if (_closeAction) _closeAction();
            }
        }
        document.addEventListener('keydown', _onKey);

        backdrop.appendChild(card);
        document.body.appendChild(backdrop);
    }

    /* v2.104.0 — player asks the GM to unlock one token. POSTs the
     * movement request; the GM gets a movement_request popup. On
     * approve the requester gets movement_request_resolved (handled
     * below) which adds the token to window._MOVEMENT_GRANTS so the
     * next drag passes the lock gate. */
    async function _requestMovement(tokenId, tokenLabel) {
        if (tokenId == null) return;
        try {
            const r = await fetch(
                `/api/campaign/${CAMPAIGN_ID}/movement_request`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token_id: tokenId }),
                },
            );
            if (r.ok) {
                showToast('🙋 Movement request sent to the GM.', 'info');
            } else {
                showToast('Could not send movement request.', 'error');
            }
        } catch (_) {
            showToast('Could not send movement request.', 'error');
        }
    }

    /* v2.104.0 — GM-side approve/deny popup for a player's movement
     * request. Only GMs receive the movement_request broadcast, so
     * this is shown whenever the handler fires. Approve issues the
     * one-shot server grant; Deny just resolves the request. */
    function _showMovementRequestModal(data) {
        const backdrop = document.createElement('div');
        backdrop.setAttribute('style', [
            'position:fixed', 'inset:0',
            'background:rgba(0,0,0,0.45)',
            'z-index:2147483600',
            'display:flex', 'align-items:center', 'justify-content:center',
            'padding:16px',
            'animation:reactionPopIn 180ms ease-out',
        ].join(';'));
        backdrop.setAttribute('role', 'dialog');
        backdrop.setAttribute('aria-label', 'Movement request');

        const card = document.createElement('div');
        card.setAttribute('style', [
            'background:#1f2433',
            'background:color-mix(in srgb, var(--bg, #1f2433) 88%, transparent)',
            'backdrop-filter:blur(8px)', '-webkit-backdrop-filter:blur(8px)',
            'border:1px solid var(--border, rgba(255,255,255,0.18))',
            'border-left:4px solid #6cb4ff',
            'border-radius:10px', 'padding:18px 20px',
            'color:var(--fg, #fff)', 'font-size:13px',
            'max-width:420px', 'width:100%',
            'box-shadow:0 10px 36px rgba(0,0,0,0.55), 0 0 0 1px rgba(108,180,255,0.18)',
        ].join(';'));

        const header = document.createElement('div');
        header.style.cssText = 'font-size:14px; font-weight:600; margin-bottom:6px;';
        header.textContent = '🙋 Movement request';
        card.appendChild(header);

        const summary = document.createElement('p');
        summary.style.cssText = 'margin:0 0 14px 0; font-size:12px; opacity:0.85; line-height:1.4;';
        summary.textContent = (
            (data.requester_name || 'A player') + ' wants to move '
            + (data.token_label || 'their token')
            + ' while movement is locked. Allow this one move?'
        );
        card.appendChild(summary);

        const btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex; gap:8px; justify-content:flex-end; margin-top:6px;';
        let _resolved = false;
        const _respond = async (approved) => {
            if (_resolved) return;
            _resolved = true;
            backdrop.remove();
            try {
                await fetch(
                    `/api/campaign/${CAMPAIGN_ID}/movement_request/`
                    + `${data.request_id}/respond`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ approved }),
                    },
                );
            } catch (_) { /* the resolved broadcast won't fire; benign */ }
        };
        function _btn(label, style, onClick) {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            b.setAttribute('style', [
                'min-height:44px', 'padding:6px 14px', 'border-radius:6px',
                'cursor:pointer', 'font-size:13px',
                'border:1px solid var(--border, rgba(255,255,255,0.22))',
            ].join(';') + ';' + style);
            b.addEventListener('click', (ev) => { ev.preventDefault(); onClick(); });
            return b;
        }
        btnRow.appendChild(_btn(
            '✋ Deny',
            'background:rgba(255,255,255,0.04); color:var(--fg);',
            () => _respond(false),
        ));
        btnRow.appendChild(_btn(
            '✓ Allow move',
            'background:#6cb4ff; color:#1f2433; font-weight:600; border-color:#3f8fdc;',
            () => _respond(true),
        ));
        card.appendChild(btnRow);

        // A resolved broadcast (e.g. another GM tab answered) dismisses
        // this popup; tracked by request_id so the handler can find it.
        backdrop.dataset.movementRequestId = data.request_id;
        backdrop.addEventListener('click', (ev) => {
            if (ev.target === backdrop) { _resolved = true; backdrop.remove(); }
        });
        backdrop.appendChild(card);
        document.body.appendChild(backdrop);
    }

    function _showGmOverRangeModal({
        tokenLabel, distanceFt, speedFt, onMove, onCancel,
    }) {
        const backdrop = document.createElement('div');
        backdrop.setAttribute('style', [
            'position:fixed', 'inset:0',
            'background:rgba(0,0,0,0.45)',
            'z-index:2147483600',
            'display:flex', 'align-items:center', 'justify-content:center',
            'padding:16px',
            'animation:reactionPopIn 180ms ease-out',
        ].join(';'));
        backdrop.setAttribute('role', 'dialog');
        backdrop.setAttribute('aria-label', 'Token moved past its speed');

        const card = document.createElement('div');
        card.setAttribute('style', [
            'background:#1f2433',
            'background:color-mix(in srgb, var(--bg, #1f2433) 88%, transparent)',
            'backdrop-filter:blur(8px)',
            '-webkit-backdrop-filter:blur(8px)',
            'border:1px solid var(--border, rgba(255,255,255,0.18))',
            'border-left:4px solid #ffb74d',
            'border-radius:10px',
            'padding:18px 20px',
            'color:var(--fg, #fff)',
            'font-size:13px',
            'max-width:420px', 'width:100%',
            'box-shadow:0 10px 36px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,183,77,0.18)',
        ].join(';'));

        const header = document.createElement('div');
        header.style.cssText = 'font-size:14px; font-weight:600; margin-bottom:6px;';
        header.textContent = '⚠ Moving past speed';
        card.appendChild(header);

        const summary = document.createElement('p');
        summary.style.cssText = 'margin:0 0 14px 0; font-size:12px; opacity:0.85; line-height:1.4;';
        const _dist = (distanceFt > 0)
            ? ((distanceFt % 1 === 0) ? distanceFt.toFixed(0) : distanceFt.toFixed(1))
            : '?';
        const _speed = (speedFt > 0)
            ? ((speedFt % 1 === 0) ? speedFt.toFixed(0) : speedFt.toFixed(1))
            : '?';
        summary.textContent = (
            (tokenLabel || 'This token') + ' would move ~' + _dist
            + ' ft in one step — more than its ' + _speed
            + ' ft speed. Move it anyway?'
        );
        card.appendChild(summary);

        const btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex; gap:8px; justify-content:flex-end; margin-top:6px;';

        function _btn(label, style, onClick) {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            b.setAttribute('style', [
                'min-height:44px', 'padding:6px 14px',
                'border-radius:6px', 'cursor:pointer', 'font-size:13px',
                'border:1px solid var(--border, rgba(255,255,255,0.22))',
            ].join(';') + ';' + style);
            b.addEventListener('click', (ev) => {
                ev.preventDefault();
                backdrop.remove();
                onClick();
            });
            return b;
        }
        // Cancel = safer default (don't over-extend); Move anyway =
        // the deliberate GM override.
        btnRow.appendChild(_btn(
            '✋ Cancel',
            'background:rgba(255,255,255,0.04); color:var(--fg);',
            onCancel,
        ));
        btnRow.appendChild(_btn(
            '➡ Move anyway',
            'background:#ffb74d; color:#1f2433; font-weight:600; border-color:#e09a2a;',
            onMove,
        ));
        card.appendChild(btnRow);

        // Click outside / Escape → Cancel (snap back).
        backdrop.addEventListener('click', (ev) => {
            if (ev.target === backdrop) {
                backdrop.remove();
                onCancel();
            }
        });
        function _onKey(ev) {
            if (ev.key === 'Escape') {
                ev.preventDefault();
                document.removeEventListener('keydown', _onKey);
                backdrop.remove();
                onCancel();
            }
        }
        document.addEventListener('keydown', _onKey);

        backdrop.appendChild(card);
        document.body.appendChild(backdrop);
    }

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
     *
     * v2.99.55: a Phase 4 pre-move OA gate runs BEFORE the
     * movement-overrun gate. If the move would provoke any OAs the
     * dragger sees a Continue/Stop modal first; OA-clear moves fall
     * through to the existing gate logic.
     */
    // v2.102.0 — movement-lock gate. Runs BEFORE the OA / over-speed
    // pre-move flow. When the GM has locked movement
    // (window._MOVEMENT_LOCKED, kept fresh by the movement_lock_update
    // WS handler):
    //   • Player → snap the token back + show the "movement is locked"
    //     notice. The server also 409s movement_locked as the backstop,
    //     but gating client-side avoids the visual flicker of an
    //     optimistic move that gets rejected.
    //   • GM → show an advisory "movement is locked — move anyway?"
    //     confirm; the GM is the arbiter and the server lets them
    //     through. On confirm, fall through to the normal move flow.
    // Unlocked → straight through to _commitTokenMoveInner.
    async function _commitTokenMove(token, origX, origY, sx, sy) {
        if (window._MOVEMENT_LOCKED) {
            // v2.104.0 — one-shot grant: a GM-approved movement request
            // lets the player move THIS token once while the table
            // stays locked. Consume the client grant + fall through;
            // the server consumes its matching grant in the move gate.
            if (window._MOVEMENT_GRANTS && window._MOVEMENT_GRANTS.has(token.id)) {
                window._MOVEMENT_GRANTS.delete(token.id);
                return _commitTokenMoveInner(token, origX, origY, sx, sy);
            }
            const snapBack = () => {
                token.x = origX; token.y = origY; render();
            };
            if (ME && ME.isGm) {
                _showMovementLockedModal({
                    isGm: true,
                    tokenLabel: token.label || 'Token',
                    onMove: () => _commitTokenMoveInner(
                        token, origX, origY, sx, sy,
                    ),
                    onCancel: snapBack,
                });
            } else {
                // Player: undo the optimistic drag, explain, and offer
                // to request movement from the GM (Phase 3).
                snapBack();
                _showMovementLockedModal({
                    isGm: false,
                    tokenId: token.id,
                    tokenLabel: token.label || 'Token',
                });
            }
            return;
        }
        return _commitTokenMoveInner(token, origX, origY, sx, sy);
    }

    async function _commitTokenMoveInner(token, origX, origY, sx, sy) {
        const tokenId = token.id;
        // v2.99.55 — plan-movement-oa-flow Phase 4. postMove now
        // accepts an opt-in oa_confirmed flag; the pre-flight preview
        // gate below sets it to true after the user clicks Continue.
        // No flag = first try; if the server returns 409 the snapback
        // fires + the legacy advisory still surfaces on the chat-log.
        const postMove = (oaConfirmed = false, overSpeedConfirmed = false) => {
            const body = { x: sx, y: sy };
            if (oaConfirmed) body.oa_confirmed = true;
            /* v2.99.99 — Dash-modal accept path passes
             * over_speed_confirmed:true so the v2.99.99 server 409
             * gate is bypassed cleanly. The user already saw the
             * client modal and chose to proceed; the gate exists
             * to catch scripted clients, not to double-prompt. */
            if (overSpeedConfirmed) body.over_speed_confirmed = true;
            return fetch(`/api/campaign/${CAMPAIGN_ID}/token/${tokenId}/move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
        };
        const snapBack = () => {
            token.x = origX;
            token.y = origY;
            render();
        };

        // v2.99.55 — plan-movement-oa-flow Phase 4 pre-move OA gate.
        // Before anything else, ask the server "would this move
        // trigger an OA?" via the v2.99.54 preview endpoint. If it
        // would, open the Continue/Stop modal; if not, fall through
        // to the existing movement-overrun gate / direct post.
        //
        // The preview is best-effort: if the network call fails or
        // the server is unreachable, we fall through to the existing
        // flow. The server's 409 oa_confirmation_required is the
        // defense-in-depth backstop — if the client somehow skipped
        // the preview AND the move triggers OAs, the actual
        // /token/move POST will 409 below.
        let _oaTriggers = [];
        let _previewDistanceFt = 0;
        // v2.100.0 — over-range advisory fields from the same preview.
        let _overRange = false;
        let _tokenSpeedFt = 0;
        try {
            const previewResp = await fetch(
                `/api/campaign/${CAMPAIGN_ID}/token/${tokenId}/preview_move`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ x: sx, y: sy }),
                },
            );
            if (previewResp.ok) {
                const data = await previewResp.json();
                if (data && data.would_trigger_oa) {
                    _oaTriggers = Array.isArray(data.triggers)
                        ? data.triggers : [];
                }
                // v2.100.0 — distance is now read unconditionally (the
                // OA branch used to be the only reader) so the GM
                // over-range modal can report it even on non-OA moves.
                _previewDistanceFt = Number(data && data.distance_ft) || 0;
                _overRange = !!(data && data.over_range);
                _tokenSpeedFt = Number(data && data.token_speed_ft) || 0;
            }
        } catch (_) {
            // Preview failed — fall through. The 409 gate on /move
            // is the safety net.
        }
        // v2.99.72 — compute active-combatant + Dash-need ONCE up
        // front so both the OA branch and the overrun branch read
        // the same numbers. Previously the OA branch fired the Dash
        // modal unconditionally (bug #1 in the user's v2.99.72
        // report) and the overrun branch GM-bypassed (bug #2). Both
        // are fixed by gating the Dash prompt on actual need
        // (projected > effectiveCap AND action available) and by
        // letting the overrun modal fire for GMs too as long as
        // the dragged token IS the active combatant.
        let _activeForDash = null;
        let _projectedDistance = _previewDistanceFt;
        let _projectedOverrun = false;
        let _needsDash = false;
        // v2.100.0 — the active combatant regardless of whether it
        // matches the dragged token. Truthy iff a battle is live; the
        // GM over-range advisory only fires during combat.
        let _anyActive = null;
        if (typeof window._getActiveCombatant === 'function') {
            const _active = window._getActiveCombatant();
            if (_active) {
                _anyActive = _active;
                // Match the active combatant to the dragged token across
                // the SAME three tiers the canonical token↔combatant lookup
                // uses (see ~:957). NPC combatants carry neither a stable
                // source_token_id (it goes stale after an encounter
                // load / reseed — fresh token ids) nor a char_id, so the
                // token_template_id + label fallback is what lets an NPC
                // mover (e.g. a Vampire Spawn) match — without it
                // _activeForDash stays null and the Dash gate never fires.
                const _matches = (
                    (_active.source_token_id != null
                     && _active.source_token_id === tokenId)
                    || (_active.char_id != null
                        && _active.char_id === token.character_id)
                    || (_active.token_template_id != null
                        && _active.token_template_id === token.token_template_id
                        && _active.name === token.label)
                );
                if (_matches) {
                    _activeForDash = _active;
                    // Use the server's preview distance when present;
                    // fall back to a local Chebyshev / Euclidean
                    // derivation when preview_move failed (offline
                    // safety net).
                    if (_projectedDistance <= 0 && gridSize > 0) {
                        const _dx = sx - origX, _dy = sy - origY;
                        const _cells = (gridType === 'square')
                            ? Math.max(Math.abs(_dx), Math.abs(_dy)) / gridSize
                            : Math.sqrt(_dx * _dx + _dy * _dy) / gridSize;
                        _projectedDistance = Math.round(_cells * 5 * 10) / 10;
                    }
                    const _econ = _active.economy || {};
                    const _used = Number(_econ.movement) || 0;
                    const _dashBonus = Number(_econ.dash_bonus_ft) || 0;
                    /* v2.99.98 — read the post-reduction effective
                     * speed (Lance of Lethargy + future Slow / web).
                     * Falls back to raw speed_walk when the global
                     * helper hasn't loaded yet. */
                    const _speed = (typeof window._effectiveSpeedWalk === 'function')
                        ? window._effectiveSpeedWalk(_active)
                        : (Number(_active.speed_walk) || 30);
                    const _cap = _speed + _dashBonus;
                    _projectedOverrun = (_used + _projectedDistance) > _cap + 0.001;
                    // v2.100.1 — re-narrow the Dash-modal gate to
                    // `overrun && !action`. v2.99.77 had broadened it
                    // to `!action` (offer Dash on EVERY OA-provoking
                    // move while the action slot is free), but that
                    // surfaced a spurious "Take the Dash action?"
                    // popup whenever a combatant still had movement
                    // budget to spare — most visibly for NPCs, whose
                    // combatant `economy.action` is typically unset
                    // (`!undefined` → true), so every short NPC step
                    // away from a PC got the green Dash card instead
                    // of going straight to the OA Continue/Stop modal.
                    // Dash only matters when the move needs MORE
                    // movement than the remaining cap allows; within
                    // the cap there's nothing to extend. The OA modal
                    // itself still fires for every OA-provoking move
                    // (it's gated on `_oaTriggers.length`, not on
                    // Dash), so within-cap provoking moves keep their
                    // OA prompt — they just skip the pointless Dash
                    // offer. Over-cap + action-available still chains
                    // Dash → OA as before.
                    _needsDash = _projectedOverrun && !_econ.action;
                }
            }
        }

        if (_oaTriggers.length > 0) {
            // v2.99.69 — sequential Dash → OA modals. v2.99.72 —
            // the Dash modal is now gated on _needsDash so it
            // doesn't appear when the active combatant still has
            // movement budget. When Dash isn't needed (plenty of
            // movement OR no active match OR action already spent),
            // jump straight to the OA Continue/Stop modal.
            const _openOaModal = () => _showPreMoveOaModal({
                tokenLabel: token.label || 'Token',
                triggers: _oaTriggers,
                distanceFt: _previewDistanceFt,
                /* v2.99.99 — reaching the OA Continue button means
                 * the user has already seen the pre-move chain
                 * (Dash → OA when _needsDash, OA-only otherwise) and
                 * made their intent clear. Pass over_speed_confirmed
                 * so the v2.99.99 server gate doesn't double-prompt
                 * via a second 409. The Dash decision is reflected
                 * in the combatant's dash_bonus_ft on the server
                 * already (via the prior /use_dash if taken). */
                onContinue: () => postMove(true, true),
                onStop: snapBack,
            });
            if (_needsDash && _activeForDash) {
                _showPreMoveDashModal({
                    tokenLabel: token.label || 'Token',
                    triggers: _oaTriggers,
                    distanceFt: _previewDistanceFt,
                    onChoice: (tookDash) => {
                        if (tookDash && typeof window._dashCombatant === 'function') {
                            try { window._dashCombatant(_activeForDash); }
                            catch (e) {
                                console.warn('[oa-dash] _dashCombatant failed', e);
                            }
                        }
                        _openOaModal();
                    },
                    onCancel: snapBack,
                });
            } else {
                _openOaModal();
            }
            return;
        }

        // v2.100.0 — GM over-range advisory. When the GM repositions
        // a token that is NOT the active combatant (an off-turn drag
        // or an NPC-side piece) further than its base walking speed in
        // a single step DURING an active battle, surface a confirm
        // popup. Pre-v2.100.0 these drags committed silently because
        // the overrun gate below only scopes to the active combatant.
        // Advisory only — "Move anyway" commits, "Cancel" snaps back —
        // since the GM is the rules arbiter and may move pieces
        // narratively. The active combatant's per-turn budget is left
        // to showMovementOverrunModal (which honors Dash + cumulative
        // movement), so we explicitly skip when the token IS active.
        if (ME && ME.isGm && _overRange && !_activeForDash && _anyActive) {
            _showGmOverRangeModal({
                tokenLabel: token.label || 'Token',
                distanceFt: _previewDistanceFt,
                speedFt: _tokenSpeedFt,
                onMove: () => postMove(),
                onCancel: snapBack,
            });
            return;
        }

        // v2.99.72 — removed the GM bypass on the overrun gate.
        // Pre-v2.99.72 a GM dragging the active combatant's token
        // past the speed cap got NO prompt, so a 35 ft drag with a
        // 30 ft cap silently committed. The active-combatant match
        // check below still scopes the modal: GM drags of off-turn
        // / NPC-side tokens still pass through without a modal.
        if (typeof window.showMovementOverrunModal !== 'function') {
            postMove();
            return;
        }
        if (!_activeForDash || !_projectedOverrun) {
            // Either we're not the active combatant (off-turn drag)
            // or the move fits inside the existing cap — no modal.
            postMove();
            return;
        }
        const _econOv = _activeForDash.economy || {};
        const _usedOv = Number(_econOv.movement) || 0;
        const _dashBonusOv = Number(_econOv.dash_bonus_ft) || 0;
        /* v2.99.98 — Dash modal reads the post-reduction speed so
         * the displayed cap (and the "you need to Dash" copy) reflect
         * Lance of Lethargy / future speed-reduction effects. */
        const _speedOv = (typeof window._effectiveSpeedWalk === 'function')
            ? window._effectiveSpeedWalk(_activeForDash)
            : (Number(_activeForDash.speed_walk) || 30);
        window.showMovementOverrunModal({
            characterName: _activeForDash.name,
            currentUsed: _usedOv,
            distanceFt: _projectedDistance,
            speedCap: _speedOv,
            dashed: _dashBonusOv > 0,
            onCancel: snapBack,
            /* v2.99.99 — when the user accepts the overrun via
             * "Just move", pass over_speed_confirmed:true so the
             * server 409 gate (v2.99.99) lets it through. The Dash
             * path doesn't need the flag — installing the dash
             * bonus raises the server's effective cap so the
             * subsequent /token/move stays under the threshold. */
            onMove: () => postMove(false, true),
            onDash: () => {
                if (typeof window._dashCombatant === 'function') {
                    window._dashCombatant(_activeForDash);
                }
                // v2.100.3 — pass over_speed_confirmed:true. The Dash
                // bonus is applied to hub state asynchronously (via the
                // /use_dash POST inside _dashCombatant), so relying on
                // the server's effective-cap gate to "see" the dash
                // before this /token/move lands is a race — under load
                // the move could 409 over_speed_cap and silently fail
                // to commit, which is exactly the "movement stops
                // tracking after Dash" symptom. The user explicitly
                // chose Dash, so bypassing the cap gate here is correct;
                // the dash_bonus_ft still propagates (for the chip cap
                // + subsequent moves) via the economy_update broadcast.
                postMove(false, true);
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
            if (_isTokenHiddenFromMe(t)) continue;
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
            // v2.86.0 — surgical encounter-background swap. Fired by
            // the encounter-load flow when the loaded encounter binds
            // a different background_url to the campaign than what's
            // currently displayed, AND by the /api/campaign/{id}/background
            // direct-set endpoint. Skipped during map_change loads
            // because that branch hard-reloads and the SSR picks the
            // new bg up.
            //
            // Rebuilds the inner media element when the type changes
            // between img and video (mp4/webm → video; everything else
            // → img); otherwise just swaps the src in place, which is
            // smooth for img/img and video/video transitions.
            if (msg.type === 'background_change') {
                const layer = document.getElementById('encounter-bg-layer');
                if (!layer) return;
                const newUrl = msg.data && msg.data.url ? String(msg.data.url) : '';
                // v2.86.1 — toggle the body class that drops body's
                // opaque theme background so the z-index:-1 layer is
                // actually visible. Without this the layer is in the
                // DOM with the right src but painted-over by the
                // body's `background: var(--bg)` rule.
                if (newUrl) {
                    document.body.classList.add('has-encounter-bg');
                } else {
                    document.body.classList.remove('has-encounter-bg');
                }
                if (!newUrl) {
                    layer.innerHTML = '';
                    return;
                }
                const ext = newUrl.split('.').pop().toLowerCase();
                const wantVideo = (ext === 'mp4' || ext === 'webm');
                const wantTag = wantVideo ? 'VIDEO' : 'IMG';
                let media = document.getElementById('encounter-bg-media');
                if (media && media.tagName !== wantTag) {
                    media.remove();
                    media = null;
                }
                if (!media) {
                    media = document.createElement(wantTag.toLowerCase());
                    media.id = 'encounter-bg-media';
                    media.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
                    if (wantVideo) {
                        media.autoplay = true; media.loop = true;
                        media.muted = true; media.playsInline = true;
                    } else {
                        media.alt = '';
                    }
                    layer.appendChild(media);
                }
                if (media.getAttribute('src') !== newUrl) {
                    media.setAttribute('src', newUrl);
                    if (wantVideo) {
                        try { media.load(); media.play().catch(() => {}); } catch (e) {}
                    }
                }
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
                // v2.99.32 — track most-recent-roll per character so
                // the BI die banner (v2.97.57) can pick up the
                // roll's stat_key / stat_ability for chat-card text.
                // Indexed by character_id; timestamps let consumers
                // ignore stale entries.
                try {
                    const d = msg.data || {};
                    if (d.character_id && (d.stat_key || d.stat_ability)) {
                        window._lastRollByChar = window._lastRollByChar || {};
                        window._lastRollByChar[d.character_id] = {
                            stat_key: d.stat_key || '',
                            stat_ability: d.stat_ability || '',
                            ts: Date.now(),
                        };
                    }
                } catch (e) { /* tracker is best-effort */ }
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
                try { _renderAoeMoveControls(); } catch (_) {}
            } else if (msg.type === 'map_ambient_light') {
                // v2.710.0 — Phase 5 vision & light: ambient changed.
                mapAmbientLight = (msg.data && msg.data.ambient_light) || 'bright';
                try { render(); } catch (_) {}
            } else if (msg.type === 'light_emitter_add') {
                // v2.710.0 — a Darkness/Daylight/Fog emitter was placed.
                if (msg.data && msg.data.id) lightEmitters.push(msg.data);
                try { render(); } catch (_) {}
            } else if (msg.type === 'light_emitter_remove') {
                lightEmitters = lightEmitters.filter(
                    e => e && e.id !== (msg.data && msg.data.id));
                try { render(); } catch (_) {}
            } else if (msg.type === 'aoe_pulse') {
                // v2.111.0 — instantaneous AoE flash (Fireball etc.).
                try { _addAoePulse(msg.data || {}); } catch (_) {}
            } else if (msg.type === 'feature_used') {
                _appendFeatureUsed(msg.data);
                _focusRollLogIfLocal(msg.data && msg.data.user_id);
            } else if (msg.type === 'legendary_action_aoe_resolved') {
                // v2.163.0 — save-AoE legendary action result card.
                _appendLegendaryAoeResolved(msg.data);
            } else if (msg.type === 'reaction_prompt') {
                // v2.99.63 — inject Take OA / Skip / per-attack buttons
                // into the matching OA chat-log card. Pairs with the
                // top-right popup (reaction_prompt.js) so the user has
                // two parallel actionable surfaces; if the popup is
                // hidden, dismissed, or fails to render, the chat-card
                // buttons still work.
                try { _injectOaButtonsToChatCard(msg.data); } catch (e) {
                    console.warn('[oa-inline] inject failed', e);
                }
            } else if (msg.type === 'reaction_prompt_resolved') {
                // v2.99.74 — when ANY surface resolves the prompt
                // (popup click in another tab, GM clicking through
                // the panel, /use_reaction race), strip the
                // .action-needed border + collapse the chat-card
                // action row so the row stops drawing the eye.
                try { _markOaCardResolved(msg.data); } catch (e) {
                    console.warn('[oa-inline] resolved-mark failed', e);
                }
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
            } else if (msg.type === 'movement_lock_update') {
                // v2.102.0 — live movement-lock toggle. Update the
                // client flag the drag gate reads + the GM toggle
                // button chrome. Everyone tracks the flag (players
                // need it so the drag gate fires without a server
                // round-trip); only the GM has the toggle button.
                _onMovementLockUpdate(!!(msg.data && msg.data.locked));
            } else if (msg.type === 'movement_request') {
                // v2.104.0 — a player asked to move while locked. Only
                // GMs receive this broadcast; show the approve/deny
                // popup. Guard on isGm as belt-and-suspenders.
                if (ME && ME.isGm && msg.data) {
                    _showMovementRequestModal(msg.data);
                }
            } else if (msg.type === 'movement_request_resolved') {
                // v2.104.0 — GM answered a movement request. Dismiss
                // any open GM popup for this request, and — on the
                // requester's own client — bank the one-shot grant (on
                // approve) or toast the denial.
                _onMovementRequestResolved(msg.data || {});
            }
        };
        ws.onclose = () => setTimeout(connectWs, 2000);
    }
    connectWs();

    // v2.115.0 — wire reroll buttons on the server-rendered roll
    // history (past rolls present at page load). Live WS rolls get
    // wired in appendRoll; these pre-rendered cards carry data-roll-id
    // / data-character-id so the same handler can attach. Reuses
    // _wireRerollButtons with a minimal roll shape.
    document.querySelectorAll('#roll-list li[data-roll-id]').forEach((li) => {
        const rollId = parseInt(li.dataset.rollId, 10);
        if (!rollId) return;
        const charId = li.dataset.characterId
            ? parseInt(li.dataset.characterId, 10) : null;
        _wireRerollButtons(li, { id: rollId, character_id: charId });
    });

    // v2.102.0 — movement-lock toggle (GM-only button) + client state.
    // window._MOVEMENT_LOCKED is seeded server-side in the template and
    // kept fresh here by the movement_lock_update WS handler; the
    // _commitTokenMove gate reads it. The button only exists for the
    // GM (players never get the toggle in the DOM).
    function _syncMovementLockBtn() {
        const btn = document.getElementById('movement-lock-btn');
        if (!btn) return;
        const locked = !!window._MOVEMENT_LOCKED;
        btn.setAttribute('aria-pressed', locked ? 'true' : 'false');
        btn.textContent = locked ? '🔒 Locked' : '🔓 Unlocked';
        btn.title = locked
            ? 'Movement is LOCKED for players — click to unlock'
            : 'Movement is unlocked — click to lock players out';
    }
    function _onMovementLockUpdate(locked) {
        window._MOVEMENT_LOCKED = !!locked;
        _syncMovementLockBtn();
    }
    // v2.104.0 — client-side one-shot movement grants (token ids the
    // GM approved while locked). The _commitTokenMove gate consumes a
    // grant to let a single drag through.
    window._MOVEMENT_GRANTS = window._MOVEMENT_GRANTS || new Set();
    function _onMovementRequestResolved(data) {
        const rid = data.request_id;
        // Dismiss any open GM approve/deny popup for this request
        // (e.g. a second GM tab already answered).
        if (rid) {
            document.querySelectorAll(
                `[data-movement-request-id="${rid}"]`,
            ).forEach((el) => el.remove());
        }
        // Only the requester banks the grant / sees the outcome toast.
        if (!ME || ME.id !== data.requester_user_id) return;
        if (data.approved) {
            if (data.token_id != null) window._MOVEMENT_GRANTS.add(data.token_id);
            showToast(
                '✓ GM approved — you can move '
                + (data.token_label || 'your token') + ' once now.',
                'info',
            );
        } else {
            showToast(
                '✋ GM denied the move for '
                + (data.token_label || 'your token') + '.',
                'error',
            );
        }
    }
    (function _wireMovementLockBtn() {
        const btn = document.getElementById('movement-lock-btn');
        if (!btn) return;  // players have no toggle
        _syncMovementLockBtn();
        btn.addEventListener('click', async () => {
            const next = !window._MOVEMENT_LOCKED;
            btn.disabled = true;
            try {
                const r = await fetch(
                    `/api/campaign/${CAMPAIGN_ID}/movement_lock`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ locked: next }),
                    },
                );
                if (r.ok) {
                    const data = await r.json();
                    // Optimistic local sync; the WS broadcast also
                    // arrives and is idempotent.
                    _onMovementLockUpdate(!!data.locked);
                }
            } catch (_) {
                // Network blip — leave state; the WS reconciles.
            } finally {
                btn.disabled = false;
            }
        });
    })();

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
                    else if (e.type === 'legendary_action_aoe_resolved') _appendLegendaryAoeResolved(e.data);
                    else if (e.type === 'lair_action_resolved') _appendLairActionResolved(e.data);
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
            // v2.99.71 — pass {auto: true} so this auto-focus call
            // doesn't toggle-close the left-docked roll log if it's
            // already open. Pre-v2.99.71 the first weapon_attack after
            // an OA auto-roll collapsed the panel because openPanel's
            // toggle-on-click branch fired on every already-open call.
            try { window._openDrawerPanel('roll-log-drawer', { auto: true }); } catch (_) {}
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

        // v2.106.0 — reroll buttons. The server attaches `reroll_options`
        // (e.g. Lucky) to the roll broadcast; render one button per
        // option, but ONLY for the GM + the roller (the PC owner who
        // rolled). A feature the char owns but is out of uses on comes
        // back with `remaining:0` → render disabled (greyed). Hidden
        // entirely when the char has no reroll feature (empty list).
        const _canReroll = (ME.isGm || r.user_id === ME.id);
        const _rerollOpts = (_canReroll && Array.isArray(r.reroll_options))
            ? r.reroll_options : [];
        const _rerollBtns = _rerollOpts.map((o) => {
            const remaining = Number(o.remaining) || 0;
            const dis = remaining <= 0;
            return `<button type="button" class="result-pill reroll-btn"`
                + ` data-feature="${escapeHTML(o.key)}"${dis ? ' disabled' : ''}`
                + ` title="${escapeHTML(o.desc || '')}">`
                + `${escapeHTML(o.icon || '🎲')} ${escapeHTML(o.label)}`
                + ` reroll (${remaining})</button>`;
        }).join('');

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
                            ${_rerollBtns}
                        </div>
                    </div>
                </div>
            </div>`;
        if (r.id != null) li.dataset.rollId = r.id;
        if (r.character_id != null) li.dataset.characterId = r.character_id;
        _wireRerollButtons(li, r);
        ul.appendChild(li);
        _scrollRollLogToBottom();
        // ``roll`` not persisted to localStorage — server pre-renders
        // rolls history via Jinja, so replay would double-render.
    }

    /* v2.106.0 — wire a roll card's reroll button(s). Each click
     * confirms, POSTs /use_reroll, and on success toasts the outcome +
     * disables the button (the spent use is reflected; the reroll's own
     * roll broadcast appends the result card). Failure re-enables. */
    function _wireRerollButtons(li, r) {
        li.querySelectorAll('.reroll-btn').forEach((btn) => {
            btn.addEventListener('click', async () => {
                if (btn.disabled) return;
                const feature = btn.dataset.feature;
                const label = btn.textContent.trim();
                if (!confirm(`Spend ${label}? This uses one charge.`)) return;
                btn.disabled = true;
                try {
                    const resp = await fetch(
                        `/api/campaign/${CAMPAIGN_ID}/use_reroll`,
                        {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                character_id: r.character_id,
                                roll_id: r.id,
                                feature_key: feature,
                            }),
                        },
                    );
                    if (resp.ok) {
                        const d = await resp.json();
                        const outcome = d.took_new
                            ? `kept the reroll (d20 ${d.new_d20}, total ${d.new_total})`
                            : `kept the original (d20 ${d.old_d20})`;
                        showToast(
                            `🎲 ${outcome} — ${d.remaining} use(s) left.`,
                            'info',
                        );
                    } else {
                        btn.disabled = false;
                        let msg = 'Reroll failed.';
                        try {
                            const e = await resp.json();
                            if (e && e.error === 'out_of_uses') {
                                msg = 'No reroll uses left.';
                            }
                        } catch (_) { /* keep default */ }
                        showToast(msg, 'error');
                    }
                } catch (_) {
                    btn.disabled = false;
                    showToast('Reroll failed.', 'error');
                }
            });
        });
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

        // v2.97.12: spell meta info moves from the inline `· tail · tail`
        // string under the spell name into pill bubbles below the name.
        // Color family is distinct from .result-pill (which uses semantic
        // damage / heal / buff colors) — these use the accent purple
        // family so the eye reads them as "what kind of spell" not
        // "what happened." The details pill is an expanding <details>
        // pill: collapsed shape matches the others, opens to reveal the
        // full spell desc inline (replaces the pre-v2.97.12 ▾ details
        // disclosure under the name row).
        const metaPills = [];
        if (d.spell_school)        metaPills.push(`<span class="spell-meta-pill">${escapeHTML(d.spell_school)}</span>`);
        if (d.spell_casting_time)  metaPills.push(`<span class="spell-meta-pill">⏱ ${escapeHTML(d.spell_casting_time)}</span>`);
        if (d.spell_range)         metaPills.push(`<span class="spell-meta-pill">📏 ${escapeHTML(d.spell_range)}</span>`);
        if (d.spell_concentration) metaPills.push(`<span class="spell-meta-pill is-flag">Concentration</span>`);
        if (d.spell_ritual)        metaPills.push(`<span class="spell-meta-pill is-flag">Ritual</span>`);
        if (d.spell_desc) {
            metaPills.push(
                `<details class="spell-meta-pill"><summary>details</summary>`
                + `<div class="spell-meta-pill-body">${escapeHTML(d.spell_desc)}</div>`
                + `</details>`
            );
        }

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
                    </div>
                    ${metaPills.length ? `<div class="spell-meta-pills">${metaPills.join('')}</div>` : ''}
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
        // v2.158.34 — AC-swing verdict pill for announce-only AC-boost
        // reactions (Form of the Beast tail swat; generic for any future
        // reaction shipping ac_bonus + new_ac). Gives the GM the same
        // glanceable MISS/HIT outcome the attack cards show, instead of
        // burying it in the feature_desc prose. From the defender's seat
        // a resulting MISS is the win → green chip-hit; a still-landing
        // HIT is red chip-miss; an unknown attack total stays neutral.
        if (typeof d.ac_bonus === 'number' && d.ac_bonus > 0 && d.new_ac != null) {
            let acCls, acTail;
            if (d.verdict === 'miss')      { acCls = 'chip-hit';  acTail = ' · ✅ MISS'; }
            else if (d.verdict === 'hit')  { acCls = 'chip-miss'; acTail = ' · ❌ HIT'; }
            else                           { acCls = 'chip-buff'; acTail = ''; }
            featurePills.push(
                `<span class="result-pill ${acCls}">🛡️ +${Number(d.ac_bonus)} AC → AC ${escapeHTML(String(d.new_ac))}${acTail}</span>`
            );
        }
        // v2.96.0 / v2.97.0 — ↶ Undo pill for feature_used cards
        // that carry a cast_id. Clicking POSTs to
        // /undo_attack_damage which dispatches one of the v2.92+ refund
        // branches:
        //   * reaction-cast sources (counterspell, shield, hellish
        //     rebuke, absorb elements, silvery barbs) → server bumps
        //     the spell slot's ``used`` count down and broadcasts
        //     spell_slot_update (v2.92.0 ``spell_slot_spend`` branch).
        //   * feature-resource sources (lay-on-hands, second-wind)
        //     → server bumps ``sheet["resources"][i]["current"]`` up
        //     by the spent amount, clamped to max, and broadcasts
        //     resource_update (v2.97.0 ``resource_spend`` branch).
        // Limited to the explicit allow-list so other feature_used
        // cards without server-side refund plumbing don't render a
        // non-functional pill — each new refundable source opts in
        // by adding its slug to the Set.
        const _REFUNDABLE_FEATURE_SOURCES = new Set([
            'counterspell-cast',
            'shield-cast',
            'hellish-rebuke-cast',
            'absorb-elements-cast',
            'silvery-barbs-cast',
            'lay-on-hands',
            'second-wind',
            'bardic-inspiration',
            'cutting-words',
            'action-surge',
            'indomitable',
            'rage',
            'patient-defense',
            'flurry-of-blows',
            'wholeness-of-body',
            'step-of-the-wind',
            'metamagic-empowered-spell',
            'arcane-recovery',
            'font-of-magic',
            'class-feature',
            'item-use',
            'stunning-strike',
            'hunters-mark',
            'hex',
            // v2.97.79 — save-pass condition-drop sources. The server
            // stamps a buff_drop_from_save log entry under a fresh
            // cast_id and ships it on these feature_used broadcasts so
            // the GM can undo a save-pass that shouldn't have been
            // allowed (wrong DC, wrong target, etc.). Hits the
            // v2.97.77 reverse branch in /undo_attack_damage.
            'repeated-save-passed',
            'repeated-save-passed-auto',
            'damage-triggered-save-passed',
        ]);
        if (d.cast_id && _REFUNDABLE_FEATURE_SOURCES.has(d.source)) {
            featurePills.push(
                `<button type="button" class="result-pill chip-undo feature-cast-undo"`
                + ` data-cast-id="${escapeHTML(d.cast_id)}"`
                + ` title="Refund the resource consumed by this feature use">↶ Undo</button>`
            );
        }
        const healPill = featurePills.length
            ? `<div class="result-pills">${featurePills.join('')}</div>`
            : '';
        const targetTagHtml = _targetTagHtml(d);
        // v2.99.63 — when this is an OA trigger card, tag the LI with
        // data attributes so the reaction_prompt arrival can find the
        // right card to inject action buttons into. The empty
        // .oa-action-row div is populated on reaction_prompt arrival
        // (per the v2.99.63 inline-buttons fallback for the popup).
        const isOaTrigger = d.source === 'opportunity-attack-trigger';
        const oaDataAttrs = isOaTrigger
            ? ` data-source="opportunity-attack-trigger"`
            + ` data-watcher-combatant-id="${escapeHTML(d.watcher_combatant_id || '')}"`
            + ` data-trigger-type="${escapeHTML(d.trigger_type || 'exit')}"`
            + ` data-prompt-injected="false"`
            : '';
        const oaActionRow = isOaTrigger
            ? `<div class="oa-action-row" style="display:none;margin-top:8px;flex-wrap:wrap;gap:6px;"></div>`
            : '';
        const li = document.createElement('li');
        if (oaDataAttrs) {
            // setAttribute path so the data-* land on the LI itself,
            // not the inner card div. Querying .closest('li') from a
            // descendant button finds the right card to mark resolved.
            li.setAttribute('data-source', 'opportunity-attack-trigger');
            if (d.watcher_combatant_id) li.setAttribute(
                'data-watcher-combatant-id', String(d.watcher_combatant_id),
            );
            if (d.trigger_type) li.setAttribute(
                'data-trigger-type', String(d.trigger_type),
            );
            li.setAttribute('data-prompt-injected', 'false');
        }
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
                    ${oaActionRow}
                </div>
            </div>`;
        ul.appendChild(li);
        _scrollRollLogToBottom();
        _persistRollEntry('feature_used', d);
        // v2.96.0 — wire the Undo pill click. Same POST shape as the
        // existing .weapon-atk-undo handlers; on success the server
        // broadcasts spell_slot_update which the sheet hydrators
        // already consume. We grey the button + change its label so
        // the GM gets immediate feedback even before the WS round-trip.
        const undoCastBtn = li.querySelector('.feature-cast-undo');
        if (undoCastBtn) {
            undoCastBtn.addEventListener('click', async () => {
                const cid = undoCastBtn.dataset.castId;
                if (!cid) return;
                undoCastBtn.disabled = true;
                const orig = undoCastBtn.textContent;
                undoCastBtn.textContent = '↶ Refunding…';
                try {
                    const r = await fetch(`/api/campaign/${CAMPAIGN_ID}/undo_attack_damage`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ attack_id: cid }),
                    });
                    if (!r.ok) {
                        let body; try { body = await r.json(); } catch { body = null; }
                        (window.showToast || function(m){ alert(m); })(
                            `Undo failed: ${body ? JSON.stringify(body) : r.status}`, 'error');
                        undoCastBtn.disabled = false;
                        undoCastBtn.textContent = orig;
                        return;
                    }
                    undoCastBtn.textContent = '↶ Refunded';
                } catch (e) {
                    console.warn('undo_attack_damage failed:', e);
                    undoCastBtn.disabled = false;
                    undoCastBtn.textContent = orig;
                }
            });
        }
    }

    // v2.163.0 — legendary-action save-AoE result card. The server
    // broadcasts ``legendary_action_aoe_resolved`` after a save-AoE
    // legendary action (the Adult Red Dragon's Wing Attack) rolls each
    // picked target's saving throw + applies save-or-take damage. This
    // renders the outcome as a roll-log card so the whole table sees who
    // saved and who took damage, instead of only the silent HP ticks.
    // Per-target pills: green ✅ SAVED for a passed save, red ❌ for a
    // failed save (with the damage dealt), neutral ⏳ for a PC target
    // whose save was prompted (GM-manual, damage deferred).
    function _appendLegendaryAoeResolved(d) {
        const ul = document.getElementById('roll-list');
        if (!ul || !d || typeof d !== 'object') return;
        const now = new Date();
        const h = now.getHours(), m = now.getMinutes();
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12  = (h % 12) || 12;
        const hhmm = h12.toString().padStart(2,'0') + ':' + m.toString().padStart(2,'0') + ' ' + ampm;
        const dragon = d.combatant_name || 'Legendary creature';
        const action = d.action_name || 'Legendary Action';
        const saveAb = String(d.save_ability || '').toUpperCase();
        const saveDc = d.save_dc;
        const dmgType = d.damage_type || '';
        const saveLine = (saveAb && saveDc != null)
            ? `${escapeHTML(saveAb)} save · DC ${escapeHTML(String(saveDc))}`
            : '';
        const results = Array.isArray(d.results) ? d.results : [];
        const pills = results.map(r => {
            if (!r || typeof r !== 'object') return '';
            const nm = escapeHTML(r.name || 'Target');
            if (r.prompted && r.passed == null) {
                return `<span class="result-pill chip-buff">⏳ ${nm} · save pending</span>`;
            }
            if (r.passed === true) {
                return `<span class="result-pill chip-hit">✅ ${nm} · saved</span>`;
            }
            // Failed save (passed === false) → took damage.
            const dmg = Number(r.damage_dealt || 0);
            const tail = dmg > 0
                ? ` · −${dmg}${dmgType ? ' ' + escapeHTML(dmgType) : ''}`
                : '';
            return `<span class="result-pill chip-miss">❌ ${nm}${tail}</span>`;
        }).filter(Boolean).join('');
        const pillRow = pills ? `<div class="result-pills">${pills}</div>` : '';
        const li = document.createElement('li');
        li.innerHTML = `
            <div class="roll-card feature-used-card">
                <div class="roll-card-header">
                    <div class="roll-card-avatar">👑</div>
                    <span class="roll-card-user">${escapeHTML(dragon)}</span>
                    <span class="spell-cast-slot">Legendary Action</span>
                    <span class="roll-card-time">${hhmm}</span>
                </div>
                <div class="roll-card-body" style="padding:6px 10px 8px;">
                    <div class="feature-used-name-row">
                        <strong class="feature-used-name">${escapeHTML(action)}</strong>
                        ${saveLine ? `<span class="feature-used-desc">· ${saveLine}</span>` : ''}
                    </div>
                    ${pillRow}
                </div>
            </div>`;
        ul.appendChild(li);
        _scrollRollLogToBottom();
        _persistRollEntry('legendary_action_aoe_resolved', d);
    }
    // Exposed for the harness so a Playwright test can drive the card
    // render without simulating a live WS broadcast.
    window._appendLegendaryAoeResolved = _appendLegendaryAoeResolved;

    // v2.177.0 — lair-action result card. The server broadcasts
    // ``lair_action_resolved`` when the GM fires a lair action (RAW MM
    // p.11). v2.170.0 surfaced it as a transient GM toast; this renders a
    // persistent roll-log card so the WHOLE table sees the count-20 beat —
    // who saved, who took damage, who got a condition — instead of only
    // the silent HP ticks. Per-target pills mirror the legendary AoE card:
    // green ✅ SAVED, red ❌ for a failed save (with damage and/or the
    // installed condition), neutral ⏳ for a PC whose save was prompted.
    function _appendLairActionResolved(d) {
        const ul = document.getElementById('roll-list');
        if (!ul || !d || typeof d !== 'object') return;
        const now = new Date();
        const h = now.getHours(), m = now.getMinutes();
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12  = (h % 12) || 12;
        const hhmm = h12.toString().padStart(2,'0') + ':' + m.toString().padStart(2,'0') + ' ' + ampm;
        const owner  = d.owner_name || 'The lair';
        const action = d.action_name || 'Lair Action';
        const saveAb = String(d.save_ability || '').toUpperCase();
        const saveDc = d.save_dc;
        const dmgType = d.damage_type || '';
        const effect = d.effect ? String(d.effect) : '';
        const saveLine = (saveAb && saveDc != null && saveDc !== '')
            ? `${escapeHTML(saveAb)} save · DC ${escapeHTML(String(saveDc))}`
            : '';
        const results = Array.isArray(d.results) ? d.results : [];
        const pills = results.map(r => {
            if (!r || typeof r !== 'object') return '';
            const nm = escapeHTML(r.name || 'Target');
            if (r.prompted && r.passed == null) {
                return `<span class="result-pill chip-buff">⏳ ${nm} · save pending</span>`;
            }
            if (r.passed === true) {
                return `<span class="result-pill chip-hit">✅ ${nm} · saved</span>`;
            }
            // Failed save (passed === false) → damage and/or condition.
            const dmg = Number(r.damage_dealt || 0);
            let tail = dmg > 0
                ? ` · −${dmg}${dmgType ? ' ' + escapeHTML(dmgType) : ''}`
                : '';
            if (r.condition_installed && effect) {
                tail += ` · ${escapeHTML(effect)}`;
            }
            return `<span class="result-pill chip-miss">❌ ${nm}${tail}</span>`;
        }).filter(Boolean).join('');
        const pillRow = pills ? `<div class="result-pills">${pills}</div>` : '';
        const li = document.createElement('li');
        li.innerHTML = `
            <div class="roll-card feature-used-card">
                <div class="roll-card-header">
                    <div class="roll-card-avatar">🌋</div>
                    <span class="roll-card-user">${escapeHTML(owner)}</span>
                    <span class="spell-cast-slot">Lair Action</span>
                    <span class="roll-card-time">${hhmm}</span>
                </div>
                <div class="roll-card-body" style="padding:6px 10px 8px;">
                    <div class="feature-used-name-row">
                        <strong class="feature-used-name">${escapeHTML(action)}</strong>
                        ${saveLine ? `<span class="feature-used-desc">· ${saveLine}</span>` : ''}
                    </div>
                    ${pillRow}
                </div>
            </div>`;
        ul.appendChild(li);
        _scrollRollLogToBottom();
        _persistRollEntry('lair_action_resolved', d);
    }
    window._appendLairActionResolved = _appendLairActionResolved;

    // v2.99.63 — inline OA action buttons in the chat-log card.
    // The reaction_prompt broadcast (popup pipeline) carries
    // prompt_id + options + watcher_combatant_id. Find the most
    // recent OA card matching watcher_combatant_id that hasn't
    // been injected yet, and populate its .oa-action-row with
    // clickable buttons (Take OA / per-attack / War Caster / Skip).
    // Click → POST /use_reaction; on success, replace the row with
    // a resolved state indicator.
    function _injectOaButtonsToChatCard(data) {
        if (!data || typeof data !== 'object') return;
        const trig = data.trigger_event || '';
        if (trig !== 'creature_exits_reach' && trig !== 'creature_enters_reach') {
            return;
        }
        const wcid = data.watcher_combatant_id;
        if (!wcid) return;
        // v2.99.77 — only inject the action buttons for users who
        // are actually allowed to act on this prompt: the GM (always
        // sees + can roll) OR a member of the prompt's
        // target_user_ids (the watcher's PC owner under the v2.99.59
        // presence routing, or the GM-as-fallback when the owner is
        // offline). Other players see the trigger card but no
        // buttons + no action-needed border, so they're aware
        // something happened without clutter on their UI.
        const meId = (typeof ME !== 'undefined' && ME && ME.id != null)
            ? Number(ME.id) : null;
        const meIsGm = !!(typeof ME !== 'undefined' && ME && ME.isGm);
        const targets = Array.isArray(data.target_user_ids)
            ? data.target_user_ids.map(Number) : [];
        const canAct = meIsGm || (meId != null && targets.includes(meId));
        if (!canAct) {
            console.log(
                '[oa-inline] user not in target_user_ids;',
                'skip buttons + border.',
                'me=' + meId,
                'gm=' + meIsGm,
                'targets=[' + targets.join(',') + ']',
            );
            return;
        }
        // Diagnostic log so the user can see (in DevTools Console)
        // that the OA prompt arrived AND was matched to a card.
        console.log(
            '[oa-inline] injecting buttons',
            'watcher=' + wcid,
            'prompt=' + data.prompt_id,
            'options=' + (data.options || []).length,
        );
        const ul = document.getElementById('roll-list');
        if (!ul) return;
        // Walk LIs in reverse to find the most recent matching OA
        // card that hasn't had buttons injected yet.
        const lis = ul.querySelectorAll(
            'li[data-source="opportunity-attack-trigger"]'
            + '[data-prompt-injected="false"]',
        );
        let targetLi = null;
        for (let i = lis.length - 1; i >= 0; i--) {
            if (String(lis[i].dataset.watcherCombatantId) === String(wcid)) {
                targetLi = lis[i];
                break;
            }
        }
        if (!targetLi) {
            console.warn(
                '[oa-inline] no matching card found for watcher='
                + wcid + '; popup-only fallback',
            );
            return;
        }
        const row = targetLi.querySelector('.oa-action-row');
        if (!row) return;
        row.innerHTML = '';
        const opts = Array.isArray(data.options) ? data.options : [];
        const promptId = data.prompt_id;
        opts.forEach(opt => {
            if (!opt || !opt.key) return;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'oa-action-btn';
            btn.textContent = opt.label || opt.key;
            btn.setAttribute('style', [
                'padding:6px 12px',
                'border-radius:6px',
                'border:1px solid var(--border, rgba(255,255,255,0.22))',
                'background:rgba(255,255,255,0.04)',
                'color:var(--fg, #fff)',
                'font-size:12px',
                'cursor:pointer',
                'min-height:36px',
            ].join(';'));
            if (opt.available === false) {
                btn.disabled = true;
                btn.title = opt.unavailable_reason || '';
                btn.style.opacity = '0.5';
                btn.style.cursor = 'not-allowed';
            }
            btn.addEventListener('click', async () => {
                row.querySelectorAll('button').forEach(b => { b.disabled = true; });
                try {
                    const resp = await fetch(
                        `/api/campaign/${CAMPAIGN_ID}/use_reaction`,
                        {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            credentials: 'same-origin',
                            body: JSON.stringify({
                                prompt_id: promptId,
                                reaction_key: opt.key,
                                watcher_char_id: data.watcher_char_id,
                            }),
                        },
                    );
                    if (resp.ok) {
                        // v2.99.75 — drop the entire "Opportunity
                        // Attack triggered" chat-card LI on resolve
                        // (was: swap row.innerHTML to "✓ Resolved").
                        // The weapon_attack card (is_oa=true) is the
                        // audit; the trigger row is noise once acted.
                        // Skip resolves leave no card at all.
                        targetLi.remove();
                        // v2.99.68 — chain the chosen OA attack roll
                        // so the chat-card click yields a weapon
                        // attack immediately. Mirrors the popup-side
                        // _chainOaAttack in reaction_prompt.js.
                        if (typeof opt.key === 'string'
                                && opt.key.startsWith('take-the-oa:')
                                && data.mover_combatant_id) {
                            const p = opt.params || {};
                            const isNpc = !!p.npc || !data.watcher_char_id;
                            try {
                                if (isNpc) {
                                    await fetch(
                                        `/api/campaign/${CAMPAIGN_ID}/npc_attack`,
                                        {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            credentials: 'same-origin',
                                            body: JSON.stringify({
                                                combatant_id: data.watcher_combatant_id,
                                                action_id: p.action_id || '',
                                                action_name: p.action_name || '',
                                                attack_bonus: p.attack_bonus || '',
                                                damage: p.damage || '',
                                                damage_type: p.damage_type || '',
                                                range: p.range || '',
                                                target_combatant_id: data.mover_combatant_id,
                                                // v2.99.75 — OA hint
                                                is_opportunity_attack: true,
                                            }),
                                        },
                                    );
                                } else {
                                    await fetch(
                                        `/api/campaign/${CAMPAIGN_ID}/attack`,
                                        {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            credentials: 'same-origin',
                                            body: JSON.stringify({
                                                character_id: data.watcher_char_id,
                                                attack_index: p.attack_index,
                                                target_combatant_id: data.mover_combatant_id,
                                                is_opportunity_attack: true,
                                            }),
                                        },
                                    );
                                }
                            } catch (chainErr) {
                                console.error('[oa-inline] auto-roll failed', chainErr);
                            }
                        }
                    } else {
                        // 409 prompt_already_resolved (cross-tab race)
                        // OR 400 (bad input). v2.99.75 — drop the
                        // trigger card; another surface already resolved
                        // and there's nothing meaningful left to show.
                        targetLi.remove();
                        if (resp.status !== 409) {
                            console.warn(
                                '[oa-inline] /use_reaction failed',
                                resp.status, await resp.text(),
                            );
                        }
                    }
                } catch (e) {
                    console.error('[oa-inline] /use_reaction errored', e);
                    row.querySelectorAll('button').forEach(b => { b.disabled = false; });
                }
            });
            row.appendChild(btn);
        });
        row.style.display = 'flex';
        targetLi.setAttribute('data-prompt-injected', 'true');
        // v2.99.74 — highlight the chat-card with the same accent
        // border the init tracker uses for the active-turn entry,
        // so the eye finds "this row needs you to click something"
        // without scrolling. Removed in the click handler above
        // when the user resolves the row (innerHTML swap to
        // "✓ Resolved" replaces the buttons; we strip the class
        // here for clarity since the same row may chain another
        // prompt later).
        targetLi.classList.add('action-needed');
    }

    // v2.99.75 — remove the OA "Opportunity Attack triggered"
    // chat-card LI entirely on resolve, per the user's request to
    // drop the legacy "triggered" + "OA Attack chosen" cards from
    // the roll log once a choice is made. The weapon_attack card
    // (now marked is_oa) carries the audit trail; the trigger row
    // is just noise once the user has acted. Covers cross-tab
    // races (popup-resolved → resolved broadcast → this clears the
    // matching chat-card on every tab) and the local click path
    // (see the inline button handler in _injectOaButtonsToChatCard
    // — it also calls _removeOaTriggerCard).
    function _markOaCardResolved(data) {
        if (!data || typeof data !== 'object') return;
        const wcid = data.watcher_combatant_id;
        if (!wcid) return;
        _removeOaTriggerCard(wcid);
    }

    function _removeOaTriggerCard(watcherCombatantId) {
        const ul = document.getElementById('roll-list');
        if (!ul) return;
        const cards = ul.querySelectorAll(
            'li[data-source="opportunity-attack-trigger"]',
        );
        for (let i = cards.length - 1; i >= 0; i--) {
            if (String(cards[i].dataset.watcherCombatantId) === String(watcherCombatantId)) {
                cards[i].remove();
                break;
            }
        }
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
        // v2.99.75 — OA chain marker. When the chained /attack
        // (or /npc_attack) carried `is_opportunity_attack: true`
        // the broadcast surfaces `is_oa: true`. Swap the slot
        // label from "⚔ Attack" to "⚔ Opportunity Attack" and
        // tag the weapon name so the chat-card reads as an OA
        // without a redundant audit row above it.
        const isOa = !!d.is_oa;
        const slotLabel = isOa ? '⚔ Opportunity Attack' : '⚔ Attack';
        const weaponPrefix = isOa ? 'OA — ' : '';
        const li = document.createElement('li');
        li.dataset.attackId = d.id;
        li.innerHTML = `
            <div class="spell-cast-card weapon-atk-card">
                <div class="roll-card-header">
                    <div class="roll-card-avatar">${avatarInner}</div>
                    <span class="roll-card-user" data-uid="${d.caster_user_id}"${color ? ` style="color:${escapeHTML(color)}"` : ''}>${escapeHTML(dispName)}</span>
                    ${targetTagHtml}
                    <span class="spell-cast-slot">${slotLabel}</span>
                    <span class="roll-card-time">${timeStr}</span>
                </div>
                <div class="spell-cast-body">
                    <div class="spell-cast-name-row">
                        <span class="spell-cast-name">🗡 ${weaponPrefix}${escapeHTML(d.attack_name || 'Attack')}</span>
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

    // v2.99.53 — plan-movement-oa-flow Phase 2 edit-mode flag. Per
    // session, not persisted. Non-edit (default) renders ownership +
    // team as pills + hides the player-assignment dropdown + the
    // upload-art input. Edit mode swaps the pills for select
    // dropdowns. Toggled by the "✎ Edit" button next to Refresh in
    // tabletop.html.
    let _tmEditMode = false;
    function toggleTokenTrackerEdit() {
        _tmEditMode = !_tmEditMode;
        const btn = document.getElementById('tm-edit-toggle');
        if (btn) {
            btn.textContent = _tmEditMode ? '✓ Done' : '✎ Edit';
            btn.title = _tmEditMode
                ? 'Stop editing (return to pill view)'
                : 'Edit ownership + team per token';
        }
        renderTokenTracker();
    }
    window.toggleTokenTrackerEdit = toggleTokenTrackerEdit;

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
        // v2.99.53 — plan-movement-oa-flow Phase 2 helpers.
        // Owner label for the non-edit pill: "👤 Alice" for a
        // member-controlled token, "⚙ GM" for NPC / blank tokens.
        function _ownerLabel(t) {
            if (t.controller_user_id == null) return '⚙ GM';
            const member = (typeof MEMBERS !== 'undefined' ? MEMBERS : [])
                .find(m => m.id === t.controller_user_id);
            return '👤 ' + (member ? member.name : 'Unknown');
        }
        // Team label + the team-color class on the pill. "neutral"
        // shows muted dash so the GM can see at a glance which
        // tokens still need tagging.
        function _teamLabel(team) {
            const t = String(team || 'neutral').toLowerCase();
            if (t === 'hero')    return '🦸 Hero';
            if (t === 'villain') return '👹 Villain';
            return '—';
        }
        function _renderToken(t) {
            const row = document.createElement('div');
            row.className = 'tt-row';
            row.dataset.id = t.id;
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

            // v2.99.53 — plan-movement-oa-flow Phase 2: non-edit shows
            // owner + team as pills BEFORE the action buttons; edit
            // mode swaps them for select dropdowns. The 🖼 upload-art
            // file input was removed in v2.99.53 per the to-do —
            // token art now lives in the character sheet / template
            // editor.
            const teamRaw = String(t.team || 'neutral').toLowerCase();
            let infoHtml = '';
            if (_tmEditMode) {
                const memberOpts = (typeof MEMBERS !== 'undefined' ? MEMBERS : [])
                    .map(m => `<option value="${m.id}"${t.controller_user_id === m.id ? ' selected' : ''}>${escapeHTML(m.name)}</option>`)
                    .join('');
                const teamOpt = (v, label) =>
                    `<option value="${v}"${teamRaw === v ? ' selected' : ''}>${escapeHTML(label)}</option>`;
                infoHtml = `
                    <select class="tt-ctrl" title="Ownership">
                        <option value="">GM</option>
                        ${memberOpts}
                    </select>
                    <select class="tt-team" title="Team — used by the OA filter">
                        ${teamOpt('neutral', '— Neutral')}
                        ${teamOpt('hero', '🦸 Hero')}
                        ${teamOpt('villain', '👹 Villain')}
                    </select>`;
            } else {
                const ownerLabel = _ownerLabel(t);
                const ownerClass = (t.controller_user_id == null)
                    ? 'tm-pill-owner-gm' : 'tm-pill-owner';
                infoHtml = `
                    <span class="tm-pill ${ownerClass}" title="Ownership">${escapeHTML(ownerLabel)}</span>
                    <span class="tm-pill tm-pill-team-${escapeHTML(teamRaw)}" title="Team: ${escapeHTML(teamRaw)}">${escapeHTML(_teamLabel(teamRaw))}</span>`;
            }

            row.innerHTML = `
                ${avatarHtml}
                <span class="tt-name" contenteditable="true" spellcheck="false">${escapeHTML(t.label)}</span>
                ${infoHtml}
                <button class="tt-btn tt-vis" title="${t.is_hidden ? 'Show token' : 'Hide token'}">${t.is_hidden ? '🚫' : '👁'}</button>
                ${targetBtnHtml}
                ${sheetBtnHtml}
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

            // v2.99.53 — edit-mode dropdowns. Only present when
            // _tmEditMode is true (the row template above gates them).
            const ctrlSel = row.querySelector('.tt-ctrl');
            if (ctrlSel) {
                ctrlSel.addEventListener('change', (e) => {
                    const val = e.target.value;
                    patchToken(t.id, { controller_user_id: val ? parseInt(val, 10) : null });
                });
            }
            const teamSel = row.querySelector('.tt-team');
            if (teamSel) {
                teamSel.addEventListener('change', (e) => {
                    patchToken(t.id, { team: e.target.value || 'neutral' });
                });
            }

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
