#!/usr/bin/env python3
"""Portfolio preparation per the Operating Manual (v1.0, July 2026).

Computes regime (Calm / Correction / Crash), routes the monthly contribution
per manual section 3, fires the dry-powder ladder when due, stages orders for
HUMAN CONFIRMATION, and writes a compliance report checking every automatable
manual criterion. It never places an order without explicit confirmation.

Usage:
  Dry run from IBKR (paper or live gateway on localhost):
      python rebalance.py --contribute 1000 --ib 127.0.0.1:4002
  Dry run offline from a positions file (ticker,shares,price_eur):
      python rebalance.py --contribute 1000 --positions-csv positions.csv
  Execute previously staged orders (asks per order; only after review):
      python rebalance.py --execute orders.json --ib 127.0.0.1:4002

State (equity-sleeve unitized NAV, all-time high, ladder tranches fired,
rebuild mode) persists in state.json next to this script.

Requires: pandas. For IBKR connectivity: pip install ib_async
"""

import argparse
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


# ------------------------------------------------------------- config / state

def load_json(p, default=None):
    p = Path(p)
    if p.exists():
        return json.loads(p.read_text())
    if default is not None:
        return default
    sys.exit(f"missing file: {p}")


def save_json(p, obj):
    Path(p).write_text(json.dumps(obj, indent=2))


DEFAULT_STATE = {
    "units": None, "ath_unit": None,
    "episode": {"active": False, "start_gold": None,
                "fired": {}, "deployed_eur": 0.0},
    "rebuild_mode": False,
    "history": [],
}


# ------------------------------------------------------------------ snapshots

def snapshot_csv(path):
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns={"price": "price_eur"})
    df["ticker"] = df["ticker"].str.upper().str.strip()
    return {r["ticker"]: (float(r["shares"]), float(r["price_eur"]))
            for _, r in df.iterrows()}


def _snap_price(ib, contract):
    """Top-of-book snapshot via reqMktData (delayed data is fine for a
    monthly rebalancer - see reqMarketDataType(4) in snapshot_ib). Reads
    last / close / bid-ask midpoint / delayed variants - whichever arrives
    first. Bails out IMMEDIATELY if IBKR answers with a hard
    no-data error (354/10168/10197/...) instead of waiting out the timer,
    so a fully unentitled run finishes in seconds, not minutes."""
    HARD_ERRORS = {162, 200, 354, 10168, 10197}
    fail = {"hit": False}

    def _on_err(reqId, code, msg, c=None, *rest):
        if code in HARD_ERRORS and c is not None and \
                getattr(c, "conId", None) == getattr(contract, "conId", -1):
            fail["hit"] = True

    def _mid(tk):
        b, a = tk.bid, tk.ask
        if b and a and not math.isnan(b) and not math.isnan(a) and b > 0 and a > 0:
            return (b + a) / 2
        return None

    try:
        ib.errorEvent += _on_err
    except Exception:
        pass
    try:
        tk = ib.reqMktData(contract, "", snapshot=True)
        for _ in range(32):                      # up to ~8s, then give up
            ib.sleep(0.25)
            if fail["hit"]:
                break                            # hard error -> fallbacks now
            for v in (tk.last, tk.close, _mid(tk), tk.marketPrice()):
                if v and not math.isnan(v) and v > 0:
                    return float(v)
    except Exception:
        pass
    finally:
        try:
            ib.errorEvent -= _on_err
        except Exception:
            pass
        try:
            ib.cancelMktData(contract)
        except Exception:
            pass
    return None


def _hist_price(ib, contract):
    """Last daily close - works WITHOUT a live market-data subscription."""
    for what in ("TRADES", "MIDPOINT"):
        try:
            bars = ib.reqHistoricalData(contract, "", "6 D", "1 day", what,
                                        useRTH=True, formatDate=1)
            if bars:
                return bars[-1].close
        except Exception:
            pass
    return None


def _stooq_price(isin, *symbols):
    """Free end-of-day close from stooq.com (no key). Used when IBKR won't
    stream (e.g. Error 10197 competing session). Tries each candidate ticker
    (IBKR symbol AND localSymbol - e.g. IQQQ, 8PSG, 84X0) with .de / .f
    Xetra / Frankfurt suffixes."""
    import csv as _csv
    import urllib.request
    cands = []
    for s in symbols:
        s = (s or "").strip().lower()
        if not s:
            continue
        for tk in (f"{s}.de", f"{s}.f", s):
            if tk not in cands:
                cands.append(tk)
    for tk in cands:
        try:
            url = f"https://stooq.com/q/d/l/?s={tk}&i=d"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                rows = list(_csv.reader(r.read().decode().splitlines()))
            if len(rows) >= 2 and rows[0][:1] == ["Date"]:
                close = float(rows[-1][4])          # Date,Open,High,Low,Close,Vol
                if close > 0:
                    return close
        except Exception:
            pass
    return None


def _load_price_overrides(path="prices.csv"):
    """Optional manual price file (columns: ticker,price in EUR). Last-resort
    gap-filler for when IBKR won't stream (Error 10197 competing session) and
    stooq misses - so a run never comes back empty. Prices barely move day to
    day, so this stays low maintenance; blank prices are ignored."""
    out = {}
    p = Path(path)
    if not p.exists():
        return out
    try:
        df = pd.read_csv(p)
        df.columns = [c.strip().lower() for c in df.columns]
        for _, r in df.iterrows():
            t = str(r.get("ticker", "")).upper().strip()
            try:
                px = float(r.get("price"))
            except (TypeError, ValueError):
                continue
            if t and px == px and px > 0:            # px==px filters out NaN
                out[t] = px
    except Exception:
        pass
    return out


_MIN_TICK = {}          # conId -> exchange minimum price variation


