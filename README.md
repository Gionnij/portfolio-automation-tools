# Portfolio toolkit

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
pip install pandas openpyxl ib_async
python webdash.py
```

Open [Lens locally](http://127.0.0.1:8642). Add tickers or search by ISIN,
choose the right listing, and enter percentages totaling 100%. Run X-Ray to
see combined holdings and overlap. **Data sources** lets you verify all fund
identities with the paper Gateway and refresh supported provider downloads.

Automatic sources currently cover the original iShares, Global X and SPDR
funds (10 equity ETFs). Other funds retain their existing files or accept a
provider download link. Missing data is explicitly counted as unknown.
Research drafts stay separate from the monthly investing policy; **Monthly
investing** opens a guided contribution → preview → approval flow. Export/import a JSON investment
list to exchange a draft with someone running their own copy.

See [UI-NOTES.md](UI-NOTES.md) for supported sources, limitations and tests.
The AI advisor questionnaire remains deferred.


## Monthly investing

Open [Monthly investing](http://127.0.0.1:8642/rebalance). It starts in paper mode.

1. Choose a contribution and press **Preview my plan**. Optional cash-fund
   deployment, minimum purchases and price updates are under **Plan options**.
2. Review estimated purchases, money left from the plan, and each proposed
   order. **Portfolio balance** compares current holdings with policy targets;
   **Checks & activity** explains flagged checks, market context and snapshots.
3. Tick the individual orders you approve, open **Review selected orders**, and
   type `EXECUTE` for paper or `EXECUTE LIVE` for live before sending.

The account menu requires typing `LIVE` to switch to real money. The `•••`
**Account tools** menu contains saved-snapshot reload, discard of an unsubmitted
preview, and a deliberate tracking reset. A tracking reset clears the market
peak and deployment steps, so it should not be used to hide a market decline.

Values are dated snapshots, exclude broker cash, and are not live valuations.
The cash breakdown is contribution plus proposed sales minus proposed purchases,
not the broker's available-cash balance. Prices and fees can change. After
submission, order outcomes remain visible; there is no automatic new preview.
