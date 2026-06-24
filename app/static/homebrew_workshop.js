/* Homebrew Workshop — docs/plans/homebrew-fork-srd.md Phase 2b.
 *
 * GM-facing panel (Campaign settings → Homebrew → Workshop): fork a shipped
 * SRD mechanic into this campaign, then tweak its key fields (name + the
 * primary action's damage / type / save / healing / area) via a form, with a
 * raw-JSON escape hatch for everything else. Saves via the Phase 2a edit
 * endpoint (POST .../homebrew/{type}/{slug}/edit); forks via Phase 1
 * (POST .../homebrew/fork); reverts via DELETE .../homebrew/{type}/{slug}.
 * All writes are campaign-scoped + GM-gated server-side, so this never
 * touches the shipped SRD tree. */
(function () {
  const cid = (typeof CAMPAIGN_ID !== 'undefined' && CAMPAIGN_ID) ? CAMPAIGN_ID : '';
  if (!cid) return;
  const $ = (id) => document.getElementById(id);
  const listEl = $('hbw-list');
  if (!listEl) return; // panel not on this page

  let current = null; // {type, slug, record}

  function status(msg, ok) {
    const s = $('hbw-status');
    if (!s) return;
    s.textContent = msg || '';
    s.style.color = ok === false ? '#c0392b' : '#2e7d32';
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g,
      c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }
  function primaryAction(rec) {
    const acts = (rec && rec.actions) || [];
    return acts.find(a => a && (a.id === 'cast' || a.id === 'effect')) || acts[0] || null;
  }

  async function loadList() {
    listEl.innerHTML = '<em>Loading…</em>';
    try {
      const r = await fetch(`/api/campaign/${cid}/homebrew/custom`);
      if (!r.ok) { listEl.innerHTML = '<em>Could not load.</em>'; return; }
      const recs = (await r.json()).records || [];
      if (!recs.length) {
        listEl.innerHTML = '<p class="muted">No campaign homebrew yet — fork an SRD mechanic above.</p>';
        return;
      }
      listEl.innerHTML = recs.map(x =>
        `<div class="hbw-row" style="display:flex;gap:8px;align-items:center;padding:6px 0;border-bottom:1px solid #eee">
           <span style="flex:1"><strong>${esc(x.name)}</strong>
             <span class="muted">${esc(x.type)} · ${esc(x.slug)}</span></span>
           <button type="button" class="hbw-export" data-type="${esc(x.type)}" data-slug="${esc(x.slug)}">Export</button>
           <button type="button" class="hbw-edit" data-type="${esc(x.type)}" data-slug="${esc(x.slug)}">Edit</button>
           <button type="button" class="hbw-revert" data-type="${esc(x.type)}" data-slug="${esc(x.slug)}">Revert</button>
         </div>`).join('');
    } catch (e) {
      listEl.innerHTML = '<em>Error loading.</em>';
    }
  }

  async function openEditor(type, slug) {
    status('');
    const r = await fetch(`/api/content/${type}/${slug}?campaign_id=${cid}`);
    if (!r.ok) { status('Could not load record.', false); return; }
    const rec = (await r.json()).record;
    current = { type, slug, record: rec };
    $('hbw-ed-name').value = rec.name || '';
    const a = primaryAction(rec) || {};
    $('hbw-ed-damage').value = a.damage || '';
    $('hbw-ed-damage-type').value = (a.damage_type || '').toLowerCase();
    $('hbw-ed-save').value = (a.save_ability || '').toUpperCase();
    $('hbw-ed-healing').value = a.healing || '';
    const area = a.area || {};
    $('hbw-ed-shape').value = area.shape || '';
    $('hbw-ed-size').value = area.size_ft || '';
    $('hbw-ed-raw').value = JSON.stringify(rec, null, 2);
    $('hbw-ed-title').textContent = `Editing: ${rec.name || slug} (${type})`;
    $('hbw-editor').hidden = false;
  }

  function buildRecordFromForm() {
    // Start from the (possibly hand-edited) raw JSON, then layer the friendly
    // fields on top so a quick form edit always wins + stays consistent.
    let rec;
    try { rec = JSON.parse($('hbw-ed-raw').value); }
    catch (e) { status('Raw JSON is invalid: ' + e.message, false); return null; }
    rec.slug = current.record.slug; // slug is immutable in the editor
    rec.name = $('hbw-ed-name').value || rec.name;
    let a = primaryAction(rec);
    if (!a) { a = { id: 'cast', name: 'Cast' }; rec.actions = rec.actions || []; rec.actions.unshift(a); }
    a.damage = $('hbw-ed-damage').value;
    a.damage_type = $('hbw-ed-damage-type').value;
    a.save_ability = $('hbw-ed-save').value;
    a.healing = $('hbw-ed-healing').value;
    const shape = $('hbw-ed-shape').value;
    const size = parseInt($('hbw-ed-size').value, 10);
    if (shape) {
      a.area = { shape, size_ft: isNaN(size) ? 0 : size, secondary_ft: (a.area && a.area.secondary_ft) || 0 };
    }
    return rec;
  }

  async function doFork(type, src, mode) {
    if (!src) { status('Enter or pick the SRD slug to fork (e.g. fireball).', false); return; }
    const r = await fetch(`/api/campaign/${cid}/homebrew/fork`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, src_slug: src, mode }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { status('Fork failed: ' + (d.detail || r.status), false); return; }
    status(`Forked → ${d.slug}`, true);
    await loadList();
    openEditor(type, d.slug);
  }

  $('hbw-fork-btn').addEventListener('click', () =>
    doFork($('hbw-fork-type').value, $('hbw-fork-slug').value.trim(), $('hbw-fork-mode').value));

  // Phase 3: search the shipped SRD (offline, SRD-only) for the selected
  // type, so the GM can fork without knowing the exact slug.
  $('hbw-search-btn').addEventListener('click', async () => {
    const type = $('hbw-fork-type').value;
    const q = $('hbw-search-q').value.trim();
    const box = $('hbw-search-results');
    box.innerHTML = '<em>Searching…</em>';
    try {
      const r = await fetch(`/api/campaign/${cid}/srd_search?type=${encodeURIComponent(type)}&q=${encodeURIComponent(q)}`);
      if (!r.ok) { box.innerHTML = '<em>Search failed.</em>'; return; }
      const recs = (await r.json()).records || [];
      if (!recs.length) { box.innerHTML = `<p class="muted">No SRD ${esc(type)} match “${esc(q)}”.</p>`; return; }
      box.innerHTML = recs.map(x =>
        `<div style="display:flex;gap:8px;align-items:center;padding:4px 0;border-bottom:1px solid #f0f0f0">
           <span style="flex:1">${esc(x.name)} <span class="muted">${esc(x.slug)}</span></span>
           <button type="button" class="hbw-search-fork" data-slug="${esc(x.slug)}">Fork</button>
         </div>`).join('');
    } catch (e) { box.innerHTML = '<em>Search error.</em>'; }
  });

  $('hbw-search-results').addEventListener('click', (e) => {
    const b = e.target.closest('.hbw-search-fork');
    if (b) doFork($('hbw-fork-type').value, b.dataset.slug, $('hbw-fork-mode').value);
  });

  // Enter in the search box triggers a search.
  $('hbw-search-q').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); $('hbw-search-btn').click(); }
  });

  listEl.addEventListener('click', async (e) => {
    const ex = e.target.closest('.hbw-export');
    const ed = e.target.closest('.hbw-edit');
    const rv = e.target.closest('.hbw-revert');
    if (ex) {
      // Download this single homebrew record as a one-row simplevtt-homebrew
      // pack (round-trips through Import). v2.623.0 — backup arc Phase 9b.
      try {
        const r = await fetch(`/api/campaign/${cid}/homebrew/${ex.dataset.type}/${ex.dataset.slug}/export`);
        if (!r.ok) { status('Export failed.', false); return; }
        const data = await r.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        const url = URL.createObjectURL(blob);
        a.href = url;
        a.download = `simplevtt-homebrew-${ex.dataset.type}-${ex.dataset.slug}.json`;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
        status('Exported.', true);
      } catch (err) { status('Export error.', false); }
      return;
    }
    if (ed) { openEditor(ed.dataset.type, ed.dataset.slug); return; }
    if (rv) {
      if (!confirm(`Revert (delete) ${rv.dataset.type}/${rv.dataset.slug}?`)) return;
      const r = await fetch(`/api/campaign/${cid}/homebrew/${rv.dataset.type}/${rv.dataset.slug}`, { method: 'DELETE' });
      if (r.ok) {
        status('Reverted.', true);
        if (current && current.slug === rv.dataset.slug) { $('hbw-editor').hidden = true; current = null; }
        loadList();
      } else { status('Revert failed.', false); }
    }
  });

  $('hbw-save-btn').addEventListener('click', async () => {
    if (!current) return;
    const rec = buildRecordFromForm();
    if (!rec) return;
    const r = await fetch(`/api/campaign/${cid}/homebrew/${current.type}/${current.slug}/edit`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(rec),
    });
    if (r.ok) { status('Saved.', true); current.record = rec; loadList(); }
    else { const d = await r.json().catch(() => ({})); status('Save failed: ' + (d.detail || r.status), false); }
  });

  $('hbw-cancel-btn').addEventListener('click', () => {
    $('hbw-editor').hidden = true; current = null; status('');
  });

  loadList();
})();
