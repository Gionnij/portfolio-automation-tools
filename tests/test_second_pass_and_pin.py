"""Covers the two behaviour changes: the leftover-cash second pass in the
engine, and the PIN gate that replaced the typed confirmation phrase."""
import copy, json, tempfile, unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import rebalance
import webdash as app

MANUAL = json.loads((Path(__file__).resolve().parent.parent / "manual.json").read_text())
PRICES = {"EXUS": 40.49, "MTPI": 8.38, "QDVB": 16.00, "IMAE": 105.46, "XEON": 150.14,
          "36BZ": 5.12, "BOTZ": 20.41, "GRID": 54.70, "XDW0": 66.95, "SGLD": 363.98,
          "ZPRV": 81.08, "UMDV": 4.74, "XDWH": 52.84, "4COP": 64.32, "NUKL": 48.80,
          "IH2O": 65.63, "IS0C": 51.83}


# A fixed allocation that always exercises the second pass, whatever Giovanni
# does to manual.json. FIX has a gap that clears the minimum but cannot buy one
# whole share (the IMAE artifact); SMALL sits under the minimum entirely.
SYNTHETIC = {
    "manual_version": "test",
    "sleeves": {
        "BIG":   {"name": "Big",   "target": 40.0, "kind": "equity", "thematic": False},
        "MID":   {"name": "Mid",   "target": 30.0, "kind": "equity", "thematic": False},
        "FIX":   {"name": "Fix",   "target": 12.0, "kind": "equity", "thematic": False},
        "SMALL": {"name": "Small", "target":  6.0, "kind": "equity", "thematic": False},
        "TINY":  {"name": "Tiny",  "target":  4.0, "kind": "equity", "thematic": False},
        # 2% target but a EUR 70 share: the smallest order clearing the EUR 100
        # minimum is 2 shares = EUR 140, i.e. 4.7% of a EUR 3,000 book against a
        # 2% target - 2.3x. This is the case the cap exists for.
        "MICRO": {"name": "Micro", "target":  2.0, "kind": "equity", "thematic": False},
        "XEON":  {"name": "Cash",  "target":  6.0, "kind": "stabilizer", "thematic": False},
    },
    "rules": dict(MANUAL["rules"], min_order_eur=100.0, second_pass_max_target_multiple=1.5),
    "semi_pattern": MANUAL.get("semi_pattern", ""),
}
SYN_PRICES = {"BIG": 40.0, "MID": 8.0, "FIX": 130.0, "SMALL": 55.0, "TINY": 20.0,
              "MICRO": 70.0, "XEON": 150.0}


def run_syn(contribution, cap=1.5):
    cfg = copy.deepcopy(SYNTHETIC)
    cfg["rules"]["second_pass_max_target_multiple"] = cap
    snap = {t: (0.0, SYN_PRICES[t]) for t in cfg["sleeves"]}
    return rebalance.prepare(cfg, copy.deepcopy(rebalance.DEFAULT_STATE), snap, contribution)


def run(contribution, held=None, cap=1.5):
    """Priced from PRICES where known, else a plausible default - so the suite
    survives Giovanni changing the sleeve list or the target weights."""
    cfg = copy.deepcopy(MANUAL)
    cfg["rules"]["second_pass_max_target_multiple"] = cap
    snap = {t: (float((held or {}).get(t, 0)), PRICES.get(t, 50.0))
            for t in cfg["sleeves"]}
    return rebalance.prepare(cfg, copy.deepcopy(rebalance.DEFAULT_STATE), snap, contribution)


def value(res):
    return sum(o["qty"] * o["est_price"] for o in res["orders"] if o["side"] == "BUY")