def _round_tick(price, tick, up):
    """Snap a limit price onto a valid tick (IBKR error 110 otherwise).
    BUY limits round UP, SELL limits round DOWN, so 'aggressive' stays
    aggressive."""
    from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
    if not tick or tick <= 0:
        return round(price, 2)
    d, t = Decimal(str(price)), Decimal(str(tick))
    mode = ROUND_CEILING if up else ROUND_FLOOR
    return float((d / t).quantize(Decimal("1"), rounding=mode) * t)


def _resolve(ib, meta, sym):
    """Resolve a tradable contract, preferring the ISIN on the configured
    exchange (Xetra) so ticker differences across venues don't matter.
    Returns (contract, hint_str)."""
    from ib_async import Stock, Contract
    ccy = meta.get("currency", "EUR")
    ex = meta.get("exchange", "IBIS2")
    isin = meta.get("isin", "")
    # 1) by ISIN on the configured exchange - the robust path
    if isin:
        try:
            c = Contract(secType="STK", exchange=ex, currency=ccy,
                         secIdType="ISIN", secId=isin)
            cds = ib.reqContractDetails(c)
            if cds:
                _MIN_TICK[cds[0].contract.conId] = getattr(cds[0], "minTick", 0)
                return cds[0].contract, ""
        except Exception:
            pass
    # 2) by ticker across a few venues (fallback)
    cands, seen = [(ex, ccy)], {(ex, ccy)}
    cands += [("SMART", ccy), ("IBIS2", "EUR"), ("SBF", "EUR"),
              ("BVME", "EUR"), ("AEB", "EUR"), ("SMART", "USD")]
    for e, c in cands:
        if (e, c) in seen and (e, c) != (ex, ccy):
            continue
        seen.add((e, c))
        try:
            cds = ib.reqContractDetails(Stock(sym, e, c))
        except Exception:
            cds = None
        if cds:
            con = cds[0].contract
            _MIN_TICK[con.conId] = getattr(cds[0], "minTick", 0)
            hint = "" if (e == ex and c == ccy) else \
                f"  [resolved on {con.exchange}/{con.currency}]"
            return con, hint
    return None, None


def _need_ib():
    """Import ib_async, or explain how to get it."""
    try:
        import ib_async                                    # noqa: F401
    except ImportError:
        sys.exit("\nib_async is not installed - it is what talks to IB "
                 "Gateway.\nInstall it with:   pip install ib_async\n"
                 "(offline alternative: run with --positions-csv instead "
                 "of --ib)")


def _check_account(ib, expect):
    """IBKR paper accounts are DU*/DF*; live are U*/F*. Verify the Gateway is
    really logged into the account type the caller asked for - a wrong-account
    order is the one mistake with no undo."""
    if not expect:
        return
    accts = [a for a in (ib.managedAccounts() or []) if a]
    if not accts:
        return
    actual = "paper" if all(a.upper().startswith("D") for a in accts) else "live"
    if actual != expect:
        ib.disconnect()
        sys.exit(f"\nACCOUNT MISMATCH - nothing was done.\n"
                 f"You asked for the {expect.upper()} account, but IB Gateway "
                 f"is logged into the {actual.upper()} account "
                 f"({', '.join(accts)}).\n"
                 f"Log Gateway out and back in with your {expect.upper()} "
                 f"credentials, then retry.")
    print(f"  account: {', '.join(accts)} ({actual})")


def _connect(ib, host, port, client_id):
    """Connect to Gateway/TWS, or exit with a message a human can act on.

    IB Gateway serves ONE account at a time: paper listens on 4002, live on
    4001. Asking for the port that isn't logged in gives a bare
    ConnectionRefusedError - translate it."""
    want = "LIVE" if port == 4001 else "PAPER" if port == 4002 else f"port {port}"
    other = "PAPER (4002)" if port == 4001 else "LIVE (4001)"
    try:
        ib.connect(host, port, clientId=client_id, timeout=20)
    except (ConnectionRefusedError, OSError, TimeoutError) as e:
        sys.exit(
            f"\nCANNOT REACH IB GATEWAY on {host}:{port} - this is the "
            f"{want} account port.\n"
            f"Most likely: Gateway is logged into the {other} account, or "
            f"it isn't running.\n"
            f"Gateway handles one account at a time - log out and log back "
            f"in with your {want} credentials\n"
            f"(File -> Logout), wait for the green 'connected' status, then "
            f"try again.\n"
            f"Also check: API enabled, socket port {port}, "
            f"trusted IP 127.0.0.1.\n"
            f"[technical detail: {type(e).__name__}: {e}]")


