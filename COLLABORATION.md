# Working together with Git and GitHub

This is the shared routine for Giovanni, Giulio, and any AI assistant working
on Lens. The goal is simple: `main` is always the agreed version, while every
piece of unfinished work lives on its own branch.

## The five rules

1. Never develop directly on `main`.
2. Start every new branch from an up-to-date `main`.
3. Use one branch for one feature, fix, or documentation change.
4. Push branches freely, but merge into `main` only through a pull request.
5. Never use force-push or `git reset --hard` to solve a collaboration problem.

## Start of the working day

First, tell each other what you plan to change. If both people need the same
central file, agree who goes first or divide the work into separate areas.

Then update the local copy:

```bash
git switch main
git pull --ff-only origin main
git status
```

`git status` should report a clean working tree. Create a new branch with a
short, descriptive name:

```bash
git switch -c giovanni/short-description
# or
git switch -c giulio/short-description
```

Examples: `giulio/order-history`, `giovanni/china-cap-copy`, or
`docs/collaboration-workflow`.

Do not start from another person's feature branch unless both people have
deliberately agreed to build a dependent change. Most work starts from `main`.

## Work hygiene

- Check `git status` regularly so unexpected files do not accumulate.
- Review `git diff` before staging. AI-written code receives the same review as
  human-written code.
- Stage only the files or portions that belong to one change:

  ```bash
  git add path/to/file
  git add -p
  ```

- Make small, understandable commits. A useful message says what changed and
  why, for example:

  ```bash
  git commit -m "fix: block submission when available cash is stale" \
    -m "A stale broker snapshot must not be treated as confirmed funding."
  ```

- Keep account data, credentials, PIN files, generated orders, reports, caches,
  and other runtime state out of Git.
- Run focused tests while developing. Run the complete suite before asking to
  merge.
- If `main` changes while a branch is open, bring it into the branch explicitly:

  ```bash
  git fetch origin
  git merge origin/main
  ```

  For now, use merges rather than rebasing shared branches. Merging does not
  rewrite published history.

### Instructions for AI assistants

At the start of a session, ask the assistant to inspect `git status`, the
current branch, recent commits, and the remote branches before editing. Tell it:

> Preserve existing work. Do not force-push, use `git reset --hard`, discard
> files, push directly to `main`, or resolve conflicts by blindly choosing one
> whole side. Show the diff and test results before publishing.

## End of the working day

Do not leave important work only in an uncommitted folder.

1. Inspect what changed:

   ```bash
   git status
   git diff
   git diff --check
   ```

2. Commit coherent changes. Partial work may remain on a feature branch, but
   the commit message or pull request should say what is unfinished.
3. Run the relevant tests.
4. Push the branch, never `main`:

   ```bash
   git push -u origin your-branch-name
   ```

5. Send the other person a short update: branch name, completed behavior,
   tests run, known problems, and whether the branch is ready for review.

If the work is not ready, open a draft pull request or simply leave the pushed
branch open. A pushed feature branch is a safe shared backup; it does not change
the agreed application.

## When to merge

Merge when a change is coherent, reviewed, and tested—not merely because the
day is ending. Prefer small pull requests that can be understood in one sitting.
Aim to merge ordinary changes the same day or within two working days. For a
larger feature, open a draft pull request early and split independent parts into
smaller pull requests.

When two branches overlap heavily, merge the smaller or foundational one first.
The owner of the second branch then merges the new `main`, resolves conflicts,
reruns tests, and updates the pull request.

### Before opening a pull request

```bash
git fetch origin
git merge origin/main
python -m unittest discover -s tests
node --test tests/test_investing_ui.cjs
git push
```

Use `python3` if the machine does not provide `python`.

The pull request must explain:

- what changed and why;
- visible behavior changes;
- important implementation decisions;
- tests run and their results;
- risks, assumptions, and known limitations;
- any broker, account, data, or configuration impact;
- what AI produced and what a human verified.

### Review and merge checklist

The other person reviews the changed files and checks that:

- the behavior matches the stated intention;
- trading and account-safety guards remain intact;
- no private or generated data was committed;
- the tests are meaningful and pass;
- unusual dependencies, easter eggs, or behavioral changes are intentional.

Resolve every material discussion before merging. Use **Create a merge commit**
so the pull request remains a visible unit and published branch history is not
rewritten. Only one person presses merge.

After the merge, both people update their computers:

```bash
git switch main
git pull --ff-only origin main
```

After confirming the pull request is merged, the branch owner may remove the
old local branch with `git branch -d branch-name`. Start the next task from the
new `main`; do not reuse the old branch.

## Handling conflicts

A conflict is not an error and it is not solved by choosing the newer-looking
file. Read both changes and decide what the final behavior should be. When the
conflict affects order generation, broker communication, portfolio rules, or
stored state, resolve it together. After removing conflict markers, stage the
resolved files, commit the resolution, and run the full tests again.

## If work accidentally starts on `main`

Do not pull, reset, or discard anything. First preserve the work on a branch:

```bash
git switch -c your-name/rescue-description
```

Then inspect, commit, and push that branch normally. If commits were already
pushed directly to `main`, stop and inspect the shared history together before
taking corrective action.

## Quick command reference

```bash
git status                         # What is happening locally?
git diff                           # What changed but is not staged?
git diff --cached                  # What will the next commit contain?
git log --oneline --decorate -10   # What happened recently?
git fetch origin                   # Refresh knowledge of GitHub
git pull --ff-only origin main     # Safely update a clean local main
git push -u origin branch-name     # Publish a new feature branch
```
