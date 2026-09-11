"""Exports use synthetic data only; no broker connection or personal files."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import data_export
import webdash


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, name, value=b'example'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        return path

    def test_complete_inventory_and_exact_data_without_credentials(self):
        included = ['portfolio.xlsx', 'manual.json', 'portfolio_operating_manual.md',
                    'state.live.json', 'state.paper.pending', 'state.undo.json',
                    'orders.live.json', 'orders_approved.paper.json', 'orders_result.json',
                    'prep_report.live.md', 'prices.csv', 'positions-demo.csv',
                    '.workspace/portfolio.json', '.workspace/identities.json', '.workspace/xray.json',
                    '.workspace/IE00B4K48X80.csv', '.workspace/IE00B4K48X80.json',
                    '.workspace/manual-v1-backup/manual.json', 'holdings/ETF.xlsx']
        excluded = ['.pin.json', '.env', '.git/config', 'webdash.py',
                    '.workspace/credentials.json', '.workspace/.secret/portfolio.json',
                    'holdings/passwords.csv', 'unrelated.json']
        for name in included + excluded:
            self.put(name, name.encode())
        output, filename = data_export.build_export(self.root)
        with output, zipfile.ZipFile(output) as archive:
            self.assertIsNone(archive.testzip())
            self.assertRegex(filename, r'^lens-data-\d{4}-\d{2}-\d{2}-\d{6}\.zip$')
            manifest = json.loads(archive.read('manifest.json'))
            self.assertFalse(manifest['encrypted'])
            self.assertEqual(manifest['file_count'], len(included))
            self.assertEqual(set(archive.namelist()), {'data/' + n for n in included} | {'README.txt', 'manifest.json'})
            for entry in manifest['files']:
                content = archive.read(entry['path'])
                self.assertEqual(content, entry['path'].removeprefix('data/').encode())
                self.assertEqual(entry['bytes'], len(content))
                self.assertEqual(entry['sha256'], hashlib.sha256(content).hexdigest())
        self.assertFalse(list(self.root.glob('*.zip')))

    def test_empty_installation_still_has_honest_inventory(self):
        output, _ = data_export.build_export(self.root)
        with output, zipfile.ZipFile(output) as archive:
            self.assertEqual(json.loads(archive.read('manifest.json'))['files'], [])

    def test_symlinked_data_is_refused(self):
        target = self.put('private.txt', b'secret')
        link = self.root / 'manual.json'
        link.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            data_export.build_export(self.root)
        link.unlink()
        (self.root / '.workspace').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            data_export.build_export(self.root)

    def request(self, path='/api/data/export', method='POST', origin=None, host=None):
        handler = object.__new__(webdash.Handler)
        handler.path = path
        handler.headers = {'Host': host or f'127.0.0.1:{webdash.SERVER_PORT}',
                           'Content-Type': 'application/json', 'Content-Length': '2'}
        if origin: handler.headers['Origin'] = origin
        handler.rfile, handler.wfile = io.BytesIO(b'{}'), io.BytesIO()
        codes, headers = [], {}
        handler.send_response = codes.append
        handler.send_header = lambda k, v: headers.update({k: v})
        handler.end_headers = lambda: None
        with patch.object(webdash, 'HERE', self.root), patch.object(webdash.gateway, 'status', side_effect=AssertionError('No broker reads')):
            getattr(handler, 'do_' + method)()
        return codes[-1], headers, handler.wfile.getvalue()

    def test_post_download_and_no_get_or_cross_origin_download(self):
        self.put('manual.json')
        code, headers, body = self.request()
        self.assertEqual(code, 200)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(int(headers['Content-Length']), len(body))
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(archive.read('data/manual.json'), b'example')
        self.assertEqual(self.request(method='GET')[0], 404)
        self.assertEqual(self.request(origin='https://untrusted.example')[0], 403)
        self.assertEqual(self.request(host='untrusted.example')[0], 403)

    def test_busy_and_export_failure_release_lock(self):
        with webdash.ACTION_LOCK:
            self.assertEqual(self.request()[0], 409)
        with patch.object(data_export, 'build_export', side_effect=OSError('Cannot read saved data')):
            self.assertEqual(self.request()[0], 500)
        self.assertFalse(webdash.ACTION_LOCK.locked())


if __name__ == '__main__':
    unittest.main()
