/* Apply before the page paints, then keep the preference in sync across tabs. */
(() => {
  const key = 'lens-theme';
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  const valid = value => ['light', 'dark'].includes(value) ? value : 'system';
  let preference = 'system';
  try { preference = valid(localStorage.getItem(key)); } catch (_) {}
  function apply() {
    document.documentElement.dataset.theme = preference === 'system'
      ? (system.matches ? 'dark' : 'light') : preference;
    const select = document.getElementById('theme-select');
    if (select) select.value = preference;
  }
  apply();
  system.addEventListener('change', apply);
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) {
      preference = valid(event.newValue);
      apply();
    }
  });
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.getElementById('theme-select')?.addEventListener('change', event => {
      preference = valid(event.target.value);
      try { localStorage.setItem(key, preference); } catch (_) {}
      apply();
    });
  });
})();
