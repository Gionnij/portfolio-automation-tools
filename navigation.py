"""Shared page composition and canonical destinations; no account mutations."""
import re

PAGES = {
    '/': 'personal-space.html', '/portfolio': 'workspace.html',
    '/portfolio/holdings': 'investing.html', '/invest': 'investing.html',
    '/invest/rules': 'profile.html', '/profile': 'profile.html',
    '/profile/activity': 'activity.html', '/profile/data': 'data-backup.html',
    '/profile/data/sources': 'workspace.html', '/profile/settings': 'device-approval.html',
    '/profile/settings/appearance': 'profile.html', '/profile/settings/connections': 'profile.html',
    '/setup': 'device-approval.html',
}
ALIASES = {'/index.html': '/', '/workspace': '/portfolio', '/rebalance': '/invest',
           '/activity': '/profile/activity', '/data-backup': '/profile/data',
           '/device-approval': '/profile/settings', '/manual': '/invest/rules'}


def links(items, current, label, css='lens-tabs'):
    return '<nav class="'+css+'" aria-label="'+label+'">'+''.join(
        '<a href="'+url+'"'+(' class="active" aria-current="page"' if key == current else '')+'>'+name+'</a>'
        for url, name, key in items)+'</nav>'


def header(route):
    refresh = 'refreshGateway()' if route in ('/invest', '/portfolio/holdings') else 'loadHoldings()' if route == '/portfolio' else 'refreshLensConnection()'
    tools = """<button type="button" data-idle onclick="document.getElementById('lens-menu').open=false;openTools()">Account tools</button>""" if route in ('/invest', '/portfolio/holdings') else ''
    return f"""<header class="lens-global-header" aria-label="Account and appearance">
<details class="gateway-menu" id="gateway-menu" data-state="checking"><summary class="gateway-toggle" id="gateway-toggle" aria-label="IBKR connection details"><span class="gateway-dot" aria-hidden="true"></span><span id="account-label" aria-live="polite">Checking account…</span><span class="gateway-chevron" aria-hidden="true">⌄</span></summary>
<div class="gateway-panel"><p class="eyebrow">IBKR Gateway</p><strong id="gateway-title">Checking IB Gateway…</strong><p id="gateway-detail">Lens follows the account connected in IB Gateway.</p><p id="gateway-issue" hidden></p><p id="live-strip" class="gateway-live-note" hidden>Live account · real money. Approved orders go to your live IBKR account.</p><button id="gateway-refresh" type="button" onclick="{refresh}">Refresh connection</button><details><summary>Connection &amp; account switching</summary><p>Sign in to IB Gateway. Keep one Gateway connected. To switch between Live and Paper, switch accounts in Gateway; Lens follows automatically.</p><p>Live normally uses port 4001; Paper uses port 4002. Enable socket clients in Gateway’s API settings and allow this computer.</p><p>Read-Only API allows viewing. Turn it off in Gateway only when you want to submit reviewed orders.</p></details></div></details>
<details class="lens-menu" id="lens-menu"><summary id="lens-menu-toggle" aria-label="Appearance and app options">•••</summary><div class="lens-menu-panel"><label for="theme-select">Appearance</label><select id="theme-select" class="theme-select" aria-label="Color theme"><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select>{tools}</div></details>
</header>"""


def remove_topbar(source):
    """Remove a page's old header without consuming adjacent page content."""
    start = source.find('<div class="topbar">')
    if start < 0:
        return source
    depth = 0
    for match in re.finditer(r'</?div\b[^>]*>', source[start:]):
        depth += -1 if match.group().startswith('</') else 1
        if depth == 0:
            return source[:start] + source[start + match.end():]
    raise ValueError('Unclosed page topbar')


def render(source, route):
    section = 'portfolio' if route.startswith('/portfolio') else 'settings' if route.startswith('/profile') or route == '/invest/rules' else 'invest' if route == '/invest' else 'home'
    nav = links([('/', 'Home', 'home'),('/portfolio/holdings', 'Portfolio', 'portfolio'),('/invest', 'Invest', 'invest'),('/profile', 'Settings', 'settings')], section, 'Main navigation', 'nav')
    sidebar = '<aside class="sidebar lens-sidebar"><a class="brand" href="/" aria-label="Lens home"><span class="brandmark" aria-hidden="true"></span>lens<span class="brand-dot">.</span></a><div class="nav-label">YOUR SPACE</div>'+nav+'<div class="lens-profile"><span id="lens-avatar" aria-hidden="true">◦</span><strong id="lens-profile-name">Your profile</strong></div></aside>'
    source = re.sub(r'<aside class="sidebar"[\s\S]*?</aside>', sidebar, source, count=1)
    title = {'/': 'Home', '/portfolio': 'Portfolio breakdown', '/portfolio/holdings': 'Holdings', '/invest': 'Investment plan', '/invest/rules': 'Investing rules', '/profile': 'Settings', '/profile/activity': 'Activity', '/profile/data': 'My data', '/profile/data/sources': 'Data sources', '/profile/settings': 'Security', '/profile/settings/appearance': 'Appearance', '/profile/settings/connections': 'Connections', '/setup': 'Set up Lens'}[route]
    source = re.sub(r'<title>.*?</title>', '<title>'+title+' · Lens</title>', source, count=1)
    source = source.replace('<body', '<body data-lens-route="'+route+'"', 1)
    source = remove_topbar(source)
    source = source.replace('<script src="/shell.js"></script>', '')
    source = source.replace('</head>', '<link rel="stylesheet" href="/navigation.css"><script src="/shell.js"></script></head>')
    source = source.replace('</body>', '<script src="/navigation.js"></script></body>')
    for old,new in ALIASES.items():
        source = source.replace('href="'+old+'"','href="'+new+'"')
    source = source.replace('href="/workspace#portfolio"','href="/portfolio/holdings"').replace('href="/workspace#xray"','href="/portfolio#xray"').replace('href="/workspace#sources"','href="/profile/data/sources"')
    intro = ''
    if section == 'settings':
        current = 'rules' if route == '/invest/rules' else 'activity' if '/activity' in route else 'data' if '/data' in route else 'security' if '/settings' in route else 'profile'
        intro = '<header class="lens-page-heading"><h1>Settings</h1></header>'
        intro += links([('/profile','Profile','profile'),('/profile/settings','Security','security'),('/profile/activity','Activity','activity'),('/profile/data','My data','data'),('/invest/rules','Investing rules','rules')],current,'Settings sections')
        if current == 'data':
            intro += links([('/profile/data','Backups','backups'),('/profile/data/sources','Data sources','sources')], 'sources' if route.endswith('/sources') else 'backups','My data sections','lens-subtabs')
    elif route == '/portfolio/holdings':
        intro = '<header class="lens-page-heading"><h1>Holdings</h1><p>What you own</p></header>' + links([('/portfolio/holdings','Holdings','holdings'),('/portfolio#xray','Portfolio breakdown','xray')],'holdings','Portfolio sections')
    elif route == '/invest':
        intro = '<header class="lens-page-heading"><h1>Invest</h1></header>'
    source = source.replace('<main class="main">','<main class="main">'+header(route)+intro,1)
    return source
