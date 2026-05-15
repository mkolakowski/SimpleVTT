/* Shared roll-result popup (1.11.0).
 *
 * Lifted out of tabletop.html so character-sheet pages get the same
 * animated dice-shape popup the tabletop already uses. Renders inside
 * #roll-toast-container — auto-created on the body if missing so pages
 * that don't ship the container element still work. CSS lives in
 * app/static/style.css.
 *
 * Two entry points:
 *
 *   1. document.addEventListener('vtt:ws-message', …)  — broadcast-driven.
 *      The tabletop's WebSocket handler dispatches a CustomEvent with
 *      ``{type: 'roll', data: <roll record>}``; the listener below
 *      filters by visibility and fires the popup. This is the legacy
 *      tabletop behaviour and is unchanged.
 *
 *   2. window.showRollToast(rollData) — direct call.
 *      Use when local code already has the roll record (e.g. a sheet
 *      action button just POSTed to /api/campaign/{id}/roll and got the
 *      breakdown back) and wants to surface the popup without going
 *      through WebSocket. The shape mirrors the broadcast payload:
 *        { visibility, user_id, user_name, char_name, expression,
 *          total, breakdown, note }
 *      Any field except `expression`, `total`, `breakdown` is optional;
 *      defaults fill in for the missing ones.
 */
