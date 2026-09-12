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
  if(profile && profile.setup_complete === false){location.replace('/setup');return}
  spaceNode('welcome').hidden = !!profile;
  spaceNode('home').hidden = !profile;
  if (profile) {
    spaceNode('home-title').textContent = profile.first_name ? 'Welcome back, ' + profile.first_name + '.' : 'Welcome back.';
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
  try {
    renderSpace(await spaceApi(action, {first_name: spaceNode(inputId).value}), action === 'create');
  } catch (error) { spaceNode('space-error').textContent = error.message; }
  finally { button.disabled = false; }
}
spaceNode('create-space').addEventListener('submit', event => saveSpace(event, 'create', 'first-name', 'create-button'));
spaceNode('retry-load').addEventListener('click', loadSpace);
// Preserve bookmarks from when the research workspace lived at the root URL.
if (['#portfolio', '#xray', '#sources'].includes(location.hash)) {
  location.replace(location.hash==='#sources'?'/profile/data/sources':'/portfolio'+location.hash);
} else {
  loadSpace();
}
