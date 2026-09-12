"""Exact account/price and genuine signed device assertions, all brokers mocked."""
import contextlib
import io
import json
from types import SimpleNamespace as Row
import unittest
from unittest.mock import Mock, patch
import test_investing
from test_device_auth import Authenticator
import approval
import device_auth as auth
import rebalance
import webdash as app


class OrderApprovalTests(unittest.TestCase):
    setUp=test_investing.InvestingTests.setUp
    tearDown=test_investing.InvestingTests.tearDown
    approve=test_investing.InvestingTests.approve

    def device_review(self):
        auth.SESSIONS.clear();auth.CHALLENGES.clear()
        session=auth.session()['session'];device=Authenticator()
        def call(action,p=None):return auth.api(self.root,action,p or {},session,app.pin_check)
        opts=call('register-options',{'pin':'1234'});call('register-verify',device.respond(opts,True))
        opts=call('test-options');call('test-verify',device.respond(opts))
        opts=call('enable-paper-options',{'pin':'1234'});call('enable-paper-verify',device.respond(opts))
        p=self.approve();p['_session']=session
        r=app.api_review(p)
        opts=auth.options(self.root,session,'orders:'+approval.get(r['review_id'],session)['digest'])
        return dict(account='paper',review_id=r['review_id'],_session=session,**device.respond(opts))

    def test_review_displays_exact_account_and_limits_and_executor_receives_same_manifest(self):
        review=app.api_review(self.approve())
        self.assertEqual(review['manifest']['broker_account'],'DU123')
        self.assertEqual(review['manifest']['orders'][0]['limit_price'],'130')
        with patch.object(app,'run_step',return_value=(True,'done')) as run:
            out=app.api_execute({'account':'paper','review_id':review['review_id'],'confirm':'1234'})
        self.assertTrue(out['ok'])
        saved=json.loads(self.paths['approved'].read_text())
        self.assertEqual(saved,review['manifest'])
        args=run.call_args.args[0]
        self.assertEqual(args[args.index('--expect-account-id')+1],'DU123')
        self.assertEqual(args[args.index('--approval-digest')+1],approval.digest(saved))

    def test_different_account_of_same_mode_cannot_receive_orders(self):
        p=self.approve();app.api_balances.return_value['broker_account']='DU999'
        with patch.object(app,'run_step') as run:
            out=app.api_execute(p)
            self.assertFalse(out['ok']);self.assertIn('account changed',out['log']);run.assert_not_called()
        app.api_balances.return_value['broker_account']='DU123'
        self.assertFalse(app.api_execute(p)['ok'])

    def test_real_device_signature_authorizes_only_one_execution(self):
        p=self.device_review()
        with patch.object(app,'run_step',return_value=(True,'done')) as run:
            self.assertTrue(app.api_execute(p)['ok'])
            self.assertFalse(app.api_execute(p)['ok'])
            self.assertEqual(run.call_count,1)

    def test_device_enabled_mode_has_no_pin_bypass(self):
        p=self.device_review();p.pop('credential');p['confirm']='1234'
        with patch.object(app,'run_step') as run:
            self.assertFalse(app.api_execute(p)['ok']);run.assert_not_called()

    def test_signature_for_one_review_cannot_authorize_another(self):
        p=self.device_review()
        old=p['review_id']
        review=app.api_review(dict(self.approve(),_session=p['_session']))
        self.assertNotEqual(old,review['review_id']);p['review_id']=review['review_id']
        with patch.object(app,'run_step') as run:
            self.assertFalse(app.api_execute(p)['ok']);run.assert_not_called()

    def test_changed_account_after_device_prompt_is_refused(self):
        p=self.device_review();app.api_balances.return_value['broker_account']='DU999'
        with patch.object(app,'run_step') as run:
            self.assertFalse(app.api_execute(p)['ok']);run.assert_not_called()

    def test_expired_review_and_durable_write_failure_never_start_executor(self):
        p=self.approve();approval.REVIEWS[p['review_id']]['expires_at']=0
        with patch.object(app,'run_step') as run:
            self.assertFalse(app.api_execute(p)['ok']);run.assert_not_called()
        p=self.approve()
        with patch.object(auth,'atomic_json',side_effect=OSError('disk full')),patch.object(app,'run_step') as run:
            self.assertTrue(app.api_execute(p)['not_submitted'])
            run.assert_not_called()
        self.assertFalse(app.api_execute(p)['ok'])

    def test_current_broker_and_policy_rechecked_during_review(self):
        p=self.approve()
        first=dict(app.api_balances.return_value)
        for updated in [dict(first,broker_account='DU999'),dict(first,open_orders=None)]:
            with patch.object(app,'api_balances',side_effect=[first,updated]):
                if updated['broker_account']=='DU999':
                    with self.assertRaises(ValueError):app.api_review(p)
                else:self.assertFalse(app.api_review(p)['funding']['allowed'])


