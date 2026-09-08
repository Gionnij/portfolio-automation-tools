"""Read-only funding context: account/currency identity and incomplete broker data."""
import json
from pathlib import Path
from types import SimpleNamespace as Row
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import balances
import webdash

CONFIG = {'sleeves': {'XEON': {'isin': 'LU-XEON', 'target': 6.5},
                       'FUND': {'isin': 'IE-FUND', 'target': 93.5}},
          'rules': {'xeon_floor_pct': 3.0}}


def value(tag, amount, currency='EUR', account='DU123', model=''):
    return Row(tag=tag, value=str(amount), currency=currency,
               account=account, modelCode=model)


def position(isin, shares, price):
    return dict(isin=isin, shares=shares, price_eur=price)


class BalanceTests(unittest.TestCase):
    def test_cash_is_eur_ledger_not_margin_base_foreign_currency_or_other_account(self):
        rows = [value('CashBalance', 625.37), value('AvailableFunds', 50000),
                value('BuyingPower', 100000), value('CashBalance', 1000, 'BASE'),
                value('CashBalance', 450, 'USD'), value('CashBalance', 42, account='U987'),
                value('CashBalance', 12, model='submodel')]
        self.assertEqual(balances.summarize(CONFIG, rows, 'DU123', [])['cash'], 625.37)

    def test_gateway_ledger_prefix_and_signed_or_zero_balances(self):
        for tag in ('CashBalance', '$LEDGER-CashBalance'):
            for cash in (0, -12.34, 456.78):
                with self.subTest(tag=tag, cash=cash):
                    self.assertEqual(balances.ledger_value([value(tag, cash)], 'DU123', 'CashBalance'), cash)

    def test_missing_invalid_or_conflicting_cash_is_unknown_not_zero(self):
        cases = [[], [value('CashBalance', 100, 'BASE')],
                 [value('CashBalance', 'nan')], [value('CashBalance', 'inf')],
                 [value('CashBalance', 1.7976931348623157e308)],
                 [value('CashBalance', 100), value('CashBalance', 200)]]
        for rows in cases:
            with self.subTest(rows=rows):
                self.assertIsNone(balances.ledger_value(rows, 'DU123', 'CashBalance'))

    def test_duplicate_identical_values_are_not_added_together(self):
        rows = [value('CashBalance', 100), value('CashBalance', 100), value('$LEDGER-CashBalance', 100)]
        self.assertEqual(balances.ledger_value(rows, 'DU123', 'CashBalance'), 100)

    def test_xeon_policy_nav_excludes_uninvested_cash_and_unrelated_holdings(self):
        positions = [position('LU-XEON', 10, 150), position('LU-XEON', 2, 150),
                     position('IE-FUND', 82, 100), position('UNRELATED', 10000, 200)]
        result = balances.summarize(CONFIG, [value('CashBalance', 1000000)], 'DU123', positions)
        self.assertEqual(result['nav'], 10000)
        self.assertEqual(result['xeon'], dict(value=1800, shares=12, target_pct=6.5, floor_pct=3))
        self.assertEqual(result['nav'] * result['xeon']['target_pct'] / 100, 650)
        self.assertEqual(result['nav'] * result['xeon']['floor_pct'] / 100, 300)
        self.assertEqual({h['ticker']: h['current_pct'] for h in result['holdings']}, {'XEON': 18, 'FUND': 82})

    def test_filled_new_position_appears_in_holdings_without_another_preview(self):
        cfg = {'sleeves': {'4COP': {'isin': 'IE-COPPER', 'target': 1.5, 'name': 'Copper fund'},
                            'FUND': {'isin': 'IE-FUND', 'target': 98.5}}}
        before = balances.summarize(cfg, [], 'DU123', [position('IE-FUND', 100, 100)])
        after = balances.summarize(cfg, [], 'DU123',
            [position('IE-FUND', 100, 100), position('IE-COPPER', 2, 62)])
        self.assertEqual(before['holdings'][0]['shares'], 0)
        copper = after['holdings'][0]
        self.assertEqual(copper['shares'], 2)
        self.assertEqual(copper['value'], 124)
        self.assertEqual(copper['name'], 'Copper fund')
        self.assertAlmostEqual(copper['current_pct'], 124 / 10124 * 100)
        self.assertEqual(copper['target_pct'], 1.5)

    def test_known_shares_without_prices_never_look_like_an_unheld_fund(self):
        result = balances.summarize(CONFIG, [], 'DU123', [position('IE-FUND', 2, None)])
        fund = next(h for h in result['holdings'] if h['ticker'] == 'FUND')
        self.assertEqual(fund['shares'], 2)
        self.assertIsNone(fund['value'])
        self.assertIsNone(fund['current_pct'])
        self.assertTrue(all(h['current_pct'] is None for h in result['holdings']))

    def test_unidentified_holdings_do_not_turn_other_sleeves_into_zero_positions(self):
        result = balances.summarize(CONFIG, [], 'DU123', [position(None, 2, 62)])
        self.assertTrue(all(h['shares'] is None and h['current_pct'] is None for h in result['holdings']))

    def test_empty_verified_portfolio_has_zero_shares_and_percentages(self):
        result = balances.summarize(CONFIG, [], 'DU123', [])
        self.assertEqual(result['nav'], 0)
        self.assertTrue(all(h['shares'] == 0 and h['current_pct'] == 0 for h in result['holdings']))

    def test_no_xeon_holding_is_zero_only_when_position_sync_is_complete(self):
        positions = [position('IE-FUND', 100, 100)]
        result = balances.summarize(CONFIG, [], 'DU123', positions)
        self.assertEqual(result['xeon']['value'], 0)
        result = balances.summarize(CONFIG, [], 'DU123', positions, complete=False)
        self.assertIsNone(result['xeon']['value'])
        self.assertIsNone(result['nav'])

    def test_unidentified_position_does_not_guess_xeon_or_target(self):
        result = balances.summarize(CONFIG, [], 'DU123', [position(None, 10, 150)])
        self.assertIsNone(result['xeon']['value'])
        self.assertIsNone(result['nav'])

    def test_missing_valuation_keeps_verified_xeon_but_hides_target(self):
        for price in (None, 0, -1, float('nan'), float('inf')):
            with self.subTest(price=price):
                result = balances.summarize(CONFIG, [], 'DU123',
                    [position('LU-XEON', 10, 150), position('IE-FUND', 100, price)])
                self.assertEqual(result['xeon']['value'], 1500)
                self.assertIsNone(result['nav'])

    def test_account_identity_refuses_mismatch_and_ambiguous_account_selection(self):
        for mode, accounts in [('paper', []), ('paper', ['U123']), ('live', ['DU123']),
                               ('live', ['DU123', 'U987']), ('paper', ['DU123', 'DU987'])]:
            with self.subTest(mode=mode, accounts=accounts), self.assertRaises(ValueError):
                balances.checked_account(accounts, mode)
        self.assertEqual(balances.checked_account(['DU123'], 'paper'), 'DU123')
        self.assertEqual(balances.checked_account(['U123'], 'live'), 'U123')

    def test_broker_uses_verified_contract_identity_and_eur_converted_prices(self):
        ib = Mock()
        ib.managedAccounts.return_value = ['DU123']
        ib.accountValues.return_value = [value('$LEDGER-CashBalance', 625),
            value('$LEDGER-RealCurrency', 'EUR', 'BASE'), value('$LEDGER-ExchangeRate', .9, 'USD')]
        contract = Row(conId=1234, currency='USD', symbol='AMBIGUOUS')
        ib.portfolio.return_value = [Row(contract=contract, position=10, marketPrice=200)]
        ib.positions.return_value = [Row(contract=contract, position=10)]
        ib.reqContractDetails.return_value = [Row(contract=contract, secIdList=[Row(tag='ISIN', value='LU-XEON')])]
        ib.reqAllOpenOrders.return_value = [Row(order=Row(account='DU123')), Row(order=Row(account='U987'))]
        result = balances.read_broker(ib, CONFIG, 'paper')
        self.assertEqual(result['xeon']['value'], 1800)
        self.assertEqual(result['nav'], 1800)
        self.assertEqual(result['cash'], 625)
        self.assertEqual(result['open_orders'], 1)
        self.assertEqual(ib.reqContractDetails.call_args.args[0].conId, 1234)
        ib.placeOrder.assert_not_called()
        ib.cancelOrder.assert_not_called()

        # A fill occurring between the position and valuation snapshots must
        # not turn an incomplete valuation into a precise target.
        ib.positions.return_value = [Row(contract=contract, position=11)]
        changed = balances.read_broker(ib, CONFIG, 'paper')
        self.assertIsNone(changed['nav'])
        self.assertIsNone(changed['xeon']['value'])
        self.assertEqual(changed['cash'], 625)

        # Foreign prices must not silently become euro prices if FX is missing.
        ib.positions.return_value = [Row(contract=contract, position=10)]
        ib.accountValues.return_value = [value('CashBalance', 625)]
        unknown_fx = balances.read_broker(ib, CONFIG, 'paper')
        self.assertIsNone(unknown_fx['nav'])
        self.assertIsNone(unknown_fx['xeon']['value'])

    def test_contract_or_order_timeout_preserves_cash_without_guessing_holdings(self):
        ib = Mock()
        ib.managedAccounts.return_value = ['DU123']
        ib.accountValues.return_value = [value('CashBalance', 625)]
        contract = Row(conId=1234, currency='EUR')
        ib.portfolio.return_value = [Row(contract=contract, position=10, marketPrice=150)]
        ib.positions.return_value = [Row(contract=contract, position=10)]
        ib.reqContractDetails.side_effect = TimeoutError
        ib.reqAllOpenOrders.side_effect = TimeoutError
        result = balances.read_broker(ib, CONFIG, 'paper')
        self.assertEqual(result['cash'], 625)
        self.assertIsNone(result['nav'])
        self.assertIsNone(result['xeon']['value'])
        self.assertIsNone(result['open_orders'])
        self.assertEqual(len(result['warnings']), 2)

    def test_disconnected_gateway_is_unavailable_and_cleans_up_connection(self):
        with patch('ib_async.IB') as IB:
            IB.return_value.connect.side_effect = ConnectionRefusedError
            with self.assertRaisesRegex(ValueError, 'Open IB Gateway connected to your live account'):
                balances.fetch('live', CONFIG)
            IB.return_value.disconnect.assert_called_once()

    def test_fetch_selects_account_port_and_readonly_connection(self):
        for mode, port in [('paper', 4002), ('live', 4001)]:
            with self.subTest(mode=mode), patch('ib_async.IB') as IB, patch.object(balances, 'read_broker', return_value={'ok': True}) as read:
                self.assertEqual(balances.fetch(mode, CONFIG), {'ok': True})
                args = IB.return_value.connect.call_args
                self.assertEqual(args.args, ('127.0.0.1', port))
                self.assertIs(args.kwargs['readonly'], True)
                read.assert_called_once_with(IB.return_value, CONFIG, mode)
                IB.return_value.disconnect.assert_called_once()

    def test_read_api_does_not_prepare_or_touch_saved_portfolio_state(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(webdash, 'HERE', Path(folder)):
            root = Path(folder)
            (root / 'manual.json').write_text(json.dumps(CONFIG))
            for filename in ('state.paper.json', 'orders.paper.json', 'state.live.json', 'pending.paper'):
                (root / filename).write_text('preserve exactly')
            before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
            with patch.object(balances, 'fetch', return_value={'ok': True}) as fetch, patch.object(webdash, 'run_step') as run:
                self.assertEqual(webdash.api_balances({'account': 'paper'}), {'ok': True})
                fetch.assert_called_once_with('paper', CONFIG)
                run.assert_not_called()
            self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()})


if __name__ == '__main__':
    unittest.main()