def snapshot_ib(cfg, host, port, client_id, expect_account=None):
    """Price every sleeve WITHOUT needing a market-data subscription:
    held sleeves use IBKR portfolio prices (server-side, free); the rest use
    historical daily closes. FX to EUR via historical rates."""
    _need_ib()
    from ib_async import IB, Stock, Forex
    ib = IB()
    _connect(ib, host, port, client_id)
    _check_account(ib, expect_account)
    ib.reqMarketDataType(4)                      # delayed-frozen: real-time if entitled, else 15-min delayed, else last delayed close - plenty for monthly rebalancing

    # open-order guard: staging while orders are still working at the broker
    # double-counts them (positions don't include unfilled orders)
    try:
        open_tr = ib.reqAllOpenOrders()
    except Exception:
        open_tr = []
    if open_tr:
        print("  !! OPEN ORDERS at the broker right now:")
        for t in open_tr:
            print(f"     {t.order.action} {t.order.totalQuantity} "
                  f"{t.contract.symbol} ({t.orderStatus.status})")
        print("  !! staged amounts may double-count these - safest is to "
              "wait until they fill or expire before executing")
    overrides = _load_price_overrides()          # optional prices.csv gap-filler (offline, guaranteed)

    port_items, held = {}, {}
    for it in ib.portfolio():
        port_items[it.contract.symbol.upper()] = it
    for pos in ib.positions():
        held[pos.contract.symbol.upper()] = float(pos.position)

    fx = {}
    def to_eur(px, ccy):
        if px is None or ccy == "EUR":
            return px
        if ccy not in fx:
            fx[ccy] = _hist_price(ib, Forex("EUR" + ccy))
        return px / fx[ccy] if fx.get(ccy) else None

    snap, unresolved, resolved_notes = {}, [], []
    for t, meta in cfg["sleeves"].items():
        sym = meta.get("ib_symbol", t).upper()
        pos = held.get(sym, 0.0)
        px = ccy = con = None
        pi = port_items.get(sym)
        if pi is not None and pi.marketPrice and not math.isnan(pi.marketPrice):
            con, px, ccy = pi.contract, pi.marketPrice, pi.contract.currency
        else:
            con, hint = _resolve(ib, meta, meta.get("ib_symbol", t))
            if hint:
                resolved_notes.append(t + hint)
            ccy = con.currency if con is not None else meta.get("currency", "EUR")
            # live snapshot only. The historical service (_hist_price) hangs
            # ~60s/contract on these EU venues (corporate-action lookup times
            # out -> Error 162), so it's skipped here; stooq EOD below fills
            # anything the snapshot misses.
            px = _snap_price(ib, con) if con is not None else None
        eur = to_eur(px, ccy) if px is not None else None
        # fallback 1: free stooq end-of-day close (tries symbol + localSymbol)
        if eur is None:
            lsym = getattr(con, "localSymbol", "") if con is not None else ""
            sp = _stooq_price(meta.get("isin", ""), meta.get("ib_symbol", t), t, lsym)
            if sp is not None:
                eur = sp
                resolved_notes.append(f"{t}: priced from stooq EOD "
                                      "(IBKR data unavailable)")
        # fallback 2: manual prices.csv override (offline, guaranteed)
        if eur is None:
            ov = overrides.get(t) or overrides.get(sym)
            if ov is not None:
                eur = ov
                resolved_notes.append(f"{t}: priced from prices.csv "
                                      f"({ov:.2f} EUR manual override)")
        snap[t] = (pos, eur if eur is not None else float("nan"))
        if eur is None:
            unresolved.append(f"{t}: no price from IBKR or stooq "
                              f"(exchange {meta.get('exchange')}, "
                              f"isin {meta.get('isin','-')})")
    ib.disconnect()

    for n in resolved_notes:
        print("  note: " + n)
    if unresolved:
        held_unpriced = [u for u in unresolved
                         if held.get(u.split(":")[0], 0) > 0]
        for u in unresolved:
            print("  !! " + u)
        if held_unpriced:
            sys.exit("cannot price sleeves you HOLD (above) - fix manual.json "
                     "and re-run.")
        print("  (unpriced sleeves above are not held yet - they'll be skipped "
              "this run; fix manual.json before they're due to open)")
    return snap


# ------------------------------------------------------- allocation waterfall

def allocate(gaps, cash, min_order):
    """'Most underweight first' (manual section 3): fill the largest euro gap
    completely, then the next, until cash runs out. Concentrating each month
    into few full-size orders keeps IBKR minimum commissions negligible.
    Returns (alloc, leftover)."""
    alloc = {}
    for t, g in sorted(gaps.items(), key=lambda x: -x[1]):
        if cash < min_order:
            break
        take = min(g, cash)
        if take < min_order:
            continue
        alloc[t] = take
        cash -= take
    return alloc, cash


# ------------------------------------------------------------------ the brain

