# Portfolio Operating Manual
**Version 1.1 — July 2026 · Review annually or on trigger**

This document exists so that decisions are made by rules written in calm weather, not by feelings in a storm. If an action isn't covered here, the default is: do nothing for 30 days, then re-read this document.

---

## 1. Target allocation

| Sleeve | Ticker | Target % | Role |
|---|---|---|---|
| US quality | QDVB | 11.0 | Core equity, quality screen |
| US small-cap value | ZPRV | 3.0 | Anti-megacap expression inside US |
| Developed world ex-US | EXUS | 20.0 | Core equity |
| Europe | IMAE | 10.0 | Deliberate Europe overweight |
| EM ex-China | MTPI | 15.5 | Core EM (carries the semis cluster) |
| China A | 36BZ | 5.0 | Onshore China real economy |
| China offshore | ICHN | 3.0 | China platform/consumer economy (HK & foreign listings) |
| Grid infrastructure | GRID | 3.5 | Electrons: transmission |
| World energy | XDW0 | 3.5 | Electrons: fuel & generation (value leg) |
| Copper miners | 4COP | 1.5 | Electrons: raw material |
| Uranium & nuclear | NUKL | 1.5 | Electrons: nuclear ecosystem |
| US medical devices | UMDV | 3.0 | Demographics |
| World healthcare | XDWH | 2.0 | Demographics |
| Agribusiness | IS0C | 1.0 | Essentials: food |
| Global water | IH2O | 1.5 | Essentials: water |
| Robotics & AI | BOTZ | 5.0 | Labor scarcity / automation |
| EUR cash (overnight) | XEON | 6.5 | Dry powder |
| Physical gold | SGLD | 3.5 | Sovereign-math insurance |
| **Total** | | **100.0** | |

**Structural bets this implies (accepted knowingly):** ~26% look-through US vs ~64% market weight; ~8.7% total China (5 onshore / 3 offshore / ~0.7 residual); ~12.5% semiconductor supply chain (mostly via MTPI); ~10% energy/electrification complex; ~25% Europe; 10% stabilizers.

---

## 2. Position discipline

- **Maximum 18 lines.** A new idea must replace an existing position, never join the list. *(Raised from 17 in v1.1 to admit ICHN; the next idea replaces, no exceptions.)*
- **US floor: look-through US equity ≥ 25% of portfolio** (direct US funds ≥ 14%). Derivation: at ~26% US, a repeat of 2010s-style US outperformance (~8pp/yr over RoW) costs ~3%/yr vs ACWI — exactly the §5 capitulation threshold. Going lower guarantees capitulation at maximum pain if the contrarian view is wrong. The anti-US view is expressed *within* this rail, never through it.
- **China cap: total look-through China ≤ 10% of portfolio.** Sizing is set by decree risk (Russia-2022 precedent: foreign holders marked to ~zero overnight), not by upside conviction. 10% marked to zero is a brutal year; more starts moving the FIRE date. Correlates with the Taiwan tail already carried by the semi cluster — the two must be considered together.
- **Minimum position: 1%.** Nothing smaller may be opened; if a position falls below 1% at review due to a fund event (not drawdown), merge or close it.
- **Thematic sleeves capped at 25% combined** (currently ~21.5%). If drift pushes them above, trim back at annual review.
- **Maximum one allocation change per quarter.** Scarcity of action is a feature.

---

## 3. Contributions and adaptive DCA

Contributions are monthly. All routing is done with new money first — selling is a last resort (it costs spread, and rebalancing by contribution is free).

**Step 1 — Measure.** Each month, compute current weights and the equity drawdown *D* = decline of the total equity sleeve (everything except XEON/SGLD) from its all-time high in EUR.

**Step 2 — Route by regime.**

| Regime | Equity drawdown D | Rule |
|---|---|---|
| Calm | < 10% | Route contribution to the most underweight sleeves (stabilizers count as sleeves — this is when they get refilled to target). |
| Correction | 10–20% | 100% of contribution to equity sleeves, most underweight first. No stabilizer top-ups. |
| Crash | > 20% | 100% of contribution to equities **and** deploy dry powder per Step 3. |

**Step 3 — Dry powder deployment ladder (crash regime only).**
Deployable cash = XEON balance above the 3% floor. The floor is never touched; it is the emergency reserve, not investment ammunition.

- At **−20%**: deploy 1/3 of deployable cash into the most underweight equity sleeves.
- At **−30%**: deploy another 1/3, plus up to half of the gold position if gold has held up or risen (sell strength, buy weakness).
- At **−40%**: deploy the remainder of deployable cash.

Each tranche fires once per drawdown episode. An episode ends when the equity sleeve makes a new all-time high.

**Step 4 — Rebuild.** After a new all-time high, route 50% of each contribution to XEON/SGLD until both are back at target, the rest per the calm rule.

**Hard rebalancing (selling):** only at annual review, and only if a sleeve has drifted more than 25% *relative* from target (e.g., a 5% sleeve beyond 6.25% or below 3.75%) and contributions cannot plausibly fix it within 6 months.

---

## 4. Kill criteria — per sleeve

A kill criterion is the evidence that would prove the thesis wrong. Price alone is never a kill criterion for a thesis position; fundamentals are. Review each on its date, act within one quarter of a trigger.

