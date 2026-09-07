# Lens workspace — September 2026 handover

The default page is now a portfolio research workspace. Run `python webdash.py`
and open http://127.0.0.1:8642. Monthly investing remains at `/rebalance` with
its existing account, per-order approval and confirmation gates.

## What works

- Edit an investment list and percentage allocation; require positive weights
  totaling 100% before analysis. ISIN checksums and duplicate funds are checked.
- Search the original fund catalog offline, or use paper IBKR search for other
  tickers / names / ISINs. Resolve search candidates to an ISIN and contract ID;
  show exchange and currency before adding. A ticker is never the storage key.
- Verify all fund IDs from Data sources. All 17 original ISINs resolved to
  unique EUR contracts during testing against the paper Gateway.
- Fetch current holdings for seven original iShares ETFs, Global X 4COP/BOTZ,
  and SPDR ZPRV. Discover actual download links from provider pages and verify
  the page ISIN. iShares supports both CSV and its current XML workbook format;
  the latter verifies the share-class ISIN in the Key Facts sheet.
- Validate the holdings before atomically replacing the cached snapshot.
  Website errors, identity mismatches and incomplete downloads keep prior data.
  Ordinary small cash liabilities retain their signed weights; short equities
  require a different model and are rejected.
- Analyze the draft with the existing X-Ray engine: combined positions, country,
  sector, currency, fund overlap, source coverage and unknown allocation.
  Missing supported funds are downloaded on first analysis. Existing snapshots
  are reused until the user explicitly refreshes them.
- Save locally and export/import a JSON investment list for another local copy.
  The full X-Ray can be exported as JSON, including provenance and methodology.

## Intentional boundaries

- The research draft is **not** the operating manual. Editing / importing /
  saving a draft cannot update targets used for orders. Drafts never place orders.
- Local-only server: no hosted sharing, login system, synchronization, or
  multi-user isolation. Friends can run their own copies and exchange portfolio
  lists. Broker account state and generated snapshots are not included in exports
  of the investment list or committed to Git.
- Xtrackers EXUS/XDW0/XDWH, First Trust GRID and VanEck NUKL still use existing
  local holdings or a user-supplied provider link. DWS and VanEck did not provide
  usable downloads to the tested automated requests. They must not be presented
  as refreshed. New funds outside the registered adapters may also need a link.
- This is one-level look-through. Nested ETFs are not expanded recursively.
  Missing ISINs use the existing normalized-name merge heuristic. Country is
  reported location or inferred domicile, not revenue exposure; inferred
  currency is a fallback, not a measurement of economic FX risk.
- Publication dates may differ between funds. The UI distinguishes retrieval
  timestamps from source dates and says when dates are unavailable. CSV dates
  for Global X come from AS_OF_DATE in the download, not another page section.
- Provider weights are preserved, including rounding and small signed cash
  balances. Totals can differ slightly from 100%. Unknown country exposure is
  explicitly visible even if it would otherwise fall into the Other chart bar.
- The future AI advisor / suitability questionnaire is not implemented.

## Existing-data correction

The manual called NUKL “Global X Uranium UCITS”, although ISIN IE000M7V94E1 is
VanEck Uranium and Nuclear Technologies UCITS. Only its descriptive name was
corrected; allocations, routing, cash rules and order logic were preserved.
Official source: https://www.vaneck.com/ie/en/investments/nuclear-etf/

The existing parser also treated every bare stock symbol as American. This
assumption was removed. It still uses recognized exchange suffixes and ISIN
prefixes when provider country data is absent. Unknowns remain unknown.

## Files and dependencies

- `webdash.py`: existing HTTP server and monthly investing UI, plus routing.
- `workspace.html`: responsive UI, system fonts, vanilla JS and CSS; no build,
  framework, external scripts, or CDN.
- `workspace.py`: identity resolution, provider adapters, local draft/snapshot
  storage, asynchronous data jobs and X-Ray JSON adaptation.
- `.workspace/`: ignored local drafts, verified IDs and ISIN-keyed snapshots.
- `tests/test_workspace.py`: offline fixtures for exposure math and safeguards.

Runtime dependencies remain `pandas openpyxl ib_async`. Research with saved
identities and local files needs no broker connection. Broker lookup uses
read-only requests to port 4002 and refuses non-paper account IDs.

## Verification

Run from this folder:

```sh
python -m unittest discover -s tests -v
python -m py_compile webdash.py workspace.py xray.py
```

Tests hand-check weighted holding aggregation, overlap, missing-file remainders,
ISIN aliasing and collisions, invalid weights, source identity mismatches,
failed-refresh preservation, current provider headers, signed cash, country
inference, local HTTP origin checks and existing execution confirmation gates.
Real provider downloads and real paper-broker identity lookup were tested
separately. No orders were placed for this UI work.