class SecondPassTests(unittest.TestCase):
    def test_leftover_is_deployed_and_never_spends_less(self):
        improved = False
        for c in (1000, 3000, 8000, 20000):
            w, wo = run_syn(c), run_syn(c, cap=0)
            self.assertGreaterEqual(value(w), value(wo),
                                    f"second pass spent less than pass 1 at EUR {c}")
            if value(w) > value(wo):
                improved = True
                self.assertTrue(any(o["reason"].startswith("second pass") for o in w["orders"]))
        self.assertTrue(improved, "second pass deployed nothing at any contribution")

    def test_live_policy_never_spends_less_either(self):
        """Same invariant against the real manual.json, whatever it now says."""
        for c in (1000, 3000, 8000, 20000):
            self.assertGreaterEqual(value(run(c)), value(run(c, cap=0)),
                                    f"second pass spent less under the live policy at EUR {c}")

    def test_the_one_share_artifact_is_fixed_synthetic(self):
        """FIX: gap EUR 120 at a EUR 1,000 contribution, one share EUR 130.
        Pass 1 allocates it and then cannot open it; the second pass must."""
        self.assertNotIn("FIX", [o["ticker"] for o in run_syn(1000, cap=0)["orders"]])
        self.assertIn("FIX", [o["ticker"] for o in run_syn(1000)["orders"]])

    def test_every_second_pass_order_clears_the_minimum(self):
        seen = 0
        for c in (1000, 3000, 8000, 20000):
            for o in run_syn(c)["orders"] + run(c)["orders"]:
                if o["reason"].startswith("second pass"):
                    seen += 1
                    self.assertGreaterEqual(o["qty"] * o["est_price"],
                                            MANUAL["rules"]["min_order_eur"] - 1e-9,
                                            f"{o['ticker']} below the minimum at EUR {c}")
        self.assertTrue(seen, "no second-pass orders to check at any contribution")

    def test_cap_keeps_sleeves_near_target_on_an_empty_book(self):
        CAP = 1.5
        res = run(1000)
        nav = 1000.0
        for o in res["orders"]:
            if o["side"] != "BUY":
                continue
            target = MANUAL["sleeves"][o["ticker"]]["target"]
            self.assertLessEqual(o["qty"] * o["est_price"] / nav * 100, target * CAP + 1e-6,
                                 f"{o['ticker']} overshot its target too far")

    def test_uncapped_would_overshoot_badly(self):
        """Guards the guard: uncapped, a small sleeve blows past its target on an
        empty book. If this stops being true the cap is no longer earning its
        keep - which is worth knowing either way."""
        worst = 0
        for c in (1000, 3000):
            for o in run_syn(c, cap=99)["orders"]:
                if o["side"] != "BUY":
                    continue
                w = (o["qty"] * o["est_price"] / c * 100) / SYNTHETIC["sleeves"][o["ticker"]]["target"]
                worst = max(worst, w)
        self.assertGreater(worst, 2.0, f"uncapped worst overshoot was only {worst:.2f}x target")

    def test_the_cap_blocks_the_case_it_exists_for(self):
        """MICRO uncapped reaches 2.3x its target. With the cap it must not be
        opened at all."""
        capped = [o["ticker"] for o in run_syn(3000)["orders"]]
        uncapped = [o["ticker"] for o in run_syn(3000, cap=99)["orders"]]
        self.assertIn("MICRO", uncapped)
        self.assertNotIn("MICRO", capped)

    def test_cash_sleeve_is_never_topped_up(self):
        for c in (1000, 3000, 8000):
            extra = [o["ticker"] for o in run(c)["orders"] + run_syn(c)["orders"]
                     if o["reason"].startswith("second pass")]
            self.assertNotIn("XEON", extra)

    def test_zero_disables_it(self):
        self.assertFalse([o for o in run(3000, cap=0)["orders"]
                          if o["reason"].startswith("second pass")])


class ContributionSweepTests(unittest.TestCase):
    """The rules are amount-independent: what changes with the contribution is
    how much lands, not which laws apply. Checked across the whole realistic
    range rather than at the two amounts that happened to be tested by hand."""

    AMOUNTS = [100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000,
               7500, 10000, 15000, 25000, 50000, 100000]

    def _check(self, res, contribution, sleeves, cap):
        buys = [o for o in res["orders"] if o["side"] == "BUY"]
        spent = sum(o["qty"] * o["est_price"] for o in buys)
        for o in buys:
            value = o["qty"] * o["est_price"]
            self.assertGreaterEqual(value, MANUAL["rules"]["min_order_eur"] - 1e-9,
                                    f"{o['ticker']} under the minimum at EUR {contribution}")
            self.assertLessEqual(value / contribution * 100,
                                 sleeves[o["ticker"]]["target"] * cap + 1e-6,
                                 f"{o['ticker']} past the cap at EUR {contribution}")
            if o["reason"].startswith("second pass"):
                self.assertNotEqual(o["ticker"], "XEON",
                                    f"cash sleeve topped up at EUR {contribution}")
        self.assertLessEqual(spent, contribution + 1e-9,
                             f"overspent at EUR {contribution}")
        return spent

    def test_invariants_hold_at_every_contribution_live_policy(self):
        for c in self.AMOUNTS:
            spent = self._check(run(c), c, MANUAL["sleeves"], 1.5)
            alone = sum(o["qty"] * o["est_price"] for o in run(c, cap=0)["orders"]
                        if o["side"] == "BUY")
            self.assertGreaterEqual(spent, alone - 1e-9,
                                    f"second pass spent less than pass 1 at EUR {c}")

    def test_invariants_hold_at_every_contribution_synthetic(self):
        for c in self.AMOUNTS:
            self._check(run_syn(c), c, SYNTHETIC["sleeves"], 1.5)

    def test_small_contributions_stage_nothing_rather_than_breaking(self):
        """Below the point where any sleeve's gap reaches the minimum, the right
        answer is an empty plan, not a tiny order."""
        for o in run_syn(100)["orders"]:
            self.assertNotEqual(o["side"], "BUY", "staged a buy it could not fund")


class PinGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(app, "HERE", Path(self.temp.name)); self.patch.start()
        app._pin_state.update(fails=0, until=0.0)

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def test_fails_closed_with_no_pin(self):
        ok, why = app.pin_check("1234")
        self.assertFalse(ok); self.assertIn("no PIN", why)

    def test_correct_and_wrong(self):
        app.pin_store("4821")
        self.assertTrue(app.pin_check("4821")[0])
        self.assertFalse(app.pin_check("0000")[0])

    def test_digits_are_never_written_to_disk(self):
        app.pin_store("4821")
        text = app.pin_file().read_text()
        self.assertNotIn("4821", text)
        self.assertEqual(sorted(json.loads(text)), ["hash", "rounds", "salt"])

    def test_shape_is_enforced(self):
        for bad in ("12", "abcd", "", "1234567890123"):
            with self.assertRaises(ValueError):
                app.pin_store(bad)

    def test_lockout_rejects_even_the_correct_pin(self):
        app.pin_store("4821")
        for _ in range(app.PIN_TRIES):
            app.pin_check("0000")
        ok, why = app.pin_check("4821")
        self.assertFalse(ok); self.assertIn("locked", why)

    def test_changing_it_requires_the_current_pin(self):
        app.pin_store("4821")
        self.assertFalse(app.api_pin({"op": "set", "pin": "9999"})["ok"])
        self.assertTrue(app.api_pin({"op": "set", "pin": "9999", "current": "4821"})["ok"])
        self.assertTrue(app.pin_check("9999")[0])

    def test_execute_refuses_a_wrong_pin_before_doing_anything(self):
        app.pin_store("4821")
        out = app.api_execute({"account": "paper", "confirm": "0000",
                               "selected": [0], "plan_id": "x"})
        self.assertTrue(out["not_submitted"]); self.assertIn("wrong PIN", out["log"])


