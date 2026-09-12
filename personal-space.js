/* Local profile only. This page never calls a broker or submits orders. */
const spaceNode = id => document.getElementById(id);
async function spaceApi(action, payload = {}) {
  const response = await fetch('/api/space/' + action, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok || !data.ok) throw Error(data.error || data.log || 'Could not open your space. Try again.');
  return data;
}
function renderSpace(data, focus = false) {
  const profile = data.profile;
  spaceNode('welcome').hidden = !!profile;
  spaceNode('home').hidden = !profile;
  if (profile) {
    spaceNode('home-title').textContent = profile.first_name ? 'Welcome back, ' + profile.first_name + '.' : 'Welcome back.';
    spaceNode('edit-name').value = profile.first_name;
    const summary = data.summary;
    spaceNode('portfolio-tag').textContent = summary.portfolio_saved ? 'Saved research portfolio' : 'From your operating manual';
    spaceNode('portfolio-summary').textContent = summary.portfolio_saved
      ? summary.fund_count + ' investment' + (summary.fund_count === 1 ? '' : 's') + ' in your saved portfolio. Continue your research or revisit your X-Ray.'
      : 'Start with the investments in your operating manual. Save your research portfolio to make it your own.';
    const date = summary.saved_at ? new Date(summary.saved_at) : null;
    const validDate = date && !Number.isNaN(date.getTime());
    spaceNode('portfolio-time').hidden = !validDate;
    spaceNode('portfolio-time').textContent = validDate ? 'Saved ' + date.toLocaleString(undefined, {dateStyle:'medium', timeStyle:'short'}) : '';
    spaceNode('manual-link').hidden = !summary.manual_available;
    spaceNode('manual-missing').hidden = summary.manual_available;
  }
  if (focus) spaceNode(profile ? 'home-title' : 'welcome-title').focus();
}
async function loadSpace() {
  spaceNode('space-loading').hidden = false;
  spaceNode('space-error').textContent = '';
  spaceNode('load-recovery').hidden = true;
  try { renderSpace(await spaceApi('bootstrap')); }
  catch (error) {
    spaceNode('space-error').textContent = error.message;
    spaceNode('load-recovery').hidden = false;
  } finally { spaceNode('space-loading').hidden = true; }
}
async function saveSpace(event, action, inputId, buttonId) {
  event.preventDefault();
  const button = spaceNode(buttonId);
  if (button.disabled) return;
  button.disabled = true;
  spaceNode('space-error').textContent = '';
  spaceNode('profile-status').textContent = '';
  try {
    renderSpace(await spaceApi(action, {first_name: spaceNode(inputId).value}), action === 'create');
    if (action === 'update') spaceNode('profile-status').textContent = 'Name saved on this computer.';
  } catch (error) { spaceNode('space-error').textContent = error.message; }
  finally { button.disabled = false; }
}
spaceNode('create-space').addEventListener('submit', event => saveSpace(event, 'create', 'first-name', 'create-button'));
spaceNode('edit-profile').addEventListener('submit', event => saveSpace(event, 'update', 'edit-name', 'save-profile'));
spaceNode('retry-load').addEventListener('click', loadSpace);
// Preserve bookmarks from when the research workspace lived at the root URL.
if (['#portfolio', '#xray', '#sources'].includes(location.hash)) {
  location.replace('/workspace' + location.hash);
} else {
  loadSpace();
}
