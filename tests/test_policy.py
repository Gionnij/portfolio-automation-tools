"""Manual v1.1 allocation, geographic estimates and stale-preview regressions."""
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy import allocation_checks
import test_investing
import webdash


class PolicyChecks(unittest.TestCase):
    def test_config_matches_authoritative_manual(self):
        root = Path(__file__).resolve().parents[1]
        cfg = json.loads((root / 'manual.json').read_text())
        table = (root / 'portfolio_operating_manual.md').read_text().split('## 2.')[0]
        targets = {t: float(w) for t, w in re.findall(r'^\|[^|]+\|\s*([A-Z0-9]+)\s*\|\s*([\d.]+)\s*\|', table, re.M)}
        self.assertEqual({t:s['target'] for t,s in cfg['sleeves'].items()}, targets)
        self.assertEqual(len(targets), 18)
        self.assertEqual(sum(targets.values()), 100)
        self.assertEqual(cfg['rules']['max_lines'], 18)
        self.assertEqual(cfg['rules']['china_cap_pct'], 10)
        self.assertEqual(cfg['rules']['us_equity_floor_pct'], 25)

    def test_country_bounds_and_equity_only_us_floor(self):
        cfg = {'rules': {'us_equity_floor_pct':25, 'china_cap_pct':10}}
        for us, china, expected in [(25,10,('ESTIMATE','ESTIMATE')), (24.99,10.01,('CHECK','CHECK'))]:
            holdings = [dict(country='United States', bucket='Equity', weight=us),
                        dict(country='United States', bucket='Cash/Derivatives', weight=4),
                        dict(country='China', bucket='Equity', weight=china)]
            checks = allocation_checks(cfg, [], holdings)
            self.assertEqual(tuple(c['status'] for c in checks), expected)
            self.assertEqual(checks[0]['value'], us)


class StalePolicyPreview(unittest.TestCase):
    setUp = test_investing.InvestingTests.setUp
    tearDown = test_investing.InvestingTests.tearDown
    approve = test_investing.InvestingTests.approve

    def test_old_manual_rejected_even_with_new_approval_token(self):
        cfg = json.loads((self.root/'manual.json').read_text())
        cfg['manual_version'] = '1.1 - July 2026'
        (self.root/'manual.json').write_text(json.dumps(cfg))
        self.assertTrue(webdash.report_payload('paper', [])['policy_stale'])
        with patch.object(webdash, 'run_step') as run:
            outcome = webdash.api_execute(self.approve())
            self.assertFalse(outcome['ok'])
            self.assertTrue(outcome['not_submitted'])
            self.assertIn('policy changed', outcome['log'])
            run.assert_not_called()

    def test_matching_policy_version_remains_usable(self):
        cfg = json.loads((self.root/'manual.json').read_text())
        cfg['manual_version'] = 'test'
        (self.root/'manual.json').write_text(json.dumps(cfg))
        self.assertFalse(webdash.report_payload('paper', [])['policy_stale'])
