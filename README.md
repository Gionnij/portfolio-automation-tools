# Portfolio toolkit

For the current Lens UI test build, use branch **`codex/lens-testing`**.
Start with [SYNC.md](SYNC.md) to download it and [SETUP.md](SETUP.md) to run it
against your own paper account. `main` still contains the earlier interface.

Two tools: **X-Ray** (look-through analysis) and **Rebalancer** (monthly prep per the Operating Manual).

# Rebalancer (rebalance.py + manual.json)

Implements Operating Manual v1.0 section 3: measures equity drawdown (unitized, so contributions don't distort it), classifies Calm/Correction/Crash, routes the monthly contribution to the most underweight sleeves by regime, fires the dry-powder ladder once per tranche per episode, handles the post-crash rebuild rule, and writes `prep_report.md` with staged orders plus a compliance checklist covering every automatable manual criterion. **It never trades without you**: orders go to `orders.json`; `--execute` asks per order.

```bash
pip install pandas ib_async
# dry run against IBKR paper account (IB Gateway, port 4002):
python rebalance.py --contribute 1000 --ib 127.0.0.1:4002
# review prep_report.md, then if you approve:
python rebalance.py --execute orders.json --ib 127.0.0.1:4002
```

Setup notes:
- Targets/rules live in `manual.json` (mirror of the manual — §6.4: if they disagree, the manual wins; update both). Verify the `exchange`, `currency`, and `ter` fields against your actual IBKR listings before first use — I prefilled best guesses.
- Test a full month on the **paper account** before touching the live one.
- `state.json` holds the ATH, ladder tranches fired, and rebuild flag. Don't delete it mid-episode.
- Unit tracking assumes staged buys execute. If you decline ALL orders one month, drawdown D will read slightly too deep afterwards — it fails conservative (deploys earlier, never later).
- The semi-cluster and TSMC checks read the x-ray `holdings/` files — keep them fresh (the §7 January checklist runs both tools together).
- Offline/testing mode: `--positions-csv file.csv` with columns `ticker,shares,price` (EUR).

# Portfolio X-Ray

Look-through analysis of an ETF portfolio: aggregated stock positions, country / sector / currency / asset-class exposure, and pairwise ETF overlap.

## Setup

```bash
pip install pandas openpyxl
```

## Usage

1. Edit `portfolio.xlsx` — one row per ETF: Ticker, Weight %, optional ISIN, Override, Holdings URL.
2. Get holdings data, either way works per-ETF:
   - **Manual**: download the full holdings file from the issuer's product page and save it as `holdings/<TICKER>.csv` (or `.xlsx`). Any issuer format works — the parser auto-detects delimiter, decimal commas, header row, and column names (iShares, Xtrackers, UBS, VanEck, L&G, Invesco tested formats).
   - **Auto**: paste a direct CSV link in the "Holdings URL" column. On iShares product pages, right-click the holdings "Download CSV" button and copy the link. The script downloads it into `holdings/` on first run and reuses the file after (delete the file to force a refresh).
3. Run:

```bash
python xray.py portfolio.xlsx
```

Output: `xray_report.xlsx` with tabs — Summary (per-ETF coverage), Holdings (aggregated look-through positions, merged by ISIN across ETFs), Countries, Sectors, Currencies, Asset classes (each with chart), Overlap (pairwise % overlap between ETFs, sum of min weights).

## Overrides

For cash/commodity ETPs where look-through is meaningless, set the Override column:

- `CASH:EUR` — counts as asset class Cash, currency EUR (e.g. XEON)
- `GOLD:GOLD` — counts as asset class Gold, own currency bucket (e.g. SGLD)

## Missing country/currency (e.g. Global X, First Trust files)

Some issuers omit country/currency columns. The script fills gaps automatically:

1. Country inferred from the ISIN's first two letters (country of incorporation).
2. Currency inferred from country (US → USD, eurozone → EUR, ...).
3. Anything left: add rules to `holdings/enrich.csv` with columns `key,country,currency,sector` — key is an exact ISIN or a name substring (case-insensitive). This file survives re-downloads; never edit issuer CSVs directly.

Caveat: ISIN country = legal domicile, not economic exposure (many Chinese ADRs carry KY/US ISINs). Issuer-provided location data is used whenever present; inference only fills blanks.

## Notes

- ETFs with no holdings file are counted as "Unknown" in every exposure so totals stay honest — the Summary tab flags them.
- Currency exposure uses each holding's trading currency, not the ETF listing currency.
- Weights entered as `17.5` or `17,5%` or Excel-percent all work.

## Lens: the integrated research UI

```sh
python -m pip install -r requirements.txt
python webdash.py
```

Open [Lens locally](http://127.0.0.1:8642) to create your personal space with an
optional first name. Return visits open your home directly, with links to your
saved research portfolio, X-Ray, operating manual and monthly investing. You can
change or remove the first name under **Personal details**.

One profile is saved per Lens installation in the private, Git-ignored
`.workspace/profile.json`; it is shared across browsers using that installation
and included in data exports and encrypted backups. Creating a space keeps all
existing portfolio and policy files intact and contacts no broker or provider.
It adds no login, app lock, file encryption or trading approval. The color theme
continues to be a per-browser preference. Backup import remains deferred.

The next phase is documented in [Device approval plan](DEVICE-APPROVAL-PLAN.md):
bind review to final orders and the exact broker account, then prototype browser
Touch ID / Windows Hello approval. Device approval is not implemented; the PIN
remains required.

Open **Your portfolio** (at `/workspace#portfolio`) to add tickers or search by ISIN,
choose the right listing, and enter percentages totaling 100%. Run X-Ray to
see combined holdings and overlap. **Data sources** lets you verify all fund
identities with the paper Gateway and refresh supported provider downloads.

The last completed X-Ray is saved automatically on this computer and restored
when you return, reload the page or restart Lens. Changes to the saved portfolio,
holdings data or operating manual mark it as an earlier snapshot; choose
**Update X-Ray** to replace it. Running an X-Ray does not save portfolio edits:
use **Save portfolio** to keep those too. The saved X-Ray is included in backups.

Automatic sources currently cover the original iShares, Global X and SPDR
funds (10 equity ETFs). Other funds retain their existing files or accept a
provider download link. Missing data is explicitly counted as unknown.
Research drafts stay separate from the monthly investing policy; **Monthly
investing** opens a guided contribution → preview → approval flow. Export/import a JSON investment
list to exchange a draft with someone running their own copy.

See [UI-NOTES.md](UI-NOTES.md) for supported sources, limitations and tests.
The AI advisor questionnaire remains deferred.


## Monthly investing

Open [Monthly investing](http://127.0.0.1:8642/rebalance). Lens detects your connected Gateway before loading any account data. Port 4001 opens live; port 4002 opens paper.

1. Choose a cash budget and press **Generate investment preview**. Optional cash-fund
   deployment, minimum purchases and price updates are under **Plan options**.
2. Review estimated purchases, money left from the plan, and each proposed
   order. **Portfolio balance** compares current holdings with policy targets;
   **Checks & activity** explains flagged checks, market context and snapshots.
3. Tick the individual orders you approve, open **Review selected orders**, and
   type `EXECUTE` for paper or `EXECUTE LIVE` for live before sending.

To switch between live and paper, switch accounts in IB Gateway. Lens follows automatically. The `•••`
**Account tools** menu contains saved-snapshot reload, discard of an unsubmitted
preview, and a deliberate tracking reset. A tracking reset clears the market
peak and deployment steps, so it should not be used to hide a market decline.

The amount card shows broker EUR cash and the XEON holding/target. Portfolio
balance reads Gateway holdings with a timestamp and labels saved fallback
snapshots. Its percentages exclude cash. The preview's cash breakdown is the
entered budget plus proposed sales minus proposed purchases; prices and fees
can change. Hypothetical budgets remain previewable, but review and submission
check available funds. After submission, order outcomes remain visible while
holdings refresh; there is no automatic new preview.

## Data & backup

Open **Data & backup** in the sidebar to download all saved Lens data as a ZIP.
The export includes the saved research draft, operating manual and policy,
live/paper/legacy investment records, reports, fund holdings and price data.
`manifest.json` lists included files with sizes and SHA-256 checksums. Files keep
their original layout inside `data/`; `README.txt` explains scope and limitations.

Save research edits before navigating away. Unsaved edits, PIN/credential files,
code, files outside this installation, and records held only by IBKR are excluded.
The ZIP is **not encrypted** and may contain account details. Lens creates it
locally; the browser chooses where to save it.

Choose **Create encrypted backup** for a protected `.lensbackup` file instead.
Save the generated recovery key separately (for example in a password manager),
confirm you have saved it, then download the backup. Each backup has its own key.
Lens does not store or receive that key and cannot replace it if lost. The key
text file is unencrypted; do not keep it together with your encrypted backup.
Encryption happens in the browser using Web Crypto, with a 256 MiB export limit.
No extra packages are required. [BACKUP-FORMAT.md](BACKUP-FORMAT.md) documents the
versioned format so future recovery can decrypt these files.

Backup import is not implemented yet. Do not copy pending approvals or orders
into a running installation. Export/backup never prepares, submits or cancels
investments. Protection applies to the downloaded backup, not the original files.

Restart Lens after installing this update. Export waits for workspace writes and
refuses while an investing action is running. Avoid command-line tools that write
Lens data during export. Symlinked data is refused rather than followed.

## Gateway connection in Lens

The entire interface follows one connected IB Gateway: **live on port 4001**,
**paper on port 4002**. The broker-reported account must agree with its port. Account IDs may have alphanumeric suffixes; paper DU/DF IDs are not restricted to digits.
The same compact status indicator appears at the top right on every view.
Click it for connection details, refresh and Gateway login/trading instructions.
All views use the shared `shell.css` layout and `shell.js` status menu, based on
Monthly investing’s white sidebar, logo and spacing. There are no app account
selectors and no paper default. If both Gateways are connected, Lens asks you
to keep only the desired Gateway connected instead of guessing.

Lens checks every 30 seconds while visible, on window focus and on Refresh.
Status uses the API handshake and does not wait for positions or prices.
Account changes and disconnections clear the old view, including any in-page
approval. Monthly investing waits for detection before loading the matching
snapshot. Orders still require individual selection and PIN approval.

Holdings reads use a 20-second connection timeout, matching the investing
engine. A holdings-data failure is reported separately from a disconnected
Gateway. Unscoped `holdings.json` cache files are not used. Research allocation
edits remain intact when the connection refreshes.

Login, authentication and the Read-Only API checkbox remain in IBKR's window.
To enable investments, open **Configure → Settings → API → Settings**, untick
**Read-Only API**, apply, then refresh Lens. Confirmed read-only rejections block
review/submission; successful reads do not prove that trading is enabled.
Detection never submits test orders or changes broker settings.

After updating Python code, restart the Lens server as well as refreshing the
browser. An old server can serve new HTML without having its new API endpoints.
If connection status is unavailable, the interface asks you to restart Lens.

Offline regressions: `python -m unittest discover -s tests` and
`node --test tests/test_investing_ui.cjs tests/test_gateway_ui.cjs tests/test_shell_ui.cjs`.
