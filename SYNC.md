# Sharing + updating workflow (Giovanni ↔ Giulio)

No more zip-and-airdrop. Code lives in one git repository; **personal data
never travels**. `.gitignore` excludes `state.json`, `orders*.json`,
`prep_report.md`, `report.html`, `prices.csv` — so pulling an update can
never overwrite your portfolio's memory or your last run's results.

| stays local, per person | shared in the repo |
|---|---|
| `state.json` (units, ATH, ladder) | the five `.py` scripts |
| `orders*.json`, `prep_report.md`, `report.html` | `manual.json` (the policy) |
| `prices.csv` (regenerate: `python fetch_prices.py`) | `holdings/`, `portfolio.xlsx` |
| `state.undo.json`, `state.pending` | `SETUP.md`, `README.md`, docs |

---

## One-time: Giovanni publishes

```bash
cd ~/Desktop/Finance/portfolio
git init
git add .
git commit -m "Portfolio rebalancer"
```

Check that nothing personal got staged — this must print **nothing**:

```bash
git ls-files | grep -E "state|orders|prep_report|report.html|prices.csv"
```

Then create an empty **private** repo on github.com (no README), and:

```bash
git remote add origin git@github.com:<you>/portfolio-tool.git
git branch -M main
git push -u origin main
```

Invite Giulio: repo → Settings → Collaborators.

## One-time: Giulio clones

```bash
cd ~
git clone git@github.com:<giovanni>/portfolio-tool.git portfolio
cd portfolio
pip install ib_async pandas openpyxl
```

(Giulio can put the folder wherever he likes — the tool has no hardcoded
paths. Giovanni keeps his under `~/Desktop/Finance/`.)

If he already has a working folder with his own `state.json`, keep it:

```bash
cp ~/Investment\ package/state.json ~/portfolio/state.json   # if it exists
```

Then he works only in the cloned folder and deletes the old one.

---

## The loop, from now on

**Giovanni, after Claude changes something:**

```bash
cd ~/Desktop/Finance/portfolio
git add -A
git commit -m "fix: round limit prices to the contract's minTick (IBKR 110)"
git push
```

**Giulio, to get it:**

```bash
cd ~/Desktop/Finance/portfolio
git pull
```

That's it. His `state.json`, his orders, his reports: untouched. If he has
uncommitted local edits to a *code* file, git will say so instead of
silently clobbering them.

**Giulio, to report a bug:** open an Issue on the repo (or send the run log).
The log is far more useful than a screenshot — it contains the IBKR error
codes.

---

## If Giulio wants a different allocation

`manual.json` is shared, so pulling would overwrite his targets. Two options:

1. **Same portfolio** (current situation): change nothing, pull normally.
2. **Own allocation**: he copies it once and points the tool at his copy —
   `cp manual.json my-manual.json`, add `my-manual.json` to `.gitignore`,
   and run with `--config my-manual.json`. The dashboard doesn't expose that
   flag yet; ask Claude to add it if it becomes necessary.

---

## Useful git safety nets

```bash
git status              # what changed since the last commit
git diff                # exactly what changed, line by line
git log --oneline       # history of updates
git checkout -- <file>  # throw away local edits to one file
git revert <commit>     # undo a bad update, keeping history
```

Because every version is recorded, a bad change is one command away from
being undone — which is worth more than the whole zip dance it replaces.
