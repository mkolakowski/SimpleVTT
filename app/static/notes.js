/* SimpleVTT — Notes & Handouts drawer (docs/plans/notes-and-handouts.md).
 *
 * Phase 5a — GM prep notes. Phase 5c/5d — player public + end-to-end-
 * encrypted private notes. Renders the #notes-drawer panel from
 * GET /api/campaign/{cid}/notes and gives every user a composer with a
 * visibility selector:
 *   - GM:     Prep (gm_only) / Public / Private
 *   - player: Public / Private
 *
 * Private notes are encrypted in the browser with notes_crypto.js: the
 * passphrase never leaves the page, the server stores only ciphertext.
 * A locked private note shows "🔒 Locked" until the user unlocks (a
 * passphrase prompt → derive key → verify → decrypt in place). Live
 * note_updated WS events upsert/remove cards (scoped server-side so a
 * private note's event only ever reaches its author).
 *
 * Reads the page globals CAMPAIGN_ID + ME (shared global lexical scope).
 */
(function () {
  "use strict";
  if (typeof CAMPAIGN_ID === "undefined") return;

  var API = "/api/campaign/" + CAMPAIGN_ID + "/notes";
  var ENC_API = "/api/notes/encryption";
  var me = (typeof ME !== "undefined" && ME) ? ME : { id: null, isGm: false };
  var isGm = !!me.isGm;

  var notes = [];
  var loaded = false;
  var composerOpen = false;
  var editingId = null;

  // Crypto state (Phase 5d). cryptoKey is held in memory for the session
  // only; never persisted, never sent to the server.
  var cryptoKey = null;
  var encConfig = null;            // {configured, salt, iterations, key_check}
  var decrypted = {};              // note_id -> {title, body} | {error:true}

  function bodyEl() { return document.getElementById("notes-body"); }

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = (s == null) ? "" : String(s);
    return d.innerHTML;
  }

  var CARD_STYLE =
    "border:1px solid var(--border);border-radius:8px;padding:8px 10px;" +
    "margin-bottom:8px;background:var(--bg-1);";
  var EDIT_BTN_STYLE =
    // Dense-panel exception (CLAUDE.md): 32px min instead of 44px.
    "min-height:32px;padding:2px 8px;font-size:11px;";
  var INPUT_STYLE = "width:100%;box-sizing:border-box;margin-bottom:6px;";

  function canEdit(n) {
    if (n.visibility === "gm_only") return isGm;
    if (n.visibility === "public") return isGm || n.author_user_id === me.id;
    if (n.visibility === "private") return n.author_user_id === me.id;
    return false;
  }

  function visibilityOptions() {
    var opts = isGm
      ? [["gm_only", "Prep (GM only)"], ["public", "Public"], ["private", "Private"]]
      : [["public", "Public"], ["private", "Private"]];
    return opts.map(function (o) {
      return '<option value="' + o[0] + '">' + o[1] + '</option>';
    }).join("");
  }

  function editorHtml(n) {
    // n === null → the "new note" composer (shows the visibility select).
    var id = n ? n.id : "";
    var isPrivate = n && n.visibility === "private";
    var dec = isPrivate ? (decrypted[n.id] || {}) : {};
    var t = n ? (isPrivate ? (dec.title || "") : (n.title || "")) : "";
    var b = n ? (isPrivate ? (dec.body || "") : (n.body || "")) : "";
    var f = n ? (n.folder || "") : "";
    var pinned = (n && n.pinned) ? "checked" : "";
    var visSelect = n
      ? ""  // visibility is fixed on edit
      : '<select class="note-vis-input" style="' + INPUT_STYLE + '">' +
        visibilityOptions() + '</select>';
    return '' +
      '<div class="note-editor" data-id="' + id + '" style="' + CARD_STYLE + '">' +
        visSelect +
        '<input class="note-title-input" type="text" maxlength="200" ' +
          'placeholder="Title" value="' + esc(t) + '" style="' + INPUT_STYLE + '">' +
        '<textarea class="note-body-input" rows="5" placeholder="Note text" ' +
          'style="' + INPUT_STYLE + 'resize:vertical;">' + esc(b) + '</textarea>' +
        '<input class="note-folder-input" type="text" maxlength="120" ' +
          'placeholder="Folder (optional)" value="' + esc(f) + '" style="' + INPUT_STYLE + '">' +
        '<label style="display:flex;align-items:center;gap:6px;font-size:12px;margin-bottom:6px;">' +
          '<input type="checkbox" class="note-pin-input" ' + pinned + '> Pin to top</label>' +
        '<div style="display:flex;gap:8px;">' +
          '<button class="note-save" data-id="' + id + '">Save</button>' +
          '<button class="note-cancel">Cancel</button>' +
        '</div>' +
      '</div>';
  }

  function visBadge(n) {
    var label = { gm_only: "GM", public: "Public", "private": "🔒 Private" }[n.visibility];
    if (!label) return "";
    return '<span style="font-size:10px;color:var(--fg-mute);border:1px solid var(--border);' +
      'border-radius:10px;padding:1px 7px;margin-left:6px;">' + label + '</span>';
  }

  function lockedCardHtml(n) {
    return '' +
      '<div class="note-card" data-id="' + n.id + '" style="' + CARD_STYLE + '">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">' +
          '<span style="font-size:13px;">🔒 <em>Locked private note</em></span>' +
          '<button class="note-unlock" style="' + EDIT_BTN_STYLE + '">Unlock</button>' +
        '</div>' +
      '</div>';
  }

  function cardHtml(n) {
    if (n.visibility === "private" && !cryptoKey) return lockedCardHtml(n);
    if (editingId === n.id) return editorHtml(n);

    var title, body;
    if (n.visibility === "private") {
      var dec = decrypted[n.id];
      if (!dec) { title = "…"; body = ""; }
      else if (dec.error) { title = "⚠ Could not decrypt"; body = ""; }
      else { title = dec.title; body = dec.body; }
    } else {
      title = n.title || "(untitled)";
      body = n.body || "";
    }

    var pin = n.pinned ? "📌 " : "";
    var actions = canEdit(n)
      ? '<span style="white-space:nowrap;display:flex;gap:4px;">' +
          '<button class="note-edit" data-id="' + n.id + '" style="' + EDIT_BTN_STYLE + '">Edit</button>' +
          '<button class="note-del" data-id="' + n.id + '" title="Delete" style="' + EDIT_BTN_STYLE + '">✕</button>' +
        '</span>'
      : "";
    var folder = n.folder
      ? '<div style="margin-top:6px;"><span style="font-size:10px;color:var(--fg-mute);' +
        'border:1px solid var(--border);border-radius:10px;padding:1px 7px;">' +
        esc(n.folder) + '</span></div>'
      : "";
    var bodyHtml = body
      ? '<div style="white-space:pre-wrap;font-size:12px;margin-top:6px;color:var(--fg);">' +
        esc(body) + '</div>'
      : "";
    return '' +
      '<div class="note-card" data-id="' + n.id + '" style="' + CARD_STYLE + '">' +
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">' +
          '<strong style="font-size:13px;">' + pin + esc(title) + visBadge(n) + '</strong>' +
          actions +
        '</div>' + bodyHtml + folder +
      '</div>';
  }

  function hasLockedPrivate() {
    return !cryptoKey && notes.some(function (n) { return n.visibility === "private"; });
  }

  function render() {
    var el = bodyEl();
    if (!el) return;
    var html =
      '<div style="font-size:11px;color:var(--accent);text-transform:uppercase;' +
      'letter-spacing:0.5px;margin-bottom:8px;">Notes</div>';

    html += composerOpen
      ? editorHtml(null)
      : '<button class="note-new" style="margin-bottom:10px;">+ New note</button>';

    if (hasLockedPrivate()) {
      html += '<button class="note-unlock" style="margin:0 0 10px 8px;">🔓 Unlock private notes</button>';
    }

    if (!notes.length) {
      html += '<p class="notes-empty" style="color:var(--fg-mute);font-size:12px;">' +
        (isGm ? "No notes yet." : "No notes yet — create one above.") + '</p>';
    } else {
      notes.forEach(function (n) { html += cardHtml(n); });
    }
    el.innerHTML = html;
  }

  function sortNotes() {
    notes.sort(function (a, b) {
      if (!!b.pinned !== !!a.pinned) return (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0);
      return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
    });
  }

  function upsert(n) {
    if (!n || !n.id) return;
    var i = notes.findIndex(function (x) { return x.id === n.id; });
    if (i >= 0) notes[i] = n; else notes.push(n);
    sortNotes();
  }

  function removeNote(id) {
    notes = notes.filter(function (n) { return n.id !== id; });
    delete decrypted[id];
  }

  async function decryptOne(n) {
    if (!cryptoKey || n.visibility !== "private") return;
    try {
      decrypted[n.id] = {
        title: n.enc_title ? await window.NotesCrypto.decryptField(cryptoKey, n.enc_title) : "",
        body: n.enc_body ? await window.NotesCrypto.decryptField(cryptoKey, n.enc_body) : "",
      };
    } catch (e) {
      decrypted[n.id] = { error: true };
    }
  }

  async function decryptAll() {
    if (!cryptoKey) return;
    for (var i = 0; i < notes.length; i++) {
      if (notes[i].visibility === "private" && !decrypted[notes[i].id]) {
        await decryptOne(notes[i]);
      }
    }
    render();
  }

  async function loadEncConfig() {
    try {
      var r = await fetch(ENC_API, { headers: { "Accept": "application/json" } });
      if (r.ok) encConfig = await r.json();
    } catch (e) { /* ignore */ }
  }

  async function ensureUnlocked() {
    if (cryptoKey) return true;
    if (!window.NotesCrypto) { window.alert("Encryption is unavailable in this browser."); return false; }
    if (!encConfig) await loadEncConfig();
    if (encConfig && encConfig.configured) {
      var pass = window.prompt("Enter your notes passphrase to unlock private notes:");
      if (!pass) return false;
      var key = await window.NotesCrypto.deriveKey(pass, encConfig.salt, encConfig.iterations);
      if (!(await window.NotesCrypto.verifyKeyCheck(key, encConfig.key_check))) {
        window.alert("Wrong passphrase.");
        return false;
      }
      cryptoKey = key;
      return true;
    }
    // First-time set-up.
    var p1 = window.prompt(
      "Set a passphrase for your private notes.\n\n" +
      "There is NO recovery: if you forget it, your private notes are " +
      "lost forever (not even the GM or the server can read them).");
    if (!p1) return false;
    var p2 = window.prompt("Confirm your passphrase:");
    if (p1 !== p2) { window.alert("Passphrases didn't match."); return false; }
    var salt = window.NotesCrypto.generateSalt();
    var iterations = 600000;
    var newKey = await window.NotesCrypto.deriveKey(p1, salt, iterations);
    var key_check = await window.NotesCrypto.makeKeyCheck(newKey);
    var resp = await fetch(ENC_API, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ salt: salt, iterations: iterations, key_check: key_check }),
    });
    if (!resp.ok) { window.alert("Could not set up encryption."); return false; }
    encConfig = { configured: true, salt: salt, iterations: iterations, key_check: key_check };
    cryptoKey = newKey;
    return true;
  }

  async function load() {
    try {
      var r = await fetch(API, { headers: { "Accept": "application/json" } });
      if (!r.ok) return;
      var data = await r.json();
      notes = (data && data.notes) || [];
      loaded = true;
      render();
      if (cryptoKey) await decryptAll();
    } catch (e) { /* leave the loading state */ }
  }

  async function postNote(payload) {
    var r = await fetch(API, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) { window.alert("Could not save the note."); return; }
    var d = await r.json();
    upsert(d.note);
    composerOpen = false;
    if (d.note.visibility === "private") await decryptOne(d.note);
    render();
  }

  async function patchNoteReq(id, payload) {
    var r = await fetch(API + "/" + id, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) { window.alert("Could not update the note."); return; }
    var d = await r.json();
    upsert(d.note);
    editingId = null;
    if (d.note.visibility === "private") await decryptOne(d.note);
    render();
  }

  async function deleteNote(id) {
    var r = await fetch(API + "/" + id, { method: "DELETE" });
    if (r.ok) { removeNote(id); render(); }
  }

  async function saveFromEditor(editor) {
    var id = editor.dataset.id;
    var title = editor.querySelector(".note-title-input").value.trim();
    var body = editor.querySelector(".note-body-input").value.trim();
    var folder = editor.querySelector(".note-folder-input").value.trim();
    var pinned = editor.querySelector(".note-pin-input").checked;
    if (!title && !body) { window.alert("Enter a title or body."); return; }

    if (id) {
      // Edit: visibility is fixed; encrypt if the note is private.
      var existing = notes.find(function (n) { return n.id === parseInt(id, 10); });
      if (existing && existing.visibility === "private") {
        if (!(await ensureUnlocked())) return;
        var et = await window.NotesCrypto.encryptField(cryptoKey, title);
        var eb = await window.NotesCrypto.encryptField(cryptoKey, body);
        await patchNoteReq(parseInt(id, 10),
          { enc_title: et, enc_body: eb, folder: folder, pinned: pinned });
      } else {
        await patchNoteReq(parseInt(id, 10),
          { title: title, body: body, folder: folder, pinned: pinned });
      }
      return;
    }

    // New note — branch on the chosen visibility.
    var vis = editor.querySelector(".note-vis-input").value;
    if (vis === "private") {
      if (!(await ensureUnlocked())) return;
      var encT = await window.NotesCrypto.encryptField(cryptoKey, title);
      var encB = await window.NotesCrypto.encryptField(cryptoKey, body);
      await postNote({ visibility: "private", enc_title: encT, enc_body: encB,
                       folder: folder, pinned: pinned });
    } else {
      await postNote({ visibility: vis, title: title, body: body,
                       folder: folder, pinned: pinned });
    }
  }

  document.addEventListener("click", function (ev) {
    var el = bodyEl();
    if (!el) return;
    var t = ev.target;
    if (!el.contains(t)) return;
    if (t.classList.contains("note-new")) {
      composerOpen = true; editingId = null; render();
    } else if (t.classList.contains("note-cancel")) {
      composerOpen = false; editingId = null; render();
    } else if (t.classList.contains("note-edit")) {
      editingId = parseInt(t.dataset.id, 10); composerOpen = false; render();
    } else if (t.classList.contains("note-del")) {
      if (window.confirm("Delete this note?")) deleteNote(parseInt(t.dataset.id, 10));
    } else if (t.classList.contains("note-unlock")) {
      ensureUnlocked().then(function (ok) { if (ok) decryptAll(); });
    } else if (t.classList.contains("note-save")) {
      var editor = t.closest(".note-editor");
      if (editor) saveFromEditor(editor);
    }
  });

  document.addEventListener("vtt:ws-message", function (ev) {
    var msg = ev.detail;
    if (!msg || msg.type !== "note_updated" || !msg.data) return;
    if (msg.data.deleted) {
      removeNote(msg.data.note_id);
      if (loaded) render();
    } else if (msg.data.note) {
      upsert(msg.data.note);
      if (msg.data.note.visibility === "private" && cryptoKey) {
        decryptOne(msg.data.note).then(function () { if (loaded) render(); });
      } else if (loaded) {
        render();
      }
    }
  });

  function init() { loadEncConfig(); load(); }
  if (document.readyState !== "loading") init();
  else document.addEventListener("DOMContentLoaded", init);

  window.Notes = { load: load, render: render };
})();
