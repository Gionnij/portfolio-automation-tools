# Sharing Lens with Giulio

The private repository is **Gionnij/portfolio-automation-tools**.
The current UI test build is on **`codex/lens-testing`**. Pulling `main`
alone will not get the Lens changes. Accept the repository collaborator
invitation and authenticate Git with your own GitHub account first.

## First download

Use a new folder so an older installation can stay intact:

```bash
git clone --branch codex/lens-testing https://github.com/Gionnij/portfolio-automation-tools.git ~/lens-testing
cd ~/lens-testing
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python webdash.py
```

Use Python 3.12 for the tested environment. On Windows, create the environment
with `py -3.12 -m venv .venv` and activate with
`.venv\Scripts\Activate.ps1` in PowerShell instead of `source`.

See [SETUP.md](SETUP.md) for the paper Gateway settings and a short test route.
If Git cannot authenticate, the same branch can be downloaded via GitHub's
**Code → Download ZIP** while signed in; unzip, open that folder in a terminal,
and follow the environment/install/run steps above. A ZIP copy cannot use
`git pull` for later updates.

## Update an existing Git clone

Stop its server with Ctrl+C and open a terminal inside the repository. Save
or commit any local edits before switching branches; do not discard them.

```bash
git status
git fetch origin
git switch codex/lens-testing
git pull --ff-only origin codex/lens-testing
source .venv/bin/activate
python -m pip install -r requirements.txt
python webdash.py
```

Create `.venv` as above if this installation does not have one. Restart the
server and refresh the browser after updates. Keep only one local server
running on port 8642.

## What is shared

Code, tests, documentation, `manual.json`, `portfolio.xlsx` and the original
provider files in `holdings/` are shared. The investing policy in
`manual.json` is the same for everyone using this branch; research drafts
do not change it.

Account state (`state.paper.json`, `state.live.json` and related preview/undo
files), orders, generated reports, `prices.csv`, `.workspace/` drafts and
download caches are ignored by Git. Use your own Gateway and account data;
there is no need to copy Giovanni's local state. Research drafts can be
shared deliberately using the UI's JSON export/import.

## Publication note for maintainers

The first `codex/lens-testing` build is a snapshot published through the
authenticated GitHub connector because local SSH authentication was unavailable.
Its file tree is verified against the local development commit. Giovanni's
development history remains on `codex/lens-portfolio-workspace`; `main` is
unchanged. The snapshot and development branch have different commit histories.
Do not force-push one over the other; publish subsequent testing updates on
top of the existing testing branch, or merge their histories deliberately.

## Useful feedback

Report the branch and `git rev-parse --short HEAD`, the steps that led to the
problem, and the expected versus actual result. A screenshot plus relevant
**Checks & activity** log lines helps. Remove account identifiers before
sharing logs.
