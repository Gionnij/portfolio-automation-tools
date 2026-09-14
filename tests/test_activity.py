"""Activity is local evidence only; all trade execution is mocked."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import activity
import data_export
import webdash
import test_investing


def manifest(rid='a'*32, account='paper'):
    return dict(review_id=rid, account=account, broker_account='DU123' if account=='paper' else 'U123',
        orders=[dict(ticker='TEST', side='BUY', qty='2', limit_price='25', currency='EUR',
                     order_ref='private-ref', challenge='secret')], credential='secret')


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_empty_read_creates_nothing_and_never_contacts_broker(self):
        with patch.object(webdash.gateway,'status',side_effect=AssertionError('No broker calls')):
            self.assertEqual(activity.listing(self.root)['entries'],[])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_requests_survive_restart_and_no_approval_secrets_are_exposed(self):
        r=activity.begin(self.root,manifest(),'device')
        path=self.root/'.workspace/activity'/('a'*32+'.json')
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        self.assertNotIn('secret',path.read_text());self.assertNotIn('order_ref',path.read_text())
        self.assertEqual(activity.listing(self.root)['entries'][0]['phase'],'requested')
        results=[dict(ticker='TEST',side='BUY',qty=2,status='working',filled=0)]
        activity.finish(self.root,r,True,False,results)
        self.assertEqual(activity.listing(self.root)['entries'][0]['results'][0]['status'],'working')
        with self.assertRaises(ValueError):activity.begin(self.root,manifest(),'device')

    def test_old_receipt_preserved_and_current_receipt_not_duplicated(self):
        old=[dict(ticker='OLD',side='SELL',qty=1,status='filled',filled=1)]
        path=self.root/'orders_result.paper.json';path.write_text(json.dumps(old))
        r=activity.begin(self.root,manifest(),'pin')
        new=[dict(ticker='TEST',side='BUY',qty=2,status='partial',filled=1)]
        activity.finish(self.root,r,True,False,new);path.write_text(json.dumps(new))
        rows=activity.listing(self.root)['entries']
        self.assertEqual(len(rows),2)
        legacy=next(e for e in rows if e['kind']=='receipt')
        self.assertEqual(legacy['results'],old);self.assertIsNone(legacy['broker_account'])
        self.assertTrue(legacy['estimated_date'])

    def test_identical_paper_and_live_receipts_remain_separate(self):
        results=[dict(ticker='TEST',side='BUY',qty=2,status='filled',filled=2)]
        live=activity.begin(self.root,manifest('b'*32,'live'),'device')
        activity.finish(self.root,live,True,False,results)
        (self.root/'orders_result.paper.json').write_text(json.dumps(results))
        activity.begin(self.root,manifest(),'pin')
        (self.root/'orders_result.paper.json').write_text('[]')
        paper=activity.listing(self.root,'paper')['entries']
        self.assertEqual(len(paper),2)
        self.assertEqual(next(r for r in paper if r['kind']=='receipt')['results'],results)

    def test_filters_pagination_and_partial_corruption(self):
        activity.begin(self.root,manifest(),'pin')
        r=activity.begin(self.root,manifest('b'*32,'live'),'device')
        activity.finish(self.root,r,False,True,[])
        folder=self.root/'.workspace'
        (folder/'profile.json').write_text(json.dumps(dict(created_at='2026-09-01T10:00:00Z')))
        (folder/'activity'/('c'*32+'.json')).write_text('broken')
        out=activity.listing(self.root,limit=2)
        self.assertEqual(out['total'],3);self.assertEqual(out['next_offset'],2);self.assertTrue(out['warnings'])
        self.assertEqual(len(activity.listing(self.root,limit=2,offset=2)['entries']),1)
        self.assertEqual(activity.listing(self.root,'live')['entries'][0]['phase'],'not_submitted')
        self.assertEqual(len(activity.listing(self.root,'personal')['entries']),1)
        for mode,limit,offset in [('bad',10,0),('all',True,0),('all',10,-1)]:
            with self.assertRaises(ValueError):activity.listing(self.root,mode,limit,offset)

    def test_export_includes_records_but_excludes_unrelated_files(self):
        activity.begin(self.root,manifest(),'device')
        (self.root/'.workspace/activity/credentials.json').write_text('secret')
        archive,_=data_export.build_export(self.root)
        with archive,zipfile.ZipFile(archive) as z:
            names=z.namelist()
            self.assertIn('data/.workspace/activity/'+ 'a'*32+'.json',names)
            self.assertFalse(any('credentials' in n for n in names))

    def test_http_history_endpoint_is_read_only_and_rejects_foreign_origin(self):
        def request(origin):
            h=object.__new__(webdash.Handler);h.path='/api/activity'
            h.headers={'Host':'localhost:8642','Content-Type':'application/json','Content-Length':'2','Origin':origin}
            h.rfile=io.BytesIO(b'{}');h.wfile=io.BytesIO();codes=[]
            h.send_response=codes.append;h.send_header=lambda *a:None;h.end_headers=lambda:None
            h.do_POST();return codes[-1],json.loads(h.wfile.getvalue())
        with patch.object(webdash,'HERE',self.root),patch.object(webdash,'run_step') as run:
            self.assertEqual(request('https://example.com')[0],403)
            self.assertEqual(request('http://localhost:8642')[1]['entries'],[])
            run.assert_not_called()
        self.assertFalse(list(self.root.iterdir()))


class ActivityExecutionTests(unittest.TestCase):
    setUp=test_investing.InvestingTests.setUp
    tearDown=test_investing.InvestingTests.tearDown
    approve=test_investing.InvestingTests.approve

    def test_failed_initial_record_prevents_execution(self):
        p=self.approve()
        with patch.object(activity,'begin',side_effect=OSError('full')),patch.object(webdash,'run_step') as run:
            out=webdash.api_execute(p)
            self.assertTrue(out['not_submitted']);run.assert_not_called()

    def test_failed_final_record_preserves_execution_response_and_does_not_retry(self):
        p=self.approve()
        with patch.object(activity,'finish',side_effect=OSError('full')),patch.object(webdash,'run_step',return_value=(True,'done')) as run:
            out=webdash.api_execute(p)
            self.assertTrue(out['ok']);self.assertIn('outcome could not be saved',out['log'])
            self.assertFalse(webdash.api_execute(p)['ok']);self.assertEqual(run.call_count,1)
        self.assertEqual(activity.listing(self.root)['entries'][0]['phase'],'requested')

    def test_uncertain_attempt_is_not_a_success(self):
        p=self.approve()
        with patch.object(webdash,'run_step',return_value=(False,'connection lost during submission')):
            out=webdash.api_execute(p)
        self.assertFalse(out['ok']);self.assertFalse(out['not_submitted'])
        self.assertEqual(activity.listing(self.root)['entries'][0]['phase'],'uncertain')
        self.assertEqual(self.paths['pending'].read_text(),'2')
