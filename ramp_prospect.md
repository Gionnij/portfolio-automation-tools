# Deployment prospect — July to December 2026

Simulated with the actual `rebalance.py` + `manual.json` (min order EUR 100), chained state month to month. Prices are placeholders and assumed flat; your real runs use live quotes, so quantities will differ — the *structure* is what this document verifies. Commissions modeled at EUR 1.25/order.

## How to read the commands

- `--contribute 600` = new cash deposited this month.
- `--deploy 1050` = permission to sell **up to** EUR 1,050 of parked XEON to fund buys beyond the contribution. The script sells only what the staged buys actually need, never below the 3% XEON floor.
- Leftover cash (whole-share rounding, sub-minimum gaps) rolls into next month's pool automatically.

## Month by month

**Wave 1 — today (manual tickets, ~EUR 6,145):**
EXUS 34 sh ≈ 1,190 · MTPI 167 sh ≈ 1,069 · QDVB 12 sh ≈ 696 · IMAE 7 sh ≈ 616 · SGLD 1 sh ≈ 305 · XEON 15 sh ≈ 2,190 (queue). Deployed ≈ 63%, idle ≈ EUR 72.

**Wave 2 — Jul 24** (`--contribute 600 --deploy 1050`): sells 7 XEON (≈1,022); opens 36BZ ≈334, BOTZ ≈336, GRID ≈228, XDW0 ≈204, ZPRV ≈192, UMDV ≈198, tops EXUS ≈140. Total invested ≈ EUR 1,630.

**Wave 3 — Aug 24** (`--contribute 600 --deploy 900`): sells 3 XEON (≈438); opens XDWH ≈100, 4COP ≈102, NUKL ≈108, IH2O ≈66; tops MTPI/QDVB/EXUS/IMAE. Ramp essentially complete — XEON lands near target.

**Sep–Dec** (`--contribute 600` each): pure maintenance — 2–7 orders/month to whichever sleeves drifted most underweight (EXUS/MTPI dominate since they're the biggest targets; satellites get topped when it's their turn).

## End state (December, flat prices)

| Sleeve | Weight | Target | | Sleeve | Weight | Target |
|---|---|---|---|---|---|---|
| EXUS | 19.9% | 20.0 | | XDW0 | 3.2% | 3.5 |
| MTPI | 17.5% | 17.5 | | SGLD | 3.2% | 3.5 |
| QDVB | 12.0% | 12.0 | | ZPRV | 2.0% | 3.0 |
| IMAE | 9.1% | 10.0 | | UMDV | 2.1% | 3.0 |
| XEON | 7.5% | 6.5 | | XDWH | 1.0% | 2.0 |
| 36BZ | 4.7% | 5.0 | | 4COP | 1.1% | 1.5 |
| BOTZ | 4.5% | 5.0 | | NUKL | 1.1% | 1.5 |
| GRID | 3.1% | 3.5 | | IH2O | 0.7% | 1.5 |
| | | | | **IS0C** | **0%** | **1.0** |

NAV ≈ EUR 9,695, cash buffer ≈ EUR 739 (rounding remainders — recycled automatically).

## Notes and caveats

1. **IS0C** (1% sleeve) just misses the EUR 100 floor through December (gap ≈ 97). It opens in January naturally, or run any wave with `--min-order 90` to pull it forward. This is the last-in-line behavior working as intended: your smallest conviction onboards last.
2. **Costs**: ~40 orders over 6 months ≈ EUR 50 ≈ 0.5% of NAV, one-time ramp overhead. Raising `min_order_eur` back to 150–200 would cut this ~30% but delay satellites; EUR 100 is the compromise you asked for.
3. Whole-share rounding keeps a small cash buffer at all times; it shrinks as NAV grows and share prices become small relative to orders.
4. Flat-price assumption: in reality drift changes each month's order list — that's the point of running the script monthly instead of following this document literally. This prospect validates the *mechanism*, not the specific quantities.
5. Not financial advice; the schedule and floors are yours to change in `manual.json`.
