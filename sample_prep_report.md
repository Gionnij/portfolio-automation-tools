# Portfolio prep report - 2026-07-07
Manual 1.0 - July 2026 | NAV EUR 99,051 | contribution EUR 1,000

## Regime

Equity drawdown **D = 31.5%** -> **Crash**
- Drawdown episode opened (D >= 20%).
- Ladder tranche -20% fires: EUR 1,176 from XEON into most underweight equity sleeves.
- Ladder tranche -30% fires: EUR 1,176 from XEON into most underweight equity sleeves.

## Current vs target

| Sleeve | Current % | Target % | Gap (EUR) | Contribution routed |
|---|---|---|---|---|
| QDVB | 11.61 | 12.0 | 506 | 506 |
| ZPRV | 2.83 | 3.0 | 202 | 202 |
| EXUS | 20.70 | 20.0 | -490 | 0 |
| IMAE | 10.30 | 10.0 | -195 | 0 |
| MTPI | 16.96 | 17.5 | 709 | 709 |
| 36BZ | 4.75 | 5.0 | 303 | 303 |
| GRID | 3.43 | 3.5 | 102 | 102 |
| XDW0 | 3.63 | 3.5 | -98 | 0 |
| 4COP | 1.41 | 1.5 | 101 | 101 |
| NUKL | 1.62 | 1.5 | -99 | 0 |
| UMDV | 2.93 | 3.0 | 102 | 102 |
| XDWH | 2.02 | 2.0 | 1 | 1 |
| IS0C | 0.96 | 1.0 | 51 | 51 |
| IH2O | 1.51 | 1.5 | 1 | 1 |
| BOTZ | 5.25 | 5.0 | -197 | 0 |
| XEON | 6.56 | 6.5 | 3 | 0 |
| SGLD | 3.53 | 3.5 | 1 | 0 |

## Staged orders (NOT executed - review, then run with --execute orders.json)

| Side | Ticker | Qty | Est. price | Est. value | Why |
|---|---|---|---|---|---|
| SELL | XEON | 16 | 140.0 | 2,240 | ladder deployment |
| BUY | MTPI | 7 | 100.0 | 700 | gap fill (crash) |
| BUY | QDVB | 5 | 100.0 | 500 | gap fill (crash) |
| BUY | 36BZ | 3 | 100.0 | 300 | gap fill (crash) |
| BUY | ZPRV | 2 | 100.0 | 200 | gap fill (crash) |

Skipped (below minimum order / 1% rule): GRID (EUR 102), UMDV (EUR 102), 4COP (EUR 101), IS0C (EUR 51), XDWH (EUR 1), IH2O (EUR 1)

## Manual compliance checklist

| § | Criterion | Status | Detail |
|---|---|---|---|
| 1 | Targets sum to 100% | PASS | sum = 100.0% |
| 2 | Max 17 lines | PASS | 17 lines configured |
| 2 | Min position 1% (open positions) | CHECK | below 1%: IS0C (merge or top up) |
| 2 | Thematic combined <= 25.0% | PASS | current 22.8% (target 22.5%) |
| 2 | Max one allocation change per quarter | HUMAN | not machine-checkable - keep the change log |
| 3 | Regime measured and routing applied | PASS | D = 31.5% -> Crash; contribution routed by rule |
| 3 | XEON floor 3.0% never touched | PASS | XEON = 6.6% (ladder only deploys the excess) |
| 3 | Band drift > 25% relative (hard-rebalance trigger, annual only) | PASS | none |
| 4 | Semi cluster <= 16.0% of portfolio | CHECK | no holdings files found - run x-ray first |
| 4 | TSMC <= 22.0% of MTPI | CHECK | MTPI holdings file not found |
| 4 | Kill criteria (fundamental judgments) | HUMAN | by design not automated - §4 reviews due are listed in §7 output |
| 4 | SGLD cap 5.0% | PASS | SGLD = 3.5% |
| 5 | Rolling 5y vs MSCI ACWI IMI | HUMAN | unit-price history logged each run (0 points so far in state.json) - measurable from 2031 |
| 7 | Weighted TER <= 0.30% | PASS | 0.24% at target weights (TERs in manual.json - verify against KIDs annually) |
| 6 | 48-hour rule / no action outside windows | HUMAN | behavioral - the script only runs when you run it |
| - | Human confirmation before any order | PASS | orders are staged to orders.json; nothing executes without --execute and per-order confirmation |

Status legend: PASS = verified now. CHECK = needs attention or data. HUMAN = deliberately left to you by the manual.