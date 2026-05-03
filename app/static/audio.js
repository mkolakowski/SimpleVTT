/* SimpleVTT audio client.
 *
 * Handles three things:
 *  1. Master volume + mute (localStorage; per-browser).
 *  2. Per-track volume override (server-side; loaded once on connect).
 *     Effective playback volume = master * (perTrackOverride ?? 1).
 *  3. Time-sync: every audio_play broadcast carries `started_at_ms` (UTC
 *     epoch from the server). On receipt, we compute elapsed seconds and
 *     seek the <audio> element to match so all clients hear the same
 *     position. A small drift correction kicks in if a client falls more
 *     than DRIFT_THRESHOLD_S out of sync (e.g., after tab throttling).
 *
 * Listens for `vtt:ws-message` CustomEvents dispatched by tabletop.js.
 */
(function () {
    'use strict';

    const root = document.getElementById('audio-panel');
    if (!root) return;

    const audioEl = document.createElement('audio');
    audioEl.id = 'vtt-audio';
    audioEl.preload = 'auto';
    audioEl.style.display = 'none';
    document.body.appendChild(audioEl);

    const nowPlayingEl = document.getElementById('audio-now-playing');
    const volSlider    = document.getElementById('audio-volume');
    const muteBtn      = document.getElementById('audio-mute');
    const enableBtn    = document.getElementById('audio-enable');
    const trackVolWrap = document.getElementById('audio-track-volume');
    const trackVolSld  = document.getElementById('audio-track-volume-slider');
    const trackVolNum  = document.getElementById('audio-track-volume-num');

    // ---- master volume + mute (localStorage) ----
    const VOL_KEY = 'simplevtt.audio.volume';
    const MUTE_KEY = 'simplevtt.audio.muted';
    function loadMasterVol() {
        const v = parseFloat(localStorage.getItem(VOL_KEY));
        return Number.isFinite(v) && v >= 0 && v <= 1 ? v : 0.6;
    }
    function loadMute() { return localStorage.getItem(MUTE_KEY) === '1'; }

    let masterVol = loadMasterVol();
    audioEl.muted = loadMute();
    if (volSlider) volSlider.value = String(masterVol);
    if (muteBtn) muteBtn.textContent = audioEl.muted ? '🔇 Unmute' : '🔈 Mute';

    // ---- per-track volume preferences (server-side) ----
    // Map of trackId (string) -> volume (0..1). Loaded once on init.
    let perTrackVol = {};
    fetch('/api/audio/preferences', { credentials: 'same-origin' })
        .then(r => r.ok ? r.json() : {})
        .then(json => { perTrackVol = json || {}; applyEffectiveVolume(); })
        .catch(() => {});

    let currentTrackId = null;
    let currentDuration = 0;       // for capping seek values
    let suppressSavingPerTrack = false;

    function effectiveTrackVol() {
        if (currentTrackId == null) return 1;
        const v = perTrackVol[String(currentTrackId)];
        return (typeof v === 'number') ? v : 1;
    }
    function applyEffectiveVolume() {
        audioEl.volume = Math.max(0, Math.min(1, masterVol * effectiveTrackVol()));
    }

    if (volSlider) {
        volSlider.addEventListener('input', () => {
            masterVol = parseFloat(volSlider.value);
            localStorage.setItem(VOL_KEY, String(masterVol));
            if (masterVol === 0 && !audioEl.muted) {
                audioEl.muted = true;
                localStorage.setItem(MUTE_KEY, '1');
                if (muteBtn) muteBtn.textContent = '🔇 Unmute';
            } else if (masterVol > 0 && audioEl.muted) {
                audioEl.muted = false;
                localStorage.setItem(MUTE_KEY, '0');
                if (muteBtn) muteBtn.textContent = '🔈 Mute';
            }
            applyEffectiveVolume();
        });
    }
    if (muteBtn) {
        muteBtn.addEventListener('click', () => {
            audioEl.muted = !audioEl.muted;
            localStorage.setItem(MUTE_KEY, audioEl.muted ? '1' : '0');
            muteBtn.textContent = audioEl.muted ? '🔇 Unmute' : '🔈 Mute';
        });
    }

    // ---- per-track slider in the tabletop panel ----
    let savePerTrackTimer = null;
    function debouncedSavePerTrack(trackId, volume) {
        if (suppressSavingPerTrack) return;
        clearTimeout(savePerTrackTimer);
        savePerTrackTimer = setTimeout(async () => {
            try {
                await fetch(`/api/audio/preferences/${trackId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({ volume }),
                });
            } catch (e) { console.warn('save per-track vol failed', e); }
        }, 350);
    }
    if (trackVolSld) {
        trackVolSld.addEventListener('input', () => {
            if (currentTrackId == null) return;
            const v = parseFloat(trackVolSld.value);
            perTrackVol[String(currentTrackId)] = v;
            if (trackVolNum) trackVolNum.textContent = Math.round(v * 100) + '%';
            applyEffectiveVolume();
            debouncedSavePerTrack(currentTrackId, v);
        });
    }
    function refreshTrackVolUI() {
        if (!trackVolWrap) return;
        if (currentTrackId == null) {
            trackVolWrap.style.display = 'none';
            return;
        }
        trackVolWrap.style.display = '';
        const v = effectiveTrackVol();
        suppressSavingPerTrack = true;
        if (trackVolSld) trackVolSld.value = String(v);
        suppressSavingPerTrack = false;
        if (trackVolNum) trackVolNum.textContent = Math.round(v * 100) + '%';
    }

    // ---- now-playing label ----
    function setNowPlaying(name) {
        if (!nowPlayingEl) return;
        nowPlayingEl.textContent = name || 'Nothing playing';
    }

    // ---- autoplay-blocked helper ----
    function tryPlay() {
        const p = audioEl.play();
        if (p && typeof p.then === 'function') {
            p.catch((err) => {
                if (enableBtn) enableBtn.style.display = '';
                console.warn('audio play blocked until user gesture:', err);
            });
        }
    }
    if (enableBtn) {
        enableBtn.style.display = 'none';
        enableBtn.addEventListener('click', () => {
            tryPlay();
            enableBtn.style.display = 'none';
        });
    }

    // ---- time sync ----
    const DRIFT_THRESHOLD_S = 0.75;   // resync if we drift more than this
    let serverStartedAtMs = null;     // canonical server timestamp

    function expectedPositionSeconds() {
        if (serverStartedAtMs == null) return 0;
        return Math.max(0, (Date.now() - serverStartedAtMs) / 1000);
    }
    function seekToExpected() {
        const target = expectedPositionSeconds();
        if (currentDuration && target > currentDuration) {
            // We joined after the track would have ended (no looping at the
            // <audio> level; the playlist loop is handled server-side).
            // Most tracks loop from the server's perspective only when the
            // playlist's last track ends. Just seek to the modulo position
            // if duration is known and small enough that wrapping makes sense
            // (e.g., a 2-min ambient loop). Otherwise seek to end and let
            // the 'ended' handler ask for /audio/next.
            if (currentDuration > 0) {
                audioEl.currentTime = target % currentDuration;
            }
        } else {
            audioEl.currentTime = target;
        }
    }
    audioEl.addEventListener('loadedmetadata', () => {
        currentDuration = audioEl.duration || 0;
        seekToExpected();
        tryPlay();
    });
    // Drift correction: every 5s, if we're more than DRIFT_THRESHOLD_S off,
    // gently snap back. We avoid doing this on every tick because seeking
    // causes audible glitches.
    setInterval(() => {
        if (!currentTrackId || serverStartedAtMs == null) return;
        if (audioEl.paused || !audioEl.duration) return;
        const expected = expectedPositionSeconds() % audioEl.duration;
        const drift = Math.abs(expected - audioEl.currentTime);
        // Accept full-cycle wrap-around (drift close to duration is actually 0).
        const wrappedDrift = Math.min(drift, Math.abs(drift - audioEl.duration));
        if (wrappedDrift > DRIFT_THRESHOLD_S) {
            audioEl.currentTime = expected;
        }
    }, 5000);

    // ---- WS event handling ----
    function handleMessage(msg) {
        if (msg.type === 'audio_play') {
            const d = msg.data || {};
            currentTrackId = d.track_id;
            serverStartedAtMs = d.started_at_ms || Date.now();
            currentDuration = 0;
            audioEl.src = d.file_url;
            setNowPlaying(`▶ ${d.name || ''}`);
            refreshTrackVolUI();
            applyEffectiveVolume();
            // playback + seek happens in 'loadedmetadata'
        } else if (msg.type === 'audio_stop') {
            currentTrackId = null;
            serverStartedAtMs = null;
            audioEl.pause();
            audioEl.removeAttribute('src');
            audioEl.load();
            setNowPlaying('Nothing playing');
            refreshTrackVolUI();
        }
    }
    document.addEventListener('vtt:ws-message', (ev) => handleMessage(ev.detail));

    // ---- track-end: ask server to advance ----
    audioEl.addEventListener('ended', async () => {
        if (!currentTrackId || typeof CAMPAIGN_ID === 'undefined') return;
        try {
            await fetch(`/campaign/${CAMPAIGN_ID}/audio/next`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ track_id: currentTrackId }),
            });
        } catch (e) { console.warn('audio_next failed', e); }
    });

    // ---- Initial state from the server-rendered "now playing" ----
    const initial = root.dataset.initialPlay;
    if (initial) {
        try {
            const d = JSON.parse(initial);
            if (d && d.file_url) {
                handleMessage({ type: 'audio_play', data: d });
            }
        } catch (e) { /* ignore */ }
    }

    // ---- GM helpers ----
    window.vttPlayTrack = async function (trackId) {
        if (typeof CAMPAIGN_ID === 'undefined') return;
        const resp = await fetch(`/campaign/${CAMPAIGN_ID}/audio/play`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ track_id: trackId }),
        });
        if (!resp.ok) alert('Could not start track: ' + (await resp.text()));
    };
    window.vttStopAudio = async function () {
        if (typeof CAMPAIGN_ID === 'undefined') return;
        await fetch(`/campaign/${CAMPAIGN_ID}/audio/stop`, {
            method: 'POST', credentials: 'same-origin',
        });
    };
    window.vttResyncAudio = async function () {
        if (typeof CAMPAIGN_ID === 'undefined') return;
        await fetch(`/campaign/${CAMPAIGN_ID}/audio/resync`, {
            method: 'POST', credentials: 'same-origin',
        });
    };
})();
