"""One remembered profile per local Lens installation; never an approval gate."""
import json
import unicodedata

import workspace


def first_name(value):
    if not isinstance(value, str):
        raise ValueError('Enter a first name, or leave it blank.')
    value = value.strip()
    if len(value) > 60 or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('Use up to 60 characters without control characters.')
    return value


def read_profile():
    path = workspace.DATA / 'profile.json'
    try:
        profile = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ValueError('Your local profile could not be read. Your portfolio is still available. Keep a backup before repairing the profile.') from exc
    if (not isinstance(profile, dict) or profile.get('version') != 1
            or not isinstance(profile.get('created_at'), str)
            or not isinstance(profile.get('first_name'), str)):
        raise ValueError('This local profile format is not supported. Your portfolio is still available.')
    first_name(profile['first_name'])
    if 'setup_complete' in profile and type(profile['setup_complete']) is not bool:
        raise ValueError('The setup state could not be read.')
    return dict({key: profile[key] for key in ('version', 'first_name', 'created_at')},
                setup_complete=profile.get('setup_complete', True))


def summary():
    # Local reads only. Research drafts and the investing policy remain separate.
    draft = workspace.read_json(workspace.DATA / 'portfolio.json', None)
    saved = isinstance(draft, dict) and isinstance(draft.get('rows'), list)
    manual = workspace.read_json(workspace.HERE / 'manual.json', {})
    sleeves = manual.get('sleeves', {}) if isinstance(manual, dict) else {}
    return {'portfolio_saved': saved,
            'fund_count': len(draft['rows']) if saved else len(sleeves) if isinstance(sleeves, dict) else 0,
            'saved_at': draft.get('saved_at') if saved else None,
            'manual_available': (workspace.HERE / 'portfolio_operating_manual.md').is_file()}


def api(action, payload):
    # Share the export/workspace lock so backups capture complete profile writes.
    with workspace.LOCK:
        profile = read_profile()
        if action == 'bootstrap':
            return {'ok': True, 'profile': profile, 'summary': summary()}
        if action not in ('create', 'update', 'complete-setup'):
            raise ValueError('Unknown personal space action.')
        name = first_name(payload.get('first_name', ''))
        if action == 'create':
            if profile is not None:
                raise ValueError('A space already exists. Reload to open it.')
            profile = {'version': 1, 'first_name': name, 'created_at': workspace.now(), 'setup_complete': False}
        else:
            if profile is None:
                raise ValueError('Create your space first.')
            if action == 'complete-setup': profile['setup_complete'] = True
            else: profile['first_name'] = name
        workspace.atomic_json(workspace.DATA / 'profile.json', profile)
        return {'ok': True, 'profile': profile, 'summary': summary()}
