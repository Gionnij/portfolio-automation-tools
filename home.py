"""Returning-user context from local snapshots only."""
from pathlib import Path
import activity


def summary(root):
    root = Path(root)
    feed = activity.listing(root, limit=4)
    next_step = dict(title='Your portfolio', description='View your holdings and explore your saved allocation.', href='/portfolio/holdings', label='Open your portfolio')
    pending = []
    for account in ('live', 'paper'):
        try: phase = (root/f'state.{account}.pending').read_text().strip()
        except OSError: continue
        if phase in ('1','2'): pending.append((phase,account))
    pending.sort(reverse=True)
    if pending:
        phase,account = pending[0]
        if phase == '2':
            next_step = dict(title='Check your last submission.', description=f'Your {account} submission has an uncertain outcome. Check IBKR before starting another plan.', href='/invest', label='Open investing')
        else:
            next_step = dict(title='Saved investment plan', description=f'A {account} preview is saved. Open Invest to refresh and review it before approval.', href='/invest', label='Review plan')
    return dict(ok=True, next_step=next_step, needs_attention=bool(pending), recent=feed['entries'], warnings=feed['warnings'])
