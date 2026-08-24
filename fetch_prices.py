#!/usr/bin/env python3
"""fetch_prices.py - fill prices.csv with free end-of-day quotes.

Reads the sleeves (ticker + ISIN) from manual.json, prices each one, and
writes prices.csv next to this script. rebalance.py picks that file up
automatically as its last-resort price source, so after running this the
rebalancer always has a price for every sleeve - no IBKR market-data
entitlement required.

Sources tried in order (no API keys):
  1. justETF quote API by ISIN, in EUR  - covers UCITS ETFs and ETCs
  2. Yahoo Finance chart API by ticker  - tries .DE (Xetra), .MI (Milan),
     .F (Frankfurt); accepts only EUR-quoted results

Typical monthly ritual:
    python fetch_prices.py
    python rebalance.py --contribute 600 --ib 127.0.0.1:4002

Exit code 0 = every sleeve priced; 1 = some missing (listed at the end).
Requires: nothing beyond the standard library.
"""

import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept": "application/json,text/plain,*/*",
}


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def price_justetf(isin):
    """EUR quote by ISIN from justETF's public quote endpoint."""
    if not isin:
        return None
    url = (f"https://www.justetf.com/api/etfs/{isin}/quote"
           f"?locale=en&currency=EUR")
    try:
        data = json.loads(_get(url))
        px = float(data["latestQuote"]["raw"])
        return px if px > 0 else None
    except Exception:
        return None


def price_yahoo(symbol):
    """(price, currency) from Yahoo's chart endpoint, or (None, None)."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?range=5d&interval=1d")
    try:
        res = json.loads(_get(url))["chart"]["result"][0]
        meta = res.get("meta", {})
        px = meta.get("regularMarketPrice")
        if not px:
            closes = [c for c in res["indicators"]["quote"][0]["close"] if c]
            px = closes[-1] if closes else None
        cur = (meta.get("currency") or "").upper()
        if px and float(px) > 0:
            return float(px), cur
    except Exception:
        pass
    return None, None


def main():
    cfg = json.loads((HERE / "manual.json").read_text())
    sleeves = sorted(cfg["sleeves"].items(), key=lambda kv: -kv[1]["target"])

    rows, misses = [], []
    print("fetching EOD prices (EUR)...")
    for t, meta in sleeves:
        isin = meta.get("isin", "")
        px, src = price_justetf(isin), "justETF"
        if px is None:
            for sym in (f"{t}.DE", f"{t}.MI", f"{t}.F"):
                ypx, cur = price_yahoo(sym)
                if ypx is not None and cur == "EUR":
                    px, src = ypx, f"yahoo {sym}"
                    break
        rows.append([t, f"{px:.2f}" if px is not None else "",
                     meta.get("name", ""), isin])
        if px is not None:
            print(f"  {t:5s} {px:10.2f}  ({src})")
        else:
            print(f"  {t:5s}        --  MISS")
            misses.append(t)
        time.sleep(0.4)                    # be polite to the free endpoints

    out = HERE / "prices.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "price", "name", "isin"])
        w.writerows(rows)

    ok = len(rows) - len(misses)
    print(f"\nwrote {out}  ({ok}/{len(rows)} priced)")
    if misses:
        print("still missing (rerun later, or fill these rows by hand): "
              + ", ".join(misses))
        sys.exit(1)


if __name__ == "__main__":
    main()
