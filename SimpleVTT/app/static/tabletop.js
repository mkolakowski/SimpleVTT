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

    const ctx = canvas.getContext('2d');
    const initialData = JSON.parse(document.getElementById('initial-data').textContent);
    let tokens = initialData.tokens || [];
    const characters = initialData.characters || [];

    const gridType = canvas.dataset.gridType || 'square';
    const gridSize = parseInt(canvas.dataset.gridSize || '70', 10);
    const bgUrl = canvas.dataset.bg;
    let bgImg = null;
    if (bgUrl) {
        bgImg = new Image();
        bgImg.onload = render;
        bgImg.src = bgUrl;
    }

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
        for (let x = 0; x < canvas.width; x += gridSize) {
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
        }
        for (let y = 0; y < canvas.height; y += gridSize) {
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
        }
    }

    function drawHexGrid() {
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.lineWidth = 1;
        const { w, h } = hexDims();
        const rowH = h * 0.75;
        const cols = Math.ceil(canvas.width / w) + 1;
        const rows = Math.ceil(canvas.height / rowH) + 1;
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

    function drawToken(t) {
        const radius = (gridSize * t.size) / 2 - 4;
        ctx.beginPath();
        ctx.arc(t.x + gridSize / 2, t.y + gridSize / 2, radius, 0, Math.PI * 2);
        ctx.fillStyle = t.color || '#cc3333';
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = '#000';
        ctx.stroke();
        // Label
        ctx.fillStyle = '#fff';
        ctx.font = '12px system-ui';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText((t.label || '').slice(0, 12), t.x + gridSize / 2, t.y + gridSize / 2);
    }

    function render() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (bgImg && bgImg.complete) {
            ctx.drawImage(bgImg, 0, 0, canvas.width, canvas.height);
        } else {
            ctx.fillStyle = '#222';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }
        if (gridType === 'square') drawSquareGrid();
        else if (gridType === 'hex') drawHexGrid();
        tokens.forEach(drawToken);
    }
    render();

    // ---------- Drag handling ----------
    let dragging = null;     // { token, offsetX, offsetY }

    function pointInToken(x, y, t) {
        const cx = t.x + gridSize / 2, cy = t.y + gridSize / 2;
        const r = (gridSize * t.size) / 2 - 4;
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r;
    }

    function canMove(t) {
        if (ME.isGm) return true;
        if (!t.character_id) return false;
        const c = characters.find(c => c.id === t.character_id);
        return c && c.owner_user_id === ME.id;
    }

    function clientToCanvas(ev) {
        const rect = canvas.getBoundingClientRect();
        const sx = canvas.width / rect.width;
        const sy = canvas.height / rect.height;
        return [(ev.clientX - rect.left) * sx, (ev.clientY - rect.top) * sy];
    }

    canvas.addEventListener('mousedown', (ev) => {
        const [x, y] = clientToCanvas(ev);
        // Iterate top-to-bottom (last drawn first)
        for (let i = tokens.length - 1; i >= 0; i--) {
            const t = tokens[i];
            if (pointInToken(x, y, t) && canMove(t)) {
                dragging = { token: t, offsetX: x - t.x, offsetY: y - t.y };
                canvas.style.cursor = 'grabbing';
                return;
            }
        }
    });

    canvas.addEventListener('mousemove', (ev) => {
        if (!dragging) return;
        const [x, y] = clientToCanvas(ev);
        dragging.token.x = x - dragging.offsetX;
        dragging.token.y = y - dragging.offsetY;
        render();
    });

    canvas.addEventListener('mouseup', () => {
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
            if (msg.type === 'token_move') {
                const t = tokens.find(t => t.id === msg.data.id);
                if (t) { t.x = msg.data.x; t.y = msg.data.y; render(); }
            } else if (msg.type === 'token_add') {
                tokens.push(msg.data);
                render();
            } else if (msg.type === 'token_delete') {
                tokens = tokens.filter(t => t.id !== msg.data.id);
                render();
            } else if (msg.type === 'roll') {
                appendRoll(msg.data);
            }
        };
        ws.onclose = () => setTimeout(connectWs, 2000);
    }
    connectWs();

    function appendRoll(r) {
        // Re-apply visibility filter on the client (server already does this
        // for non-broadcast targets but every client receives the same payload).
        if (!ME.isGm) {
            if (r.visibility === 'gm_only') return;
            if (r.visibility === 'gm_and_roller' && r.user_id !== ME.id) return;
        }
        const ul = document.getElementById('roll-list');
        const li = document.createElement('li');
        li.innerHTML = `<strong>${escapeHTML(r.user_name)}</strong>: ${escapeHTML(r.expression)} = <strong>${r.total}</strong>
            <div class="muted">${escapeHTML(r.breakdown)}</div>
            <span class="roll-vis">${r.visibility}${r.note ? ' • ' + escapeHTML(r.note) : ''}</span>`;
        ul.prepend(li);
    }

    function escapeHTML(s) {
        return String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
    }

    // ---------- Dice form ----------
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
            document.getElementById('roll-expr').value = btn.dataset.expr;
            document.getElementById('roll-form').dispatchEvent(new Event('submit', { cancelable: true }));
        });
    });

    // ---------- GM: add token button ----------
    const addBtn = document.getElementById('add-token-btn');
    if (addBtn) {
        addBtn.addEventListener('click', async () => {
            const label = prompt('Token label?', 'Token');
            if (label === null) return;
            const charIdStr = prompt('Character ID to link (blank for unlinked):', '');
            const charId = charIdStr ? parseInt(charIdStr, 10) : null;
            const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/tokens`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label, character_id: charId, x: 100, y: 100 }),
            });
            if (!resp.ok) alert('Failed to add token');
            // Token appears via WS broadcast.
        });
    }

    // ---------- Sheet modal ----------
    window.openSheet = async function (charId) {
        const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/character/${charId}`);
        if (!resp.ok) { alert('Could not load character'); return; }
        const html = await resp.text();
        const root = document.getElementById('modal-root');
        root.innerHTML = `<div class="modal-bg" onclick="if(event.target===this)closeSheet()"><div class="modal">${html}</div></div>`;
        // The injected fragment contains <script src="/static/sheet.js"> which
        // will re-bind the sheet form on load.
    };
    window.closeSheet = function () {
        document.getElementById('modal-root').innerHTML = '';
    };
})();
