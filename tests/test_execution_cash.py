"""Execution cash gates with a mocked broker; no real orders or connections."""
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace as Row
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rebalance

class ExecutionCashTests(unittest.TestCase):
    def execute_fixture(self, orders, cash, sell_fails=False):
        ib = Mock()
        ib.managedAccounts.return_value = ['DU123']
        ib.reqAllOpenOrders.return_value = []
        values = [Row(account='DU123',tag='AvailableFunds',currency='EUR',value='10000',modelCode='')]
        if cash is not None:
            values.append(Row(account='DU123',tag='$LEDGER-CashBalance',currency='EUR',value=str(cash),modelCode=''))
        ib.accountValues.return_value = values
        def place(contract, order):
            failed = sell_fails and order.action == 'SELL'
            return Row(orderStatus=Row(status='Cancelled' if failed else 'Filled',
                       filled=0 if failed else order.totalQuantity,avgFillPrice=10),log=[])
        ib.placeOrder.side_effect = place
        with tempfile.TemporaryDirectory() as folder:
            orders_file=Path(folder)/'orders.json';results_file=Path(folder)/'results.json'
            orders_file.write_text(json.dumps(orders))
            with patch('ib_async.IB',return_value=ib), patch.object(rebalance,'_connect'), \
                 patch.object(rebalance,'_resolve',return_value=(Row(conId=123),None)), \
                 patch.object(rebalance,'_tick_at',return_value=.01), contextlib.redirect_stdout(io.StringIO()):
                rebalance.execute(orders_file, {'sleeves':{o['ticker']:{} for o in orders}},
                    '127.0.0.1',4002,83,auto_yes=True,expect_account='paper',result_path=results_file)
            return ib,json.loads(results_file.read_text())

    def test_margin_allowance_and_missing_cash_cannot_fund_a_buy(self):
        for cash in (None,50,-10):
            with self.subTest(cash=cash):
                ib,results=self.execute_fixture([dict(ticker='AAA',side='BUY',qty=10,est_price=10)],cash)
                ib.placeOrder.assert_not_called()
                self.assertEqual(results[0]['status'],'skipped')

    def test_orders_reserve_cash_before_broker_values_catch_up(self):
        ib,results=self.execute_fixture([dict(ticker=t,side='BUY',qty=10,est_price=10) for t in ('AAA','BBB')],150)
        self.assertEqual(ib.placeOrder.call_count,1)
        self.assertEqual({r['ticker']:r['status'] for r in results},{'AAA':'filled','BBB':'skipped'})

    def test_unfilled_xeon_sale_does_not_allow_buys_using_margin(self):
        ib,results=self.execute_fixture([dict(ticker='XEON',side='SELL',qty=1,est_price=550),
                                        dict(ticker='AAA',side='BUY',qty=10,est_price=10)],50,sell_fails=True)
        self.assertEqual(ib.placeOrder.call_count,1)
        self.assertEqual(ib.placeOrder.call_args.args[1].action,'SELL')
        self.assertEqual(results[-1]['status'],'skipped')

if __name__=='__main__':unittest.main()
