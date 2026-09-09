"""Operating-manual checks shared by research and monthly investing."""


def allocation_checks(cfg, rows, holdings):
    rules = cfg.get('rules', {})
    weights = {r['isin']: r['weight'] for r in rows}
    checks = []
    def add(label, value, limit, minimum=False, estimate=False):
        within = value >= limit - 1e-9 if minimum else value <= limit + 1e-9
        checks.append(dict(label=label, value=value, limit=limit,
                           relation='≥' if minimum else '≤',
                           status='CHECK' if not within else 'ESTIMATE' if estimate else 'PASS'))
    if 'max_lines' in rules:
        add('Positions', len(rows), rules['max_lines'])
    if 'us_direct_floor_pct' in rules:
        direct = sum(weights.get(cfg['sleeves'][t]['isin'], 0)
                     for t in rules['us_direct_tickers'] if t in cfg['sleeves'])
        add('Direct US funds', direct, rules['us_direct_floor_pct'], minimum=True)
    for key, label, country, minimum in (
            ('us_equity_floor_pct', 'US equity look-through', 'United States', True),
            ('china_cap_pct', 'China look-through', 'China', False)):
        if key in rules:
            value = sum(h['weight'] for h in holdings
                        if h['country'] == country and (not minimum or h['bucket'] == 'Equity'))
            add(label, value, rules[key], minimum=minimum, estimate=True)
    return checks
