"""Local activity records, never an authorization source or a broker connection."""
import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import device_auth
import workspace

ORDER_FIELDS = ('ticker', 'isin', 'side', 'qty', 'currency', 'limit_price')
RESULT_FIELDS = ('ticker', 'side', 'qty', 'status', 'filled', 'note')
PHASES = {'requested', 'completed', 'not_submitted', 'uncertain'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def fields(rows, keys):
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Invalid activity rows.')
    return [{k: row[k] for k in keys if k in row} for row in rows]


def begin(root, manifest, method):
    """Persist the request before execution. It does not prove broker acceptance."""
    rid = manifest['review_id']
    if not re.fullmatch(r'[a-f0-9]{32}', rid):
        raise ValueError('Invalid activity identifier.')
    record = dict(version=1, id=rid, kind='submission', created_at=stamp(),
                  phase='requested', account=manifest['account'],
                  broker_account=manifest['broker_account'], method=method,
                  orders=fields(manifest['orders'], ORDER_FIELDS), results=[])
    with workspace.LOCK:
        folder = Path(root)/'.workspace'/'activity'
        folder.mkdir(parents=True, exist_ok=True)
        # Preserve the previous version's last receipt before execution replaces it.
        previous = Path(root)/f"orders_result.{manifest['account']}.json"
        if previous.exists():
            try:
                results = fields(read_json(previous), RESULT_FIELDS)
                known = []
                for saved in folder.glob('*.json'):
                    try:
                        old_record = read_json(saved)
                        if old_record.get('account') == manifest['account']:
                            known.append(old_record.get('results'))
                    except (OSError, ValueError, AttributeError): pass
                if results and results not in known:
                    date = datetime.fromtimestamp(previous.stat().st_mtime, timezone.utc).isoformat()
                    old_id = hashlib.sha256(json.dumps([manifest['account'], date, results], sort_keys=True).encode()).hexdigest()[:32]
                    old = dict(version=1, id=old_id, kind='receipt', created_at=date,
                        phase='completed', account=manifest['account'], estimated_date=True, orders=[], results=results)
                    device_auth.atomic_json(folder/(old_id+'.json'), old)
            except (ValueError, TypeError, AttributeError):
                # A corrupt old receipt cannot be represented as a successful trade.
                # Keep its bytes in place by refusing to overwrite it with a new run.
                raise ValueError('The previous receipt could not be archived.')
        path = folder/(rid+'.json')
        if path.exists(): raise ValueError('This submission is already recorded.')
        device_auth.atomic_json(path, record)
    return record


def finish(root, record, ok, not_submitted, results):
    record = dict(record, phase='not_submitted' if not_submitted else 'completed' if ok else 'uncertain',
                  updated_at=stamp(), results=fields(results, RESULT_FIELDS))
    with workspace.LOCK:
        device_auth.atomic_json(Path(root)/'.workspace'/'activity'/(record['id']+'.json'), record)


def read_json(path):
    return json.loads(path.read_text())


def timestamp(value):
    if not isinstance(value, str): raise ValueError('Missing date')
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None: date = date.replace(tzinfo=timezone.utc)
    return date.timestamp()


def listing(root, mode='all', limit=100, offset=0):
    if mode not in ('all', 'personal', 'paper', 'live'):
        raise ValueError('Choose all, personal, paper or live activity.')
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise ValueError('Invalid activity page.')
    root = Path(root)
    entries, warnings = [], []
    with workspace.LOCK:
        folder = root/'.workspace'/'activity'
        for path in sorted(folder.glob('*.json')):
            try:
                if path.is_symlink(): raise ValueError('Linked record')
                r = read_json(path)
                if (r['version'] != 1 or r['kind'] not in ('submission', 'receipt') or r['phase'] not in PHASES
                    or r['account'] not in ('paper', 'live') or r['id'] != path.stem):
                    raise ValueError('Invalid record')
                if r['kind'] == 'submission' and (r.get('method') not in ('pin', 'device')
                    or not isinstance(r.get('broker_account'), str) or not r['broker_account']):
                    raise ValueError('Invalid submission identity')
                timestamp(r['created_at'])
                # Explicit projection: activity never exposes credentials or approval data.
                entries.append(dict(id=r['id'], kind=r['kind'], created_at=r['created_at'], estimated_date=bool(r.get('estimated_date')),
                    updated_at=r.get('updated_at'), account=r['account'], phase=r['phase'],
                    broker_account=r.get('broker_account'), method=r.get('method'),
                    orders=fields(r['orders'], ORDER_FIELDS), results=fields(r['results'], RESULT_FIELDS)))
            except (OSError, ValueError, TypeError, KeyError):
                warnings.append('A saved submission record could not be read. Your history may be incomplete.')
        for name, kind, date_key in [('profile', 'space', 'created_at'), ('portfolio', 'portfolio', 'saved_at'), ('xray', 'xray', None)]:
            path = root/'.workspace'/(name+'.json')
            if not path.exists(): continue
            try:
                data = read_json(path)
                if not isinstance(data, dict): raise ValueError('Invalid saved work')
                date = data.get(date_key) if date_key else None
                estimated = not date
                date = date or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
                timestamp(date)
                entries.append(dict(id=kind, kind=kind, account='personal', created_at=date, estimated_date=estimated))
            except (OSError, ValueError, TypeError):
                warnings.append('Some saved personal work could not be read.')
        # Earlier versions kept only one receipt per mode. Never invent earlier trades,
        # or associate that receipt with a possibly newer approval/account file.
        for account in ('paper', 'live'):
            path = root/f'orders_result.{account}.json'
            if not path.exists(): continue
            try:
                results = fields(read_json(path), RESULT_FIELDS)
                if results and not any(e.get('results') == results and e['account'] == account for e in entries):
                    entries.append(dict(id='legacy-'+account, kind='receipt', account=account,
                        created_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                        estimated_date=True, results=results, orders=[]))
            except (OSError, ValueError, TypeError):
                warnings.append(f'The latest {account} receipt could not be read.')
    entries.sort(key=lambda e: (timestamp(e['created_at']), e['id']), reverse=True)
    selected = [e for e in entries if mode == 'all' or e['account'] == mode]
    return dict(ok=True, entries=selected[offset:offset+limit], total=len(selected),
                next_offset=offset+limit if len(selected) > offset+limit else None,
                warnings=sorted(set(warnings)))
