# Run and test Lens

Start with [SYNC.md](SYNC.md) to download **`codex/lens-testing`** from the
private repository. The tested environment is **Python 3.12**, with package
versions recorded in `requirements.txt`. No Node.js or frontend build is
needed to run the app.

## Install and start

Inside your downloaded repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python webdash.py
```

On later runs, activate the environment and run `python webdash.py` again.
Leave the terminal open. Ctrl+C stops the app.

Open **http://127.0.0.1:8642** for your personal space, then choose Your portfolio
for research and X-Ray, or open
**http://127.0.0.1:8642/rebalance** for monthly investing. These addresses
refer to your own laptop. Nothing connects to Giovanni's running app.

## Connect your paper account

1. Open IB Gateway and sign in to **your own paper account**.
2. In the API settings, enable socket clients where that setting is shown,
   set the socket port to **4002**, and allow `127.0.0.1` as a trusted IP.
3. Leave Gateway open. Keep Lens in its default green **paper** mode.
4. To test sending paper orders, turn off **Read-Only API** in the paper
   Gateway. The cash/holdings display only reads the account.

Lens uses port 4002 for paper and 4001 for live. It checks the account type
reported by the broker and rejects a mismatch. Order submission requires
individual order selections plus a typed confirmation. The test route below
uses paper mode throughout.

Research drafts and saved provider files can be explored without Gateway.
IBKR instrument verification, fresh account balances, and investment previews
need a working Gateway connection. Provider downloads need internet access
and some funds still require a manual file or download link.

## Suggested test route

1. **Research:** enter tickers or ISINs, resolve the correct listings, and
   set percentages totaling 100%. Check **Data sources**, refresh supported
   ETF holdings, and run **X-Ray**. Missing data remains labelled unknown.
2. **Choose an amount:** check the EUR cash figure. Under **Plan options**,
   inspect the XEON holding and target. Enter a total cash budget, including
   any uninvested cash you intend to reuse.
3. **Generate investment preview:** check proposed purchases and leftover
   cash. This stages a plan and does not send orders. If prices are missing,
   try `python fetch_prices.py` from another terminal with the same environment
   active, then regenerate. Availability of external price sources can vary.
4. **Funding check:** try a budget above your paper EUR cash, tick proposed
   orders and choose **Review selected orders**. The preview should remain
   usable, but submission should be blocked with the exact funding gap and
   the available funding options.
5. **Paper orders:** generate a funded preview, select the orders you want,
   choose **Review selected orders**, type `EXECUTE`, then **Send paper orders**.
   Inspect broker results and refresh **Portfolio balance** to check holdings.

The portfolio table defaults to held value descending, then target descending,
then ticker alphabetically. Unheld positions appear at the bottom. Gateway
read times are shown; saved snapshots are explicitly labelled when fresh
values are unavailable.

## How to interpret the preview

- The plan uses the shared policy in `manual.json`; editing a research draft
  does not replace that policy.
- The entered cash budget may include money already deposited. Do not add
  the displayed cash balance a second time. XEON deployment is separate and
  proposes selling some of that holding.
- Whole shares, minimum purchases and allocation rules leave cash uninvested.
  Changing the budget recalculates each fund's allocation before rounding;
  leftover cash is not automatically redistributed in a second pass.
- Portfolio percentages cover policy holdings and exclude uninvested cash.
  Prices, execution amounts and fees can differ from preview estimates.
- Orders already open at IBKR block another submission. Check broker status
  before preparing another set. A missing quote or unavailable balance is
  not treated as zero.

## Local files and tests

Paper and live state, preview inputs, orders, reports, price caches and
research drafts are local and Git-ignored. A fresh clone creates its own
state. Keep older state files if migrating an existing installation; do not
delete them as part of an update. See [SYNC.md](SYNC.md).

Optional developer checks (mocked broker; no real trades):

```bash
python -m unittest discover -s tests
node --test tests/test_investing_ui.cjs
```

Node.js is needed only for the second test command. The current app changes
passed 65 Python tests and 11 JavaScript tests on Giovanni's machine.
See [UI-NOTES.md](UI-NOTES.md) for implementation details and limitations.
