# Setup guide — portfolio rebalancer

Everything you need to run this on your own laptop against **your own IBKR
paper account**. Nothing in the Python code needs editing.

Safety model, up front: the tool **never places an order on its own**. It
stages orders to `orders.json` and shows them to you; an order is only sent
after you tick it and type a confirmation phrase. Keep it on the paper
account (port 4002) for testing.

---

## 1. Install

Python 3.10+ (3.11–3.13 fine), then:

```bash
pip install pandas ib_async openpyxl
```

`openpyxl` is only needed for the x-ray tool (`xray.py`), not the rebalancer.

Put the folder wherever you like and always run from inside it:

```bash
cd ~/portfolio-tool
```

## 2. IB Gateway (or TWS)

1. Download **IB Gateway** from IBKR, log in with your **paper** credentials.
2. Configure → Settings → **API → Settings**:
   - tick **Enable ActiveX and Socket Clients**
   - **untick Read-Only API**  (needed to place orders; leave it TICKED on a
     live account except when you actually execute)
   - Socket port: **4002** for paper (4001 = live)
   - Trusted IPs: `127.0.0.1`
3. Leave Gateway running while you use the tool.

Market data: **you don't need a subscription.** The tool tries IBKR live
prices first, then free end-of-day data from justETF/Yahoo. If you see
`Error 354 / 10197 / 10168` in the log, that's expected — it just means
prices came from the free source instead. Run `python fetch_prices.py`
first (see below) and everything works regardless.

One gotcha: IBKR gives your login **one** market-data line. If you're logged
into Client Portal or the mobile app at the same time, you'll get
`Error 10197 (competing live session)`. Harmless here, but log out of those
if you want live prices.

## 3. First run

```bash
python fetch_prices.py        # fills prices.csv from justETF/Yahoo (free)
python webdash.py             # opens http://127.0.0.1:8642
```

In the browser:

- leave the toggle on **Paper** (port 4002 under the hood)
- set **contribute €** (e.g. 6145 to simulate the whole starting pot)
- **Prepare (dry run)** — nothing is sent; you get regime, staged orders,
  current-vs-target bars, and the compliance checklist
- tick the orders you approve, type **EXECUTE**, press **Execute selected**
- results repaint green (filled) / yellow (partial or still working at its
  limit) / red (skipped or failed, with the reason)

Monthly after that: `contribute 600` and repeat. `deploy N` additionally
sells up to €N of the XEON cash-parking sleeve to fund buys (used during the
ramp; leave at 0 normally).

## 4. Files — what's what

| file | role |
|---|---|
| `webdash.py` | the dashboard (start here) |
| `rebalance.py` | the engine: regime, routing, staging, execution |
| `fetch_prices.py` | free EOD prices → `prices.csv` |
| `manual.json` | **the policy**: sleeve targets, ISINs, all rules |
| `holdings/` | ETF holdings files, for the semi-cluster / TSMC checks |
| `xray.py` + `portfolio.xlsx` | look-through analysis (separate tool) |
| `dashboard.py` | static HTML report generator (pre-webdash, optional) |

Files the tool creates: `state.json` (memory: units, all-time high, ladder),
`orders.json`, `orders_result.json`, `prep_report.md`. **Start with none of
them** — a fresh `state.json` is created on first run, which is what you want
for a from-zero test.

## 5. Things worth knowing before you judge the output

- **NAV counts sleeves only, not cash.** Right after you fund the account (or
  mid-wave, with orders still working), NAV looks low and the drawdown `D`
  can read as "Correction". It corrects itself once the buys fill.
- **Whole shares only**, and a €100 minimum per order — so small sleeves
  (1–1.5% targets) don't open until the pot is big enough. That's intended:
  smallest convictions onboard last.
- **Leftover cash is normal** — rounding remainders roll into the next run.
- Sells execute **before** buys, and each buy is checked against actually
  available cash, so a sell that doesn't fill can't cause failed buys.
- If orders are still open at the broker, prepare warns and execute
  **refuses** (they'd be double-counted). Wait for fill/expiry.
- In the raw log, `Error 10349 "TIF was set to DAY"` and the
  `Canceled order:` blocks that follow are an ib_async labelling quirk — the
  colored results table shows the real final status.

## 6. What to change if you want your own allocation

Everything policy-ish lives in `manual.json`: each sleeve's `target` %,
`isin`, `exchange`, `currency`, `ter`, plus the `rules` block (min order,
thematic cap, XEON floor, regime thresholds, ladder levels…). Targets must
sum to 100 — the checklist tells you if they don't. If you change a ticker,
set its ISIN correctly: contracts are resolved by ISIN, which is what makes
cross-venue ticker differences (e.g. UMDV listing as U5MD on Xetra) a
non-issue.

## 7. Feedback that would help most

- Does a from-zero run stage sensible orders at your account size?
- Any sleeve that fails to resolve or price on your machine?
- Anything in the dashboard that's ambiguous or mis-labelled?
- Any order rejected by *your* Gateway's precautionary settings?
