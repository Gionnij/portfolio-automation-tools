"""Read-only funding context for monthly investing; never prepares or submits orders.

CashBalance is the EUR currency ledger, not AvailableFunds or BuyingPower.
IBKR supports both CashBalance and $LEDGER-CashBalance (Gateway setting).
https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/per-currency-account-value-prefix
"""
import asyncio
import math
from datetime import datetime, timezone


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and abs(value) < 1e100 else None
    except (ValueError, TypeError):
        return None


def checked_account(accounts, mode):
    # The UI does not yet choose between multiple brokerage accounts.
    if len(accounts) != 1:
        raise ValueError('Connect exactly one IBKR account to read its balances.')
    acct = accounts[0]
    expected = ('DU', 'DF') if mode == 'paper' else ('U', 'F')
    if not acct.upper().startswith(expected):
        raise ValueError(f'The Gateway is not connected to the selected {mode} account.')
    return acct


def ledger_value(values, account, tag, currency='EUR'):
    # Never substitute the BASE aggregate for a currency's actual cash holding.
    # Duplicate model rows can be identical; conflicting values stay unknown.
    for key in ('$LEDGER-' + tag, tag):
        matches = [number(v.value) for v in values
                   if v.account == account and v.tag == key and v.currency == currency
                   and not getattr(v, 'modelCode', '')]
        if matches:
            return matches[0] if all(v == matches[0] for v in matches) else None
    return None


def summarize(cfg, values, account, positions, complete=True):
    """positions contains broker-verified ISIN, shares, and price in EUR.

    Target/floor use policy holdings only, matching the engine's NAV. Broker
    cash and unrelated investments do not inflate the XEON target.
    """
    cash = ledger_value(values, account, 'CashBalance')
    sleeves = cfg.get('sleeves', {})
    policy_isins = {s.get('isin') for s in sleeves.values() if s.get('isin')}
    xeon = sleeves.get('XEON', {})
    xeon_isin = xeon.get('isin')
    nav, xeon_value, xeon_shares = 0.0, 0.0, 0.0
    xeon_known = complete and bool(xeon_isin)
    nav_known = complete
    for pos in positions:
        isin = pos.get('isin')
        if not isin:
            nav_known = xeon_known = False
            continue
        if isin not in policy_isins:
            continue
        qty, px = number(pos.get('shares')), number(pos.get('price_eur'))
        valid = qty is not None and px is not None and px > 0
        if not valid:
            nav_known = False
        if isin == xeon_isin:
            if not valid:
                xeon_known = False
            else:
                xeon_value += qty * px
                xeon_shares += qty
        if valid:
            nav += qty * px
    return {
        'currency': 'EUR', 'cash': cash,
        'nav': round(nav, 2) if nav_known and nav >= 0 else None,
        'xeon': {'value': round(xeon_value, 2) if xeon_known else None,
                 'shares': xeon_shares if xeon_known else None,
                 'target_pct': number(xeon.get('target')),
                 'floor_pct': number(cfg.get('rules', {}).get('xeon_floor_pct'))},
    }


def read_broker(ib, cfg, mode):
    from ib_async import Contract
    account = checked_account(ib.managedAccounts(), mode)
    values = ib.accountValues(account)
    items = [p for p in ib.portfolio(account) if p.position]
    held = {p.contract.conId: p.position for p in ib.positions(account) if p.position}
    complete = held == {p.contract.conId: p.position for p in items}
    warnings, positions = [], []
    base = next((v.value for v in values if v.account == account
                 and v.tag in ('RealCurrency', '$LEDGER-RealCurrency')
                 and v.currency == 'BASE'), None)
    for item in items:
        isin = None
        try:
            details = ib.reqContractDetails(Contract(conId=item.contract.conId))
            ids = {s.value for d in details if d.contract.conId == item.contract.conId
                   for s in d.secIdList if s.tag == 'ISIN'}
            if len(ids) == 1:
                isin = ids.pop()
        except (TimeoutError, ConnectionError):
            pass
        ccy = item.contract.currency
        rate = 1 if ccy == 'EUR' else ledger_value(values, account, 'ExchangeRate', ccy) if base == 'EUR' else None
        px = number(item.marketPrice)
        positions.append({'isin': isin, 'shares': item.position,
                          'price_eur': px * rate if px is not None and rate is not None and rate > 0 else None})
    result = summarize(cfg, values, account, positions, complete)
    if result['nav'] is None:
        warnings.append('Some holdings could not be valued or identified. XEON target amounts are unavailable until all policy holdings can be checked.')
    if result['cash'] is None:
        warnings.append('IBKR did not provide a usable EUR cash balance. Other currencies and buying power are not substituted.')
    try:
        trades = ib.reqAllOpenOrders()  # read-only; never binds, cancels or places orders
        open_orders = sum(1 for t in trades if not t.order.account or t.order.account == account)
    except (TimeoutError, ConnectionError):
        open_orders = None
        warnings.append('Pending orders could not be checked. They may affect spendable cash.')
    return dict(result, ok=True, account=mode, read_at=datetime.now(timezone.utc).isoformat(),
                open_orders=open_orders, warnings=warnings)


def fetch(mode, cfg):
    if mode not in ('paper', 'live'):
        raise ValueError('Choose paper or live for the balance lookup.')
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from ib_async import IB, StartupFetch
    ib = IB()
    try:
        ib.RequestTimeout = 6
        ib.connect('127.0.0.1', 4002 if mode == 'paper' else 4001,
                   clientId=83, readonly=True, timeout=6, raiseSyncErrors=True,
                   fetchFields=StartupFetch.ACCOUNT_UPDATES)
        return read_broker(ib, cfg, mode)
    except (TimeoutError, ConnectionError, OSError) as exc:
        raise ValueError(f'Open IB Gateway connected to your {mode} account, then refresh balances.') from exc
    finally:
        ib.disconnect()
        loop.close()
        asyncio.set_event_loop(None)
