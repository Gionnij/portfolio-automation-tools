# Background for a new chat — UI/UX work on the dashboard

Paste this into a fresh Claude session before asking for interface work.

---

## What this project is

A **semi-automated monthly portfolio rebalancer** for a 17-sleeve ETF
portfolio held at Interactive Brokers. I (Giovanni) designed the investment
policy — a written "Portfolio Operating Manual" — and built this tool with
Claude over several weeks to execute it mechanically, so monthly investing
can't be derailed by emotion or market noise.

The tool reads my IBKR account, decides what to buy, and **stages** orders.
It never trades on its own: I tick each order and type a confirmation phrase
before anything is sent. It also re-verifies every automatable rule from the
manual on each run (target weights, minimum position size, thematic cap,
semiconductor concentration, weighted TER, cash floor, etc.).

It is in **real use with real money**. It has completed several live waves.
A friend (Giulio) tests it independently on his paper account.

## Where the code is

**Folder: `~/Desktop/Finance/portfolio`** — please ask for access to it at the
start of the session so you can edit files directly.

**Git: `git@github.com:Gionnij/portfolio-automation-tools.git`** (private).
Everything is versioned. Personal data is gitignored and never committed:
`state.{paper,live}.json`, `orders*.json`, `prep_report.*.md`, `report.html`,
`prices.csv`.

**Important workflow rule:** you edit files in the folder; *I* commit and
push. After you finish a change, remind me to run:

```bash
cd ~/Desktop/Finance/portfolio
git add -A && git commit -m "..." && git push
```

Giulio then runs `git pull` to get it. Never commit on my behalf.

## The files

| file | role |
|---|---|
| **`webdash.py`** | **the dashboard — this is what UI work touches** |
| `rebalance.py` | the engine (prices, regime, allocation, staging, execution) |
| `fetch_prices.py` | free end-of-day prices → `prices.csv` |
| `manual.json` | the policy: targets, ISINs, thresholds |
| `xray.py`, `dashboard.py` | separate look-through tool; older static-HTML report |
| `SETUP.md`, `SYNC.md`, `BRIEFING.md` | install guide, git workflow, briefing for Giulio |

`webdash.py` is a **single file, standard library only** — a small
`ThreadingHTTPServer` plus one big `PAGE` string containing all HTML, CSS and
vanilla JS. No build step, no framework, no CDN. It runs at
`http://127.0.0.1:8642` and shells out to `rebalance.py` for real work.
Please keep it dependency-free and single-file unless we agree otherwise.

## What the interface currently has

One folder serves **both** accounts (paper and live), with separate state
files per account.

- **Banner**: account mode, port, state-file name
- **Mode selector**: always starts on PAPER; switching to LIVE needs a button
  press plus typing `LIVE` in a prompt; the page turns red in live mode
- **Inputs**: contribute €, deploy € (sell parked cash-sleeve to fund buys),
  min order €, "refresh prices" checkbox
- **Buttons**: Prepare (dry run), Undo state, Resync baseline
- **Status chips**: regime (Calm/Correction/Crash), drawdown D, PASS/CHECK
  counts, "preview not executed", drift warning, account
- **Staged orders**: table with per-order checkboxes, then a confirmation
  phrase field (`EXECUTE` / `EXECUTE LIVE`) and the Execute button
- **Execution results**: same table repainted green (filled) / yellow
  (partial or still working) / red (skipped or failed, with reason)
- **Current vs target**: per-sleeve bars (light = target, dark = current),
  current %, target %, gap €, routed €
- **Compliance checklist**: § / criterion / status chip / detail, long details
  collapsed
- **Log**: collapsible raw output of the run

## Safety model — must be preserved

These are deliberate and load-bearing. Please don't weaken them, and don't
propose removing friction to "streamline" the flow:

1. Nothing is sent without **per-order checkboxes** plus the **typed phrase**.
2. The page always opens on PAPER; live mode requires an explicit arming step.
3. The engine asks IBKR which account is connected (paper IDs start with
   `DU`) and **refuses to run on a mismatch**.
4. Sells execute before buys; each buy is gated on actually available cash.
5. If orders are still open at the broker, prepare warns and execute refuses.
6. If positions changed outside the tool, drawdown tracking is treated as
   stale and automatic deployment is suppressed until I press Resync.

## Known UX pain points (starting list, not exhaustive)

- The **log is very noisy**: IBKR emits `Error 10349 "TIF was set to DAY"`
  plus a `Canceled order:` block for every order, which is a harmless
  ib_async labelling quirk but looks alarming. Real errors get buried.
- **Market-data errors** (`354 / 10168 / 10197`) are expected and harmless —
  prices fall back to a free source — but they read like failures.
- **NAV excludes cash**, so mid-wave the drawdown can briefly show
  "Correction" for a reason that isn't explained on screen.
- **Held-back money** (whole-share rounding, minimum order, 1% floor) is
  explained only in the report text, not visibly in the table.
- No **history view**: `state.*.json` holds a run history and unit prices, but
  the page shows nothing over time.
- No indication of **which price source** each sleeve used (live IBKR /
  free EOD / manual override) except buried in the log.
- The **compliance checklist** is long and always fully expanded; PASS rows
  dominate while CHECK rows are what matter.
- Numbers are dense; there's no summary line like "deploying €1,142 of €1,250
  across 5 sleeves, €108 rolls over".

## How we test

There's no live-broker test environment, so changes are verified with an
**offline mock of `ib_async`** — a fake IB class injected into `sys.modules`
that simulates contract resolution, market rules, fills, partial fills and
rejections. Several real bugs were caught this way before reaching the
account. Please test changes rather than assuming, and prefer verifying
against the real `prep_report.*.md` files in the folder.

## Tone

I'm not a professional developer but I'm comfortable in the terminal and I've
been deeply involved in every design decision. Explain trade-offs, push back
if an idea is bad, and tell me when something is a judgment call rather than
a right answer.
