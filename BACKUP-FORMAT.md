# Lens encrypted backup, version 1

Creation is available under Data & backup. Import is intentionally not implemented.
An encrypted backup contains the same ZIP produced by `/api/data/export`, including
the manifest and all its exclusions. No saved file is changed by backup creation.

## Encryption and recovery

The browser generates a fresh random 32-byte key and 16-byte backup ID with
`crypto.getRandomValues`. The key is displayed as `LENS1-` followed by eight groups
of eight uppercase hexadecimal digits, separated by hyphens. Remove that prefix
and the hyphens, then hex-decode the remaining 64 digits to recover the AES key.
This is a random key, not a user password; no password derivation is used.

The application uses Web Crypto AES-256-GCM with a random 12-byte IV and a 128-bit
authentication tag. The entire header is authenticated as additional data.
See [Web Crypto AES-GCM parameters](https://developer.mozilla.org/en-US/docs/Web/API/AesGcmParams).

The binary `.lensbackup` layout is:

| Byte offset | Length | Content |
| --- | --- | --- |
| 0 | 8 | ASCII `LENSBAK1` (format/version marker) |
| 8 | 16 | Random backup ID |
| 24 | 12 | Random IV |
| 36 | remaining | AES-GCM ciphertext followed by its 16-byte tag |

The exact first 36 bytes are the GCM additional authenticated data. The plaintext
is the original export ZIP, unchanged. Its internal manifest's `encrypted: false`
describes that inner ZIP, not this encrypted envelope. No key is stored in the
envelope. The filename includes the date and the full backup ID in lowercase hex.
The optional recovery text file includes that filename, ID and the formatted key.

Every new dialog creates a new key and ID. An export/encryption retry uses a fresh
IV. Re-downloading a completed backup reuses the same encrypted bytes. Keys exist
in page memory only; the app sends none to its server or browser storage. Closing
the dialog clears its fields and drops the key/backup references. This does not
promise secure erasure of JavaScript memory, the clipboard, or downloaded files.

## Boundaries

- The user must acknowledge saving the key before encryption/download. A download
  handoff is not proof that the browser saved the file or that a separate copy exists.
- A key file is plaintext. Keep it separately from the backup. Losing the key makes
  that backup unrecoverable by Lens. Each backup needs its own matching key.
- Browser encryption requires Web Crypto (available on supported localhost browsers).
  There is no unencrypted fallback for the encrypted-backup button.
- The existing export travels from the loopback server to the browser unencrypted;
  encryption protects the downloaded backup, not the app's original local files.
- One-shot Web Crypto processes the export in memory. Backups above 256 MiB are
  refused before encryption; larger datasets need a future streaming format.
- A future importer must authenticate/decrypt the entire envelope before parsing
  the ZIP, enforce archive/path/size/schema checks, and never restore pending trading
  authorizations or replay historical orders. It must reconcile state with the broker.
