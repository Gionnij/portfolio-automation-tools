"""Offline regressions: python -m unittest discover -s tests -v.

No network or broker account is needed. Fixtures use two overlapping funds
and known ISINs so effective exposure and unknown coverage can be hand-checked.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workspace as w
import xray
import webdash

A = 'IE00BD1F4L37'
B = 'IE00B4K48X80'
CSV_A = b'Name,ISIN,Weight (%),Country,Currency\nApple,US0378331005,60,US,USD\nMicrosoft,US5949181045,40,US,USD\n'
CSV_B = b'Name,ISIN,Weight (%),Country,Currency\nApple,US0378331005,20,US,USD\nShell,GB00BP6MXD84,80,GB,GBP\n'


def row(isin=A, weight=100, ticker='TEST'):
    return dict(isin=isin, weight=weight, ticker=ticker, name=ticker,
                currency='EUR', exchange='IBIS2', override='', source_url='', provider_page='')


def xml(isin=A):
    return f'''<?xml version="1.0"?>
<ss:Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
<ss:Worksheet ss:Name="Key Facts"><ss:Table><ss:Row><ss:Cell><ss:Data>ISIN</ss:Data></ss:Cell><ss:Cell><ss:Data>{isin}</ss:Data></ss:Cell></ss:Row></ss:Table></ss:Worksheet>
<ss:Worksheet ss:Name="Holdings"><ss:Table>
<ss:Row><ss:Cell><ss:Data>as of</ss:Data></ss:Cell><ss:Cell><ss:Data>04/Sept/2026</ss:Data></ss:Cell></ss:Row>
<ss:Row><ss:Cell><ss:Data>Name</ss:Data></ss:Cell><ss:Cell><ss:Data>Weight (%)</ss:Data></ss:Cell></ss:Row>
<ss:Row><ss:Cell><ss:Data>Apple</ss:Data></ss:Cell><ss:Cell><ss:Data>100</ss:Data></ss:Cell></ss:Row>
</ss:Table></ss:Worksheet></ss:Workbook>'''.encode()


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / '.workspace'
        self.cache.mkdir()
        (self.root/'holdings').mkdir()
        manual = {'sleeves':{'AAA':{'isin':A,'name':'Fund A','target':50,'currency':'EUR','exchange':'IBIS2'},
                             'BBB':{'isin':B,'name':'Fund B','target':50,'currency':'EUR','exchange':'IBIS2'}}}
        (self.root/'manual.json').write_text(json.dumps(manual))
        self.patches = [patch.object(w,'HERE',self.root),patch.object(w,'DATA',self.cache)]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in self.patches:p.stop()
        self.temp.cleanup()

    def put(self, isin, body):
        (self.cache/(isin+'.csv')).write_bytes(body)
        (self.cache/(isin+'.json')).write_text(json.dumps({'source_url':'https://www.ishares.com/test','as_of':'04/Sept/2026'}))

    def test_isin_checksum(self):
        self.assertTrue(w.valid_isin(A))
        self.assertFalse(w.valid_isin(A[:-1]+'8'))
        self.assertFalse(w.valid_isin('../../private'))

    def test_positive_finite_allocations_only(self):
        for value in [0,-1,101,float('inf'),float('nan')]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                w.validate_rows([row(weight=value)])

    def test_total_is_not_silently_normalized(self):
        with self.assertRaisesRegex(ValueError,'100%'):
            w.analyze_rows([row(weight=90)])

    def test_duplicate_isin_rejected_even_on_other_venue(self):
        with self.assertRaisesRegex(ValueError,'same ISIN'):
            w.validate_rows([row(weight=50),row(weight=50,ticker='OTHER')])

    def test_path_ticker_rejected(self):
        with self.assertRaises(ValueError):w.validate_rows([row(ticker='../state')])

    def test_manual_cannot_be_changed_by_draft(self):
        before=(self.root/'manual.json').read_bytes()
        w.api('save',{'rows':[row()]})
        self.assertEqual((self.root/'manual.json').read_bytes(),before)
        self.assertEqual(w.bootstrap()['origin'],'saved')
        self.assertEqual(w.bootstrap()['rows'][0]['isin'],A)

    def test_weighted_holdings_and_pairwise_overlap(self):
        self.put(A,CSV_A);self.put(B,CSV_B)
        r=w.analyze_rows([row(A,50,'AAA'),row(B,50,'BBB')])
        weights={h['isin']:h['weight'] for h in r['holdings']}
        self.assertAlmostEqual(weights['US0378331005'],40)
        self.assertAlmostEqual(weights['US5949181045'],20)
        self.assertAlmostEqual(weights['GB00BP6MXD84'],40)
        self.assertAlmostEqual(r['overlap'][0]['weight'],20)
        self.assertAlmostEqual(r['stats']['holdings_coverage'],100)
        self.assertAlmostEqual(sum(h['weight'] for h in r['exposures']['country']),100)

    def test_xray_survives_reopening_without_reanalysis(self):
        self.put(A,CSV_A);self.put(B,CSV_B)
        rows = w.catalog()
        report = w.api('analyze', {'rows':rows})
        self.assertTrue((self.cache/'xray.json').exists())
        with patch.object(w, 'analyze_rows', side_effect=AssertionError('Must restore, not rerun')):
            reopened = w.api('bootstrap', {})
        self.assertEqual(reopened['report'], report)
        self.assertFalse(reopened['report_stale'])
        self.assertEqual(reopened['origin'], 'manual')

    def test_saved_xray_preserves_unsaved_analysis_without_overwriting_draft(self):
        self.put(A,CSV_A);self.put(B,CSV_B)
        w.api('save', {'rows':w.catalog()})
        report = w.api('analyze', {'rows':[row()]})
        reopened = w.bootstrap()
        self.assertEqual(reopened['report'], report)
        self.assertTrue(reopened['report_stale'])
        self.assertEqual(len(reopened['rows']), 2)
        w.api('save', {'rows':[row()]})
        self.assertFalse(w.bootstrap()['report_stale'])

    def test_xray_detects_changed_source_bytes_metadata_enrichment_and_policy(self):
        self.put(A,CSV_A)
        w.api('save', {'rows':[row()]})
        for path, replacement in [
                (self.cache/(A+'.csv'), CSV_B),
                (self.cache/(A+'.json'), b'{"as_of":"2026-09-11"}'),
                (self.root/'holdings'/'enrich.csv', b'key,country\nApple,IE\n'),
                (self.root/'manual.json', (self.root/'manual.json').read_bytes()+b'\n')]:
            with self.subTest(path=path):
                report = w.api('analyze', {'rows':[row()]})
                original = path.read_bytes() if path.exists() else None
                path.write_bytes(replacement)
                reopened = w.bootstrap()
                self.assertEqual(reopened['report'], report)
                self.assertTrue(reopened['report_stale'])
                if original is None: path.unlink()
                else: path.write_bytes(original)
                self.assertFalse(w.bootstrap()['report_stale'])

    def test_failed_xray_keeps_previous_successful_report(self):
        self.put(A,CSV_A)
        report = w.api('analyze', {'rows':[row()]})
        with self.assertRaises(ValueError):
            w.api('analyze', {'rows':[row(weight=90)]})
        self.assertEqual(w.bootstrap()['report'], report)
        self.put(A,CSV_B)
        updated = w.api('analyze', {'rows':[row()]})
        self.assertNotEqual(updated['holdings'], report['holdings'])
        self.assertEqual(w.bootstrap()['report'], updated)

    def test_absent_or_unreadable_xray_does_not_break_bootstrap(self):
        self.assertIsNone(w.bootstrap()['report'])
        for value in ['{', 'null', '[]', '{"version":2}',
                      '{"version":1,"report":{"stats":{}}}']:
            (self.cache/'xray.json').write_text(value)
            self.assertIsNone(w.bootstrap()['report'])
            self.assertEqual(len(w.bootstrap()['rows']), 2)

    def test_same_symbol_different_fund_does_not_overwrite_contribution(self):
        self.put(A,CSV_A);self.put(B,CSV_B)
        r=w.analyze_rows([row(A,50,'SAME'),row(B,50,'SAME')])
        apple=next(h for h in r['holdings'] if h['isin']=='US0378331005')
        self.assertEqual(len(apple['etfs']),2)
        self.assertAlmostEqual(sum(apple['etfs'].values()),40)

    def test_missing_holdings_stay_in_denominator(self):
        self.put(A,CSV_A)
        r=w.analyze_rows([row(A,60,'AAA'),row(B,40,'BBB')])
        self.assertAlmostEqual(r['stats']['unknown'],40)
        self.assertAlmostEqual(r['stats']['holdings_coverage'],60)
        self.assertAlmostEqual(r['stats']['exposure_total'],100)

    def test_partial_file_remainder_is_unknown(self):
        self.put(A,b'Name,Weight (%)\nApple,60\n')
        r=w.analyze_rows([row()])
        self.assertAlmostEqual(r['stats']['unknown'],40)
        self.assertAlmostEqual(r['stats']['exposure_total'],100)

    def test_legacy_file_bound_by_isin_not_user_ticker(self):
        (self.root/'holdings'/'AAA.csv').write_bytes(CSV_A)
        self.assertEqual(w.source_meta(row(A,ticker='ALIAS'))['file'],'AAA.csv')
        self.assertEqual(w.source_meta(row('IE00BK5BQT80',ticker='AAA'))['status'],'missing')

    def test_provider_allowlist_blocks_localhost_and_spoofed_domains(self):
        for url in ['http://www.ishares.com/file','https://127.0.0.1/file',
                    'https://www.ishares.com.evil.test/file','file:///etc/passwd',
                    'https://www.ishares.com:8642/file','https://a@www.ishares.com/file']:
            with self.subTest(url=url),self.assertRaises(ValueError):w.allowed_url(url)
        self.assertEqual(w.allowed_url('https://www.ishares.com/file'),'https://www.ishares.com/file')

    def test_redirect_cannot_reach_private_service(self):
        with self.assertRaises(ValueError):
            w.ProviderRedirect().redirect_request(None,None,302,'',{},'https://127.0.0.1/')

    def test_xml_checks_fund_identity_not_constituents(self):
        body,asof=w.xml_holdings(xml(),A)
        self.assertIn(b'Apple,100',body)
        self.assertEqual(asof,'04/Sept/2026')
        with self.assertRaisesRegex(ValueError,'identity mismatch'):
            w.xml_holdings(xml(B),A)

    def test_failed_download_preserves_last_good_snapshot(self):
        self.put(A,CSV_A)
        r=row();r['source_url']='https://www.ishares.com/test.csv'
        for body in [b'<html>Access denied</html>',b'Name,Weight (%)\nApple,12\n',xml(B)]:
            with patch.object(w,'fetch',return_value=(body,r['source_url'])):
                with self.assertRaises(ValueError):w.download_one(r)
            self.assertEqual(w.snapshot_path(A).read_bytes(),CSV_A)

    def test_valid_provider_xml_is_canonicalized(self):
        r=row();r['source_url']='https://www.ishares.com/test'
        with patch.object(w,'fetch',return_value=(xml(),r['source_url'])):
            result=w.download_one(r)
        self.assertTrue(result['identity_verified'])
        self.assertEqual(result['holdings_count'],1)
        self.assertAlmostEqual(xray.read_holdings_file(w.snapshot_path(A)).weight.sum(),100)

    def test_bare_ticker_does_not_imply_us_country(self):
        self.assertEqual(xray.ticker_country('SAP'),'')
        self.assertEqual(xray.ticker_country('BHP AU'),'Australia')

    def test_globalx_current_csv_header_and_country_codes(self):
        p=self.root/'global.csv'
        p.write_text('AS_OF_DATE,NAME,NET_ASSETS,TICKER,ISIN,COUNTRY\n2026-09-04,Canadian Co,100,CC CN,CA4436281022,CA\n')
        frame=xray.read_holdings_file(p)
        self.assertEqual(frame.iloc[0]['country'],'Canada')
        self.assertAlmostEqual(frame.weight.sum(),100)

    def test_execution_phrase_and_per_order_selection_remain_required(self):
        with patch.object(webdash,'HERE',self.root), patch.object(webdash,'run_step') as runner:
            self.assertFalse(webdash.api_execute({'account':'paper','confirm':'wrong','selected':[0]})['ok'])
            (self.root/'orders.paper.json').write_text('[{"ticker":"AAA"}]')
            self.assertFalse(webdash.api_execute({'account':'paper','confirm':'EXECUTE','selected':[]})['ok'])
            self.assertFalse(webdash.api_execute({'account':'live','confirm':'EXECUTE','selected':[0]})['ok'])
            runner.assert_not_called()

    def test_signed_cash_is_preserved_but_short_equity_is_rejected(self):
        r=row();r['source_url']='https://globalxetfs.eu/test.csv'
        cash=b'Name,Weight (%)\nApple,100.1\nNORWEGIAN KRONE,-0.1\n'
        with patch.object(w,'fetch',return_value=(cash,r['source_url'])):
            result=w.download_one(r)
        self.assertAlmostEqual(result['coverage'],100)
        short=b'Name,Weight (%)\nApple,101\nMicrosoft,-1\n'
        with patch.object(w,'fetch',return_value=(short,r['source_url'])):
            with self.assertRaisesRegex(ValueError,'short exposure'):w.download_one(r)

    def test_globalx_date_comes_from_download_not_page_dates(self):
        r=row();r['source_url']='https://globalxetfs.eu/test.csv'
        body=b'AS_OF_DATE,NAME,NET_ASSETS,TICKER,ISIN,COUNTRY\n2026-09-04,Apple,100,AAPL,US0378331005,US\n'
        with patch.object(w,'fetch',return_value=(body,r['source_url'])):
            result=w.download_one(r)
        self.assertEqual(result['as_of'],'2026-09-04')

    def test_local_http_boundary_rejects_cross_origin_and_non_json(self):
        import http.client
        import threading
        server=webdash.ThreadingHTTPServer(('127.0.0.1',0),webdash.Handler)
        port=server.server_port
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with patch.object(webdash,'SERVER_PORT',port):
                for extra,expected in [({'Origin':'https://attacker.invalid','Content-Type':'application/json'},403),({'Content-Type':'text/plain'},415),({'Content-Type':'application/json'},200)]:
                    conn=http.client.HTTPConnection('127.0.0.1',port)
                    conn.request('POST','/api/workspace/bootstrap',body='{}',headers=extra)
                    response=conn.getresponse()
                    self.assertEqual(response.status,expected)
                    response.read();conn.close()
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