(function () {
    'use strict';

    function _ensureContainer() {
        let container = document.getElementById('roll-toast-container');
        if (container) return container;
        container = document.createElement('div');
        container.id = 'roll-toast-container';
        document.body.appendChild(container);
        return container;
    }

    /* SVG inner markup for each die face.
       d4 is INVERTED (flat top, point bottom) — visually distinct from d20
       (point top, flat bottom). No inner lines on d8 — the horizontal line
       would cross the number. */
    const DIE_SHAPES = {
        4:   `<polygon points="7,8 93,8 50,92" fill="none" stroke="currentColor" stroke-width="8" stroke-linejoin="round"/>`,
        6:   `<rect x="10" y="10" width="80" height="80" rx="12" fill="none" stroke="currentColor" stroke-width="8"/>`,
        8:   `<polygon points="50,8 92,50 50,92 8,50" fill="none" stroke="currentColor" stroke-width="8" stroke-linejoin="round"/>`,
        10:  `<polygon points="50,6 88,36 74,90 26,90 12,36" fill="none" stroke="currentColor" stroke-width="8" stroke-linejoin="round"/>`,
        12:  `<polygon points="50,8 88,33 76,77 24,77 12,33" fill="none" stroke="currentColor" stroke-width="8" stroke-linejoin="round"/>`,
        20:  `<polygon points="50,7 93,28.5 93,71.5 50,93 7,71.5 7,28.5" fill="none" stroke="currentColor" stroke-width="8" stroke-linejoin="round"/><polygon points="50,7 93,71.5 7,71.5" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" opacity="0.45"/><polygon points="93,28.5 50,93 7,28.5" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round" opacity="0.45"/>`,
        100: `<circle cx="50" cy="50" r="43" fill="none" stroke="currentColor" stroke-width="8"/><circle cx="50" cy="50" r="28" fill="none" stroke="currentColor" stroke-width="3" opacity="0.35"/>`,
    };

    function _makeDie(sides, size) {
        const NS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('class', 'rt-die');
        svg.setAttribute('width', size);
        svg.setAttribute('height', size);
        svg.setAttribute('viewBox', '0 0 100 100');
        svg.setAttribute('aria-hidden', 'true');
        svg.innerHTML = DIE_SHAPES[sides] || DIE_SHAPES[6];

        const t = document.createElementNS(NS, 'text');
        t.setAttribute('x', '50');
        /* d4 is inverted (flat top, point bottom) — centroid in upper third.
           d20 is upright (point top, flat bottom) — centroid in lower third. */
        t.setAttribute('y', sides === 4 ? '38' : '54');
        t.setAttribute('text-anchor', 'middle');
        t.setAttribute('dominant-baseline', 'middle');
        t.setAttribute('fill', 'currentColor');
        t.setAttribute('font-size', sides >= 100 ? '26' : sides >= 20 ? '34' : '40');
        t.setAttribute('font-weight', '800');
        svg.appendChild(t);
        return { svg, t };
    }

    /* Parse individual die values out of the breakdown string.
       Format: "2d6[3,5]=8 +1d4[2]=2  =>  10" → [3, 5, 2] */
    function _parseDieVals(breakdown) {
        const out = [];
        const re = /\[([^\]]+)\]/g;
        let m;
        while ((m = re.exec(String(breakdown))) !== null) {
            m[1].split(',').forEach(v => { const n = parseInt(v); if (!isNaN(n)) out.push(n); });
        }
        return out;
    }

    function _dismiss(toast) {
        if (toast.dataset.gone) return;
        toast.dataset.gone = '1';
        clearTimeout(toast._timer);
        toast.classList.add('rt-out');
        setTimeout(() => toast.remove(), 370);
    }

    function _meId() {
        return (typeof window !== 'undefined' && window.ME && window.ME.id) || null;
    }

    function showRollToast(r) {
        if (!r || !r.expression) return;
        const container = _ensureContainer();
        const myId = _meId();

        const toast = document.createElement('div');
        toast.className = 'roll-toast rt-animating';
        toast.title = 'Click to dismiss';

        const lbl = document.createElement('div');
        lbl.className = 'rt-label';
        const roller = r.char_name || r.user_name || 'You';
        lbl.textContent = (r.user_id != null && myId != null && r.user_id === myId)
            ? '🎲 ' + (r.note || r.expression)
            : (r.user_id == null
                ? '🎲 ' + (r.note || r.expression)
                : '🎲 ' + roller + ' — ' + (r.note || r.expression));

        /* Build one die element per die in the expression (max 6).
           Count is optional — "d20" treated as "1d20". */
        const MAX_DICE = 6;
        const sides = [];
        for (const m of String(r.expression).matchAll(/(\d*)d(\d+)/gi)) {
            const cnt = parseInt(m[1]) || 1;
            for (let i = 0; i < cnt && sides.length < MAX_DICE; i++) sides.push(parseInt(m[2]));
        }
        if (!sides.length) sides.push(6);

        const n    = sides.length;
        const sz   = n === 1 ? 82 : n <= 3 ? 60 : n <= 5 ? 46 : 38;
        const dies = sides.map(s => _makeDie(s, sz));

        const diceRow = document.createElement('div');
        diceRow.className = 'rt-dice';
        dies.forEach(d => diceRow.appendChild(d.svg));

        /* Sum line shown below the dice for multi-die rolls */
        const sumEl = n > 1
            ? Object.assign(document.createElement('div'), { className: 'rt-sum' })
            : null;

        toast.append(lbl, diceRow);
        if (sumEl) toast.appendChild(sumEl);
        toast.addEventListener('click', () => _dismiss(toast));
        container.appendChild(toast);

        /* Ease-out animation: each die independently cycles 1–sides */
        const delays = [50, 55, 60, 75, 100, 150, 220, 320, 430];
        let di = 0;
        function tick() {
            if (di < delays.length) {
                dies.forEach((d, i) => { d.t.textContent = Math.floor(Math.random() * sides[i]) + 1; });
                setTimeout(tick, delays[di++]);
            } else {
                toast.classList.remove('rt-animating');
                if (n === 1) {
                    /* Single die: show total directly (handles advantage/kh/kl correctly) */
                    dies[0].t.textContent = r.total;
                    dies[0].svg.classList.add('rt-die-landed');
                } else {
                    /* Multi-die: show per-die results parsed from breakdown */
                    const vals = _parseDieVals(r.breakdown);
                    dies.forEach((d, i) => { d.t.textContent = vals[i] != null ? vals[i] : '?'; });
                    sumEl.textContent = '= ' + r.total;
                    sumEl.classList.add('rt-landed');
                }

                const bkd = document.createElement('div');
                bkd.className = 'rt-breakdown';
                bkd.textContent = r.breakdown;

                const hint = document.createElement('div');
                hint.className = 'rt-dismiss';
                hint.textContent = 'click to dismiss';

                toast.append(bkd, hint);
                toast._timer = setTimeout(() => _dismiss(toast), 10000);
            }
        }
        tick();
    }
    window.showRollToast = showRollToast;

    /* Legacy tabletop behaviour: the WS handler in tabletop.js dispatches a
       `vtt:ws-message` CustomEvent on every incoming message; we filter to
       the `roll` type and fire the popup with the visibility checks the
       tabletop has always done. Sheets don't have a WS connection so this
       listener is a no-op there — they call window.showRollToast directly. */
    document.addEventListener('vtt:ws-message', (ev) => {
        const msg = ev.detail;
        if (!msg || msg.type !== 'roll') return;
        const r = msg.data;
        if (!r) return;
        const isGm = !!(window.ME && window.ME.isGm);
        const myId = _meId();
        if (r.visibility === 'gm_only' && !isGm) return;
        if (r.visibility === 'gm_and_roller' && !isGm && r.user_id !== myId) return;
        showRollToast(r);
    });
})();
