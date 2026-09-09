#!/usr/bin/env python3
"""List (and optionally cancel) open orders on the IBKR paper account.

IB Gateway has no order window, so a stuck order otherwise means logging into
Client Portal - which grabs the single market-data line and makes Lens fall
back to free prices. This talks to the Gateway you already have running.

    python check_orders.py                 # list only - never changes anything
    python check_orders.py --cancel        # cancel one by one, after typing CANCEL
    python check_orders.py --cancel --all  # global cancel (any client's orders)

IMPORTANT: IBKR only lets the CLIENT THAT PLACED an order cancel it. Lens uses
clientId 7 (rebalance.py --client-id), so that is the default here. Connecting
with any other id can list the orders but gets "Error 10147 ... not found" on
cancel. --all uses reqGlobalCancel, which is account-wide and ignores clientId.

Paper only: refuses to run against an account whose id does not start with DU.
"""
import argparse, sys
from ib_async import IB

ap = argparse.ArgumentParser()
ap.add_argument("--cancel", action="store_true", help="cancel the open orders")
ap.add_argument("--all", action="store_true",
                help="with --cancel: global cancel, works across clientIds")
ap.add_argument("--client-id", type=int, default=7,
                help="must match the client that placed the orders (Lens uses 7)")
ap.add_argument("--port", type=int, default=4002, help="4002 paper (default)")
ap.add_argument("--host", default="127.0.0.1")
args = ap.parse_args()

ib = IB()
try:
    ib.connect(args.host, args.port, clientId=args.client_id, timeout=15)
except Exception as exc:
    sys.exit(f"cannot reach IB Gateway on {args.host}:{args.port} with clientId "
             f"{args.client_id}.\nIs Gateway running and logged in? Is another "
             f"process already using that clientId (stop webdash.py first)?\n{exc}")

try:
    accounts = ib.managedAccounts()
    if not all(a.startswith("DU") for a in accounts):
        sys.exit(f"refusing to run: {accounts} is not a paper account (paper ids start with DU)")
    print(f"account(s): {', '.join(accounts)}  (paper, clientId {args.client_id})")

    ib.reqAllOpenOrders()
    ib.sleep(1.5)
    trades = list(ib.openTrades())
    if not trades:
        print("\nNo open orders. Lens will let you prepare and submit again.")
        sys.exit(0)

    print(f"\n{len(trades)} open order(s):\n")
    print(f"  {'SYMBOL':<8}{'SIDE':<6}{'QTY':>6}  {'LIMIT':>9}  {'FILLED':>7}  {'CLIENT':>6}  STATUS")
    for t in trades:
        o, c, st = t.order, t.contract, t.orderStatus
        print(f"  {c.localSymbol or c.symbol:<8}{o.action:<6}{o.totalQuantity:>6.0f}  "
              f"{(o.lmtPrice or 0):>9.2f}  {st.filled:>7.0f}  {o.clientId:>6}  {st.status}")
    print("\nStatus meanings: Submitted = live at the exchange · PreSubmitted = accepted "
          "but held by IBKR, not yet working at the venue · Inactive = not working.")
    mine = [t for t in trades if t.order.clientId == args.client_id]
    if len(mine) != len(trades):
        print(f"\nNote: {len(trades) - len(mine)} order(s) were placed by a different "
              f"clientId. Per-order cancel will fail on those (Error 10147) - use --all.")

    if not args.cancel:
        print("\nListing only. Re-run with --cancel to cancel these.")
        sys.exit(0)

    if input("\nType CANCEL to cancel every order above: ").strip() != "CANCEL":
        sys.exit("Nothing cancelled.")

    if args.all:
        print("  sending global cancel (account-wide, all clients)...")
        ib.reqGlobalCancel()
    else:
        for t in trades:
            ib.cancelOrder(t.order)
            print(f"  cancel sent: {t.contract.localSymbol or t.contract.symbol}")
    ib.sleep(3)
    ib.reqAllOpenOrders()
    ib.sleep(1.5)
    still = list(ib.openTrades())
    print(f"\n{len(trades) - len(still)} cancelled, {len(still)} still open.")
    if still and not args.all:
        print("Still stuck? Re-run with:  python check_orders.py --cancel --all")
finally:
    ib.disconnect()
