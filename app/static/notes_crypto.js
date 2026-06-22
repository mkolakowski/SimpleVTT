/* SimpleVTT — Notes & Handouts: end-to-end encryption for private notes.
 *
 * Phase 4b of docs/plans/notes-and-handouts.md. Uses only the platform
 * Web Crypto API (no third-party dependency, works offline): a
 * passphrase is stretched with PBKDF2-SHA256 into an AES-GCM-256 key,
 * and each field is sealed in a self-describing {v,iv,ct} envelope.
 *
 * The passphrase NEVER leaves the browser. The server stores only the
 * salt + KDF params + a key_check token (to verify a passphrase) and the
 * per-note ciphertext envelopes — it has no key and no decryption path.
 * A lost passphrase is unrecoverable by design.
 *
 * window.NotesCrypto API:
 *   generateSalt()                      -> base64 128-bit salt
 *   deriveKey(passphrase, saltB64, n)   -> CryptoKey (n = PBKDF2 rounds)
 *   encryptField(key, plaintext)        -> envelope JSON string
 *   decryptField(key, envelope)         -> plaintext (throws on wrong key)
 *   makeKeyCheck(key)                   -> envelope of a fixed sentinel
 *   verifyKeyCheck(key, keyCheck)       -> bool (false on wrong passphrase)
 */
(function () {
  "use strict";

  // Bumped only if the envelope format changes; the server never reads it.
  var SENTINEL = "simplevtt-notes-v1";
  var encoder = new TextEncoder();
  var decoder = new TextDecoder();

  function bytesToB64(buf) {
    var arr = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
    var s = "";
    for (var i = 0; i < arr.length; i++) s += String.fromCharCode(arr[i]);
    return btoa(s);
  }

  function b64ToBytes(b64) {
    var s = atob(b64);
    var out = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
    return out;
  }

  function generateSalt() {
    return bytesToB64(crypto.getRandomValues(new Uint8Array(16)));
  }

  async function deriveKey(passphrase, saltB64, iterations) {
    var baseKey = await crypto.subtle.importKey(
      "raw", encoder.encode(passphrase), "PBKDF2", false, ["deriveKey"]);
    // Extractable so the key can be wrapped under a recovery key
    // (the raw bytes never leave the browser; only an AES-GCM-encrypted
    // wrap of them is stored / downloaded).
    return crypto.subtle.deriveKey(
      { name: "PBKDF2", salt: b64ToBytes(saltB64),
        iterations: iterations, hash: "SHA-256" },
      baseKey,
      { name: "AES-GCM", length: 256 },
      true,
      ["encrypt", "decrypt"]);
  }

  // ── Recovery key (an alternate unlock) ─────────────────────────────
  // The note key is wrapped (AES-GCM-encrypted) under a random recovery
  // key the user downloads. Forgot the passphrase → unwrap the note key
  // with the recovery key. The server stores only the wrapped envelope.

  function generateRecoveryKey() {
    return bytesToB64(crypto.getRandomValues(new Uint8Array(32)));
  }

  function importRecoveryKey(recoveryKeyB64) {
    return crypto.subtle.importKey(
      "raw", b64ToBytes(recoveryKeyB64), { name: "AES-GCM" }, false,
      ["encrypt", "decrypt"]);
  }

  async function wrapKeyForRecovery(noteKey, recoveryKeyB64) {
    var rk = await importRecoveryKey(recoveryKeyB64);
    var rawNote = await crypto.subtle.exportKey("raw", noteKey);
    var iv = crypto.getRandomValues(new Uint8Array(12));
    var ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv: iv }, rk, rawNote);
    return JSON.stringify({ v: 1, iv: bytesToB64(iv), ct: bytesToB64(ct) });
  }

  async function unwrapKeyFromRecovery(recoveryKeyB64, envelope) {
    var rk = await importRecoveryKey(recoveryKeyB64);
    var obj = JSON.parse(envelope);
    var rawNote = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: b64ToBytes(obj.iv) }, rk, b64ToBytes(obj.ct));
    // Re-import as the note key (extractable, so it can be re-wrapped).
    return crypto.subtle.importKey(
      "raw", rawNote, { name: "AES-GCM" }, true, ["encrypt", "decrypt"]);
  }

  async function encryptField(key, plaintext) {
    var iv = crypto.getRandomValues(new Uint8Array(12));
    var ct = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv: iv }, key, encoder.encode(plaintext));
    return JSON.stringify({ v: 1, iv: bytesToB64(iv), ct: bytesToB64(ct) });
  }

  async function decryptField(key, envelope) {
    var obj = JSON.parse(envelope);
    var pt = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: b64ToBytes(obj.iv) }, key, b64ToBytes(obj.ct));
    return decoder.decode(pt);
  }

  async function makeKeyCheck(key) {
    return encryptField(key, SENTINEL);
  }

  async function verifyKeyCheck(key, keyCheck) {
    try {
      return (await decryptField(key, keyCheck)) === SENTINEL;
    } catch (e) {
      return false;  // wrong passphrase / tampered token
    }
  }

  window.NotesCrypto = {
    generateSalt: generateSalt,
    deriveKey: deriveKey,
    encryptField: encryptField,
    decryptField: decryptField,
    makeKeyCheck: makeKeyCheck,
    verifyKeyCheck: verifyKeyCheck,
    generateRecoveryKey: generateRecoveryKey,
    wrapKeyForRecovery: wrapKeyForRecovery,
    unwrapKeyFromRecovery: unwrapKeyFromRecovery,
    SENTINEL: SENTINEL,
  };
})();