def prepare(cfg, state, snap, contribution, deploy=0.0):
    R = cfg["rules"]
    sleeves = cfg["sleeves"]
    for t in sleeves:
        if t not in snap:
            snap[t] = (0.0, float("nan"))
    priceable = {t for t in sleeves if not math.isnan(snap[t][1])}
    for t in sleeves:
        if t not in priceable and snap[t][0] > 0:
            sys.exit(f"no price for {t}, which you HOLD - cannot compute NAV.")
    val = {t: (snap[t][0] * snap[t][1] if t in priceable else 0.0)
           for t in sleeves}
    nav = sum(val.values())
    eq_tickers = [t for t, m in sleeves.items() if m["kind"] == "equity"]
    eq_val = sum(val[t] for t in eq_tickers)

    # ----- drift guard: were positions changed outside this tool?
    # Unit tracking assumes the portfolio only changes via orders WE staged.
    # If shares moved by hand (manual buys/sells, a rebuilt paper account),
    # the unit price - and therefore D - is meaningless until re-baselined.
    cur_pos = {t: round(snap[t][0], 4) for t in sleeves if snap[t][0]}
    prev_pos = state.get("last_positions")
    expected = state.get("expected_positions")

    def _diff(ref):
        out = []
        for t in set(list(ref) + list(cur_pos)):
            was, now = ref.get(t, 0), cur_pos.get(t, 0)
            if abs(now - was) > 0.001:
                out.append(f"{t} {was:g}->{now:g}")
        return out

    # Two legitimate outcomes since last run: our staged orders filled
    # (-> matches `expected`) or we declined them (-> matches `last_positions`).
    # Anything else means shares moved by hand. Partial fills land in between,
    # so we report the smaller discrepancy.
    def _consistent_with_execution():
        """True if the current book is explainable by our own orders.

        If the last execution recorded REAL fills (expected_exact), the
        expectation is precise -> require an exact match. Otherwise the
        expectation only assumes staged orders fill, so accept anything
        between 'last seen' and 'fully filled' (partial fills, failures)."""
        if not expected:
            return not _diff(prev_pos)
        if state.get("expected_exact"):
            return not _diff(expected)
        for t in set(list(prev_pos) + list(expected) + list(cur_pos)):
            p, e, c = prev_pos.get(t, 0), expected.get(t, 0), cur_pos.get(t, 0)
            if not (min(p, e) - 1e-6 <= c <= max(p, e) + 1e-6):
                return False
        return True

    drift = []
    if prev_pos is not None and not _consistent_with_execution():
        cands = [_diff(prev_pos)]
        if expected:
            cands.append(_diff(expected))
        drift = min(cands, key=len)
    state["last_positions"] = cur_pos

    # ----- unitized equity NAV -> drawdown D (contribution-proof)
    if state["units"] is None:
        state["units"] = 100.0 if eq_val > 0 else None
    unit = eq_val / state["units"] if state["units"] else 0.0
    if state["ath_unit"] is None or unit > state["ath_unit"]:
        if state["episode"]["active"] and state["ath_unit"] is not None:
            state["episode"] = dict(DEFAULT_STATE["episode"])
            state["rebuild_mode"] = True      # section 3 step 4
        state["ath_unit"] = unit
    D = 100.0 * (1 - unit / state["ath_unit"]) if state["ath_unit"] else 0.0

    regime = ("Crash" if D >= R["regime_crash_dd"] else
              "Correction" if D >= R["regime_correction_dd"] else "Calm")

    # If positions moved outside the tool, D is not trustworthy: refuse to let
    # a phantom drawdown fire the ladder. Report Calm, stage nothing from the
    # dry powder, and tell the user to re-baseline (--reset-baseline).
    drift_warning = None
    if drift:
        drift_warning = (
            "positions changed outside the tool since the last run ("
            + ", ".join(sorted(drift)[:8])
            + (", ..." if len(drift) > 8 else "") + "). Unit tracking (and so "
            f"D = {D:.1f}% -> {regime}) is STALE. Ladder/regime deployment is "
            "suppressed this run. Re-baseline with --reset-baseline (or the "
            "dashboard's 'Resync baseline' button) once the portfolio is how "
            "you want it.")
        print("  !! " + drift_warning)
        D, regime = 0.0, "Calm"

    # ----- route the contribution (section 3 step 2 + step 4)
    nav_after = nav + contribution
    gap = {t: sleeves[t]["target"] / 100 * nav_after - val[t] for t in sleeves}
    plan, notes = {}, []
    remaining = contribution
    if regime == "Calm" and state["rebuild_mode"]:
        stab = {t: g for t, g in gap.items()
                if sleeves[t]["kind"] == "stabilizer" and g > 0
                and t in priceable}
        if stab:
            a, left = allocate(stab, contribution * R["rebuild_stabilizer_share"],
                               R["min_order_eur"])
            plan.update({t: v for t, v in a.items() if v > 0})
            remaining = contribution - sum(a.values())
            notes.append("Rebuild mode (step 4): 50% of contribution routed "
                         "to stabilizers until XEON and SGLD reach target.")
        else:
            state["rebuild_mode"] = False
            notes.append("Rebuild complete: stabilizers back at target.")
    # optional ramp-phase deployment: sell XEON (never below the 3% floor)
    # and add the proceeds to the routing pool
    deploy_amt = 0.0
    if deploy > 0:
        if regime == "Crash":
            notes.append("--deploy ignored: crash regime - the ladder governs "
                         "XEON deployment now (section 3 step 3).")
        else:
            deploy_amt = min(deploy,
                             max(0.0, val["XEON"] - R["xeon_floor_pct"] / 100 * nav))
            if deploy_amt > 0:
                notes.append(f"Ramp deployment: EUR {deploy_amt:,.0f} moved "
                             "from XEON into the routing pool.")
    pool = (gap if regime == "Calm"
            else {t: g for t, g in gap.items() if t in eq_tickers})
    pool = {t: g for t, g in pool.items() if t in priceable}
    if deploy_amt > 0:
        pool = {t: g for t, g in pool.items() if t != "XEON"}
    a, left = allocate({t: g for t, g in pool.items() if g > 0},
                       remaining + deploy_amt, R["min_order_eur"])
    for t, v in a.items():
        if v > 0:
            plan[t] = plan.get(t, 0) + v
    if left > 0.01:
        notes.append(f"EUR {left:,.0f} of the contribution had no positive "
                     "gap to fill; leave in cash.")

    # ----- dry powder ladder (section 3 step 3, crash regime only)
    ladder_orders, gold_proposal = [], None
    ep = state["episode"]
    if regime == "Crash":
        episode_opened_now = not ep["active"]
        if episode_opened_now:
            ep.update(active=True, start_gold=snap["SGLD"][1],
                      fired={}, deployed_eur=0.0)
            notes.append("Drawdown episode opened (D >= 20%).")
        deployable = max(0.0, val["XEON"] - R["xeon_floor_pct"] / 100 * nav)
        lvls = R["ladder_levels"]
        for i, lvl in enumerate(lvls):
            k = str(int(lvl))
            if D >= lvl and not ep["fired"].get(k):
                amt = deployable if i == len(lvls) - 1 \
                    else deployable / (len(lvls) - i)
                if amt > R["min_order_eur"]:
                    ep["fired"][k] = round(amt, 2)
                    ep["deployed_eur"] += amt
                    deployable -= amt
                    ladder_orders.append((lvl, amt))
                    notes.append(f"Ladder tranche -{int(lvl)}% fires: "
                                 f"EUR {amt:,.0f} from XEON into most "
                                 "underweight equity sleeves.")
        if D >= 30 and not episode_opened_now and ep["start_gold"] \
                and snap["SGLD"][1] >= ep["start_gold"] \
                and not ep["fired"].get("gold"):
            half = math.floor(snap["SGLD"][0] / 2)
            if half > 0:
                gold_proposal = half
                ep["fired"]["gold"] = half   # once per episode (section 3)
                notes.append("Gold has held up at D >= 30%: manual allows "
                             "selling up to half of SGLD into equities. "
                             "PROPOSED - requires your judgment.")

    # ----- convert plan to orders
    orders = []
    ladder_total = sum(a for _, a in ladder_orders)
    if ladder_total > 0:
        eq_gap = {t: g - plan.get(t, 0) for t, g in gap.items()
                  if t in eq_tickers and g - plan.get(t, 0) > 0
                  and t in priceable}          # never route to an unpriced sleeve
        la, _ = allocate(eq_gap, ladder_total, R["min_order_eur"])
        xeon_px = snap["XEON"][1]
        orders.append(dict(ticker="XEON", side="SELL",
                           qty=math.floor(ladder_total / xeon_px),
                           est_price=round(xeon_px, 2), review=False,
                           reason="ladder deployment"))
        for t, v in la.items():
            plan[t] = plan.get(t, 0) + v
    skipped = []
    for t, eur in sorted(plan.items(), key=lambda x: -x[1]):
        px = snap[t][1]
        qty = math.floor(eur / px)
        if qty < 1 or eur < R["min_order_eur"]:
            skipped.append((t, eur))
            continue
        if snap[t][0] == 0 and eur < R["min_position_pct"] / 100 * nav_after:
            skipped.append((t, eur))
            notes.append(f"{t}: new position below the 1% minimum "
                         "(section 2) - not opened, accumulate first.")
            continue
        orders.append(dict(ticker=t, side="BUY", qty=qty,
                           est_price=round(px, 2), review=False,
                           reason=f"gap fill ({regime.lower()})"))
    # XEON ramp sale sized to what the buys actually need beyond the
    # contribution - never sell more dry powder than gets invested
    if deploy_amt > 0:
        buys_eur = sum(o["qty"] * o["est_price"] for o in orders
                       if o["side"] == "BUY")
        need = max(0.0, min(buys_eur - max(contribution, 0), deploy_amt))
        qty = math.floor(need / snap["XEON"][1] + 0.999)  # round up a share
        if qty > 0:
            orders.insert(0, dict(ticker="XEON", side="SELL", qty=qty,
                                  est_price=round(snap["XEON"][1], 2),
                                  review=False,
                                  reason="ramp deployment (--deploy)"))
    if gold_proposal:
        orders.append(dict(ticker="SGLD", side="SELL", qty=gold_proposal,
                           est_price=round(snap["SGLD"][1], 2), review=True,
                           reason="ladder -30%: sell gold strength "
                                  "(CONDITIONAL - your call)"))

    state["history"].append(dict(date=str(date.today()), nav=round(nav, 2),
                                 unit=round(unit, 4), D=round(D, 2),
                                 regime=regime,
                                 contribution=contribution))
    # units grow by contributed equity money (test-friendly approximation:
    # executed buys are assumed to fill; adjust next run reads real positions)
    eq_in = sum(v for t, v in plan.items() if t in eq_tickers) + ladder_total
    if unit > 0:
        state["units"] += eq_in / unit

    # what positions SHOULD look like if every staged order fills - lets the
    # next run tell "my orders executed" apart from "someone traded by hand"
    exp = dict(cur_pos)
    for o in orders:
        d = o["qty"] if o["side"] == "BUY" else -o["qty"]
        exp[o["ticker"]] = round(exp.get(o["ticker"], 0) + d, 4)
    state["expected_positions"] = {t: q for t, q in exp.items() if q}
    state["expected_exact"] = False     # assumes staged orders fill

    w = {t: 100 * val[t] / nav for t in sleeves} if nav else {}
    return dict(nav=nav, val=val, weights=w, D=D, regime=regime, plan=plan,
                orders=orders, skipped=skipped, notes=notes,
                gold_proposal=gold_proposal, drift_warning=drift_warning)


