# Lens navigation and personal setup

The main destinations are **Home**, **Portfolio** and **Invest**. The name/avatar
opens the personal area. Shared navigation is composed by `navigation.py`, styled
by `navigation.css` and populated with the local name by `navigation.js`.

| Destination | Contents | Route |
| --- | --- | --- |
| Home | Saved portfolio, one next action, recent local activity | `/` |
| Portfolio · Holdings | Connected account holdings and policy targets | `/portfolio/holdings` |
| Portfolio · Research / X-Ray | Editable research portfolio and saved analysis | `/portfolio#portfolio`, `/portfolio#xray` |
| Invest | Monthly plan, exact order review, approvals, outcomes and contextual checks | `/invest` |
| Investing rules | Existing operating manual | `/invest/rules` |
| Profile · Details | Optional first name | `/profile` |
| Profile · Activity | Local personal work and paper/live receipts | `/profile/activity` |
| Profile · My data | Backups and fund data sources | `/profile/data`, `/profile/data/sources` |
| Profile · Settings | Security, appearance and connections | `/profile/settings`, `/profile/settings/appearance`, `/profile/settings/connections` |

Portfolio and X-Ray have a direct **Data sources** shortcut. The sources screen
links back to X-Ray. Unsaved research edits retain their existing leave-page warning.
Holdings uses the same balance presentation as the investing engine; the planner
is hidden in the holdings destination. Order review and execution gates are unchanged.

Old routes (`/workspace`, `/rebalance`, `/activity`, `/data-backup`, `/device-approval`,
`/manual`) redirect to the corresponding destinations. Research/X-Ray hash bookmarks
remain supported; old `#sources` bookmarks lead to Profile / My data / Data sources.
Home and profile administration use local reads; broker connection checks belong
to Holdings, Invest, and an explicit check in Settings / Connections.

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

PIN changes now live in Settings / Security. Theme choices live in Appearance and
remain per browser. App locking, multiple isolated personal profiles, working-file
encryption and backup restoration remain separate future work.
