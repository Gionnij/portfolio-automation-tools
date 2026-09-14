"""Frozen, expiring reviews. No authentication or order submission lives here."""
import copy
import hashlib
import json
import secrets
import time
from decimal import Decimal, InvalidOperation

import balances
import gateway
import rebalance

REVIEWS = {}
TTL = 120


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def decimal(value):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d <= 0:
            raise ValueError()
        return format(d, 'f')
    except (InvalidOperation, ValueError):
        raise ValueError('Order quantities and prices must be positive finite numbers.')


def freeze_orders(cfg, mode, chosen, expected_account):
    """Resolve by ISIN only and price before review, with read-only broker calls."""
    from ib_async import Contract

    def read(ib, connection):
        account = balances.checked_account(ib.managedAccounts(), mode)
        if account != expected_account:
            raise ValueError('The brokerage account changed. Review again.')
        open_orders = ib.reqAllOpenOrders()
        if not isinstance(open_orders, list):
            raise ValueError('Open orders could not be verified.')
        if open_orders:
            raise ValueError('There are open orders at IBKR. Check them before reviewing.')
        frozen = []
        for o in chosen:
            meta = cfg['sleeves'][o['ticker']]
            isin = meta.get('isin')
            if not isin or meta.get('currency', 'EUR') != 'EUR':
                raise ValueError('Exact approval currently requires an ISIN and an EUR trading listing.')
            details = ib.reqContractDetails(Contract(secType='STK', secIdType='ISIN', secId=isin,
                                            currency='EUR', exchange=meta.get('exchange', 'IBIS2')))
            unique = {d.contract.conId: d for d in details if d.contract.conId > 0 and d.contract.currency == 'EUR'}
            if len(unique) != 1:
                raise ValueError(f"Could not uniquely verify {o['ticker']}. No orders were approved.")
            det = next(iter(unique.values()))
            # Refresh rules for every review. Never carry a stale venue tick table.
            rebalance._RULES.pop(det.contract.conId, None)
            rebalance._cache_rules(ib, det)
            if not rebalance._RULES.get(det.contract.conId):
                raise ValueError(f"Price increments for {o['ticker']} are unavailable. Try reviewing again.")
            side = o['side']
            if side not in ('BUY', 'SELL'):
                raise ValueError('Unsupported order side.')
            quantity = decimal(o['qty'])
            estimate = decimal(o['est_price'])
            raw = Decimal(estimate) * (Decimal('1.002') if side == 'BUY' else Decimal('0.995'))
            tick = rebalance._tick_at(det.contract.conId, float(raw))
            limit = decimal(rebalance._round_tick(raw, tick, up=side == 'BUY'))
            frozen.append(dict(ticker=o['ticker'], isin=isin, con_id=det.contract.conId,
                currency='EUR', exchange='SMART', side=side, qty=quantity,
                est_price=estimate, limit_price=limit, order_type='LMT', tif='DAY',
                outside_rth=False, review=bool(o.get('review'))))
        return frozen
    return gateway.with_connection(read, mode)


def create(mode, broker_account, orders, plan_id, policy_hash, budget, method, session='', selection=None):
    now = time.time()
    for key in list(REVIEWS):
        if REVIEWS[key]['expires_at'] <= now:
            del REVIEWS[key]
    if len(REVIEWS) >= 100:
        raise ValueError('Too many active reviews. Wait two minutes and try again.')
    # One current review per browser: a re-review invalidates its previous grant.
    if session:
        for key in list(REVIEWS):
            if REVIEWS[key]['session'] == session:
                del REVIEWS[key]
    rid = secrets.token_hex(16)
    manifest = dict(version=1, review_id=rid, account=mode, broker_account=broker_account,
                    plan_id=plan_id, policy_hash=policy_hash, budget=budget, selection=selection,
                    orders=[dict(o, order_ref=f'lens-{rid[:16]}-{i}') for i, o in enumerate(orders)])
    rec = dict(manifest=manifest, digest=digest(manifest), expires_at=now+TTL,
               method=method, session=session)
    REVIEWS[rid] = rec
    return dict(review_id=rid, manifest=copy.deepcopy(manifest), expires_at=rec['expires_at'], auth_method=method)


def get(rid, session=''):
    rec = REVIEWS.get(rid) if isinstance(rid, str) else None
    if not rec or rec['expires_at'] <= time.time() or rec['session'] != session:
        raise ValueError('This review expired or changed. Review the orders again.')
    return copy.deepcopy(rec)


def consume(rid, session=''):
    rec = get(rid, session)
    del REVIEWS[rid]
    return rec


def validate_manifest(manifest, expected_digest, expected_account):
    """Executor boundary: verify every frozen field before connecting to IBKR."""
    if not expected_digest or digest(manifest) != expected_digest:
        raise ValueError('The approved orders changed. Review again.')
    if manifest.get('version') != 1 or manifest.get('broker_account') != expected_account:
        raise ValueError('The approved account changed.')
    orders = manifest.get('orders')
    if not isinstance(orders, list) or not orders:
        raise ValueError('No frozen orders to execute.')
    refs = set()
    for o in orders:
        if (type(o.get('con_id')) is not int or o['con_id'] <= 0 or o.get('currency') != 'EUR'
            or o.get('exchange') != 'SMART' or o.get('side') not in ('BUY','SELL')
            or o.get('order_type') != 'LMT' or o.get('tif') != 'DAY' or o.get('outside_rth') is not False
            or not isinstance(o.get('order_ref'), str) or not o['order_ref'].startswith('lens-')
            or o['order_ref'] in refs):
            raise ValueError('Invalid frozen order.')
        refs.add(o['order_ref'])
        decimal(o['qty']); decimal(o['limit_price']); decimal(o['est_price'])
    return orders
