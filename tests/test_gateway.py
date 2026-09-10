"""Account discovery and failure paths. All broker calls are simulated."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as Row
from unittest.mock import MagicMock, patch
import gateway
import workspace
import balances
import webdash


class Event:
    def __init__(self): self.handlers = []
    def __iadd__(self, handler): self.handlers.append(handler); return self
    def __isub__(self, handler): self.handlers.remove(handler); return self
    def emit(self, message):
        for handler in self.handlers: handler(-1, 321, message, None)


def broker(account=None, read_only=False):
    ib = MagicMock()
    ib.errorEvent = Event()
    if account is None:
        ib.connect.side_effect = ConnectionRefusedError('raw socket error 127.0.0.1')
        ib.client.connect.side_effect = ConnectionRefusedError('raw socket error 127.0.0.1')
    ib.managedAccounts.return_value = [account] if account else []
    if read_only:
        def reject():
            ib.errorEvent.emit('The API interface is currently in Read-Only mode.')
            raise TimeoutError()
        ib.reqAllOpenOrders.side_effect = reject
    return ib


class GatewayTests(unittest.TestCase):
    def test_port_and_account_must_agree(self):
        with patch('ib_async.IB', side_effect=[broker('U123'), broker()]):
            state = gateway.status()
        self.assertEqual(state['state'], 'unavailable')
        self.assertIsNone(state['mode'])
        self.assertIn('port 4002', state['message'])

    def test_live_status_uses_handshake_without_position_sync_or_orders(self):
        paper, live = broker(), broker('U123')
        with patch('ib_async.IB', side_effect=[paper, live]):
            state = gateway.status()
        self.assertEqual((state['mode'],state['port']), ('live',4001))
        self.assertIsNone(state['read_only'])
        live.client.connect.assert_called_once_with('127.0.0.1',4001,clientId=79,timeout=20)
        live.connect.assert_not_called()
        live.reqAllOpenOrders.assert_not_called()
        live.placeOrder.assert_not_called()
        live.disconnect.assert_called()

    def test_both_accounts_are_ambiguous_even_for_explicit_mode(self):
        for mode in ('auto','paper','live'):
            with patch('ib_async.IB', side_effect=[broker('DU123'), broker('U123')]):
                result = gateway.status(mode)
            self.assertEqual(result['state'], 'multiple_connections')
            self.assertIsNone(result['mode'])
            self.assertIn('IB Gateway', result['message'])

    def test_requested_account_never_silently_falls_back(self):
        with patch('ib_async.IB', side_effect=[broker(), broker('U123')]):
            state = gateway.status('paper')
        self.assertEqual(state['state'], 'different_account')
        self.assertIsNone(state['mode'])

    def test_no_gateway_is_a_friendly_state(self):
        with patch('ib_async.IB', side_effect=[broker(), broker()]):
            result = workspace.broker_holdings()
        self.assertTrue(result['ok'])
        self.assertIsNone(result['holdings'])
        self.assertEqual(result['connection']['state'], 'disconnected')
        self.assertNotIn('socket', str(result))
        self.assertNotIn('127.0.0.1', str(result))

    def test_unsupported_and_multiple_accounts_are_rejected(self):
        for accounts in ([], ['unknown'], ['DU123', 'DU456']):
            with self.subTest(accounts=accounts), self.assertRaises(ValueError):
                gateway.account_mode(accounts)
        self.assertEqual(gateway.account_mode(['DF123']), 'paper')
        self.assertEqual(gateway.account_mode(['F123']), 'live')

    def test_readonly_rejection_keeps_holdings_available(self):
        ib = broker('DU123', True)
        with patch('ib_async.IB', side_effect=[ib, broker()]):
            state = gateway.with_connection(lambda ib, connection: connection)
        self.assertTrue(state['read_only'])
        self.assertEqual(state['state'], 'connected')
        self.assertIn('untick Read-Only API', state['message'])
        ib.placeOrder.assert_not_called()

    def test_unknown_permissions_are_never_called_enabled(self):
        ib = broker('DU123')
        ib.reqAllOpenOrders.side_effect = TimeoutError()
        with patch('ib_async.IB', side_effect=[ib, broker()]):
            self.assertIsNone(gateway.status()['read_only'])

    def test_old_unscoped_cache_cannot_leak_into_disconnected_view(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(workspace, 'DATA', Path(folder)):
            (Path(folder)/'holdings.json').write_text('{"holdings":{"OLD":{"value_eur":123}}}')
            with patch('ib_async.IB', side_effect=[broker(), broker()]):
                self.assertIsNone(workspace.broker_holdings()['holdings'])

    def test_balance_observer_reports_readonly(self):
        ib = broker('DU123')
        def read(*args):
            ib.errorEvent.emit('API interface is in Read-Only mode')
            return {'ok': True, 'warnings': []}
        with patch('ib_async.IB', return_value=ib), patch.object(balances, 'read_broker', side_effect=read):
            result = balances.fetch('paper', {})
        self.assertTrue(result['read_only'])
        self.assertIn('untick', result['warnings'][0])

    def test_readonly_blocks_review_and_submission_funding(self):
        with tempfile.TemporaryDirectory() as folder:
            inputs = Path(folder)/'inputs.json'
            inputs.write_text('{"contribute":10}')
            with patch.object(webdash, 'P', return_value={'inputs': inputs}), patch.object(webdash, 'api_balances', return_value={'account':'paper', 'cash':100, 'read_only':True}):
                funding, _ = webdash.check_funding('paper', [])
        self.assertFalse(funding['allowed'])
        self.assertEqual(funding['reason'], 'read_only')
        self.assertIn('untick', funding['message'])

    def test_holdings_failure_does_not_mislabel_connected_gateway(self):
        ib=broker('U123')
        ib.portfolio.side_effect=RuntimeError('positions not ready')
        connection={'mode':'live','port':4001,'state':'connected'}
        with patch.object(gateway,'with_connection',side_effect=lambda fn, mode:fn(ib,connection)):
            result=workspace.broker_holdings()
        self.assertIsNone(result['holdings'])
        self.assertEqual(result['connection']['state'],'connected')
        self.assertIn('holdings could not be refreshed',result['holdings_message'])

    def test_alphanumeric_paper_id_is_detected_after_live_disconnect(self):
        with patch('ib_async.IB',side_effect=[broker(),broker('U123456')]):
            self.assertEqual(gateway.status()['mode'],'live')
        with patch('ib_async.IB',side_effect=[broker(),broker()]):
            self.assertEqual(gateway.status()['state'],'disconnected')
        with patch('ib_async.IB',side_effect=[broker('DUZ654321'),broker()]):
            status=gateway.status()
        self.assertEqual(status['mode'],'paper')
        self.assertEqual(status['port'],4002)
        self.assertEqual(balances.checked_account(['DUZ654321'],'paper'),'DUZ654321')

    def test_alphanumeric_id_never_bypasses_port_account_check(self):
        with patch('ib_async.IB',side_effect=[broker(),broker('DUZ654321')]):
            status=gateway.status()
        self.assertEqual(status['state'],'unavailable')
        self.assertIsNone(status['mode'])