| Position | Thesis (one line) | Kill / action trigger | Review |
|---|---|---|---|
| US underweight (structural) | US megacaps are priced for perfection | If by **2030** US megacap *earnings* have grown into their multiples (no valuation expansion needed to justify prices), cut the underweight in half — move ~5% from EXUS/IMAE to QDVB | Every 2 years |
| ZPRV | Small-cap value is the cheapest neglected corner of the cheapest neglected factor | Judged on a decade, not years. **No performance-based kill before 2033.** Exit only on fund closure, TER hike, or index methodology change | 2033 |
| MTPI / semis cluster | EM ex-China growth, accepting the chip concentration | If TSMC exceeds **22% of MTPI** or the total semi cluster exceeds **16% of portfolio**, trim MTPI and route proceeds to the most underweight core sleeve | Annual |
| 36BZ | Onshore China domestic economy, uncorrelated policy cycle | Exit if Stock Connect access is restricted / capital repatriation is impaired, or if the position is >40% underwater with no domestic stimulus cycle by **2029** | Annual |
| ICHN | China offshore: platform economy at a structural discount, shareholder-return reforms gaining traction | Exit immediately if VIE/P-chip structures are legally impaired or HK/foreign listings face forced delisting or capital controls. Exit by **2030** if payout ratios and buybacks have not structurally improved (state-over-shareholder alignment confirmed). Onshore and offshore fail differently — this criterion is independent of 36BZ's | Annual |
| GRID | Grid capex supercycle: transmission is the bottleneck | Fold into XDW0 if by **2029** grid capex growth has stalled (utility capex plans flat in real terms) or the fund trades >2× market P/E without matching earnings growth | 2029 |
| XDW0 | Energy majors: cheap, disciplined, structurally underowned | Exit on either: (a) capital discipline breaks — majors return to debt-funded megaprojects and dividend cuts; or (b) thesis completes — sector re-rates to market multiple. (b) is a *victory* exit | Annual |
| NUKL | Nuclear renaissance moves from rhetoric to concrete | Exit if by **end-2030** Western FIDs and restarts have not materially progressed beyond the 2026 announcements (still summits, not concrete pours) | 2028 check, 2030 verdict |
| 4COP | Copper: demand from every thesis, supply takes 15 years | Trim half on a 2× re-rate; exit if grid/EV capex collapses for structural (not cyclical) reasons | Annual |
| BOTZ | Automation is the only answer to demographic labor scarcity | Exit if by **2029** the fund's top holdings still show story-stock economics (widening losses, revenue misses) rather than industrial revenue growth | 2029 |
| UMDV / XDWH | Aging populations consume healthcare regardless of GDP | Near-permanent. Exit UMDV only if US policy durably crushes device pricing power (regulated margins). XDWH has no thesis kill — review for fund quality only | Every 2 years |
| IS0C / IH2O | Food and water are the ultimate non-discretionary | Permanent. Review only TER, tracking, and fund viability | Every 2 years |
| SGLD | Insurance against sovereign math | **No kill criterion — insurance is not a trade.** Cap at 5%; trim above | Never |
| XEON | Optionality | No kill. Floor 3%, target 6.5% | — |

---

## 5. Global kill criterion — the capitulation clause

The whole strategy is falsifiable too. If, over any **rolling 5-year period**, the portfolio underperforms MSCI ACWI IMI by more than **3% annualized** *and* the majority of sleeve theses show no fundamental confirmation (not price — fundamentals: energy capex, reactor construction, automation revenue, US earnings convergence), then the worldview is wrong, not early.

**Action:** migrate 70% of the portfolio to a plain world index fund over 12 months, keep stabilizers, keep at most 2 thematic convictions. This clause exists because the failure mode of contrarians is not being wrong — it's staying wrong for twenty years out of identity.

---

## 6. Behavioral rules

1. **The 48-hour rule.** No portfolio action within 48 hours of consuming news that provoked the urge. If the idea survives 48 hours and a re-read of this document, it may be scheduled for the next quarterly window.
2. **Underperformance is the price of the strategy.** This portfolio is built to deviate from the index. Expect multi-year stretches of looking stupid; that is tracking error, not failure. Failure is defined in §4 and §5 only.
3. **Never check prices more than weekly in calm regimes.** In crash regimes, check monthly against the deployment ladder — the ladder replaces judgment precisely when judgment is worst.
4. **One source of truth.** Targets live in this document. If the spreadsheet and this document disagree, this document wins until formally revised.
5. **Revisions require a version bump, a date, and one written sentence of justification.** If the justification sounds like a rationalization of recent price action, it is.

---

## 7. Annual maintenance checklist (each January)

- [ ] Re-run the x-ray script; verify no sleeve has silently changed character (the WIRE lesson)
- [ ] Check semi cluster ≤ 16% and TSMC ≤ 22% of MTPI
- [ ] Check look-through US ≥ 25% and total China ≤ 10%
- [ ] Check thematic total ≤ 25%
- [ ] Check weighted TER; flag if portfolio average exceeds ~0.30%
- [ ] Check band drift (>25% relative) — schedule hard rebalance if contributions can't fix it
- [ ] Review kill criteria due this year (§4)
- [ ] Compute rolling 5-year gap vs MSCI ACWI IMI (§5)
- [ ] Verify fund health: AUM, TER changes, index changes, domicile
- [ ] Re-read §6. Change nothing else.

---

## 8. Revision history

| Version | Date | Change | Justification (one sentence, per §6.5) |
|---|---|---|---|
| 1.0 | July 2026 | Initial manual | — |
| 1.1 | July 2026 | Added ICHN 3% (funded MTPI 17.5→15.5, QDVB 12→11); line max 17→18; added US floor (≥25%) and China cap (≤10%) rails; added ICHN kill criterion | No fund in the portfolio held the offshore half of the Chinese economy (MTPI is ex-China), and the directional anti-US view is now expressed inside hard rails derived from the §5 capitulation threshold and decree-risk sizing rather than from perception. |
