# Lens navigation and personal setup

The four main destinations are **Home**, **Portfolio**, **Invest**, and
**Settings**. `navigation.py` composes the shared sidebar and sticky account /
appearance header; `navigation.css` and `navigation.js` keep them consistent.

| Destination | Contents | Route |
| --- | --- | --- |
| Home | Saved allocation, pending-plan notice, recent local activity | `/` |
| Portfolio · Holdings | Connected account holdings and policy targets | `/portfolio/holdings` |
| Portfolio · Portfolio breakdown | Read-only exposure analysis of the saved allocation | `/portfolio#xray` |
| Invest | Investment plan, exact order review, approvals, outcomes and plan checks | `/invest` |
| Settings · Profile | Optional first name | `/profile` |
| Settings · Security | Existing PIN and device approval preferences | `/profile/settings` |
| Settings · Activity | Local activity and paper/live receipts | `/profile/activity` |
| Settings · My data | Backups and fund data sources | `/profile/data`, `/profile/data/sources` |
| Settings · Investing rules | Existing operating manual | `/invest/rules` |

The global account indicator contains connection instructions and account-switching
help. Lens follows the account signed into IB Gateway. The three-dot menu contains
System / Light / Dark appearance controls; Holdings and Invest also expose their
existing Account tools there. Appearance and Connections are absent from Settings
navigation; their old URLs still resolve for bookmarks.

Research editing is hidden. Old `/portfolio#portfolio` links open the read-only
breakdown, preserving saved drafts and results. The breakdown describes the saved
allocation, not necessarily the connected account's actual holdings. Its data notes
link to Settings / My data / Data sources. Editing and applying a portfolio remains
future work; no policy or order rules changed in this cleanup.

Holdings has a compact heading and no completion counter or duplicated total-value
banner. Invest no longer exposes a balance tab: contextual balance links open
Holdings. Its empty preview card is hidden until generating a plan; pending-preview
information remains beside the composer. Existing approval and execution gates
are unchanged.

Every page shares the account palette. A cached mode supplies only the initial
paint; it never selects an account or authorizes an order. Fresh Gateway data still
drives investing mode and invalidates approvals when the connection changes.
Home and Settings read connection status for the header, without fetching holdings
or creating a plan. Invest and Portfolio reuse their existing account readers.

Old routes (`/workspace`, `/rebalance`, `/activity`, `/data-backup`, `/device-approval`,
`/manual`) continue to resolve. Old `#sources` bookmarks lead to My data / Data sources.
Home metrics/history redesign, unified authentication preferences, and the mushroom
animation are separate upcoming tasks.

## First run

1. Enter an optional first name and continue.
2. Create a 4–12 digit PIN and repeat it. Existing PIN storage keeps a salted hash,
   never the digits. The PIN is not stored in browser storage or the profile.
3. Offer native device registration and its no-trade test. The user may continue
   with the PIN and configure device approval later.
4. Paper/live device approval is activated separately and explicitly. Completing
   setup does not activate a mode or send any order.
5. Open Home. Interrupted setup resumes from the saved profile/PIN/device state.

New profiles have `setup_complete: false` in version 1 `profile.json`. The completion
endpoint requires an existing PIN. Profiles created before this change (no field)
are treated as complete without rewriting their file or altering credentials.
This flag is a navigation preference, never an authorization source. Completed
profiles keep their PIN, registered passkey and existing paper/live settings.

PIN changes now live in Settings / Security. Theme choices live in the global three-dot menu and
remain per browser. App locking, multiple isolated personal profiles, working-file
encryption and backup restoration remain separate future work.

## Holdings gain/loss and investment funding — 14 September 2026

Home shows the broker-recorded cost of policy investments still held, their
current estimated value, and unrealized gain/loss in euros and percent.
`balances.summarize` aggregates by verified policy ISIN; cash and unrelated
holdings are excluded. Cost is shares × IBKR averageCost for STK instruments
(ETFs/ETCs); gain/loss is value − cost; percentage is gain/loss ÷ cost.
Missing/zero cost, missing prices, unknown identity, incomplete position sync,
short positions or unsupported contract types leave gain/loss unavailable.
A verified empty portfolio shows zero euros and no return percentage.
Foreign values and cost use the same current EUR exchange rate. This excludes
historical FX changes, distributions, interest and closed-position results; it
is neither lifetime nor annualized return. The Home disclosure explains this.
IBKR field definitions: https://www.interactivebrokers.com/docs/tws-api/doc/account-portfolio-data/account-updates/account-value-keys

The Home metric reader listens to fresh shared Gateway status, then calls the
read-only balance endpoint. Switching account/session or losing the connection
clears previous figures and invalidates in-flight responses. A failed balance
refresh within the same session labels the retained reading as last known.
No contribution history is inferred from previews, and no private metrics are
written to browser storage.

All numeric fields use typing-only text inputs with decimal keyboards and
format validation. There are no increment buttons, numeric spinners, sliders,
or wheel/arrow-key value changes, including in plan options and allocation
fields. Exact decimal amounts and XEON funding adjustments remain valid. The
funding bar now compares the cash budget with cash available, independently of
existing holdings, and stripes the unfunded portion. Exact budget, cash balance
and additional cash needed stay visible even for zero/negative cash. This is
preview context; existing funding checks, fee reserves, order selection and
PIN/device approval remain in force.

The original mushroom burst runs once after a fresh successful response includes
at least one confirmed placement. Filled/partial orders require positive filled
shares; working orders require explicit PreSubmitted/Submitted acknowledgement.
Working receipts now retain the broker status to distinguish PendingSubmit.
Errors, uncertain outcomes, previews and reopened receipts never trigger it.
Reduced-motion preferences suppress particles, which clean themselves up after
animation. The separate 420 planning easter egg remains unchanged.
