'use strict';
async function downloadAllData() {
  const button = document.getElementById('download-data');
  const status = document.getElementById('download-status');
  const error = document.getElementById('download-error');
  if (button.disabled) return;
  button.disabled = true;
  button.textContent = 'Preparing download…';
  status.textContent = 'Gathering your saved data…';
  error.textContent = '';
  try {
    const response = await fetch('/api/data/export', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
    });
    if (!response.ok) {
      let detail;
      try { detail = await response.json(); } catch {}
      throw new Error(detail?.error || detail?.log || 'Download unavailable. Restart Lens after updating, then try again.');
    }
    if (!response.headers.get('Content-Type')?.startsWith('application/zip')) {
      throw new Error('Lens returned an unexpected response. Restart Lens, then try again.');
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = response.headers.get('Content-Disposition')?.match(/filename="(lens-data-[\d-]+\.zip)"/)?.[1] || 'lens-data.zip';
    document.body.appendChild(link);
    try { link.click(); } finally {
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    }
    status.textContent = 'Download handed to your browser. Check your downloads to confirm it was saved.';
  } catch (e) {
    status.textContent = '';
    error.textContent = e.message || 'The download could not be prepared. Please try again.';
  } finally {
    button.disabled = false;
    button.textContent = 'Download all data';
  }
}

