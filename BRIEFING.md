# Briefing — paste this into a new Claude chat

*(Giulio: copy everything below the line into your first message to Claude.
Then just talk to it normally — it will have the full picture.)*

---

I'm testing a portfolio rebalancing tool that a friend and I designed
together. He built it with Claude over the past couple of weeks; I now have my
own copy and I'm testing it against my **IBKR paper account** before anyone
trusts it further. Please help me run it, understand its output, and
investigate anything that looks wrong. Here's the full context.

## What the tool is

A **semi-automated monthly rebalancer** for a 17-sleeve ETF portfolio held at
Interactive Brokers. It reads the account, decides what to buy, and **stages**
orders — it never trades on its own. A human ticks each order and types a
confirmation phrase before anything is sent.

It encodes a written "Portfolio Operating Manual": fixed target weights,
minimum position sizes, a thematic cap, a cash-parking sleeve (XEON) used as
dry powder, a market-regime rule (Calm / Correction / Crash based on drawdown),
and a compliance checklist that re-verifies every automatable rule on each run.
The design goal is that monthly investing becomes mechanical, so it can't be
derailed by emotion or market noise.

## The files

| file | role |
|---|---|
| `webdash.py` | **the only thing I run** — local web dashboard, opens in the browser |
| `rebalance.py` | the engine: prices, regime, allocation, staging, execution |
| `fetch_prices.py` | free end-of-day prices from justETF/Yahoo → `prices.csv` |
| `manual.json` | **the policy**: sleeve targets, ISINs, exchanges, all thresholds |
| `holdings/` | ETF holdings files, used for the semiconductor-concentration check |
| `xray.py`, `portfolio.xlsx` | separate look-through analysis tool |
| `SETUP.md`, `SYNC.md` | install guide and the git workflow |

Files created per run and **never shared** (gitignored): `state.paper.json` /
`state.live.json` (portfolio memory: units, all-time high, ladder state),
`orders.*.json`, `prep_report.*.md`, `prices.csv`.

## How I run it

```bash
cd ~/portfolio
python webdash.py        # opens http://127.0.0.1:8642
```

IB Gateway must be running and logged in, with API enabled, "Read-Only API"
unticked, socket port 4002 (paper) / 4001 (live), trusted IP 127.0.0.1.

In the dashboard: set **contribute €** (new money) and optionally **deploy €**
(sell that much parked XEON to fund buys), press **Prepare (dry run)**, review,
then tick orders + type `EXECUTE` + press Execute.

## Safety model — please respect it

- The page **always opens on PAPER**. Switching to live needs a button plus
  typing `LIVE`, and live execution needs the phrase `EXECUTE LIVE`.
- The tool asks IBKR which account is connected (paper IDs start with `DU`)
  and **refuses to run on a mismatch**.
- Nothing is ever sent without per-order ticks + the typed phrase.
- Sells execute before buys, and each buy is checked against actually
  available cash.
- If orders are still open at the broker, prepare warns and execute refuses
  (they would be double-counted).
- **Never suggest removing these gates.** If something is blocked, find out
  why rather than bypassing it.

## Known quirks — these look like bugs but are not

1. **Market-data errors are normal.** `Error 354 / 10168 / 10197 / 2119` mean
   my account lacks a Xetra subscription, or another IBKR session (Client
   Portal, phone app) is holding the single market-data line. The tool falls
   back to free justETF prices and completes anyway. Run `fetch_prices.py`
   first and it's a non-issue.
2. **`Error 10349 "TIF was set to DAY"` plus `Canceled order:` blocks** in the
   raw log are an ib_async labelling quirk — the real status follows. Trust the
   coloured results table, not the log spam.
3. **NAV counts sleeves only, not cash.** Right after funding, or while orders
   are still working, NAV looks low and the drawdown `D` can wrongly read as
   "Correction". It corrects once buys fill.
4. **Leftover cash every run is expected** — whole-share rounding plus a €100
   minimum order. Held-back money rolls into the next run; the report says
   exactly how much and why.
5. **Small sleeves (1–1.5% targets) don't open early on.** Their slice is below
   the minimum order. That's deliberate: smallest convictions onboard last.
   Setting **min order € = 0** opens more of them.
6. **`D = 0%` and "positions changed outside the tool"** appears if I traded by
   hand. Unit tracking is then stale, so the tool suppresses regime/ladder
   deployment and asks me to press **Resync baseline**. That's correct — do
   that once the portfolio is how I want it.

## Bugs already found and fixed (don't re-introduce)

- Orders must be resolved **by ISIN** and submitted **by conId with SMART
  routing** — direct-to-exchange routing gets rejected by Gateway's
  precautionary settings, and ticker/localSymbol mismatches (UMDV→U5MD,
  BOTZ→XB0T) break plain-ticker orders.
- Limit prices must be rounded to the tick size IBKR actually enforces, or it
  rejects with `Error 110`. `ContractDetails.minTick` is **not** it for EU
  ETFs (it reports ~0.0001); the real increment comes from `reqMarketRule()`
  price bands. Buys round up, sells round down.
- Historical-data requests (`reqHistoricalData`) hang for ~60s per contract on
  EU venues — the tool deliberately does not use them.

## What I want to do now

Run a **from-scratch test on my paper account**: fund it, run Prepare with a
realistic contribution, inspect whether the staged orders make sense, execute
them, and check the resulting portfolio matches the intended target weights.
I'm looking for anything that behaves unexpectedly, any sleeve that fails to
price or resolve, and anything in the dashboard that's confusing or
mislabelled — my friend wants that feedback.

Please ask me what you need (screenshots of the dashboard, the run log, my
IBKR positions) rather than guessing. When something fails, the **run log from
the dashboard's Log card** is the most useful thing — it contains the IBKR
error codes.
