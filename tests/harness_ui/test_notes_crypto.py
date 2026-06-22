"""Phase 4b — browser-side note encryption round-trip (Playwright).

docs/plans/notes-and-handouts.md. Web Crypto only runs in a real
browser, so these drive `/static/notes_crypto.js` through Playwright:

  - the crypto module round-trips (encrypt → decrypt) with no plaintext
    in the ciphertext, the key_check verifies the right passphrase and
    rejects the wrong one, and a wrong key fails to decrypt;
  - the full path through the API: derive a key, PUT the encryption
    config, POST a private note with encrypted fields, GET it back and
    decrypt — proving the server stored NO plaintext (title/body empty)
    and the POST body carried NO plaintext on the wire.

Run as alice (a non-GM member) in an authenticated, same-origin page so
`fetch` carries her session cookie.
"""
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID, sheet_url

_MODULE_TEST = """
async () => {
  const NC = window.NotesCrypto;
  const salt = NC.generateSalt();
  const key = await NC.deriveKey("correct horse battery", salt, 200000);
  const PLAIN = "The lich's phylactery is in the well";
  const env = await NC.encryptField(key, PLAIN);
  const dec = await NC.decryptField(key, env);
  const kc = await NC.makeKeyCheck(key);
  const okCheck = await NC.verifyKeyCheck(key, kc);
  const wrongKey = await NC.deriveKey("wrong passphrase", salt, 200000);
  const wrongCheck = await NC.verifyKeyCheck(wrongKey, kc);
  let wrongDecryptThrew = false;
  try { await NC.decryptField(wrongKey, env); }
  catch (e) { wrongDecryptThrew = true; }
  return {
    roundTrip: dec === PLAIN,
    envHasPlaintext: env.indexOf(PLAIN) !== -1,
    okCheck: okCheck,
    wrongCheck: wrongCheck,
    wrongDecryptThrew: wrongDecryptThrew,
  };
}
"""

_SERVER_TEST = """
async (cid) => {
  const NC = window.NotesCrypto;
  // Reset any prior config so the PUT below isn't a 409.
  await fetch("/api/notes/encryption", {method: "DELETE"});
  const salt = NC.generateSalt();
  const iterations = 200000;
  const key = await NC.deriveKey("my session passphrase", salt, iterations);
  const key_check = await NC.makeKeyCheck(key);
  const putResp = await fetch("/api/notes/encryption", {
    method: "PUT", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({salt: salt, iterations: iterations, key_check: key_check}),
  });
  const TITLE = "Private Title XYZZY";
  const BODY = "Private Body PLUGH";
  const enc_title = await NC.encryptField(key, TITLE);
  const enc_body = await NC.encryptField(key, BODY);
  const postBody = JSON.stringify({
    visibility: "private", enc_title: enc_title, enc_body: enc_body});
  const postResp = await fetch(`/api/campaign/${cid}/notes`, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: postBody,
  });
  const created = await postResp.json();
  const nid = created.note.id;
  const got = (await (await fetch(`/api/campaign/${cid}/notes/${nid}`)).json()).note;
  const decTitle = await NC.decryptField(key, got.enc_title);
  const decBody = await NC.decryptField(key, got.enc_body);
  await fetch("/api/notes/encryption", {method: "DELETE"});  // cleanup
  return {
    putStatus: putResp.status,
    postStatus: postResp.status,
    serverTitle: got.title,
    serverBody: got.body,
    isEncrypted: got.is_encrypted,
    decTitle: decTitle,
    decBody: decBody,
    postBodyHasPlaintext:
      postBody.indexOf(TITLE) !== -1 || postBody.indexOf(BODY) !== -1,
  };
}
"""


def _load_module(page: Page, roster: dict) -> None:
    """Land on an authenticated same-origin page, then inject the crypto
    module so window.NotesCrypto is available + fetch carries the cookie."""
    pip = roster["Pip Quickfingers"]
    resp = page.goto(sheet_url(pip["id"]))
    assert resp is not None and resp.ok, "auth page failed to load"
    page.add_script_tag(url="/static/notes_crypto.js")
    assert page.evaluate("() => typeof window.NotesCrypto === 'object'")


def test_notes_crypto_module_roundtrip(alice_page: Page, roster: dict):
    """The crypto module encrypts/decrypts correctly, leaks no plaintext
    into the ciphertext, and the key_check accepts the right passphrase
    while rejecting the wrong one."""
    _load_module(alice_page, roster)
    r = alice_page.evaluate(_MODULE_TEST)
    assert r["roundTrip"] is True, "decrypt(encrypt(x)) must equal x"
    assert r["envHasPlaintext"] is False, "ciphertext must not contain plaintext"
    assert r["okCheck"] is True, "correct passphrase must verify"
    assert r["wrongCheck"] is False, "wrong passphrase must be rejected"
    assert r["wrongDecryptThrew"] is True, "wrong key must fail to decrypt"


def test_notes_crypto_server_roundtrip(alice_page: Page, roster: dict):
    """Full path: encrypt in-browser → PUT config → POST private note →
    GET back → decrypt. The server stored NO plaintext and the POST body
    carried NO plaintext on the wire."""
    _load_module(alice_page, roster)
    r = alice_page.evaluate(_SERVER_TEST, CAMPAIGN_ID)
    assert r["putStatus"] == 200, r
    assert r["postStatus"] == 200, r
    assert r["isEncrypted"] is True
    assert r["serverTitle"] == "", "server must hold no plaintext title"
    assert r["serverBody"] == "", "server must hold no plaintext body"
    assert r["decTitle"] == "Private Title XYZZY", "title round-trips via server"
    assert r["decBody"] == "Private Body PLUGH", "body round-trips via server"
    assert r["postBodyHasPlaintext"] is False, "no plaintext on the wire"
