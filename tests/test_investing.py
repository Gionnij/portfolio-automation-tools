"""Investing presentation and approval regressions. All broker calls are mocked."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import webdash as app

REPORT = '''# Portfolio prep report - 2026-09-07
Manual test | NAV EUR 10,000 | contribution EUR 600

## Regime
Equity drawdown **D = 12.5%** -> **Correction**
- A routing explanation.

## Current vs target
| Sleeve | Current % | Target % | Gap (EUR) | Contribution routed |
|---|---|---|---|---|
| AAA | 30.00 | 50.0 | 300 | 390 |
| XEON | 70.00 | 50.0 | -300 | -140 |

## Staged orders
Held back this run: AAA EUR 25
Reason: whole shares and minimum purchase size.

## Manual compliance checklist
| § | Criterion | Status | Detail |
|---|---|---|---|
| 3 | Band drift > 25% | CHECK | Review this allocation |
'''
ORDERS = [dict(ticker='XEON',side='SELL',qty=1,est_price=140),
          dict(ticker='AAA',side='BUY',qty=3,est_price=130)]

class InvestingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.patch=patch.object(app,'HERE',self.root);self.patch.start()
        (self.root/'manual.json').write_text(json.dumps({'sleeves':{'AAA':{'name':'Example fund'}},'rules':{'min_order_eur':75}}))
        self.paths=app.P('paper')
        self.paths['report'].write_text(REPORT)
        self.paths['orders'].write_text(json.dumps(ORDERS))
        self.paths['state'].write_text(json.dumps({'history':[{'date':'2026-09-07','nav':10000,'unit':90,'contribution':600}]}))
        self.paths['pending'].write_text('1')

    def tearDown(self):
        self.patch.stop();self.temp.cleanup()

    def approve(self, **extra):
        return dict(account='paper',confirm='EXECUTE',plan_id=app.plan_id('paper'),selected=[1],**extra)

    def test_cash_flow_counts_sales_and_purchases_without_claiming_account_cash(self):
        p=app.report_payload('paper',[])
        self.assertEqual(p['estimates'],dict(buys=390,sells=140,cash_left=350))
        self.assertEqual(p['nav'],10000)
        self.assertEqual(p['contribution'],600)
        self.assertEqual(p['d'],12.5)
        self.assertEqual(p['snapshot_date'],'2026-09-07')
        self.assertEqual(p['funds']['AAA']['name'],'Example fund')
        self.assertEqual(p['min_order'],75)
        self.assertEqual(p['notes'],['A routing explanation.'])
        self.assertTrue(p['held_back'])
        self.assertNotIn('available_cash',p)

    def test_missing_metadata_stays_unknown(self):
        self.paths['report'].write_text(REPORT.replace('NAV EUR 10,000 | contribution EUR 600','No valuation available'))
        p=app.report_payload('paper',[])
        self.assertIsNone(p['nav']);self.assertIsNone(p['estimates']['cash_left'])

    def test_first_visit_without_report_still_returns_fund_names_and_settings(self):
        self.paths['report'].unlink()
        p=app.report_payload('paper',[])
        self.assertTrue(p['ok']);self.assertFalse(p['has_report'])
        self.assertEqual(p['min_order'],75)

    def test_changed_orders_or_policy_invalidate_approval(self):
        for filename in ['orders','policy']:
            with self.subTest(filename=filename):
                payload=self.approve()
                path=self.paths['orders'] if filename=='orders' else self.root/'manual.json'
                path.write_text(path.read_text()+' ')
                with patch.object(app,'run_step') as run:
                    self.assertFalse(app.api_execute(payload)['ok']);run.assert_not_called()

    def test_new_preview_with_identical_values_invalidates_old_approval(self):
        payload=self.approve()
        import os
        path=self.paths['report'];stamp=path.stat().st_mtime_ns
        os.utime(path,ns=(stamp+1000000,stamp+1000000))
        with patch.object(app,'run_step') as run:
            self.assertFalse(app.api_execute(payload)['ok']);run.assert_not_called()

    def test_exact_selection_and_account_gate_remain_in_subprocess(self):
        with patch.object(app,'run_step',return_value=(True,'done')) as run:
            self.assertTrue(app.api_execute(self.approve())['ok'])
            self.assertEqual(json.loads(self.paths['approved'].read_text()),[ORDERS[1]])
            args=run.call_args.args[0]
            self.assertIn('--expect-account',args)
            self.assertEqual(args[args.index('--expect-account')+1],'paper')
            self.assertIn('127.0.0.1:4002',args)

    def test_replay_and_undo_after_submission_are_blocked_even_on_failure(self):
        payload=self.approve()
        with patch.object(app,'run_step',return_value=(False,'interrupted')) as run:
            self.assertFalse(app.api_execute(payload)['ok'])
            self.assertFalse(app.api_execute(payload)['ok'])
            self.assertFalse(app.api_undo({'account':'paper'})['ok'])
            self.assertEqual(run.call_count,1)

    def test_known_preflight_refusal_preserves_baseline_without_uncertain_marker(self):
        original='{"units":100,"ath_unit":150}'
        self.paths['undo'].write_text(original)
        with patch.object(app,'run_step',return_value=(False,'!! REFUSING to execute - orders are still open at the broker:')):
            result=app.api_execute(self.approve())
        self.assertFalse(result['ok']);self.assertTrue(result['not_submitted'])
        self.assertFalse(app._uncertain('paper'));self.assertFalse(app._pending('paper'))
        self.assertEqual(self.paths['state'].read_text(),original)

    def test_interrupted_submission_pauses_planning_without_resetting_tracking(self):
        with patch.object(app,'run_step',side_effect=RuntimeError('lost process')):
            with self.assertRaises(RuntimeError):app.api_execute(self.approve())
        before=self.paths['state'].read_bytes()
        self.assertTrue(app.report_payload('paper',[])['submission_uncertain'])
        with patch.object(app,'run_step') as run:
            with self.assertRaisesRegex(ValueError,'previous submission was interrupted'):
                app.api_prepare({'account':'paper','fetch':False,'contribute':600})
            run.assert_not_called()
        self.assertEqual(self.paths['state'].read_bytes(),before)

    def test_discard_first_ever_preview_restores_absence_of_state(self):
        self.paths['undo'].write_bytes(b'')
        self.assertTrue(app.api_undo({'account':'paper'})['ok'])
        self.assertFalse(self.paths['state'].exists())

    def test_invalid_selection_never_submits(self):
        for sel in [[],[True],[-1],[500],['1'],'1',None]:
            with self.subTest(sel=sel),patch.object(app,'run_step') as run:
                payload=self.approve();payload['selected']=sel
                self.assertFalse(app.api_execute(payload)['ok']);run.assert_not_called()

    def test_invalid_amount_never_changes_state_or_contacts_broker(self):
        state=self.paths['state'].read_bytes()
        for val in [-1,float('nan'),float('inf'),'600',True]:
            with self.subTest(val=val),patch.object(app,'run_step') as run:
                with self.assertRaises(ValueError):app.api_prepare({'contribute':val})
                run.assert_not_called();self.assertEqual(self.paths['state'].read_bytes(),state)

    def test_failed_preview_cannot_leave_previous_orders_approvable(self):
        payload=self.approve()
        with patch.object(app,'run_step',return_value=(False,'cannot connect')):
            self.assertFalse(app.api_prepare({'fetch':False,'contribute':600})['ok'])
        with patch.object(app,'run_step') as run:
            self.assertFalse(app.api_execute(payload)['ok']);run.assert_not_called()

    def test_discard_restores_only_unsubmitted_preview(self):
        self.paths['undo'].write_text('{"before":true}')
        self.assertTrue(app.api_undo({'account':'paper'})['ok'])
        self.assertEqual(json.loads(self.paths['state'].read_text()),{'before':True})
        self.assertFalse(app._pending('paper'))

if __name__=='__main__':unittest.main()