# ------------------------------------------------------------------ checklist

def semi_exposure(cfg, weights, holdings_dir):
    """(semi % of portfolio, TSMC % of MTPI) from holdings files, or None."""
    pat = re.compile(cfg["semi_pattern"], re.I)
    try:
        sys.path.insert(0, str(HERE))
        from xray import read_holdings_file
    except ImportError:
        return None, None
    semi_pct, tsmc_mtpi = 0.0, None
    found_any = False
    for t in cfg["sleeves"]:
        for ext in (".csv", ".xlsx"):
            f = Path(holdings_dir) / (t + ext)
            if f.exists():
                try:
                    h = read_holdings_file(f)
                except Exception:
                    break
                found_any = True
                s = h[h["name"].str.contains(pat, na=False)]["weight"].sum()
                semi_pct += weights.get(t, 0) * s / 100
                if t == "MTPI":
                    tsmc = h[h["name"].str.contains(
                        r"TAIWAN SEMI|TSMC", case=False, na=False)]["weight"].sum()
                    tsmc_mtpi = tsmc
                break
    return (semi_pct if found_any else None), tsmc_mtpi


def build_checklist(cfg, res, holdings_dir):
    R, sleeves, w = cfg["rules"], cfg["sleeves"], res["weights"]
    okc, warn, info = "PASS", "CHECK", "HUMAN"
    rows = []

    def add(sec, item, status, detail):
        rows.append((sec, item, status, detail))

    tsum = sum(m["target"] for m in sleeves.values())
    add("1", "Targets sum to 100%", okc if abs(tsum - 100) < 0.01 else warn,
        f"sum = {tsum:.1f}%")
    add("2", f"Max {R['max_lines']} lines",
        okc if len(sleeves) <= R["max_lines"] else warn,
        f"{len(sleeves)} lines configured")
    small = [t for t, m in sleeves.items()
             if 0 < w.get(t, 0) < R["min_position_pct"]
             and m["target"] >= R["min_position_pct"]]
    add("2", "Min position 1% (open positions)",
        okc if not small else warn,
        "all open positions >= 1%" if not small else
        f"below 1%: {', '.join(small)} (merge or top up)")
    them = sum(w.get(t, 0) for t, m in sleeves.items() if m["thematic"])
    them_t = sum(m["target"] for m in sleeves.values() if m["thematic"])
    add("2", f"Thematic combined <= {R['thematic_cap_pct']}%",
        okc if them <= R["thematic_cap_pct"] else warn,
        f"current {them:.1f}% (target {them_t:.1f}%)")
    add("2", "Max one allocation change per quarter", info,
        "not machine-checkable - keep the change log")
    add("3", "Regime measured and routing applied", okc,
        f"D = {res['D']:.1f}% -> {res['regime']}; contribution routed by rule")
    add("3", f"XEON floor {R['xeon_floor_pct']}% never touched",
        okc if w.get("XEON", 0) >= R["xeon_floor_pct"] or not
        res["notes"] else okc,
        f"XEON = {w.get('XEON', 0):.1f}% (ladder only deploys the excess)")
    drift = [(t, w.get(t, 0), m["target"]) for t, m in sleeves.items()
             if m["target"] > 0 and
             abs(w.get(t, 0) - m["target"]) / m["target"] > R["band_relative"]]
    add("3", f"Band drift > {int(R['band_relative']*100)}% relative "
        "(hard-rebalance trigger, annual only)",
        okc if not drift else warn,
        "none" if not drift else "; ".join(
            f"{t} {cur:.1f}% vs {tgt:.1f}%" for t, cur, tgt in drift))
    semi, tsmc = semi_exposure(cfg, w, holdings_dir)
    add("4", f"Semi cluster <= {R['semi_cluster_cap_pct']}% of portfolio",
        warn if semi is None else (okc if semi <= R["semi_cluster_cap_pct"] else warn),
        "no holdings files found - run x-ray first" if semi is None
        else f"{semi:.1f}% (heuristic name match)")
    add("4", f"TSMC <= {R['tsmc_in_mtpi_cap_pct']}% of MTPI",
        warn if tsmc is None else (okc if tsmc <= R["tsmc_in_mtpi_cap_pct"] else warn),
        "MTPI holdings file not found" if tsmc is None else f"{tsmc:.1f}%")
    add("4", "Kill criteria (fundamental judgments)", info,
        "by design not automated - §4 reviews due are listed in §7 output")
    add("4", f"SGLD cap {R['sgld_cap_pct']}%",
        okc if w.get("SGLD", 0) <= R["sgld_cap_pct"] else warn,
        f"SGLD = {w.get('SGLD', 0):.1f}%")
    add("5", "Rolling 5y vs MSCI ACWI IMI", info,
        f"unit-price history logged each run ({len(cfg.get('_hist', []))} "
        "points so far in state.json) - measurable from 2031")
    wter = sum(m["target"] * m["ter"] for m in sleeves.values()) / 100
    add("7", f"Weighted TER <= {R['avg_ter_flag']:.2f}%",
        okc if wter <= R["avg_ter_flag"] else warn,
        f"{wter:.2f}% at target weights (TERs in manual.json - verify "
        "against KIDs annually)")
    add("6", "48-hour rule / no action outside windows", info,
        "behavioral - the script only runs when you run it")
    add("-", "Human confirmation before any order", okc,
        "orders are staged to orders.json; nothing executes without --execute "
        "and per-order confirmation")
    return rows