class ExecutorApprovalTests(unittest.TestCase):
    def fixture(self):
        cfg={'sleeves':{'AAA':{}}}
        orders=test_investing.frozen([test_investing.ORDERS[1]])
        orders[0].update(limit_price='130.05',order_ref='lens-test-0',con_id=987)
        m=dict(version=1,account='paper',broker_account='DU123',policy_hash=approval.digest(cfg),orders=orders)
        ib=Mock();ib.managedAccounts.return_value=['DU123'];ib.reqAllOpenOrders.return_value=[]
        ib.accountValues.return_value=[Row(account='DU123',tag='CashBalance',currency='EUR',value='10000',modelCode='')]
        ib.placeOrder.return_value=Row(orderStatus=Row(status='Filled',filled=3,avgFillPrice=130.01),log=[])
        return cfg,m,ib

    def execute(self,cfg,m,ib,digest=None):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            orders=Path(tmp)/'orders.json';orders.write_text(json.dumps(m))
            with patch('ib_async.IB',return_value=ib),patch.object(rebalance,'_connect'),\
                 patch.object(rebalance,'_resolve',side_effect=AssertionError('Must not resolve after approval')),\
                 patch.object(rebalance,'_tick_at',side_effect=AssertionError('Must not reprice after approval')),\
                 contextlib.redirect_stdout(io.StringIO()):
                rebalance.execute(orders,cfg,'127.0.0.1',4002,7,auto_yes=True,expect_account='paper',
                    expected_account_id='DU123',approval_digest=digest or approval.digest(m),result_path=Path(tmp)/'result.json')

    def test_frozen_order_is_sent_without_resolving_or_repricing(self):
        cfg,m,ib=self.fixture();self.execute(cfg,m,ib)
        con,order=ib.placeOrder.call_args.args
        self.assertEqual((con.conId,con.exchange,order.account,order.lmtPrice),(987,'SMART','DU123',130.05))
        self.assertEqual((order.totalQuantity,order.tif,order.outsideRth,order.orderRef),(3,'DAY',False,'lens-test-0'))

    def test_changed_empty_multiple_or_unknown_accounts_fail_closed(self):
        for accounts in [[],['DU999'],['DU123','DU456'],['unknown'],['U123']]:
            cfg,m,ib=self.fixture();ib.managedAccounts.return_value=accounts
            with self.subTest(accounts=accounts),self.assertRaises(SystemExit):self.execute(cfg,m,ib)
            ib.placeOrder.assert_not_called()

    def test_account_change_during_batch_is_uncertain_not_preflight_refusal(self):
        cfg,m,ib=self.fixture()
        m['orders'].append(dict(m['orders'][0],order_ref='lens-test-1'))
        ib.managedAccounts.side_effect=lambda: ['DU999'] if ib.placeOrder.call_count else ['DU123']
        ib.accountValues.side_effect=lambda account: [Row(account=account,tag='CashBalance',currency='EUR',value='10000',modelCode='')]
        with self.assertRaisesRegex(SystemExit,'ACCOUNT CHANGED DURING SUBMISSION'):
            self.execute(cfg,m,ib)
        self.assertEqual(ib.placeOrder.call_count,1)

    def test_open_order_lookup_failure_does_not_mean_zero(self):
        for result in [None, RuntimeError('unavailable')]:
            cfg,m,ib=self.fixture()
            if isinstance(result,Exception):ib.reqAllOpenOrders.side_effect=result
            else:ib.reqAllOpenOrders.return_value=result
            with self.assertRaises(SystemExit):self.execute(cfg,m,ib)
            ib.placeOrder.assert_not_called()

    def test_modified_price_contract_or_policy_never_reaches_broker(self):
        for key,value in [('limit_price','130.06'),('con_id',1234),('qty','4')]:
            cfg,m,ib=self.fixture();d=approval.digest(m);m['orders'][0][key]=value
            with self.assertRaises(ValueError):self.execute(cfg,m,ib,d)
            ib.placeOrder.assert_not_called()
        cfg,m,ib=self.fixture();cfg['changed']=True
        with self.assertRaises(ValueError):self.execute(cfg,m,ib)
        ib.placeOrder.assert_not_called()


class ResolveBeforeReviewTests(unittest.TestCase):
    def test_isin_contract_and_tick_limit_are_fixed_before_review(self):
        ib=Mock();ib.managedAccounts.return_value=['DU123'];ib.reqAllOpenOrders.return_value=[]
        ib.reqContractDetails.return_value=[Row(contract=Row(conId=987,currency='EUR'),marketRuleIds='1')]
        ib.reqMarketRule.return_value=[Row(lowEdge=0,increment=.05)]
        cfg={'sleeves':{'AAA':{'isin':'IE00B4K48X80','currency':'EUR','exchange':'IBIS2'}}}
        with patch.object(approval.gateway,'with_connection',side_effect=lambda fn,mode:fn(ib,{})):
            rows=approval.freeze_orders(cfg,'paper',[dict(ticker='AAA',side='BUY',qty=3,est_price=130)],'DU123')
        self.assertEqual(rows[0]['limit_price'],'130.3')
        self.assertEqual(rows[0]['con_id'],987)
        self.assertEqual(ib.reqContractDetails.call_args.args[0].secId,'IE00B4K48X80')
        ib.placeOrder.assert_not_called()
        ib.reqMarketRule.return_value=[]
        with patch.object(approval.gateway,'with_connection',side_effect=lambda fn,mode:fn(ib,{})):
            with self.assertRaises(ValueError):approval.freeze_orders(cfg,'paper',[dict(ticker='AAA',side='BUY',qty=3,est_price=130)],'DU123')


if __name__=='__main__':unittest.main()
