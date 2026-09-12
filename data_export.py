"""Portable export of Lens-owned data. Never exports code, PINs or credentials."""
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT_FILES = {
    'manual.json', 'portfolio_operating_manual.md', 'portfolio.xlsx',
    'prices.csv', 'xray_report.xlsx', 'report.html',
}
RECORD = re.compile(
    r'(?:state(?:\.[\w-]+)*\.(?:json|pending)|'
    r'orders(?:_approved|_result)?(?:\.[\w-]+)*\.json|'
    r'prep_report(?:\.[\w-]+)*\.md|(?:positions|pos)[\w.-]*\.csv)\Z')
WORKSPACE_FILE = re.compile(
    r'(?:profile|portfolio|xray|identities|manual|holdings(?:\.(?:live|paper))?)\.json\Z|'
    r'[A-Z]{2}[A-Z0-9]{9}[0-9]\.(?:csv|json)\Z')


def export_paths(root):
    """Use an allowlist; never follow a directory or file symlink."""
    for folder, dirs, files in os.walk(root, followlinks=False):
        relative = Path(folder).relative_to(root)
        if relative == Path('.'):
            dirs[:] = sorted(d for d in dirs if d in ('.workspace', 'holdings'))
        else:
            dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        if any((Path(folder) / name).is_symlink() for name in dirs):
            raise ValueError('A saved data folder is a symbolic link. Move it into the Lens folder before exporting.')
        for name in sorted(files):
            path = Path(folder) / name
            if relative == Path('.'):
                include = name in ROOT_FILES or bool(RECORD.fullmatch(name))
            elif relative == Path('.workspace/activity'):
                include = bool(re.fullmatch(r'[a-f0-9]{32}\.json', name))
            elif relative.parts[0] == '.workspace':
                include = bool(WORKSPACE_FILE.fullmatch(name))
            else:
                include = (not name.startswith('.') and
                           path.suffix.lower() in ('.csv', '.xlsx', '.xls', '.json'))
                if re.search(r'(?i)(credential|password|secret|token|^pin[.])', name):
                    include = False
            if include:
                yield path


def build_export(root):
    """Caller holds the investing and workspace locks during the snapshot.

    Returns an open, rewound temporary ZIP and its download name. No persistent
    export copy is left in the app. This is an export, not a restorable snapshot
    of a running broker session; command-line/external writers are not locked.
    """
    root = Path(root).resolve()
    created = datetime.now(timezone.utc)
    output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    entries = []
    try:
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(export_paths(root)):
                relative = path.relative_to(root).as_posix()
                # Refuse a partial export if a selected data file is unsafe.
                if any(p.is_symlink() for p in (path, *path.parents) if p != root):
                    raise ValueError('A saved data file is a symbolic link. Move it into the Lens folder before exporting.')
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, 'rb') as source:
                    before = os.fstat(source.fileno())
                    if not stat.S_ISREG(before.st_mode):
                        raise ValueError('Only regular data files can be exported.')
                    digest = hashlib.sha256()
                    size = 0
                    with archive.open('data/' + relative, 'w', force_zip64=True) as target:
                        while chunk := source.read(1024 * 1024):
                            target.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                    after = os.fstat(source.fileno())
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError('Saved data changed during export. Wait for other work to finish and try again.')
                    entries.append({'path': 'data/' + relative, 'bytes': size, 'sha256': digest.hexdigest()})
            archive.writestr('manifest.json', json.dumps({
                'format': 'lens-data-export', 'version': 1,
                'created_at': created.isoformat(timespec='seconds'),
                'encrypted': False, 'file_count': len(entries), 'files': entries,
                'scope': 'All recognized saved Lens data in this installation, including live, paper and legacy records.',
                'excluded': ['PIN and credential files', 'Application code and Git history',
                             'Unsaved browser edits', 'Files outside this Lens installation',
                             'Broker records not saved in Lens'],
            }, indent=2) + '\n')
            archive.writestr('README.txt', (
                'LENS DATA EXPORT\n\n'
                'Your saved data is in data/, preserving its original folder structure.\n'
                'manifest.json lists every included file, its size and SHA-256 checksum.\n'
                'Includes your local profile, portfolio drafts, operating manual, investment\n'
                'records for live and paper accounts, reports and downloaded fund data.\n'
                'Only records still saved by Lens are available; this is not a complete\n'
                'broker statement or a history of every past trade.\n\n'
                'This ZIP is NOT encrypted and may contain account identifiers and balances.\n'
                'Keep it somewhere private. PINs and credential files are not included.\n'
                'Unsaved edits, broker-only records and files outside this installation\n'
                'are not included. Save your edits before downloading.\n\n'
                'Automatic restore is not implemented. Do not overwrite a running Lens\n'
                'installation with these files: historical orders and pending approvals\n'
                'are records, not instructions to execute. No broker session or trading\n'
                'authorization is transferred by this export.\n'
            ))
        output.seek(0)
        return output, created.strftime('lens-data-%Y-%m-%d-%H%M%S.zip')
    except Exception:
        output.close()
        raise