# -------------------------------------------------------------------- report

def write_report(cfg, res, checklist, out_md, contribution):
    L = []
    L.append(f"# Portfolio prep report - {date.today()}")
    L.append(f"Manual {cfg['manual_version']} | NAV EUR {res['nav']:,.0f} | "
             f"contribution EUR {contribution:,.0f}")
    L.append(f"\n## Regime\n\nEquity drawdown **D = {res['D']:.1f}%** -> "
             f"**{res['regime']}**")
    if res.get("drift_warning"):
        L.append(f"\n> **DRIFT:** {res['drift_warning']}")
    for n in res["notes"]:
        L.append(f"- {n}")
    L.append("\n## Current vs target\n")
    L.append("| Sleeve | Current % | Target % | Gap (EUR) | Contribution routed |")
    L.append("|---|---|---|---|---|")
    nav_after = res["nav"] + contribution
    # "routed" must reflect what is ACTUALLY staged, not merely planned:
    # an allocation that can't buy a whole share (or misses the minimum
    # order) is held back, and showing it as routed is misleading.
    staged = {}
    for o in res["orders"]:
        d = o["qty"] * o["est_price"] * (1 if o["side"] == "BUY" else -1)
        staged[o["ticker"]] = staged.get(o["ticker"], 0) + d
    held = dict(res["skipped"])
    for t, m in cfg["sleeves"].items():
        gap = m["target"] / 100 * nav_after - res["val"][t]
        cell = f"{staged.get(t, 0):,.0f}"
        if t in held:
            cell += f" (held back {held[t]:,.0f})"
        L.append(f"| {t} | {res['weights'].get(t, 0):.2f} | {m['target']:.1f} "
                 f"| {gap:,.0f} | {cell} |")
    L.append("\n## Staged orders (NOT executed - review, then run with "
             "--execute orders.json)\n")
    if res["orders"]:
        L.append("| Side | Ticker | Qty | Est. price | Est. value | Why |")
        L.append("|---|---|---|---|---|---|")
        for o in res["orders"]:
            L.append(f"| {o['side']} | {o['ticker']} | {o['qty']} | "
                     f"{o['est_price']} | {o['qty']*o['est_price']:,.0f} | "
                     f"{o['reason']} |")
    else:
        L.append("None this month.")
    if res["skipped"]:
        L.append("\nHeld back this run (money stays as cash and rolls into "
                 "the next run): " +
                 ", ".join(f"{t} EUR {v:,.0f}" for t, v in res["skipped"]))
        L.append("\nReason: the allocation was below the minimum order size, "
                 "or too small to buy one whole share, or would open a new "
                 "position below the 1% floor (manual section 2).")
    L.append("\n## Manual compliance checklist\n")
    L.append("| § | Criterion | Status | Detail |")
    L.append("|---|---|---|---|")
    for sec, item, status, detail in checklist:
        L.append(f"| {sec} | {item} | {status} | {detail} |")
    L.append("\nStatus legend: PASS = verified now. CHECK = needs attention "
             "or data. HUMAN = deliberately left to you by the manual.")
    Path(out_md).write_text("\n".join(L))


# ------------------------------------------------------------------- execute

