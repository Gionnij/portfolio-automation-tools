"""Profile persistence uses temporary synthetic data, with no broker access."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import personal_space as space
import workspace
import webdash


class PersonalSpaceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / '.workspace'
        for target, name, value in [(workspace, 'HERE', self.root), (workspace, 'DATA', self.data)]:
            p = patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(webdash.gateway, 'status', side_effect=AssertionError('No broker reads'))
        p.start()
        self.addCleanup(p.stop)

    def test_first_visit_creates_nothing_and_blank_name_is_remembered(self):
        self.assertIsNone(space.api('bootstrap', {})['profile'])
        self.assertFalse(self.data.exists())
        created = space.api('create', {'first_name': '  '})['profile']
        self.assertEqual(created['first_name'], '')
        self.assertEqual(space.api('bootstrap', {})['profile'], created)
        self.assertEqual((self.data/'profile.json').stat().st_mode & 0o777, 0o600)

    def test_existing_data_is_preserved_and_name_can_be_changed_or_removed(self):
        self.data.mkdir()
        files = {self.data/'portfolio.json': {'rows': [{'ticker': 'TEST'}], 'saved_at': '2026-09-12T10:00:00Z'},
                 self.root/'manual.json': {'sleeves': {'TEST': {}}},
                 self.root/'orders_approved.paper.json': {'sentinel': True}}
        for path, value in files.items(): path.write_text(json.dumps(value))
        before = {path: path.read_bytes() for path in files}
        created = space.api('create', {'first_name': '  Zoë  ', 'approved': True})
        self.assertTrue(created['summary']['portfolio_saved'])
        self.assertEqual(created['summary']['fund_count'], 1)
        self.assertEqual(created['profile']['first_name'], 'Zoë')
        self.assertNotIn('approved', created['profile'])
        for name in ['Giovanni', '']:
            updated = space.api('update', {'first_name': name})['profile']
            self.assertEqual(updated['first_name'], name)
            self.assertEqual(updated['created_at'], created['profile']['created_at'])
        self.assertEqual(before, {path: path.read_bytes() for path in files})

    def test_creation_cannot_overwrite_an_existing_or_corrupt_profile(self):
        space.api('create', {})
        path = self.data/'profile.json'
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            space.api('create', {'first_name': 'Other'})
        self.assertEqual(path.read_bytes(), original)
        for raw in ['broken', '[]', '{"version":2}', '{"version":1,"first_name":null,"created_at":"now"}']:
            path.write_text(raw)
            for action in ['bootstrap', 'create', 'update']:
                with self.assertRaises(ValueError): space.api(action, {})
            self.assertEqual(path.read_text(), raw)

    def test_validation_and_failed_write_leave_saved_profile_intact(self):
        with self.assertRaisesRegex(ValueError, 'Create your space first'):
            space.api('update', {})
        space.api('create', {'first_name': 'Original'})
        for value in [None, [], 123, 'x'*61, 'a\nb', 'a\x00b']:
            with self.assertRaises(ValueError): space.api('update', {'first_name': value})
        with patch.object(workspace, 'atomic_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): space.api('update', {'first_name': 'New'})
        self.assertEqual(space.api('bootstrap', {})['profile']['first_name'], 'Original')

    def request(self, action, payload, origin=None):
        handler = object.__new__(webdash.Handler)
        handler.path = '/api/space/' + action
        body = json.dumps(payload).encode()
        handler.headers = {'Host': f'127.0.0.1:{webdash.SERVER_PORT}', 'Content-Type': 'application/json',
                           'Content-Length': str(len(body))}
        if origin: handler.headers['Origin'] = origin
        handler.rfile, handler.wfile = io.BytesIO(body), io.BytesIO()
        codes, headers = [], {}
        handler.send_response = codes.append
        handler.send_header = lambda key, value: headers.update({key: value})
        handler.end_headers = lambda: None
        handler.do_POST()
        return codes[-1], headers, json.loads(handler.wfile.getvalue())

    def test_http_origin_validation_and_persistence(self):
        self.assertEqual(self.request('create', {}, 'https://untrusted.example')[0], 403)
        self.assertFalse(self.data.exists())
        self.assertEqual(self.request('create', {'first_name': 'Ada'})[0], 200)
        code, headers, body = self.request('bootstrap', {})
        self.assertEqual((code, headers['Cache-Control'], body['profile']['first_name']), (200, 'no-store', 'Ada'))
        self.assertEqual(self.request('update', {'first_name': 12})[0], 400)


if __name__ == '__main__':
    unittest.main()
