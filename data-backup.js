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
