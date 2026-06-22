/* SimpleVTT — Notes & Handouts drawer (docs/plans/notes-and-handouts.md).
 *
 * Phase 5a: GM prep notes. Renders the #notes-drawer panel from
 * GET /api/campaign/{cid}/notes and gives the GM create/edit/delete over
 * gm_only prep notes, with live note_updated WS sync. Later slices add
 * handouts (5b), player public notes (5c), and the encrypted private-note
 * unlock flow (5d) — this module is the shared rendering shell they grow
 * into.
 *
 * Reads the page globals CAMPAIGN_ID + ME (shared global lexical scope,
 * the same way tabletop.js / roll_toast.js do). Listens for the
 * `vtt:ws-message` document event the tabletop dispatches per WS frame.
 */
(function () {
  "use strict";
  if (typeof CAMPAIGN_ID === "undefined") return;

  var API = "/api/campaign/" + CAMPAIGN_ID + "/notes";
  var me = (typeof ME !== "undefined" && ME) ? ME : { id: null, isGm: false };
  var isGm = !!me.isGm;

  var notes = [];
  var loaded = false;
  var composerOpen = false;
  var editingId = null;

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
    // Dense panel exception (CLAUDE.md): 32px min instead of 44px.
    "min-height:32px;padding:2px 8px;font-size:11px;";
  var INPUT_STYLE =
    "width:100%;box-sizing:border-box;margin-bottom:6px;";

  function canEdit(n) {
    if (n.visibility === "gm_only") return isGm;
    if (n.visibility === "public") return isGm || n.author_user_id === me.id;
    if (n.visibility === "private") return n.author_user_id === me.id;
    return false;
  }

  function editorHtml(n) {
    var id = n ? n.id : "";
    var t = n ? (n.title || "") : "";
    var b = n ? (n.body || "") : "";
    var f = n ? (n.folder || "") : "";
    var pinned = (n && n.pinned) ? "checked" : "";
    return '' +
      '<div class="note-editor" data-id="' + id + '" style="' + CARD_STYLE + '">' +
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

  function cardHtml(n) {
    if (editingId === n.id) return editorHtml(n);
    var pin = n.pinned ? "📌 " : "";
    var actions = "";
    if (canEdit(n)) {
      actions =
        '<span style="white-space:nowrap;display:flex;gap:4px;">' +
          '<button class="note-edit" data-id="' + n.id + '" style="' + EDIT_BTN_STYLE + '">Edit</button>' +
          '<button class="note-del" data-id="' + n.id + '" title="Delete" style="' + EDIT_BTN_STYLE + '">✕</button>' +
        '</span>';
    }
    var folder = n.folder
      ? '<div style="margin-top:6px;"><span style="font-size:10px;color:var(--fg-mute);' +
        'border:1px solid var(--border);border-radius:10px;padding:1px 7px;">' +
        esc(n.folder) + '</span></div>'
      : "";
    var bodyHtml = n.body
      ? '<div style="white-space:pre-wrap;font-size:12px;margin-top:6px;' +
        'color:var(--fg);">' + esc(n.body) + '</div>'
      : "";
    return '' +
      '<div class="note-card" data-id="' + n.id + '" style="' + CARD_STYLE + '">' +
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">' +
          '<strong style="font-size:13px;">' + pin + esc(n.title || "(untitled)") + '</strong>' +
          actions +
        '</div>' + bodyHtml + folder +
      '</div>';
  }

  function render() {
    var el = bodyEl();
    if (!el) return;
    var html =
      '<div style="font-size:11px;color:var(--accent);text-transform:uppercase;' +
      'letter-spacing:0.5px;margin-bottom:8px;">' +
      (isGm ? "GM Prep Notes" : "Notes") + '</div>';

    if (isGm) {
      html += composerOpen
        ? editorHtml(null)
        : '<button class="note-new" style="margin-bottom:10px;">+ New prep note</button>';
    }

    if (!notes.length) {
      html += '<p class="notes-empty" style="color:var(--fg-mute);font-size:12px;">' +
        (isGm ? "No prep notes yet." : "No notes shared with you yet.") + '</p>';
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
  }

  async function load() {
    try {
      var r = await fetch(API, { headers: { "Accept": "application/json" } });
      if (!r.ok) return;
      var data = await r.json();
      notes = (data && data.notes) || [];
      loaded = true;
      render();
    } catch (e) { /* leave the loading state */ }
  }

  async function createNote(payload) {
    var r = await fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (r.ok) {
      var d = await r.json();
      upsert(d.note);
      composerOpen = false;
      render();
    } else {
      window.alert("Could not save the note.");
    }
  }

  async function patchNote(id, payload) {
    var r = await fetch(API + "/" + id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (r.ok) {
      var d = await r.json();
      upsert(d.note);
      editingId = null;
      render();
    } else {
      window.alert("Could not update the note.");
    }
  }

  async function deleteNote(id) {
    var r = await fetch(API + "/" + id, { method: "DELETE" });
    if (r.ok) { removeNote(id); render(); }
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
    } else if (t.classList.contains("note-save")) {
      var editor = t.closest(".note-editor");
      if (!editor) return;
      var title = editor.querySelector(".note-title-input").value.trim();
      var body = editor.querySelector(".note-body-input").value.trim();
      var folder = editor.querySelector(".note-folder-input").value.trim();
      var pinned = editor.querySelector(".note-pin-input").checked;
      if (!title && !body) { window.alert("Enter a title or body."); return; }
      var id = editor.dataset.id;
      var payload = { title: title, body: body, folder: folder, pinned: pinned };
      if (id) {
        patchNote(parseInt(id, 10), payload);
      } else {
        // Phase 5a: the GM composer creates gm_only prep notes.
        payload.visibility = "gm_only";
        createNote(payload);
      }
    }
  });

  document.addEventListener("vtt:ws-message", function (ev) {
    var msg = ev.detail;
    if (!msg || msg.type !== "note_updated" || !msg.data) return;
    if (msg.data.deleted) {
      removeNote(msg.data.note_id);
    } else if (msg.data.note) {
      upsert(msg.data.note);
    }
    if (loaded) render();
  });

  if (document.readyState !== "loading") load();
  else document.addEventListener("DOMContentLoaded", load);

  window.Notes = { load: load, render: render };
})();
