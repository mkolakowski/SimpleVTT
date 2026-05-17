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

    function render() {
        ctx.clearRect(0, 0, MAP_W, MAP_H);
        if (showGrid) {
            if (gridType === 'square') drawSquareGrid();
            else if (gridType === 'hex') drawHexGrid();
        }
        tokens.forEach(drawToken);
        drawSpawnMarkers();
        _updateGifOverlay();
    }
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

    canvas.addEventListener('contextmenu', (ev) => ev.preventDefault());

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
                dragging = { token: t, offsetX: x - t.x, offsetY: y - t.y };
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
        if (ev.key === 'Escape' && spawnArmingCharId != null) {
            window.vttCancelSpawnArming();
        }
    });

    canvas.addEventListener('mousemove', (ev) => {
        if (panning) {
            panX = ev.clientX - panning.startX;
            panY = ev.clientY - panning.startY;
            applyTransform();
            return;
        }
        if (!dragging) return;
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
        const id = dragging.token.id;
        fetch(`/api/campaign/${CAMPAIGN_ID}/token/${id}/move`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ x: sx, y: sy }),
        });
        dragging = null;
        canvas.style.cursor = 'grab';
        render();
    });

    // Release pan/drag if mouse button is lifted outside the canvas
    document.addEventListener('mouseup', (ev) => {
        if (ev.button === 2 && panning) {
            panning = null;
            canvas.style.cursor = 'grab';
        }
    });

    canvas.addEventListener('dblclick', (ev) => {
        const [x, y] = clientToCanvas(ev);
        for (let i = tokens.length - 1; i >= 0; i--) {
            const t = tokens[i];
            if (pointInToken(x, y, t) && t.character_id) {
                openSheet(t.character_id);
                return;
            }
        }
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
                        touchDrag = { token: tok, offsetX: wx - tok.x, offsetY: wy - tok.y };
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
                const id = touchDrag.token.id;
                fetch(`/api/campaign/${CAMPAIGN_ID}/token/${id}/move`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ x: sx, y: sy }),
                });
                touchDrag = null;
                render();
                tapStart = null;
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
            if (tapStart && ev.changedTouches.length === 1 && ev.touches.length === 0) {
                const ct = ev.changedTouches[0];
                const moved = Math.hypot(ct.clientX - tapStart.x, ct.clientY - tapStart.y);
                const dt = Date.now() - tapStart.time;
                if (moved < 12 && dt < 350) {
                    const now = Date.now();
                    const dx = ct.clientX - lastTap.x;
                    const dy = ct.clientY - lastTap.y;
                    if (now - lastTap.time < 400 && Math.hypot(dx, dy) < 30) {
                        // Double-tap → mirror dblclick behaviour.
                        const [wx, wy] = clientToCanvasXY(ct.clientX, ct.clientY);
                        for (let i = tokens.length - 1; i >= 0; i--) {
                            const tok = tokens[i];
                            if (pointInToken(wx, wy, tok) && tok.character_id) {
                                openSheet(tok.character_id);
                                break;
                            }
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
            } else if (msg.type === 'spell_cast') {
                appendSpellCast(msg.data);
            } else if (msg.type === 'weapon_attack') {
                appendWeaponAttack(msg.data);
            } else if (msg.type === 'spell_slot_update') {
                // Forwarded as a CustomEvent above; the open mini-sheet listens
                // for it to update its pip row in place.
            } else if (msg.type === 'heal_applied') {
                _onHealApplied(msg.data);
            } else if (msg.type === 'feature_used') {
                _appendFeatureUsed(msg.data);
            } else if (msg.type === 'character_death_save') {
                _onCharacterDeathSave(msg.data);
            } else if (msg.type === 'character_roll_state') {
                _onCharacterRollState(msg.data);
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
            const dispName = r.char_name || USER_CHAR_NAMES[r.user_id] || r.user_name || 'Player';
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
        const dispName  = r.char_name    || USER_CHAR_NAMES[r.user_id] || r.user_name;
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
                        <div class="roll-card-expr">${escapeHTML(r.expression)}</div>
                        <div class="roll-card-breakdown">${formatBreakdown(r.breakdown)}</div>
                    </div>
                </div>
            </div>`;
        ul.appendChild(li);
        _scrollRollLogToBottom();
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
        const actions = (d.actions && d.actions.length) ? d.actions : [_synthesizeCastAction(d)];
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

        const li = document.createElement('li');
        li.dataset.castId = d.id;
        li.innerHTML = `
            <div class="spell-cast-card">
                <div class="roll-card-header">
                    <div class="roll-card-avatar">${avatarInner}</div>
                    <span class="roll-card-user" data-uid="${d.caster_user_id}"${color ? ` style="color:${escapeHTML(color)}"` : ''}>${escapeHTML(dispName)}</span>
                    <span class="spell-cast-slot">${escapeHTML(slotLabel)}</span>
                    <span class="roll-card-time">${timeStr}</span>
                </div>
                <div class="spell-cast-body">
                    <div class="spell-cast-name">🪄 ${escapeHTML(d.spell_name || 'Spell')}</div>
                    ${metaBits.length ? `<div class="spell-cast-meta">${metaBits.join(' · ')}</div>` : ''}
                    ${d.spell_desc ? `<div class="spell-cast-desc">${escapeHTML(d.spell_desc)}</div>` : ''}
                    <div class="spell-cast-actions"></div>
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
                damage: (_action, dmgExpr) => openDamagePicker(d, dmgExpr, li),
                heal:   (_action, btn) => _applyHealing(d, li, btn),
                // attack and toggle handlers are wired through where consumers
                // need them — the spell-cast card itself only uses save/damage/heal.
            },
        }));

        // Stash the cast metadata on the element so the roll listener can
        // correlate save responses back to this card (matches by note prefix).
        li._spellCast = { ...d, _saveLabel: null };
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
    }

    // ---------- Death save broadcast handler (v2.1.0) ----------
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
        const src   = d.source || '';
        const remaining = (d.max && d.max > 0)
            ? `<span style="font-size:11px;color:var(--muted,#888);">(${d.remaining}/${d.max} left)</span>`
            : '';
        const desc = d.feature_desc
            ? `<div style="font-size:11px;color:var(--muted,#888);margin-top:3px;line-height:1.35;">${escapeHTML(d.feature_desc)}</div>`
            : '';
        const li = document.createElement('li');
        li.innerHTML = `
            <div class="roll-card feature-used-card">
                <div class="roll-card-header">
                    <div class="roll-card-avatar">✨</div>
                    <span class="roll-card-user" data-uid="${d.character_id || ''}"${color ? ` style="color:${escapeHTML(color)}"` : ''}>${escapeHTML(name)}</span>
                    <span class="roll-card-time">${hhmm}</span>
                </div>
                <div class="roll-card-body" style="padding:6px 10px 8px;">
                    <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;">
                        <strong style="font-size:13px;">${escapeHTML(feat)}</strong>
                        ${remaining}
                        ${src ? `<span style="font-size:10px;color:var(--muted,#888);">${escapeHTML(src)}</span>` : ''}
                    </div>
                    ${desc}
                </div>
            </div>`;
        ul.appendChild(li);
        _scrollRollLogToBottom();
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

        // Attack roll line (skipped for save-based attacks)
        const atkLineHtml = !d.is_save && d.attack_total != null
            ? `<div class="weapon-atk-line">
                   <span class="weapon-atk-label">🎯 To hit</span>
                   <span class="weapon-atk-total">${d.attack_total}</span>
                   <span class="weapon-atk-breakdown">${formatBreakdown(d.attack_breakdown || '')}</span>
               </div>`
            : '';

        // Damage line (always present if a damage expression was set)
        const dmgLineHtml = d.damage_total != null
            ? `<div class="weapon-atk-line">
                   <span class="weapon-atk-label">💥 Damage</span>
                   <span class="weapon-atk-total">${d.damage_total}${d.damage_type ? ' <span class="weapon-atk-dmgtype">' + escapeHTML(d.damage_type) + '</span>' : ''}</span>
                   <span class="weapon-atk-breakdown">${formatBreakdown(d.damage_breakdown || '')}</span>
               </div>`
            : '';

        const saveBtnHtml = d.is_save
            ? `<button class="spell-cast-btn weapon-atk-save-btn" type="button" title="Prompt all players for a ${escapeHTML(d.save_ability)} save">📋 Prompt ${escapeHTML(d.save_ability)} save (DC ${d.save_dc})</button>`
            : '';

        const li = document.createElement('li');
        li.dataset.attackId = d.id;
        li.innerHTML = `
            <div class="spell-cast-card weapon-atk-card">
                <div class="roll-card-header">
                    <div class="roll-card-avatar">${avatarInner}</div>
                    <span class="roll-card-user" data-uid="${d.caster_user_id}"${color ? ` style="color:${escapeHTML(color)}"` : ''}>${escapeHTML(dispName)}</span>
                    <span class="spell-cast-slot">⚔ Attack</span>
                    <span class="roll-card-time">${timeStr}</span>
                </div>
                <div class="spell-cast-body">
                    <div class="spell-cast-name">🗡 ${escapeHTML(d.attack_name || 'Attack')}</div>
                    ${metaBits.length ? `<div class="spell-cast-meta">${metaBits.join(' · ')}</div>` : ''}
                    ${atkLineHtml}
                    ${dmgLineHtml}
                    ${d.desc ? `<div class="spell-cast-desc">${escapeHTML(d.desc)}</div>` : ''}
                    ${saveBtnHtml ? `<div class="spell-cast-actions">${saveBtnHtml}</div>` : ''}
                    <div class="spell-cast-results"></div>
                </div>
            </div>`;
        ul.appendChild(li);
        _scrollRollLogToBottom();

        const saveBtn = li.querySelector('.weapon-atk-save-btn');
        if (saveBtn) saveBtn.addEventListener('click', () => promptAttackSave(d, li, saveBtn));

        // Stash the attack metadata on the element so the roll listener can
        // correlate save responses back to this card (matches by note prefix).
        li._spellCast = {
            // Reuse the spell-cast save-correlation field name so the existing
            // roll listener appends pass/fail rows here without modification.
            _saveLabel: null,
            spell_save_ability: d.save_ability,
            spell_name: d.attack_name,
        };
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
        if (!resp.ok) showToast('Damage roll failed: ' + await resp.text(), 'error');
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

            // Clear search when tab is opened
            modal.querySelectorAll('.atm-tab-btn').forEach(btn => {
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
            row.innerHTML = `
                ${avatarHtml}
                <span class="tt-name" contenteditable="true" spellcheck="false">${escapeHTML(t.label)}</span>
                <button class="tt-btn tt-vis" title="${t.is_hidden ? 'Show token' : 'Hide token'}">${t.is_hidden ? '🚫' : '👁'}</button>
                <label class="tt-btn tt-art-label" title="Upload art">
                    🖼<input class="tt-art-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif" style="display:none">
                </label>
                <select class="tt-ctrl">
                    <option value="">GM</option>
                    ${memberOpts}
                </select>
                <button class="tt-btn tt-del" title="Delete token">🗑</button>`;
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
})();
