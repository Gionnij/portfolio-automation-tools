"""Discover local IB Gateway sessions without placing or changing orders.

Ports are discovery endpoints, never evidence of paper/live account identity.
Login and the Read-Only API setting remain in IBKR's own application.
"""
import asyncio
import hashlib
import re
import threading

LOCK = threading.Lock()
PORTS = (4002, 4001)
READ_ONLY_HELP = ('IBKR has Read-Only API enabled. You can view holdings, but cannot '
                  'send investments. In IB Gateway, open Configure → Settings → '
                  'API → Settings, untick Read-Only API, apply, then refresh in Lens.')


def is_read_only(message):
    return bool(re.search(r'read[\s-]*only', str(message), re.I))


def account_mode(accounts):
    if len(accounts) != 1:
        raise ValueError('Connect exactly one IBKR account per Gateway session.')
    account = accounts[0].upper()
    # IBKR also issues alphanumeric account IDs (including paper DU IDs).
    # Validate the family and structure without assuming a numeric suffix.
    if re.fullmatch(r'D[UF][A-Z0-9]+', account) and any(c.isdigit() for c in account):
        return 'paper'
    if re.fullmatch(r'[UF][A-Z0-9]+', account) and any(c.isdigit() for c in account):
        return 'live'
    raise ValueError('Lens could not identify this IBKR account as paper or live.')


class Unavailable(ValueError):
    def __init__(self, connection):
        super().__init__(connection['message'])
        self.connection = connection


def disconnected(message=None, state='disconnected', sessions=None):
    return dict(state=state, sessions=sessions or [], mode=None, read_only=None,
                message=message or 'IB Gateway is not connected. Open it and log in to your paper or live account. Lens will detect it automatically.')


def with_connection(fn, mode='auto', *, status_only=False):
    if mode not in ('auto', 'paper', 'live'):
        raise ValueError('Choose automatic, paper or live holdings.')
    with LOCK:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        connections, sessions, failures = [], [], []
        try:
            from ib_async import IB, StartupFetch
            for port in PORTS:
                ib = IB()
                connections.append(ib)
                try:
                    ib.RequestTimeout = 10
                    if status_only:
                        # The API handshake provides managed accounts. Status
                        # must not depend on positions/prices synchronizing.
                        ib.client.connect('127.0.0.1', port, clientId=79, timeout=20)
                    else:
                        ib.connect('127.0.0.1', port, clientId=79, timeout=20,
                                   readonly=True, raiseSyncErrors=True,
                                   fetchFields=StartupFetch.ACCOUNT_UPDATES)
                    accounts = ib.managedAccounts()
                    actual = account_mode(accounts)
                    expected = 'live' if port == 4001 else 'paper'
                    if actual != expected:
                        raise ValueError(f'Gateway port {port} is configured for {actual}. Use port 4001 for live and 4002 for paper in IB Gateway, then reconnect.')
                    key = hashlib.sha256(accounts[0].encode()).hexdigest()[:16]
                    sessions.append((ib, dict(mode=expected, port=port, session_key=f'{port}:{key}')))
                except Exception as exc:
                    if isinstance(exc, ValueError):
                        failures.append(str(exc))
                    ib.disconnect()
            public = [s for _, s in sessions]
            # One Gateway determines the whole interface. A stale caller cannot
            # select a second session or silently route to a different mode.
            if len(sessions) > 1:
                raise Unavailable(disconnected('Both Gateway ports are connected. Keep only the account you want to use connected in IB Gateway. Lens will follow it automatically.', 'multiple_connections', public))
            matches = [(ib, s) for ib, s in sessions if mode == 'auto' or s['mode'] == mode]
            if len(matches) != 1:
                if sessions:
                    message = f'Your {mode} Gateway is not connected. The {sessions[0][1]["mode"]} account is available. Switch accounts in IB Gateway, then refresh Lens.'
                    state = 'different_account'
                else:
                    message = failures[0] if failures else None
                    state = 'unavailable' if failures else 'disconnected'
                raise Unavailable(disconnected(message, state, public))
            ib, selected = matches[0]
            connection = dict(selected, state='connected', sessions=public, read_only=None,
                              message=f'Connected to your {selected["mode"]} account on port {selected["port"]}. To switch accounts, log out and switch in IB Gateway. Lens follows automatically.')
            if status_only:
                return fn(ib, connection)

            # Request existing orders only, with a nonzero client ID: never bind,
            # modify, cancel or submit an order to test permissions. Absence of a
            # read-only rejection does NOT prove that order submission is enabled.
            def on_error(req_id, code, message, *args):
                if is_read_only(message):
                    connection.update(read_only=True, message=READ_ONLY_HELP)
            ib.errorEvent += on_error
            try:
                try:
                    ib.reqAllOpenOrders()
                except Exception as exc:
                    on_error(None, None, str(exc))
                return fn(ib, connection)
            finally:
                ib.errorEvent -= on_error
        except ImportError as exc:
            raise Unavailable(disconnected('The IBKR connection component is unavailable. Install the app requirements, then restart Lens.', 'unavailable')) from exc
        finally:
            for ib in connections:
                ib.disconnect()
            loop.close()
            asyncio.set_event_loop(None)


def status(mode='auto'):
    try:
        return with_connection(lambda ib, connection: connection, mode, status_only=True)
    except Unavailable as exc:
        return exc.connection