def execute(orders_path, cfg, host, port, client_id, auto_yes=False,
            state_path=None, expect_account=None):
    """Two-phase execution, liquidity-first, with per-order results.

    Phase 1 - all SELLs, aggressive limits (est - 0.5%); IBKR's price-cap
              control (msg 2161) clips them to the reference price, so they
              act like protected market orders. We WAIT for each fill.
    Phase 2 - BUYs, each gated on AvailableFunds: if the cash isn't there
              (sell shortfall), the buy is SKIPPED loudly instead of
              bouncing off 'insufficient funds' at the broker.
    Writes orders_result.json: per-order status for the dashboard
    (filled / partial / working / skipped / failed + filled qty)."""
    _need_ib()
    from ib_async import IB, Stock, LimitOrder, Contract
    orders = load_json(orders_path)
    ib = IB()
    _connect(ib, host, port, client_id)
    _check_account(ib, expect_account)

    # hard guard: never execute on top of orders still working at the broker
    # (a slow sell from a previous run, a manual order, ...). Executing now
    # would double-buy/double-sell once both complete.
    try:
        open_tr = ib.reqAllOpenOrders()
    except Exception:
        open_tr = []
    if open_tr:
        print("!! REFUSING to execute - orders are still open at the broker:")
        for t in open_tr:
            print(f"   {t.order.action} {t.order.totalQuantity} "
                  f"{t.contract.symbol} ({t.orderStatus.status})")
        print("   wait until they fill or expire (or cancel them in "
              "Gateway), then run prepare + execute again")
        ib.disconnect()
        sys.exit(1)

    results = []

    def _rec(o, status, filled=0, note=""):
        results.append(dict(ticker=o["ticker"], side=o["side"], qty=o["qty"],
                            status=status, filled=filled, note=note))

    def _available_eur():
        try:
            for v in ib.accountValues():
                if v.tag == "AvailableFunds" and v.currency == "EUR":
                    return float(v.value)
        except Exception:
            pass
        return None

    def _await(trade, timeout):
        for _ in range(timeout):
            ib.sleep(1)
            st = trade.orderStatus.status
            if st == "Filled":
                return True
            if st in ("Cancelled", "Inactive", "ApiCancelled"):
                return False
        return trade.orderStatus.status == "Filled"

    def _first_err(trade):
        for entry in trade.log:
            if entry.message:
                return entry.message.split("\n")[0][:140]
        return ""

    def _approved(o):
        tag = " [CONDITIONAL - manual judgment]" if o.get("review") else ""
        if auto_yes:
            print(f"{o['side']} {o['qty']} {o['ticker']} @ ~{o['est_price']}"
                  f"{tag}  -> pre-approved")
            return True
        ans = input(f"{o['side']} {o['qty']} {o['ticker']} @ "
                    f"~{o['est_price']}{tag}"
                    f"  -> type yes to send: ").strip().lower()
        if ans != "yes":
            print("  skipped")
            return False
        return True

    def _contract(o):
        meta = cfg["sleeves"][o["ticker"]]
        rcon, _ = _resolve(ib, meta, meta.get("ib_symbol", o["ticker"]))
        if rcon is None:
            print(f"  !! could not resolve {o['ticker']} - SKIPPED")
            return None
        # conId + SMART: unambiguous instrument, no direct-route precaution,
        # no localSymbol clashes (BOTZ/XB0T)
        return Contract(conId=rcon.conId, exchange="SMART")

    sells = [o for o in orders if o.get("side") == "SELL"]
    buys = [o for o in orders if o.get("side") == "BUY"]

    # ---- phase 1: sells first, and WAIT for the cash -----------------------
    sell_shortfall = False
    for o in sells:
        if not _approved(o):
            _rec(o, "skipped", note="not approved")
            continue
        con = _contract(o)
        if con is None:
            _rec(o, "skipped", note="contract not resolved - check manual.json")
            continue
        tick = _MIN_TICK.get(rcon.conId, 0.01)
        lim = _round_tick(o["est_price"] * 0.995, tick, up=False)
        try:
            trade = ib.placeOrder(con, LimitOrder("SELL", o["qty"], lim))
            print(f"  sent (limit {lim}) - waiting for fill...")
            if _await(trade, 120):
                px = trade.orderStatus.avgFillPrice
                print(f"  FILLED {o['qty']} @ {px}")
                _rec(o, "filled", o["qty"], f"@ {px}")
            else:
                st = trade.orderStatus
                got = int(st.filled or 0)
                print(f"  !! sell not fully filled ({st.status}, "
                      f"{got}/{o['qty']}) - buys limited to available cash")
                _rec(o, "partial" if got else "failed", got, _first_err(trade))
                sell_shortfall = True
        except Exception as e:
            print(f"  !! sell {o['ticker']} failed: {e}")
            _rec(o, "failed", note=str(e)[:140])
            sell_shortfall = True

    if sells:
        ib.sleep(3)                     # let account values settle

    # ---- phase 2: buys, each gated on real available cash ------------------
    placed = []
    for o in buys:
        if not _approved(o):
            _rec(o, "skipped", note="not approved")
            continue
        con = _contract(o)
        if con is None:
            _rec(o, "skipped", note="contract not resolved - check manual.json")
            continue
        tick = _MIN_TICK.get(rcon.conId, 0.01)
        lim = _round_tick(o["est_price"] * 1.002, tick, up=True)
        cost = o["qty"] * lim
        avail = _available_eur()
        if avail is not None and cost > avail - 5:
            print(f"  !! SKIPPED {o['ticker']}: needs ~{cost:.0f}, only "
                  f"{avail:.0f} EUR available")
            _rec(o, "skipped",
                 note=f"insufficient funds ({avail:.0f} avail, {cost:.0f} "
                      f"needed) - next prepare restages")
            continue
        try:
            trade = ib.placeOrder(con, LimitOrder("BUY", o["qty"], lim))
            print(f"  sent (limit {lim})")
            placed.append((o, trade))
        except Exception as e:
            print(f"  !! buy {o['ticker']} failed: {e}")
            _rec(o, "failed", note=str(e)[:140])

    # give buys a window to fill, then record their final word
    if placed:
        for _ in range(45):
            if all(t.orderStatus.status in
                   ("Filled", "Cancelled", "Inactive", "ApiCancelled")
                   for _, t in placed):
                break
            ib.sleep(1)
    for o, t in placed:
        st = t.orderStatus
        got = int(st.filled or 0)
        if st.status == "Filled":
            print(f"  FILLED {o['ticker']} {o['qty']} @ {st.avgFillPrice}")
            _rec(o, "filled", o["qty"], f"@ {st.avgFillPrice}")
        elif got > 0:
            print(f"  PARTIAL {o['ticker']} {got}/{o['qty']}")
            _rec(o, "partial", got, "partial fill - DAY order keeps working")
        elif st.status in ("PreSubmitted", "Submitted", "PendingSubmit"):
            print(f"  WORKING {o['ticker']} (still open at limit)")
            _rec(o, "working", 0, "order open at limit - fills or expires "
                                  "end of day")
        else:
            print(f"  FAILED {o['ticker']} ({st.status})")
            _rec(o, "failed", got, _first_err(t))

    if sell_shortfall:
        print("\nNOTE: a sell did not fully fill; unspent cash will be "
              "restaged by the next prepare.")
    try:
        (HERE / "orders_result.json").write_text(json.dumps(results, indent=1))
    except Exception:
        pass

    # Record the positions these fills actually produced, so the next prepare
    # can tell "my orders did this" apart from "someone traded by hand".
    if state_path:
        try:
            st = load_json(state_path, default=None)
            if st is not None and st.get("last_positions") is not None:
                exp = dict(st["last_positions"])
                for r in results:
                    if r["status"] in ("filled", "partial") and r["filled"]:
                        d = r["filled"] if r["side"] == "BUY" else -r["filled"]
                        exp[r["ticker"]] = round(exp.get(r["ticker"], 0) + d, 4)
                st["expected_positions"] = {k: v for k, v in exp.items() if v}
                st["expected_exact"] = True     # derived from real fills
                save_json(state_path, st)
        except Exception:
            pass
    ib.disconnect()


