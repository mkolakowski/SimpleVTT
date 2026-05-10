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
    const initialData = JSON.parse(document.getElementById('initial-data').textContent);
    let tokens = initialData.tokens || [];
    const characters = initialData.characters || [];
    const templates = initialData.templates || [];

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

    const _tokenImgCache = {};

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
        if (t.image_url) {
            if (!_tokenImgCache[t.image_url]) {
                const img = new Image();
                img.src = t.image_url;
                img.onload = render;
                _tokenImgCache[t.image_url] = img;
            }
            const img = _tokenImgCache[t.image_url];
            if (img.complete && img.naturalWidth > 0) {
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.clip();
                ctx.drawImage(img, cx - r, cy - r, r * 2, r * 2);
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.lineWidth = 2;
                ctx.strokeStyle = t.color || '#000';
                ctx.stroke();
            } else {
                _drawCircleToken(t, cx, cy, r);
            }
        } else {
            _drawCircleToken(t, cx, cy, r);
        }
        ctx.restore();
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

    // ---------- Pan & zoom ----------
    let scale = 1;
    let panX = 0;
    let panY = 0;
    const MIN_SCALE = 0.15;
    const MAX_SCALE = 5;
    canvas.style.transformOrigin = '0 0';

    function applyTransform() {
        canvas.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
    }

    mapPane.addEventListener('wheel', (ev) => {
        ev.preventDefault();
        const rect = mapPane.getBoundingClientRect();
        const mouseX = ev.clientX - rect.left;
        const mouseY = ev.clientY - rect.top;
        const factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
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

    canvas.addEventListener('mousedown', (ev) => {
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
                renderTokenTracker();
                refreshPlaceButtons();
                render();
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
                <div class="roll-card-header">
                    <div class="roll-card-avatar">${avatarInner}</div>
                    <span class="roll-card-user" data-uid="${r.user_id}"${color ? ` style="color:${escapeHTML(color)}"` : ''}>${escapeHTML(dispName)}</span>
                    ${badgeText ? `<span class="roll-card-badge">${badgeText}</span>` : ''}
                    <span class="roll-card-time">${hhmm}</span>
                </div>
                <div class="roll-card-body">
                    ${r.note ? `<div class="roll-card-note">${escapeHTML(r.note)}</div>` : ''}
                    <span class="roll-card-total">${r.total}</span>
                    <div class="roll-card-breakdown">${formatBreakdown(r.breakdown)}</div>
                </div>
            </div>`;
        ul.prepend(li);
    }

    function appendRollRequest(req) {
        const ul = document.getElementById('roll-list');
        if (!ul) return;

        const now = new Date();
        const h = now.getHours(), m = now.getMinutes();
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12 = (h % 12) || 12;
        const timeStr = h12.toString().padStart(2, '0') + ':' + m.toString().padStart(2, '0') + ' ' + ampm;

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
                    <div class="roll-req-actions">
                        ${charSelectHtml}
                        <button class="roll-req-btn" type="button">🎲 Roll</button>
                        <span class="roll-req-status"></span>
                    </div>
                </div>
            </div>`;

        const rollBtn = li.querySelector('.roll-req-btn');
        rollBtn.addEventListener('click', async () => {
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

        ul.prepend(li);
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

        const damageExpr = _diceExprFromDamage(d.spell_damage || '');
        const saveBtnHtml = d.spell_save_ability
            ? `<button class="spell-cast-btn spell-cast-save-btn" type="button" title="Prompt all players for a ${escapeHTML(d.spell_save_ability)} save">📋 Prompt ${escapeHTML(d.spell_save_ability)} save</button>`
            : '';
        const damageBtnHtml = damageExpr
            ? `<button class="spell-cast-btn spell-cast-dmg-btn" type="button" title="Roll ${escapeHTML(d.spell_damage)}">🎲 Roll damage (${escapeHTML(d.spell_damage)})</button>`
            : '';
        const healExpr = (d.spell_healing || '').trim();
        const aoeTargets = d.spell_aoe_targets || 1;
        const isAoe = aoeTargets > 1;
        const chargeHtml = isAoe
            ? ` <span class="heal-charge-tracker" data-claimed="0" data-max="${aoeTargets}">(0/${aoeTargets})</span>`
            : '';
        const healBtnHtml = healExpr
            ? `<button class="spell-cast-btn spell-cast-heal-btn" type="button"
                   data-cast-id="${escapeHTML(d.id)}" data-aoe="${isAoe ? '1' : '0'}"
                   title="Roll ${escapeHTML(healExpr)} and apply to your character">🩹 Apply Healing (${escapeHTML(healExpr)})${chargeHtml}</button>`
            : '';

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
                    <div class="spell-cast-actions">
                        ${saveBtnHtml}
                        ${damageBtnHtml}
                        ${healBtnHtml}
                    </div>
                    <div class="spell-cast-results"></div>
                </div>
            </div>`;
        ul.prepend(li);

        const saveBtn = li.querySelector('.spell-cast-save-btn');
        if (saveBtn) saveBtn.addEventListener('click', () => promptSpellSave(d, li, saveBtn));

        const dmgBtn = li.querySelector('.spell-cast-dmg-btn');
        if (dmgBtn) dmgBtn.addEventListener('click', () => openDamagePicker(d, damageExpr, li));

        const healBtn = li.querySelector('.spell-cast-heal-btn');
        if (healBtn) healBtn.addEventListener('click', () => _applyHealing(d, li, healBtn));

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
        ul.prepend(li);

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
                        const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/tokens`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ token_template_id: tmpl.id }),
                        });
                        if (!resp.ok) alert('Failed to place token');
                    });
                    grid.appendChild(card);
                });
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
                const resp = await fetch(`/api/campaign/${CAMPAIGN_ID}/tokens`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ label, color, x: 100, y: 100 }),
                });
                if (!resp.ok) alert('Failed to add token');
            });
        }

        // Close modal on backdrop click
        document.getElementById('add-token-modal').addEventListener('click', (ev) => {
            if (ev.target === ev.currentTarget) ev.currentTarget.style.display = 'none';
        });
    }

    // ---------- GM: token tracker ----------

    function buildMiniSheetEl(name, tmpl, sheet) {
        const sh = sheet || {};
        const wrap = document.createElement('div');
        wrap.className = 'mini-sheet';
        wrap.style.padding = '8px 2px';

        if (tmpl === 'dnd5e') {
            const abMap = sh.abilities || {};
            const saveMap = sh.saving_throws || {};
            const skillMap = sh.skills || {};
            const prof = parseInt(sh.proficiency_bonus || 2);
            function abMod(ab) { return Math.floor(((parseInt(abMap[ab] || 10)) - 10) / 2); }
            function fmtM(m) { return (m >= 0 ? '+' : '') + m; }

            // Tags
            const tags = [sh['class'], sh.level ? `Lv ${sh.level}` : null, sh.race].filter(Boolean);
            if (tags.length) {
                const tagRow = document.createElement('div');
                tagRow.className = 'mini-tags';
                tags.forEach(tag => {
                    const s = document.createElement('span');
                    s.className = 'mini-tag';
                    s.textContent = tag;
                    tagRow.appendChild(s);
                });
                wrap.appendChild(tagRow);
            }

            // Combat stats
            const statsGrid = document.createElement('div');
            statsGrid.className = 'mini-grid-3';
            const hp = sh.hp || {};
            [
                ['HP', `${hp.current ?? '—'}/${hp.max ?? '—'}`],
                ['AC', sh.ac ?? '—'],
                ['Speed', sh.speed ? sh.speed + 'ft' : '—'],
            ].forEach(([lbl, val]) => {
                const cell = document.createElement('div');
                cell.className = 'mini-cell';
                cell.innerHTML = `<span class="mc-label">${escapeHTML(lbl)}</span><span class="mc-value">${escapeHTML(String(val))}</span>`;
                statsGrid.appendChild(cell);
            });
            wrap.appendChild(statsGrid);

            // Abilities
            const abLbl = document.createElement('div');
            abLbl.className = 'mini-section-label';
            abLbl.textContent = 'Abilities & Saves';
            wrap.appendChild(abLbl);
            const abGrid = document.createElement('div');
            abGrid.className = 'mini-ab-grid';
            const ABS = ['STR','DEX','CON','INT','WIS','CHA'];
            // Row 1: names
            ABS.forEach(ab => {
                const isP = saveMap[ab];
                const el = document.createElement('span');
                el.className = 'mac-name' + (isP ? ' mac-name-prof' : '');
                el.textContent = ab;
                abGrid.appendChild(el);
            });
            // Row 2: scores
            ABS.forEach(ab => {
                const el = document.createElement('span');
                el.className = 'mac-score';
                el.textContent = abMap[ab] ?? 10;
                abGrid.appendChild(el);
            });
            // Row 3: modifiers
            ABS.forEach(ab => {
                const el = document.createElement('span');
                el.className = 'mac-mod';
                el.textContent = fmtM(abMod(ab));
                abGrid.appendChild(el);
            });
            // Row 4: Check label + buttons
            const ckLbl = document.createElement('span');
            ckLbl.className = 'mac-row-label';
            ckLbl.textContent = 'Check';
            abGrid.appendChild(ckLbl);
            ABS.forEach(ab => {
                const m = abMod(ab);
                const btn = document.createElement('button');
                btn.className = 'mini-roll-btn mac-btn';
                btn.dataset.expr = `1d20${fmtM(m)}`;
                btn.dataset.note = `${ab} check`;
                btn.textContent = '🎲';
                abGrid.appendChild(btn);
            });
            // Row 5: Save label + buttons
            const svLbl = document.createElement('span');
            svLbl.className = 'mac-row-label';
            svLbl.textContent = 'Save';
            abGrid.appendChild(svLbl);
            ABS.forEach(ab => {
                const m = abMod(ab);
                const isP = saveMap[ab];
                const sv = m + (isP ? prof : 0);
                const btn = document.createElement('button');
                btn.className = 'mini-roll-btn mac-btn';
                btn.dataset.expr = `1d20${fmtM(sv)}`;
                btn.dataset.note = `${ab} save${isP ? ' (prof)' : ''}`;
                btn.textContent = '🎲';
                abGrid.appendChild(btn);
            });
            wrap.appendChild(abGrid);

            // Skills
            const sklLbl = document.createElement('div');
            sklLbl.className = 'mini-section-label';
            sklLbl.style.marginTop = '10px';
            sklLbl.textContent = 'Skills';
            wrap.appendChild(sklLbl);
            const sklGrid = document.createElement('div');
            sklGrid.className = 'mini-skills-grid';
            [
                ['Acrobatics','DEX'],['Animal Handling','WIS'],['Arcana','INT'],
                ['Athletics','STR'],['Deception','CHA'],['History','INT'],
                ['Insight','WIS'],['Intimidation','CHA'],['Investigation','INT'],
                ['Medicine','WIS'],['Nature','INT'],['Perception','WIS'],
                ['Performance','CHA'],['Persuasion','CHA'],['Religion','INT'],
                ['Sleight of Hand','DEX'],['Stealth','DEX'],['Survival','WIS'],
            ].forEach(([sname, sab]) => {
                const sMod = abMod(sab);
                const sk = skillMap[sname] || {};
                const isExp = sk.expertise;
                const isProf = sk.proficient;
                const bonus = sMod + (isExp ? prof*2 : isProf ? prof : 0);
                const row = document.createElement('div');
                row.className = 'mini-roll-row';
                const nameEl = document.createElement('span');
                nameEl.className = `mini-skill-name${isExp ? ' is-exp' : isProf ? ' is-prof' : ''}`;
                nameEl.textContent = sname;
                const abEl = document.createElement('span');
                abEl.className = 'mini-skill-ab';
                abEl.textContent = sab;
                const btn = document.createElement('button');
                btn.className = 'mini-roll-btn';
                btn.dataset.expr = `1d20${fmtM(bonus)}`;
                btn.dataset.note = `${sname}${isExp ? ' (expertise)' : isProf ? ' (prof)' : ''}`;
                btn.textContent = `🎲 ${fmtM(bonus)}`;
                row.append(nameEl, abEl, btn);
                sklGrid.appendChild(row);
            });
            wrap.appendChild(sklGrid);

        } else {
            // Generic sheet
            if (sh.summary) {
                const p = document.createElement('p');
                p.className = 'mini-summary';
                p.textContent = String(sh.summary).slice(0, 200);
                wrap.appendChild(p);
            }
            if (sh.stats && Object.keys(sh.stats).length) {
                const kv = document.createElement('div');
                kv.className = 'mini-kv';
                Object.entries(sh.stats).forEach(([k, v]) => {
                    const pair = document.createElement('span');
                    pair.className = 'mini-kv-pair';
                    pair.innerHTML = `<span class="mk">${escapeHTML(k)}</span>${escapeHTML(String(v))}`;
                    kv.appendChild(pair);
                });
                wrap.appendChild(kv);
            }
            if (!sh.summary && (!sh.stats || !Object.keys(sh.stats).length)) {
                const p = document.createElement('p');
                p.className = 'no-chars-msg';
                p.textContent = 'No sheet data yet.';
                wrap.appendChild(p);
            }
        }

        // Wire roll buttons (public roll by default; respects roll-vis selector)
        wrap.querySelectorAll('.mini-roll-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const expr = btn.dataset.expr;
                if (!expr) return;
                const note = `${name}: ${btn.dataset.note || ''}`;
                const visEl = document.getElementById('roll-vis');
                const visibility = visEl ? visEl.value : 'public';
                btn.disabled = true;
                try {
                    await fetch(`/api/campaign/${CAMPAIGN_ID}/roll`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ expression: expr, visibility, note }),
                    });
                } finally { btn.disabled = false; }
            });
        });

        return wrap;
    }

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
        tokens.forEach(t => {
            const row = document.createElement('div');
            row.className = 'tt-row';
            row.dataset.id = t.id;
            const memberOpts = (typeof MEMBERS !== 'undefined' ? MEMBERS : [])
                .map(m => `<option value="${m.id}"${t.controller_user_id === m.id ? ' selected' : ''}>${escapeHTML(m.name)}</option>`)
                .join('');
            row.innerHTML = `
                <span class="tt-swatch" style="background:${escapeHTML(t.color || '#cc3333')}"></span>
                <span class="tt-name" contenteditable="true" spellcheck="false">${escapeHTML(t.label)}</span>
                <button class="tt-btn tt-vis" title="${t.is_hidden ? 'Show token' : 'Hide token'}">${t.is_hidden ? '🚫' : '👁'}</button>
                <label class="tt-btn tt-art-label" title="Upload art">
                    🖼<input class="tt-art-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif" style="display:none">
                </label>
                <select class="tt-ctrl">
                    <option value="">No controller</option>
                    ${memberOpts}
                </select>
                <button class="tt-btn tt-sheet" title="Show sheet">📋</button>
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

            // Mini-sheet expand
            const sheetBtn = row.querySelector('.tt-sheet');
            if (sheetBtn) {
                const sheetRow = document.createElement('div');
                sheetRow.style.cssText = 'display:none; padding:0 10px 10px; border-bottom:1px solid #2a2d3a;';
                row.after(sheetRow);
                sheetBtn.addEventListener('click', () => {
                    const isOpen = sheetRow.style.display !== 'none';
                    if (isOpen) {
                        sheetRow.style.display = 'none';
                    } else {
                        if (!sheetRow.children.length) {
                            // Build the mini-sheet
                            let sheetData = null;
                            if (t.character_id) {
                                const c = characters.find(c => c.id === t.character_id);
                                if (c) sheetData = { name: c.name, template: c.template, sheet: c.sheet };
                            } else if (t.token_template_id) {
                                const tmpl = templates.find(tmpl => tmpl.id === t.token_template_id);
                                if (tmpl) sheetData = { name: tmpl.name, template: tmpl.template, sheet: tmpl.sheet };
                            }
                            if (sheetData) {
                                sheetRow.appendChild(buildMiniSheetEl(sheetData.name, sheetData.template, sheetData.sheet));
                            } else {
                                const p = document.createElement('p');
                                p.className = 'no-chars-msg';
                                p.textContent = 'No sheet data for this token.';
                                sheetRow.appendChild(p);
                            }
                        }
                        sheetRow.style.display = '';
                    }
                });
            }
        });
    }

    renderTokenTracker();

    // ---------- Player: place/remove character token buttons ----------
    function charTokenOnMap(charId) {
        return tokens.find(t => t.character_id === charId) || null;
    }

    function canPlaceChar(charId) {
        if (ME.isGm) return true;
        const c = characters.find(c => c.id === charId);
        return c && c.owner_user_id === ME.id;
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
                        const resp = await fetch(url, {
                            method: existing ? 'DELETE' : 'POST',
                            headers: { 'Content-Type': 'application/json' },
                        });
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

    // ---------- Sheet modal ----------
    let _sheetJs = null;   // cached text of sheet.js so we only fetch it once

    window.openSheet = async function (charId) {
        const [sheetResp] = await Promise.all([
            fetch(`/api/campaign/${CAMPAIGN_ID}/character/${charId}`),
        ]);
        if (!sheetResp.ok) { alert('Could not load character'); return; }
        const html = await sheetResp.text();

        // Strip <script> tags before injecting — innerHTML never executes them
        // and createContextualFragment behavior for external src varies by browser.
        const doc = new DOMParser().parseFromString(html, 'text/html');
        doc.querySelectorAll('script').forEach(s => s.remove());

        const root = document.getElementById('modal-root');
        root.innerHTML = '<div class="modal-bg"><div class="modal"></div></div>';
        root.firstChild.onclick = (ev) => { if (ev.target === ev.currentTarget) closeSheet(); };
        root.querySelector('.modal').innerHTML = doc.body.innerHTML;

        // Explicitly fetch and run sheet.js so the form is always bound.
        // We use a real <script> element rather than new Function() because
        // new Function() only sees window properties, not const/let top-level
        // bindings (e.g. CAMPAIGN_ID) that live in the declarative record.
        if (!_sheetJs) _sheetJs = await fetch('/static/sheet.js').then(r => r.text());
        const _s = document.createElement('script');
        _s.textContent = _sheetJs;
        document.head.appendChild(_s);
        _s.remove();
    };
    window.closeSheet = function () {
        document.getElementById('modal-root').innerHTML = '';
    };
})();