class OpenOrderTests(unittest.TestCase):
    """Listing and cancelling open orders. Cancel only ever REMOVES orders."""

    def _ib(self, rows, account="DU123"):
        ib = MagicMock()
        ib.managedAccounts.return_value = [account]
        ib.reqAllOpenOrders.return_value = rows
        return ib

    def _row(self, sym, status="PreSubmitted", account="DU123", client=7):
        t = MagicMock()
        t.contract.localSymbol = sym; t.contract.symbol = sym
        t.order.account = account; t.order.action = "BUY"
        t.order.totalQuantity = 5; t.order.lmtPrice = 10.5; t.order.clientId = client
        t.orderStatus.filled = 0; t.orderStatus.status = status
        return t

    def test_list_returns_rows_with_status(self):
        import balances
        ib = self._ib([self._row("EXUS"), self._row("MTPI", "Submitted")])
        with patch.object(balances, "_session", return_value=(ib, MagicMock())), \
             patch.object(balances, "_close"):
            out = balances.list_orders("paper")
        self.assertTrue(out["ok"])
        self.assertEqual([r["symbol"] for r in out["orders"]], ["EXUS", "MTPI"])
        self.assertEqual(out["orders"][1]["status"], "Submitted")

    def test_other_accounts_are_ignored(self):
        import balances
        ib = self._ib([self._row("EXUS"), self._row("XXXX", account="U987")])
        with patch.object(balances, "_session", return_value=(ib, MagicMock())), \
             patch.object(balances, "_close"):
            out = balances.list_orders("paper")
        self.assertEqual([r["symbol"] for r in out["orders"]], ["EXUS"])

    def test_paper_mode_refuses_a_non_paper_account(self):
        import balances
        ib = self._ib([], account="U987")
        with patch.object(balances, "_session", return_value=(ib, MagicMock())), \
             patch.object(balances, "_close"):
            with self.assertRaises(ValueError):
                balances.list_orders("paper")

    def test_cancel_uses_global_cancel_and_reports_the_delta(self):
        import balances
        ib = self._ib([self._row("EXUS"), self._row("MTPI")])
        ib.reqAllOpenOrders.side_effect = [
            [self._row("EXUS"), self._row("MTPI")],   # before
            [],                                        # after
        ]
        with patch.object(balances, "_session", return_value=(ib, MagicMock())), \
             patch.object(balances, "_close"):
            out = balances.cancel_open_orders("paper")
        ib.reqGlobalCancel.assert_called_once()
        self.assertEqual((out["before"], out["cancelled"], out["remaining"]), (2, 2, []))

    def test_cancel_does_nothing_when_there_is_nothing_open(self):
        import balances
        ib = self._ib([])
        with patch.object(balances, "_session", return_value=(ib, MagicMock())), \
             patch.object(balances, "_close"):
            out = balances.cancel_open_orders("paper")
        ib.reqGlobalCancel.assert_not_called()
        self.assertEqual(out["cancelled"], 0)

    def test_cancel_needs_the_pin(self):
        """Cancelling is authorised by the PIN, not a typed word."""
        temp = tempfile.TemporaryDirectory()
        with patch.object(app, "HERE", Path(temp.name)):
            app._pin_state.update(fails=0, until=0.0)
            out = app.api_orders({"account": "paper", "op": "cancel", "pin": "1234"})
            self.assertFalse(out["ok"]); self.assertIn("no PIN", out["log"])
            app.pin_store("4821")
            out = app.api_orders({"account": "paper", "op": "cancel", "pin": "0000"})
            self.assertFalse(out["ok"]); self.assertIn("wrong PIN", out["log"])
        temp.cleanup()


class HoldingsCacheTests(unittest.TestCase):
    """The research page falls back to the last reading when Gateway is down,
    but must never present it as live."""

    def setUp(self):
        import workspace
        self.ws = workspace
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        self.patch = patch.object(workspace, "DATA", self.data); self.patch.start()

    def tearDown(self):
        self.patch.stop(); self.temp.cleanup()

    def _ib(self):
        ib = MagicMock()
        ib.managedAccounts.return_value = ["DU123"]
        item = MagicMock()
        item.position = 10; item.marketPrice = 20.0
        item.contract.conId = 1; item.contract.currency = "EUR"
        ib.portfolio.return_value = [item]
        sid = MagicMock(); sid.tag = "ISIN"; sid.value = "IE0000000001"
        det = MagicMock(); det.contract.conId = 1; det.secIdList = [sid]
        ib.reqContractDetails.return_value = [det]
        return ib

    def test_a_good_read_is_cached_and_marked_live(self):
        with patch.object(self.ws, "with_broker", lambda fn: fn(self._ib())):
            out = self.ws.broker_holdings()
        self.assertFalse(out["stale"])
        self.assertEqual(out["holdings"]["IE0000000001"]["value_eur"], 200.0)
        self.assertTrue((self.data / "holdings.json").exists())

    def test_a_failed_read_returns_the_cache_marked_stale(self):
        with patch.object(self.ws, "with_broker", lambda fn: fn(self._ib())):
            first = self.ws.broker_holdings()
        def boom(fn):
            raise ValueError("Gateway is not running")
        with patch.object(self.ws, "with_broker", boom):
            out = self.ws.broker_holdings()
        self.assertTrue(out["stale"])
        self.assertEqual(out["holdings"], first["holdings"])
        self.assertEqual(out["read_at"], first["read_at"])   # the ORIGINAL time, not now
        self.assertIn("Gateway is not running", out["reason"])

    def test_a_failure_with_no_cache_still_raises(self):
        def boom(fn):
            raise ValueError("Gateway is not running")
        with patch.object(self.ws, "with_broker", boom):
            with self.assertRaises(ValueError):
                self.ws.broker_holdings()
