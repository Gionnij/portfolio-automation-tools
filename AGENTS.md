# Collaboration workflow

- Before editing, check the current branch and working tree. Never develop on `main`.
- Use one branch per person per working day: `giovanni/YYYY-MM-DD` or `giulio/YYYY-MM-DD`, using that person's local date. Giovanni is the user of this checkout.
- At the start of a new day, update a clean `main` from `origin/main`, then create the daily branch. Reuse today's branch across tasks. If yesterday's work is unfinished, preserve it and continue that branch until ready.
- Preserve all existing edits. If edits were made on `main` accidentally, move them to the daily branch before further work; never discard them to switch branches.
- Keep each completed change in a focused commit with relevant validation. Merge through review; do not push or merge unless requested.
- Never commit private portfolio state, orders, credentials, or backups.