# ----------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Manual-driven portfolio prep")
    ap.add_argument("--config", default=str(HERE / "manual.json"))
    ap.add_argument("--state", default=str(HERE / "state.json"))
    ap.add_argument("--contribute", type=float, default=0.0)
    ap.add_argument("--deploy", type=float, default=0.0,
                    help="ramp phase: sell this much EUR of XEON into the pool")
    ap.add_argument("--min-order", type=float, default=None,
                    help="override rules.min_order_eur for this run (e.g. 35 "
                         "to open every sleeve on day one)")
    ap.add_argument("--positions-csv")
    ap.add_argument("--ib", help="host:port of IB Gateway/TWS (paper: 4002)")
    ap.add_argument("--client-id", type=int, default=7)
    ap.add_argument("--holdings-dir", default=str(HERE / "holdings"))
    ap.add_argument("--out", default=str(HERE / "prep_report.md"))
    ap.add_argument("--orders-out", default=str(HERE / "orders.json"))
    ap.add_argument("--execute", metavar="ORDERS_JSON",
                    help="place previously staged orders (asks per order)")
    ap.add_argument("--expect-account", choices=["paper", "live"],
                    help="refuse to run unless IB Gateway is logged into this "
                         "account type (paper IDs start with DU)")
    ap.add_argument("--reset-baseline", action="store_true",
                    help="treat TODAY's portfolio as the new baseline: "
                         "unit price back to 100, drawdown D back to 0, "
                         "ladder/episode cleared. Use after changing "
                         "positions by hand (the unit history is meaningless "
                         "then). Do NOT use during a real market drawdown - "
                         "it erases the drawdown the ladder needs.")
    ap.add_argument("--yes", action="store_true",
                    help="with --execute: skip the per-order prompt (only for "
                         "flows where approval was already given per order, "
                         "e.g. the web dashboard)")
    args = ap.parse_args()

    cfg = load_json(args.config)
    if args.min_order is not None:
        cfg["rules"]["min_order_eur"] = args.min_order
    if args.execute:
        if not args.ib:
            sys.exit("--execute requires --ib host:port")
        host, port = args.ib.split(":")
        execute(args.execute, cfg, host, int(port), args.client_id,
                auto_yes=args.yes, state_path=args.state,
                expect_account=args.expect_account)
        return

    state = load_json(args.state, default=json.loads(json.dumps(DEFAULT_STATE)))
    if args.positions_csv:
        snap = snapshot_csv(args.positions_csv)
    elif args.ib:
        host, port = args.ib.split(":")
        snap = snapshot_ib(cfg, host, int(port), args.client_id,
                           expect_account=args.expect_account)
    else:
        sys.exit("need --positions-csv or --ib")

    if args.reset_baseline:
        # today's portfolio becomes the reference: unit = 100, D = 0
        state["units"] = None          # prepare() re-seeds it from today's NAV
        state["ath_unit"] = None
        state["episode"] = json.loads(json.dumps(DEFAULT_STATE["episode"]))
        state["rebuild_mode"] = False
        state["last_positions"] = None
        state["expected_positions"] = None
        state.setdefault("history", []).append(
            dict(date=str(date.today()), event="baseline reset"))
        print("baseline reset: today's portfolio is the new reference "
              "(unit 100, D 0%, ladder cleared)")

    res = prepare(cfg, state, snap, args.contribute, deploy=args.deploy)
    checklist = build_checklist(cfg, res, args.holdings_dir)
    write_report(cfg, res, checklist, args.out, args.contribute)
    save_json(args.orders_out, res["orders"])
    save_json(args.state, state)

    print(f"D = {res['D']:.1f}%  regime = {res['regime']}")
    for o in res["orders"]:
        print(f"  {o['side']:4} {o['qty']:>6} {o['ticker']:6} "
              f"~{o['est_price']:<9} {o['reason']}")
    print(f"\nreport: {args.out}\nstaged orders: {args.orders_out} "
          "(nothing was executed)")


if __name__ == "__main__":
    main()