let dataGatewayBusy = false;
async function refreshDataGateway() {
  if (dataGatewayBusy || document.hidden) return;
  dataGatewayBusy = true;
  renderGatewayIndicator(null, true);
  try {
    const response = await fetch('/api/gateway', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error('Connection status unavailable. Restart Lens after updating.');
    renderGatewayIndicator(data.connection);
  } catch (e) {
    renderGatewayIndicator(null, false, e.message);
  } finally { dataGatewayBusy = false; }
}
document.getElementById('download-data').addEventListener('click', downloadAllData);
refreshDataGateway();
setInterval(refreshDataGateway, 30000);
window.addEventListener('focus', refreshDataGateway);

// Versioned encrypted envelope; see BACKUP-FORMAT.md. Keys never go to the server.
const MAX_BACKUP_BYTES = 256 * 1024 * 1024;
let backupState = null;
const backupNode = id => document.getElementById(id);
const backupHex = bytes => Array.from(bytes, n => n.toString(16).padStart(2, '0')).join('');
function recoveryText(key) {
  return 'LENS1-' + backupHex(key).toUpperCase().match(/.{8}/g).join('-');
}
async function encryptBackup(bytes, keyBytes, id) {
  if (bytes.byteLength > MAX_BACKUP_BYTES) throw new Error('This backup is too large for browser encryption (256 MB limit).');
  const header = new Uint8Array(36);
  header.set(new TextEncoder().encode('LENSBAK1'));
  header.set(id, 8);
  header.set(crypto.getRandomValues(new Uint8Array(12)), 24);
  const key = await crypto.subtle.importKey('raw', keyBytes, 'AES-GCM', false, ['encrypt']);
  const ciphertext = await crypto.subtle.encrypt({
    name: 'AES-GCM', iv: header.slice(24), additionalData: header, tagLength: 128
  }, key, bytes);
  return new Blob([header, ciphertext], {type: 'application/octet-stream'});
}
function offerBackupDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  try { link.click(); } finally {
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
}
function updateBackupButton() {
  backupNode('download-backup').disabled = !backupState || backupState.busy || !backupNode('recovery-confirmed').checked;
}
function clearBackup() {
  if (backupState?.busy) return;
  backupState?.key.fill(0);
  backupState = null;
  backupNode('recovery-key').value = '';
  backupNode('recovery-confirmed').checked = false;
  backupNode('backup-id').textContent = '';
  updateBackupButton();
}
function openBackup() {
  if (backupState?.busy || backupNode('backup-dialog').open) return;
  const pageStatus = backupNode('backup-page-status');
  pageStatus.textContent = '';
  if (!globalThis.crypto?.subtle) {
    pageStatus.textContent = 'Encrypted backup needs a browser with Web Crypto support. Open Lens at http://127.0.0.1:8642 in a current browser.';
    return;
  }
  clearBackup();
  const id = crypto.getRandomValues(new Uint8Array(16));
  backupState = {
    id, key: crypto.getRandomValues(new Uint8Array(32)), busy: false, blob: null,
    filename: `lens-backup-${new Date().toISOString().slice(0,10)}-${backupHex(id)}.lensbackup`
  };
  backupNode('recovery-key').value = recoveryText(backupState.key);
  backupNode('backup-id').textContent = 'Backup ID: ' + backupHex(id);
  for (const id of ['key-status', 'backup-status', 'backup-error']) backupNode(id).textContent = '';
  backupNode('download-backup').textContent = 'Download encrypted backup';
  backupNode('close-backup').textContent = 'Cancel';
  updateBackupButton();
  backupNode('backup-dialog').showModal();
}
async function copyRecoveryKey() {
  const state = backupState;
  if (!state) return;
  try {
    await navigator.clipboard.writeText(recoveryText(state.key));
    if (backupState === state) backupNode('key-status').textContent = 'Key copied. Save it in your password manager or another safe place.';
  } catch {
    if (backupState === state) backupNode('key-status').textContent = 'Copy isn’t available here. Select the key above to copy it manually, or download the key file.';
  }
}
function downloadRecoveryKey() {
  if (!backupState) return;
  const content = `LENS BACKUP RECOVERY KEY\n\nBackup: ${backupState.filename}\nBackup ID: ${backupHex(backupState.id)}\n\n${recoveryText(backupState.key)}\n\nKeep this key separately from the backup, ideally in your password manager.\nAnyone with both files can read the backup. Lens cannot replace a lost key.\nThis key works only with its matching backup. Backup import is not available yet.\n`;
  offerBackupDownload(new Blob([content], {type: 'text/plain;charset=utf-8'}), `lens-recovery-${backupHex(backupState.id)}.txt`);
  backupNode('key-status').textContent = 'Key file handed to your browser. Confirm it was saved, then store it separately from your backup.';
}
async function downloadEncryptedBackup() {
  if (!backupState || backupState.busy || !backupNode('recovery-confirmed').checked) return;
  const state = backupState;
  state.busy = true;
  updateBackupButton();
  backupNode('close-backup').disabled = true;
  backupNode('backup-error').textContent = '';
  backupNode('backup-status').textContent = 'Gathering and encrypting your saved data…';
  try {
    if (!state.blob) {
      const response = await fetch('/api/data/export', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
      });
      if (!response.ok) {
        let detail;
        try { detail = await response.json(); } catch {}
        throw new Error(detail?.error || detail?.log || 'Backup unavailable. Please try again.');
      }
      if (!response.headers.get('Content-Type')?.startsWith('application/zip')) {
        throw new Error('Lens returned an unexpected response. Restart Lens, then try again.');
      }
      if (Number(response.headers.get('Content-Length')) > MAX_BACKUP_BYTES) {
        await response.body?.cancel();
        throw new Error('This backup is too large for browser encryption (256 MB limit).');
      }
      const bytes = await response.arrayBuffer();
      try { state.blob = await encryptBackup(bytes, state.key, state.id); }
      finally { new Uint8Array(bytes).fill(0); }
    }
    offerBackupDownload(state.blob, state.filename);
    backupNode('backup-status').textContent = 'Encrypted backup handed to your browser. Check it was saved and keep its matching key separately.';
    backupNode('backup-page-status').textContent = 'Encrypted backup prepared. Check your browser downloads to confirm it was saved.';
  } catch (e) {
    backupNode('backup-status').textContent = '';
    backupNode('backup-error').textContent = e.message || 'Backup could not be created. Your saved data has not changed. Try again.';
  } finally {
    state.busy = false;
    backupNode('close-backup').disabled = false;
    backupNode('close-backup').textContent = state.blob ? 'Done' : 'Cancel';
    backupNode('download-backup').textContent = state.blob ? 'Download again' : 'Download encrypted backup';
    updateBackupButton();
  }
}
backupNode('create-backup').addEventListener('click', openBackup);
backupNode('copy-recovery').addEventListener('click', copyRecoveryKey);
backupNode('download-recovery').addEventListener('click', downloadRecoveryKey);
backupNode('recovery-confirmed').addEventListener('change', updateBackupButton);
backupNode('download-backup').addEventListener('click', downloadEncryptedBackup);
function closeBackup() {
  if (backupState?.busy) return;
  clearBackup();
  backupNode('backup-dialog').close();
}
backupNode('close-backup').addEventListener('click', closeBackup);
backupNode('backup-dialog').addEventListener('cancel', e => { e.preventDefault(); closeBackup(); });
backupNode('backup-dialog').addEventListener('close', () => {
  if (!backupNode('backup-dialog').open) clearBackup();
});
window.addEventListener('beforeunload', e => {
  if (backupState?.busy) { e.preventDefault(); e.returnValue = ''; }
});
