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


def render(source, route):
    section = 'portfolio' if route.startswith('/portfolio') else 'invest' if route.startswith('/invest') else 'profile' if route.startswith('/profile') else 'home'
    nav = links([('/', 'Home', 'home'),('/portfolio/holdings', 'Portfolio', 'portfolio'),('/invest', 'Invest', 'invest')], section, 'Main navigation', 'nav')
    sidebar = '<aside class="sidebar lens-sidebar"><a class="brand" href="/" aria-label="Lens home"><span class="brandmark" aria-hidden="true"></span>lens<span class="brand-dot">.</span></a><div class="nav-label">YOUR SPACE</div>'+nav+'<a class="lens-profile'+(' active' if section=='profile' else '')+'" href="/profile"'+(' aria-current="page"' if section=='profile' else '')+'><span id="lens-avatar" aria-hidden="true">◦</span><span><strong id="lens-profile-name">Your profile</strong><small>Activity, data & settings</small></span></a></aside>'
    source = re.sub(r'<aside class="sidebar"[\s\S]*?</aside>', sidebar, source, count=1)
    title = {'/': 'Home', '/portfolio': 'Portfolio', '/portfolio/holdings': 'Holdings', '/invest': 'Invest', '/invest/rules': 'Investing rules', '/profile': 'Your profile', '/profile/activity': 'Activity', '/profile/data': 'My data', '/profile/data/sources': 'Data sources', '/profile/settings': 'Security', '/profile/settings/appearance': 'Appearance', '/profile/settings/connections': 'Connections', '/setup': 'Set up your space'}[route]
    source = re.sub(r'<title>.*?</title>', '<title>'+title+' · Lens</title>', source, count=1)
    source = source.replace('<body', '<body data-lens-route="'+route+'"', 1)
    source = source.replace('</head>', '<link rel="stylesheet" href="/navigation.css"></head>')
    source = source.replace('</body>', '<script src="/navigation.js"></script></body>')
    # Canonical links; route aliases remain available for old bookmarks.
    for old,new in ALIASES.items():
        source = source.replace('href="'+old+'"','href="'+new+'"')
    source = source.replace('href="/workspace#portfolio"','href="/portfolio#portfolio"').replace('href="/workspace#xray"','href="/portfolio#xray"').replace('href="/workspace#sources"','href="/profile/data/sources"')
    intro = ''
    if section == 'profile':
        current = 'activity' if '/activity' in route else 'data' if '/data' in route else 'settings' if '/settings' in route else 'details'
        intro = '<header class="lens-profile-heading"><p class="lens-eyebrow">Your personal space</p><h1 id="lens-heading-name">Your profile</h1></header>'
        intro += links([('/profile','Details','details'),('/profile/activity','Activity','activity'),('/profile/data','My data','data'),('/profile/settings','Settings','settings')],current,'Profile sections')
        if current == 'data':
            intro += links([('/profile/data','Backups','backups'),('/profile/data/sources','Data sources','sources')], 'sources' if route.endswith('/sources') else 'backups','My data sections','lens-subtabs')
        if current == 'settings':
            intro += links([('/profile/settings','Security','security'),('/profile/settings/appearance','Appearance','appearance'),('/profile/settings/connections','Connections','connections')],route.rsplit('/',1)[-1] if route != '/profile/settings' else 'security','Settings sections','lens-subtabs')
    elif route == '/portfolio/holdings':
        intro = '<header class="lens-page-heading"><p class="lens-eyebrow">Your portfolio</p><h1>What you own.</h1></header>' + links([('/portfolio/holdings','Holdings','holdings'),('/portfolio#portfolio','Research','research'),('/portfolio#xray','X-Ray','xray')],'holdings','Portfolio sections')
        intro += '<p class="lens-shortcut"><a href="/profile/data/sources">Data sources ↗</a></p>'
    elif route == '/invest/rules':
        intro = '<header class="lens-page-heading"><p class="lens-eyebrow">Invest</p><h1>Your investing rules.</h1></header>'+links([('/invest','This month','plan'),('/invest/rules','Investing rules','rules')],'rules','Invest sections')
    if intro:
        source = source.replace('<main class="main">','<main class="main">'+intro,1)
    return source
